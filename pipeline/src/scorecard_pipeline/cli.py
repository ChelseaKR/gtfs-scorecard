"""Command-line entrypoint: from feed URL to scorecard artifact, plus the
operational commands the rollout roadmap (docs/roadmap.md) needs.

scorecard run --all
scorecard run --agency unitrans [--date 2026-06-11] [--force-fetch]
scorecard try <gtfs-zip-url> [--country CA] [--name "Agency"]  # ad-hoc, unpublished
scorecard sync --country US --state California   # propose registry entries
scorecard discover --expired [--apply]            # find feeds whose URL moved
scorecard vendors [--rollup <id>]                 # expiry status by feed host
scorecard shards --count 4                        # CI fan-out plan (JSON)
scorecard activation-targets --ids "unitrans yolobus"  # validate manual publish scope
scorecard activation-hydrate --bucket name --targets-file ids.txt  # exact current S3 corpus
scorecard run-summary build --shard 0 --outcomes o.ndjson --started <iso> --out s.json
scorecard run-summary merge --out data/artifacts/run/latest.json s0.json s1.json ...
scorecard alerts [--out digest.md]                # expiry/regression digest
scorecard portfolio-digest [--rollup id] [--out]  # weekly cohort digest for liaisons
scorecard coverage-check [--save]                 # weekly plain-language coverage advisory
scorecard rollups                                 # portfolio rollup artifacts
scorecard campaign --rollup id --kind calendar-renewal  # bounded support worklist
scorecard sensitivity [--factor 0.2]              # rubric weight-sensitivity study
scorecard canary --candidate-version 8.1.0        # validator-upgrade impact report
scorecard reproduce unitrans 2026-06-11            # re-derive a published grade (FIX-02)
scorecard evidence-packet artifact.json [--format markdown]  # vendor remediation record
scorecard fix-outcomes [--format markdown]          # observed resolution and recurrence
scorecard report --agency unitrans [--brand b.yaml] [--out r.html]  # board-ready report file
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import hashlib
import json
import logging
import os
import sys
import time
import urllib.parse
from pathlib import Path
from typing import Any

from .agencies import load_agencies
from .completeness import completeness
from .config import AGENCIES, Agency, raw_dir, repo_root
from .constants_export import GRADE_RANK
from .fetch import fetch_static
from .gtfs import read_feed_dates
from .metrics import correctness, freshness
from .publish import build_artifact, publish
from .rt import capture_window, realtime, scheduled_trip_ids_at
from .rt_drift import compute_drift, vehicle_plausibility
from .score import build_scorecard
from .validate import (
    country_scoped_output_dir,
    parse_report,
    run_validator,
    validator_country_code,
)

log = logging.getLogger(__name__)


def _maybe_api_report(agency: Agency, sha256: str, validator_version: str):  # type: ignore[no-untyped-def]
    """MobilityData's validation report for this feed's bytes, or None.

    Only attempted for U.S. feeds when the agency pins an mdb id and a Feed API
    token is in the environment (MOBILITY_FEED_API_TOKEN). The Feed API response
    proves feed hash and validator version but does not expose the validator's
    country flag, so reusing it abroad could import country-sensitive notices
    produced under the wrong rules. Every miss falls back to the local validator.
    """
    token = os.environ.get("MOBILITY_FEED_API_TOKEN", "")
    if validator_country_code(agency.country) != "US" or not agency.mdb_id or not token:
        return None
    from .feedapi import try_cached_report

    report = try_cached_report(agency.mdb_id, sha256, validator_version, token)
    if report is not None:
        log.info("%s: reused MobilityData validation (%s)", agency.id, sha256[:12])
    return report


@dataclasses.dataclass(frozen=True)
class RunOutcome:
    """What run_agency actually did, for the FIX-11 run-health summary: the
    artifact path plus the two operational signals a shard's outcome log
    (run_summary.py) needs and that only run_agency's own locals know --
    whether the feed had to fall back to the Mobility Database mirror, and
    whether the validator report was reused from the sha-keyed cache."""

    path: str
    mirrored: bool
    cache_hit: bool


def run_agency(  # noqa: C901
    agency_id: str,
    date: dt.date,
    force_fetch: bool = False,
    rt_samples: int = 3,
    rt_interval: int = 30,
    skip_rt: bool = False,
) -> RunOutcome:
    """Run the full pipeline for one agency; return its RunOutcome."""
    agency = AGENCIES[agency_id]
    fetched = fetch_static(agency, date, force=force_fetch)

    # Content-addressed raw archive (FIX-02): keep the bytes that produced this
    # grade, deduplicated by hash, so a disputed grade or `scorecard reproduce`
    # can pull the exact zip later. Best-effort by design (archive.py); never
    # blocks a score.
    from . import archive

    try:
        archive.store(fetched.sha256, fetched.path)
    except OSError as exc:
        log.warning("%s: raw archive write failed: %s", agency.id, exc)

    # Skip the Java validator when this exact feed (same bytes, same validator
    # version) was already validated; reuse the cached normalized report.
    from .validate import VALIDATOR_VERSION
    from .vcache import load_cached, store_cached

    report = (
        None
        if force_fetch
        else load_cached(
            agency.id,
            fetched.sha256,
            VALIDATOR_VERSION,
            country_code=agency.country,
        )
    )
    cache_hit = report is not None
    if report is not None:
        log.info("%s: validator cache hit (%s)", agency.id, fetched.sha256[:12])
    else:
        # Cost lever: if MobilityData already validated these exact bytes with our
        # validator version, reuse their report instead of running Java. Guarded
        # by an mdb id, a Feed API token, and an exact hash + version match; any
        # miss falls through to a local run (feedapi.py).
        report = _maybe_api_report(agency, fetched.sha256, VALIDATOR_VERSION)
        if report is None:
            report_dir = country_scoped_output_dir(
                raw_dir() / agency.id / date.isoformat() / "validator",
                agency.country,
            )
            report_path = report_dir / "report.json"
            if not report_path.exists() or force_fetch:
                report_path = run_validator(
                    fetched.path,
                    report_dir,
                    country_code=agency.country,
                )
            report = parse_report(report_path)
        store_cached(
            agency.id,
            fetched.sha256,
            VALIDATOR_VERSION,
            report,
            country_code=agency.country,
        )

    cats = [
        correctness(report),
        freshness(read_feed_dates(str(fetched.path)), today=date, service_type=agency.service_type),
        completeness(str(fetched.path), fare_free=agency.fare_free),
    ]
    if agency.rt_urls and not skip_rt:
        window = capture_window(agency, date, samples=rt_samples, interval_seconds=rt_interval)
        scheduled = scheduled_trip_ids_at(str(fetched.path), dt.datetime.now(dt.UTC))
        cats.append(
            realtime(
                window,
                scheduled or None,
                drift=compute_drift(window.samples, str(fetched.path)),
                plausibility=vehicle_plausibility(window.samples, str(fetched.path)),
            )
        )
    scorecard = build_scorecard(cats)
    # Derive generated_at from the snapshot date (not wall-clock) so re-running a
    # given date reproduces the artifact byte-for-byte (publish.py contract).
    generated_at = dt.datetime.combine(fetched.fetched_date, dt.time(), dt.UTC)
    artifact = build_artifact(agency, fetched, scorecard, generated_at=generated_at)
    # Beyond-the-grade opportunities (Fares v2, Flex completeness, accessibility):
    # attached as a separate block so they show as recommendations without moving
    # any category score.
    from .recommend import gather_recommendations

    artifact["recommendations"] = gather_recommendations(str(fetched.path))
    # Conformance mark: a pass/not-yet credential over the scores just computed.
    # Attached so the badge and the page can show it without recomputing.
    from .conformance import assess as assess_conformance

    artifact["conformance"] = assess_conformance(artifact).to_dict()
    # A small per-agency geometry (median stop point + bbox) for the national
    # map. Attached when the feed has located stops; absent feeds are simply not
    # plotted. Computed here so the map needs no separate geometry pass.
    from .geo import agency_geo_from_zip

    geo = agency_geo_from_zip(str(fetched.path))
    if geo is not None:
        artifact["geo"] = geo
    # Per-agency route + stop geometry for the scorecard map: one deduplicated
    # LineString per route plus the stops as points, drawn from this feed's own
    # shapes.txt and stops.txt. The drawable GeoJSON is written next to the
    # artifacts (committed and served like the dated JSON); a compact summary (the
    # route list with colors and the stop count) rides on the artifact so the
    # page's accessible route table needs no second file read. Feeds with neither
    # routes nor located stops carry no map.
    from .config import artifacts_dir as _artifacts_dir
    from .route_geometry import route_geometry_from_zip

    geometry = route_geometry_from_zip(str(fetched.path))
    geometry_dir = _artifacts_dir() / agency.id
    geometry_dir.mkdir(parents=True, exist_ok=True)
    geometry_path = geometry_dir / "geometry.geojson"
    if geometry.feature_collection is not None:
        geometry_path.write_text(
            json.dumps(geometry.feature_collection, sort_keys=True, separators=(",", ":")) + "\n"
        )
        route_map = dict(geometry.summary)
        route_map["path"] = f"data/artifacts/{agency.id}/geometry.geojson"
        artifact["route_map"] = route_map
    else:
        # No drawable geometry this run: drop any stale file so the page falls back
        # cleanly and the artifact stays free of a dead map reference.
        geometry_path.unlink(missing_ok=True)
        artifact["route_map"] = dict(geometry.summary)
    # The export diff (EXP-18): what changed in the feed itself since the last
    # export, diffed from the compact structure fingerprint remembered beside
    # the artifact. Best-effort by design; a diff must never block a score.
    from .exportdiff import export_diff

    try:
        diff_block = export_diff(agency.id, str(fetched.path), fetched.sha256)
        if diff_block is not None:
            artifact["export_diff"] = diff_block
    except Exception as exc:
        log.warning("%s: export diff failed: %s", agency.id, exc)

    # Routing-flavored usability checks (single-stop trips, orphan stops): a
    # zero-deduction block so the grade is unchanged, attached for the page.
    from .routability import assess_routability

    routability = assess_routability(str(fetched.path))
    artifact["routability"] = {
        **routability.to_details(),
        "findings": [f.to_json() for f in routability.findings],
    }
    # NTD GTFS readiness and agency_id alignment are US-only surfaces:
    # they map the feed onto the FTA National Transit Database, which has no
    # meaning abroad. A non-US agency is scored on the same rubric but skips both,
    # so no hollow NTD box appears (ADR 0026). Absent keys mean the SPA and API
    # omit the section, and render_site gates its recomputed view on country too.
    if agency.country == "US":
        from .gtfs import read_agency_ids, read_shapes_coverage
        from .ntd import assess as assess_ntd_readiness
        from .ntd import assess_id_alignment, assess_shapes_readiness

        # NTD ID alignment: does the feed's agency_id match the agency's NTD ID?
        # A forward-looking compliance flag (FTA RY2025/26), zero-deduction, shown
        # as not-yet-checked when we have no NTD ID on file.
        artifact["ntd_id_alignment"] = assess_id_alignment(
            read_agency_ids(str(fetched.path)), agency.ntd_id
        ).to_dict()
        # Shapes readiness: does shapes.txt cover this feed's trips? FTA's July
        # 2025 final rule requires shapes.txt from Reduced, Rural, and Tribal
        # NTD reporters starting Report Year 2026 (Full Reporters, RY2025).
        shapes_coverage = read_shapes_coverage(str(fetched.path))
        artifact["shapes_readiness"] = assess_shapes_readiness(
            shapes_coverage.total_trips, shapes_coverage.trips_with_shape
        ).to_dict()
        # NTD GTFS readiness (published / valid / current), precomputed so
        # the web app and API render it without re-deriving the verdict.
        artifact["ntd_readiness"] = assess_ntd_readiness(artifact).to_dict()
    # Corrected-feed offer: run the safe deterministic fixes over the feed we
    # already fetched (no extra network call) and attach a summary the page can
    # render. The patched zip is written next to the agency's artifacts; it is
    # gitignored and reaches the CDN through the workflow's S3 file sync, so the
    # download link points at SCORECARD_CDN_BASE when that is set.
    from .autofix import autofix_zip
    from .config import artifacts_dir

    corrected = artifacts_dir() / agency.id / "corrected.zip"
    corrected.parent.mkdir(parents=True, exist_ok=True)
    fixes = autofix_zip(str(fetched.path), str(corrected))
    if fixes:
        autofix_block: dict[str, Any] = {
            "available": True,
            "total": sum(f.count for f in fixes),
            "fixes": [
                {
                    "code": f.code,
                    "label": f.label,
                    "count": f.count,
                    "examples": f.examples[:3],
                }
                for f in fixes
            ],
            "download_path": f"data/artifacts/{agency.id}/corrected.zip",
        }
        cdn_base = os.environ.get("SCORECARD_CDN_BASE")
        if cdn_base:
            autofix_block["download_url"] = (
                f"{cdn_base.rstrip('/')}/data/artifacts/{agency.id}/corrected.zip"
            )
        artifact["autofix"] = autofix_block
    else:
        artifact["autofix"] = {"available": False}
    path = publish(artifact)
    log.info(
        "%s: %s (%s) -> %s",
        agency.id,
        artifact["overall"]["grade"],
        artifact["overall"]["score"],
        path,
    )
    return RunOutcome(path=str(path), mirrored=fetched.source == "mirror", cache_hit=cache_hit)


def run_adhoc(
    url: str,
    name: str | None,
    date: dt.date,
    country: str = "US",
) -> dict[str, Any]:
    """Score an arbitrary GTFS Schedule feed without registering or publishing.

    For live, exploratory use: point it at any feed zip and get the same grade,
    category scores, and plain-language fixes a tracked agency gets. Nothing is
    written to the public artifacts or index; the download and validator output
    land in the gitignored data/raw cache. Realtime is not sampled (an ad-hoc
    URL carries no RT endpoints), so that category shows as not yet measured.
    """
    country_code = validator_country_code(country)
    label = name or urllib.parse.urlparse(url).netloc or "Ad-hoc feed"
    agency = Agency(id="_adhoc", name=label, static_gtfs_url=url, country=country_code)
    # Keep the public artifact identity stable while isolating scratch files by
    # URL and validator country. Several local/worker invocations can score
    # different feeds at once; a shared `_adhoc/<date>` path lets one download
    # replace another between fetch and validation.
    scratch_key = f"{country_code}\0{url}".encode()
    scratch_id = f"_adhoc-{hashlib.sha256(scratch_key).hexdigest()[:16]}"
    scratch_agency = dataclasses.replace(agency, id=scratch_id)
    fetched = fetch_static(scratch_agency, date, force=True)
    report_dir = raw_dir() / scratch_id / date.isoformat() / "validator"
    report = parse_report(run_validator(fetched.path, report_dir, country_code=country_code))
    cats = [
        correctness(report),
        freshness(read_feed_dates(str(fetched.path)), today=date),
        completeness(str(fetched.path)),
    ]
    scorecard = build_scorecard(cats)
    generated_at = dt.datetime.combine(fetched.fetched_date, dt.time(), dt.UTC)
    return build_artifact(agency, fetched, scorecard, generated_at=generated_at)


_SUMMARY_LABELS = {
    "correctness": "Correctness",
    "freshness": "Freshness",
    "completeness": "Rider experience",
    "realtime": "Realtime",
}


def _print_scorecard_summary(artifact: dict[str, Any]) -> None:
    """A clean terminal scorecard: grade, category bars, and the top fixes."""
    overall = artifact["overall"]
    print(f"\n  {artifact['agency']['name']}")
    print(f"  {artifact['feed']['static_url']}")
    print(f"\n  Overall grade: {overall['grade']}  ({overall['score']}/100)\n")
    for key, label in _SUMMARY_LABELS.items():
        cat = artifact["categories"].get(key, {})
        if cat.get("status") == "measured":
            score = float(cat["score"])
            filled = round(score / 10)
            bar = "█" * filled + "░" * (10 - filled)
            print(f"  {label:16} {score:5.1f}  {bar}")
        else:
            print(f"  {label:16}    --  not yet measured")
    fixes = artifact.get("top_fixes", [])
    if fixes:
        print("\n  Top things to fix:")
        for i, fix in enumerate(fixes, 1):
            print(f"    {i}. {fix['fix']}  ({fix['effort']})")
    else:
        print("\n  Nothing urgent. This feed passed every check we translate into fixes.")
    print()


def _cmd_try(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    try:
        artifact = run_adhoc(
            args.url,
            args.name,
            args.date,
            country=getattr(args, "country", "US"),
        )
    except Exception as exc:
        log.error("could not score %s: %s", args.url, exc)
        return 1
    _print_scorecard_summary(artifact)
    if args.html:
        import re

        from .instance import BASE_URL
        from .render_site import _render_agency

        # Rewrite root-absolute asset and nav links to the live domain so the
        # page renders correctly opened straight from disk (file://).
        page = re.sub(r'(href|src)="/', rf'\1="{BASE_URL}/', _render_agency(artifact, []))
        out = Path(args.html)
        out.write_text(page)
        print(f"  Standalone scorecard written to {out}\n")

    if getattr(args, "comment", None):
        from .onboard import render_comment

        out = Path(args.comment)
        out.write_text(render_comment(artifact, page_url=getattr(args, "page_url", None)))
        print(f"  Comment markdown written to {out}\n")

    if getattr(args, "json_out", None):
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
        print(f"  Scorecard JSON written to {out}\n")

    # CI gating: a feed-deployment repo can run `scorecard try <url> --min-grade B
    # --min-days-to-expiry 30` and fail the build before publishing a bad feed.
    return _try_gate(artifact, args)


def _try_gate(artifact: dict[str, Any], args: argparse.Namespace) -> int:
    """Return a non-zero exit code when the scored feed fails a requested
    threshold, so `scorecard try` can gate CI. No thresholds means exit 0."""
    failures: list[str] = []
    if args.min_grade:
        grade = str(artifact["overall"]["grade"])
        if GRADE_RANK.get(grade, 0) < GRADE_RANK[args.min_grade]:
            failures.append(f"grade {grade} is below the required {args.min_grade}")
    if args.min_days_to_expiry is not None:
        days = (
            artifact.get("categories", {})
            .get("freshness", {})
            .get("details", {})
            .get("days_until_expiry")
        )
        if days is None or days < args.min_days_to_expiry:
            shown = "no expiry date" if days is None else f"{days} days"
            failures.append(f"feed expires too soon ({shown} < {args.min_days_to_expiry})")
    for f in failures:
        log.error("gate failed: %s", f)
    return 1 if failures else 0


def _country_arg(value: str) -> str:
    """Argparse adapter for assigned ISO 3166-1 alpha-2 country codes."""
    try:
        return validator_country_code(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _liveness_unchanged(agency_id: str) -> bool:
    """Perform a cheap conditional GET and return True when the feed is unchanged.

    Updates and persists the liveness record in data/liveness.json so
    checked_at stays current even on a skip. Returns False when there is no
    prior record (first run always scores) or when the feed is unreachable
    (let the normal score attempt surface the failure and increment the
    consecutive-failure counter for the alert digest).
    """
    from .config import repo_root
    from .liveness import UNCHANGED, check_feed, load_state, save_state

    agency = AGENCIES[agency_id]
    state_path = repo_root() / "data" / "liveness.json"
    state = load_state(state_path)
    prev = state.get(agency_id)
    record, classification = check_feed(agency.static_gtfs_url, prev)
    state[agency_id] = record
    save_state(state_path, state)
    return classification == UNCHANGED


def _cmd_run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.all and not args.agency:
        parser.error("pass --agency <id> or --all")
    targets = sorted(AGENCIES) if args.all else [args.agency]
    failures = 0
    skipped = 0
    outcome_out = getattr(args, "outcome_out", None)
    for agency_id in targets:
        started = time.monotonic()
        if getattr(args, "skip_unchanged", False) and _liveness_unchanged(agency_id):
            log.info("Skipping %s: feed unchanged since last check", agency_id)
            skipped += 1
            if outcome_out:
                from .run_summary import AgencyOutcome, append_outcome

                append_outcome(
                    outcome_out,
                    AgencyOutcome(
                        agency_id=agency_id,
                        outcome="reused",
                        wall_seconds=time.monotonic() - started,
                    ),
                )
            continue
        try:
            result = run_agency(
                agency_id,
                args.date,
                force_fetch=args.force_fetch,
                rt_samples=args.rt_samples,
                rt_interval=args.rt_interval,
                skip_rt=args.skip_rt,
            )
            print(result.path)
            if outcome_out:
                from .run_summary import AgencyOutcome, append_outcome

                append_outcome(
                    outcome_out,
                    AgencyOutcome(
                        agency_id=agency_id,
                        outcome="scored",
                        mirrored=result.mirrored,
                        cache_hit=result.cache_hit,
                        wall_seconds=time.monotonic() - started,
                    ),
                )
        except Exception:
            failures += 1
            log.exception("%s: pipeline run failed", agency_id)
            if outcome_out:
                from .run_summary import AgencyOutcome, append_outcome

                append_outcome(
                    outcome_out,
                    AgencyOutcome(
                        agency_id=agency_id,
                        outcome="unreachable",
                        wall_seconds=time.monotonic() - started,
                    ),
                )
    if failures:
        return 1
    # Single-agency skip: use exit code 2 so the CI shell loop can distinguish
    # "skipped (nothing to stage)" from "scored (stage the fresh artifact)".
    if skipped and len(targets) == 1:
        return 2
    return 0


def _cmd_sync(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .mobilitydb import (
        DEFAULT_CATALOG_URL,
        fetch_catalog,
        parse_catalog,
        propose_agencies,
        render_yaml,
    )

    source = args.catalog or DEFAULT_CATALOG_URL
    is_url = source.startswith(("http://", "https://"))
    csv_text = fetch_catalog(source) if is_url else Path(source).read_text()
    feeds = parse_catalog(csv_text)
    proposals = propose_agencies(
        feeds,
        country=args.country,
        subdivision=args.state,
        providers=args.provider or None,
        existing_ids=set(AGENCIES),
    )
    if not proposals:
        log.info("No new agencies matched the filter (all matches already tracked).")
        return 0
    block = render_yaml(proposals)
    if args.out:
        Path(args.out).write_text(block)
        log.info("Wrote %d proposed agencies to %s", len(proposals), args.out)
    else:
        print(block, end="")
    log.info("%d proposed; review and merge into the registry intake shard.", len(proposals))
    return 0


def _expiry_status_for(agency_id: str) -> str:
    """Read an agency's latest artifact and bucket it by feed validity window.

    Returns ``unknown`` when no artifact has been published yet, so the discover
    command can run before a full pipeline pass without crashing.
    """
    from .config import artifacts_dir
    from .metrics import expiry_status

    latest = artifacts_dir() / agency_id / "latest.json"
    if not latest.exists():
        return "unknown"
    artifact = json.loads(latest.read_text())
    days = (
        artifact.get("categories", {})
        .get("freshness", {})
        .get("details", {})
        .get("days_until_expiry")
    )
    return expiry_status(days)


def _cmd_backfill_state(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .mobilitydb import (
        DEFAULT_CATALOG_URL,
        apply_state_backfill,
        fetch_catalog,
        parse_catalog,
        resolve_states,
    )

    source = args.catalog or DEFAULT_CATALOG_URL
    is_url = source.startswith(("http://", "https://"))
    csv_text = fetch_catalog(source) if is_url else Path(source).read_text()
    resolved = resolve_states(AGENCIES.values(), parse_catalog(csv_text))
    if not resolved:
        log.info("No agencies need a state backfill (all set, or unresolvable from the catalog).")
        return 0
    if args.apply:
        from .agencies import registry_paths

        changed: list[str] = []
        for registry_path in registry_paths(repo_root()):
            updated, changed_here = apply_state_backfill(registry_path.read_text(), resolved)
            if changed_here:
                registry_path.write_text(updated)
                changed.extend(changed_here)
        log.info(
            "Set state on %d agencies across the registry; re-score to persist it.", len(changed)
        )
    else:
        for agency_id, state in sorted(resolved.items()):
            print(f"{agency_id}\t{state}")
        log.info("%d agencies would get a state (dry run; pass --apply to write).", len(resolved))
    return 0


def _cmd_discover(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .config import repo_root
    from .mobilitydb import (
        DEFAULT_CATALOG_URL,
        apply_replacements,
        fetch_catalog,
        find_replacements,
        parse_catalog,
        render_replacements_md,
    )

    source = args.catalog or DEFAULT_CATALOG_URL
    is_url = source.startswith(("http://", "https://"))
    csv_text = fetch_catalog(source) if is_url else Path(source).read_text()
    feeds = parse_catalog(csv_text)

    # Which tracked agencies to check. Default to the expired ones, since a
    # current feed's URL is by definition still working; --all checks every one.
    wanted_statuses = (
        {"lapsed", "stale"}
        if args.expired
        else {"stale"}
        if args.stale
        else set()  # empty == no status filter
    )
    registry: list[tuple[str, str, str]] = []
    mdb_ids: dict[str, str] = {}
    for agency_id in sorted(AGENCIES):
        if wanted_statuses and _expiry_status_for(agency_id) not in wanted_statuses:
            continue
        a = AGENCIES[agency_id]
        registry.append((a.id, a.name, a.static_gtfs_url))
        if a.mdb_id:
            mdb_ids[a.id] = a.mdb_id

    if not registry:
        log.info("No agencies matched the status filter.")
        return 0

    matches = find_replacements(feeds, registry, mdb_ids)
    report = render_replacements_md(matches, today=dt.date.today().isoformat())
    if args.out:
        Path(args.out).write_text(report)
        log.info("Wrote feed-discovery report for %d agencies to %s", len(registry), args.out)
    else:
        print(report, end="")
    replaced = sum(1 for m in matches if m.status == "replaced")
    missing = sum(1 for m in matches if m.status == "missing")
    log.info("%d checked: %d replaced, %d missing.", len(registry), replaced, missing)

    if args.apply:
        from .agencies import registry_paths

        changed: list[str] = []
        for registry_path in registry_paths(repo_root()):
            updated, changed_here = apply_replacements(registry_path.read_text(), matches)
            if changed_here:
                registry_path.write_text(updated)
                changed.extend(changed_here)
        if changed:
            log.info(
                "Updated static_gtfs_url for %d agency(ies): %s", len(changed), ", ".join(changed)
            )
        else:
            log.info("No replacement URLs to apply.")
    return 0


def _cmd_vendor_report(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Emit a freshness-by-host report for CI step summaries.

    This is an operator's tool for state program staffers. It must not be written
    to any public path (web/ or equivalent). The default output is Markdown so it
    can be appended directly to GITHUB_STEP_SUMMARY.
    """
    from .vendors import (
        render_vendor_report_csv,
        render_vendor_report_markdown,
        vendor_breakdown,
    )

    stats = vendor_breakdown()
    if args.format == "csv":
        report = render_vendor_report_csv(stats)
    else:
        report = render_vendor_report_markdown(stats)
    if args.out:
        Path(args.out).write_text(report)
        log.info("Wrote vendor report to %s", args.out)
    else:
        print(report, end="")
    return 0


