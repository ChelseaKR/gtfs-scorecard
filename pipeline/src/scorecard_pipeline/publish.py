"""Write versioned scorecard JSON artifacts.

Artifacts are the only interface between pipeline and web app: dated JSON
under data/artifacts/<agency>/, plus latest.json and an index the frontend
uses for the agency picker and trend lines. Publishing is idempotent —
re-running a day overwrites that day's artifact byte-for-byte deterministically.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import functools
import json
import logging
import sys
from pathlib import Path
from typing import Any

import jsonschema

from . import (
    RUBRIC_VERSION,
    SCHEMA_VERSION,
    SCORING_PROFILE_ID,
    SCORING_PROFILE_PROVENANCE,
)
from .badge import render_badge, render_mark
from .comparisons import reader_archive_profile
from .config import Agency, artifacts_dir, repo_root
from .effort_calibration import (
    CALIBRATION_SCHEMA_NOTE,
    agency_episodes,
    stats_from_episodes,
)
from .feed_provenance import (
    FeedSourceProvenance,
    classify_feed_source,
    confidence_source_note,
)
from .fetch import FetchResult
from .fixlog import diff_receipts, load_fixlog_candidates, merge_receipts, reconcile_receipts
from .identity import resolve_published_agency_name
from .metrics import expiry_status, resolve_service_horizon_status
from .score import Scorecard
from .site_shell import CATEGORY_LABELS

log = logging.getLogger(__name__)

# Subdirectories of data/artifacts that hold published aggregates, not agencies.
# They have no per-agency latest.json/dated artifact shape, so anything walking
# the artifacts tree as if every dir were an agency must skip them. "run" holds
# the FIX-11 pipeline run-health summary (run_summary.py), merged there by
# `scorecard run-summary merge` in the collect job.
RESERVED_ARTIFACT_DIRS = frozenset({"rollups", "changes", "run"})

# Measurement-confidence levels, weakest first (EXP-01). Words, never a letter
# or a number, so the read cannot be mistaken for a second grade.
CONFIDENCE_LEVELS = ("provisional", "medium", "high")

# A snapshot older than this at scoring time is read as stale evidence, and the
# confidence level drops one step.
STALE_SNAPSHOT_DAYS = 7


def _join_labels(labels: list[str]) -> str:
    """Plain-language list of category labels ("Freshness and Realtime quality",
    "Freshness, Rider experience, and Realtime quality"), used in confidence
    notes naming what was not measured this run."""
    if len(labels) <= 1:
        return "".join(labels)
    return ", ".join(labels[:-1]) + (f"{',' if len(labels) > 2 else ''} and {labels[-1]}")


def _confidence(
    card: dict[str, Any],
    fetch: FetchResult,
    generated_at: dt.datetime,
    source_provenance: FeedSourceProvenance,
) -> dict[str, Any]:
    """How much of this grade the pipeline could actually measure, and from
    what source (EXP-01, docs/ideation/03-expansions.md).

    A legibility layer on the one grade, never a second grade: the level is a
    word, and low confidence describes our measurement coverage this run, not
    the feed. Derived only from signals the pipeline already records: which
    categories are measured vs not_yet_measured (score.py), the realtime
    sampling depth when realtime was measured (rt.py details), the fetch
    source (fetch.py: origin | mirror | unknown), and the snapshot's age at
    scoring time.
    """
    categories: dict[str, Any] = card["categories"]
    measured = [k for k, c in categories.items() if c.get("status") == "measured"]
    unmeasured = [k for k in categories if k not in measured]
    total = len(categories)
    notes: list[str] = []

    # Breadth of measurement sets the base level; provenance and staleness can
    # only lower it.
    if not unmeasured:
        rank = 2
        notes.append("All four score categories were measured this run.")
    else:
        rank = 1 if len(measured) * 2 >= total else 0
        labels = _join_labels([CATEGORY_LABELS.get(k, k) for k in unmeasured])
        was, does = ("was", "It does") if len(unmeasured) == 1 else ("were", "They do")
        notes.append(f"{labels} {was} not measured this run. {does} not count against the grade.")

    rt_windows = 1 if categories.get("realtime", {}).get("status") == "measured" else 0
    if rt_windows:
        samples = categories["realtime"].get("details", {}).get("samples")
        if samples:
            notes.append(f"Realtime was sampled in one bounded window of {samples} snapshots.")
        else:
            notes.append("Realtime was sampled in one bounded window.")

    if fetch.source in {"mirror", "unknown"}:
        rank -= 1
    notes.append(confidence_source_note(source_provenance, fetch.source))

    feed_age_days = max(0, (generated_at.date() - fetch.fetched_date).days)
    if feed_age_days:
        if feed_age_days > STALE_SNAPSHOT_DAYS:
            rank -= 1
        s = "" if feed_age_days == 1 else "s"
        notes.append(f"The scored snapshot was {feed_age_days} day{s} old at scoring time.")

    return {
        "level": CONFIDENCE_LEVELS[max(0, rank)],
        "measured_categories": len(measured),
        "total_categories": total,
        "fetch_source": fetch.source,
        "rt_windows": rt_windows,
        "feed_age_days": feed_age_days,
        "notes": notes,
    }


def build_artifact(
    agency: Agency,
    fetch: FetchResult,
    scorecard: Scorecard,
    generated_at: dt.datetime,
) -> dict[str, Any]:
    card = scorecard.to_json()
    source_provenance = classify_feed_source(agency)
    rt = card["categories"]["realtime"]
    if rt.get("status") == "not_yet_measured" and agency.rt_note:
        rt["summary"] = agency.rt_note
    validator_version = (
        card["categories"]["correctness"].get("details", {}).get("validator_version")
    )
    # A curator's operating-status note (mainly for long-expired feeds) rides on
    # the agency block when set, so the scorecard and directory can show a
    # human-verified "still running" without re-reading the registry. Omitted
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
    if agency.subdivision_code:
        agency_block["subdivision_code"] = agency.subdivision_code
    if agency.subdivision_name:
        agency_block["subdivision_name"] = agency.subdivision_name
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
        "reader_archive_profile": fetch.reader_archive_profile,
    }
    if fetch.max_attempts is not None:
        fetch_block["max_attempts"] = fetch.max_attempts
    if fetch.origin_error:
        fetch_block["origin_error"] = fetch.origin_error
    # The feed hash and validator still describe the exact raw archive. This
    # optional flag discloses that Scorecard-owned readers used the bounded
    # single-root/filename-whitespace view prepared by fetch.py.
    fetch_block.update(
        {"reader_archive_normalized": True} if fetch.reader_archive_normalized else {}
    )
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        # Provenance: which methodology and which validator produced this grade,
        # so a snapshot is citable and a trend can separate a feed change from a
        # rubric or validator change.
        "rubric_version": RUBRIC_VERSION,
        "scoring_profile": {
            "id": SCORING_PROFILE_ID,
            "rubric_version": RUBRIC_VERSION,
            "provenance": SCORING_PROFILE_PROVENANCE,
        },
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
            # Registry evidence about who publishes the configured URL is
            # distinct from fetch.source, which only says how this run obtained
            # the bytes. Unknown stays explicit instead of being inferred from
            # a successful request.
            "source_provenance": source_provenance,
        },
        "fetch": fetch_block,
        # The measurement-confidence read (EXP-01): what this run could and
        # could not measure, so a reader can tell a fully-measured grade from
        # a provisional one. Additive; schema 1.5.
        "confidence": _confidence(card, fetch, generated_at, source_provenance),
        **card,
    }
    artifact["conformance"] = _current_conformance(artifact)
    return artifact


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
        artifact = json.loads(path.read_text())
        if not isinstance(artifact, dict):
            raise TypeError("artifact root must be an object")
        # Legacy artifacts may use older additive schemas, but every scorecard
        # must still expose the stable identity and history summary fields used
        # by reindex and render. Valid JSON with the wrong shape is corruption,
        # not a reason to abort the whole corpus build.
        _history_entry(artifact)
        str(artifact["agency"]["id"])
        str(artifact["agency"]["name"])
        return artifact
    except (AttributeError, json.JSONDecodeError, KeyError, OSError, TypeError) as exc:
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


def _current_conformance(artifact: dict[str, Any]) -> dict[str, Any]:
    """Derive today's versioned credential without trusting embedded copy."""

    from .conformance import assess
    from .mode_language import adapt_artifact_language

    carrier: dict[str, Any] = {"conformance": assess(artifact).to_dict()}
    if "mode_profile" in artifact:
        carrier["mode_profile"] = artifact["mode_profile"]
    return dict(adapt_artifact_language(carrier)["conformance"])


