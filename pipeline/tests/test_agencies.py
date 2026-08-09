"""Tests for the legacy and manifest-backed agency registry loaders."""

from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from scorecard_pipeline.agencies import (
    AgencyConfigError,
    load_agencies,
    parse_agencies,
    read_agencies,
    registry_paths,
)
from scorecard_pipeline.config import AGENCIES
from scorecard_pipeline.global_coverage import EUROPE_BETA_COUNTRY_CODES
from scorecard_pipeline.jurisdictions import JURISDICTIONS
from scorecard_pipeline.location import SUPPORTED_COUNTRY_CODES

REPO_ROOT = Path(__file__).resolve().parents[2]

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
    assert agency.reuse_evidence is None


VALID_REUSE_EVIDENCE: dict[str, object] = {
    "decision": "approved",
    "source_kind": "official_portal",
    "provider_source_url": "https://data.example.org/datasets/demo",
    "terms_url": "https://data.example.org/terms",
    "scope": ["gtfs_schedule"],
    "attribution": "  Demo Transit Authority  ",
    "reviewed_by": "  Registry curator  ",
    "reviewed_on": "2026-07-16",
    "identity_reviewed": True,
}


def test_reuse_evidence_parses_as_frozen_reviewed_record() -> None:
    (agency,) = parse_agencies(entry(reuse_evidence=VALID_REUSE_EVIDENCE))
    evidence = agency.reuse_evidence

    assert evidence is not None
    assert evidence.decision == "approved"
    assert evidence.source_kind == "official_portal"
    assert evidence.provider_source_url == "https://data.example.org/datasets/demo"
    assert evidence.terms_url == "https://data.example.org/terms"
    assert evidence.scope == ("gtfs_schedule",)
    assert evidence.attribution == "Demo Transit Authority"
    assert evidence.reviewed_by == "Registry curator"
    assert evidence.reviewed_on == "2026-07-16"
    assert evidence.identity_reviewed is True
    with pytest.raises(FrozenInstanceError):
        evidence.reviewed_by = "Someone else"  # type: ignore[misc]


