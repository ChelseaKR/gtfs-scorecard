"""A read-only MCP (Model Context Protocol) server over the published scorecard.

AI assistants became a mainstream consumer of civic datasets; MCP is the
protocol they speak (docs/expansion-ideation-2026-07.md, section C). This
server lets an agent answer questions like "why did my grade drop and what do
I tell my vendor" grounded in the same published JSON the site serves, with
zero write surface and no key: every tool is a read of gtfsscorecard.org.

The transport is MCP's stdio framing (newline-delimited JSON-RPC 2.0), written
directly against the spec rather than pulling in an SDK, mirroring the repo's
stdlib-only Lambda handler. The protocol core is pure functions over dicts, so
the whole conversation is testable without a socket or a subprocess.

Run it:  ``scorecard-mcp``  (or ``python -m scorecard_pipeline.mcp_server``)

Client config (Claude Desktop / any MCP client), see docs/mcp.md:
    {"mcpServers": {"gtfs-scorecard": {"command": "scorecard-mcp"}}}

``SCORECARD_BASE_URL`` overrides the data source, e.g. for a fork or a local
preview server; a fork with its own ``instance.yaml`` (EXP-15,
``docs/fork-quickstart.md``) already gets the right default with no env var
needed.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from .instance import BASE_URL as DEFAULT_BASE_URL
from .metrics import presented_freshness_summary, resolve_service_horizon_status
from .ntd import presented_readiness as presented_ntd_readiness

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "gtfs-scorecard", "version": "1.0.0"}

Fetch = Callable[[str], Any]


def _http_fetch(url: str) -> Any:
    req = urllib.request.Request(  # noqa: S310 - our own site (_base_url()/env override), not attacker-controlled
        url, headers={"User-Agent": "gtfs-scorecard-mcp"}
    )
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - our own site, not attacker-controlled
        return json.loads(resp.read().decode("utf-8"))


def _base_url() -> str:
    return os.environ.get("SCORECARD_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


# ---- tools ----------------------------------------------------------------


# The catalog is ~1 MB and stable within a run; a long-lived server answering
# several searches in one conversation should not refetch it every call.
_CATALOG_TTL_SECONDS = 300.0
_catalog_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}


def _catalog(fetch: Fetch) -> list[dict[str, Any]]:
    base = _base_url()
    cached = _catalog_cache.get(base)
    now = time.monotonic()
    if cached and now - cached[0] < _CATALOG_TTL_SECONDS:
        return cached[1]
    rows = list(fetch(f"{base}/catalog.json").get("agencies", []))
    _catalog_cache[base] = (now, rows)
    return rows


def search_agencies(
    fetch: Fetch,
    query: str = "",
    state: str = "",
    grade: str = "",
    limit: int = 20,
    country: str = "",
    subdivision: str = "",
) -> dict[str, Any]:
    """Search the covered catalog by identity, portable location, or grade.

    ``state`` remains as a compatibility input and also matches the portable
    subdivision name. New clients should send an ISO country code plus either
    an ISO subdivision code or its display name.
    """
    q = query.strip().lower()
    wanted_country = country.strip().upper()
    wanted_subdivision = subdivision.strip().casefold()
    wanted_state = state.strip().casefold()

    def _country(row: dict[str, Any]) -> str:
        # Catalog rows published before the portable contract are US records.
        return str(row.get("country") or "US").strip().upper()

    def _subdivision_matches(row: dict[str, Any], wanted: str) -> bool:
        return wanted in {
            str(row.get("subdivision_code") or "").strip().casefold(),
            str(row.get("subdivision_name") or "").strip().casefold(),
        }

    def _query_text(row: dict[str, Any]) -> str:
        return " ".join(
            str(row.get(field) or "")
            for field in (
                "name",
                "id",
                "country",
                "subdivision_code",
                "subdivision_name",
                "state",
            )
        ).lower()

    rows = [
        r
        for r in _catalog(fetch)
        if (not q or q in _query_text(r))
        and (not wanted_country or _country(r) == wanted_country)
        and (not wanted_subdivision or _subdivision_matches(r, wanted_subdivision))
        and (
            not wanted_state
            or wanted_state
            in {
                str(r.get("state") or "").strip().casefold(),
                str(r.get("subdivision_name") or "").strip().casefold(),
            }
        )
        and (not grade or str(r.get("grade", "")).upper() == grade.strip().upper())
    ]
    slim = [
        {
            "id": r.get("id"),
            "name": r.get("name"),
            "grade": r.get("grade"),
            "score": r.get("score"),
            "state": r.get("state"),
            "country": _country(r),
            "subdivision_code": r.get("subdivision_code"),
            "subdivision_name": r.get("subdivision_name"),
            "days_until_expiry": r.get("days_until_expiry"),
            "service_horizon_status": resolve_service_horizon_status(r),
            "expiry_status": r.get("expiry_status"),
            "national_percentile": None,
            "peer_percentile": None,
            "ntd_ready": r.get("ntd_ready"),
            "google_gate": r.get("google_gate"),
            "scorecard_url": r.get("scorecard_url"),
        }
        for r in rows
    ]
    # Honour the caller's limit exactly, clamped to 0..100; limit=0 means none.
    return {"total": len(slim), "agencies": slim[: max(0, min(int(limit), 100))]}


def get_scorecard(fetch: Fetch, agency_id: str) -> dict[str, Any]:
    """One agency's latest scorecard, trimmed to what an assistant needs."""
    art = fetch(f"{_base_url()}/data/artifacts/{agency_id}/latest.json")
    categories: dict[str, Any] = {}
    findings: list[dict[str, Any]] = []
    for key, cat in (art.get("categories") or {}).items():
        category = {
            "status": cat.get("status"),
            "score": cat.get("score"),
            "summary": (
                presented_freshness_summary(cat, art.get("snapshot_date"))
                if key == "freshness"
                else cat.get("summary")
            ),
        }
        if key == "freshness":
            details = cat.get("details") or {}
            category["service_horizon_status"] = resolve_service_horizon_status(
                details, art.get("snapshot_date")
            )
            category["effective_expiry_date"] = details.get("effective_expiry_date")
        categories[key] = category
        if cat.get("status") != "measured":
            continue
        for f in cat.get("findings", []):
            findings.append(
                {
                    "category": key,
                    "severity": f.get("severity"),
                    "count": f.get("count"),
                    "what": f.get("what"),
                    "why": f.get("why"),
                    "fix": f.get("fix"),
                    "effort": f.get("effort"),
                    "code": f.get("code"),
                    "fix_guide_url": f"{_base_url()}/fix/{f.get('code')}/",
                }
            )
    return {
        "agency": art.get("agency"),
        "snapshot_date": art.get("snapshot_date"),
        "overall": art.get("overall"),
        "categories": categories,
        "top_fixes": art.get("top_fixes"),
        "findings": findings,
        "ntd_readiness": presented_ntd_readiness(art),
        "scorecard_url": f"{_base_url()}/agency/{agency_id}/",
        "note": (
            "A data-quality lens on the published GTFS, not an official compliance "
            "determination. Findings are framed as fixes."
        ),
    }


