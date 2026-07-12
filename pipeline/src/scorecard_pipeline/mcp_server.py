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
            "expiry_status": r.get("expiry_status"),
            "national_percentile": r.get("national_percentile"),
            "peer_percentile": r.get("peer_percentile"),
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
        categories[key] = {
            "status": cat.get("status"),
            "score": cat.get("score"),
            "summary": cat.get("summary"),
        }
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
        "ntd_readiness": art.get("ntd_readiness"),
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
]


def call_tool(name: str, arguments: dict[str, Any], fetch: Fetch = _http_fetch) -> Any:
    if name == "search_agencies":
        return search_agencies(
            fetch,
            query=str(arguments.get("query", "")),
            state=str(arguments.get("state", "")),
            grade=str(arguments.get("grade", "")),
            limit=int(arguments.get("limit", 20)),
            country=str(arguments.get("country", "")),
            subdivision=str(arguments.get("subdivision", "")),
        )
    if name == "get_scorecard":
        agency_id = str(arguments.get("agency_id", "")).strip()
        if not agency_id:
            raise ValueError("agency_id is required")
        return get_scorecard(fetch, agency_id)
    if name == "national_stats":
        return national_stats(fetch)
    if name == "coverage_stats":
        return coverage_stats(fetch)
    raise ValueError(f"unknown tool: {name}")


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
