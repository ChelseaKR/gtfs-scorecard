"""Program rollup artifacts: a portfolio view across many agencies.

The roadmap's view for the second core user (docs/roadmap.md): a district
liaison or statewide program staffer supports many agencies and wants one
screen sorted by what needs attention, with the same fix-framed language the
per-agency page uses. Rollups are computed from the published artifacts and
written as static JSON, exactly like everything else the web app reads.

Rollups are defined in an optional rollups.yaml at the repo root (named groups
with explicit member ids, or `all: true`). With no config file, a single
"all tracked agencies" rollup is produced, so the feature works the moment a
second agency exists.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from . import SCHEMA_VERSION
from .alerts import build_digest
from .config import artifacts_dir, repo_root
from .metrics import expiry_status
from .ntd import assess_shapes_readiness
from .publish import RESERVED_ARTIFACT_DIRS, _write_json
from .ridership import annual_trips_for


@dataclass(frozen=True)
class Rollup:
    id: str
    name: str
    member_ids: tuple[str, ...]  # empty means "all agencies with artifacts"
    state: str | None = None  # auto-include every agency in this state (no member list)


def _available_agency_ids() -> list[str]:
    root = artifacts_dir()
    if not root.exists():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir() and p.name not in RESERVED_ARTIFACT_DIRS and (p / "latest.json").exists()
    )


def load_rollups(path: Path | None = None) -> list[Rollup]:
    """Read rollups.yaml, or fall back to a single all-agencies rollup."""
    config_path = path or repo_root() / "rollups.yaml"
    if not config_path.exists():
        return [Rollup(id="all", name="All tracked agencies", member_ids=())]

    raw = yaml.safe_load(config_path.read_text()) or {}
    rollups: list[Rollup] = []
    for entry in raw.get("rollups", []):
        state = entry.get("state")
        members = () if (entry.get("all") or state) else tuple(entry.get("members", []))
        rollups.append(
            Rollup(
                id=str(entry["id"]),
                name=str(entry["name"]),
                member_ids=members,
                state=str(state) if state else None,
            )
        )
    return rollups or [Rollup(id="all", name="All tracked agencies", member_ids=())]


def _load_latest(agency_id: str) -> dict[str, Any] | None:
    path = artifacts_dir() / agency_id / "latest.json"
    try:
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    except (FileNotFoundError, ValueError):
        return None


def _catalog_states() -> dict[str, str]:
    """Agency-id to state from the published catalog.json fallback.

    Artifacts don't yet carry state (that persists once agencies.yaml has state
    fields populated). Until then, read from catalog.json which render-site
    already derives via the Mobility Database. Returns {} when the file is absent."""
    path = repo_root() / "web" / "catalog.json"
    try:
        data = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}
    return {a["id"]: a["state"] for a in data.get("agencies", []) if a.get("id") and a.get("state")}


def _agency_ids_in_state(state: str) -> list[str]:
    """Available agencies whose state matches, checked against each agency's
    artifact first (once agencies.yaml has state fields) then catalog.json."""
    want = state.strip().upper()
    fallback = {k: v.upper() for k, v in _catalog_states().items()}
    ids = []
    for agency_id in _available_agency_ids():
        latest = _load_latest(agency_id)
        raw_state = latest.get("agency", {}).get("state", "") if latest else ""
        artifact_state = str(raw_state).strip().upper()
        resolved = artifact_state or fallback.get(agency_id, "")
        if resolved == want:
            ids.append(agency_id)
    return ids


def resolve_member_ids(rollup: Rollup) -> list[str]:
    """The agency ids a rollup covers.

    Explicit members when the rollup lists them, otherwise every agency in its
    state, otherwise every agency with a published artifact. Shared by the
    rollup artifact build and the portfolio digest so a cohort means the same
    set of agencies in both."""
    if rollup.member_ids:
        return list(rollup.member_ids)
    if rollup.state:
        return _agency_ids_in_state(rollup.state)
    return _available_agency_ids()


def _shapes_status(latest: dict[str, Any]) -> str | None:
    """This agency's current shapes.txt (NTD RY2026) readiness status, or None
    when it does not apply: a non-US agency (NTD is a US-federal FTA program,
    ADR 0026) or an artifact that predates the check. Recomputed from the
    stored trip counts rather than trusting the stored status/prose directly,
    the same pattern render_site.py's _current_shapes_readiness uses, so a
    wording or threshold fix reaches every rollup without a rescore."""
    if latest.get("agency", {}).get("country", "US") != "US":
        return None
    shapes = latest.get("shapes_readiness")
    if not shapes:
        return None
    total = shapes.get("total_trips")
    with_shape = shapes.get("trips_with_shape")
    if isinstance(total, int) and isinstance(with_shape, int):
        return assess_shapes_readiness(total, with_shape).status
    status = shapes.get("status")
    return str(status) if status is not None else None


def build_rollup(
    rollup: Rollup,
    generated_at: dt.datetime,
    attention: dict[str, str] | None = None,
    ridership: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Aggregate member artifacts into one rollup payload.

    Members are sorted worst-score-first so the agencies needing attention sit
    at the top, which is the order a liaison reads them in. "Needs attention"
    means something is actually wrong or about to break — the feed is expiring
    or the grade regressed (the same signal that triggers an email digest) —
    not merely "below a B", so the flag points at the calls worth making first.
    Common fixes are counted across members so a program can see the one export
    setting that would lift several agencies at once.

    When an NTD ridership snapshot is supplied (ADR 0021,
    docs/decisions/0021-ridership-weighting.md), the attention group is ordered
    by annual rider-trips first, so a high-ridership feed that is expiring ranks
    above a tiny one before falling back to score — the same call is worth making
    first when more riders depend on it. This is a tiebreak on ordering only, not
    a re-scoring: the framing stays "worst first, here to help", never a ranking
    of agencies against each other. Non-attention members keep their plain
    worst-score-first order, and with no ridership data the order is unchanged.
    """
    attention = attention or {}
    member_ids = resolve_member_ids(rollup)
    members: list[dict[str, Any]] = []
    fix_counter: Counter[tuple[str, str]] = Counter()

    for agency_id in member_ids:
        latest = _load_latest(agency_id)
        if not latest or "overall" not in latest:
            # Skip a missing or malformed (non-agency, partial) artifact rather
            # than crash the whole rollup on it.
            continue
        overall = latest["overall"]
        fixes = latest.get("top_fixes", [])
        for fix in fixes:
            fix_counter[(fix.get("code", ""), fix.get("fix", ""))] += 1
        days = (
            latest.get("categories", {})
            .get("freshness", {})
            .get("details", {})
            .get("days_until_expiry")
        )
        ntd_id = (latest.get("ntd_id_alignment") or {}).get("ntd_id")
        members.append(
            {
                "id": latest["agency"]["id"],
                "name": latest["agency"]["name"],
                "score": overall["score"],
                "grade": overall["grade"],
                "snapshot_date": latest["snapshot_date"],
                "needs_attention": agency_id in attention,
                "attention_reason": attention.get(agency_id),
                "days_until_expiry": days,
                "expiry_status": expiry_status(days),
                "top_fix": fixes[0]["fix"] if fixes else None,
                "shapes_status": _shapes_status(latest),
                "annual_trips": annual_trips_for({"ntd_id": ntd_id}, ridership),
            }
        )

    # Attention-needing agencies first (a call worth making). Within that group,
    # order by annual rider-trips descending when ridership data is present (ADR
    # 0021) so a high-ridership feed outranks a tiny one, then worst-score-first;
    # non-attention members stay plain worst-score-first. With no ridership data
    # every annual_trips is None (treated as 0), leaving the order unchanged.
    def _sort_key(m: dict[str, Any]) -> tuple[int, int, float, str]:
        if m["needs_attention"]:
            return (0, -(m["annual_trips"] or 0), m["score"], m["id"])
        return (1, 0, m["score"], m["id"])

    members.sort(key=_sort_key)
    scores = [float(m["score"]) for m in members]
    grades = Counter(str(m["grade"]) for m in members)
    common = [
        {"code": code, "fix": fix, "agencies": n}
        for (code, fix), n in fix_counter.most_common()
        if n > 1
    ]

    # Expired feeds are the program's clearest worklist, split the same way the
    # public directory splits them: lapsed (expired within a year, likely still
    # running) versus stale (expired over a year, the source went quiet).
    lapsed = sum(1 for m in members if m["expiry_status"] == "lapsed")
    stale = sum(1 for m in members if m["expiry_status"] == "stale")

    # shapes.txt (NTD RY2026) readiness across the cohort, the liaison-facing
    # half of the per-agency check (03-A1). "not_measured" folds together a
    # non-US member and an artifact that predates the check — both mean "no
    # signal yet," which is what a liaison scanning the summary cares about.
    shapes_statuses = [m["shapes_status"] for m in members if m["shapes_status"]]
    shapes_counts = Counter(shapes_statuses)
    shapes_readiness = {
        "ready": shapes_counts.get("ready", 0),
        "at_risk": shapes_counts.get("at_risk", 0),
        "not_ready": shapes_counts.get("not_ready", 0),
        "not_measured": len(members) - len(shapes_statuses),
        "total": len(members),
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "rollup": {"id": rollup.id, "name": rollup.name},
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "agency_count": len(members),
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        "grade_distribution": {g: grades[g] for g in sorted(grades)},
        "needs_attention": sum(1 for m in members if m["needs_attention"]),
        "expired": {"lapsed": lapsed, "stale": stale, "total": lapsed + stale},
        "shapes_readiness": shapes_readiness,
        "members": members,
        "common_fixes": common,
    }