def national_stats(fetch: Fetch) -> dict[str, Any]:
    """Legacy United States policy view, retained for MCP client compatibility.

    The historical ``stats`` member describes the full covered corpus and stays
    byte-compatible. NTD readiness is explicitly a United States-only policy
    overlay. New geography-neutral callers should use ``coverage_stats``.
    """
    return {
        "stats": fetch(f"{_base_url()}/api/v1/stats.json"),
        "ntd_readiness": fetch(f"{_base_url()}/ntd.json"),
        "scope": {
            "stats": "covered_corpus",
            "ntd_readiness": {"country": "US", "country_name": "United States"},
            "note": (
                "NTD readiness is a United States-only policy measure. The legacy stats "
                "member covers every feed tracked when it was generated; use coverage_stats "
                "for portable country and subdivision totals."
            ),
        },
    }


def coverage_stats(fetch: Fetch) -> dict[str, Any]:
    """Geography-neutral covered-set totals with country/subdivision rollups."""
    return {
        "stats": fetch(f"{_base_url()}/api/v1/stats.json"),
        "by_location": fetch(f"{_base_url()}/api/v1/by-location.json"),
        "note": (
            "Counts describe the public feeds this scorecard tracks, not every transit "
            "operator in a country. Absence means not covered, never failing."
        ),
    }


