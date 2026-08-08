"""The California / Caltrans directory crosswalk and the figures it reports."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scorecard_pipeline.caltrans_crosswalk import (
    Crosswalk,
    CrosswalkRecord,
    crosswalk_path,
    load_crosswalk,
    reconciliation,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
COMMITTED = REPO_ROOT / "data" / "california-caltrans-crosswalk.yaml"
SNAPSHOT = REPO_ROOT / "data" / "caltrans-report-directory.json"


def _payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "directory_source": "https://reports.example.gov/2026/06",
        "directory_month": "2026-06",
        "directory_retrieved_on": "2026-08-07",
        "directory_agencies": 4,
        "records": [
            {
                "id": "alpha",
                "name": "Alpha Transit",
                "status": "matched",
                "method": "feed_url",
                "evidence": "their report lists this feed URL",
                "caltrans_id": 1,
                "caltrans_name": "City of Alpha",
            },
            {
                "id": "alpha-mirror",
                "name": "Alpha Transit",
                "status": "matched",
                "method": "org_name",
                "evidence": "the organization names agree",
                "caltrans_id": 1,
                "caltrans_name": "City of Alpha",
            },
            {
                "id": "bravo",
                "name": "Bravo Shuttle",
                "status": "uncertain",
                "method": "name_overlap",
                "evidence": "only a partial name overlap",
            },
            {
                "id": "charlie",
                "name": "Charlie Trolley",
                "status": "absent",
                "method": "no_candidate",
                "evidence": "no organization shares a name",
            },
        ],
        "directory_only": [{"caltrans_id": 9, "name": "City of Delta"}],
    }
    base.update(overrides)
    return base


def _write(tmp_path: Path, payload: dict[str, object]) -> Path:
    target = tmp_path / "crosswalk.yaml"
    target.write_text(yaml.safe_dump(payload, sort_keys=False))
    return target


def test_load_reads_the_snapshot_provenance_and_every_record(tmp_path: Path) -> None:
    crosswalk = load_crosswalk(_write(tmp_path, _payload()))
    assert crosswalk is not None
    assert crosswalk.directory_month == "2026-06"
    assert crosswalk.directory_retrieved_on == "2026-08-07"
    assert crosswalk.directory_agencies == 4
    assert len(crosswalk.records) == 4
    assert crosswalk.by_id()["alpha"].caltrans_name == "City of Alpha"
    assert crosswalk.directory_only[0]["name"] == "City of Delta"


def test_a_record_without_a_match_carries_no_directory_id(tmp_path: Path) -> None:
    crosswalk = load_crosswalk(_write(tmp_path, _payload()))
    assert crosswalk is not None
    assert crosswalk.by_id()["bravo"].caltrans_id is None
    assert crosswalk.by_id()["bravo"].caltrans_name == ""


def test_a_missing_file_is_not_an_error(tmp_path: Path) -> None:
    assert load_crosswalk(tmp_path / "absent.yaml") is None


@pytest.mark.parametrize("payload", ["", "[]", "records: []"])
def test_an_empty_or_wrongly_shaped_file_reads_as_no_crosswalk(
    tmp_path: Path, payload: str
) -> None:
    target = tmp_path / "crosswalk.yaml"
    target.write_text(payload)
    assert load_crosswalk(target) is None


def test_an_unknown_status_is_refused_rather_than_counted(tmp_path: Path) -> None:
    broken = _payload(
        records=[
            {
                "id": "alpha",
                "name": "Alpha Transit",
                "status": "probably",
                "method": "feed_url",
                "evidence": "their report lists this feed URL",
            }
        ]
    )
    with pytest.raises(ValueError, match="unknown crosswalk status"):
        load_crosswalk(_write(tmp_path, broken))


def test_a_record_falls_back_to_its_id_when_it_carries_no_name(tmp_path: Path) -> None:
    payload = _payload(
        records=[{"id": "nameless", "status": "absent", "method": "no_candidate", "evidence": ""}]
    )
    crosswalk = load_crosswalk(_write(tmp_path, payload))
    assert crosswalk is not None
    assert crosswalk.records[0].name == "nameless"


def test_reconciliation_counts_each_status_separately(tmp_path: Path) -> None:
    crosswalk = load_crosswalk(_write(tmp_path, _payload()))
    assert crosswalk is not None
    out = reconciliation(crosswalk, ["alpha", "alpha-mirror", "bravo", "charlie"])
    assert out["reconciled_records"] == 4
    assert out["matched_records"] == 2
    assert out["uncertain_records"] == 1
    assert out["absent_records"] == 1


def test_an_uncertain_match_is_never_reported_as_agreement(tmp_path: Path) -> None:
    crosswalk = load_crosswalk(_write(tmp_path, _payload()))
    assert crosswalk is not None
    out = reconciliation(crosswalk, ["bravo"])
    assert out["matched_records"] == 0
    assert out["uncertain_records"] == 1
    assert out["organizations_matched"] == 0


def test_two_feed_records_for_one_operator_count_as_one_organization(tmp_path: Path) -> None:
    crosswalk = load_crosswalk(_write(tmp_path, _payload()))
    assert crosswalk is not None
    out = reconciliation(crosswalk, ["alpha", "alpha-mirror"])
    assert out["matched_records"] == 2
    assert out["organizations_matched"] == 1


def test_members_absent_from_the_crosswalk_are_reported_not_dropped(tmp_path: Path) -> None:
    crosswalk = load_crosswalk(_write(tmp_path, _payload()))
    assert crosswalk is not None
    out = reconciliation(crosswalk, ["alpha", "not-in-the-crosswalk"])
    assert out["reconciled_records"] == 1
    assert out["unreconciled_records"] == 1


def test_reconciliation_carries_the_directory_provenance_through(tmp_path: Path) -> None:
    crosswalk = load_crosswalk(_write(tmp_path, _payload()))
    assert crosswalk is not None
    out = reconciliation(crosswalk, ["alpha"])
    assert out["directory_source"] == "https://reports.example.gov/2026/06"
    assert out["directory_month"] == "2026-06"
    assert out["directory_agencies"] == 4
    assert out["directory_only_agencies"] == 1


def test_crosswalk_path_sits_under_the_repository_data_directory() -> None:
    assert crosswalk_path().name == "california-caltrans-crosswalk.yaml"
    assert crosswalk_path().parent.name == "data"


def test_the_dataclasses_are_frozen_records() -> None:
    record = CrosswalkRecord("a", "A", "matched", "feed_url", "why", 1, "City of A")
    with pytest.raises(AttributeError):
        record.status = "absent"  # type: ignore[misc]
    crosswalk = Crosswalk("s", "2026-06", "2026-08-07", 1, (record,), ())
    with pytest.raises(AttributeError):
        crosswalk.directory_agencies = 2  # type: ignore[misc]


# --- the committed crosswalk itself ----------------------------------------


@pytest.mark.skipif(not COMMITTED.exists(), reason="no committed California crosswalk")
def test_the_committed_crosswalk_loads_and_every_match_names_a_real_agency() -> None:
    import json

    crosswalk = load_crosswalk(COMMITTED)
    assert crosswalk is not None
    directory = json.loads(SNAPSHOT.read_text())
    known = {a["caltrans_id"] for a in directory["agencies"]}
    assert crosswalk.directory_agencies == len(known)
    for record in crosswalk.records:
        if record.status == "matched":
            assert record.caltrans_id in known, record.agency_id
            assert record.evidence, record.agency_id
        else:
            assert record.caltrans_id is None, record.agency_id


@pytest.mark.skipif(not COMMITTED.exists(), reason="no committed California crosswalk")
def test_every_committed_record_states_why_it_was_decided_that_way() -> None:
    crosswalk = load_crosswalk(COMMITTED)
    assert crosswalk is not None
    assert crosswalk.records
    for record in crosswalk.records:
        assert record.method, record.agency_id
        assert record.evidence, record.agency_id


@pytest.mark.skipif(not COMMITTED.exists(), reason="no committed California crosswalk")
def test_the_california_program_members_are_all_in_the_crosswalk() -> None:
    rollups = yaml.safe_load((REPO_ROOT / "rollups.yaml").read_text())["rollups"]
    members = next(r for r in rollups if r["id"] == "california")["members"]
    crosswalk = load_crosswalk(COMMITTED)
    assert crosswalk is not None
    known = crosswalk.by_id()
    missing = [member for member in members if member not in known]
    assert not missing, f"California page members with no crosswalk decision: {missing}"
