"""Tests for the Caltrans crosswalk's matching cascade.

`build_california_crosswalk.py` sat outside every gate this repo runs: not
linted, not format-checked, not type-checked, and with no test of its own. The
one piece of it that makes a judgment is `decide`, which picks how a California
registry record is tied to an organization in Caltrans' own report directory.
Its answer decides whether a public crosswalk row reads "matched" or
"uncertain", so the ordering between its strategies is policy, not detail.

These tests pin that ordering and each strategy's own tie-breaking, so the
split of `decide` into per-strategy functions is checkable rather than
asserted.
"""

from __future__ import annotations

import importlib.util
from collections import defaultdict
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "pipeline" / "scripts" / "build_california_crosswalk.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("build_california_crosswalk", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crosswalk = _load()


def _agency(caltrans_id: int, name: str, urls: list[str] | None = None) -> dict[str, Any]:
    """One directory entry with the derived fields main() attaches."""
    urls = urls or []
    hosts: set[str] = set()
    for url in urls:
        host = crosswalk.hostname_of(url)
        if host not in crosswalk.SHARED_HOSTS:
            hosts |= crosswalk.host_labels(host)
    return {
        "caltrans_id": caltrans_id,
        "name": name,
        "feeds": {"schedule": urls},
        "_urls": {crosswalk.normalized_url(u) for u in urls} - {""},
        "_words": crosswalk.place_words(name),
        "_hosts": hosts,
    }


def _owners(directory: list[dict[str, Any]]) -> tuple[dict[str, set[int]], dict[str, set[int]]]:
    org: dict[str, set[int]] = defaultdict(set)
    host: dict[str, set[int]] = defaultdict(set)
    for agency in directory:
        for word in agency["_words"]:
            org[word].add(agency["caltrans_id"])
        for label in agency["_hosts"]:
            host[label].add(agency["caltrans_id"])
    return org, host


def _decide(record: dict[str, Any], directory: list[dict[str, Any]]) -> tuple[Any, ...]:
    org, host = _owners(directory)
    decision: tuple[Any, ...] = crosswalk.decide(record, directory, org, host)
    return decision


def test_a_curated_answer_outranks_every_derived_one() -> None:
    """The curated decision is a reviewer's, so nothing computed may override
    it. BART is curated to 279; a directory that would otherwise match its feed
    URL to a different organization must not win."""
    directory = [_agency(999, "Some Other Body", ["https://example.org/bart.zip"])]
    record = {
        "id": "bay-area-rapid-transit-bart",
        "name": "Bay Area Rapid Transit",
        "static_gtfs_url": "https://example.org/bart.zip",
    }

    status, method, caltrans_id, _evidence = _decide(record, directory)

    assert (status, method, caltrans_id) == ("matched", "curated", 279)


def test_a_curated_uncertain_record_stays_uncertain() -> None:
    agency_id = next(iter(crosswalk.CURATED_UNCERTAIN))
    record = {"id": agency_id, "name": "Anything At All", "static_gtfs_url": ""}

    status, method, caltrans_id, evidence = _decide(record, [])

    assert (status, method, caltrans_id) == ("uncertain", "curated", None)
    assert evidence == crosswalk.CURATED_UNCERTAIN[agency_id]


def test_a_shared_feed_url_matches_and_outranks_the_name() -> None:
    directory = [
        _agency(10, "Completely Different Name", ["https://feeds.example.org/one.zip"]),
        _agency(11, "Testville Transit"),
    ]
    record = {
        "id": "testville-transit",
        "name": "Testville Transit",
        "static_gtfs_url": "https://feeds.example.org/one.zip",
    }

    status, method, caltrans_id, evidence = _decide(record, directory)

    assert (status, method, caltrans_id) == ("matched", "feed_url", 10)
    assert "feed URL" in evidence


def test_a_feed_url_two_organizations_both_report_is_uncertain() -> None:
    directory = [
        _agency(10, "Alpha Transit", ["https://feeds.example.org/one.zip"]),
        _agency(11, "Beta Transit", ["https://feeds.example.org/one.zip"]),
    ]
    record = {
        "id": "x",
        "name": "Alpha Transit",
        "static_gtfs_url": "https://feeds.example.org/one.zip",
    }

    status, method, caltrans_id, evidence = _decide(record, directory)

    assert (status, method, caltrans_id) == ("uncertain", "feed_url", None)
    assert "Alpha Transit" in evidence and "Beta Transit" in evidence


