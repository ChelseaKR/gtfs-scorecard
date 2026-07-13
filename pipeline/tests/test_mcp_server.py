"""Tests for the read-only MCP server (protocol handling and tool logic)."""

from __future__ import annotations

import copy
import json
from typing import Any

from scorecard_pipeline.mcp_server import TOOLS, call_tool, handle_request

_CATALOG = {
    "agencies": [
        {
            "id": "unitrans",
            "name": "Unitrans (ASUCD / City of Davis)",
            "grade": "B",
            "score": 80.8,
            "state": "California",
            "country": "US",
            "subdivision_code": "US-CA",
            "subdivision_name": "California",
            "days_until_expiry": 83,
            "service_horizon_status": "within_review_threshold",
            "ntd_ready": "ready",
            "scorecard_url": "https://gtfsscorecard.org/agency/unitrans/",
        },
        {
            "id": "barrie-transit",
            "name": "Barrie Transit (Ontario)",
            "grade": "C",
            "score": 71.0,
            "state": None,
            "country": "CA",
            "subdivision_code": "CA-ON",
            "subdivision_name": "Ontario",
            "days_until_expiry": 40,
            "service_horizon_status": "within_review_threshold",
            "ntd_ready": None,
            "scorecard_url": "https://gtfsscorecard.org/agency/barrie-transit/",
        },
    ]
}

_ARTIFACT = {
    "agency": {"id": "unitrans", "name": "Unitrans"},
    "snapshot_date": "2026-07-01",
    "overall": {"grade": "B", "score": 80.8},
    "categories": {
        "correctness": {
            "status": "measured",
            "score": 84.8,
            "summary": "4 kinds of issue.",
            "findings": [
                {
                    "severity": "WARNING",
                    "count": 72,
                    "what": "Stops far from shape.",
                    "why": "Riders get pointed to the wrong corner.",
                    "fix": "Re-snap stops in your export tool.",
                    "effort": "An afternoon.",
                    "code": "stop_too_far_from_shape",
                }
            ],
        },
        "realtime": {"status": "not_yet_measured", "summary": "Needs a key."},
    },
    "top_fixes": [{"fix": "Re-snap stops."}],
    "ntd_readiness": {"status": "ready"},
}


def _fetch(url: str) -> Any:
    if url.endswith("/catalog.json"):
        return _CATALOG
    if url.endswith("/data/artifacts/unitrans/latest.json"):
        return _ARTIFACT
    if url.endswith("/api/v1/stats.json"):
        return {"agencies": 2}
    if url.endswith("/api/v1/by-location.json"):
        return {
            "countries": [
                {"country_code": "US", "country_name": "United States", "count": 1},
                {"country_code": "CA", "country_name": "Canada", "count": 1},
            ]
        }
    if url.endswith("/ntd.json"):
        return {"pct_ready": 50.0}
    raise AssertionError(f"unexpected fetch: {url}")


def test_initialize_and_tools_list_shape() -> None:
    init = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"}, _fetch)
    assert init is not None
    assert init["result"]["serverInfo"]["name"] == "gtfs-scorecard"
    assert "tools" in init["result"]["capabilities"]
    listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, _fetch)
    assert listed is not None
    names = {t["name"] for t in listed["result"]["tools"]}
    assert names == {t["name"] for t in TOOLS}
    assert {"search_agencies", "get_scorecard", "coverage_stats", "national_stats"} <= names
    # Every tool carries a JSON schema, the contract a client codes against.
    assert all("inputSchema" in t for t in listed["result"]["tools"])


def test_notifications_get_no_reply_and_unknown_methods_error() -> None:
    assert handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}, _fetch) is None
    bad = handle_request({"jsonrpc": "2.0", "id": 3, "method": "nope"}, _fetch)
    assert bad is not None and bad["error"]["code"] == -32601


def test_search_agencies_filters_by_state_and_grade() -> None:
    ontario = call_tool("search_agencies", {"state": "Ontario"}, _fetch)
    assert [a["id"] for a in ontario["agencies"]] == ["barrie-transit"]
    graded = call_tool("search_agencies", {"grade": "b"}, _fetch)
    assert [a["id"] for a in graded["agencies"]] == ["unitrans"]
    named = call_tool("search_agencies", {"query": "davis"}, _fetch)
    assert named["total"] == 1


def test_search_agencies_filters_and_returns_portable_location() -> None:
    by_country = call_tool("search_agencies", {"country": "ca"}, _fetch)
    assert [a["id"] for a in by_country["agencies"]] == ["barrie-transit"]
    by_code = call_tool("search_agencies", {"subdivision": "ca-on"}, _fetch)
    assert by_code["agencies"] == by_country["agencies"]
    by_name = call_tool("search_agencies", {"subdivision": "Ontario"}, _fetch)
    assert by_name["agencies"] == by_country["agencies"]
    row = by_country["agencies"][0]
    assert (row["country"], row["subdivision_code"], row["subdivision_name"]) == (
        "CA",
        "CA-ON",
        "Ontario",
    )