# Liaison-facing columns: the cohort status a district staffer or statewide
# program drops straight into a quarterly report or spreadsheet. (header, member key)
_CSV_COLUMNS: tuple[tuple[str, str], ...] = (
    ("agency_id", "id"),
    ("agency_name", "name"),
    ("grade", "grade"),
    ("score", "score"),
    ("checked", "snapshot_date"),
    ("expiry_status", "expiry_status"),
    ("days_until_expiry", "days_until_expiry"),
    ("needs_attention", "needs_attention"),
    ("attention_reason", "attention_reason"),
    ("top_fix", "top_fix"),
    ("shapes_txt_status", "shapes_status"),
)


def _csv_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def rollup_csv(payload: dict[str, Any]) -> str:
    """Render a rollup's members as CSV for a liaison's report or spreadsheet.

    Same order as the JSON (attention first, then worst score), so a program can
    work the list top to bottom. Deterministic, so re-running publish is a no-op.
    """
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow([header for header, _ in _CSV_COLUMNS])
    for member in payload.get("members", []):
        writer.writerow([_csv_cell(member.get(key)) for _, key in _CSV_COLUMNS])
    return buf.getvalue()


def publish_rollups(generated_at: dt.datetime | None = None) -> list[Path]:
    """Write every configured rollup plus a rollups index. Idempotent."""
    when = generated_at or dt.datetime.now(dt.UTC)
    out_dir = artifacts_dir() / "rollups"
    out_dir.mkdir(parents=True, exist_ok=True)
    rollups = load_rollups()

    # "Needs attention" = the same expiry/regression signal that drives the email
    # digest, computed once and shared across rollups so the flag is consistent.
    attention = {item.agency_id: item.headline for item in build_digest(today=when.date()).items}

    # Ridership snapshot (ADR 0021), loaded once and shared: when present it tie-
    # breaks each rollup's attention list toward higher-ridership feeds. None when
    # the file is absent, in which case ordering is unweighted as before.
    from .ridership import load_ridership

    ridership = load_ridership(repo_root() / "data" / "ntd-ridership.csv")

    written: list[Path] = []
    index: list[dict[str, Any]] = []
    for rollup in rollups:
        payload = build_rollup(rollup, when, attention, ridership)
        path = out_dir / f"{rollup.id}.json"
        _write_json(path, payload)
        written.append(path)
        # A spreadsheet of the same cohort, for a liaison's quarterly report.
        csv_path = out_dir / f"{rollup.id}.csv"
        csv_path.write_text(rollup_csv(payload), encoding="utf-8")
        written.append(csv_path)
        index.append(
            {
                "id": rollup.id,
                "name": rollup.name,
                "agency_count": payload["agency_count"],
                "average_score": payload["average_score"],
                "needs_attention": payload["needs_attention"],
                "expired": payload["expired"]["total"],
            }
        )

    index_path = out_dir / "index.json"
    _write_json(index_path, {"schema_version": SCHEMA_VERSION, "rollups": index})
    written.append(index_path)
    return written