def _with_current_conformance(artifact: dict[str, Any]) -> dict[str, Any]:
    """Copy an artifact and replace its derived conformance presentation."""

    current = dict(artifact)
    current["conformance"] = _current_conformance(artifact)
    return current


def publish(artifact: dict[str, Any]) -> Path:
    """Validate the artifact against the published schema, then write the dated
    artifact, refresh latest.json, and update the index."""
    artifact = _with_current_conformance(artifact)
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
    fresh_details = artifact.get("categories", {}).get("freshness", {}).get("details", {})
    days = fresh_details.get("days_until_expiry")
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
    # This is derived presentation over scored facts. Recompute even when an
    # artifact embeds an older result so conformance.json and the seal cannot
    # preserve stale or misleading guidance indefinitely.
    conformance = _current_conformance(artifact)
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
    'since your last check' deltas without fetching every dated artifact.

    Rubric version and feed hash make public change views safe to compare: a
    methodology change is not presented as an agency regression, and duplicate
    current feed records can be removed from named corpus views.
    """
    categories = {
        key: cat["score"]
        for key in _CATEGORY_KEYS
        if (cat := artifact.get("categories", {}).get(key, {})).get("status") == "measured"
    }
    # Carry days-until-expiry so the directory and app can split the expired
    # population (recently lapsed vs long dead) without fetching every artifact.
    fresh_details = artifact.get("categories", {}).get("freshness", {}).get("details", {})
    days = fresh_details.get("days_until_expiry")
    profile = artifact.get("scoring_profile") or {}
    return {
        "date": artifact["snapshot_date"],
        "score": artifact["overall"]["score"],
        "grade": artifact["overall"]["grade"],
        "rubric_version": artifact.get("rubric_version"),
        "scoring_profile_id": profile.get("id"),
        "scoring_profile_rubric_version": profile.get("rubric_version"),
        "validator_version": artifact.get("validator_version"),
        "reader_archive_profile": reader_archive_profile(artifact),
        "feed_sha256": artifact.get("feed", {}).get("sha256"),
        "categories": categories,
        "days_until_expiry": days,
        "service_horizon_status": resolve_service_horizon_status(
            fresh_details, artifact.get("snapshot_date")
        ),
    }


_HISTORY_PROVENANCE_FIELDS = (
    "rubric_version",
    "scoring_profile_id",
    "scoring_profile_rubric_version",
    "validator_version",
    "reader_archive_profile",
    "feed_sha256",
)


def _history_provenance_for_point(
    artifact_root: Path, agency_id: str, point: dict[str, Any]
) -> dict[str, Any] | None:
    snapshot_date = str(point.get("date") or "")
    if not snapshot_date:
        return None
    artifact_path = artifact_root / agency_id / f"{snapshot_date}.json"
    if not artifact_path.exists():
        return None
    artifact = _read_artifact(artifact_path)
    if artifact is None:
        return None
    enriched = _history_entry(artifact)
    if str(enriched.get("date")) != snapshot_date:
        return None
    return enriched


def enrich_index_history_provenance(index: dict[str, Any], root: Path | None = None) -> int:
    """Backfill rubric/hash on index points from locally available artifacts.

    Index history predates these comparison-provenance fields. Deploy renders
    hydrate recent dated artifacts without necessarily running ``rebuild_index``;
    enriching in memory keeps the first deployment from suppressing every
    aggregate and change. Missing historical files remain untouched and their
    cross-rubric deltas remain safely suppressed.
    """
    artifact_root = root or artifacts_dir()
    changed = 0
    for agency_id, entry in (index.get("agencies") or {}).items():
        for point in entry.get("history") or []:
            if all(point.get(key) for key in _HISTORY_PROVENANCE_FIELDS):
                continue
            try:
                enriched = _history_provenance_for_point(artifact_root, str(agency_id), point)
            except (AttributeError, KeyError, TypeError) as exc:
                log.warning("skipping malformed history artifact for %s: %s", agency_id, exc)
                continue
            if enriched is None:
                continue
            for key in _HISTORY_PROVENANCE_FIELDS:
                value = enriched.get(key)
                if value is not None and point.get(key) != value:
                    point[key] = value
                    changed += 1
    return changed


def registered_agency_dirs(root: Path, *, log_skipped: bool = False) -> list[Path]:
    """Current agency directories under ``root``, bounded to the loaded registry.

    The S3 artifacts store is additive and outlives registry edits, so a
    hydrated tree can hold directories for agencies that were removed from
    the registry, that have since become aliases of a live successor, or that
    a since-abandoned run published and no registry version ever listed. The
    registry's active canonical entries are the sole source of what is listed
    (docs/listing-policy.md), so walkers must not treat the other directories
    as current listings; cleanup stays a curator decision (`scorecard prune`).
    With no registry loaded (library callers, most unit tests) every directory
    is returned unchanged.
    """
    from .config import AGENCIES

    dirs = sorted(p for p in root.iterdir() if p.is_dir() and p.name not in RESERVED_ARTIFACT_DIRS)
    if not AGENCIES:
        return dirs
    unregistered = [p.name for p in dirs if p.name not in AGENCIES]
    if unregistered and log_skipped:
        log.warning(
            "skipping %d artifact directories with no registry entry"
            " (run `scorecard prune` to review): %s",
            len(unregistered),
            ", ".join(unregistered[:10]) + (", ..." if len(unregistered) > 10 else ""),
        )
    noncanonical = [
        p.name for p in dirs if p.name in AGENCIES and not AGENCIES[p.name].is_canonical_feed
    ]
    if noncanonical and log_skipped:
        log.warning(
            "skipping %d retired/noncanonical artifact directories"
            " (history remains available for reproducibility): %s",
            len(noncanonical),
            ", ".join(noncanonical[:10]) + (", ..." if len(noncanonical) > 10 else ""),
        )
    return [p for p in dirs if p.name in AGENCIES and AGENCIES[p.name].is_canonical_feed]


def _dated_reindex_artifacts(
    agency_dir: Path,
) -> tuple[dict[str, dict[str, Any]], set[str]]:
    """Readable local dated artifacts whose path and payload identity agree."""
    paths = sorted(agency_dir.glob("[0-9]" * 4 + "-[0-9][0-9]-[0-9][0-9].json"))
    present_dates = {path.stem for path in paths}
    artifacts: dict[str, dict[str, Any]] = {}
    for path in paths:
        artifact = _read_artifact(path)
        if artifact is None:
            continue
        try:
            path_date = dt.date.fromisoformat(path.stem)
            artifact_date = str(artifact["snapshot_date"])
            parsed_artifact_date = dt.date.fromisoformat(artifact_date)
            artifact_id = str(artifact["agency"]["id"])
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("ignoring malformed dated artifact %s: %s", path, exc)
            continue
        if (
            path_date.isoformat() != path.stem
            or parsed_artifact_date.isoformat() != artifact_date
            or artifact_date != path.stem
            or artifact_id != agency_dir.name
        ):
            log.warning(
                "ignoring mismatched dated artifact %s (id=%s, date=%s)",
                path,
                artifact_id,
                artifact_date,
            )
            continue
        artifacts[path.stem] = artifact
    return artifacts, present_dates


def _current_reindex_artifact(
    agency_dir: Path,
) -> tuple[dict[str, Any], str, dict[str, Any]] | None:
    """A structurally valid latest artifact, its date, and compact summary."""
    latest_path = agency_dir / "latest.json"
    if not latest_path.exists():
        return None
    latest = _read_artifact(latest_path)
    if latest is None:
        return None
    try:
        latest_id = str(latest["agency"]["id"])
        latest_date = str(latest["snapshot_date"])
        parsed_date = dt.date.fromisoformat(latest_date)
    except (KeyError, TypeError, ValueError) as exc:
        log.warning("ignoring malformed current artifact %s: %s", latest_path, exc)
        return None
    if parsed_date.isoformat() != latest_date or latest_id != agency_dir.name:
        log.warning(
            "ignoring mismatched current artifact %s (id=%s, date=%s)",
            latest_path,
            latest_id,
            latest_date,
        )
        return None
    return latest, latest_date, _history_entry(latest)


def _reindex_artifact_sequence(
    agency_dir: Path, prior_current: dict[str, Any] | None
) -> tuple[list[dict[str, Any]], set[str]]:
    """Resolve local dated files plus the verified authoritative current.

    A hydrated latest that matches the prior index tail preserves a skipped
    feed when its dated object is absent locally. A matching latest/dated pair
    may replace the prior tail on the same date after a methodology re-score.
    """
    artifacts, present_dates = _dated_reindex_artifacts(agency_dir)
    prior_date = str((prior_current or {}).get("date") or "")
    accepted_same_day_overlay = False
    current = _current_reindex_artifact(agency_dir)
    if current is not None:
        latest, latest_date, latest_history = current
        matches_prior = bool(
            prior_current is not None
            and latest_date == prior_date
            and all(latest_history.get(field) == value for field, value in prior_current.items())
        )
        matches_dated = artifacts.get(latest_date) == latest
        if latest_date >= max(artifacts, default="") and (
            matches_prior or matches_dated or (prior_current is None and not artifacts)
        ):
            artifacts[latest_date] = latest
            present_dates.add(latest_date)
            accepted_same_day_overlay = bool(
                matches_dated
                and prior_current is not None
                and latest_date == prior_date
                and not matches_prior
            )

    newest_date = max(artifacts, default="")
    if prior_date and newest_date < prior_date:
        raise RuntimeError(
            f"authoritative current artifact missing for {agency_dir.name}: "
            f"index ends at {prior_date}, available artifacts end at {newest_date or 'none'}"
        )
    if prior_current is not None and newest_date == prior_date:
        current_summary = _history_entry(artifacts[newest_date])
        mismatch = any(
            current_summary.get(field) != value for field, value in prior_current.items()
        )
        if mismatch and not accepted_same_day_overlay:
            raise RuntimeError(f"authoritative latest/index summary mismatch for {agency_dir.name}")
    return [artifacts[date] for date in sorted(artifacts)], present_dates


def rebuild_index() -> Path:
    """Rebuild index.json, and reconcile each agency's latest.json + badge, from
    every dated artifact on disk.

    The sharded daily run (docs/roadmap.md) scores agencies in parallel jobs.
    Each shard checks out the whole repo and uploads its entire data/artifacts
    tree, so when the shard artifacts are merged the dated files union cleanly.
    The collect job first hydrates each durable current artifact and its compact
    index from S3, then overlays newly scored shard files. This step verifies
    that current pair, accepts a same-day latest/dated replacement from a shard,
    and derives latest.json plus badges without letting bounded checkout history
    roll an unchanged feed backward.

    Only registered agencies are indexed (see :func:`registered_agency_dirs`);
    indexing whatever is on disk let unlisted S3 directories resurface as live
    listings after the S3 source-of-truth cutover.
    """
    from .config import AGENCIES

    root = artifacts_dir()
    index_path = root / "index.json"
    previous_index: dict[str, Any] = {"agencies": {}}
    if index_path.exists():
        with contextlib.suppress(json.JSONDecodeError, OSError):
            previous_index = json.loads(index_path.read_text())
    index: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "agencies": {}}
    if not root.exists():
        _write_json(root / "index.json", index)
        return root / "index.json"

    # Finding-clearance episodes accumulate across every agency in this one walk,
    # so the corpus-level effort-calibration.json costs no extra artifact reads
    # (effort_calibration.py). The calibration itself requires a complete,
    # unchanged producer contract and makes no claim about who changed a feed.
    all_episodes: list[Any] = []
    for agency_dir in registered_agency_dirs(root, log_skipped=True):
        name = agency_dir.name
        operating_note = ""
        prior_history = (
            previous_index.get("agencies", {}).get(agency_dir.name, {}).get("history", [])
        )
        prior_current = prior_history[-1] if prior_history else None
        agency_artifacts, present_dates = _reindex_artifact_sequence(agency_dir, prior_current)
        history = [_history_entry(artifact) for artifact in agency_artifacts]
        receipts: list[dict[str, Any]] = []
        previous_artifact: dict[str, Any] | None = None
        for artifact in agency_artifacts:
            # A finding present one run and gone the next is a fix receipt
            # (fixlog.py); this walk is already reading every available artifact
            # in order, so the diff costs nothing extra.
            receipts.extend(diff_receipts(previous_artifact, artifact))
            previous_artifact = artifact
        artifacts_by_date = {
            str(artifact.get("snapshot_date") or ""): artifact for artifact in agency_artifacts
        }
        existing_receipts = reconcile_receipts(
            load_fixlog_candidates(agency_dir), artifacts_by_date
        )
        all_receipts = merge_receipts(existing_receipts, receipts)
        fixlog_path = agency_dir / "fixlog.json"
        if all_receipts:
            _write_json(fixlog_path, {"receipts": all_receipts})
        elif fixlog_path.exists():
            # A legacy or contradictory receipt must not remain public merely
            # because there was nothing valid to overwrite it with this run.
            fixlog_path.unlink()
        newest = agency_artifacts[-1] if agency_artifacts else None
        if newest is not None:
            name = resolve_published_agency_name(
                agency_dir.name,
                registry_name=(
                    AGENCIES[agency_dir.name].name if agency_dir.name in AGENCIES else ""
                ),
                artifact_name=str(newest["agency"].get("name") or ""),
            )
            operating_note = newest["agency"].get("operating_note", "")
        # Episodes are derived per agency from its own dated sequence, then
        # pooled corpus-wide for the calibration stats.
        all_episodes.extend(agency_episodes(agency_artifacts))
        if history and newest is not None:
            # Re-derive mutable current surfaces without rewriting immutable
            # dated evidence. This also migrates versioned presentation fields
            # (such as conformance guidance) for unchanged or unreachable feeds.
            current = _with_current_conformance(newest)
            _write_json(agency_dir / "latest.json", current)
            _write_badge(agency_dir, current)
            _write_mark(agency_dir, current)
            # S3 is the durable dated-history store. A clean CI checkout keeps
            # only the repository's cutover snapshot plus the newest two days,
            # while index.json carries the compact complete trend. Preserve
            # entries whose dated file is simply absent locally; an unreadable
            # file that is present is still dropped so corruption stays visible.
            by_date = {
                str(item.get("date")): item
                for item in prior_history
                if item.get("date") and str(item.get("date")) not in present_dates
            }
            by_date.update({str(item["date"]): item for item in history})
            merged_history = [by_date[date] for date in sorted(by_date)]
            entry: dict[str, Any] = {"name": name, "history": merged_history}
            if operating_note:
                entry["operating_note"] = operating_note
            index["agencies"][agency_dir.name] = entry

    _write_calibration(stats_from_episodes(all_episodes))

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
    from .config import AGENCIES

    index_path = artifacts_dir() / "index.json"
    index: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "agencies": {}}
    if index_path.exists():
        index = json.loads(index_path.read_text())

    # A curator may retain a retired endpoint as an alias so its dated evidence
    # remains reproducible. A manual single-agency re-score may therefore still
    # write that evidence, but it must never revive the retired feed as a current
    # scorecard. Full reindex applies the same policy through
    # registered_agency_dirs().
    agency = AGENCIES.get(agency_id)
    if agency is not None and not agency.is_canonical_feed:
        index.setdefault("agencies", {}).pop(agency_id, None)
        _write_json(index_path, index)
        return

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
    entry: dict[str, Any] = {
        "name": resolve_published_agency_name(
            agency_id,
            registry_name=AGENCIES[agency_id].name if agency_id in AGENCIES else "",
            artifact_name=str(artifact["agency"].get("name") or ""),
        ),
        "history": history,
    }
    if artifact["agency"].get("operating_note"):
        entry["operating_note"] = artifact["agency"]["operating_note"]
    index["agencies"][agency_id] = entry
    _write_json(index_path, index)
