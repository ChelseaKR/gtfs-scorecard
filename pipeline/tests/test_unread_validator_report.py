"""A validator report nobody could read must not be scored as a clean feed.

The upward twin of the fabricated F. On 2026-09-01 two categories that had
measured nothing were caught publishing a 0.0 for it, and the scorer learned to
refuse a feed it could not read (tests/test_unmeasurable_feed.py). Correctness
kept the same defect pointing the other way, and kept it longer because a
flattering number invites no complaint.

``ValidationReport`` carries one field that answers "what did the validator
find" -- a list of notice groups -- and an empty list meant both "it found
nothing wrong" and "there was no report to read". ``correctness`` starts at
100.0 and deducts per notice, so the second case published:

    Correctness  100.0 / 100
    "The validator found no problems in this feed. That is rare and worth
     celebrating."

about a feed whose report had never been read. Four payloads reached that
sentence: an empty dict, a dict of an entirely different shape, a truncated
report that kept its ``summary`` and lost its ``notices``, and (via TypeError
rather than a score) a report whose ``notices`` were null.

Correctness was the only scored category with no way to say "not measured".
Freshness and rider experience each return None and are dropped by
``score_feed_content``; realtime is simply never appended when an agency
publishes no realtime feed, and ``Scorecard.to_json`` renders all three
absences as ``status: not_yet_measured`` with no number. Correctness returned a
``CategoryResult`` unconditionally, from the only two functions in the package
that build a ``ValidationReport``.

So the refusal goes at those two boundaries, and the three callers that can get
the same report from somewhere else recover rather than refuse:

* ``vcache`` treats an unreadable cache entry as a miss, so the validator runs
  again. A cache is an optimization; the right cost of a corrupt entry is one
  re-validation, never a fabricated 100.
* ``feedapi`` treats an unreadable hosted report the way it already treats every
  other mismatch -- return None, validate locally.
* The local report.json is our own validator's output. Nothing can re-derive it,
  so ``parse_report`` raises and no scorecard is written for that agency at all,
  by the same ValueError path a non-zip response body already travels. The
  stale record stays and the run reports a failure, which is what "we could not
  read it" looks like from the outside.

The narrowness tests matter as much as the refusal. A validator report with
``"notices": []`` is a real measurement of a genuinely clean feed, and it must
keep scoring 100.0. The rule is about the absence of the report, never about
the absence of notices inside one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import vcache
from scorecard_pipeline.feedapi import ApiDataset, ApiValidation, report_from_api
from scorecard_pipeline.metrics import correctness
from scorecard_pipeline.score import build_scorecard
from scorecard_pipeline.validate import (
    UnreadableValidatorReportError,
    ValidationReport,
    parse_report,
    parse_report_data,
)

#: A real report about a genuinely clean feed. Empty notices, deliberately.
A_REAL_CLEAN_REPORT: dict[str, Any] = {
    "summary": {"validatorVersion": "8.0.1", "gtfsInput": "gtfs.zip"},
    "notices": [],
}

#: A real report about a feed with one real problem.
A_REAL_REPORT_WITH_A_FINDING: dict[str, Any] = {
    "summary": {"validatorVersion": "8.0.1"},
    "notices": [
        {"code": "unused_stop", "severity": "WARNING", "totalNotices": 3, "sampleNotices": []}
    ],
}

#: Every payload observed to reach "The validator found no problems in this
#: feed", named by what it actually was.
NOT_A_REPORT: dict[str, dict[str, Any]] = {
    "an empty JSON object": {},
    "a dict of some other shape": {"unexpected": "shape"},
    "a report truncated after its summary": {"summary": {"validatorVersion": "8.0.1"}},
    "a report whose notices are null": {"summary": {"validatorVersion": "8.0.1"}, "notices": None},
    "a report whose notices are an object": {"summary": {}, "notices": {"code": "unused_stop"}},
    "a report whose notices are a bare string": {"summary": {}, "notices": "none"},
}


# --- the refusal at the parse boundary ---------------------------------------


@pytest.mark.parametrize("payload", NOT_A_REPORT.values(), ids=list(NOT_A_REPORT))
def test_a_payload_that_is_not_a_report_is_refused_not_scored_as_clean(
    payload: dict[str, Any],
) -> None:
    with pytest.raises(UnreadableValidatorReportError, match="not a gtfs-validator report"):
        parse_report_data(payload)


def test_a_notice_that_is_not_an_object_is_refused_rather_than_dropped() -> None:
    """Dropping it would silently lower the notice count, which raises the score.

    The same fabrication as an empty list, arrived at one notice at a time.
    """
    payload = {"summary": {}, "notices": [{"code": "unused_stop", "severity": "WARNING"}, "oops"]}
    with pytest.raises(UnreadableValidatorReportError):
        parse_report_data(payload)


def test_the_refusal_reaches_a_report_file_on_disk(tmp_path: Path) -> None:
    """``parse_report`` is the daily run's path; the refusal has to travel it."""
    path = tmp_path / "report.json"
    path.write_text(json.dumps({}))
    with pytest.raises(UnreadableValidatorReportError):
        parse_report(path)


def test_the_refusal_is_a_valueerror_like_every_other_refusal_here() -> None:
    """``scorecard try`` and the collect loop already handle ValueError.

    A non-zip response body raises ValueError from ``fetch_static`` and an
    archive with no schedule data raises ``UnreadableFeedError``, itself a
    ValueError. This one joins them rather than adding a fourth handler.
    """
    assert issubclass(UnreadableValidatorReportError, ValueError)


