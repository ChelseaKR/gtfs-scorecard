"""Tests for registry hygiene checks (pure, no file I/O)."""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.config import Agency
from scorecard_pipeline.lint import is_feed_descriptor, lint_registry


def test_is_feed_descriptor_matches_known_catalog_descriptors() -> None:
    # These are feed descriptors the catalog sometimes puts in the name column.
    assert is_feed_descriptor("Flex")
    assert is_feed_descriptor("  flex v2 included ")  # whitespace and case ignored
    assert is_feed_descriptor("Do not use - deprecated")
    assert is_feed_descriptor("Bus")
    # Real agency names are not descriptors.
    assert not is_feed_descriptor("Yolobus")
    assert not is_feed_descriptor("Unitrans")
    assert not is_feed_descriptor("Flexible Bus Company")


def _agency(**kw: object) -> Agency:
    base: dict[str, Any] = {
        "id": "demo",
        "name": "Demo Transit",
        "static_gtfs_url": "https://example.org/gtfs.zip",
        "mdb_id": "mdb-1",
    }
    base.update(kw)
    return Agency(**base)


def test_clean_registry_has_no_issues() -> None:
    assert lint_registry([_agency()]) == []


def test_flags_feed_descriptor_name() -> None:
    issues = lint_registry([_agency(id="flexy", name="Flex")])
    assert len(issues) == 1
    assert issues[0].kind == "feed_descriptor_name"
    assert issues[0].agency_id == "flexy"
    assert "Flex" in issues[0].detail


def test_flags_non_https_url_and_missing_mdb_id() -> None:
    issues = lint_registry(
        [_agency(id="insecure", static_gtfs_url="http://example.org/gtfs.zip", mdb_id="")]
    )
    kinds = {i.kind for i in issues}
    assert kinds == {"non_https_url", "missing_mdb_id"}


def test_feed_descriptor_issue_sorts_before_others() -> None:
    # A wrong name is the worst issue, so it leads regardless of agency id.
    issues = lint_registry(
        [
            _agency(id="zzz", static_gtfs_url="http://x/gtfs.zip"),
            _agency(id="aaa", name="Bus"),
        ]
    )
    assert issues[0].kind == "feed_descriptor_name"
    assert issues[0].agency_id == "aaa"


def test_duplicate_identity_requires_an_explicit_alias() -> None:
    duplicate = _agency(id="duplicate")
    issues = lint_registry([_agency(id="canonical"), duplicate])
    kinds = {issue.kind for issue in issues}
    assert {"duplicate_mdb_id", "duplicate_feed_url"} <= kinds

    aliased = _agency(id="duplicate", alias_of="canonical", feed_status="deprecated")
    kinds = {issue.kind for issue in lint_registry([_agency(id="canonical"), aliased])}
    assert "duplicate_mdb_id" not in kinds
    assert "duplicate_feed_url" not in kinds
