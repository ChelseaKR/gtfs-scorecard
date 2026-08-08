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
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from . import SCHEMA_VERSION
from .alerts import build_digest
from .comparisons import build_comparison_cohort, reader_archive_profile
from .config import artifacts_dir, repo_root
from .identity import resolve_published_agency_name
from .location import country_name, normalize_country_code
from .metrics import expiry_status
from .ntd import assess_shapes_readiness
from .publish import RESERVED_ARTIFACT_DIRS, _write_json
from .ridership import annual_trips_for, duplicate_ntd_reporter_ids, normalize_ntd_id


@dataclass(frozen=True)
class Rollup:
    id: str
    name: str
    member_ids: tuple[str, ...]  # empty means "all agencies with artifacts"
    state: str | None = None  # auto-include every agency in this state (no member list)
    # Auto-include every agency in this ISO 3166-1 alpha-2 country (no member
    # list). Mutually exclusive with state: a rollup names one jurisdiction level.
    country: str | None = None


def _available_agency_ids() -> list[str]:
    # Bounded to the registry: an S3-hydrated tree can hold directories for
    # agencies no registry version lists, and a rollup must not count those.
    from .config import AGENCIES

    root = artifacts_dir()
    if not root.exists():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir()
        and p.name not in RESERVED_ARTIFACT_DIRS
        and (p / "latest.json").exists()
        and (not AGENCIES or p.name in AGENCIES)
    )


def _parse_rollup_country(entry: dict[str, Any]) -> str | None:
    """Validated ISO 3166-1 alpha-2 country selector, or None when unset.

    A rollup names one jurisdiction level, so setting both state and country
    is a configuration error, and an unassigned code fails loading with a
    sentence instead of silently publishing an empty cohort."""
    raw = entry.get("country")
    if raw is None:
        return None
    if entry.get("state"):
        raise ValueError(
            f"rollups.yaml, rollup {entry.get('id')!r}: set state or country, not both"
        )
    code = normalize_country_code(str(raw))
    if not code:
        raise ValueError(
            f"rollups.yaml, rollup {entry.get('id')!r}: country must be an assigned "
            f"ISO 3166-1 alpha-2 code, got {raw!r}"
        )
    return code


