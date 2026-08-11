"""Tests for producing-tool detection (RESEARCH-ROADMAP R5).

The distinction under test throughout is hosting versus producing: the host
serving a zip is not the tool that wrote it, so a host match alone only counts
where the URL is a tool's own generated-export endpoint.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from scorecard_pipeline import tool_profiles
from scorecard_pipeline.tool_profiles import HOST_EVIDENCE, KINDS, detect_tool

_REAL_RECORDED = tool_profiles._recorded_declaration


@pytest.fixture(autouse=True)
def _no_committed_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    """Detection under test reads only the declarations a test supplies.

    Without this the committed `data/feed-publishers.json` would answer for the
    example URLs, and a snapshot refresh would rewrite these tests' meaning.
    """
    monkeypatch.setattr(tool_profiles, "_recorded_declaration", lambda url: None)


def _snapshot(monkeypatch: pytest.MonkeyPatch, entries: dict[str, tuple[str, str]]) -> None:
    monkeypatch.setattr(tool_profiles, "_recorded_declaration", entries.get)


# --- the host is the producer -------------------------------------------------


def test_passio_endpoint_is_producer_evidence() -> None:
    # passio3.com/<tenant>/passioTransit/gtfs/ is Passio's own generated export.
    tool = detect_tool("https://passio3.com/clovis/passioTransit/gtfs/google_transit.zip")
    assert tool is not None
    assert tool.key == "passio"
    assert tool.kind == "hosted"


def test_remix_export_endpoint_is_producer_evidence() -> None:
    tool = detect_tool("https://gtfs.remix.com/citilink_fortwayne_in_us.zip")
    assert tool is not None and tool.key == "remix"


def test_declaration_confirming_the_host_attributes_the_host() -> None:
    tool = detect_tool(
        "https://data.trilliumtransit.com/gtfs/unitrans-ca-us/unitrans.zip",
        publisher_name="Trillium Solutions, Inc.",
        publisher_url="http://www.trilliumtransit.com",
    )
    assert tool is not None
    assert tool.key == "trillium"
    assert tool.kind == "hosted"
    assert "Trillium" in tool.fix_path


def test_declaration_attributes_a_producer_on_an_unremarkable_host() -> None:
    # A feed the agency re-hosts on its own bucket still says who built it.
    tool = detect_tool(
        "https://s3.amazonaws.com/agency-bucket/gtfs.zip",
        publisher_name="Trillium Solutions",
        publisher_url="https://trilliumtransit.com",
    )
    assert tool is not None and tool.key == "trillium"


# --- the host merely hosts ----------------------------------------------------


def test_hosting_service_alone_does_not_attribute_the_host() -> None:
    # data.trilliumtransit.com carries feeds Trillium did not build, so serving
    # a feed there is not evidence that Trillium produced it.
    assert detect_tool("https://data.trilliumtransit.com/gtfs/some-ca-us/some-ca-us.zip") is None
    assert detect_tool("http://oregon-gtfs.trilliumtransit.com/some-or-us.zip") is None


def test_upload_path_alone_does_not_attribute_the_tool() -> None:
    # Every rapid.nationalrtap.org feed URL is under a file-upload path, which
    # carries whatever an agency uploaded, GTFS Builder's work or not.
    url = (
        "https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/5191/google_transit.zip"
    )
    assert detect_tool(url) is None


def test_declaration_naming_another_producer_beats_the_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A Trillium-served feed whose own feed_info names GMV Syncromatics must not
    # be credited to Trillium. No fix path is documented for GMV Syncromatics,
    # so the honest answer is no named vendor at all.
    url = "https://data.trilliumtransit.com/gtfs/wilsonville-or-us/wilsonville-or-us.zip"
    _snapshot(monkeypatch, {url: ("GMV Syncromatics", "https://gmvsyncromatics.com")})
    assert detect_tool(url) is None


def test_declaration_moves_attribution_between_documented_tools() -> None:
    # Same rule in the other direction: the feed's word decides, not the host.
    tool = detect_tool(
        "https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/1/gtfs.zip",
        publisher_name="Trillium Solutions, Inc.",
        publisher_url="https://trilliumtransit.com",
    )
    assert tool is not None and tool.key == "trillium"


# --- the honest unknown -------------------------------------------------------


def test_recognized_producer_without_a_fix_path_returns_unknown() -> None:
    assert (
        detect_tool(
            "https://rapid.nationalrtap.org/GTFSFileManagement/UserUploadFiles/5191/gtfs.zip",
            publisher_name="Connexionz Ltd",
            publisher_url="https://www.connexionz.com",
        )
        is None
    )


def test_agency_naming_itself_is_not_evidence_about_the_tool() -> None:
    # Most tools write the agency into feed_publisher_name, so an agency name
    # neither confirms nor rules out the host. A hosting service still fails.
    assert (
        detect_tool(
            "https://data.trilliumtransit.com/gtfs/rfta-co-us/rfta-co-us.zip",
            publisher_name="RFTA",
            publisher_url="http://www.rfta.com/",
        )
        is None
    )
    # ... while a tool's own export endpoint still resolves.
    tool = detect_tool(
        "https://gtfs.remix.com/act_los_alamos_nm_us.zip",
        publisher_name="Atomic City Transit",
        publisher_url="http://www.atomiccitytransit.com",
    )
    assert tool is not None and tool.key == "remix"


def test_self_contradicting_declaration_names_nobody() -> None:
    assert (
        detect_tool(
            "https://data.trilliumtransit.com/gtfs/x-ca-us/x-ca-us.zip",
            publisher_name="Passio Technologies",
            publisher_url="https://trilliumtransit.com",
        )
        is None
    )


def test_generic_hosting_stays_unmatched() -> None:
    # An S3 bucket or an agency's own site says nothing about the producing
    # tool; guessing would misdirect the one email a manager sends.
    for url in (
        "https://s3.amazonaws.com/bucket/gtfs.zip",
        "https://www.cityofdavis.org/files/gtfs.zip",
        "https://mjcaction.com/mjc_gtfs_public/demo/google_transit.zip",
    ):
        assert detect_tool(url) is None, url


def test_lookalike_host_is_not_a_suffix_match() -> None:
    # evil-github.com must not match github.com; only a dot boundary counts.
    assert detect_tool("https://nottransitfeeds.com/feed.zip") is None
    assert detect_tool("https://faketrilliumtransit.com/feed.zip") is None


def test_missing_or_blank_url_returns_none() -> None:
    assert detect_tool(None) is None
    assert detect_tool("") is None
    assert detect_tool("not a url") is None


# --- publishing routes --------------------------------------------------------


def test_repo_hosts_detected() -> None:
    for url in (
        "https://github.com/agency/gtfs/raw/main/gtfs.zip",
        "https://raw.githubusercontent.com/agency/gtfs/main/gtfs.zip",
        "https://gitlab.com/agency/gtfs/-/raw/main/gtfs.zip",
    ):
        tool = detect_tool(url)
        assert tool is not None and tool.key == "repo", url


def test_repo_route_survives_an_unprofiled_producer(monkeypatch: pytest.MonkeyPatch) -> None:
    # The repository profile names no organization, so a producer this project
    # has no fix path for does not contradict it and the route copy stands.
    url = "https://raw.githubusercontent.com/lab/gtfs/main/gtfs.zip"
    _snapshot(monkeypatch, {url: ("MTI UMD", "https://mti.umd.edu/")})
    tool = detect_tool(url)
    assert tool is not None and tool.key == "repo"


def test_repo_route_yields_to_a_documented_producer(monkeypatch: pytest.MonkeyPatch) -> None:
    # A feed mirrored into a repository but built by a tool with a documented
    # fix path is better addressed to that tool than to the repo maintainer.
    url = "https://raw.githubusercontent.com/region/gtfs/main/lynwood-ca-us.zip"
    _snapshot(monkeypatch, {url: ("Trillium Solutions, Inc.", "https://trilliumtransit.com")})
    tool = detect_tool(url)
    assert tool is not None and tool.key == "trillium"


def test_producer_endpoint_yields_to_a_contradicting_declaration() -> None:
    # Even a tool's own export endpoint gives way to the feed's own word.
    assert (
        detect_tool(
            "https://gtfs.remix.com/somefeed.zip",
            publisher_name="GMV Syncromatics",
            publisher_url="https://gmvsyncromatics.com",
        )
        is None
    )


def test_archive_host_detected() -> None:
    tool = detect_tool("https://transitfeeds.com/p/demo/1/latest/download")
    assert tool is not None
    assert tool.kind == "archive"
    assert "live URL" in tool.fix_path


def test_archive_url_outranks_a_producer_declaration() -> None:
    # "Publish from a live URL" is true of the URL whoever built the bytes, and
    # must not be replaced by a vendor conversation.
    tool = detect_tool(
        "https://transitfeeds.com/p/demo/1/latest/download",
        publisher_name="Trillium Solutions, Inc.",
        publisher_url="https://trilliumtransit.com",
    )
    assert tool is not None and tool.kind == "archive"


# --- the committed snapshot ---------------------------------------------------


def test_snapshot_supplies_the_declaration_when_none_is_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://data.trilliumtransit.com/gtfs/sagestage-ca-us/sagestage-ca-us.zip"
    _snapshot(monkeypatch, {url: ("Trillium Solutions, Inc.", "http://www.trilliumtransit.com")})
    tool = detect_tool(url)
    assert tool is not None and tool.key == "trillium"


def test_snapshot_is_keyed_on_the_url_it_was_read_from(monkeypatch: pytest.MonkeyPatch) -> None:
    # A feed that moved has no evidence at its new URL, so it falls back to what
    # the host alone proves rather than inheriting a stale declaration.
    recorded = "https://data.trilliumtransit.com/gtfs/old-ca-us/old-ca-us.zip"
    monkeypatch.setattr(
        tool_profiles,
        "_recorded_declaration",
        {recorded: ("Trillium Solutions, Inc.", "https://trilliumtransit.com")}.get,
    )
    assert detect_tool("https://data.trilliumtransit.com/gtfs/new-ca-us/new-ca-us.zip") is None


def test_snapshot_tolerates_a_scheme_change(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tool_profiles,
        "_publisher_snapshot",
        lambda: {
            "http://data.trilliumtransit.com/gtfs/a-ca-us/a-ca-us.zip": (
                "Trillium Solutions, Inc.",
                "https://trilliumtransit.com",
            )
        },
    )
    monkeypatch.setattr(tool_profiles, "_recorded_declaration", _REAL_RECORDED)
    tool = detect_tool("https://data.trilliumtransit.com/gtfs/a-ca-us/a-ca-us.zip")
    assert tool is not None and tool.key == "trillium"


def test_missing_snapshot_is_an_empty_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.setattr(tool_profiles, "repo_root", lambda: tmp_path)
    assert tool_profiles._publisher_snapshot() == {}


def test_snapshot_cache_follows_the_configured_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    # conftest points SCORECARD_ROOT at a throwaway tree for every test, so a
    # process-wide cache would let the first tree read answer for later ones.
    empty = tmp_path / "empty"
    populated = tmp_path / "populated"
    (populated / "data").mkdir(parents=True)
    (populated / "data" / "feed-publishers.json").write_text(
        json.dumps(
            {
                "feeds": {
                    "demo": {
                        "url": "https://example.org/gtfs.zip",
                        "publisher_name": "Trillium Solutions, Inc.",
                        "publisher_url": "https://trilliumtransit.com",
                    }
                }
            }
        )
    )
    monkeypatch.setattr(tool_profiles, "repo_root", lambda: empty)
    assert tool_profiles._publisher_snapshot() == {}
    monkeypatch.setattr(tool_profiles, "repo_root", lambda: populated)
    assert tool_profiles._publisher_snapshot() != {}


def test_committed_snapshot_parses_and_is_url_keyed(monkeypatch: pytest.MonkeyPatch) -> None:
    # conftest isolates SCORECARD_ROOT; this one assertion is about the file
    # this repository actually ships, so it reads the real tree.
    monkeypatch.delenv("SCORECARD_ROOT", raising=False)
    index = tool_profiles._publisher_snapshot()
    assert index, "the committed publisher snapshot should not be empty"
    assert all(key.startswith(("http://", "https://")) for key in index)


# --- vocabulary ---------------------------------------------------------------


def test_every_profile_kind_is_documented() -> None:
    # Each profile's kind must be one the render layer knows how to phrase.
    seen = set()
    for url, name in (
        ("https://data.trilliumtransit.com/x.zip", "Trillium Solutions, Inc."),
        ("https://rapid.nationalrtap.org/x", "National RTAP"),
        ("https://gtfs.remix.com/x.zip", ""),
        ("https://passio3.com/x/gtfs.zip", ""),
        ("https://github.com/x/x.zip", ""),
        ("https://transitfeeds.com/x", ""),
    ):
        tool = detect_tool(url, publisher_name=name or None)
        assert tool is not None and tool.kind in KINDS, url
        seen.add(tool.kind)
    assert seen == set(KINDS)


def test_every_host_rule_declares_known_evidence() -> None:
    for suffix, rule in tool_profiles._HOST_RULES.items():
        assert rule.evidence in HOST_EVIDENCE, suffix
        assert rule.profile.kind in KINDS, suffix
