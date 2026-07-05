"""Write versioned scorecard JSON artifacts.

Artifacts are the only interface between pipeline and web app: dated JSON
under data/artifacts/<agency>/, plus latest.json and an index the frontend
uses for the agency picker and trend lines. Publishing is idempotent —
re-running a day overwrites that day's artifact byte-for-byte deterministically.
"""

from __future__ import annotations

import datetime as dt
import functools
import json
import logging
import sys
from pathlib import Path
from typing import Any

import jsonschema

from . import RUBRIC_VERSION, SCHEMA_VERSION
from .badge import render_badge, render_mark
from .config import Agency, artifacts_dir, repo_root
from .effort_calibration import (
    CALIBRATION_SCHEMA_NOTE,
    agency_episodes,
    stats_from_episodes,
)
from .fetch import FetchResult
from .fixlog import diff_receipts, load_fixlog, merge_receipts
from .metrics import expiry_status
from .score import Scorecard

log = logging.getLogger(__name__)

# Subdirectories of data/artifacts that hold published aggregates, not agencies.
# They have no per-agency latest.json/dated artifact shape, so anything walking
# the artifacts tree as if every dir were an agency must skip them.
RESERVED_ARTIFACT_DIRS = frozenset({"rollups", "changes"})


def build_artifact(
    agency: Agency,
    fetch: FetchResult,
    scorecard: Scorecard,
    generated_at: dt.datetime,
) -> dict[str, Any]:
    card = scorecard.to_json()
    rt = card["categories"]["realtime"]
    if rt.get("status") == "not_yet_measured" and agency.rt_note:
        rt["summary"] = agency.rt_note
    validator_version = (
        card["categories"]["correctness"].get("details", {}).get("validator_version")
    )
    # A curator's operating-status note (mainly for long-expired feeds) rides on
    # the agency block when set, so the scorecard and directory can show a
    # human-verified "still running" without re-reading agencies.yaml. Omitted
    # when empty so artifacts for agencies without a note stay byte-identical.
    agency_block: dict[str, Any] = {"id": agency.id, "name": agency.name}
    # Country rides on the block only when it is not the US default, so US
    # artifacts stay byte-identical; a non-US agency carries it so the page, SPA,
    # and API skip the US-only NTD surfaces (ADR 0026).
    if agency.country != "US":
        agency_block["country"] = agency.country
    if agency.operating_note:
        agency_block["operating_note"] = agency.operating_note
    if agency.ntd_note:
        agency_block["ntd_note"] = agency.ntd_note
    # Persist the curator-set state so state-selected rollups and exports work
    # offline, without re-deriving location from the Mobility Database catalog.
    if agency.state:
        agency_block["state"] = agency.state
    # Fetch provenance: how the graded bytes were obtained — origin vs the
    # Mobility Database mirror, the URL that actually served them, and the
    # User-Agent presented — so a grade is a citable record and a mirror-scored
    # snapshot is distinguishable from an origin fetch. Additive to the schema
    # (consumers tolerate new fields, docs/api.md); optional fields are omitted
    # when unknown so artifacts stay byte-stable.
    fetch_block: dict[str, Any] = {
        "source": fetch.source,
        # A snapshot from before provenance recording has no final_url on disk;
        # the configured feed URL is the best available statement of the fetch.
        "final_url": fetch.final_url or fetch.url,
        "user_agent": fetch.user_agent,
    }
    if fetch.max_attempts is not None:
        fetch_block["max_attempts"] = fetch.max_attempts
    if fetch.origin_error:
        fetch_block["origin_error"] = fetch.origin_error
    return {
        "schema_version": SCHEMA_VERSION,
        # Provenance: which methodology and which validator produced this grade,
        # so a snapshot is citable and a trend can separate a feed change from a
        # rubric or validator change.
        "rubric_version": RUBRIC_VERSION,
        "validator_version": validator_version,
        "agency": agency_block,
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "snapshot_date": fetch.fetched_date.isoformat(),
        "feed": {
            "static_url": fetch.url,
            "sha256": fetch.sha256,
            "size_bytes": fetch.size_bytes,
            "license_note": agency.license_note,
            "reachable": True,
        },
        "fetch": fetch_block,
        **card,
    }


