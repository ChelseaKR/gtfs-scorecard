"""Tests for the self-serve submission core."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scorecard_pipeline.agencies import AgencyConfigError, parse_agencies
from scorecard_pipeline.submissions import build_submission, form_to_entry

REPO_YAML = (Path(__file__).resolve().parents[2] / "agencies.yaml").read_text()

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


def test_submission_yaml_parses_and_includes_new_agency() -> None:
    sub = build_submission(FORM, REPO_YAML)
    agencies = parse_agencies(yaml.safe_load(sub.file_content))
    ids = {a.id for a in agencies}
    assert "fairfield-and-suisun-transit" in ids
    # every entry already in the intake file is preserved
    existing = {a.id for a in parse_agencies(yaml.safe_load(REPO_YAML))}
    assert existing <= ids
    assert sub.branch == "submit-fairfield-and-suisun-transit"
    assert "fasttransit.example" in sub.pr_body


def test_duplicate_of_an_intake_entry_is_rejected() -> None:
    existing = parse_agencies(yaml.safe_load(REPO_YAML))
    dup = dict(FORM, name=existing[0].name)
    with pytest.raises(AgencyConfigError, match="already tracked"):
        build_submission(dup, REPO_YAML)


def test_duplicate_of_a_sharded_entry_is_rejected_via_known_ids() -> None:
    # After the FIX-12 split most tracked agencies live in registry/ shards,
    # not the intake file; the caller-supplied id set keeps the check honest.
    dup = dict(FORM, name="Unitrans")
    with pytest.raises(AgencyConfigError, match="already tracked"):
        build_submission(dup, REPO_YAML, known_ids={"unitrans"})


def test_missing_name_is_rejected() -> None:
    with pytest.raises(AgencyConfigError):
        build_submission(dict(FORM, name=""), REPO_YAML)


def test_bad_url_is_rejected_by_registry_rules() -> None:
    with pytest.raises(AgencyConfigError):
        build_submission(dict(FORM, static_gtfs_url="ftp://nope"), REPO_YAML)
