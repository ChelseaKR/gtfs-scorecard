"""Tests for the agencies.yaml registry loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scorecard_pipeline.agencies import AgencyConfigError, load_agencies, parse_agencies
from scorecard_pipeline.config import AGENCIES, Agency

REPO_YAML = Path(__file__).resolve().parents[2] / "agencies.yaml"

VALID_ENTRY: dict[str, object] = {
    "id": "demo",
    "name": "Demo Transit",
    "static_gtfs_url": "https://example.org/gtfs.zip",
    "rt_urls": {"trip_updates": "https://example.org/tu.pb"},
    "rt_note": "",
    "license_note": "CC-BY",
}
VALID: dict[str, object] = {"agencies": [VALID_ENTRY]}


def entry(**overrides: object) -> dict[str, object]:
    base = dict(VALID_ENTRY)
    base.update(overrides)
    return {"agencies": [base]}


def test_valid_entry_parses() -> None:
    (agency,) = parse_agencies(VALID)
    assert agency.id == "demo"
    assert agency.rt_urls == {"trip_updates": "https://example.org/tu.pb"}
    assert agency.license_note == "CC-BY"


def _repo_registry() -> list[Agency]:
    """Every entry across the real repo registry: intake file plus shards
    (FIX-12), parsed the way the loader merges them."""
    from scorecard_pipeline.agencies import registry_paths

    agencies = []
    for path in registry_paths(REPO_YAML.parent):
        agencies.extend(
            parse_agencies(
                yaml.safe_load(path.read_text()), validate_aliases=False, allow_empty=True
            )
        )
    return agencies


def test_repo_registry_is_valid_and_lists_pilots() -> None:
    agencies = _repo_registry()
    ids = {a.id for a in agencies}
    assert {"unitrans", "yolobus"} <= ids
    yolobus = next(a for a in agencies if a.id == "yolobus")
    assert set(yolobus.rt_urls) == {"trip_updates", "vehicle_positions", "service_alerts"}
    assert yolobus.ntd_id == "90090"  # FTA-assigned NTD ID
    unitrans = next(a for a in agencies if a.id == "unitrans")
    assert unitrans.rt_note  # key-gated realtime keeps its neutral note
    assert unitrans.ntd_id == "90142"


def test_ntd_id_parses_and_defaults_empty() -> None:
    (default_agency,) = parse_agencies(VALID)
    assert default_agency.ntd_id == ""
    (agency,) = parse_agencies(entry(ntd_id="  90142  "))
    assert agency.ntd_id == "90142"


def test_ntd_id_rejects_non_numeric() -> None:
    with pytest.raises(AgencyConfigError, match="ntd_id must be a 4- or 5-digit NTD number"):
        parse_agencies(entry(ntd_id="90142x"))


def test_country_defaults_to_us_and_normalizes() -> None:
    (default_agency,) = parse_agencies(VALID)
    assert default_agency.country == "US"  # default keeps every existing entry US
    (agency,) = parse_agencies(entry(country="ca"))
    assert agency.country == "CA"  # normalized to an uppercase ISO code


def test_country_rejects_non_iso_code() -> None:
    with pytest.raises(AgencyConfigError, match="country must be one of"):
        parse_agencies(entry(country="Canada"))


def test_repo_registry_includes_canada_pilot() -> None:
    agencies = _repo_registry()
    by_id = {a.id: a for a in agencies}
    assert {"whitehorse-transit", "barrie-transit", "london-transit-commission"} <= set(by_id)
    assert all(by_id[i].country == "CA" for i in ("whitehorse-transit", "barrie-transit"))
    assert by_id["unitrans"].country == "US"  # US pilots keep the default


def test_load_agencies_populates_registry(tmp_path: Path) -> None:
    path = tmp_path / "agencies.yaml"
    path.write_text(yaml.safe_dump(VALID))
    load_agencies(path)
    assert set(AGENCIES) == {"demo"}
    load_agencies(path)  # idempotent, no duplicates
    assert set(AGENCIES) == {"demo"}


@pytest.mark.parametrize(
    ("broken", "hint"),
    [
        (entry(id="Bad Slug!"), "lowercase slug"),
        (entry(name=""), "name is required"),
        (entry(static_gtfs_url="ftp://x"), "http(s) URL"),
        (entry(rt_urls={"positions": "https://x"}), "unknown rt_urls kind"),
        (entry(rt_urls={"trip_updates": "not a url"}), "rt_urls.trip_updates"),
        (entry(extra_field=1), "unknown field"),
        ({"agencies": []}, "no agencies"),
        ({"nope": True}, "top-level 'agencies:'"),
    ],
)
def test_malformed_entries_fail_with_plain_messages(broken: object, hint: str) -> None:
    with pytest.raises(AgencyConfigError, match=r".*") as excinfo:
        parse_agencies(broken)
    assert hint in str(excinfo.value)


def test_duplicate_ids_rejected() -> None:
    doubled = {"agencies": [VALID_ENTRY, VALID_ENTRY]}
    with pytest.raises(AgencyConfigError) as excinfo:
        parse_agencies(doubled)
    assert "duplicate" in str(excinfo.value)


def test_missing_file_message(tmp_path: Path) -> None:
    with pytest.raises(AgencyConfigError) as excinfo:
        load_agencies(tmp_path / "nowhere.yaml")
    assert "no agency registry" in str(excinfo.value)


def test_operating_note_parsed_and_trimmed() -> None:
    (agency,) = parse_agencies(entry(operating_note="  Confirmed running 2026-06.  "))
    assert agency.operating_note == "Confirmed running 2026-06."


def test_operating_note_defaults_empty() -> None:
    (agency,) = parse_agencies(VALID)
    assert agency.operating_note == ""


def test_fare_free_defaults_false_and_parses() -> None:
    (default_agency,) = parse_agencies(VALID)
    assert default_agency.fare_free is False
    (agency,) = parse_agencies(entry(fare_free=True))
    assert agency.fare_free is True


def test_fare_free_must_be_boolean() -> None:
    with pytest.raises(AgencyConfigError, match="fare_free must be true or false"):
        parse_agencies(entry(fare_free="yes"))


def test_mdb_id_parsed() -> None:
    (agency,) = parse_agencies(entry(mdb_id="777"))
    assert agency.mdb_id == "777"


def test_feed_identity_fields_parse_with_conservative_defaults() -> None:
    (default_agency,) = parse_agencies(VALID)
    assert default_agency.organization_key == "demo"
    assert default_agency.feed_status == "active"
    assert default_agency.is_official is None
    assert default_agency.is_canonical_feed is True

    raw = {
        "agencies": [
            {
                **VALID_ENTRY,
                "id": "canonical",
                "organization_id": "demo-transit",
                "feed_variant": "bus",
                "is_official": True,
            },
            {
                **VALID_ENTRY,
                "id": "legacy",
                "alias_of": "canonical",
                "feed_status": "deprecated",
            },
        ]
    }
    canonical, legacy = parse_agencies(raw)
    assert canonical.organization_key == "demo-transit"
    assert canonical.feed_variant == "bus"
    assert canonical.is_official is True
    assert legacy.alias_of == "canonical"
    assert legacy.is_canonical_feed is False


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        (entry(feed_status="retired"), "feed_status must be one of"),
        (entry(is_official="yes"), "is_official must be true or false"),
        (entry(organization_id="Bad Name"), "organization_id must be a lowercase slug"),
        (entry(alias_of="demo"), "alias_of cannot point to the same entry"),
        (entry(alias_of="missing"), "alias_of references unknown id"),
    ],
)
def test_invalid_feed_identity_fields_fail(raw: object, message: str) -> None:
    with pytest.raises(AgencyConfigError, match=message):
        parse_agencies(raw)


def test_alias_cycles_are_rejected() -> None:
    raw = {
        "agencies": [
            {**VALID_ENTRY, "id": "a", "alias_of": "b"},
            {**VALID_ENTRY, "id": "b", "alias_of": "a"},
        ]
    }
    with pytest.raises(AgencyConfigError, match="alias_of contains a cycle"):
        parse_agencies(raw)


def test_country_typo_fails_with_supported_list() -> None:
    import pytest

    from scorecard_pipeline.agencies import AgencyConfigError, parse_agencies

    raw = {
        "agencies": [
            {"id": "x", "name": "X", "static_gtfs_url": "https://ex.org/g.zip", "country": "UU"}
        ]
    }
    with pytest.raises(AgencyConfigError, match="country must be one of"):
        parse_agencies(raw)


def test_ntd_note_parses_and_defaults_empty() -> None:
    from scorecard_pipeline.agencies import parse_agencies

    raw = {
        "agencies": [
            {
                "id": "x",
                "name": "X",
                "static_gtfs_url": "https://ex.org/g.zip",
                "ntd_note": "Holds an FTA technical-assistance waiver for RY2026.",
            },
            {"id": "y", "name": "Y", "static_gtfs_url": "https://ex.org/h.zip"},
        ]
    }
    a, b = parse_agencies(raw)
    assert a.ntd_note.startswith("Holds an FTA")
    assert b.ntd_note == ""


# ---- the sharded registry (FIX-12): agencies.yaml + registry/<country>/<state> ----


def _write(root: Path, rel: str, entries: list[dict[str, object]]) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump({"agencies": entries}))


def test_registry_shards_merge_with_the_intake_file(isolated_repo_root: Path) -> None:
    _write(isolated_repo_root, "agencies.yaml", [dict(VALID_ENTRY)])
    _write(
        isolated_repo_root,
        "registry/us/california.yaml",
        [{**VALID_ENTRY, "id": "davis", "state": "California"}],
    )
    _write(
        isolated_repo_root,
        "registry/ca/ontario.yaml",
        [{**VALID_ENTRY, "id": "barrie", "country": "CA", "state": "Ontario"}],
    )
    load_agencies()
    assert set(AGENCIES) == {"demo", "davis", "barrie"}
    assert AGENCIES["davis"].state == "California"


def test_duplicate_id_across_files_names_both_sources(isolated_repo_root: Path) -> None:
    _write(isolated_repo_root, "agencies.yaml", [dict(VALID_ENTRY)])
    _write(isolated_repo_root, "registry/us/iowa.yaml", [dict(VALID_ENTRY)])
    with pytest.raises(AgencyConfigError) as excinfo:
        load_agencies()
    assert "agencies.yaml" in str(excinfo.value)
    assert "registry/us/iowa.yaml" in str(excinfo.value)


def test_a_malformed_shard_is_named_in_the_error(isolated_repo_root: Path) -> None:
    _write(isolated_repo_root, "agencies.yaml", [dict(VALID_ENTRY)])
    _write(isolated_repo_root, "registry/us/ohio.yaml", [{**VALID_ENTRY, "id": "Bad Slug!"}])
    with pytest.raises(AgencyConfigError) as excinfo:
        load_agencies()
    assert "registry/us/ohio.yaml" in str(excinfo.value)
    assert "lowercase slug" in str(excinfo.value)


def test_an_alias_may_point_into_another_shard(isolated_repo_root: Path) -> None:
    _write(isolated_repo_root, "agencies.yaml", [{**VALID_ENTRY, "alias_of": "davis"}])
    _write(
        isolated_repo_root,
        "registry/us/california.yaml",
        [{**VALID_ENTRY, "id": "davis", "state": "California"}],
    )
    load_agencies()
    assert AGENCIES["demo"].alias_of == "davis"


def test_an_empty_intake_file_is_fine_when_shards_carry_the_registry(
    isolated_repo_root: Path,
) -> None:
    _write(isolated_repo_root, "agencies.yaml", [])
    _write(isolated_repo_root, "registry/us/iowa.yaml", [dict(VALID_ENTRY)])
    load_agencies()
    assert set(AGENCIES) == {"demo"}


def test_an_entirely_empty_registry_still_fails(isolated_repo_root: Path) -> None:
    _write(isolated_repo_root, "agencies.yaml", [])
    with pytest.raises(AgencyConfigError, match="lists no agencies"):
        load_agencies()
