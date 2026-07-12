"""Tests for the agencies.yaml registry loader."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scorecard_pipeline.agencies import (
    AgencyConfigError,
    load_agencies,
    parse_agencies,
    read_agencies,
)
from scorecard_pipeline.config import AGENCIES
from scorecard_pipeline.jurisdictions import JURISDICTIONS
from scorecard_pipeline.location import SUPPORTED_COUNTRY_CODES

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


def test_repo_registry_is_valid_and_lists_pilots() -> None:
    agencies = parse_agencies(yaml.safe_load(REPO_YAML.read_text()))
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


def test_iso_subdivision_parses_and_legacy_us_state_derives_it() -> None:
    (canadian,) = parse_agencies(
        entry(country="ca", subdivision_code="ca-on", subdivision_name="Ontario")
    )
    assert canadian.subdivision_code == "CA-ON"
    assert canadian.subdivision_name == "Ontario"
    assert canadian.state == ""

    (legacy_us,) = parse_agencies(entry(state="California"))
    assert legacy_us.subdivision_code == "US-CA"
    assert legacy_us.subdivision_name == "California"
    assert legacy_us.state == "California"


def test_subdivision_must_match_country_and_legacy_state() -> None:
    with pytest.raises(AgencyConfigError, match="country prefix"):
        parse_agencies(entry(country="CA", subdivision_code="US-CA"))
    with pytest.raises(AgencyConfigError, match="state conflicts"):
        parse_agencies(
            entry(
                state="California",
                subdivision_code="US-NY",
                subdivision_name="New York",
            )
        )
    with pytest.raises(AgencyConfigError, match="state is a deprecated US-only field"):
        parse_agencies(entry(country="CA", state="Ontario"))


def test_country_rejects_non_iso_code() -> None:
    with pytest.raises(AgencyConfigError, match="country must be one of"):
        parse_agencies(entry(country="Canada"))


def test_agency_country_allowlist_comes_from_jurisdiction_config() -> None:
    assert frozenset(JURISDICTIONS.countries) == SUPPORTED_COUNTRY_CODES
    with pytest.raises(AgencyConfigError, match=r"add it to jurisdictions[.]yaml"):
        parse_agencies(entry(country="GB", subdivision_code="GB-ENG", subdivision_name="England"))


def test_fresh_process_activates_a_country_from_configuration_only(tmp_path: Path) -> None:
    (tmp_path / "jurisdictions.yaml").write_text(
        yaml.safe_dump(
            {
                "countries": {
                    "US": {"name": "United States", "subdivisions": {}},
                    "GB": {
                        "name": "United Kingdom",
                        "subdivisions": {"GB-ENG": "England"},
                    },
                }
            },
            sort_keys=False,
        )
    )
    (tmp_path / "agencies.yaml").write_text(
        yaml.safe_dump(
            {
                "agencies": [
                    {
                        "id": "example-gb",
                        "name": "Example GB Transit",
                        "static_gtfs_url": "https://example.org/gtfs.zip",
                        "country": "GB",
                        "subdivision_code": "GB-ENG",
                        "subdivision_name": "England",
                    }
                ]
            },
            sort_keys=False,
        )
    )
    env = os.environ.copy()
    env["SCORECARD_ROOT"] = str(tmp_path)
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from scorecard_pipeline.agencies import read_agencies; "
            "a = read_agencies()[0]; print(a.country, a.subdivision_code, a.subdivision_name)",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.stdout.strip() == "GB GB-ENG England"


def test_repo_registry_includes_canada_pilot() -> None:
    agencies = parse_agencies(yaml.safe_load(REPO_YAML.read_text()))
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


def test_default_loader_uses_legacy_file_when_manifest_is_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "agencies.yaml").write_text(yaml.safe_dump(VALID))
    monkeypatch.setenv("SCORECARD_ROOT", str(root))

    load_agencies()

    assert list(AGENCIES) == ["demo"]


def test_read_agencies_uses_legacy_file_without_mutating_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "agencies.yaml").write_text(yaml.safe_dump(VALID))
    monkeypatch.setenv("SCORECARD_ROOT", str(root))
    AGENCIES["existing"] = object()  # type: ignore[assignment]

    agencies = read_agencies()

    assert [agency.id for agency in agencies] == ["demo"]
    assert list(AGENCIES) == ["existing"]


def _write_registry_shard(root: Path, relative: str, agencies: list[dict[str, object]]) -> None:
    shard = root / relative
    shard.parent.mkdir(parents=True, exist_ok=True)
    shard.write_text(yaml.safe_dump({"agencies": agencies}))


def test_manifest_loads_shards_in_listed_order_and_allows_cross_shard_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    _write_registry_shard(root, "registry/CA/on.yaml", [{**VALID_ENTRY, "id": "second"}])
    _write_registry_shard(
        root,
        "registry/US/ca.yaml",
        [{**VALID_ENTRY, "id": "first", "alias_of": "second"}],
    )
    (root / "registry/index.yaml").write_text(
        yaml.safe_dump({"shards": ["registry/US/ca.yaml", "registry/CA/on.yaml"]})
    )
    monkeypatch.setenv("SCORECARD_ROOT", str(root))

    load_agencies()

    assert list(AGENCIES) == ["first", "second"]
    assert AGENCIES["first"].alias_of == "second"


def test_read_agencies_uses_manifest_without_mutating_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    _write_registry_shard(root, "registry/only.yaml", [VALID_ENTRY])
    (root / "registry/index.yaml").write_text(yaml.safe_dump({"shards": ["registry/only.yaml"]}))
    monkeypatch.setenv("SCORECARD_ROOT", str(root))
    AGENCIES["existing"] = object()  # type: ignore[assignment]

    agencies = read_agencies()

    assert [agency.id for agency in agencies] == ["demo"]
    assert list(AGENCIES) == ["existing"]


def test_manifest_rejects_duplicate_ids_across_shards_and_names_second_shard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    _write_registry_shard(root, "registry/a.yaml", [VALID_ENTRY])
    _write_registry_shard(root, "registry/b.yaml", [VALID_ENTRY])
    (root / "registry/index.yaml").write_text(
        yaml.safe_dump({"shards": ["registry/a.yaml", "registry/b.yaml"]})
    )
    monkeypatch.setenv("SCORECARD_ROOT", str(root))

    with pytest.raises(AgencyConfigError, match=r"registry/b\.yaml.*duplicate id"):
        load_agencies()


def test_manifest_failure_preserves_previously_loaded_registry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    valid_path = tmp_path / "valid.yaml"
    valid_path.write_text(yaml.safe_dump(VALID))
    load_agencies(valid_path)
    root = tmp_path / "repo"
    broken = dict(VALID_ENTRY)
    broken["name"] = ""
    _write_registry_shard(root, "registry/broken.yaml", [broken])
    (root / "registry/index.yaml").write_text(yaml.safe_dump({"shards": ["registry/broken.yaml"]}))
    monkeypatch.setenv("SCORECARD_ROOT", str(root))

    with pytest.raises(AgencyConfigError, match=r"registry/broken\.yaml.*name is required"):
        load_agencies()

    assert set(AGENCIES) == {"demo"}


def test_manifest_alias_chain_missing_target_names_owning_shard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    _write_registry_shard(
        root,
        "registry/a.yaml",
        [{**VALID_ENTRY, "id": "first", "alias_of": "second"}],
    )
    _write_registry_shard(
        root,
        "registry/b.yaml",
        [{**VALID_ENTRY, "id": "second", "alias_of": "missing"}],
    )
    (root / "registry/index.yaml").write_text(
        yaml.safe_dump({"shards": ["registry/a.yaml", "registry/b.yaml"]})
    )
    monkeypatch.setenv("SCORECARD_ROOT", str(root))

    with pytest.raises(AgencyConfigError, match=r"registry/b\.yaml.*unknown id 'missing'"):
        load_agencies()


def test_default_loader_rejects_ambiguous_and_partial_migrations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    registry = root / "registry"
    registry.mkdir(parents=True)
    (root / "agencies.yaml").write_text(yaml.safe_dump(VALID))
    monkeypatch.setenv("SCORECARD_ROOT", str(root))

    with pytest.raises(AgencyConfigError, match="partial agency registry migration"):
        load_agencies()

    (registry / "index.yaml").write_text(yaml.safe_dump({"shards": ["registry/a.yaml"]}))
    with pytest.raises(AgencyConfigError, match="ambiguous agency registry"):
        load_agencies()


@pytest.mark.parametrize(
    ("manifest", "message"),
    [
        ({"shards": []}, "lists no registry shards"),
        ({"shards": ["../outside.yaml"]}, "stay within the repository"),
        ({"shards": ["agencies.yaml"]}, "stay within the registry directory"),
        ({"shards": ["registry/missing.yaml"]}, "shard not found"),
        ({"shards": ["registry/a.yaml", "registry/a.yaml"]}, "duplicate path"),
        ({"shards": [7]}, "path must be a non-empty string"),
    ],
)
def test_manifest_rejects_partial_or_unsafe_lists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest: object,
    message: str,
) -> None:
    root = tmp_path / "repo"
    (root / "registry").mkdir(parents=True)
    _write_registry_shard(root, "registry/a.yaml", [VALID_ENTRY])
    (root / "registry/index.yaml").write_text(yaml.safe_dump(manifest))
    monkeypatch.setenv("SCORECARD_ROOT", str(root))

    with pytest.raises(AgencyConfigError, match=message):
        load_agencies()


def test_manifest_rejects_an_unlisted_shard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    _write_registry_shard(root, "registry/listed.yaml", [VALID_ENTRY])
    _write_registry_shard(root, "registry/unlisted.yml", [{**VALID_ENTRY, "id": "other"}])
    (root / "registry/index.yaml").write_text(yaml.safe_dump({"shards": ["registry/listed.yaml"]}))
    monkeypatch.setenv("SCORECARD_ROOT", str(root))

    with pytest.raises(AgencyConfigError, match=r"unlisted registry shard.*unlisted\.yml"):
        load_agencies()


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
