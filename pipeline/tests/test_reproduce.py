"""Tests for `scorecard reproduce` (FIX-02): re-deriving a published grade from
the archived raw bytes and diffing it against what was published.

The validator/metrics layer is mocked (it is exercised elsewhere); this tests
the artifact-loading, archive-miss handling, and diff logic in isolation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import scorecard_pipeline.archive as archive
import scorecard_pipeline.reproduce as reproduce
from scorecard_pipeline.config import Agency
from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.validate import NoticeGroup, ValidationReport

AGENCY = Agency(id="demo", name="Demo Transit", static_gtfs_url="https://example.org/gtfs.zip")
DATE = "2026-06-11"
SHA = "d" * 64

PUBLISHED_ARTIFACT = {
    "feed": {"sha256": SHA},
    "validator_version": "8.0.1",
    # (95*0.35 + 100*0.20 + 80*0.25) / 0.80 = 91.5625 -> rounds to 91.6, matching
    # the re-derived score build_scorecard computes from the mocked categories
    # below (renormalized over the three measured weights: realtime is not
    # published, so its 0.20 weight drops out of the denominator).
    "overall": {"score": 91.6, "grade": "A"},
    "categories": {
        "correctness": {"status": "measured", "score": 95.0},
        "freshness": {"status": "measured", "score": 100.0},
        "completeness": {"status": "measured", "score": 80.0},
        "realtime": {"status": "not_yet_measured"},
    },
}


def _write_artifact(tmp_path: Path, payload: dict) -> None:  # type: ignore[type-arg]
    agency_dir = tmp_path / "data" / "artifacts" / AGENCY.id
    agency_dir.mkdir(parents=True)
    (agency_dir / f"{DATE}.json").write_text(json.dumps(payload))


def _wire_common(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")
    monkeypatch.setattr(archive, "fetch", lambda sha: b"PK\x03\x04fake")
    monkeypatch.setattr(reproduce, "run_validator", lambda *a, **k: Path("/tmp/fake-report.json"))
    monkeypatch.setattr(
        reproduce,
        "parse_report",
        lambda path: ValidationReport(
            validator_version="8.0.1", notices=[NoticeGroup("x", "WARNING", 1)]
        ),
    )
    monkeypatch.setattr(reproduce, "read_feed_dates", lambda path: [])


def _wire_categories(  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch, *, correctness=95.0, freshness=100.0, completeness=80.0
) -> None:
    monkeypatch.setattr(
        reproduce, "correctness", lambda report: CategoryResult("correctness", correctness, "s")
    )
    monkeypatch.setattr(
        reproduce,
        "freshness",
        lambda dates, today, service_type: CategoryResult("freshness", freshness, "s"),
    )
    monkeypatch.setattr(
        reproduce,
        "completeness",
        lambda path, fare_free=False: CategoryResult("completeness", completeness, "s"),
    )


def test_load_published_artifact_reads_the_dated_file(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _write_artifact(tmp_path, PUBLISHED_ARTIFACT)
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")
    got = reproduce.load_published_artifact(AGENCY.id, DATE)
    assert got["feed"]["sha256"] == SHA


def test_load_published_artifact_missing_file_raises(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")
    with pytest.raises(reproduce.ReproduceError, match="no published artifact"):
        reproduce.load_published_artifact(AGENCY.id, DATE)


def test_reproduce_reports_identical_when_scores_match(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _write_artifact(tmp_path, PUBLISHED_ARTIFACT)
    _wire_common(tmp_path, monkeypatch)
    _wire_categories(monkeypatch)  # matches the published scores exactly

    result = reproduce.reproduce(AGENCY, DATE)
    assert result["identical"] is True
    assert result["differences"] == []
    assert result["sha256"] == SHA
    assert result["validator_version"] == "8.0.1"


def test_reproduce_passes_agency_country_to_validator(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _write_artifact(tmp_path, PUBLISHED_ARTIFACT)
    _wire_common(tmp_path, monkeypatch)
    _wire_categories(monkeypatch)
    calls: list[dict[str, object]] = []

    def validate(*_args: object, **kwargs: object) -> Path:
        calls.append(kwargs)
        return Path("/tmp/fake-report.json")

    monkeypatch.setattr(reproduce, "run_validator", validate)
    canadian = Agency(
        id=AGENCY.id,
        name=AGENCY.name,
        static_gtfs_url=AGENCY.static_gtfs_url,
        country="CA",
    )

    reproduce.reproduce(canadian, DATE)

    assert calls == [{"country_code": "CA", "version": "8.0.1"}]


def test_reproduce_reports_the_diff_when_a_category_moved(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _write_artifact(tmp_path, PUBLISHED_ARTIFACT)
    _wire_common(tmp_path, monkeypatch)
    _wire_categories(monkeypatch, correctness=70.0)  # a regression re-derives lower

    result = reproduce.reproduce(AGENCY, DATE)
    assert result["identical"] is False
    assert any("correctness" in d for d in result["differences"])
    assert any("grade" in d or "score" in d for d in result["differences"])


def test_reproduce_skips_unmeasured_categories(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    # realtime is not_yet_measured in the published artifact and build_scorecard
    # never receives a realtime CategoryResult here; it must not be compared.
    _write_artifact(tmp_path, PUBLISHED_ARTIFACT)
    _wire_common(tmp_path, monkeypatch)
    _wire_categories(monkeypatch)

    result = reproduce.reproduce(AGENCY, DATE)
    assert not any("realtime" in d for d in result["differences"])
    assert result["not_compared"]


def test_reproduce_raises_when_artifact_has_no_hash(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    payload = {**PUBLISHED_ARTIFACT, "feed": {}}
    _write_artifact(tmp_path, payload)
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")
    with pytest.raises(reproduce.ReproduceError, match=r"no feed\.sha256"):
        reproduce.reproduce(AGENCY, DATE)


def test_reproduce_raises_a_clear_error_on_archive_miss(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    _write_artifact(tmp_path, PUBLISHED_ARTIFACT)
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")

    def _miss(sha: str) -> bytes:
        raise archive.ArchiveMiss(f"feed {sha} is not in the raw archive (checked local only)")

    monkeypatch.setattr(archive, "fetch", _miss)
    with pytest.raises(reproduce.ReproduceError, match="cannot reproduce"):
        reproduce.reproduce(AGENCY, DATE)