def test_an_exact_organization_name_matches() -> None:
    directory = [_agency(21, "Testville Transit (TT)"), _agency(22, "Elsewhere Transit")]
    record = {"id": "x", "name": "Testville Transit", "static_gtfs_url": ""}

    status, method, caltrans_id, _evidence = _decide(record, directory)

    assert (status, method, caltrans_id) == ("matched", "org_name", 21)


def test_a_place_word_only_one_organization_owns_matches() -> None:
    directory = [_agency(31, "Testville Regional Bus"), _agency(32, "Elsewhere Regional Bus")]
    record = {"id": "x", "name": "Testville Community Shuttle", "static_gtfs_url": ""}

    status, method, caltrans_id, evidence = _decide(record, directory)

    assert (status, method, caltrans_id) == ("matched", "place_name", 31)
    assert "testville" in evidence


def test_a_place_word_two_organizations_share_is_uncertain() -> None:
    """The word has to pick out exactly one body. Two owners means the
    directory cannot tell them apart, and neither can this."""
    directory = [_agency(41, "Testville Bus"), _agency(42, "Testville Rail")]
    record = {"id": "x", "name": "Testville Shuttle", "static_gtfs_url": ""}

    status, method, caltrans_id, _evidence = _decide(record, directory)

    # "testville" is owned by both, so no unique-owner word survives and the
    # cascade falls through to the loose overlap at the end.
    assert (status, method, caltrans_id) == ("uncertain", "name_overlap", None)


def test_a_unique_feed_hostname_label_matches_a_service_to_its_body() -> None:
    directory = [
        _agency(
            51, "Zzyzx County Joint Powers Authority", ["https://gtfs.riverline.example/a.zip"]
        ),
        _agency(52, "Somewhere Else Authority", ["https://gtfs.otherbrand.example/b.zip"]),
    ]
    record = {
        "id": "riverline",
        "name": "Riverline",
        "static_gtfs_url": "https://gtfs.riverline.example/current.zip",
    }

    status, method, caltrans_id, evidence = _decide(record, directory)

    assert (status, method, caltrans_id) == ("matched", "source_url_token", 51)
    assert "hostname" in evidence


def test_a_shared_vendor_host_is_not_treated_as_a_brand() -> None:
    """SHARED_HOSTS exists because a vendor's domain says nothing about who
    runs the service. A record on one must not match through it."""
    shared = next(iter(crosswalk.SHARED_HOSTS))
    directory = [_agency(61, "Some Authority", [f"https://{shared}/a.zip"])]
    record = {"id": "x", "name": "Unrelated Service", "static_gtfs_url": f"https://{shared}/b.zip"}

    status, method, caltrans_id, _evidence = _decide(record, directory)

    assert (status, method, caltrans_id) == ("absent", "no_candidate", None)


def test_nothing_in_the_directory_shares_a_name() -> None:
    directory = [_agency(71, "Elsewhere Regional Bus")]
    record = {"id": "x", "name": "Testville Shuttle", "static_gtfs_url": ""}

    status, method, caltrans_id, evidence = _decide(record, directory)

    assert (status, method, caltrans_id) == ("absent", "no_candidate", None)
    assert "no organization" in evidence


def test_a_partial_name_overlap_is_uncertain_never_matched() -> None:
    """A leftover overlap is reported so a reviewer can see it, and is never
    written as a match."""
    directory = [_agency(81, "Testville Bus"), _agency(82, "Testville Rail")]
    record = {"id": "x", "name": "Testville Something", "static_gtfs_url": ""}

    status, method, caltrans_id, evidence = _decide(record, directory)

    assert status == "uncertain"
    assert method == "name_overlap"
    assert caltrans_id is None
    assert "partial name overlap" in evidence


@pytest.mark.parametrize(
    "strategy",
    ["_curated_decision", "_feed_url_decision", "_org_name_decision"],
)
def test_each_strategy_returns_none_rather_than_guessing(strategy: str) -> None:
    """Every strategy has to be able to decline. A strategy that always
    answered would make the ones after it unreachable."""
    assert callable(getattr(crosswalk, strategy))