#: The one sentence every response repeats. An assistant will paraphrase what it
#: is given; if the framing is not in the payload it does not survive the
#: paraphrase, and a data-quality grade starts being read as a compliance verdict.
LENS_NOTE = (
    "A data-quality lens on the published GTFS, not an official compliance "
    "determination. Findings are framed as fixes."
)

#: Ceilings on what one tool call can return. An MCP response goes into a model's
#: context window, so an unbounded history or a thousand-row rollup is not a
#: richer answer, it is a truncated one somewhere the caller cannot see.
MAX_HISTORY_POINTS = 120
MAX_ROLLUP_MEMBERS = 100
MAX_SHARED_FIXES = 20


def _history_points(fetch: Fetch, agency_id: str) -> tuple[str, list[dict[str, Any]]]:
    index = fetch(f"{_base_url()}/data/artifacts/index.json")
    record = (index.get("agencies") or {}).get(agency_id)
    if not isinstance(record, dict):
        raise ValueError(f"no tracked feed record for agency id {agency_id!r}")
    points = [p for p in record.get("history") or [] if isinstance(p, dict)]
    points.sort(key=lambda p: str(p.get("date") or ""))
    return str(record.get("name") or ""), points


def get_history(
    fetch: Fetch, agency_id: str, since: str = "", limit: int = MAX_HISTORY_POINTS
) -> dict[str, Any]:
    """One feed's dated history, with every measurement-contract boundary marked.

    The published history carries each point's producer contract, so this can
    say which adjacent pairs are the same measurement. Where they are not, the
    point is marked ``comparable_with_previous: false`` and **no change is
    described across it** — a rubric or validator release moving a score is not
    the feed moving, and an assistant handed an unmarked series will narrate it
    as though it were.

    Finding-level change is reported for the most recent adjacent pair only, and
    only when that pair is comparable, because it costs one fetch per dated
    artifact and an unbounded walk of the history is not something a tool call
    should do quietly.
    """
    from .comparisons import producer_contract, same_producer_contract

    name, points = _history_points(fetch, agency_id)
    if since:
        points = [p for p in points if str(p.get("date") or "") >= since]
    bounded = points[-max(1, min(int(limit), MAX_HISTORY_POINTS)) :]

    rows: list[dict[str, Any]] = []
    for position, point in enumerate(bounded):
        comparable: bool | None = None
        if position > 0:
            comparable = same_producer_contract(bounded[position - 1], point)
        rows.append(
            {
                "date": point.get("date"),
                "grade": point.get("grade"),
                "score": point.get("score"),
                "categories": point.get("categories"),
                "days_until_expiry": point.get("days_until_expiry"),
                "comparable_with_previous": comparable,
                "measured_categories": list(producer_contract(point)[5]),
            }
        )

    changes = _latest_finding_changes(fetch, agency_id, bounded)
    return {
        "agency_id": agency_id,
        "name": name,
        "returned": len(rows),
        "available": len(points),
        "truncated": len(rows) < len(points),
        "history": rows,
        "latest_change": changes,
        "note": (
            f"{LENS_NOTE} A point marked comparable_with_previous: false was scored "
            "under a different rubric, scoring profile, validator, reader archive "
            "profile, or measured-category set; the difference across that boundary "
            "is not a change in the feed and must not be described as one."
        ),
    }