def load_rollups(path: Path | None = None) -> list[Rollup]:
    """Read rollups.yaml, or fall back to a single all-agencies rollup."""
    config_path = path or repo_root() / "rollups.yaml"
    if not config_path.exists():
        return [Rollup(id="all", name="All tracked agencies", member_ids=())]

    raw = yaml.safe_load(config_path.read_text()) or {}
    rollups: list[Rollup] = []
    for entry in raw.get("rollups", []):
        state = entry.get("state")
        country = _parse_rollup_country(entry)
        members = () if (entry.get("all") or state or country) else tuple(entry.get("members", []))
        rollups.append(
            Rollup(
                id=str(entry["id"]),
                name=str(entry["name"]),
                member_ids=members,
                state=str(state) if state else None,
                country=country,
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

    Artifacts don't yet carry state (that persists once the registry has state
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
    artifact first (once registry entries have state fields) then catalog.json."""
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


def _agency_ids_in_country(country: str) -> list[str]:
    """Available agencies whose ISO 3166-1 country matches, checked against the
    curated registry entry first (the authoritative location) and then the
    persisted artifact. An artifact that predates the country field is a US
    record by the public API contract (location_rollups.py)."""
    from .config import AGENCIES

    want = country.strip().upper()
    ids = []
    for agency_id in _available_agency_ids():
        agency = AGENCIES.get(agency_id)
        resolved = agency.country.strip().upper() if agency else ""
        if not resolved:
            latest = _load_latest(agency_id)
            raw_country = latest.get("agency", {}).get("country", "US") if latest else "US"
            resolved = str(raw_country).strip().upper() or "US"
        if resolved == want:
            ids.append(agency_id)
    return ids


def resolve_member_ids(rollup: Rollup) -> list[str]:
    """The agency ids a rollup covers.

    Explicit members when the rollup lists them, otherwise every agency in its
    state or country, otherwise every agency with a published artifact. Shared
    by the rollup artifact build and the portfolio digest so a cohort means the
    same set of agencies in both."""
    if rollup.member_ids:
        return list(rollup.member_ids)
    if rollup.state:
        return _agency_ids_in_state(rollup.state)
    if rollup.country:
        return _agency_ids_in_country(rollup.country)
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


def _rollup_identity(rollup: Rollup) -> dict[str, Any]:
    """The payload's identity block. Country rollups carry their ISO identity
    so every renderer can state the cohort's scope honestly (reviewed feed
    records tracked in that country, never country coverage) without keying
    off id naming conventions."""
    identity: dict[str, Any] = {"id": rollup.id, "name": rollup.name}
    if rollup.country:
        identity["country_code"] = rollup.country
        identity["country_name"] = country_name(rollup.country, rollup.country)
    return identity


def build_rollup(
    rollup: Rollup,
    generated_at: dt.datetime,
    attention: dict[str, str] | None = None,
    ridership: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Aggregate member artifacts into one rollup payload.

    Members needing attention sit at the top, which is the order a liaison
    reads them in. Other members are alphabetical. "Needs attention"
    means something is actually wrong or about to break — the feed is expiring
    or the grade regressed (the same signal that triggers an email digest) —
    not merely "below a B", so the flag points at the calls worth making first.
    Common fixes are counted across members so a program can see the one export
    setting that would lift several agencies at once.

    When an NTD ridership snapshot is supplied (ADR 0021,
    docs/decisions/0021-ridership-weighting.md), the attention group is ordered
    by annual rider-trips first, so a high-ridership feed that is expiring ranks
    above a tiny one before falling back to score — the same call is worth making
    first when more riders depend on it. This is a worklist order only, not a
    ranking of agencies against each other.
    """
    attention = attention or {}
    from .config import AGENCIES

    member_ids = resolve_member_ids(rollup)
    members: list[dict[str, Any]] = []
    comparison_records: list[dict[str, Any]] = []
    fixes_by_id: dict[str, list[dict[str, Any]]] = {}
    ntd_id_by_member: dict[str, str] = {}

    for agency_id in member_ids:
        latest = _load_latest(agency_id)
        if not latest or "overall" not in latest:
            # Skip a missing or malformed (non-agency, partial) artifact rather
            # than crash the whole rollup on it.
            continue
        overall = latest["overall"]
        fixes = latest.get("top_fixes", [])
        fixes_by_id[str(latest["agency"]["id"])] = fixes
        days = (
            latest.get("categories", {})
            .get("freshness", {})
            .get("details", {})
            .get("days_until_expiry")
        )
        member_id = str(latest["agency"]["id"])
        member_name = resolve_published_agency_name(
            member_id,
            registry_name=AGENCIES[member_id].name if member_id in AGENCIES else "",
            artifact_name=str(latest["agency"].get("name") or ""),
        )
        ntd_id = normalize_ntd_id((latest.get("ntd_id_alignment") or {}).get("ntd_id"))
        if ntd_id:
            ntd_id_by_member[member_id] = ntd_id
        members.append(
            {
                "id": member_id,
                "name": member_name,
                "score": overall["score"],
                "grade": overall["grade"],
                "snapshot_date": latest["snapshot_date"],
                "needs_attention": agency_id in attention,
                "attention_reason": attention.get(agency_id),
                "days_until_expiry": days,
                "expiry_status": expiry_status(days),
                "top_fix": fixes[0]["fix"] if fixes else None,
                "top_fix_code": fixes[0].get("code") if fixes else None,
                "shapes_status": _shapes_status(latest),
                # Filled after every member is loaded, when duplicate reporter
                # ids can be quarantined rather than double-attributed.
                "annual_trips": None,
            }
        )
        categories = latest.get("categories") or {}
        comparison_records.append(
            {
                "id": latest["agency"]["id"],
                "name": member_name,
                "score": overall["score"],
                "grade": overall["grade"],
                "date": latest.get("snapshot_date"),
                "rubric_version": latest.get("rubric_version"),
                "scoring_profile_id": (latest.get("scoring_profile") or {}).get("id"),
                "scoring_profile_rubric_version": (latest.get("scoring_profile") or {}).get(
                    "rubric_version"
                ),
                "validator_version": latest.get("validator_version"),
                "reader_archive_profile": reader_archive_profile(latest),
                "feed_sha256": (latest.get("feed") or {}).get("sha256"),
                "days_until_expiry": days,
                **{
                    key: (
                        categories.get(key, {}).get("score")
                        if categories.get(key, {}).get("status") == "measured"
                        else None
                    )
                    for key in ("correctness", "freshness", "completeness", "realtime")
                },
            }
        )

    # NTD annual trips describe one reporter, not one GTFS feed. If more than
    # one rollup member claims the same reporter id, every match is ambiguous:
    # leave all of them unweighted rather than assigning the full rider count
    # to each feed or guessing which record is canonical.
    from .config import AGENCIES

    ntd_id_counts = Counter(ntd_id_by_member.values())
    ambiguous_ntd_ids = duplicate_ntd_reporter_ids(AGENCIES.values())
    ambiguous_ntd_ids.update(
        ntd_id for ntd_id, member_count in ntd_id_counts.items() if member_count > 1
    )
    for member in members:
        member_ntd_id = ntd_id_by_member.get(str(member["id"]))
        if member_ntd_id and member_ntd_id not in ambiguous_ntd_ids:
            member["annual_trips"] = annual_trips_for({"ntd_id": member_ntd_id}, ridership)

    # Attention-needing agencies first (a call worth making). Within that group,
    # order by annual rider-trips descending when available, then name. Members
    # without an attention signal are alphabetical, never score-ranked.
    def _sort_key(m: dict[str, Any]) -> tuple[int, int, str, str]:
        if m["needs_attention"]:
            return (0, -(m["annual_trips"] or 0), str(m["name"]).casefold(), m["id"])
        return (1, 0, str(m["name"]).casefold(), m["id"])

    members.sort(key=_sort_key)
    comparable_records, comparison = build_comparison_cohort(
        comparison_records,
        agencies=AGENCIES.values() if AGENCIES else None,
    )
    comparable_ids = {str(record["id"]) for record in comparable_records}
    fix_counter: Counter[tuple[str, str]] = Counter()
    for agency_id in comparable_ids:
        for fix in fixes_by_id.get(agency_id, []):
            fix_counter[(fix.get("code", ""), fix.get("fix", ""))] += 1
    scores = [float(m["score"]) for m in comparable_records]
    grades = Counter(str(m["grade"]) for m in comparable_records)
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

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "rollup": _rollup_identity(rollup),
        "generated_at": generated_at.isoformat(timespec="seconds"),
        "agency_count": len(members),
        "average_score": round(sum(scores) / len(scores), 1) if scores else None,
        "grade_distribution": {g: grades[g] for g in sorted(grades)},
        "comparison": comparison,
        "state_percentile": None,
        "needs_attention": sum(1 for m in members if m["needs_attention"]),
        "expired": {"lapsed": lapsed, "stale": stale, "total": lapsed + stale},
        "shapes_readiness": shapes_readiness,
        "realtime": _realtime_block(members),
        "members": members,
        "common_fixes": common,
        **_reconciliation_block(member_ids),
    }
    return payload