def _write_atomic(path: Path, text: str) -> None:
    """Write text via a temp file + atomic replace, so an interrupted run never
    leaves a truncated artifact the renderer/web app would fail to parse."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    tmp.replace(path)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_atomic(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _read_artifact(path: Path) -> dict[str, Any] | None:
    """Parse one dated artifact, tolerating a single unreadable file.

    At national scale (~1,200 agencies, thousands of dated files) one corrupt
    or partially written JSON must not abort the whole daily reindex and drop
    every agency's refresh. Mirror the per-agency scoring tolerance: warn,
    naming the file so it can be found and fixed, and skip it.
    """
    try:
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError) as exc:
        print(f"::warning title=unreadable artifact::skipping {path}: {exc}", file=sys.stderr)
        return None


def _artifact_schema_path() -> Path:
    """Locate web/schemas/artifact.schema.json.

    Prefer the configured repo root (the production checkout). Tests point
    SCORECARD_ROOT at a throwaway directory that has no web/ tree, so fall back
    to the source checkout this module lives in — validation must stay enforced
    there too, never silently skipped.
    """
    for root in (repo_root(), Path(__file__).resolve().parents[3]):
        path = root / "web" / "schemas" / "artifact.schema.json"
        if path.exists():
            return path
    raise FileNotFoundError("web/schemas/artifact.schema.json not found")


@functools.lru_cache(maxsize=1)
def _artifact_validator() -> jsonschema.Draft202012Validator:
    schema = json.loads(_artifact_schema_path().read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def validate_artifact(artifact: dict[str, Any]) -> None:
    """Machine-enforce the per-agency data contract (web/schemas/artifact.schema.json).

    Raises jsonschema.ValidationError on the first mismatch. Called by publish()
    so no collect run can write an artifact that violates the published schema:
    a shape change must ship with a schema update (and version bump), never by
    consumers noticing.
    """
    _artifact_validator().validate(artifact)


def publish(artifact: dict[str, Any]) -> Path:
    """Validate the artifact against the published schema, then write the dated
    artifact, refresh latest.json, and update the index."""
    validate_artifact(artifact)
    agency_id = str(artifact["agency"]["id"])
    date = str(artifact["snapshot_date"])
    agency_dir = artifacts_dir() / agency_id

    dated = agency_dir / f"{date}.json"
    _write_json(dated, artifact)
    _write_json(agency_dir / "latest.json", artifact)
    _write_badge(agency_dir, artifact)
    _write_mark(agency_dir, artifact)
    _update_index(agency_id, artifact)
    return dated


# Shields.io endpoint colors by grade, so a consumer can render a custom-styled
# badge from badge.json with the same color language as the SVG.
_BADGE_COLORS = {"A": "brightgreen", "B": "green", "C": "yellow", "D": "orange", "F": "red"}


def _write_badge(agency_dir: Path, artifact: dict[str, Any]) -> None:
    """Write the embeddable grade badge next to the artifacts: an SVG plus a
    Shields.io endpoint JSON so consumers can style their own badge."""
    overall = artifact["overall"]
    days = (
        artifact.get("categories", {})
        .get("freshness", {})
        .get("details", {})
        .get("days_until_expiry")
    )
    grade = str(overall["grade"])
    status = expiry_status(days)
    svg = render_badge(grade, float(overall["score"]), expiry_status=status)
    _write_atomic(agency_dir / "badge.svg", svg)

    message = f"{grade} {overall['score']}"
    if status in ("lapsed", "stale"):
        message += " · feed expired"
    elif status == "expiring_soon":
        message += " · expires soon"
    endpoint = {
        "schemaVersion": 1,
        "label": "GTFS quality",
        "message": message,
        "color": _BADGE_COLORS.get(grade, "lightgrey"),
    }
    _write_atomic(agency_dir / "badge.json", json.dumps(endpoint, indent=2) + "\n")


def _write_mark(agency_dir: Path, artifact: dict[str, Any]) -> None:
    """Write the conformance credential next to the artifacts.

    Always writes conformance.json (the machine-readable result). The mark.svg
    seal is written only when the feed earns the mark, and a stale seal is
    removed when it no longer does, so the presence of the file is the credential.
    """
    conformance = artifact.get("conformance")
    if conformance is None:
        from .conformance import assess

        conformance = assess(artifact).to_dict()
    _write_atomic(agency_dir / "conformance.json", json.dumps(conformance, indent=2) + "\n")
    mark_path = agency_dir / "mark.svg"
    if conformance.get("awarded"):
        _write_atomic(mark_path, render_mark())
    elif mark_path.exists():
        # A revoked credential leaves a trace: contracts and procurement pages
        # reference the mark as a standing condition, so its disappearance must
        # be auditable in the run log, not silent.
        failed = [
            str(c.get("key", ""))
            for c in conformance.get("criteria", [])
            if not c.get("met", False)
        ]
        why = ", ".join(failed) or "criteria no longer met"
        log.warning("conformance mark revoked for %s (%s)", agency_dir.name, why)
        print(
            f"::notice title=conformance mark revoked::{agency_dir.name} no longer meets: {why}",
            file=sys.stderr,
        )
        mark_path.unlink()


_CATEGORY_KEYS = ("correctness", "freshness", "completeness", "realtime")


def _history_entry(artifact: dict[str, Any]) -> dict[str, Any]:
    """One trend point for index.json: overall score/grade plus the score of
    each measured category, so the web app can show per-category trends and
    'since your last check' deltas without fetching every dated artifact."""
    categories = {
        key: cat["score"]
        for key in _CATEGORY_KEYS
        if (cat := artifact.get("categories", {}).get(key, {})).get("status") == "measured"
    }
    # Carry days-until-expiry so the directory and app can split the expired
    # population (recently lapsed vs long dead) without fetching every artifact.
    days = (
        artifact.get("categories", {})
        .get("freshness", {})
        .get("details", {})
        .get("days_until_expiry")
    )
    return {
        "date": artifact["snapshot_date"],
        "score": artifact["overall"]["score"],
        "grade": artifact["overall"]["grade"],
        "categories": categories,
        "days_until_expiry": days,
    }


def rebuild_index() -> Path:
    """Rebuild index.json, and reconcile each agency's latest.json + badge, from
    every dated artifact on disk.

    The sharded daily run (docs/roadmap.md) scores agencies in parallel jobs.
    Each shard checks out the whole repo and uploads its entire data/artifacts
    tree, so when the shard artifacts are merged the dated files union cleanly
    (unique paths) but the per-agency latest.json and badge.svg can be clobbered
    by a stale copy from a shard that did not score that agency. The dated files
    are the source of truth; this collect step derives latest.json and the badge
    from the newest dated artifact per agency, making the result independent of
    merge order.
    """
    root = artifacts_dir()
    index: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "agencies": {}}
    if not root.exists():
        _write_json(root / "index.json", index)
        return root / "index.json"

    # Runs-to-clear episodes accumulate across every agency in this one walk, so
    # the corpus-level effort-calibration.json costs no extra artifact reads
    # (effort_calibration.py).
    all_episodes: list[Any] = []
    for agency_dir in sorted(
        p for p in root.iterdir() if p.is_dir() and p.name not in RESERVED_ARTIFACT_DIRS
    ):
        history = []
        name = agency_dir.name
        operating_note = ""
        newest: dict[str, Any] | None = None
        receipts: list[dict[str, str]] = []
        agency_artifacts: list[dict[str, Any]] = []
        for dated in sorted(agency_dir.glob("[0-9]" * 4 + "-[0-9][0-9]-[0-9][0-9].json")):
            artifact = _read_artifact(dated)
            if artifact is None:
                continue
            name = artifact["agency"]["name"]
            operating_note = artifact["agency"].get("operating_note", "")
            history.append(_history_entry(artifact))
            # A finding present one run and gone the next is a fix receipt
            # (fixlog.py); this walk is already reading every dated artifact in
            # order, so the diff costs nothing extra.
            receipts.extend(diff_receipts(newest, artifact))
            agency_artifacts.append(artifact)
            newest = artifact
        # Episodes are derived per agency from its own dated sequence, then
        # pooled corpus-wide for the calibration stats.
        all_episodes.extend(agency_episodes(agency_artifacts))
        if history and newest is not None:
            # Re-derive latest.json, badge, and mark so a clobbered copy is repaired.
            _write_json(agency_dir / "latest.json", newest)
            _write_badge(agency_dir, newest)
            _write_mark(agency_dir, newest)
            # Merge, never replace: a receipt survives the dated artifacts it
            # came from, and re-running collect duplicates nothing.
            all_receipts = merge_receipts(load_fixlog(agency_dir), receipts)
            if all_receipts:
                _write_json(agency_dir / "fixlog.json", {"receipts": all_receipts})
            entry: dict[str, Any] = {"name": name, "history": history}
            if operating_note:
                entry["operating_note"] = operating_note
            index["agencies"][agency_dir.name] = entry

    _write_calibration(stats_from_episodes(all_episodes))

    index_path = root / "index.json"
    _write_json(index_path, index)
    return index_path


def _write_calibration(stats: dict[str, Any]) -> None:
    """Write the corpus-level effort-calibration.json.

    Written under data/ (a sibling of the artifacts tree) because it is a
    cross-agency aggregate, not a per-agency file. Ordering is deterministic
    (sort_keys) so re-running collect over unchanged history is a no-op; the
    generated date is the only field that moves day to day.
    """
    payload = {
        "schema_note": CALIBRATION_SCHEMA_NOTE,
        "generated": dt.date.today().isoformat(),
        "codes": stats,
    }
    _write_json(repo_root() / "data" / "effort-calibration.json", payload)


def _update_index(agency_id: str, artifact: dict[str, Any]) -> None:
    """Maintain data/artifacts/index.json: per-agency history of
    (date, score, grade) so the frontend can draw trends without fetching
    every artifact."""
    index_path = artifacts_dir() / "index.json"
    index: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "agencies": {}}
    if index_path.exists():
        index = json.loads(index_path.read_text())

    # Reconcile this agency's history from the dated artifacts actually on disk,
    # rather than appending to whatever the index held. This keeps an incremental
    # publish identical to a full rebuild_index for that agency, so deleted dates
    # drop and the two index code paths can't disagree.
    agency_dir = artifacts_dir() / agency_id
    history = [
        _history_entry(art)
        for dated in sorted(agency_dir.glob("[0-9]" * 4 + "-[0-9][0-9]-[0-9][0-9].json"))
        if (art := _read_artifact(dated)) is not None
    ]
    entry: dict[str, Any] = {"name": artifact["agency"]["name"], "history": history}
    if artifact["agency"].get("operating_note"):
        entry["operating_note"] = artifact["agency"]["operating_note"]
    index["agencies"][agency_id] = entry
    _write_json(index_path, index)
