"""Tests for the organization/feed identity ledger."""

from __future__ import annotations

from scorecard_pipeline.config import Agency
from scorecard_pipeline.identity import build_identity_ledger, normalized_feed_url


def _agency(agency_id: str, url: str, **kwargs: object) -> Agency:
    return Agency(
        id=agency_id,
        name=agency_id,
        static_gtfs_url=url,
        **kwargs,  # type: ignore[arg-type]
    )


def test_normalized_feed_url_ignores_scheme_and_default_port() -> None:
    assert normalized_feed_url("http://Example.org:80/feed.zip") == "example.org/feed.zip"
    assert normalized_feed_url("https://example.org/feed.zip/") == "example.org/feed.zip"


def test_identity_ledger_keeps_denominators_separate() -> None:
    agencies = [
        _agency(
            "bus",
            "https://example.org/feed.zip",
            mdb_id="mdb-1",
            organization_id="demo-transit",
            is_official=True,
        ),
        _agency(
            "rail",
            "https://example.org/rail.zip",
            mdb_id="mdb-2",
            organization_id="demo-transit",
        ),
        _agency(
            "old",
            "http://example.org/feed.zip",
            mdb_id="mdb-1",
            alias_of="bus",
            feed_status="deprecated",
        ),
    ]

    ledger = build_identity_ledger(agencies)
    assert ledger["configured_feed_records"] == 3
    assert ledger["active_feed_records"] == 2
    assert ledger["canonical_feed_records"] == 2
    assert ledger["active_canonical_feed_records"] == 2
    assert ledger["distinct_organizations"] == 1
    assert ledger["distinct_organization_keys"] == 1
    assert ledger["provisional_organization_keys"] == 0
    assert ledger["alias_records"] == 1
    assert ledger["official_sources"] == 1
    assert ledger["unresolved_duplicate_mdb_ids"] == []
    assert ledger["unresolved_duplicate_feed_urls"] == []


def test_identity_ledger_reports_unresolved_canonical_duplicates() -> None:
    ledger = build_identity_ledger(
        [
            _agency("one", "http://example.org/feed.zip", mdb_id="same"),
            _agency("two", "https://example.org/feed.zip", mdb_id="same"),
        ]
    )

    assert ledger["unresolved_duplicate_mdb_ids"] == [{"key": "same", "ids": ["one", "two"]}]
    assert ledger["unresolved_duplicate_feed_urls"] == [
        {"key": "example.org/feed.zip", "ids": ["one", "two"]}
    ]
    assert ledger["provisional_organization_keys"] == 2