def _cmd_vendor_radar(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Run the standing vendor-regression radar over today's dated artifacts.

    Grouped by detected producing tool and notice code, flags a same-day spike
    in a code's incidence within a vendor cohort (EXP-07,
    docs/ideation/03-expansions.md). Emits two artifacts: a private per-vendor
    worklist (agency names included, never write this to a public path) and a
    public de-identified aggregate digest (safe to publish; names no agency).
    Default output is the public digest, matching `vendor-report`'s
    CI-step-summary default; pass `--private` for the internal worklist.
    """
    from .vendor_regression_radar import (
        detect_regressions,
        load_runs,
        render_private_worklist,
        render_public_digest,
    )

    runs = load_runs()
    regressions = detect_regressions(runs)
    report = (
        render_private_worklist(regressions) if args.private else render_public_digest(regressions)
    )
    if args.out:
        Path(args.out).write_text(report)
        log.info("Wrote vendor-radar %s to %s", "worklist" if args.private else "digest", args.out)
    else:
        print(report, end="")
    if regressions:
        log.info(
            "%d same-day vendor-regression pattern(s) detected across %d tool(s).",
            len(regressions),
            len({r.tool_key for r in regressions}),
        )
    return 0


def _cmd_evidence_packet(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Build a deterministic, single-agency vendor remediation packet."""
    from .evidence_packet import build_evidence_packet, render_evidence_packet_markdown

    artifact_path = Path(args.artifact)
    try:
        artifact = json.loads(artifact_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"could not read scorecard artifact: {exc}")
    packet = build_evidence_packet(artifact, scorecard_url=args.scorecard_url)
    output = (
        render_evidence_packet_markdown(packet)
        if args.format == "markdown"
        else json.dumps(packet, indent=2, sort_keys=True) + "\n"
    )
    if args.out:
        Path(args.out).write_text(output)
        log.info("Wrote vendor evidence packet to %s", args.out)
    else:
        print(output, end="")
    return 0