# --- narrowness: a clean feed is still a measurement --------------------------


def test_a_real_report_with_no_notices_still_scores_a_clean_100() -> None:
    """The opposite mistake would hide every genuinely clean feed.

    Passes before the fix as well as after; it is here to pin the boundary, not
    to demonstrate it moved.
    """
    category = correctness(parse_report_data(A_REAL_CLEAN_REPORT))
    assert category.score == 100.0
    assert "found no problems" in category.summary
    assert category.to_json()["status"] == "measured"


def test_a_real_report_with_a_finding_still_scores_it() -> None:
    """Also passes either way. The refusal must not touch reports that parsed."""
    category = correctness(parse_report_data(A_REAL_REPORT_WITH_A_FINDING))
    assert category.score < 100.0
    assert [f.code for f in category.findings] == ["unused_stop"]


# --- vcache: an unreadable entry is a miss, not a clean feed ------------------


def _write_cache_entry(tmp_path: Path, agency_id: str, report: Any) -> None:
    path = vcache.cache_path(agency_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "sha256": "abc123",
                "validator_version": "8.0.1",
                "country_code": "US",
                "report": report,
            }
        )
    )


@pytest.fixture
def private_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(vcache, "cache_dir", lambda: tmp_path)
    monkeypatch.delenv("VALIDATOR_CACHE_BUCKET", raising=False)
    monkeypatch.delenv("ARTIFACTS_BUCKET", raising=False)
    return tmp_path


def test_an_unreadable_cache_entry_is_a_miss_so_the_validator_runs_again(
    private_cache: Path,
) -> None:
    """The cache is an optimization. A corrupt entry costs one re-validation."""
    _write_cache_entry(private_cache, "some-agency", {})
    assert vcache.load_cached("some-agency", "abc123", "8.0.1") is None


def test_a_cache_entry_whose_notices_are_null_is_also_a_miss(private_cache: Path) -> None:
    _write_cache_entry(private_cache, "some-agency", {"validator_version": "8.0.1"})
    assert vcache.load_cached("some-agency", "abc123", "8.0.1") is None


def test_a_readable_cache_entry_is_still_a_hit(private_cache: Path) -> None:
    """Narrowness. A cached clean report is a real measurement and stays one."""
    _write_cache_entry(private_cache, "some-agency", {"validator_version": "8.0.1", "notices": []})
    hit = vcache.load_cached("some-agency", "abc123", "8.0.1")
    assert isinstance(hit, ValidationReport)
    assert correctness(hit).score == 100.0


def test_a_round_trip_through_the_cache_survives(private_cache: Path) -> None:
    """Narrowness, again: the refusal must not reject what store_cached writes."""
    report = parse_report_data(A_REAL_REPORT_WITH_A_FINDING)
    vcache.store_cached("some-agency", "abc123", "8.0.1", report)
    assert vcache.load_cached("some-agency", "abc123", "8.0.1") == report


# --- feedapi: an unreadable hosted report falls back to a local run -----------


def _dataset(sha256: str = "abc123", version: str = "8.0.1") -> ApiDataset:
    return ApiDataset(
        dataset_id="ds-1",
        feed_id="mdb-1",
        hosted_url="https://example.org/gtfs.zip",
        downloaded_at="2026-09-01T00:00:00Z",
        sha256=sha256,
        validation=ApiValidation(
            validator_version=version,
            total_error=0,
            total_warning=1,
            total_info=0,
            url_json="https://example.org/report.json",
        ),
    )


def test_a_hosted_report_that_is_not_a_report_falls_back_to_local_validation() -> None:
    """MobilityData's report arrives over the network; it can be anything.

    An error page or a schema change would otherwise have been reused as a
    clean bill of health for a feed no validator run had looked at.
    """
    assert (
        report_from_api(
            _dataset(),
            "abc123",
            "8.0.1",
            fetch_report=lambda _url: {"error": "not found"},
        )
        is None
    )


def test_a_hosted_report_that_is_a_report_is_still_reused() -> None:
    """Narrowness. The cost lever this guards has to keep working."""
    report = report_from_api(
        _dataset(),
        "abc123",
        "8.0.1",
        fetch_report=lambda _url: A_REAL_REPORT_WITH_A_FINDING,
    )
    assert report is not None
    assert [g.code for g in report.notices] == ["unused_stop"]


# --- what a not-measured correctness looks like, if one is ever built --------


def test_an_absent_correctness_category_renders_with_no_number() -> None:
    """The convention the other three categories already use, pinned.

    Passes before the fix as well as after. It is here so the shape of a
    correctness that was never measured is written down: the category is left
    out of ``build_scorecard``, and ``Scorecard.to_json`` gives it
    ``not_yet_measured`` and no score, exactly as it does for an agency with no
    realtime feed. Nothing in the artifact ever carries a correctness number
    that no report produced.
    """
    from scorecard_pipeline.metrics import CategoryResult

    card = build_scorecard(
        [CategoryResult(name="completeness", score=62.0, summary="Measured.")]
    ).to_json()
    assert card["categories"]["correctness"] == {
        "name": "correctness",
        "status": "not_yet_measured",
        "weight": 0.35,
        "summary": "Not scored yet. Nothing here counts against the grade.",
    }
    assert "score" not in card["categories"]["correctness"]
