"""Unit tests for the program report bundle core: request validation, id
classification against the registry, the build (zip + manifest), and the
delivery email. The report renderer itself is covered in test_report.py;
here it is exercised only through generate_report on a published fixture."""

from __future__ import annotations

import base64
import datetime as dt
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.bundle import (
    BUNDLE_ID_RE,
    DOWNLOAD_DAYS,
    MAX_AGENCIES,
    MAX_LOGO_BYTES,
    STATUS_CURRENT,
    STATUS_INCLUDED,
    STATUS_NOT_PUBLISHED,
    STATUS_RETIRED,
    STATUS_UNKNOWN,
    BundleError,
    BundleRequest,
    build_bundle,
    classify,
    delivery_email,
    expires_on,
    new_bundle_id,
    parse_request,
    plan,
    resolve_logo,
)
from scorecard_pipeline.config import AGENCIES, Agency


def _publish_fixture(root: Path, agency_id: str = "sampletown") -> None:
    """A minimal published artifact + index, the fields the report reads.
    Mirrors test_report._publish_fixture; tests run in importlib mode, so a
    sibling import is not available."""
    art = root / "data" / "artifacts"
    (art / agency_id).mkdir(parents=True)
    artifact = {
        "schema_version": "1.5",
        "rubric_version": "1.2",
        "scoring_profile_id": "gtfs-scorecard-1.2",
        "scoring_profile_rubric_version": "1.2",
        "validator_version": "7.0.0",
        "snapshot_date": "2026-09-01",
        "agency": {"id": agency_id, "name": "Sampletown Transit"},
        "feed": {"static_url": "https://example.org/gtfs.zip", "reachable": True},
        "overall": {"grade": "B", "score": 81.5},
        "categories": {
            "correctness": {
                "name": "correctness",
                "status": "measured",
                "score": 90.0,
                "weight": 0.35,
                "summary": "The validator flagged 2 kinds of issue.",
            },
            "freshness": {
                "name": "freshness",
                "status": "measured",
                "score": 100.0,
                "weight": 0.2,
                "summary": "Service data covers the next 60 days.",
                "details": {"days_until_expiry": 60},
            },
            "completeness": {
                "name": "completeness",
                "status": "measured",
                "score": 55.0,
                "weight": 0.25,
                "summary": "Wheelchair accessibility is unstated on most stops.",
            },
            "realtime": {
                "name": "realtime",
                "status": "not_yet_measured",
                "weight": 0.2,
                "summary": "No realtime feed is published yet. Nothing counts against the grade.",
            },
        },
        "top_fixes": [
            {
                "rank": 1,
                "code": "scorecard_wheelchair_boarding_unknown",
                "what": "12 of 12 stops don't say whether a wheelchair user can board there.",
                "why": "Riders who use wheelchairs can't plan a trip.",
                "fix": "Set wheelchair_boarding for every stop.",
                "effort": "A column in stops.txt.",
            }
        ],
    }
    (art / agency_id / "latest.json").write_text(json.dumps(artifact))
    index = {"schema_version": "1", "agencies": {agency_id: {"name": "Sampletown Transit"}}}
    (art / "index.json").write_text(json.dumps(index))


FROZEN = dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.UTC)
BUNDLE_ID = "0123456789abcdef0123456789abcdef"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
SVG = b"<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg'/>"


def _raw(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "bundle_id": BUNDLE_ID,
        "program_name": "Example State Transit Program",
        "accent": "#2C5F70",
        "logo": "",
        "agency_ids": "sampletown, Yolobus ,sampletown",
        "deliver_to": "liaison@example.org",
        "cadence": "one_time",
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# parse_request
# ---------------------------------------------------------------------------


def test_parse_request_normalizes_ids_accent_and_defaults() -> None:
    request = parse_request(_raw())
    assert request.agency_ids == ("sampletown", "yolobus")
    assert request.accent == "#2c5f70"
    assert request.logo is None
    assert request.cadence == "one_time"
    assert request.as_dict()["agency_ids"] == ["sampletown", "yolobus"]
    assert request.as_dict()["logo"] == ""


def test_parse_request_accepts_a_list_of_ids_and_defaults_the_accent() -> None:
    request = parse_request(_raw(agency_ids=["a1", "b-2"], accent="", cadence=""))
    assert request.agency_ids == ("a1", "b-2")
    assert request.accent == "#163a2c"
    assert request.cadence == "one_time"


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("bundle_id", "short", "32 lowercase hex"),
        ("bundle_id", "", "32 lowercase hex"),
        ("program_name", "", "program_name is required"),
        ("program_name", "x" * 121, "120 characters"),
        ("accent", "teal", "rrggbb"),
        ("deliver_to", "not-an-email", "email address"),
        ("cadence", "weekly", "cadence must be one of"),
        ("agency_ids", "", "at least one agency"),
        ("agency_ids", "Bad Id!", "not a scorecard id"),
        ("agency_ids", 7, "comma-separated string or a list"),
        ("logo", "http://example.org/logo.png", "https URL"),
        ("logo", "data:text/plain;base64,aGk=", "data: URI"),
        ("logo", "data:image/png;base64,***", "data: URI"),
        ("logo", "data:image/png;base64,abc", "not valid base64"),
    ],
)
def test_parse_request_refuses_with_one_plain_sentence(field: str, value: Any, match: str) -> None:
    with pytest.raises(BundleError, match=match):
        parse_request(_raw(**{field: value}))


