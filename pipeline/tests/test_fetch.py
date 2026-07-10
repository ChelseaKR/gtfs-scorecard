"""Tests for the feed fetcher's Mobility Database mirror fallback."""

from __future__ import annotations

import datetime as dt
import io
import zipfile

import pytest
import requests

from scorecard_pipeline import fetch as fetchmod
from scorecard_pipeline.config import Agency, raw_dir
from scorecard_pipeline.net import UnsafeURLError

ORIGIN = "https://origin.example.org/g.zip"
MIRROR = "https://storage.googleapis.com/storage/v1/b/mdb-latest/o/x.zip?alt=media"
AGENCY = Agency(id="x", name="X Transit", static_gtfs_url=ORIGIN)


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("agency.txt", "agency_name\nX")
    return buf.getvalue()


def test_origin_success_records_origin_provenance(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fetchmod, "safe_get", lambda url, **_: _zip_bytes())
    body, prov = fetchmod._download_with_mirror_fallback(AGENCY)
    assert zipfile.is_zipfile(io.BytesIO(body))
    assert prov.source == "origin"
    assert prov.final_url == ORIGIN
    assert prov.max_attempts == fetchmod.FETCH_RETRIES + 1
    assert prov.origin_error is None


def test_falls_back_to_mirror_when_origin_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    def fake_safe_get(url: str, **_: object) -> bytes:
        seen.append(url)
        if url == ORIGIN:
            raise requests.exceptions.ConnectTimeout("origin firewalls our IP")
        return _zip_bytes()

    monkeypatch.setattr(fetchmod, "safe_get", fake_safe_get)
    monkeypatch.setattr("scorecard_pipeline.mobilitydb.hosted_mirror_url", lambda *a, **k: MIRROR)
    body, prov = fetchmod._download_with_mirror_fallback(AGENCY)
    assert zipfile.is_zipfile(io.BytesIO(body))
    assert seen == [ORIGIN, MIRROR]
    # The provenance states the mirror served the bytes, and why.
    assert prov.source == "mirror"
    assert prov.final_url == MIRROR
    assert prov.origin_error == "ConnectTimeout"


def test_mirror_fallback_on_origin_403_records_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = requests.Response()
    resp.status_code = 403

    def fake_safe_get(url: str, **_: object) -> bytes:
        if url == ORIGIN:
            raise requests.exceptions.HTTPError("403 blocked", response=resp)
        return _zip_bytes()

    monkeypatch.setattr(fetchmod, "safe_get", fake_safe_get)
    monkeypatch.setattr("scorecard_pipeline.mobilitydb.hosted_mirror_url", lambda *a, **k: MIRROR)
    _body, prov = fetchmod._download_with_mirror_fallback(AGENCY)
    assert prov.source == "mirror"
    assert prov.final_url == MIRROR
    assert prov.origin_error == "HTTPError"


def test_reraises_when_no_mirror_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_safe_get(url: str, **_: object) -> bytes:
        raise requests.exceptions.ConnectTimeout("blocked")

    monkeypatch.setattr(fetchmod, "safe_get", fake_safe_get)
    monkeypatch.setattr("scorecard_pipeline.mobilitydb.hosted_mirror_url", lambda *a, **k: None)
    with pytest.raises(requests.exceptions.ConnectTimeout):
        fetchmod._download_with_mirror_fallback(AGENCY)


def test_unsafe_url_is_never_mirrored(monkeypatch: pytest.MonkeyPatch) -> None:
    mirror_calls = {"n": 0}

    def fake_safe_get(url: str, **_: object) -> bytes:
        raise UnsafeURLError("resolves to a private address")

    def fake_mirror(*_a: object, **_k: object) -> str:
        mirror_calls["n"] += 1
        return MIRROR

    monkeypatch.setattr(fetchmod, "safe_get", fake_safe_get)
    monkeypatch.setattr("scorecard_pipeline.mobilitydb.hosted_mirror_url", fake_mirror)
    with pytest.raises(UnsafeURLError):
        fetchmod._download_with_mirror_fallback(AGENCY)
    assert mirror_calls["n"] == 0  # an unsafe URL is a hard stop, not a fetch to route around


# ----------------------------------------------------------- fetch_static

DATE = dt.date(2026, 6, 11)

ORIGIN_PROV = fetchmod.FetchProvenance(
    source="origin", final_url=ORIGIN, max_attempts=fetchmod.FETCH_RETRIES + 1
)


