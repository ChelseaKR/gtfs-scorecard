"""Tests for the self-serve submission core."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scorecard_pipeline.agencies import AgencyConfigError, parse_agencies
from scorecard_pipeline.submissions import build_submission, form_to_entry

INTAKE_YAML = (Path(__file__).resolve().parents[2] / "registry/intake.yaml").read_text()

FORM = {
    "name": "Fairfield and Suisun Transit",
    "static_gtfs_url": "https://example.org/fast.zip",
    "vehicle_positions": "https://example.org/fast/vp.pb",
    "license_note": "CC-BY 4.0",
    "submitter_email": "ops@fasttransit.example",
}


def test_form_to_entry_derives_slug_and_rt() -> None:
    entry = form_to_entry(FORM)
    assert entry["id"] == "fairfield-and-suisun-transit"
    assert entry["rt_urls"] == {"vehicle_positions": "https://example.org/fast/vp.pb"}
    assert "country" not in entry  # legacy API payload keeps the registry's US default


def test_submission_yaml_parses_and_includes_new_agency() -> None:
    sub = build_submission(FORM, INTAKE_YAML)
    agencies = parse_agencies(yaml.safe_load(sub.file_content))
    ids = {a.id for a in agencies}
    assert "fairfield-and-suisun-transit" in ids
    existing = {a.id for a in parse_agencies(yaml.safe_load(INTAKE_YAML))}
    assert existing <= ids
    assert sub.branch == "submit-fairfield-and-suisun-transit"
    assert "fasttransit.example" in sub.pr_body
    assert "- Location: US" in sub.pr_body


def test_international_submission_preserves_explicit_portable_location() -> None:
    form = {
        **FORM,
        "name": "Barrie Transit Test",
        "country": "ca",
        "subdivision_code": "ca-on",
        "subdivision_name": "Ontario",
    }
    entry = form_to_entry(form)
    assert entry["country"] == "CA"
    assert entry["subdivision_code"] == "CA-ON"
    assert entry["subdivision_name"] == "Ontario"
    sub = build_submission(form, INTAKE_YAML)
    agencies = parse_agencies(yaml.safe_load(sub.file_content))
    added = next(a for a in agencies if a.id == "barrie-transit-test")
    assert (added.country, added.subdivision_code, added.subdivision_name) == (
        "CA",
        "CA-ON",
        "Ontario",
    )
    assert "- Location: CA / CA-ON (Ontario)" in sub.pr_body


def test_country_only_international_submission_is_valid() -> None:
    form = {**FORM, "name": "National Feed Test", "country": "CA"}
    entry = form_to_entry(form)
    assert entry["country"] == "CA"
    assert "subdivision_code" not in entry
    sub = build_submission(form, INTAKE_YAML)
    agencies = parse_agencies(yaml.safe_load(sub.file_content))
    added = next(a for a in agencies if a.id == "national-feed-test")
    assert (added.country, added.subdivision_code, added.subdivision_name) == ("CA", "", "")


@pytest.mark.parametrize(
    "updates, message",
    [
        (
            {"country": "CA", "subdivision_code": "CA-ON"},
            "both an ISO subdivision code and subdivision name",
        ),
        (
            {"country": "CA", "subdivision_name": "Ontario"},
            "both an ISO subdivision code and subdivision name",
        ),
        ({"subdivision_code": "US-CA", "subdivision_name": "California"}, "Country is required"),
    ],
)
def test_ambiguous_international_location_is_rejected(
    updates: dict[str, str], message: str
) -> None:
    with pytest.raises(AgencyConfigError, match=message):
        form_to_entry({**FORM, **updates})


def test_duplicate_intake_agency_is_rejected() -> None:
    # An agency still awaiting a verified location, so this exercises the
    # intake half of the duplicate check rather than the sharded half below.
    dup = dict(FORM, name="Megabus")
    with pytest.raises(AgencyConfigError, match="already tracked"):
        build_submission(dup, INTAKE_YAML)


def test_duplicate_sharded_agency_is_rejected_via_known_ids() -> None:
    dup = dict(FORM, name="Unitrans")
    with pytest.raises(AgencyConfigError, match="already tracked"):
        build_submission(dup, INTAKE_YAML, known_ids={"unitrans"})


def test_missing_name_is_rejected() -> None:
    with pytest.raises(AgencyConfigError):
        build_submission(dict(FORM, name=""), INTAKE_YAML)


def test_bad_url_is_rejected_by_registry_rules() -> None:
    with pytest.raises(AgencyConfigError):
        build_submission(dict(FORM, static_gtfs_url="ftp://nope"), INTAKE_YAML)