def test_reuse_evidence_review_date_cannot_be_in_the_future(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline import agencies as agency_config

    monkeypatch.setattr(agency_config, "_today", lambda: dt.date(2026, 7, 16))

    parse_agencies(entry(reuse_evidence={**VALID_REUSE_EVIDENCE, "reviewed_on": "2026-07-16"}))
    with pytest.raises(AgencyConfigError, match="reviewed_on must not be in the future"):
        parse_agencies(entry(reuse_evidence={**VALID_REUSE_EVIDENCE, "reviewed_on": "2026-07-17"}))


def test_legacy_provenance_never_implies_reuse_approval() -> None:
    (agency,) = parse_agencies(
        entry(
            license_note="CC BY 4.0",
            is_official=True,
            mdb_id="mdb-1234",
        )
    )

    assert agency.reuse_evidence is None


@pytest.mark.parametrize(
    ("reuse_evidence", "message"),
    [
        (None, "reuse_evidence must be a mapping"),
        ({}, "reuse_evidence missing required field"),
        ({**VALID_REUSE_EVIDENCE, "extra": True}, "unknown reuse_evidence field"),
        ({**VALID_REUSE_EVIDENCE, "decision": "pending"}, "decision must be exactly"),
        ({**VALID_REUSE_EVIDENCE, "decision": " approved "}, "decision must be exactly"),
        ({**VALID_REUSE_EVIDENCE, "source_kind": "catalog"}, "source_kind must be one of"),
        ({**VALID_REUSE_EVIDENCE, "source_kind": []}, "source_kind must be one of"),
        (
            {**VALID_REUSE_EVIDENCE, "provider_source_url": "ftp://example.org/feed"},
            "provider_source_url must be an http(s) URL",
        ),
        (
            {**VALID_REUSE_EVIDENCE, "terms_url": "example.org/terms"},
            "terms_url must be an http(s) URL",
        ),
        ({**VALID_REUSE_EVIDENCE, "scope": []}, "scope must be a non-empty list"),
        ({**VALID_REUSE_EVIDENCE, "scope": "gtfs_schedule"}, "scope must be a non-empty list"),
        ({**VALID_REUSE_EVIDENCE, "scope": [1]}, "scope entries must be strings"),
        (
            {**VALID_REUSE_EVIDENCE, "scope": ["gtfs_schedule", "gtfs_schedule"]},
            "scope entries must be unique",
        ),
        (
            {**VALID_REUSE_EVIDENCE, "scope": ["gtfs_realtime"]},
            "scope contains unknown value",
        ),
        ({**VALID_REUSE_EVIDENCE, "attribution": "  "}, "attribution must be a non-empty"),
        ({**VALID_REUSE_EVIDENCE, "reviewed_by": ""}, "reviewed_by must be a non-empty"),
        (
            {**VALID_REUSE_EVIDENCE, "reviewed_on": "2026-7-16"},
            "reviewed_on must be an ISO date",
        ),
        (
            {**VALID_REUSE_EVIDENCE, "reviewed_on": "2026-02-30"},
            "reviewed_on must be a valid ISO date",
        ),
        (
            {**VALID_REUSE_EVIDENCE, "identity_reviewed": "yes"},
            "identity_reviewed must be true or false",
        ),
    ],
)
def test_invalid_reuse_evidence_fails_closed(reuse_evidence: object, message: str) -> None:
    with pytest.raises(AgencyConfigError) as excinfo:
        parse_agencies(entry(reuse_evidence=reuse_evidence))
    assert message in str(excinfo.value)


def test_repo_registry_is_valid_and_lists_pilots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    agencies = read_agencies()
    ids = {a.id for a in agencies}
    assert {"unitrans", "yolobus"} <= ids
    yolobus = next(a for a in agencies if a.id == "yolobus")
    assert set(yolobus.rt_urls) == {"trip_updates", "vehicle_positions", "service_alerts"}
    assert yolobus.ntd_id == "90090"  # FTA-assigned NTD ID
    unitrans = next(a for a in agencies if a.id == "unitrans")
    assert unitrans.rt_note  # key-gated realtime keeps its neutral note
    assert unitrans.ntd_id == "90142"


def test_repo_registry_matches_documented_feed_record_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    agencies = read_agencies()
    european = [agency for agency in agencies if agency.country in EUROPE_BETA_COUNTRY_CODES]

    assert len(agencies) == 2_185
    assert len(european) == 528
    assert len({agency.country for agency in european}) == 26


def test_repo_registry_carries_reviewed_coverage_recovery_updates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    by_id = {agency.id: agency for agency in read_agencies()}

    assert by_id["ovapi-netherlands"].large_feed is True
    assert by_id["cache-valley-transit-district"].static_gtfs_url == (
        "https://www.mycvtdbus.org/gtfs"
    )
    assert by_id["cache-valley-transit-district"].mdb_id == "ntd-80028"
    assert by_id["greenville-transit-authority-greenlink"].static_gtfs_url == (
        "https://gtfs.greenlink.cadavl.com/GTA/GTFS/GTFS_GTA.zip"
    )
    assert by_id["greenville-transit-authority-greenlink"].mdb_id == "tld-490"
    assert by_id["jacksonville-transportation-authority-jta"].static_gtfs_url == (
        "https://ride.jtafla.com/gtfs-archive/gtfs.zip"
    )
    assert by_id["jacksonville-transportation-authority-jta"].mdb_id == "tld-764"


def test_repo_registry_includes_france_pan_and_new_country_code_wave(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    by_id = {agency.id: agency for agency in read_agencies()}
    france_pan = [agency for agency in by_id.values() if agency.id.startswith("fr-pan-")]

    assert len(france_pan) == 136
    assert {agency.country for agency in france_pan} == {"FR"}
    assert {agency.subdivision_code for agency in france_pan} >= {
        "FR-20R",
        "FR-973",
        "FR-ARA",
        "FR-BRE",
        "FR-GES",
        "FR-NAQ",
        "FR-PAC",
    }
    for agency in france_pan:
        assert agency.is_official is True
        assert agency.reuse_evidence is not None
        assert agency.reuse_evidence.source_kind == "official_portal"
        assert agency.reuse_evidence.provider_source_url.startswith(
            "https://transport.data.gouv.fr/datasets/"
        )
        assert agency.reuse_evidence.reviewed_on == "2026-07-23"
        assert agency.reuse_evidence.identity_reviewed is True

    taneo = by_id["nc-taneo-82780"]
    assert taneo.country == "NC"
    assert taneo.reuse_evidence is not None
    assert taneo.reuse_evidence.source_kind == "official_portal"

    ati = by_id["puerto-rico-ati"]
    assert ati.country == "PR"
    assert ati.reuse_evidence is not None
    assert ati.reuse_evidence.source_kind == "official_portal"

    mwasalat = by_id["mwasalat-oman"]
    assert mwasalat.country == "OM"
    assert mwasalat.reuse_evidence is not None
    assert mwasalat.reuse_evidence.source_kind == "provider"


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


def test_large_feed_defaults_false_and_parses_when_set() -> None:
    (default_agency,) = parse_agencies(VALID)
    assert default_agency.large_feed is False
    (large,) = parse_agencies(entry(large_feed=True))
    assert large.large_feed is True


def test_large_feed_must_be_boolean() -> None:
    with pytest.raises(AgencyConfigError, match="large_feed must be true or false"):
        parse_agencies(entry(large_feed="yes"))


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
    with pytest.raises(AgencyConfigError, match="assigned ISO 3166-1"):
        parse_agencies(entry(country="Canada"))


def test_agency_country_validation_uses_the_global_iso_vocabulary() -> None:
    assert frozenset(JURISDICTIONS.countries) == SUPPORTED_COUNTRY_CODES
    assert len(SUPPORTED_COUNTRY_CODES) == 249
    (british,) = parse_agencies(
        entry(country="GB", subdivision_code="GB-ENG", subdivision_name="England")
    )
    assert (british.country, british.subdivision_code) == ("GB", "GB-ENG")
    with pytest.raises(AgencyConfigError, match="assigned ISO 3166-1"):
        parse_agencies(entry(country="XK"))


def test_fresh_process_accepts_a_global_country_without_activation(tmp_path: Path) -> None:
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


def test_ambiguous_subdivision_name_requires_an_iso_code() -> None:
    with pytest.raises(AgencyConfigError, match="matches more than one ISO subdivision"):
        parse_agencies(entry(country="AZ", subdivision_name="Lənkəran"))
    (agency,) = parse_agencies(
        entry(country="AZ", subdivision_code="AZ-LA", subdivision_name="Lənkəran")
    )
    assert agency.subdivision_code == "AZ-LA"


def test_subdivision_name_typo_is_rejected_even_when_the_code_is_valid() -> None:
    with pytest.raises(AgencyConfigError, match="subdivision_code and subdivision_name disagree"):
        parse_agencies(entry(country="GB", subdivision_code="GB-ENG", subdivision_name="Englnd"))


def test_repo_registry_includes_canada_pilot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    agencies = read_agencies()
    by_id = {a.id: a for a in agencies}
    assert {"whitehorse-transit", "barrie-transit", "london-transit-commission"} <= set(by_id)
    assert all(by_id[i].country == "CA" for i in ("whitehorse-transit", "barrie-transit"))
    assert by_id["unitrans"].country == "US"  # US pilots keep the default


def test_repo_registry_includes_four_region_worldwide_cohort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    agencies = read_agencies()
    by_id = {agency.id: agency for agency in agencies}
    cohort = {
        "lbus-bernay": ("FR", "FR-NOR", "Normandie"),
        "basmy-kangar": ("MY", "MY-09", "Perlis"),
        "orbus-otago": ("NZ", "NZ-OTA", "Otago"),
        "mtop-uruguay-metropolitan": ("UY", "UY-MO", "Montevideo"),
    }

    assert cohort.keys() <= by_id.keys()
    for agency_id, location in cohort.items():
        agency = by_id[agency_id]
        assert (agency.country, agency.subdivision_code, agency.subdivision_name) == location
        assert agency.is_official is True
        assert agency.ntd_id == ""
        assert agency.ntd_note == ""


def test_repo_registry_includes_european_breadth_wave(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    by_id = {agency.id: agency for agency in read_agencies()}
    cohort = {
        "tec-wallonia": ("BE", "BE-WAL", "wallonne, Région", "1212", True),
        "swiss-demand-responsive-ski-plus": ("CH", "", "", "2053", True),
        "rejseplanen-denmark": ("DK", "", "", "1292", True),
        "tallinn-public-transport-tlt": ("EE", "EE-37", "Harjumaa", "3047", True),
        "metro-bilbao": ("ES", "ES-BI", "Bizkaia", "3052", True),
        "waltti-kotka": ("FI", "FI-09", "Kymenlaakso", "1127", True),
        "morebus": (
            "GB",
            "GB-BCP",
            "Bournemouth, Christchurch and Poole",
            "1943",
            None,
        ),
        "ztm-gdansk": ("PL", "PL-22", "Pomorskie", "2093", True),
        "transtejo-soflusa": ("PT", "PT-11", "Lisboa", "2921", True),
    }

    assert cohort.keys() <= by_id.keys()
    for agency_id, expected in cohort.items():
        agency = by_id[agency_id]
        actual = (
            agency.country,
            agency.subdivision_code,
            agency.subdivision_name,
            agency.mdb_id,
            agency.is_official,
        )
        assert actual == expected
        assert agency.reuse_evidence is not None
        assert agency.reuse_evidence.decision == "approved"
        assert agency.reuse_evidence.identity_reviewed is True

    assert by_id["swiss-demand-responsive-ski-plus"].service_type == "demand_response"
    assert len({by_id[agency_id].mdb_id for agency_id in cohort}) == len(cohort)
    assert len({by_id[agency_id].static_gtfs_url for agency_id in cohort}) == len(cohort)


def test_repo_registry_tracks_calitp_hosting_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    by_id = {agency.id: agency for agency in read_agencies()}

    assert (
        by_id["city-of-wasco"].static_gtfs_url
        == "https://gtfs.dds.dot.ca.gov/gtfs_files/WascoDialaRideFlex.zip"
    )
    assert by_id["city-of-wasco"].service_type == "demand_response"
    assert "stale and noncanonical" in by_id["city-of-wasco"].operating_note
    assert (
        by_id["clean-air-express"].static_gtfs_url
        == "https://cleanairexpress.com/wp-content/uploads/GTFS.zip"
    )


def test_worldwide_cohort_preserves_public_names_and_realtime_semantics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    agencies = read_agencies()
    by_id = {agency.id: agency for agency in agencies}

    bernay = by_id["lbus-bernay"]
    assert bernay.name == "Réseau urbain l'Bus (Bernay)"
    assert set(bernay.rt_urls) == {"trip_updates", "vehicle_positions", "service_alerts"}
    assert len(set(bernay.rt_urls.values())) == 1  # publisher's combined stream

    kangar = by_id["basmy-kangar"]
    assert kangar.name == "BAS.MY Kangar"
    assert set(kangar.rt_urls) == {"vehicle_positions"}

    otago = by_id["orbus-otago"]
    assert otago.name == "Orbus (Otago Regional Council)"
    assert otago.rt_urls == {}
    assert "no keyless public GTFS-Realtime endpoint" in otago.rt_note
    assert "Nothing here counts against the grade" in otago.rt_note

    uruguay = by_id["mtop-uruguay-metropolitan"]
    assert uruguay.name == "Servicios metropolitanos de ómnibus (MTOP Uruguay)"
    assert uruguay.rt_urls == {}


def test_repo_registry_includes_hong_kong_frequency_canary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    by_id = {agency.id: agency for agency in read_agencies()}

    agency = by_id["hong-kong-transport-department"]
    assert agency.country == "HK"
    assert agency.subdivision_code == ""
    assert agency.subdivision_name == ""
    assert agency.mdb_id == "1924"
    assert agency.is_official is True
    assert agency.static_gtfs_url == "https://static.data.gov.hk/td/pt-headway-en/gtfs.zip"
    assert agency.reuse_evidence is not None
    assert agency.reuse_evidence.decision == "approved"
    assert agency.reuse_evidence.identity_reviewed is True
    assert "frequencies.txt" in agency.operating_note
    assert "unusually distant horizon" in agency.operating_note


def test_repo_registry_includes_tasmania_official_aggregate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    by_id = {agency.id: agency for agency in read_agencies()}

    agency = by_id["tasmania-public-transport"]
    assert agency.country == "AU"
    assert agency.subdivision_code == "AU-TAS"
    assert agency.subdivision_name == "Tasmania"
    assert agency.is_official is True
    assert (
        agency.static_gtfs_url
        == "https://www.transport.tas.gov.au/__data/assets/file/0011/557615/tas_gtfs.zip"
    )
    assert agency.reuse_evidence is not None
    assert agency.reuse_evidence.decision == "approved"
    assert agency.reuse_evidence.provider_source_url.endswith("/public_transport/gtfs-data")
    assert agency.reuse_evidence.identity_reviewed is True
    assert "one feed record, not six agencies" in agency.operating_note


def test_repo_registry_includes_reactivated_basmy_town_feeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    by_id = {agency.id: agency for agency in read_agencies()}
    expected = {
        "basmy-alor-setar": ("MY-02", "Kedah", "mybas-alor-setar"),
        "basmy-kota-bharu": ("MY-03", "Kelantan", "mybas-kota-bharu"),
        "basmy-kuala-terengganu": (
            "MY-11",
            "Terengganu",
            "mybas-kuala-terengganu",
        ),
        "basmy-kuching": ("MY-13", "Sarawak", "mybas-kuching"),
    }

    for agency_id, (subdivision_code, subdivision_name, endpoint) in expected.items():
        agency = by_id[agency_id]
        assert agency.country == "MY"
        assert agency.subdivision_code == subdivision_code
        assert agency.subdivision_name == subdivision_name
        assert agency.is_official is True
        assert agency.static_gtfs_url.endswith(endpoint)
        assert agency.reuse_evidence is not None
        assert agency.reuse_evidence.decision == "approved"
        assert agency.reuse_evidence.identity_reviewed is True
        assert "service through 2026-12-31" in agency.operating_note


def test_repo_registry_includes_japan_five_loop_cohort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    by_id = {agency.id: agency for agency in read_agencies()}
    cohort = {
        "kamishihoro-autonomous-bus": ("JP-01", "Hokkaido", "kamishihorotown"),
        "konan-railway": ("JP-02", "Aomori", "hirosakicity"),
        "tsukubane-go": ("JP-08", "Ibaraki", "tsukubacity"),
        "awaji-jenova-line": ("JP-28", "Hyogo", "awajicity"),
        "hokushin-bus": ("JP-33", "Okayama", "hokushin-bus"),
    }

    for agency_id, (subdivision_code, subdivision_name, publisher) in cohort.items():
        agency = by_id[agency_id]
        assert agency.country == "JP"
        assert agency.subdivision_code == subdivision_code
        assert agency.subdivision_name == subdivision_name
        assert agency.is_official is True
        assert publisher in agency.static_gtfs_url
        assert agency.static_gtfs_url.endswith("files/feed.zip?rid=current")
        assert agency.reuse_evidence is not None
        assert agency.reuse_evidence.decision == "approved"
        assert agency.reuse_evidence.identity_reviewed is True
        assert agency.reuse_evidence.reviewed_on == "2026-07-23"


def test_repo_registry_includes_japan_operational_depth_cohort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    by_id = {agency.id: agency for agency in read_agencies()}
    cohort = {
        "jr-east-tsugaru-line-replacement-bus": ("JP-02", "Aomori", "jr-east-morioka"),
        "mizuho-choisoko-demand-transit": ("JP-13", "Tokyo", "mizuhotown"),
        "toyama-chitetsu-bus": ("JP-16", "Toyama", "chitetsu"),
        "toba-municipal-ferry": ("JP-24", "Mie", "tobacity"),
        "kochi-airport-shared-taxi": ("JP-39", "Kochi", "kochiap"),
    }

    for agency_id, (subdivision_code, subdivision_name, publisher) in cohort.items():
        agency = by_id[agency_id]
        assert agency.country == "JP"
        assert agency.subdivision_code == subdivision_code
        assert agency.subdivision_name == subdivision_name
        assert agency.is_official is True
        assert publisher in agency.static_gtfs_url
        assert agency.static_gtfs_url.endswith("files/feed.zip?rid=current")
        assert agency.reuse_evidence is not None
        assert agency.reuse_evidence.decision == "approved"
        assert agency.reuse_evidence.identity_reviewed is True
        assert agency.reuse_evidence.reviewed_on == "2026-07-23"

    assert by_id["mizuho-choisoko-demand-transit"].service_type == "demand_response"
    assert by_id["kochi-airport-shared-taxi"].service_type == "demand_response"
    assert set(by_id["toyama-chitetsu-bus"].rt_urls) == {
        "trip_updates",
        "vehicle_positions",
    }


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
    assert registry_paths(root) == [root.resolve() / "agencies.yaml"]


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


def test_default_loader_accepts_a_relative_repository_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "agencies.yaml").write_text(yaml.safe_dump(VALID))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SCORECARD_ROOT", "repo")

    assert [agency.id for agency in read_agencies()] == ["demo"]


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
    assert registry_paths(root) == [
        root.resolve() / "registry/US/ca.yaml",
        root.resolve() / "registry/CA/on.yaml",
    ]


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


@pytest.mark.parametrize("terminal_status", ["deprecated", "inactive", "development"])
def test_alias_chain_must_terminate_at_an_active_canonical_feed(
    terminal_status: str,
) -> None:
    raw = {
        "agencies": [
            {**VALID_ENTRY, "id": "legacy", "alias_of": "intermediate"},
            {**VALID_ENTRY, "id": "intermediate", "alias_of": "terminal"},
            {**VALID_ENTRY, "id": "terminal", "feed_status": terminal_status},
        ]
    }

    with pytest.raises(
        AgencyConfigError,
        match="alias_of chain must terminate at an active canonical feed",
    ):
        parse_agencies(raw)


def test_country_typo_fails_against_assigned_iso_codes() -> None:
    import pytest

    from scorecard_pipeline.agencies import AgencyConfigError, parse_agencies

    raw = {
        "agencies": [
            {"id": "x", "name": "X", "static_gtfs_url": "https://ex.org/g.zip", "country": "UU"}
        ]
    }
    with pytest.raises(AgencyConfigError, match="assigned ISO 3166-1"):
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