def test_parse_request_caps_the_cohort() -> None:
    ids = ",".join(f"agency{i}" for i in range(MAX_AGENCIES + 1))
    with pytest.raises(BundleError, match=f"at most {MAX_AGENCIES}"):
        parse_request(_raw(agency_ids=ids))
    assert len(parse_request(_raw(agency_ids=ids.rsplit(",", 1)[0])).agency_ids) == MAX_AGENCIES


def test_parse_request_keeps_a_valid_data_uri_and_bounds_its_size() -> None:
    small = "data:image/png;base64," + base64.b64encode(PNG).decode()
    assert parse_request(_raw(logo=small)).logo == small
    big = "data:image/png;base64," + base64.b64encode(b"\0" * (MAX_LOGO_BYTES + 1)).decode()
    with pytest.raises(BundleError, match="KiB or smaller"):
        parse_request(_raw(logo=big))


def test_parse_request_keeps_an_https_logo_url_for_the_build_step(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scorecard_pipeline.bundle.validate_public_url", lambda url: None)
    request = parse_request(_raw(logo="https://example.org/logo.svg"))
    assert request.logo == "https://example.org/logo.svg"


def test_parse_request_refuses_a_non_public_logo_host(monkeypatch: pytest.MonkeyPatch) -> None:
    from scorecard_pipeline.net import UnsafeURLError

    def refuse(url: str) -> None:
        raise UnsafeURLError("host resolves to non-public address")

    monkeypatch.setattr("scorecard_pipeline.bundle.validate_public_url", refuse)
    with pytest.raises(BundleError, match="logo URL refused"):
        parse_request(_raw(logo="https://10.0.0.1/logo.svg"))


def test_new_bundle_id_is_a_128_bit_hex_token() -> None:
    token = new_bundle_id()
    assert BUNDLE_ID_RE.match(token)
    assert token != new_bundle_id()


# ---------------------------------------------------------------------------
# classify / plan
# ---------------------------------------------------------------------------


def _register(agency_id: str, **kwargs: Any) -> None:
    AGENCIES[agency_id] = Agency(
        id=agency_id, name=agency_id.title(), static_gtfs_url="https://example.org/g.zip", **kwargs
    )


def test_classify_treats_every_id_as_current_when_no_registry_is_loaded() -> None:
    assert classify(("a", "b")) == {"a": STATUS_CURRENT, "b": STATUS_CURRENT}


def test_classify_against_the_registry() -> None:
    _register("live")
    _register("old", alias_of="live")
    _register("gone", feed_status="inactive")
    assert classify(("live", "old", "gone", "nowhere")) == {
        "live": STATUS_CURRENT,
        "old": STATUS_RETIRED,
        "gone": STATUS_RETIRED,
        "nowhere": STATUS_UNKNOWN,
    }


def test_plan_separates_fetchable_ids_from_refusals_with_reasons() -> None:
    _register("live")
    _register("old", alias_of="live")
    request = parse_request(_raw(agency_ids="live,old,nowhere"))
    out = plan(request)
    assert out["bundle_id"] == BUNDLE_ID
    assert out["current"] == ["live"]
    assert [r["id"] for r in out["refused"]] == ["old", "nowhere"]
    assert all(r["detail"] for r in out["refused"])


# ---------------------------------------------------------------------------
# resolve_logo
# ---------------------------------------------------------------------------


def test_resolve_logo_passes_none_and_data_uris_through() -> None:
    assert resolve_logo(None) is None
    uri = "data:image/svg+xml;base64,PHN2Zy8+"
    assert resolve_logo(uri, fetch=lambda url: b"") == uri


@pytest.mark.parametrize(
    ("raw", "media_type"),
    [(PNG, "image/png"), (b"\xff\xd8\xff\xe0", "image/jpeg"), (SVG, "image/svg+xml")],
)
def test_resolve_logo_fetches_and_sniffs_the_media_type(raw: bytes, media_type: str) -> None:
    out = resolve_logo("https://example.org/logo", fetch=lambda url: raw)
    assert out is not None
    assert out.startswith(f"data:{media_type};base64,")
    assert base64.b64decode(out.split(",", 1)[1]) == raw


def test_resolve_logo_refuses_non_images_oversize_and_fetch_failures() -> None:
    with pytest.raises(BundleError, match="did not return an SVG, PNG, or JPEG"):
        resolve_logo("https://example.org/x", fetch=lambda url: b"<!doctype html><p>hi")
    with pytest.raises(BundleError, match="KiB or smaller"):
        resolve_logo("https://example.org/x", fetch=lambda url: b"\0" * (MAX_LOGO_BYTES + 1))

    def boom(url: str) -> bytes:
        raise OSError("connection refused")

    with pytest.raises(BundleError, match="could not be fetched"):
        resolve_logo("https://example.org/x", fetch=boom)


# ---------------------------------------------------------------------------
# build_bundle
# ---------------------------------------------------------------------------


def test_build_bundle_zips_reports_and_names_every_requested_id(
    isolated_repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("scorecard_pipeline.bundle.validate_public_url", lambda url: None)
    _publish_fixture(isolated_repo_root)
    _register("sampletown")
    _register("tracked-but-unscored")
    _register("old", alias_of="sampletown")
    request = parse_request(
        _raw(
            agency_ids="sampletown,tracked-but-unscored,old,nowhere",
            logo="https://example.org/logo.svg",
        )
    )
    out = tmp_path / "out" / "bundle.zip"
    manifest = build_bundle(request, out, now=FROZEN, fetch_logo=lambda url: SVG)

    assert manifest["requested"] == 4
    assert manifest["included"] == 1
    assert manifest["generated_at"] == "2026-09-01T12:00:00+00:00"
    statuses = {a["id"]: a["status"] for a in manifest["agencies"]}
    assert statuses == {
        "sampletown": STATUS_INCLUDED,
        "tracked-but-unscored": STATUS_NOT_PUBLISHED,
        "old": STATUS_RETIRED,
        "nowhere": STATUS_UNKNOWN,
    }
    with zipfile.ZipFile(out) as archive:
        names = set(archive.namelist())
        assert names == {"README.txt", "manifest.json", "reports/sampletown-board-report.html"}
        report = archive.read("reports/sampletown-board-report.html").decode()
        assert "Prepared by Example State Transit Program" in report
        assert "data:image/svg+xml;base64," in report
        assert json.loads(archive.read("manifest.json")) == manifest
        readme = archive.read("README.txt").decode()
        assert "1 of 4 requested agencies are included" in readme
        assert "nowhere: not a tracked scorecard id" in readme
        assert "buys no influence over grades" in readme


def test_build_bundle_with_no_registry_lets_the_artifact_tree_decide(
    isolated_repo_root: Path, tmp_path: Path
) -> None:
    _publish_fixture(isolated_repo_root)
    request = parse_request(_raw(agency_ids="sampletown,nowhere"))
    manifest = build_bundle(request, tmp_path / "b.zip", now=FROZEN)
    statuses = {a["id"]: a["status"] for a in manifest["agencies"]}
    assert statuses == {"sampletown": STATUS_INCLUDED, "nowhere": STATUS_NOT_PUBLISHED}


def test_build_bundle_with_nothing_publishable_still_writes_the_manifest(
    isolated_repo_root: Path, tmp_path: Path
) -> None:
    request = parse_request(_raw(agency_ids="nowhere"))
    out = tmp_path / "b.zip"
    manifest = build_bundle(request, out, now=FROZEN)
    assert manifest["included"] == 0
    with zipfile.ZipFile(out) as archive:
        assert set(archive.namelist()) == {"README.txt", "manifest.json"}


def test_build_bundle_raises_for_an_unusable_logo_before_rendering(
    isolated_repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("scorecard_pipeline.bundle.validate_public_url", lambda url: None)
    request = parse_request(_raw(logo="https://example.org/logo.svg"))
    with pytest.raises(BundleError, match="did not return"):
        build_bundle(request, tmp_path / "b.zip", now=FROZEN, fetch_logo=lambda url: b"nope")
    assert not (tmp_path / "b.zip").exists()


# ---------------------------------------------------------------------------
# delivery_email / expires_on
# ---------------------------------------------------------------------------


def _manifest() -> dict[str, Any]:
    return {
        "requested": 3,
        "included": 2,
        "agencies": [
            {"id": "a", "status": STATUS_INCLUDED, "detail": ""},
            {"id": "b", "status": STATUS_INCLUDED, "detail": ""},
            {"id": "c", "status": STATUS_UNKNOWN, "detail": "not a tracked scorecard id"},
        ],
    }


def test_delivery_email_states_the_link_the_expiry_and_every_omission() -> None:
    request = parse_request(_raw())
    email = delivery_email(request, _manifest(), "https://x.example/download/abc", "2026-10-01")
    assert email.to == "liaison@example.org"
    assert email.subject == "Board reports for Example State Transit Program: 2 of 3 ready"
    assert "valid until 2026-10-01" in email.body
    assert "https://x.example/download/abc" in email.body
    assert "c: not a tracked scorecard id" in email.body
    assert "refreshes monthly" not in email.body
    assert "buys no influence" in email.body


def test_delivery_email_for_a_subscription_says_how_to_cancel() -> None:
    request = BundleRequest(
        bundle_id=BUNDLE_ID,
        program_name="P",
        accent="#163a2c",
        logo=None,
        agency_ids=("a",),
        deliver_to="p@example.org",
        cadence="monthly",
    )
    email = delivery_email(request, _manifest(), "https://x.example/d", "2026-10-01")
    assert "refreshes monthly" in email.body
    assert "cancel the subscription" in email.body


def test_expires_on_is_the_download_window_in_utc() -> None:
    assert DOWNLOAD_DAYS == 30
    assert expires_on(FROZEN) == "2026-10-01"
    assert expires_on(FROZEN, days=1) == "2026-09-02"