def _latest_finding_changes(
    fetch: Fetch, agency_id: str, points: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Findings that appeared or cleared between the last two dated snapshots.

    ``None`` when there is nothing comparable to say, always with a reason, so a
    caller can tell "no findings moved" from "we refuse to claim anything here".
    """
    from .comparisons import same_producer_contract
    from .timemachine import finding_codes

    if len(points) < 2:
        return {
            "comparable": False,
            "reason": "only one dated snapshot is available, so nothing can be compared",
        }
    previous, latest = points[-2], points[-1]
    if not same_producer_contract(previous, latest):
        return {
            "comparable": False,
            "from_date": previous.get("date"),
            "to_date": latest.get("date"),
            "reason": (
                "the two most recent snapshots are different measurements, so no "
                "finding is described as new or cleared across them"
            ),
        }
    base = _base_url()
    before = fetch(f"{base}/data/artifacts/{agency_id}/{previous.get('date')}.json")
    after = fetch(f"{base}/data/artifacts/{agency_id}/{latest.get('date')}.json")
    before_codes, after_codes = finding_codes(before), finding_codes(after)
    return {
        "comparable": True,
        "from_date": previous.get("date"),
        "to_date": latest.get("date"),
        "appeared": [
            {"code": code, "what": what}
            for code, what in sorted(after_codes.items())
            if code not in before_codes
        ],
        "cleared": [
            {"code": code, "what": what}
            for code, what in sorted(before_codes.items())
            if code not in after_codes
        ],
    }


def explain_finding(code: str, tool: str = "") -> dict[str, Any]:
    """The fix recipe for a notice code, its rule link, and tool-specific guidance.

    Offline: everything here is in this package. Two refusals are the point.

    A code with no curated recipe returns ``recipe: null`` and the rule link
    alone. ``notices.translate`` has a generated fallback for exactly this case
    and it is deliberately **not** used: it is honest wording for a scorecard
    page next to a real count, but as an answer to "what does this code mean" it
    is a sentence the project made up being handed to an assistant as knowledge.

    A ``tool`` this project has no profile for returns ``tool_guidance: null``
    and says which keys it does know. Naming the wrong vendor in a fix path is
    worse than being generic.
    """
    from .notices import TRANSLATIONS
    from .rule_links import RULE_LINKS, rule_link_for
    from .tool_profiles import PROFILES_BY_KEY, profile_for_key

    normalized = str(code).strip()
    translation = TRANSLATIONS.get(normalized)
    link = rule_link_for(normalized)
    profile = profile_for_key(tool) if tool else None
    return {
        "code": normalized,
        "recipe": (
            {
                "what": translation.what,
                "why": translation.why,
                "fix": translation.fix,
                "effort": translation.effort,
            }
            if translation is not None
            else None
        ),
        "has_recipe": translation is not None,
        "fix_guide_url": (f"{_base_url()}/fix/{normalized}/" if normalized in RULE_LINKS else None),
        "rule": (
            {"url": link.url, "authority": link.authority, "canonical_notice": link.canonical}
            if link is not None
            else None
        ),
        "tool_guidance": (
            {
                "key": profile.key,
                "name": profile.name,
                "kind": profile.kind,
                "fix_path": profile.fix_path,
                "request_lede": profile.request_lede,
            }
            if profile is not None
            else None
        ),
        "known_tools": sorted(PROFILES_BY_KEY) if tool and profile is None else None,
        "note": (
            LENS_NOTE
            if translation is not None
            else (
                "No fix recipe is written for this code. The rule link is the "
                f"authority; nothing here describes it further. {LENS_NOTE}"
            )
        ),
    }


def get_rollup(fetch: Fetch, rollup_id: str) -> dict[str, Any]:
    """One program rollup: its cohort's shared fixes and members needing attention."""
    payload = fetch(f"{_base_url()}/data/artifacts/rollups/{rollup_id}.json")
    members = [m for m in payload.get("members") or [] if isinstance(m, dict)]
    shown = members[:MAX_ROLLUP_MEMBERS]
    return {
        "rollup": payload.get("rollup"),
        "agency_count": payload.get("agency_count"),
        "average_score": payload.get("average_score"),
        "grade_distribution": payload.get("grade_distribution"),
        "expired": payload.get("expired"),
        "needs_attention": payload.get("needs_attention"),
        "shared_fixes": (payload.get("common_fixes") or [])[:MAX_SHARED_FIXES],
        "members": [
            {
                "id": m.get("id"),
                "name": m.get("name"),
                "grade": m.get("grade"),
                "score": m.get("score"),
                "expiry_status": m.get("expiry_status"),
                "needs_attention": m.get("needs_attention"),
                "attention_reason": m.get("attention_reason"),
                "top_fix": m.get("top_fix"),
            }
            for m in shown
        ],
        "members_returned": len(shown),
        "members_total": len(members),
        "members_truncated": len(shown) < len(members),
        "note": (
            f"{LENS_NOTE} A shared fix is one many feeds in this cohort would make; "
            "it is not a ranking of the agencies."
        ),
    }


def get_evidence_packet(fetch: Fetch, agency_id: str) -> dict[str, Any]:
    """The deterministic vendor remediation packet for one agency's latest scorecard."""
    from .evidence_packet import build_evidence_packet

    base = _base_url()
    artifact = fetch(f"{base}/data/artifacts/{agency_id}/latest.json")
    packet = build_evidence_packet(artifact, scorecard_url=f"{base}/agency/{agency_id}/")
    packet["note"] = LENS_NOTE
    return packet


def coverage_for(fetch: Fetch, country: str, subdivision: str = "") -> dict[str, Any]:
    """Covered-set totals for one country, or one subdivision inside it.

    A country this scorecard does not cover returns explicit zeros **labelled as
    not covered**, never a bare zero: "we track no feeds here" and "there are no
    feeds here" are different statements and only the first is one we can make.
    """
    payload = fetch(f"{_base_url()}/api/v1/by-location.json")
    wanted = str(country).strip().upper()
    countries = [c for c in payload.get("countries") or [] if isinstance(c, dict)]
    match = next((c for c in countries if str(c.get("country_code") or "").upper() == wanted), None)
    if match is None:
        return {
            "country_code": wanted,
            "covered": False,
            "note": (
                f"This scorecard tracks no feeds in {wanted or 'that country'}. That is "
                f"a statement about this project's coverage, not about whether transit "
                f"agencies there publish GTFS. {LENS_NOTE}"
            ),
        }
    subdivisions = [s for s in match.get("subdivisions") or [] if isinstance(s, dict)]
    wanted_sub = str(subdivision).strip().casefold()
    if wanted_sub:
        found = next(
            (
                s
                for s in subdivisions
                if wanted_sub
                in {
                    str(s.get("subdivision_code") or "").casefold(),
                    str(s.get("subdivision_name") or "").casefold(),
                }
            ),
            None,
        )
        if found is None:
            return {
                "country_code": match.get("country_code"),
                "country_name": match.get("country_name"),
                "subdivision": subdivision,
                "covered": False,
                "note": (
                    f"This scorecard tracks no feeds in that subdivision of "
                    f"{match.get('country_name')}. That is a statement about this "
                    f"project's coverage, not about whether agencies there publish "
                    f"GTFS. {LENS_NOTE}"
                ),
            }
        return {
            "country_code": match.get("country_code"),
            "country_name": match.get("country_name"),
            "subdivision_code": found.get("subdivision_code"),
            "subdivision_name": found.get("subdivision_name"),
            "covered": True,
            "count": found.get("count"),
            "median_score": found.get("median_score"),
            "grade_distribution": found.get("grade_distribution"),
            "comparison_eligible_count": found.get("comparison_eligible_count"),
            "note": LENS_NOTE,
        }
    return {
        "country_code": match.get("country_code"),
        "country_name": match.get("country_name"),
        "covered": True,
        "count": match.get("count"),
        "median_score": match.get("median_score"),
        "grade_distribution": match.get("grade_distribution"),
        "comparison_eligible_count": match.get("comparison_eligible_count"),
        "subdivisions": [
            {
                "subdivision_code": s.get("subdivision_code"),
                "subdivision_name": s.get("subdivision_name"),
                "count": s.get("count"),
                "median_score": s.get("median_score"),
            }
            for s in subdivisions
        ],
        "note": LENS_NOTE,
    }


TOOLS: list[dict[str, Any]] = [
    {
        "name": "search_agencies",
        "description": (
            "Search tracked transit agencies by name, id, ISO country, ISO subdivision "
            "or subdivision name, legacy state, or letter grade. Returns portable "
            "location, grade, score, expiry, and applicable readiness fields."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Name fragment or exact agency id"},
                "country": {
                    "type": "string",
                    "description": "ISO 3166-1 alpha-2 country code, e.g. CA",
                },
                "subdivision": {
                    "type": "string",
                    "description": "ISO 3166-2 code or subdivision name, e.g. CA-ON or Ontario",
                },
                "state": {
                    "type": "string",
                    "description": "Legacy state/province-name filter; prefer subdivision",
                },
                "grade": {"type": "string", "description": "Letter grade A-F"},
                "limit": {"type": "integer", "description": "Max results (default 20)"},
            },
        },
    },
    {
        "name": "get_scorecard",
        "description": (
            "An agency's latest scorecard: overall grade, category scores and "
            "plain-language summaries, every finding with its fix and effort, "
            "top fixes, and NTD GTFS readiness."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agency_id": {"type": "string", "description": "Agency slug, e.g. 'unitrans'"}
            },
            "required": ["agency_id"],
        },
    },
    {
        "name": "national_stats",
        "description": (
            "Legacy United States policy view: NTD GTFS readiness nationally and by "
            "state, plus the backwards-compatible covered-corpus stats member. Prefer "
            "coverage_stats for geography-neutral totals."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "coverage_stats",
        "description": (
            "Coverage-wide quality totals and portable country/subdivision rollups over "
            "the feeds this scorecard tracks."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_history",
        "description": (
            "One feed's dated grade and score history, with every measurement-contract "
            "boundary marked. A point marked comparable_with_previous: false was scored "
            "under a different rubric, scoring profile, validator, reader archive "
            "profile, or measured-category set, and the difference across it is not a "
            "change in the feed. Also reports findings that appeared or cleared between "
            "the two most recent snapshots, but only when those two are comparable."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agency_id": {"type": "string", "description": "Agency slug, e.g. 'unitrans'"},
                "since": {
                    "type": "string",
                    "description": "Earliest snapshot date to include, YYYY-MM-DD",
                },
                "limit": {
                    "type": "integer",
                    "description": f"Max dated points (default and ceiling {MAX_HISTORY_POINTS})",
                },
            },
            "required": ["agency_id"],
        },
    },
    {
        "name": "explain_finding",
        "description": (
            "The fix recipe for one validator or scorecard notice code, its "
            "authoritative rule link, and, when a producing tool is named, that tool's "
            "fix path. A code with no written recipe returns the rule link alone and "
            "says so; nothing is described beyond what is written."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Notice code, e.g. 'expired_calendar'",
                },
                "tool": {
                    "type": "string",
                    "description": (
                        "Optional producing-tool key: trillium, gtfs_builder, remix, "
                        "passio, repo, or archive"
                    ),
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "get_rollup",
        "description": (
            "One program rollup: the cohort's shared fixes, grade distribution, and the "
            "members needing attention. Shared fixes describe work many feeds share; "
            "they are not a ranking of agencies."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "rollup_id": {"type": "string", "description": "Rollup id, e.g. 'california'"}
            },
            "required": ["rollup_id"],
        },
    },
    {
        "name": "get_evidence_packet",
        "description": (
            "The deterministic vendor remediation packet for one agency's latest "
            "scorecard: the producer contract, the work items with their acceptance "
            "tests, and the feed identity they were measured against."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "agency_id": {"type": "string", "description": "Agency slug, e.g. 'unitrans'"}
            },
            "required": ["agency_id"],
        },
    },
    {
        "name": "coverage_for",
        "description": (
            "Covered-set totals for one ISO country, or one subdivision inside it. A "
            "place this scorecard does not track is reported as not covered rather than "
            "as zero feeds: absence of coverage is not absence of transit data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "country": {
                    "type": "string",
                    "description": "ISO 3166-1 alpha-2 country code, e.g. US",
                },
                "subdivision": {
                    "type": "string",
                    "description": "Optional ISO 3166-2 code or subdivision name",
                },
            },
            "required": ["country"],
        },
    },
]