def test_legacy_state_filter_matches_portable_subdivision_name() -> None:
    ontario = call_tool("search_agencies", {"state": "Ontario"}, _fetch)
    assert [a["id"] for a in ontario["agencies"]] == ["barrie-transit"]


def test_get_scorecard_trims_and_frames_as_fixes() -> None:
    card = call_tool("get_scorecard", {"agency_id": "unitrans"}, _fetch)
    assert card["overall"]["grade"] == "B"
    # Unmeasured categories keep their neutral summary, never a zero.
    assert card["categories"]["realtime"]["status"] == "not_yet_measured"
    f = card["findings"][0]
    assert f["fix"].startswith("Re-snap")
    assert f["fix_guide_url"].endswith("/fix/stop_too_far_from_shape/")
    assert "not an official compliance determination" in card["note"]


def test_search_derives_legacy_catalog_horizon_from_snapshot_and_days() -> None:
    import scorecard_pipeline.mcp_server as mcp

    catalog = {
        "agencies": [
            {
                "id": "legacy-global",
                "name": "Legacy Global Transit",
                "snapshot_date": "2026-07-13",
                "days_until_expiry": 26_834,
            }
        ]
    }
    mcp._catalog_cache.clear()
    result = call_tool(
        "search_agencies",
        {"query": "legacy-global"},
        lambda _url: catalog,
    )
    assert result["agencies"][0]["service_horizon_status"] == "unusually_distant"
    mcp._catalog_cache.clear()


def test_get_scorecard_normalizes_legacy_embedded_countdown() -> None:
    artifact: dict[str, Any] = copy.deepcopy(_ARTIFACT)
    artifact["snapshot_date"] = "2026-07-13"
    artifact["feed"] = {"static_url": "https://example.org/gtfs.zip", "reachable": True}
    artifact["categories"]["freshness"] = {
        "status": "measured",
        "score": 100.0,
        "summary": "Service data covers the next 26834 days.",
        "findings": [],
        "details": {"days_until_expiry": 26_834},
    }
    artifact["ntd_readiness"] = {
        "status": "ready",
        "summary": "Ready.",
        "pillars": [
            {
                "key": "current",
                "status": "ready",
                "detail": "Service data covers the next 26834 days.",
            }
        ],
    }

    card = call_tool("get_scorecard", {"agency_id": "unitrans"}, lambda _url: artifact)
    freshness = card["categories"]["freshness"]
    assert freshness["service_horizon_status"] == "unusually_distant"
    assert "unusually distant" in freshness["summary"]
    assert "26834" not in json.dumps(card)


def test_tools_call_wraps_payload_and_errors_in_content() -> None:
    ok = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "national_stats", "arguments": {}},
        },
        _fetch,
    )
    assert ok is not None
    assert ok["result"]["content"][0]["type"] == "text"
    assert "pct_ready" in ok["result"]["content"][0]["text"]
    missing = handle_request(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "get_scorecard", "arguments": {}},
        },
        _fetch,
    )
    assert missing is not None
    assert missing["result"]["isError"] is True


def test_coverage_stats_is_portable_and_national_stats_marks_us_scope() -> None:
    coverage = call_tool("coverage_stats", {}, _fetch)
    assert {row["country_code"] for row in coverage["by_location"]["countries"]} == {
        "US",
        "CA",
    }
    assert "not every transit operator" in coverage["note"]
    legacy = call_tool("national_stats", {}, _fetch)
    assert legacy["scope"]["stats"] == "covered_corpus"
    assert legacy["scope"]["ntd_readiness"]["country"] == "US"
    assert "United States-only" in legacy["scope"]["note"]


def test_search_limit_zero_returns_none_and_catalog_is_cached() -> None:
    import scorecard_pipeline.mcp_server as mcp

    calls = {"n": 0}

    def counting_fetch(url: str) -> Any:
        calls["n"] += 1
        return _fetch(url)

    mcp._catalog_cache.clear()
    none = call_tool("search_agencies", {"limit": 0}, counting_fetch)
    assert none["agencies"] == [] and none["total"] == 2
    # A second search within the TTL reuses the cached catalog: one fetch total.
    call_tool("search_agencies", {"query": "davis"}, counting_fetch)
    assert calls["n"] == 1
    mcp._catalog_cache.clear()


def test_search_rows_carry_the_documented_readiness_fields() -> None:
    # The MCP slim row must not lag the documented catalog contract (api.md):
    # readiness and percentile fields ride along so an agent never has to
    # refetch the raw catalog for them.
    row = call_tool("search_agencies", {"query": "davis"}, _fetch)["agencies"][0]
    for field in (
        "country",
        "subdivision_code",
        "subdivision_name",
        "expiry_status",
        "service_horizon_status",
        "national_percentile",
        "peer_percentile",
        "ntd_ready",
        "google_gate",
    ):
        assert field in row, field
