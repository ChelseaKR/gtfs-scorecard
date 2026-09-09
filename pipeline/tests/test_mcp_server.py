"""Tests for the read-only MCP server (protocol handling and tool logic)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
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
    # readiness fields ride along so an agent does not have to refetch the raw
    # catalog. Individual percentile fields are deliberately not published.
    row = call_tool("search_agencies", {"query": "davis"}, _fetch)["agencies"][0]
    for field in (
        "country",
        "subdivision_code",
        "subdivision_name",
        "expiry_status",
        "service_horizon_status",
        "ntd_ready",
        "google_gate",
    ):
        assert field in row, field
    assert row["national_percentile"] is None
    assert row["peer_percentile"] is None


# --- history, fix recipes, rollups, packets, and coverage ----------------------


def _point(
    date: str,
    *,
    grade: str = "C",
    score: float = 72.0,
    validator: str = "8.0.1",
    rubric: str = "1.3",
    realtime: float | None = None,
) -> dict[str, Any]:
    categories: dict[str, Any] = {"correctness": 76.0, "freshness": 80.0, "completeness": 60.0}
    if realtime is not None:
        categories["realtime"] = realtime
    return {
        "date": date,
        "grade": grade,
        "score": score,
        "categories": categories,
        "days_until_expiry": 40,
        "rubric_version": rubric,
        "scoring_profile_id": "gtfs-scorecard-1.3",
        "scoring_profile_rubric_version": rubric,
        "validator_version": validator,
        "reader_archive_profile": "raw-v1",
    }


def _dated_artifact(findings: list[str]) -> dict[str, Any]:
    return {
        "categories": {
            "correctness": {
                "status": "measured",
                "score": 76.0,
                "findings": [
                    {"code": code, "count": 1, "severity": "WARNING", "what": f"{code} happened"}
                    for code in findings
                ],
            }
        }
    }


_INDEX: dict[str, Any] = {
    "agencies": {
        "unitrans": {
            "name": "Unitrans",
            "history": [
                _point("2026-06-01", grade="D", score=64.0, validator="7.0.0"),
                _point("2026-06-02", grade="C", score=72.0),
                _point("2026-06-03", grade="C", score=73.0),
            ],
        },
        "one-shot": {"name": "One Shot", "history": [_point("2026-06-01")]},
        "boundary-last": {
            "name": "Boundary Last",
            "history": [_point("2026-06-01"), _point("2026-06-02", rubric="1.4")],
        },
    }
}

_ROLLUP: dict[str, Any] = {
    "rollup": {"id": "california", "name": "California"},
    "agency_count": 2,
    "average_score": 70.0,
    "grade_distribution": {"A": 0, "B": 1, "C": 1, "D": 0, "F": 0},
    "expired": 0,
    "needs_attention": 1,
    "common_fixes": [
        {"code": "scorecard_wheelchair_boarding_unknown", "agencies": 2, "fix": "Set it."}
    ],
    "members": [
        {
            "id": "unitrans",
            "name": "Unitrans",
            "grade": "B",
            "score": 80.8,
            "expiry_status": "ok",
            "needs_attention": False,
            "top_fix": "Re-snap stops.",
        }
    ],
}

_BY_LOCATION: dict[str, Any] = {
    "countries": [
        {
            "country_code": "US",
            "country_name": "United States",
            "count": 2,
            "median_score": 74.0,
            "grade_distribution": {"A": 0, "B": 1, "C": 1, "D": 0, "F": 0},
            "comparison_eligible_count": 2,
            "subdivisions": [
                {
                    "subdivision_code": "US-CA",
                    "subdivision_name": "California",
                    "count": 2,
                    "median_score": 74.0,
                    "grade_distribution": {"A": 0, "B": 1, "C": 1, "D": 0, "F": 0},
                    "comparison_eligible_count": 2,
                }
            ],
        }
    ]
}

_DATED: dict[str, list[str]] = {
    "2026-06-01": ["expired_calendar"],
    "2026-06-02": ["expired_calendar", "unused_shape"],
    "2026-06-03": ["unused_shape"],
}


def _fetch2(url: str) -> Any:
    """The harness above plus the documents the new tools read."""
    if url.endswith("/data/artifacts/index.json"):
        return copy.deepcopy(_INDEX)
    if url.endswith("/data/artifacts/rollups/california.json"):
        return copy.deepcopy(_ROLLUP)
    if url.endswith("/api/v1/by-location.json"):
        return copy.deepcopy(_BY_LOCATION)
    for date, codes in _DATED.items():
        if url.endswith(f"/{date}.json"):
            return _dated_artifact(codes)
    return _fetch(url)


def test_every_declared_tool_is_dispatchable_and_vice_versa() -> None:
    """A tool listed but not dispatchable is a promise the server cannot keep."""
    from scorecard_pipeline.mcp_server import _HANDLERS

    assert {t["name"] for t in TOOLS} == set(_HANDLERS)
    assert {
        "get_history",
        "explain_finding",
        "get_rollup",
        "get_evidence_packet",
        "coverage_for",
    } <= set(_HANDLERS)
    assert all("inputSchema" in t and t["description"] for t in TOOLS)


def test_get_history_marks_the_contract_boundary() -> None:
    history = call_tool("get_history", {"agency_id": "unitrans"}, _fetch2)
    rows = history["history"]
    assert [r["date"] for r in rows] == ["2026-06-01", "2026-06-02", "2026-06-03"]
    assert rows[0]["comparable_with_previous"] is None
    # 7.0.0 -> 8.0.1 across the first pair: a different measurement.
    assert rows[1]["comparable_with_previous"] is False
    assert rows[2]["comparable_with_previous"] is True
    assert "not a change in the feed" in history["note"]


def test_get_history_reports_findings_only_across_a_comparable_pair() -> None:
    history = call_tool("get_history", {"agency_id": "unitrans"}, _fetch2)
    change = history["latest_change"]
    assert change["comparable"] is True
    assert change["from_date"] == "2026-06-02"
    assert [f["code"] for f in change["cleared"]] == ["expired_calendar"]
    assert change["appeared"] == []


def test_get_history_makes_no_change_claim_across_a_rubric_change() -> None:
    """The refusal, and it names why rather than returning an empty list."""
    history = call_tool("get_history", {"agency_id": "boundary-last"}, _fetch2)
    change = history["latest_change"]
    assert change["comparable"] is False
    assert "different measurements" in change["reason"]
    assert "appeared" not in change
    assert "cleared" not in change


def test_get_history_with_one_snapshot_says_so_rather_than_reporting_nothing() -> None:
    history = call_tool("get_history", {"agency_id": "one-shot"}, _fetch2)
    assert history["latest_change"]["comparable"] is False
    assert "only one dated snapshot" in history["latest_change"]["reason"]


def test_get_history_filters_by_since_and_bounds_the_window() -> None:
    since = call_tool("get_history", {"agency_id": "unitrans", "since": "2026-06-02"}, _fetch2)
    assert [r["date"] for r in since["history"]] == ["2026-06-02", "2026-06-03"]
    limited = call_tool("get_history", {"agency_id": "unitrans", "limit": 2}, _fetch2)
    assert limited["returned"] == 2
    assert limited["available"] == 3
    assert limited["truncated"] is True


def test_get_history_refuses_an_untracked_agency() -> None:
    import pytest

    with pytest.raises(ValueError, match="no tracked feed record"):
        call_tool("get_history", {"agency_id": "nope"}, _fetch2)


def test_explain_finding_returns_the_written_recipe_and_the_rule() -> None:
    out = call_tool("explain_finding", {"code": "expired_calendar"}, _fetch2)
    assert out["has_recipe"] is True
    assert out["recipe"]["fix"]
    assert out["rule"]["url"].endswith("#expired_calendar-rule")
    assert out["fix_guide_url"].endswith("/fix/expired_calendar/")


def test_explain_finding_invents_nothing_for_an_unknown_code() -> None:
    """`notices.translate` has a generated fallback. It must not be used here."""
    out = call_tool("explain_finding", {"code": "not_a_real_notice"}, _fetch2)
    assert out["has_recipe"] is False
    assert out["recipe"] is None
    assert "No fix recipe is written for this code" in out["note"]
    # The rule link is still the honest answer: rules.html anchors every notice.
    assert out["rule"]["url"].endswith("#not_a_real_notice-rule")
    assert out["fix_guide_url"] is None


def test_explain_finding_adds_the_tool_fix_path_and_refuses_an_unknown_tool() -> None:
    known = call_tool("explain_finding", {"code": "expired_calendar", "tool": "trillium"}, _fetch2)
    assert known["tool_guidance"]["name"] == "Trillium"
    assert known["known_tools"] is None
    unknown = call_tool(
        "explain_finding", {"code": "expired_calendar", "tool": "some_vendor"}, _fetch2
    )
    assert unknown["tool_guidance"] is None
    assert "trillium" in unknown["known_tools"]


def test_get_rollup_returns_shared_fixes_and_bounds_members() -> None:
    out = call_tool("get_rollup", {"rollup_id": "california"}, _fetch2)
    assert out["rollup"]["id"] == "california"
    assert out["shared_fixes"][0]["code"] == "scorecard_wheelchair_boarding_unknown"
    assert out["members_returned"] == 1
    assert out["members_truncated"] is False
    assert "not a ranking" in out["note"]


def test_get_evidence_packet_builds_the_deterministic_packet() -> None:
    out = call_tool("get_evidence_packet", {"agency_id": "unitrans"}, _fetch2)
    again = call_tool("get_evidence_packet", {"agency_id": "unitrans"}, _fetch2)
    assert out == again
    assert out["note"]


def test_coverage_for_reports_a_country_and_its_subdivision() -> None:
    country = call_tool("coverage_for", {"country": "us"}, _fetch2)
    assert country["covered"] is True
    assert country["count"] == 2
    assert country["subdivisions"][0]["subdivision_code"] == "US-CA"
    sub = call_tool("coverage_for", {"country": "US", "subdivision": "California"}, _fetch2)
    assert sub["covered"] is True
    assert sub["subdivision_code"] == "US-CA"


def test_an_uncovered_place_is_labelled_not_covered_rather_than_zero() -> None:
    """ "We track no feeds here" and "there are no feeds here" are different claims."""
    country = call_tool("coverage_for", {"country": "ZZ"}, _fetch2)
    assert country["covered"] is False
    assert "count" not in country
    assert "not about whether transit" in country["note"]
    sub = call_tool("coverage_for", {"country": "US", "subdivision": "Atlantis"}, _fetch2)
    assert sub["covered"] is False
    assert "count" not in sub


def test_every_new_tool_repeats_the_lens_framing() -> None:
    """An assistant paraphrases what it is given; framing not in the payload is lost."""
    payloads = [
        call_tool("get_history", {"agency_id": "unitrans"}, _fetch2),
        call_tool("explain_finding", {"code": "expired_calendar"}, _fetch2),
        call_tool("get_rollup", {"rollup_id": "california"}, _fetch2),
        call_tool("get_evidence_packet", {"agency_id": "unitrans"}, _fetch2),
        call_tool("coverage_for", {"country": "US"}, _fetch2),
        call_tool("coverage_for", {"country": "ZZ"}, _fetch2),
    ]
    assert all("not an official compliance determination" in p["note"] for p in payloads)


def test_the_new_tools_introduce_no_language_model() -> None:
    """The AI Evaluation standard row stays N/A only while this holds."""
    source = (
        Path(__file__).resolve().parents[1] / "src/scorecard_pipeline/mcp_server.py"
    ).read_text()
    for forbidden in ("anthropic", "openai", "langchain", "llm", "boto3", "bedrock"):
        assert forbidden not in source.lower()