def _required(arguments: dict[str, Any], key: str) -> str:
    """A required string argument, or a refusal naming it.

    Not defaulted to "": an empty agency id would build a URL that fetches some
    other document and report whatever came back.
    """
    value = str(arguments.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


#: Tool name -> the adapter that reads its arguments and calls it. A table
#: rather than a chain of ifs so adding a tool cannot quietly push the dispatch
#: past the complexity ceiling, and so `TOOLS` and the dispatch can be asserted
#: to name the same set.
_HANDLERS: dict[str, Callable[[dict[str, Any], Fetch], Any]] = {
    "search_agencies": lambda a, f: search_agencies(
        f,
        query=str(a.get("query", "")),
        state=str(a.get("state", "")),
        grade=str(a.get("grade", "")),
        limit=int(a.get("limit", 20)),
        country=str(a.get("country", "")),
        subdivision=str(a.get("subdivision", "")),
    ),
    "get_scorecard": lambda a, f: get_scorecard(f, _required(a, "agency_id")),
    "national_stats": lambda a, f: national_stats(f),
    "coverage_stats": lambda a, f: coverage_stats(f),
    "get_history": lambda a, f: get_history(
        f,
        _required(a, "agency_id"),
        since=str(a.get("since", "")).strip(),
        limit=int(a.get("limit", MAX_HISTORY_POINTS)),
    ),
    "explain_finding": lambda a, f: explain_finding(
        _required(a, "code"), tool=str(a.get("tool", ""))
    ),
    "get_rollup": lambda a, f: get_rollup(f, _required(a, "rollup_id")),
    "get_evidence_packet": lambda a, f: get_evidence_packet(f, _required(a, "agency_id")),
    "coverage_for": lambda a, f: coverage_for(
        f, _required(a, "country"), subdivision=str(a.get("subdivision", ""))
    ),
}


def call_tool(name: str, arguments: dict[str, Any], fetch: Fetch = _http_fetch) -> Any:
    handler = _HANDLERS.get(name)
    if handler is None:
        raise ValueError(f"unknown tool: {name}")
    return handler(arguments, fetch)


# ---- JSON-RPC / MCP plumbing ----------------------------------------------


def _result(req_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def handle_request(msg: dict[str, Any], fetch: Fetch = _http_fetch) -> dict[str, Any] | None:
    """One JSON-RPC message in, one (or None for notifications) out. Pure but for
    the injected fetch, so the whole protocol conversation is unit-testable."""
    method = msg.get("method", "")
    req_id = msg.get("id")
    if method.startswith("notifications/"):
        return None
    if method == "initialize":
        return _result(
            req_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": SERVER_INFO,
            },
        )
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": TOOLS})
    if method == "tools/call":
        params = msg.get("params") or {}
        name = str(params.get("name", ""))
        arguments = params.get("arguments") or {}
        try:
            payload = call_tool(name, arguments, fetch)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return _result(
                    req_id,
                    {
                        "content": [
                            {
                                "type": "text",
                                "text": "Not found. Check the agency id with search_agencies.",
                            }
                        ],
                        "isError": True,
                    },
                )
            return _result(
                req_id,
                {
                    "content": [{"type": "text", "text": f"Upstream error: HTTP {exc.code}"}],
                    "isError": True,
                },
            )
        except (ValueError, urllib.error.URLError) as exc:
            return _result(
                req_id,
                {"content": [{"type": "text", "text": str(exc)}], "isError": True},
            )
        return _result(
            req_id,
            {"content": [{"type": "text", "text": json.dumps(payload, indent=1)}]},
        )
    return _error(req_id, -32601, f"method not found: {method}")


def main() -> None:
    """Serve MCP over stdio: one JSON-RPC message per line, LSP-free framing."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = handle_request(msg)
        if reply is not None:
            sys.stdout.write(json.dumps(reply, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