def test_fetch_static_reuses_an_existing_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    dest = raw_dir() / AGENCY.id / DATE.isoformat() / "gtfs.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_zip_bytes())

    def explode(_agency: Agency) -> tuple[bytes, fetchmod.FetchProvenance]:
        raise AssertionError("must not re-download when a snapshot already exists")

    monkeypatch.setattr(fetchmod, "_download_with_mirror_fallback", explode)
    result = fetchmod.fetch_static(AGENCY, DATE)
    assert result.reused is True
    assert result.path == dest
    assert result.size_bytes == dest.stat().st_size
    assert len(result.sha256) == 64
    # A snapshot written without a provenance sidecar cannot say how it was
    # fetched; the result states that instead of guessing.
    assert result.source == "unknown"
    assert result.final_url == ORIGIN
    assert result.user_agent == fetchmod.USER_AGENT
    assert result.max_attempts is None
    assert result.origin_error is None


def test_fetch_static_downloads_and_records_the_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fetchmod, "_download_with_mirror_fallback", lambda _a: (_zip_bytes(), ORIGIN_PROV)
    )
    result = fetchmod.fetch_static(AGENCY, DATE)
    assert result.reused is False
    assert result.path.exists()
    assert zipfile.is_zipfile(result.path)
    assert result.size_bytes > 0
    assert result.source == "origin"
    assert result.final_url == ORIGIN
    assert result.user_agent == fetchmod.USER_AGENT
    assert result.max_attempts == fetchmod.FETCH_RETRIES + 1


def test_fetch_static_rejects_a_non_zip_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fetchmod,
        "_download_with_mirror_fallback",
        lambda _a: (b"<html>404</html>", ORIGIN_PROV),
    )
    with pytest.raises(ValueError, match="not a zip"):
        fetchmod.fetch_static(AGENCY, DATE)
    # The rejected partial download is cleaned up and never promoted to a snapshot.
    dest = raw_dir() / AGENCY.id / DATE.isoformat() / "gtfs.zip"
    assert not dest.exists()
    assert not dest.with_suffix(".zip.part").exists()


def test_fetch_static_rejects_an_oversized_archive_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fetchmod, "MAX_GTFS_ENTRY_BYTES", 8)
    monkeypatch.setattr(
        fetchmod, "_download_with_mirror_fallback", lambda _a: (_zip_bytes(), ORIGIN_PROV)
    )

    with pytest.raises(ValueError, match=r"entry 'agency\.txt' expands"):
        fetchmod.fetch_static(AGENCY, DATE)

    dest = raw_dir() / AGENCY.id / DATE.isoformat() / "gtfs.zip"
    assert not dest.exists()
    assert not dest.with_suffix(".zip.part").exists()


def test_fetch_static_rejects_an_extreme_compression_ratio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("stop_times.txt", "A" * 10_000)
    monkeypatch.setattr(fetchmod, "COMPRESSION_RATIO_MIN_BYTES", 1)
    monkeypatch.setattr(fetchmod, "MAX_GTFS_COMPRESSION_RATIO", 2)
    monkeypatch.setattr(
        fetchmod, "_download_with_mirror_fallback", lambda _a: (buf.getvalue(), ORIGIN_PROV)
    )

    with pytest.raises(ValueError, match="unsafe compression ratio"):
        fetchmod.fetch_static(AGENCY, DATE)


def test_reused_snapshot_reads_provenance_back_from_the_sidecar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A fresh mirror-fallback download records its provenance next to gtfs.zip...
    mirror_prov = fetchmod.FetchProvenance(
        source="mirror", final_url=MIRROR, max_attempts=1, origin_error="ConnectTimeout"
    )
    monkeypatch.setattr(
        fetchmod, "_download_with_mirror_fallback", lambda _a: (_zip_bytes(), mirror_prov)
    )
    fresh = fetchmod.fetch_static(AGENCY, DATE)
    assert fresh.source == "mirror"
    sidecar = fresh.path.parent / fetchmod.PROVENANCE_FILENAME
    assert sidecar.exists()

    # ...so a rerun that reuses the snapshot reports the same provenance, and
    # republishing the day stays byte-identical.
    def explode(_agency: Agency) -> tuple[bytes, fetchmod.FetchProvenance]:
        raise AssertionError("must not re-download when a snapshot already exists")

    monkeypatch.setattr(fetchmod, "_download_with_mirror_fallback", explode)
    reused = fetchmod.fetch_static(AGENCY, DATE)
    assert reused.reused is True
    assert reused.source == "mirror"
    assert reused.final_url == MIRROR
    assert reused.user_agent == fetchmod.USER_AGENT
    assert reused.max_attempts == 1
    assert reused.origin_error == "ConnectTimeout"
