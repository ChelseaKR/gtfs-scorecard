"""Tests for `scorecard reproduce` (FIX-02): re-deriving a published grade from
the archived raw bytes and diffing it against what was published.

The validator/metrics layer is mocked (it is exercised elsewhere); this tests
the artifact-loading, archive-miss handling, and diff logic in isolation.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

import scorecard_pipeline.archive as archive
import scorecard_pipeline.reproduce as reproduce
from scorecard_pipeline.config import Agency
from scorecard_pipeline.fetch import (
    FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE,
    ReaderArchive,
)
from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.validate import NoticeGroup, ValidationReport

AGENCY = Agency(id="demo", name="Demo Transit", static_gtfs_url="https://example.org/gtfs.zip")
DATE = "2026-06-11"


def _basic_zip_bytes() -> bytes:
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive_zip:
        archive_zip.writestr("agency.txt", "agency_name\nDemo")
    return body.getvalue()


ARCHIVED_BYTES = _basic_zip_bytes()
SHA = hashlib.sha256(ARCHIVED_BYTES).hexdigest()

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
    monkeypatch.setattr(archive, "fetch", lambda sha: ARCHIVED_BYTES)
    monkeypatch.setattr(reproduce, "run_validator", lambda *a, **k: Path("/tmp/fake-report.json"))
    monkeypatch.setattr(
        reproduce,
        "parse_report",
        lambda path: ValidationReport(
            validator_version="8.0.1", notices=[NoticeGroup("x", "WARNING", 1)]
        ),
    )
    monkeypatch.setattr(
        reproduce,
        "prepare_reader_archive",
        lambda path: ReaderArchive(path=path, normalized=False),
    )


def _wire_categories(  # type: ignore[no-untyped-def]
    monkeypatch: pytest.MonkeyPatch, *, correctness=95.0, freshness=100.0, completeness=80.0
) -> None:
    monkeypatch.setattr(
        reproduce, "correctness", lambda report: CategoryResult("correctness", correctness, "s")
    )
    # The two feed-content categories now come back from one call, which is
    # also where an archive that could not be read is refused outright, so the
    # stub stands in for the pair rather than for each reader.
    monkeypatch.setattr(
        reproduce,
        "score_feed_content",
        lambda path, *, today, service_type="fixed", fare_free=False: [
            CategoryResult("freshness", freshness, "s"),
            CategoryResult("completeness", completeness, "s"),
        ],
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


@pytest.mark.parametrize("bad_date", ["../latest", "2026-6-11", "20260611", "2026-02-30"])
def test_load_published_artifact_rejects_noncanonical_or_traversal_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_date: str
) -> None:
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")
    with pytest.raises(reproduce.ReproduceError, match="canonical YYYY-MM-DD"):
        reproduce.load_published_artifact(AGENCY.id, bad_date)


@pytest.mark.parametrize("bad_agency_id", ["../escape", "UPPER", "agency/name"])
def test_load_published_artifact_rejects_non_slug_or_traversal_agency_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bad_agency_id: str
) -> None:
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")
    with pytest.raises(reproduce.ReproduceError, match="lowercase registry slug"):
        reproduce.load_published_artifact(bad_agency_id, DATE)


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


@pytest.mark.parametrize(
    "fetch_block",
    [
        {"reader_archive_profile": FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE},
        {"reader_archive_normalized": True},
    ],
)
def test_reproduce_validates_raw_wasco_archive_but_scores_normalized_reader_view(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fetch_block: dict[str, object]
) -> None:
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive_zip:
        archive_zip.writestr("Wasco Dial-a-Ride/agency.txt", "agency_name\nWasco")
        archive_zip.writestr("Wasco Dial-a-Ride/ stop_times.txt", "trip_id\n")
        archive_zip.writestr("Wasco Dial-a-Ride/calendar.txt", "service_id,end_date\n")
    archived_body = body.getvalue()
    payload = {
        **PUBLISHED_ARTIFACT,
        "feed": {"sha256": hashlib.sha256(archived_body).hexdigest()},
        "fetch": fetch_block,
    }
    _write_artifact(tmp_path, payload)
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")
    monkeypatch.setattr(archive, "fetch", lambda _sha: archived_body)

    seen: dict[str, object] = {}

    def validate(raw_path: Path, *_args: object, **_kwargs: object) -> Path:
        seen["validator_path"] = raw_path.name
        with zipfile.ZipFile(raw_path) as raw:
            seen["validator_names"] = raw.namelist()
        return Path("/tmp/fake-report.json")

    def feed_content(reader_path: str, **_kwargs: object) -> list[CategoryResult]:
        path = Path(reader_path)
        seen["reader_path"] = path.name
        with zipfile.ZipFile(path) as reader:
            seen["reader_names"] = reader.namelist()
        return [CategoryResult("freshness", 100.0, "s"), CategoryResult("completeness", 80.0, "s")]

    monkeypatch.setattr(reproduce, "run_validator", validate)
    monkeypatch.setattr(
        reproduce,
        "parse_report",
        lambda _path: ValidationReport(
            validator_version="8.0.1", notices=[NoticeGroup("x", "WARNING", 1)]
        ),
    )
    monkeypatch.setattr(reproduce, "score_feed_content", feed_content)
    monkeypatch.setattr(
        reproduce, "correctness", lambda report: CategoryResult("correctness", 95.0, "s")
    )

    result = reproduce.reproduce(AGENCY, DATE)

    assert seen["validator_path"] == "gtfs.zip"
    assert seen["validator_names"] == [
        "Wasco Dial-a-Ride/agency.txt",
        "Wasco Dial-a-Ride/ stop_times.txt",
        "Wasco Dial-a-Ride/calendar.txt",
    ]
    assert seen["reader_path"] == "gtfs.reader.zip"
    assert seen["reader_names"] == ["agency.txt", "calendar.txt", "stop_times.txt"]
    assert result["reader_archive_normalized"] is True


def test_reproduce_without_published_flag_keeps_historical_raw_reader_behavior(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive_zip:
        archive_zip.writestr("Wrapped/agency.txt", "agency_name\nDemo")
    archived_body = body.getvalue()
    payload = {
        **PUBLISHED_ARTIFACT,
        "feed": {"sha256": hashlib.sha256(archived_body).hexdigest()},
    }
    _write_artifact(tmp_path, payload)
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")
    monkeypatch.setattr(archive, "fetch", lambda _sha: archived_body)
    monkeypatch.setattr(
        reproduce,
        "prepare_reader_archive",
        lambda _path: (_ for _ in ()).throw(AssertionError("historical artifact normalized")),
    )
    seen: dict[str, str] = {}

    def validate(path: Path, *_args: object, **_kwargs: object) -> Path:
        seen["validator"] = path.name
        return Path("/tmp/fake-report.json")

    monkeypatch.setattr(reproduce, "run_validator", validate)
    monkeypatch.setattr(
        reproduce,
        "parse_report",
        lambda _path: ValidationReport(validator_version="8.0.1", notices=[]),
    )

    def feed_content(path: str, **_kwargs: object) -> list[CategoryResult]:
        # score_feed_content is now the only reader of the feed's own contents,
        # so it is where the reader-view routing is observable.
        seen["reader"] = Path(path).name
        return [CategoryResult("freshness", 100.0, "s"), CategoryResult("completeness", 80.0, "s")]

    monkeypatch.setattr(reproduce, "score_feed_content", feed_content)
    monkeypatch.setattr(
        reproduce, "correctness", lambda report: CategoryResult("correctness", 95.0, "s")
    )

    result = reproduce.reproduce(AGENCY, DATE)

    assert seen == {"validator": "gtfs.zip", "reader": "gtfs.zip"}
    assert result["reader_archive_normalized"] is False


def test_reproduce_rejects_published_normalization_flag_that_cannot_be_replayed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {**PUBLISHED_ARTIFACT, "fetch": {"reader_archive_normalized": True}}
    _write_artifact(tmp_path, payload)
    _wire_common(tmp_path, monkeypatch)

    with pytest.raises(reproduce.ReproduceError, match="do not produce a normalized view"):
        reproduce.reproduce(AGENCY, DATE)


def test_reproduce_rejects_unknown_reader_archive_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = {**PUBLISHED_ARTIFACT, "fetch": {"reader_archive_profile": "future-v9"}}
    _write_artifact(tmp_path, payload)
    _wire_common(tmp_path, monkeypatch)

    with pytest.raises(reproduce.ReproduceError, match="unknown reader archive profile"):
        reproduce.reproduce(AGENCY, DATE)


def test_reproduce_wraps_unreadable_archived_gtfs_as_domain_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = b"not a zip"
    payload = {
        **PUBLISHED_ARTIFACT,
        "feed": {"sha256": hashlib.sha256(body).hexdigest()},
    }
    _write_artifact(tmp_path, payload)
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")
    monkeypatch.setattr(archive, "fetch", lambda _sha: body)

    with pytest.raises(reproduce.ReproduceError, match="unsafe or unreadable"):
        reproduce.reproduce(AGENCY, DATE)


def test_reproduce_wraps_ambiguous_normalized_archive_as_domain_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    body = io.BytesIO()
    with zipfile.ZipFile(body, "w") as archive_zip:
        archive_zip.writestr("A/agency.txt", "agency_name\nA")
        archive_zip.writestr("B/stops.txt", "stop_id\nB")
    archived_body = body.getvalue()
    payload = {
        **PUBLISHED_ARTIFACT,
        "feed": {"sha256": hashlib.sha256(archived_body).hexdigest()},
        "fetch": {"reader_archive_profile": FLAT_SINGLE_ROOT_READER_ARCHIVE_PROFILE},
    }
    _write_artifact(tmp_path, payload)
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")
    monkeypatch.setattr(archive, "fetch", lambda _sha: archived_body)

    with pytest.raises(reproduce.ReproduceError, match=r"normalization failed.*multiple"):
        reproduce.reproduce(AGENCY, DATE)


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


def test_reproduce_wraps_archive_integrity_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_artifact(tmp_path, PUBLISHED_ARTIFACT)
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")

    def corrupt(_sha: str) -> bytes:
        raise archive.ArchiveIntegrityError("corrupt local archive")

    monkeypatch.setattr(archive, "fetch", corrupt)
    with pytest.raises(reproduce.ReproduceError, match="corrupt local archive"):
        reproduce.reproduce(AGENCY, DATE)


def test_reproduce_verifies_bytes_even_when_archive_fetch_is_replaced(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_artifact(tmp_path, PUBLISHED_ARTIFACT)
    monkeypatch.setattr(reproduce, "artifacts_dir", lambda: tmp_path / "data" / "artifacts")
    monkeypatch.setattr(archive, "fetch", lambda _sha: b"wrong bytes")

    with pytest.raises(reproduce.ReproduceError, match=r"not the artifact's feed\.sha256"):
        reproduce.reproduce(AGENCY, DATE)