def _cmd_fix_outcomes(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Measure finding resolution and recurrence from dated artifacts on disk."""
    from .config import artifacts_dir
    from .outcomes import build_fix_outcomes, render_fix_outcomes_markdown
    from .publish import RESERVED_ARTIFACT_DIRS

    histories: dict[str, list[dict[str, Any]]] = {}
    root = artifacts_dir()
    if root.exists():
        for agency_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            if agency_dir.name in RESERVED_ARTIFACT_DIRS:
                continue
            artifacts: list[dict[str, Any]] = []
            for dated in sorted(agency_dir.glob("[0-9]" * 4 + "-[0-9][0-9]-[0-9][0-9].json")):
                try:
                    artifacts.append(json.loads(dated.read_text()))
                except (OSError, json.JSONDecodeError):
                    continue
            if artifacts:
                histories[agency_dir.name] = artifacts
    report = build_fix_outcomes(histories)
    output = (
        render_fix_outcomes_markdown(report, min_episodes=args.min_episodes)
        if args.format == "markdown"
        else json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    if args.out:
        Path(args.out).write_text(output)
        log.info("Wrote finding outcome report to %s", args.out)
    else:
        print(output, end="")
    return 0


def _cmd_prune(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Report (and optionally delete) artifact directories whose agency left the
    registry. Removing an agency from the registry never cleaned up its
    published pages and dated artifacts, so a bookmarked scorecard for a
    retired agency stayed live indefinitely and orphans accumulated with churn
    (review finding). Report-only by default: deletion is a curator decision
    (docs/listing-policy.md), not an automatic one."""
    from .config import artifacts_dir
    from .publish import RESERVED_ARTIFACT_DIRS

    art = artifacts_dir()
    if not art.exists():
        print("no artifacts directory; nothing to prune")
        return 0
    registered = set(AGENCIES)
    orphans = sorted(
        d.name
        for d in art.iterdir()
        if d.is_dir()
        and d.name not in registered
        and d.name not in RESERVED_ARTIFACT_DIRS
        and not d.name.startswith(".")
    )
    if not orphans:
        print("no orphaned artifact directories; every directory has a registry entry")
        return 0
    for name in orphans:
        print(f"orphan\t{name}")
    print(f"{len(orphans)} artifact directories have no registry entry.")
    if args.delete:
        import shutil

        for name in orphans:
            shutil.rmtree(art / name)
        print(f"deleted {len(orphans)} orphaned directories.")
    else:
        print("Report only. Re-run with --delete after checking docs/listing-policy.md.")
    return 0


def _cmd_vendors(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .vendors import render_vendor_report, vendor_breakdown

    agency_ids: list[str] | None = None
    if args.rollup:
        from .rollups import _available_agency_ids, load_rollups

        rollup = next((r for r in load_rollups() if r.id == args.rollup), None)
        if rollup is None:
            parser.error(f"no rollup with id {args.rollup!r}")
        agency_ids = list(rollup.member_ids) or _available_agency_ids()

    if args.quality:
        from .vendors import render_vendor_quality, vendor_quality

        report = render_vendor_quality(vendor_quality(_latest_records(agency_ids)))
        if args.out:
            Path(args.out).write_text(report)
            log.info("Wrote vendor quality report to %s", args.out)
        else:
            print(report, end="")
        return 0

    report = render_vendor_report(vendor_breakdown(agency_ids))
    if args.out:
        Path(args.out).write_text(report)
        log.info("Wrote vendor report to %s", args.out)
    else:
        print(report, end="")
    return 0


def _latest_records(agency_ids: list[str] | None = None) -> list[dict[str, Any]]:
    """Flat per-agency records (id, name, feed_url, grade, score, stops, state)
    from each latest.json, for the portfolio/quality/dataset commands."""
    import json as _json

    from .config import artifacts_dir
    from .publish import RESERVED_ARTIFACT_DIRS

    root = artifacts_dir()
    if not root.exists():
        return []
    wanted = set(agency_ids) if agency_ids is not None else None
    records: list[dict[str, Any]] = []
    for agency_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if agency_dir.name in RESERVED_ARTIFACT_DIRS:
            continue
        if wanted is not None and agency_dir.name not in wanted:
            continue
        latest = agency_dir / "latest.json"
        if not latest.exists():
            continue
        try:
            art = _json.loads(latest.read_text())
        except (OSError, ValueError):
            continue
        comp = art.get("categories", {}).get("completeness", {}).get("details", {})
        records.append(
            {
                "id": agency_dir.name,
                "name": art.get("agency", {}).get("name", agency_dir.name),
                "state": art.get("agency", {}).get("state", ""),
                "feed_url": art.get("feed", {}).get("static_url"),
                "grade": art.get("overall", {}).get("grade"),
                "score": art.get("overall", {}).get("score"),
                "stops": comp.get("stops"),
                "artifact": art,
            }
        )
    return records


def _cmd_dataset(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import json as _json

    from .config import artifacts_dir
    from .dataset import build_quality_dataset, national_summary, to_csv

    index_path = artifacts_dir() / "index.json"
    index = _json.loads(index_path.read_text()) if index_path.exists() else {"agencies": {}}
    dataset = build_quality_dataset(index)
    if args.out:
        out = Path(args.out)
        out.write_text(_json.dumps(dataset, indent=2, sort_keys=True) + "\n")
        out.with_suffix(".csv").write_text(to_csv(dataset))
        log.info("Wrote %d rows to %s and %s", len(dataset["rows"]), out, out.with_suffix(".csv"))
    else:
        print(to_csv(dataset), end="")
    summary = national_summary(dataset)
    log.info(
        "Covered dataset: %d agencies, average %s, %s%% current.",
        summary["agency_count"],
        summary["average_score"],
        summary["pct_current"],
    )
    return 0


def _cmd_sensitivity(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Publish the rubric weight-sensitivity study (FIX-07): rescore the latest
    national snapshot under one-at-a-time ±factor weight perturbations and report
    how many letter grades change. Written under data/artifacts so it is served
    and committed like the other national artifacts."""
    import json as _json

    from . import DATA_ATTRIBUTION, DATA_LICENSE, RUBRIC_VERSION, SCHEMA_VERSION
    from .config import artifacts_dir
    from .sensitivity import latest_category_scores, weight_sensitivity

    index_path = artifacts_dir() / "index.json"
    index = _json.loads(index_path.read_text()) if index_path.exists() else {"agencies": {}}
    study = weight_sensitivity(latest_category_scores(index), factor=args.factor)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "license": DATA_LICENSE,
        "attribution": DATA_ATTRIBUTION,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        **study,
    }
    out = Path(args.out) if args.out else artifacts_dir() / "sensitivity.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json.dumps(payload, indent=2, sort_keys=True) + "\n")
    log.info(
        "Weight sensitivity over %d agencies: at most %s%% of letters change "
        "under ±%d%% single-weight perturbations (%s)",
        study["agency_count"],
        study["max_grade_change_pct"],
        round(args.factor * 100),
        out,
    )
    return 0


def _published_states() -> dict[str, str]:
    """Agency id to state from the last published catalog.json, since artifacts
    do not persist state. Empty when the file is absent."""
    import json as _json

    path = repo_root() / "web" / "catalog.json"
    try:
        catalog = _json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return {
        a["id"]: a["state"] for a in catalog.get("agencies", []) if a.get("id") and a.get("state")
    }


def _cmd_ntd(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .ntd import portfolio_summary, render_portfolio

    records = _latest_records()
    states = _published_states()
    artifacts = []
    for r in records:
        art = r["artifact"]
        # Artifacts don't carry state; backfill from the published catalog so the
        # per-state breakdown works (Unlocated when still unknown).
        agency = art.setdefault("agency", {})
        if not agency.get("state") and states.get(r["id"]):
            agency["state"] = states[r["id"]]
        artifacts.append(art)
    if args.state:
        artifacts = [a for a in artifacts if a.get("agency", {}).get("state", "") == args.state]
    summary = portfolio_summary(artifacts)
    report = render_portfolio(summary)
    if args.out:
        Path(args.out).write_text(report)
        log.info("Wrote NTD portfolio summary to %s", args.out)
    else:
        print(report, end="")
    log.info(
        "%d of %d agencies ready to certify (%s%%).",
        summary.ready,
        summary.total,
        summary.pct_ready,
    )
    return 0


def _cmd_ntd_crosswalk(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .agencies import registry_paths
    from .config import repo_root
    from .ntd_crosswalk import (
        agencies_with_ntd_id,
        apply_to_yaml,
        build_index,
        build_name_index,
        fetch_atlas,
        match_agencies,
        match_agencies_by_name,
    )

    registry_files = registry_paths(repo_root())
    texts = {path: path.read_text() for path in registry_files}
    have: set[str] = set()
    for text in texts.values():
        have |= agencies_with_ntd_id(text)

    log.info("Fetching the Transitland Atlas crosswalk...")
    docs = fetch_atlas()
    index = build_index(docs)
    name_index = build_name_index(docs)
    log.info(
        "Atlas maps %d feed URLs and %d unique names to an NTD ID.", len(index), len(name_index)
    )

    # Pass 1: exact feed-URL match (precise).
    registry = [{"id": a.id, "static_gtfs_url": a.static_gtfs_url} for a in AGENCIES.values()]
    url_props = match_agencies(registry, index, skip_ids=have)

    # Pass 2: unique-name match with a geographic guardrail, for agencies the URL
    # pass did not cover. Agency geometry comes from the published artifacts.
    matched_ids = have | {p.agency_id for p in url_props}
    geo = {r["id"]: (r["artifact"].get("geo") or {}) for r in _latest_records()}
    name_candidates = [
        {
            "id": a.id,
            "name": a.name,
            "lat": geo.get(a.id, {}).get("lat"),
            "lon": geo.get(a.id, {}).get("lon"),
        }
        for a in AGENCIES.values()
    ]
    name_props = match_agencies_by_name(name_candidates, name_index, skip_ids=matched_ids)

    proposals = sorted(url_props + name_props, key=lambda p: p.agency_id)
    log.info(
        "Matched %d of %d agencies (%d by feed URL, %d by name; %d already had an NTD ID).",
        len(proposals),
        len(registry),
        len(url_props),
        len(name_props),
        len(have),
    )
    for p in proposals:
        print(f"{p.agency_id}\t{p.ntd_id}")

    if args.apply:
        inserted = 0
        for registry_path, text in texts.items():
            new_text, inserted_here = apply_to_yaml(text, proposals)
            if inserted_here:
                registry_path.write_text(new_text)
                inserted += inserted_here
        log.info("Wrote %d new ntd_id values into the registry.", inserted)
    else:
        log.info("Dry run; pass --apply to write these into the registry.")
    return 0


def _cmd_ntd_ridership(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .config import repo_root
    from .metrics import expiry_status
    from .ridership import fetch_ridership_csv, parse_ridership_csv, weighted_impact

    csv_path = Path(args.csv) if args.csv else repo_root() / "data" / "ntd-ridership.csv"
    if args.fetch:
        # Latest complete report year first, then the one before: FTA publishes
        # annual products with a lag, so early in a year the prior one is it.
        year = dt.date.today().year
        for candidate in (year - 1, year - 2):
            try:
                text = fetch_ridership_csv(candidate)
            except Exception as exc:
                log.warning("NTD ridership fetch for %s failed: %s", candidate, exc)
                continue
            if len(parse_ridership_csv(text)) > 100:
                csv_path.parent.mkdir(parents=True, exist_ok=True)
                csv_path.write_text(text)
                log.info("Fetched NTD %s ridership to %s.", candidate, csv_path)
                break
        else:
            log.warning("No NTD ridership year could be fetched; keeping any existing file.")
    if not csv_path.exists():
        log.warning(
            "No ridership data at %s. Run with --fetch (or commit the public NTD "
            "ridership CSV there) to weight quality by rider-trips; see "
            "docs/decisions/0021-ridership-weighting.md.",
            csv_path,
        )
        return 0
    ridership = parse_ridership_csv(csv_path.read_text())
    log.info("Loaded annual ridership for %d NTD reporters.", len(ridership))

    records = []
    for r in _latest_records():
        cfg = AGENCIES.get(r["id"])
        days = (r["artifact"].get("categories", {}).get("freshness", {}).get("details", {})).get(
            "days_until_expiry"
        )
        records.append(
            {
                "ntd_id": cfg.ntd_id if cfg else "",
                "score": r["score"],
                "grade": r["grade"],
                "expiry_status": expiry_status(days),
            }
        )

    impact = weighted_impact(records, ridership)
    print(json.dumps(impact, indent=2, sort_keys=True))
    log.info(
        "Weighted %d of %d agencies by ridership: %s annual trips, %s%% on expired feeds.",
        impact["matched_agencies"],
        impact["total_agencies"],
        f"{impact['total_annual_trips']:,}",
        impact["expired_trips_pct"],
    )
    return 0


def _cmd_lint(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from collections import Counter

    from .lint import lint_registry

    issues = lint_registry(AGENCIES.values())
    if not issues:
        log.info("Registry is clean: %d agencies, no hygiene issues.", len(AGENCIES))
        return 0
    for issue in issues:
        print(f"{issue.kind}\t{issue.agency_id}\t{issue.detail}")
    by_kind = Counter(i.kind for i in issues)
    log.info("%d registry issue(s): %s", len(issues), dict(by_kind))
    if args.strict and by_kind.get("feed_descriptor_name"):
        return 1
    return 0


def _cmd_identity(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .identity import build_identity_ledger

    payload = build_identity_ledger(AGENCIES.values())
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if args.out:
        path = Path(args.out)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        log.info("Wrote feed identity ledger to %s.", path)
    else:
        print(text, end="")
    return 0


def _cmd_cadence(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import json as _json
    from collections import Counter

    from .cadence import cadence_tier, due_now
    from .config import artifacts_dir
    from .publish import RESERVED_ARTIFACT_DIRS

    root = artifacts_dir()
    tiers: dict[str, str] = {}
    if root.exists():
        for agency_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            if agency_dir.name in RESERVED_ARTIFACT_DIRS:
                continue
            latest = agency_dir / "latest.json"
            if not latest.exists():
                continue
            try:
                artifact = _json.loads(latest.read_text())
            except (OSError, ValueError):
                continue
            tiers[agency_dir.name] = cadence_tier(artifact)

    hour = args.at if args.at is not None else dt.datetime.now(dt.UTC).hour
    due = due_now(tiers, hour)
    if args.out:
        Path(args.out).write_text("".join(f"{aid}\n" for aid in due))
        log.info("Wrote %d due feed id(s) to %s.", len(due), args.out)
    else:
        for aid in due:
            print(aid)
    counts = Counter(tiers.values())
    log.info(
        "Cadence at hour %02d: %d of %d feeds due (%d priority, %d standard).",
        hour,
        len(due),
        len(tiers),
        counts.get("priority", 0),
        counts.get("standard", 0),
    )
    return 0


def _cmd_rt_archive(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .rt_archiver import run_session

    agency = AGENCIES[args.agency]
    if not agency.rt_urls:
        log.error("%s publishes no realtime feed to archive.", agency.id)
        return 1
    recorded = run_session(agency, duration_seconds=args.duration, interval_seconds=args.interval)
    log.info("Archived %d realtime observations for %s.", recorded, agency.id)
    return 0


def _cmd_rt_health(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .rt_health import append_observation, observe

    targets = [args.agency] if args.agency else sorted(AGENCIES)
    monitored = 0
    for agency_id in targets:
        agency = AGENCIES[agency_id]
        if not agency.rt_urls:
            continue
        monitored += 1
        try:
            window = capture_window(
                agency, dt.date.today(), samples=args.samples, interval_seconds=args.interval
            )
        except Exception:
            log.exception("%s: realtime sampling failed", agency_id)
            continue
        # The monitor stays a lightweight realtime poll: coverage needs the static
        # feed and is recorded by the daily score, not here.
        obs = observe(window, kinds_total=len(agency.rt_urls), scheduled=None)
        append_observation(agency_id, obs)
        log.info(
            "%s: rt-health %d/%d feeds up, worst lag %ss",
            agency_id,
            obs.kinds_reachable,
            obs.kinds_total,
            obs.worst_lag_seconds,
        )
    log.info("Monitored realtime for %d agencies.", monitored)
    return 0


def _cmd_feedapi(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .feedapi import feed_id_for, fetch_latest_dataset
    from .validate import VALIDATOR_VERSION

    token = args.token or os.environ.get("MOBILITY_FEED_API_TOKEN", "")
    if not token:
        parser.error("a Feed API token is required (--token or MOBILITY_FEED_API_TOKEN)")
    feed_id = feed_id_for(args.feed_id)
    dataset = fetch_latest_dataset(feed_id, token)
    print(f"Feed:            {dataset.feed_id}")
    print(f"Latest dataset:  {dataset.dataset_id}")
    print(f"Downloaded:      {dataset.downloaded_at or 'unknown'}")
    print(f"Content hash:    {dataset.sha256 or 'not reported'}")
    print(f"Hosted zip:      {dataset.hosted_url or 'not reported'}")
    val = dataset.validation
    if val is None:
        print("Validation:      none reported")
    else:
        print(
            f"Validation:      {val.total_error} errors, {val.total_warning} warnings, "
            f"{val.total_info} info (validator {val.validator_version})"
        )
        match = (
            "matches ours" if val.validator_version == VALIDATOR_VERSION else "differs from ours"
        )
        print(f"Validator:       {match} ({VALIDATOR_VERSION})")
        if val.url_json:
            print(f"Report JSON:     {val.url_json}")
    return 0


def _cmd_otp(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .gtfs import read_tables
    from .otp import assess_routing, fetch_plan, sample_od_pairs

    rows = read_tables(args.feed, ["stops.txt"]).get("stops.txt", [])
    points: list[tuple[float, float]] = []
    for row in rows:
        try:
            lon, lat = float(row.get("stop_lon", "")), float(row.get("stop_lat", ""))
        except ValueError:
            continue
        if -180 <= lon <= 180 and -90 <= lat <= 90 and not (lon == 0 and lat == 0):
            points.append((lon, lat))
    pairs = sample_od_pairs(points, args.pairs)
    if not pairs:
        log.error("Not enough located stops to sample an origin/destination pair.")
        return 1
    results = []
    for origin, destination in pairs:
        try:
            results.append(
                fetch_plan(args.base, origin, destination, date=args.date, time=args.time)
            )
        except Exception as exc:
            log.warning("OTP plan request failed: %s", exc)
            from .otp import PlanResult

            results.append(PlanResult(routable=False, itinerary_count=0, error=str(exc)[:120]))
    qa = assess_routing(results)
    log.info(
        "Routing QA: %d of %d sampled trips routable (%.0f%%).",
        qa.pairs_routable,
        qa.pairs_tested,
        qa.routable_share * 100,
    )
    for failure in qa.failures:
        print(f"unroutable\t{failure}")
    return 0 if qa.all_routable else 1


def _cmd_otp_batch(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.select:
        from .config import artifacts_dir
        from .otp_batch import matrix_entries, select_best_worst

        index_path = artifacts_dir() / "index.json"
        index = json.loads(index_path.read_text()) if index_path.exists() else {"agencies": {}}
        feed_urls = {a.id: a.static_gtfs_url for a in AGENCIES.values()}
        chosen = select_best_worst(index, feed_urls, count=args.count)
        if not chosen:
            log.error("No scored feeds with a known URL to select from.")
            return 1
        for feed in chosen:
            log.info("selected %s feed %s (score %.1f)", feed.cohort, feed.feed_id, feed.score)
        print(json.dumps(matrix_entries(chosen)))
        return 0
    if not (args.base and args.feed):
        parser.error("pass --select best-worst, or --base and --feed to route one feed")
    return _cmd_otp(args, parser)


def _cmd_query(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import json as _json

    from .config import artifacts_dir
    from .dataset import build_quality_dataset
    from .warehouse import query_rows, to_parquet

    index_path = artifacts_dir() / "index.json"
    index = _json.loads(index_path.read_text()) if index_path.exists() else {"agencies": {}}
    rows = build_quality_dataset(index)["rows"]

    if args.export:
        to_parquet(rows, args.export)
        log.info("Wrote %d rows to %s", len(rows), args.export)
        return 0
    if not args.sql:
        parser.error("pass a SQL query, or --export <path>")
    result = query_rows(rows, args.sql)
    print(_json.dumps(result, indent=2, default=str))
    log.info("%d row(s).", len(result))
    return 0


def _cmd_equity(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import json as _json

    from .config import artifacts_dir
    from .dataset import build_quality_dataset
    from .equity import build_overlay, fetch_state_indicators, render_overlay

    index_path = artifacts_dir() / "index.json"
    index = _json.loads(index_path.read_text()) if index_path.exists() else {"agencies": {}}
    dataset = build_quality_dataset(index)
    states = _published_states()
    try:
        indicators = fetch_state_indicators()
        log.info("equity: ACS returned indicators for %d states.", len(indicators))
    except Exception as exc:
        if not args.allow_empty:
            log.error(
                "equity: ACS fetch FAILED, refusing to write an overlay without need tiers: %s",
                exc,
            )
            log.error(
                "equity: the Census API now requires a key (keyless requests redirect to "
                "missing_key.html). Set a free CENSUS_API_KEY: "
                "https://api.census.gov/data/key_signup.html"
            )
            return 1
        log.warning("equity: ACS fetch failed; --allow-empty set, writing counts-only (%s)", exc)
        indicators = {}
    overlay = build_overlay(dataset["rows"], states, indicators)
    tiered = sum(1 for s in overlay["states"] if s["need_tier"] != "unknown")
    log.info("equity: %d of %d states have an ACS need tier.", tiered, len(overlay["states"]))
    if tiered == 0 and not args.allow_empty:
        log.error(
            "equity: 0 of %d states received an ACS need tier; the ACS join produced nothing. "
            "Refusing to overwrite the overlay with empty tiers (pass --allow-empty to override). "
            "Check CENSUS_API_KEY and the ACS variables.",
            len(overlay["states"]),
        )
        return 1
    if args.json_out:
        Path(args.json_out).write_text(_json.dumps(overlay, indent=2, sort_keys=True) + "\n")
        log.info("Wrote equity overlay JSON to %s", args.json_out)
    report = render_overlay(overlay)
    if args.out:
        Path(args.out).write_text(report)
        log.info("Wrote equity report to %s", args.out)
    elif not args.json_out:
        print(report)
    log.info("Equity overlay: %d high-need states flagged.", len(overlay["priority"]))
    return 0


def _cmd_canada_equity(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import json as _json

    from .agencies import load_agencies
    from .cimd import agency_cimd
    from .config import AGENCIES, artifacts_dir
    from .tract_data import stops_from_geometry

    load_agencies()
    agencies = [a for a in AGENCIES.values() if a.country == "CA"]
    if not agencies:
        log.warning("canada-equity: no Canadian agencies in the registry; nothing to do.")
    results: dict[str, Any] = {}
    for agency in sorted(agencies, key=lambda a: a.id):
        geo_path = artifacts_dir() / agency.id / "geometry.geojson"
        if not geo_path.exists():
            log.warning("canada-equity: no geometry for %s; score it first.", agency.id)
            continue
        try:
            stops = stops_from_geometry(_json.loads(geo_path.read_text()))
        except (OSError, ValueError) as exc:
            log.warning("canada-equity: unreadable geometry for %s: %s", agency.id, exc)
            continue
        try:
            tier, quintile = agency_cimd(stops)
        except Exception as exc:
            log.warning("canada-equity: CIMD fetch failed for %s: %s", agency.id, exc)
            continue
        results[agency.id] = {"name": agency.name, "need_tier": tier, "mean_quintile": quintile}
        log.info("canada-equity: %s -> %s (mean quintile %s)", agency.id, tier, quintile)
    doc: dict[str, Any] = {"schema_version": 1, "agencies": results}
    out_path = Path(args.out) if args.out else artifacts_dir() / "canada-equity.json"
    out_path.write_text(_json.dumps(doc, indent=2, sort_keys=True) + "\n")
    log.info("canada-equity: wrote %d Canadian agency tiers to %s", len(results), out_path)
    return 0


def _cmd_gbfs(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from pathlib import Path as _Path

    from .gbfs import (
        DEFAULT_CATALOG_URL,
        assess_catalog,
        fetch_systems_csv,
        parse_systems_csv,
        render_report,
    )

    source = args.catalog or DEFAULT_CATALOG_URL
    local = _Path(source)
    text = local.read_text() if local.exists() else fetch_systems_csv(source)
    systems = parse_systems_csv(text)
    if args.country:
        systems = [s for s in systems if s.country_code == args.country.upper()]
    summary = assess_catalog(systems)
    report = render_report(summary, country=args.country)
    if args.out:
        Path(args.out).write_text(report)
        log.info("Wrote GBFS currency report to %s", args.out)
    else:
        print(report)
    log.info(
        "%d GBFS systems: %d current, %d supported, %d outdated, %d unknown.",
        summary.total,
        summary.current,
        summary.supported,
        summary.outdated,
        summary.unknown,
    )
    return 0


def _cmd_autofix(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .autofix import autofix_zip, render_report

    results = autofix_zip(args.zip, args.out)
    report = render_report(results, feed_label=args.zip)
    if args.report:
        Path(args.report).write_text(report)
    total = sum(r.count for r in results)
    if total:
        log.info("Applied %d fix(es) across %d recipe(s) -> %s", total, len(results), args.out)
        for r in results:
            print(f"{r.code}\t{r.count}")
    else:
        log.info("No safe fixes needed; wrote an unchanged copy to %s", args.out)
    return 0


def _cmd_onboard(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .onboard import parse_issue_form

    body = Path(args.body_file).read_text()
    request = parse_issue_form(body)
    if request is None:
        log.error("no usable http(s) GTFS URL found in the issue body")
        return 1
    payload = json.dumps({"url": request.url, "name": request.name})
    if args.out:
        Path(args.out).write_text(payload + "\n")
    else:
        print(payload)
    return 0


def _cmd_freshness_sweep(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    import json as _json

    from .config import artifacts_dir
    from .publish import publish, registered_agency_dirs
    from .sweep import needs_sweep, resweep

    today = args.date
    root = artifacts_dir()
    if not root.exists():
        log.info("No artifacts to sweep.")
        return 0

    swept = 0
    changes: list[dict[str, Any]] = []
    # Bounded to the registry: re-stamping an unlisted S3-hydrated directory
    # keeps a delisted feed looking alive (docs/listing-policy.md).
    for agency_dir in registered_agency_dirs(root):
        latest = agency_dir / "latest.json"
        if not latest.exists():
            continue
        try:
            artifact = _json.loads(latest.read_text())
        except (OSError, ValueError):
            continue
        if not needs_sweep(artifact, today):
            continue
        new_artifact, summary = resweep(artifact, today)
        swept += 1
        if summary["grade_changed"]:
            changes.append(summary)
        if args.apply:
            publish(new_artifact)

    for c in sorted(changes, key=lambda c: (c["new_grade"], c["id"] or "")):
        log.info(
            "%s: %s -> %s (%s -> %s days)",
            c["id"],
            c["old_grade"],
            c["new_grade"],
            c["old_days"],
            c["new_days"],
        )
    verb = "Applied" if args.apply else "Would change"
    log.info(
        "Freshness sweep for %s: %d agencies reswept, %s %d grade(s).%s",
        today.isoformat(),
        swept,
        verb.lower(),
        len(changes),
        "" if args.apply else " Re-run with --apply to publish.",
    )
    return 0


def _cmd_liveness(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:  # noqa: C901 - tracked, see docs/lint-complexity-ratchet.md
    from collections import Counter

    from .config import repo_root
    from .liveness import (
        CHANGED,
        UNREACHABLE,
        check_feed,
        load_state,
        recovered,
        save_state,
    )

    state_path = repo_root() / "data" / "liveness.json"
    state = load_state(state_path)
    tally: Counter[str] = Counter()
    changed: list[str] = []
    unreachable: list[str] = []
    recovered_ids: list[str] = []

    only: set[str] | None = None
    if args.only:
        only = {line.strip() for line in Path(args.only).read_text().splitlines() if line.strip()}

    for agency_id, agency in sorted(AGENCIES.items()):
        if only is not None and agency_id not in only:
            continue
        prev = state.get(agency_id)
        record, classification = check_feed(agency.static_gtfs_url, prev, timeout=args.timeout)
        if recovered(prev, classification):
            recovered_ids.append(agency_id)
        state[agency_id] = record
        tally[classification] += 1
        if classification == CHANGED:
            changed.append(agency_id)
        elif classification == UNREACHABLE:
            unreachable.append(agency_id)

    for agency_id in changed:
        print(f"changed\t{agency_id}\t{state[agency_id].url}")
    for agency_id in unreachable:
        rec = state[agency_id]
        print(f"unreachable\t{agency_id}\tstatus={rec.status} fails={rec.consecutive_failures}")
    for agency_id in recovered_ids:
        print(f"recovered\t{agency_id}")

    if args.changed_out:
        # One id per line for the refresh workflow to re-score; changed feeds
        # plus recovered ones (back online, so worth a fresh full score).
        rescore = sorted(set(changed) | set(recovered_ids))
        Path(args.changed_out).write_text("".join(f"{aid}\n" for aid in rescore))
        log.info("Wrote %d feed id(s) to re-score to %s.", len(rescore), args.changed_out)

    if args.apply:
        save_state(state_path, state)
        log.info("Wrote liveness state for %d feeds.", len(state))
    log.info(
        "Liveness: %d changed, %d unreachable, %d recovered, %d unchanged.%s",
        len(changed),
        len(unreachable),
        len(recovered_ids),
        tally.get("unchanged", 0),
        "" if args.apply else " Report only; re-run with --apply to persist state.",
    )
    return 0


def _cmd_shards(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .shards import plan_shards

    print(json.dumps(plan_shards(sorted(AGENCIES), args.count)))
    return 0


def _cmd_activation_targets(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Validate and materialize a bounded manual activation selection."""
    from .activation import ActivationTargetError, parse_activation_targets

    try:
        targets = parse_activation_targets(args.ids, AGENCIES)
    except ActivationTargetError as exc:
        parser.error(str(exc))
    output = "".join(f"{target}\n" for target in targets)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output)
    else:
        print(output, end="")
    return 0


def _cmd_activation_hydrate(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Hydrate the authoritative current corpus for a bounded activation."""
    from .activation import ActivationHydrationError, hydrate_activation_corpus
    from .config import artifacts_dir

    try:
        targets = args.targets_file.read_text(encoding="utf-8").splitlines()
        result = hydrate_activation_corpus(
            bucket=args.bucket,
            targets=targets,
            known_ids=AGENCIES,
            artifacts_root=artifacts_dir(),
            index_before=args.index_before_out,
            etag_out=args.etag_out,
            liveness_out=repo_root() / "data" / "liveness.json",
            workers=args.workers,
        )
    except (ActivationHydrationError, OSError) as exc:
        parser.error(str(exc))
    log.info(
        "Hydrated %d current agencies and %d S3 objects (%d optional misses, "
        "%d selected-directory objects, %d unregistered index entries skipped).",
        result.agencies,
        result.objects,
        result.optional_misses,
        result.selected_objects,
        result.skipped_unregistered,
    )
    return 0


def _cmd_run_summary(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .run_summary import build_shard_summary, merge_run_summaries, read_outcomes

    if args.run_summary_cmd == "build":
        outcomes = read_outcomes(args.outcomes)
        summary = build_shard_summary(args.shard, outcomes, args.started, dt.datetime.now(dt.UTC))
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        log.info(
            "shard %s: %d scored, %d reused, %d unreachable -> %s",
            args.shard,
            summary["scored"],
            summary["reused"],
            summary["unreachable"],
            out,
        )
        return 0

    # merge
    summaries = []
    for p in args.summaries:
        path = Path(p)
        if not path.exists():
            log.warning(
                "run-summary merge: %s not found, skipping (shard upload likely failed)", path
            )
            continue
        summaries.append(json.loads(path.read_text()))
    merged = merge_run_summaries(summaries, dt.datetime.now(dt.UTC))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    log.info(
        "merged %d shard summaries: %d scored, %d reused, %d unreachable (degraded=%s) -> %s",
        merged["shard_count"],
        merged["scored"],
        merged["reused"],
        merged["unreachable"],
        merged["degraded"],
        out,
    )
    return 0


def _cmd_alerts(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .alerts import build_digest, render_digest

    digest = build_digest(today=args.date, expiry_days=args.expiry_days)
    text = render_digest(digest)
    if args.out:
        Path(args.out).write_text(text)
        log.info("Wrote alert digest (%d items) to %s", len(digest.items), args.out)
    else:
        print(text, end="")
    return 0


def _cmd_notify(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .alerts import build_digest
    from .notify import (
        build_emails,
        build_webhook_notifications,
        load_subscribers,
        load_subscribers_from_dynamo,
        send_via_ses,
        send_webhooks,
    )

    table = args.table or os.environ.get("SUBSCRIPTIONS_TABLE")
    if table:
        region = os.environ.get("AWS_REGION", "us-west-2")
        subscribers = load_subscribers_from_dynamo(table, region=region)
    else:
        subs_path = Path(args.subscriptions) if args.subscriptions else None
        subscribers = load_subscribers(subs_path)
    digest = build_digest(today=args.date, expiry_days=args.expiry_days)
    unsubscribe_base = os.environ.get("ALERTS_API_BASE")
    emails = build_emails(subscribers, digest, unsubscribe_base=unsubscribe_base)
    webhooks = build_webhook_notifications(subscribers, digest)

    if not emails and not webhooks:
        log.info(
            "Nothing to send: %d subscriber(s), no followed feed needs attention.", len(subscribers)
        )
        return 0

    if args.send:
        if emails:
            sender = args.sender or os.environ.get("SES_FROM")
            if not sender:
                parser.error("--send requires --from or the SES_FROM environment variable")
            region = os.environ.get("AWS_REGION", "us-west-2")
            sent = send_via_ses(emails, sender, region=region)
            log.info("Sent %d digest email(s) via SES from %s.", sent, sender)
        if webhooks:
            sent_hooks = send_webhooks(webhooks)
            log.info("Posted %d digest webhook(s) of %d configured.", sent_hooks, len(webhooks))
        return 0

    for email in emails:
        print(f"=== To: {email.to}\nSubject: {email.subject}\n\n{email.body}")
    for hook in webhooks:
        print(f"=== Webhook: {hook.url}\n\n{hook.payload['text']}")
    log.info(
        "%d email(s), %d webhook(s) would be sent (dry run; pass --send to send).",
        len(emails),
        len(webhooks),
    )
    return 0


def _cmd_portfolio_digest(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .portfolio_digest import (
        build_portfolio_digest,
        load_snapshot,
        render_portfolio_digest,
        save_snapshot,
    )
    from .rollups import load_rollups

    rollups = load_rollups()
    if args.rollup:
        rollups = [r for r in rollups if r.id == args.rollup]
        if not rollups:
            parser.error(f"no rollup with id {args.rollup!r}")

    sections: list[str] = []
    for rollup in rollups:
        previous = load_snapshot(rollup)
        digest = build_portfolio_digest(rollup, today=args.date, previous_snapshot=previous)
        sections.append(render_portfolio_digest(digest))
        if args.save:
            # Advance the baseline so next week diffs against this run. Off by
            # default: a preview or re-run must not consume movement the next
            # real weekly run should report. The scheduled send passes --save.
            save_snapshot(rollup, digest.snapshot, digest.as_of)

    text = "\n".join(sections)
    if args.out:
        Path(args.out).write_text(text)
        log.info("Wrote portfolio digest for %d rollup(s) to %s", len(rollups), args.out)
    else:
        print(text, end="" if text.endswith("\n") else "\n")
    return 0


def _cmd_coverage_check(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """FIX-08's weekly advisory: warn when plain-language coverage drops.

    Computes instance-weighted coverage over every latest.json the same way
    the /problems/ render does, compares it to the saved baseline, and prints
    either an OK line or a COVERAGE DROP advisory (always exit 0 — the check
    warns, it never blocks a run). --save advances the baseline, the same
    preview-vs-persist split as portfolio-digest.
    """
    from .config import artifacts_dir
    from .findings_national import (
        agency_findings,
        coverage_regression,
        national_problems,
        plain_language_coverage,
    )
    from .publish import RESERVED_ARTIFACT_DIRS

    root = artifacts_dir()
    per_agency: list[list[dict[str, Any]]] = []
    scored = 0
    if root.exists():
        for agency_dir in sorted(p for p in root.iterdir() if p.is_dir()):
            if agency_dir.name in RESERVED_ARTIFACT_DIRS:
                continue
            latest = agency_dir / "latest.json"
            if not latest.exists():
                continue
            try:
                artifact = json.loads(latest.read_text())
            except (OSError, ValueError):
                # One unreadable artifact must not abort the advisory; the
                # render loop makes the same call.
                continue
            scored += 1
            per_agency.append(agency_findings(artifact))
    current = plain_language_coverage(national_problems(per_agency, total_agencies=scored))

    baseline_path = root / "coverage-baseline.json"
    previous: dict[str, Any] | None = None
    if baseline_path.exists():
        previous = json.loads(baseline_path.read_text())

    message = coverage_regression(previous, current)
    if message:
        print(message)
    else:
        print(
            f"OK  instance-weighted plain-language coverage "
            f"{current['instance_weighted_coverage']}% "
            f"({current['curated_codes']}/{current['total_codes']} codes curated, "
            f"{scored} scored agencies)"
        )
    if args.save:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(
            json.dumps(
                {
                    "as_of": args.date.isoformat(),
                    "distinct_code_coverage": current["distinct_code_coverage"],
                    "instance_weighted_coverage": current["instance_weighted_coverage"],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )
    return 0


def _cmd_rollups(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .rollups import publish_rollups

    paths = publish_rollups()
    for path in paths:
        print(path)
    return 0


def _cmd_campaign(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Build one fix-themed support campaign for a configured rollup."""
    from .campaigns import build_program_campaign, render_program_campaign_markdown
    from .rollups import _load_latest, load_rollups, resolve_member_ids

    rollup = next((candidate for candidate in load_rollups() if candidate.id == args.rollup), None)
    if rollup is None:
        parser.error(f"no rollup with id {args.rollup!r}")
    artifacts = [
        artifact
        for agency_id in resolve_member_ids(rollup)
        if (artifact := _load_latest(agency_id)) is not None
    ]
    campaign = build_program_campaign(
        rollup_id=rollup.id,
        rollup_name=rollup.name,
        kind=args.kind,
        artifacts=artifacts,
        as_of=args.date,
    )
    output = (
        render_program_campaign_markdown(campaign)
        if args.format == "markdown"
        else json.dumps(campaign, indent=2, sort_keys=True) + "\n"
    )
    if args.out:
        Path(args.out).write_text(output)
        log.info("Wrote %s campaign for %s to %s", args.kind, rollup.id, args.out)
    else:
        print(output, end="")
    return 0


def _cmd_reindex(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .publish import rebuild_index

    print(rebuild_index())
    return 0


def _cmd_render_site(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .constants_export import write_constants
    from .render_site import render_site

    # Refresh the generated presentation constants first, so a full site render
    # never ships an app whose labels or grade bands drifted from the pipeline.
    write_constants()
    written = render_site()
    log.info("rendered %d static pages/files under web/", len(written))
    return 0


def _cmd_render_constants(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .constants_export import write_constants

    print(write_constants())
    return 0


def _cmd_report(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .report import ReportError, generate_report, load_brand

    try:
        brand = load_brand(args.brand) if args.brand else None
        path = generate_report(args.agency, brand=brand, out=args.out)
    except ReportError as err:
        print(f"error: {err}", file=sys.stderr)
        return 2
    print(path)
    return 0


def _cmd_canary(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .canary import run_canary
    from .validate import VALIDATOR_VERSION

    if args.candidate_version == VALIDATOR_VERSION:
        parser.error(f"--candidate-version {args.candidate_version} is already the pinned version")
    md_path, json_path = run_canary(
        args.candidate_version,
        sample_size=args.sample_size,
        seed=args.seed,
        date=args.date,
        out_dir=Path(args.out) if args.out else None,
    )
    print(md_path)
    print(json_path)
    return 0


def _cmd_reproduce(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    from .reproduce import ReproduceError, reproduce

    agency = AGENCIES.get(args.agency)
    if agency is None:
        parser.error(f"unknown agency: {args.agency}")
        return 2
    try:
        result = reproduce(agency, args.date)
    except ReproduceError as exc:
        log.error("%s", exc)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["identical"]:
        print(
            f"\nidentical: {agency.id}/{args.date} reproduces byte-for-byte against feed "
            f"{result['sha256'][:12]} with validator {result['validator_version']}."
        )
        return 0
    print(f"\nDIFFERS from the published artifact ({len(result['differences'])} field(s)):")
    for line in result["differences"]:
        print(f"  - {line}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="scorecard", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="fetch, validate, score, and publish")
    run.add_argument("--agency", help="one agency id")
    run.add_argument("--all", action="store_true", help="run every registered agency")
    run.add_argument(
        "--date",
        type=dt.date.fromisoformat,
        default=dt.date.today(),
        help="snapshot date (default: today)",
    )
    run.add_argument("--force-fetch", action="store_true", help="re-download and re-validate")
    run.add_argument("--rt-samples", type=int, default=3, help="realtime samples per endpoint")
    run.add_argument("--rt-interval", type=int, default=30, help="seconds between realtime samples")
    run.add_argument("--skip-rt", action="store_true", help="skip realtime sampling")
    run.add_argument(
        "--skip-unchanged",
        action="store_true",
        help="skip re-scoring when a cheap conditional GET confirms the feed is unchanged "
        "(exit 2 for a single skipped agency so the CI loop can distinguish skip from error)",
    )
    run.add_argument(
        "--outcome-out",
        help="append one ndjson outcome line per agency here (FIX-11 shard run-health log; "
        "the CI shard loop calls `run` once per agency, so lines accumulate across "
        "invocations, then `scorecard run-summary build` turns the log into a summary)",
    )

    adhoc = sub.add_parser("try", help="score any GTFS feed URL ad-hoc (not published)")
    adhoc.add_argument("url", help="direct link to a GTFS Schedule zip")
    adhoc.add_argument("--name", help="agency name to show (default: the feed host)")
    adhoc.add_argument(
        "--country",
        type=_country_arg,
        default="US",
        help="assigned ISO 3166-1 alpha-2 feed country (default: US)",
    )
    adhoc.add_argument(
        "--date",
        type=dt.date.fromisoformat,
        default=dt.date.today(),
        help="snapshot date (default: today)",
    )
    adhoc.add_argument("--html", help="also write a standalone HTML scorecard to this path")
    adhoc.add_argument(
        "--comment",
        help="also write a markdown comment summary to this path (for the onboarding bot)",
    )
    adhoc.add_argument(
        "--json-out",
        help="write the complete scorecard artifact as JSON before applying CI thresholds",
    )
    adhoc.add_argument(
        "--page-url", help="link to the full scorecard, included in the --comment markdown"
    )
    adhoc.add_argument(
        "--min-grade",
        choices=["A", "B", "C", "D", "F"],
        help="exit non-zero if the overall grade is below this (for CI gating)",
    )
    adhoc.add_argument(
        "--min-days-to-expiry",
        type=int,
        help="exit non-zero if the feed expires within this many days (for CI gating)",
    )

    onboard = sub.add_parser(
        "onboard", help="parse a feed URL and name from a score-a-feed issue body"
    )
    onboard.add_argument("--body-file", required=True, help="path to the rendered issue body")
    onboard.add_argument("--out", help="write the parsed request as JSON here (default: stdout)")

    autofix = sub.add_parser(
        "autofix", help="apply safe deterministic fixes to a GTFS zip, writing a patched copy"
    )
    autofix.add_argument("zip", help="path to a GTFS Schedule zip")
    autofix.add_argument("--out", required=True, help="write the patched zip here")
    autofix.add_argument("--report", help="also write a markdown record of the changes here")

    gbfs = sub.add_parser("gbfs", help="GBFS version-currency report over the open GBFS catalog")
    gbfs.add_argument("--catalog", help="catalog CSV path or URL (default: MobilityData GBFS)")
    gbfs.add_argument("--country", help="ISO country code filter, e.g. US")
    gbfs.add_argument("--out", help="write the report here instead of stdout")

    equity = sub.add_parser(
        "equity", help="equity overlay: where weak data meets high transit need (ACS)"
    )
    equity.add_argument("--json-out", help="write the overlay as JSON here")
    equity.add_argument("--out", help="write the markdown report here instead of stdout")
    equity.add_argument(
        "--allow-empty",
        action="store_true",
        help="write a counts-only overlay even when ACS returns no need tiers (default: fail)",
    )

    canada_equity = sub.add_parser(
        "canada-equity",
        help="Canada equity: served-area CIMD need tier per Canadian agency (StatCan, gated)",
    )
    canada_equity.add_argument(
        "--out", help="write canada-equity.json here (default: data/artifacts/canada-equity.json)"
    )

    query = sub.add_parser(
        "query", help="run SQL over the covered dataset (DuckDB), or export Parquet"
    )
    query.add_argument("sql", nargs="?", help="SQL against the 'agencies' table")
    query.add_argument("--export", help="write the dataset to this Parquet path and exit")

    otp = sub.add_parser(
        "otp", help="routing QA: ask an OpenTripPlanner instance to plan sample trips"
    )
    otp.add_argument("--base", required=True, help="OTP base URL, e.g. http://localhost:8080")
    otp.add_argument(
        "--feed", required=True, help="GTFS zip to sample origin/destination stops from"
    )
    otp.add_argument("--pairs", type=int, default=3, help="how many O/D pairs to test")
    otp.add_argument(
        "--date", default=dt.date.today().isoformat(), help="service date (YYYY-MM-DD)"
    )
    otp.add_argument("--time", default="08:00", help="departure time (HH:MM)")

    otp_batch = sub.add_parser(
        "otp-batch",
        help="weekly routing-QA batch: pick best/worst feeds for CI, or route one feed",
    )
    otp_batch.add_argument(
        "--select",
        choices=["best-worst"],
        help="print the chosen feeds as a JSON matrix ({feed_id, feed_url, cohort}) and exit",
    )
    otp_batch.add_argument("--count", type=int, default=2, help="feeds per cohort (best and worst)")
    otp_batch.add_argument("--base", help="OTP base URL, e.g. http://localhost:8080")
    otp_batch.add_argument("--feed", help="GTFS zip to sample origin/destination stops from")
    otp_batch.add_argument("--pairs", type=int, default=5, help="how many O/D pairs to test")
    otp_batch.add_argument(
        "--date", default=dt.date.today().isoformat(), help="service date (YYYY-MM-DD)"
    )
    otp_batch.add_argument("--time", default="08:00", help="departure time (HH:MM)")

    sync = sub.add_parser("sync", help="propose registry entries from the Mobility Database")
    sync.add_argument("--catalog", help="catalog CSV path or URL (default: Mobility Database)")
    sync.add_argument("--country", help="ISO country code filter, e.g. US")
    sync.add_argument("--state", help="state/subdivision filter, e.g. California")
    sync.add_argument("--provider", action="append", help="provider name filter (repeatable)")
    sync.add_argument("--out", help="write proposals here instead of stdout")

    discover = sub.add_parser(
        "discover", help="check tracked feed URLs against the Mobility Database for replacements"
    )
    discover.add_argument("--catalog", help="catalog CSV path or URL (default: Mobility Database)")
    discover.add_argument(
        "--expired", action="store_true", help="only check expired feeds (lapsed or stale)"
    )
    discover.add_argument(
        "--stale", action="store_true", help="only check long-dead feeds (expired over a year)"
    )
    discover.add_argument("--out", help="write the report here instead of stdout")
    discover.add_argument(
        "--apply",
        action="store_true",
        help="rewrite static_gtfs_url in registry shards for agencies whose feed moved",
    )

    prune = sub.add_parser(
        "prune", help="report artifact directories whose agency left the registry"
    )
    prune.add_argument(
        "--delete",
        action="store_true",
        help="actually delete the orphaned directories (default: report only)",
    )

    vendors = sub.add_parser("vendors", help="operator view: expiry status aggregated by feed host")
    vendors.add_argument("--rollup", help="scope to a rollup's members (default: all agencies)")
    vendors.add_argument(
        "--quality", action="store_true", help="benchmark data quality by feed host instead"
    )
    vendors.add_argument("--out", help="write the report here instead of stdout")

    vendor_report = sub.add_parser(
        "vendor-report",
        help="markdown/CSV freshness-by-host report for CI step summaries (internal only)",
    )
    vendor_report.add_argument(
        "--format",
        choices=["markdown", "csv"],
        default="markdown",
        help="output format (default: markdown for GitHub Actions step summary)",
    )
    vendor_report.add_argument("--out", help="write the report here instead of stdout")

    vendor_radar = sub.add_parser(
        "vendor-radar",
        help=(
            "standing cross-corpus scan for same-day vendor regressions "
            "(EXP-07: public digest by default, --private for the internal worklist)"
        ),
    )
    vendor_radar.add_argument(
        "--private",
        action="store_true",
        help="emit the private per-vendor worklist (names agencies; do not publish) "
        "instead of the public de-identified digest",
    )
    vendor_radar.add_argument("--out", help="write the report here instead of stdout")

    evidence_packet = sub.add_parser(
        "evidence-packet",
        help="turn one scorecard artifact into a reproducible vendor remediation packet",
    )
    evidence_packet.add_argument("artifact", help="path to a published scorecard artifact JSON")
    evidence_packet.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="output format (default: json)",
    )
    evidence_packet.add_argument("--scorecard-url", help="override the canonical scorecard URL")
    evidence_packet.add_argument("--out", help="write the packet here instead of stdout")

    fix_outcomes = sub.add_parser(
        "fix-outcomes",
        help="measure finding resolution time and recurrence from dated artifact history",
    )
    fix_outcomes.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="output format (default: json)",
    )
    fix_outcomes.add_argument(
        "--min-episodes",
        type=int,
        default=1,
        help="minimum episodes per code in Markdown output (default: 1)",
    )
    fix_outcomes.add_argument("--out", help="write the report here instead of stdout")

    dataset = sub.add_parser("dataset", help="build the open covered-set dataset (JSON + CSV)")
    dataset.add_argument("--out", help="write dataset.json (and a sibling .csv) here")

    sensitivity = sub.add_parser(
        "sensitivity",
        help="rubric weight-sensitivity study: grade churn under perturbed weights",
    )
    sensitivity.add_argument(
        "--factor",
        type=float,
        default=0.2,
        help="one-at-a-time weight perturbation, as a fraction (default 0.2 = ±20%%)",
    )
    sensitivity.add_argument(
        "--out", help="write the study here (default: data/artifacts/sensitivity.json)"
    )

    ntd = sub.add_parser("ntd", help="NTD GTFS-readiness portfolio summary")
    ntd.add_argument("--state", help="scope to one state (default: all agencies)")
    ntd.add_argument("--out", help="write the summary here instead of stdout")

    crosswalk = sub.add_parser(
        "ntd-crosswalk", help="populate agency NTD IDs from the Transitland Atlas (by feed URL)"
    )
    crosswalk.add_argument(
        "--apply", action="store_true", help="write matched ntd_id values into registry shards"
    )

    ridership = sub.add_parser(
        "ntd-ridership", help="weight feed quality by NTD annual ridership (rider-trips)"
    )
    ridership.add_argument(
        "--csv",
        help="NTD ridership CSV (default: data/ntd-ridership.csv if present)",
    )
    ridership.add_argument(
        "--fetch",
        action="store_true",
        help="fetch the latest NTD annual ridership from data.transportation.gov first",
    )

    shards = sub.add_parser("shards", help="emit a JSON fan-out plan for CI")
    shards.add_argument("--count", type=int, default=4, help="number of shards")

    activation_targets = sub.add_parser(
        "activation-targets",
        help="validate a bounded manual agency selection against the registry",
    )
    activation_targets.add_argument(
        "--ids",
        required=True,
        help="agency ids separated by commas, spaces, or newlines (maximum 25)",
    )
    activation_targets.add_argument(
        "--out",
        type=Path,
        help="write one validated agency id per line instead of stdout",
    )
    activation_hydrate = sub.add_parser(
        "activation-hydrate",
        help="hydrate the exact authoritative current corpus for targeted activation",
    )
    activation_hydrate.add_argument("--bucket", required=True, help="authoritative S3 bucket")
    activation_hydrate.add_argument(
        "--targets-file",
        required=True,
        type=Path,
        help="validated file with one selected registry id per line",
    )
    activation_hydrate.add_argument(
        "--index-before-out",
        required=True,
        type=Path,
        help="preserve the exact captured index bytes here for merge and comparison",
    )
    activation_hydrate.add_argument(
        "--etag-out",
        required=True,
        type=Path,
        help="write the captured index ETag here for optimistic publication guards",
    )
    activation_hydrate.add_argument(
        "--workers",
        type=int,
        default=16,
        help="bounded concurrent exact S3 reads (default 16; maximum 32)",
    )

    run_summary = sub.add_parser(
        "run-summary",
        help="build/merge per-shard pipeline run-health summaries for /status/ (FIX-11)",
    )
    run_summary_sub = run_summary.add_subparsers(dest="run_summary_cmd", required=True)
    rs_build = run_summary_sub.add_parser(
        "build", help="turn one shard's --outcome-out ndjson log into its run-summary.json"
    )
    rs_build.add_argument("--shard", required=True, help="shard id (e.g. the matrix job index)")
    rs_build.add_argument(
        "--outcomes",
        required=True,
        help="ndjson outcome log written by `scorecard run --outcome-out`",
    )
    rs_build.add_argument(
        "--started",
        required=True,
        type=dt.datetime.fromisoformat,
        help="ISO 8601 shard start time",
    )
    rs_build.add_argument("--out", required=True, help="write this shard's run-summary.json here")
    rs_merge = run_summary_sub.add_parser(
        "merge", help="merge every shard's run-summary.json into data/artifacts/run/latest.json"
    )
    rs_merge.add_argument("summaries", nargs="+", help="paths to shard run-summary.json files")
    rs_merge.add_argument("--out", required=True, help="write the merged run summary here")

    alerts = sub.add_parser("alerts", help="build the expiry/regression alert digest")
    alerts.add_argument(
        "--date", type=dt.date.fromisoformat, default=dt.date.today(), help="as-of date"
    )
    alerts.add_argument("--expiry-days", type=int, default=60, help="warn within this many days")
    alerts.add_argument("--out", help="write the digest here instead of stdout")

    notify = sub.add_parser("notify", help="build per-subscriber feed-health emails")
    notify.add_argument("--subscriptions", help="path to subscriptions.yaml")
    notify.add_argument(
        "--table",
        help="read subscribers from this DynamoDB table instead of YAML "
        "(or set SUBSCRIPTIONS_TABLE); the private opt-in store",
    )
    notify.add_argument(
        "--date", type=dt.date.fromisoformat, default=dt.date.today(), help="as-of date"
    )
    notify.add_argument("--expiry-days", type=int, default=60, help="warn within this many days")
    notify.add_argument(
        "--send", action="store_true", help="send via SES (needs --from or SES_FROM)"
    )
    notify.add_argument("--from", dest="sender", help="verified SES sender address")

    portfolio = sub.add_parser(
        "portfolio-digest", help="build the weekly cohort digest for a program liaison"
    )
    portfolio.add_argument("--rollup", help="scope to one rollup id (default: every rollup)")
    portfolio.add_argument(
        "--date", type=dt.date.fromisoformat, default=dt.date.today(), help="as-of date"
    )
    portfolio.add_argument("--out", help="write the digest here instead of stdout")
    portfolio.add_argument(
        "--save",
        action="store_true",
        help="persist this run as the new weekly baseline (default: preview only, "
        "so a re-run never silently consumes a week's movement)",
    )

    coverage = sub.add_parser(
        "coverage-check",
        help="weekly advisory: warn if plain-language coverage dropped (FIX-08)",
    )
    coverage.add_argument(
        "--date", type=dt.date.fromisoformat, default=dt.date.today(), help="as-of date"
    )
    coverage.add_argument(
        "--save",
        action="store_true",
        help="persist this run's coverage as the new baseline (default: preview only)",
    )

    sub.add_parser("rollups", help="publish portfolio rollup artifacts")
    campaign = sub.add_parser(
        "campaign", help="build a bounded, fix-themed support campaign for a rollup"
    )
    campaign.add_argument("--rollup", required=True, help="configured rollup id")
    campaign.add_argument(
        "--kind",
        required=True,
        choices=["calendar-renewal", "accessibility-fields", "rider-information"],
        help="campaign theme",
    )
    campaign.add_argument(
        "--format",
        choices=["json", "markdown"],
        default="json",
        help="output format (default: json)",
    )
    campaign.add_argument(
        "--date", type=dt.date.fromisoformat, default=dt.date.today(), help="baseline date"
    )
    campaign.add_argument("--out", help="write the campaign here instead of stdout")
    sub.add_parser("reindex", help="rebuild index.json from artifacts on disk")
    sub.add_parser("render-site", help="generate crawlable static HTML pages, sitemap, robots")
    sub.add_parser(
        "render-constants",
        help="regenerate web/src/generated/constants.js from the Python definitions",
    )

    report = sub.add_parser(
        "report",
        help="render one agency's scorecard as a self-contained board-ready HTML report",
    )
    report.add_argument("--agency", required=True, help="agency id, e.g. unitrans")
    report.add_argument(
        "--brand",
        type=Path,
        default=None,
        help="brand YAML (name, optional logo path, optional #rrggbb accent) for the cover",
    )
    report.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output path (default: <agency>-board-report.html in the current directory)",
    )

    backfill = sub.add_parser(
        "backfill-state", help="fill missing agency state from the Mobility Database catalog"
    )
    backfill.add_argument("--catalog", help="catalog CSV path or URL (default: Mobility Database)")
    backfill.add_argument("--apply", action="store_true", help="write state into registry shards")

    lint = sub.add_parser("lint", help="check the agency registry for hygiene issues")
    lint.add_argument(
        "--strict",
        action="store_true",
        help="exit non-zero when an agency name is a feed descriptor (for CI)",
    )

    identity = sub.add_parser(
        "identity", help="report feed records, canonical feeds, organizations, and aliases"
    )
    identity.add_argument("--out", help="write the identity ledger JSON here")

    sweep = sub.add_parser(
        "freshness-sweep",
        help="recompute freshness/expiry from the last score without re-fetching",
    )
    sweep.add_argument(
        "--date", type=dt.date.fromisoformat, default=dt.date.today(), help="sweep as-of date"
    )
    sweep.add_argument(
        "--apply", action="store_true", help="publish refreshed artifacts (default: report only)"
    )

    liveness = sub.add_parser(
        "liveness",
        help="conditionally check feeds for change/outage without a full score",
    )
    liveness.add_argument(
        "--apply", action="store_true", help="persist liveness state (default: report only)"
    )
    liveness.add_argument(
        "--timeout", type=float, default=30.0, help="per-feed request timeout in seconds"
    )
    liveness.add_argument(
        "--changed-out",
        dest="changed_out",
        help="write the ids of changed/recovered feeds here (one per line) to re-score",
    )
    liveness.add_argument(
        "--only", help="check only the feed ids listed in this file (one per line)"
    )

    cadence = sub.add_parser(
        "cadence",
        help="list the feeds due for a liveness check this cycle, by tier",
    )
    cadence.add_argument(
        "--at", type=int, help="hour of day 0-23 for the cycle (default: now, UTC)"
    )
    cadence.add_argument("--out", help="write due feed ids here (one per line)")

    rthealth = sub.add_parser(
        "rt-health",
        help="sample realtime feeds and append an uptime/freshness observation",
    )
    rthealth.add_argument("--agency", help="one agency id (default: all)")
    rthealth.add_argument("--samples", type=int, default=2, help="samples per feed this run")
    rthealth.add_argument(
        "--interval", type=int, default=30, help="seconds between samples (polling etiquette)"
    )

    rtarchive = sub.add_parser(
        "rt-archive",
        help="high-cadence realtime archiving session for one agency (ADR 0012)",
    )
    rtarchive.add_argument("--agency", required=True, help="agency id")
    rtarchive.add_argument(
        "--duration", type=int, default=600, help="session length in seconds (default: 600)"
    )
    rtarchive.add_argument(
        "--interval", type=int, default=20, help="seconds between polls (spec cadence)"
    )

    feedapi = sub.add_parser(
        "feedapi",
        help="inspect a feed's Mobility Feed API dataset and validation summary",
    )
    feedapi.add_argument("feed_id", help="Feed API id (e.g. mdb-1234) or a bare mdb id")
    feedapi.add_argument(
        "--token",
        help="Feed API bearer token (default: MOBILITY_FEED_API_TOKEN env var)",
    )

    canary = sub.add_parser(
        "canary",
        help="shadow-score a candidate validator version and write an impact report (FIX-06)",
    )
    canary.add_argument(
        "--candidate-version",
        required=True,
        help="gtfs-validator version to shadow-score against the pinned one, e.g. 8.1.0",
    )
    canary.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="how many agencies to dual-score (deterministic stratified sample)",
    )
    canary.add_argument("--seed", type=int, default=0, help="rotate the deterministic sample")
    canary.add_argument(
        "--out",
        help="directory for the Markdown + JSON impact report (default: data/canary)",
    )
    canary.add_argument(
        "--date",
        type=dt.date.fromisoformat,
        default=dt.date.today(),
        help="snapshot date to fetch/score (default: today)",
    )

    reproduce = sub.add_parser(
        "reproduce",
        help=(
            "re-derive a published grade from the archived raw feed bytes and diff it "
            "against the published artifact (FIX-02)"
        ),
    )
    reproduce.add_argument("agency", help="agency id, e.g. unitrans")
    reproduce.add_argument("date", help="published snapshot date, YYYY-MM-DD")

    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # The ad-hoc scorer is intentionally registry-free: it is the Marketplace
    # action and installed-wheel entry point for checking one supplied URL.
    # Every registry-backed command loads only after argparse has handled help,
    # so `scorecard --help` and `scorecard try` work from a standalone wheel.
    if args.command != "try":
        load_agencies()
        agency_id = getattr(args, "agency", None)
        if agency_id and agency_id not in AGENCIES:
            parser.error(f"unknown agency: {agency_id}")

    handlers = {
        "run": _cmd_run,
        "try": _cmd_try,
        "sync": _cmd_sync,
        "discover": _cmd_discover,
        "prune": _cmd_prune,
        "vendors": _cmd_vendors,
        "vendor-report": _cmd_vendor_report,
        "vendor-radar": _cmd_vendor_radar,
        "evidence-packet": _cmd_evidence_packet,
        "fix-outcomes": _cmd_fix_outcomes,
        "dataset": _cmd_dataset,
        "sensitivity": _cmd_sensitivity,
        "ntd": _cmd_ntd,
        "ntd-crosswalk": _cmd_ntd_crosswalk,
        "ntd-ridership": _cmd_ntd_ridership,
        "shards": _cmd_shards,
        "activation-targets": _cmd_activation_targets,
        "activation-hydrate": _cmd_activation_hydrate,
        "run-summary": _cmd_run_summary,
        "alerts": _cmd_alerts,
        "notify": _cmd_notify,
        "portfolio-digest": _cmd_portfolio_digest,
        "coverage-check": _cmd_coverage_check,
        "rollups": _cmd_rollups,
        "campaign": _cmd_campaign,
        "reindex": _cmd_reindex,
        "render-site": _cmd_render_site,
        "render-constants": _cmd_render_constants,
        "report": _cmd_report,
        "backfill-state": _cmd_backfill_state,
        "lint": _cmd_lint,
        "identity": _cmd_identity,
        "freshness-sweep": _cmd_freshness_sweep,
        "liveness": _cmd_liveness,
        "cadence": _cmd_cadence,
        "feedapi": _cmd_feedapi,
        "canary": _cmd_canary,
        "onboard": _cmd_onboard,
        "autofix": _cmd_autofix,
        "gbfs": _cmd_gbfs,
        "equity": _cmd_equity,
        "canada-equity": _cmd_canada_equity,
        "query": _cmd_query,
        "otp": _cmd_otp,
        "otp-batch": _cmd_otp_batch,
        "rt-health": _cmd_rt_health,
        "rt-archive": _cmd_rt_archive,
        "reproduce": _cmd_reproduce,
    }
    handler = handlers.get(args.command)
    if handler is None:
        return 2
    return handler(args, parser)


if __name__ == "__main__":
    sys.exit(main())