@lru_cache(maxsize=4)
def _rt_kinds_for_root(root: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Which realtime feed kinds each registry record publishes, under one repo root.

    Read from the registry rather than the process-global ``AGENCIES``, which
    ``read_agencies`` deliberately leaves alone, so this is correct whichever
    entry point built the rollup. Keyed on the root because tests point the
    pipeline at a temporary one. A root with no registry at all yields nothing,
    which is the right answer for a bare fixture repo.
    """
    from .agencies import AgencyConfigError, read_agencies

    try:
        agencies = read_agencies()
    except AgencyConfigError:
        return ()
    return tuple(
        (agency.id, tuple(sorted(agency.rt_urls))) for agency in agencies if agency.rt_urls
    )


def _configured_rt_kinds() -> dict[str, tuple[str, ...]]:
    return dict(_rt_kinds_for_root(str(repo_root())))


def _realtime_block(members: list[dict[str, Any]]) -> dict[str, Any]:
    """Realtime reliability across this program's members, agency by agency.

    The monthly reports a state programme publishes assess the schedule side,
    and check realtime presence at most a couple of times a month. The realtime
    monitor here already records reachability, header freshness, and trip
    coverage on a schedule (ADR 0012); this rolls that record up per program so
    a reader sees the whole cohort at once rather than one agency page at a
    time.

    Each member gains its own reading, and members the monitor has not observed
    are counted as unmonitored rather than as a zero. Reliability is the share
    of monitor runs the feed answered; it is not a grade input and changes no
    score.
    """
    from ._stats import _median
    from .rt_health import load_observations, summarize
    from .rt_national import reliability_band

    registry = _configured_rt_kinds()
    rows: list[dict[str, Any]] = []
    configured = 0
    for member in members:
        kinds: tuple[str, ...] = registry.get(member["id"], ())
        if kinds:
            configured += 1
        observations = load_observations(member["id"])
        if not observations:
            continue
        health = summarize(observations)
        rows.append(
            {
                "id": member["id"],
                "name": member["name"],
                "configured_kinds": list(kinds),
                "observations": health.observations,
                "uptime_pct": health.uptime_pct,
                "band": reliability_band(health.uptime_pct),
                "median_lag_seconds": health.median_lag_seconds,
                "median_coverage_pct": health.median_coverage_pct,
                "first_ts": health.first_ts,
                "last_ts": health.last_ts,
            }
        )
    rows.sort(key=lambda r: (r["uptime_pct"], -(r["median_lag_seconds"] or 0), r["name"]))
    uptimes = [float(r["uptime_pct"]) for r in rows]
    lags = [float(r["median_lag_seconds"]) for r in rows if r["median_lag_seconds"] is not None]
    covs = [float(r["median_coverage_pct"]) for r in rows if r["median_coverage_pct"] is not None]
    median_uptime = _median(uptimes)
    median_lag = _median(lags)
    median_cov = _median(covs)
    bands = {
        band: sum(1 for r in rows if r["band"] == band) for band in ("reliable", "mostly", "spotty")
    }
    return {
        "configured_feed_records": configured,
        "monitored_feed_records": len(rows),
        "bands": bands,
        "median_uptime_pct": round(median_uptime, 1) if median_uptime is not None else None,
        "median_lag_seconds": int(median_lag) if median_lag is not None else None,
        "median_coverage_pct": round(median_cov, 1) if median_cov is not None else None,
        "members": rows,
    }


def _reconciliation_block(member_ids: list[str]) -> dict[str, Any]:
    """This rollup's standing against an external agency directory, if one applies.

    Only California has a published state directory mapped so far, so this
    returns an empty mapping for every other program and the page omits the
    section. The
    crosswalk is a committed file; nothing here reaches the network.

    A partly reconciled cohort reports nothing at all. A figure covering some of a
    program's members would read as though it covered all of them, and the
    nationwide rollup would carry a California statistic.
    """
    from .caltrans_crosswalk import load_crosswalk, reconciliation

    crosswalk = load_crosswalk()
    if crosswalk is None or not member_ids:
        return {}
    known = crosswalk.by_id()
    if any(member not in known for member in member_ids):
        return {}
    return {"reconciliation": reconciliation(crosswalk, member_ids)}


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

    Same order as the JSON (attention first, then impact/name), so a program can
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

    # Build every payload before writing so the JSON and index share one
    # generated timestamp and one guarded comparison policy.
    built = [(rollup, build_rollup(rollup, when, attention, ridership)) for rollup in rollups]

    written: list[Path] = []
    index: list[dict[str, Any]] = []
    for rollup, payload in built:
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
                "comparison_eligible": payload["comparison"]["eligible_count"],
                "needs_attention": payload["needs_attention"],
                "expired": payload["expired"]["total"],
            }
        )

    index_path = out_dir / "index.json"
    _write_json(index_path, {"schema_version": SCHEMA_VERSION, "rollups": index})
    written.append(index_path)
    return written
