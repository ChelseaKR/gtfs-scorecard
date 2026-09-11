"""`scorecard retest`: a new export against an evidence packet's acceptance tests (#366)."""

from __future__ import annotations

import datetime as dt
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import cli
from scorecard_pipeline.evidence_packet import (
    acceptance_test_passes,
    build_evidence_packet,
    observe_notice,
)
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.retest import (
    ALL_CLEARED,
    CLEARED,
    NON_COMPARABLE,
    STILL_PRESENT,
    PacketError,
    build_retest_record,
    describe_source,
    render_retest_markdown,
    retest_exit_code,
    validate_packet,
)
from scorecard_pipeline.validate import NoticeGroup, ValidationReport

FIXTURE = Path(__file__).parent / "fixtures" / "unitrans_trimmed.zip"
HEADSIGN = "missing_trip_headsign"
WHEELCHAIR = "scorecard_wheelchair_boarding_unknown"


def _fix(rank: int, code: str, count: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "code": code,
        "count": count,
        "severity": "WARNING",
        "what": f"{count} instances of {code}.",
        "why": "Riders are affected.",
        "fix": "Correct the export.",
        "effort": "One setting.",
    }


def _artifact() -> dict[str, Any]:
    """Two findings in two measured categories, so per-category rules can be isolated."""
    return {
        "schema_version": "1.5",
        "snapshot_date": "2026-07-02",
        "generated_at": "2026-07-02T13:00:00+00:00",
        "rubric_version": "1.3",
        "scoring_profile": {"id": "gtfs-scorecard-1.3", "rubric_version": "1.3"},
        "validator_version": "8.0.1",
        "agency": {"id": "small-town", "name": "Small Town Transit"},
        "feed": {"static_url": "https://transit.example/gtfs.zip", "sha256": "a" * 64},
        "overall": {"grade": "C", "score": 74.2},
        "categories": {
            "correctness": {
                "status": "measured",
                "score": 80.0,
                "findings": [{"code": HEADSIGN, "count": 12}],
            },
            "completeness": {
                "status": "measured",
                "score": 60.0,
                "findings": [{"code": WHEELCHAIR, "count": 40}],
            },
        },
        "top_fixes": [_fix(1, WHEELCHAIR, 40), _fix(2, HEADSIGN, 12)],
    }


def _corrected() -> dict[str, Any]:
    """The republished export: new bytes, the same contract, both notices gone."""
    artifact = _artifact()
    artifact["snapshot_date"] = "2026-08-01"
    artifact["feed"]["sha256"] = "b" * 64
    for category in artifact["categories"].values():
        category["findings"] = []
    artifact["top_fixes"] = []
    return artifact


def _record(packet_source: dict[str, Any], retest: dict[str, Any]) -> dict[str, Any]:
    packet = validate_packet(build_evidence_packet(packet_source))
    return build_retest_record(packet, retest, retest_source="https://transit.example/new.zip")


def _verdicts(record: dict[str, Any]) -> dict[str, str]:
    return {entry["notice_code"]: entry["verdict"] for entry in record["findings"]}


# --- the negative control for the whole verb -------------------------------------------


def test_retesting_the_same_bytes_reports_every_finding_still_present() -> None:
    record = _record(_artifact(), _artifact())

    assert _verdicts(record) == {WHEELCHAIR: STILL_PRESENT, HEADSIGN: STILL_PRESENT}
    assert record["summary"][CLEARED] == 0
    assert record["same_bytes_as_baseline"] is True
    assert record["outcome"] == STILL_PRESENT
    assert retest_exit_code(record) == 1


def test_a_notice_raised_with_a_count_of_zero_is_still_present_not_cleared() -> None:
    """The shape that passed on unchanged bytes: "0 of 0 stops don't say ..."."""
    empty_table = _artifact()
    empty_table["categories"]["completeness"]["findings"] = [{"code": WHEELCHAIR, "count": 0}]
    empty_table["top_fixes"] = [_fix(1, WHEELCHAIR, 0)]

    record = _record(empty_table, deepcopy(empty_table))
    entry = record["findings"][0]
    assert entry["verdict"] == STILL_PRESENT
    assert entry["retest_instances"] == 0
    assert retest_exit_code(record) == 1

    acceptance = build_evidence_packet(empty_table)["work_items"][0]["acceptance_test"]
    assert not acceptance_test_passes(acceptance, deepcopy(empty_table))


def test_acceptance_still_passes_when_the_notice_is_gone() -> None:
    acceptance = build_evidence_packet(_artifact())["work_items"][0]["acceptance_test"]
    assert acceptance_test_passes(acceptance, _corrected())


def test_an_absent_notice_is_cleared() -> None:
    record = _record(_artifact(), _corrected())

    assert _verdicts(record) == {WHEELCHAIR: CLEARED, HEADSIGN: CLEARED}
    assert all(entry["retest_instances"] == 0 for entry in record["findings"])
    assert record["same_bytes_as_baseline"] is False
    assert record["outcome"] == ALL_CLEARED
    assert retest_exit_code(record) == 0


def test_a_notice_with_fewer_instances_is_still_present_with_its_count() -> None:
    partly = _corrected()
    partly["categories"]["completeness"]["findings"] = [{"code": WHEELCHAIR, "count": 3}]

    record = _record(_artifact(), partly)
    entry = next(e for e in record["findings"] if e["notice_code"] == WHEELCHAIR)
    assert (entry["verdict"], entry["baseline_instances"], entry["retest_instances"]) == (
        STILL_PRESENT,
        40,
        3,
    )


# --- comparability ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "mutate"),
    [
        ("validator_version", lambda a: a.update(validator_version="8.1.0")),
        ("rubric_version", lambda a: a.update(rubric_version="1.4")),
        (
            "scoring_profile_id",
            lambda a: a.update(scoring_profile={"id": "experimental", "rubric_version": "1.3"}),
        ),
        (
            "scoring_profile_rubric_version",
            lambda a: a.update(scoring_profile={"id": "gtfs-scorecard-1.3", "rubric_version": "9"}),
        ),
        (
            "reader_archive_profile",
            lambda a: a.update(fetch={"reader_archive_profile": "flat-single-root-v1"}),
        ),
    ],
)
def test_a_different_producer_contract_makes_every_finding_non_comparable(
    field: str, mutate: Any
) -> None:
    corrected = _corrected()
    mutate(corrected)

    record = _record(_artifact(), corrected)

    assert set(_verdicts(record).values()) == {NON_COMPARABLE}
    assert record["summary"][CLEARED] == 0
    assert [d["field"] for d in record["contract_comparison"]["differences"]] == [field]
    assert all(field in entry["reason"] for entry in record["findings"])
    assert retest_exit_code(record) == 2


def test_the_contract_reason_names_both_versions() -> None:
    corrected = _corrected()
    corrected["validator_version"] = "8.1.0"

    reason = _record(_artifact(), corrected)["findings"][0]["reason"]
    assert "validator_version 8.0.1 in the packet, 8.1.0 in the retest" in reason


def test_an_unmeasured_category_makes_only_its_own_finding_non_comparable() -> None:
    corrected = _corrected()
    corrected["categories"]["completeness"] = {"status": "not_yet_measured", "findings": []}

    record = _record(_artifact(), corrected)

    assert _verdicts(record) == {WHEELCHAIR: NON_COMPARABLE, HEADSIGN: CLEARED}
    wheelchair = next(e for e in record["findings"] if e["notice_code"] == WHEELCHAIR)
    assert wheelchair["reason"] == "the retest did not measure completeness"
    assert record["contract_comparison"]["measured_categories_removed"] == ["completeness"]
    assert record["contract_comparison"]["comparable"] is True
    assert retest_exit_code(record) == 2


def test_realtime_measured_only_in_the_baseline_does_not_block_other_findings() -> None:
    baseline = _artifact()
    baseline["categories"]["realtime"] = {"status": "measured", "score": 90.0, "findings": []}

    record = _record(baseline, _corrected())

    assert _verdicts(record) == {WHEELCHAIR: CLEARED, HEADSIGN: CLEARED}
    assert record["contract_comparison"]["measured_categories_removed"] == ["realtime"]
    assert retest_exit_code(record) == 0


def test_unreadable_findings_are_non_comparable_not_cleared() -> None:
    corrected = _corrected()
    corrected["categories"]["correctness"]["findings"] = [{"code": HEADSIGN, "count": "many"}]

    record = _record(_artifact(), corrected)
    headsign = next(e for e in record["findings"] if e["notice_code"] == HEADSIGN)
    assert headsign["verdict"] == NON_COMPARABLE
    assert "no readable count" in headsign["reason"]


def test_still_present_outranks_non_comparable_in_the_exit_code() -> None:
    mixed = _artifact()
    mixed["categories"]["completeness"] = {"status": "not_yet_measured", "findings": []}

    record = _record(_artifact(), mixed)

    assert _verdicts(record) == {WHEELCHAIR: NON_COMPARABLE, HEADSIGN: STILL_PRESENT}
    assert retest_exit_code(record) == 1


def test_a_finding_the_packet_could_not_place_is_non_comparable() -> None:
    orphan = _artifact()
    orphan["top_fixes"].append(_fix(3, "scorecard_unplaced", 5))

    record = _record(orphan, _corrected())
    entry = next(e for e in record["findings"] if e["notice_code"] == "scorecard_unplaced")
    assert entry["category"] is None
    assert entry["verdict"] == NON_COMPARABLE
    assert "does not name the category" in entry["reason"]


def test_observe_notice_separates_absent_from_counted_at_zero() -> None:
    measured = {"status": "measured", "findings": [{"code": "x", "count": 0}]}
    assert observe_notice(measured, "x") == observe_notice(measured, "x")
    observed = observe_notice(measured, "x")
    assert observed is not None
    assert (observed.present, observed.instances) == (True, 0)
    absent = observe_notice(measured, "y")
    assert absent is not None
    assert (absent.present, absent.instances) == (False, 0)
    twice = {
        "status": "measured",
        "findings": [{"code": "x", "count": 2}, {"code": "x", "count": 3}],
    }
    summed = observe_notice(twice, "x")
    assert summed is not None
    assert summed.instances == 5
    assert observe_notice({"status": "not_yet_measured", "findings": []}, "x") is None
    assert observe_notice({"status": "measured", "findings": "nope"}, "x") is None


# --- packet refusals -----------------------------------------------------------------------


def _packet() -> dict[str, Any]:
    return build_evidence_packet(_artifact())


def _break(path: tuple[Any, ...], value: Any) -> dict[str, Any]:
    packet = _packet()
    target: Any = packet
    for key in path[:-1]:
        target = target[key]
    if value is _DELETE:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return packet


_DELETE = object()


@pytest.mark.parametrize(
    ("packet", "message"),
    [
        (["not", "a", "packet"], "not a JSON object"),
        (_break(("schema_version",), "2.0"), "unsupported packet schema_version"),
        (_break(("packet_id",), ""), "no packet_id"),
        (_break(("agency",), _DELETE), "names no agency"),
        (_break(("baseline",), None), "no baseline block"),
        (_break(("baseline", "validator_version"), ""), "baseline producer contract is incomplete"),
        (_break(("work_items",), {}), "no work_items list"),
        (_break(("work_items",), []), "nothing to retest"),
        (_break(("work_items", 0), "x"), "work item 1 is not an object"),
        (_break(("work_items", 0, "acceptance_test"), _DELETE), "has no acceptance_test"),
        (_break(("work_items", 0, "acceptance_test", "notice_code"), ""), "names no notice code"),
        (_break(("work_items", 0, "notice_code"), "other"), "disagree"),
        (_break(("work_items", 0, "acceptance_test", "category"), 7), "is not a string"),
        (
            _break(("work_items", 0, "acceptance_test", "required_category_status"), "any"),
            "does not require a measured category",
        ),
        (
            _break(("work_items", 0, "acceptance_test", "expected_instances"), True),
            "not a non-negative integer",
        ),
        (
            _break(("work_items", 0, "acceptance_test", "expected_instances"), 3),
            "expects 3 instances",
        ),
        (
            _break(("work_items", 0, "acceptance_test", "reader_archive_profile"), ""),
            "producer contract is incomplete",
        ),
        (
            _break(("work_items", 0, "acceptance_test", "validator_version"), "7.0.0"),
            "different producer contract",
        ),
        (
            _break(("work_items", 0, "acceptance_test", "category"), "realtime"),
            "which the baseline did not measure",
        ),
    ],
)
def test_a_packet_that_cannot_be_retested_is_refused(packet: Any, message: str) -> None:
    with pytest.raises(PacketError, match=message):
        validate_packet(packet)


def test_the_record_builder_refuses_an_unvalidated_incomplete_baseline() -> None:
    packet = _break(("baseline", "validator_version"), "")
    with pytest.raises(PacketError, match="incomplete"):
        build_retest_record(packet, _corrected(), retest_source="x")


# --- the record ----------------------------------------------------------------------------


def test_the_record_carries_both_hashes_and_both_contracts() -> None:
    record = _record(_artifact(), _corrected())

    assert record["record_type"] == "gtfs-scorecard-retest"
    assert record["retest_date"] == "2026-08-01"
    assert record["packet"]["baseline_snapshot_date"] == "2026-07-02"
    assert record["baseline"]["feed_sha256"] == "a" * 64
    assert record["retest"]["feed_sha256"] == "b" * 64
    assert record["baseline"]["contract"] == record["retest"]["contract"]
    assert record["baseline"]["contract"]["validator_version"] == "8.0.1"
    assert record["baseline"]["contract"]["measured_categories"] == ["correctness", "completeness"]
    assert "not a closure receipt" in record["note"]


def test_the_record_is_deterministic() -> None:
    first = json.dumps(_record(_artifact(), _corrected()), sort_keys=True)
    second = json.dumps(_record(_artifact(), _corrected()), sort_keys=True)
    assert first == second


def test_an_unrecorded_hash_leaves_same_bytes_unknown() -> None:
    corrected = _corrected()
    del corrected["feed"]
    assert _record(_artifact(), corrected)["same_bytes_as_baseline"] is None


def test_a_local_feed_is_recorded_by_name_only() -> None:
    assert describe_source("https://transit.example/gtfs.zip") == "https://transit.example/gtfs.zip"
    assert describe_source("/home/someone/exports/corrected.zip") == "local file corrected.zip"


def test_markdown_names_each_verdict_and_why_a_finding_was_not_compared() -> None:
    mixed = _artifact()
    mixed["categories"]["completeness"] = {"status": "not_yet_measured", "findings": []}
    out = render_retest_markdown(_record(_artifact(), mixed))

    assert out.startswith("# GTFS retest: Small Town Transit\n")
    assert "**1 of 2 findings are still present.**" in out
    assert f"| `{HEADSIGN}` | correctness | 12 | 12 | Still present |" in out
    assert f"| `{WHEELCHAIR}` | completeness | 40 |  | Not comparable |" in out
    assert f"- `{WHEELCHAIR}`: the retest did not measure completeness." in out
    assert "same bytes" in out
    assert "not a closure receipt" in out


def test_markdown_for_a_clean_retest() -> None:
    out = render_retest_markdown(_record(_artifact(), _corrected()))
    assert "**All 2 findings in the packet are cleared.**" in out
    assert "same bytes" not in out
    assert "could not be compared" not in out


def test_markdown_for_a_contract_mismatch() -> None:
    corrected = _corrected()
    corrected["validator_version"] = "8.1.0"
    out = render_retest_markdown(_record(_artifact(), corrected))
    assert "**2 of 2 findings could not be compared.**" in out
    assert "| Validator | 8.0.1 | 8.1.0 |" in out


# --- the command ---------------------------------------------------------------------------


def _stub_scoring(monkeypatch: pytest.MonkeyPatch, *, validator: str, notices: int) -> None:
    fetched = FetchResult(
        agency_id="_adhoc",
        path=FIXTURE,
        url="https://example.test/gtfs.zip",
        fetched_date=dt.date(2026, 6, 11),
        sha256="ab" * 32,
        size_bytes=FIXTURE.stat().st_size,
        reused=False,
    )
    report = ValidationReport(
        validator_version=validator,
        notices=[NoticeGroup(code="route_short_name_too_long", severity="WARNING", total=notices)]
        if notices
        else [],
    )
    monkeypatch.setattr(cli, "fetch_static", lambda *a, **k: fetched)
    monkeypatch.setattr(cli, "run_validator", lambda *a, **k: Path("unused.json"))
    monkeypatch.setattr(cli, "parse_report", lambda *a, **k: report)


def _no_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli, "load_agencies", lambda *a, **k: pytest.fail("retest must not load the registry")
    )


def _packet_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _stub_scoring(monkeypatch, validator="9.9.9", notices=2)
    artifact = cli.run_adhoc("https://example.test/gtfs.zip", "Test", dt.date(2026, 6, 11))
    packet = build_evidence_packet(artifact)
    assert packet["work_items"], "the fixture must produce findings to retest"
    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet))
    return path


def _run(argv: list[str]) -> int:
    return cli.main(["retest", *argv])


def test_the_command_reports_the_same_bytes_as_still_present(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    packet = _packet_file(tmp_path, monkeypatch)
    _no_registry(monkeypatch)
    record_path = tmp_path / "out" / "record.json"
    markdown_path = tmp_path / "out" / "record.md"

    code = _run(
        [
            str(packet),
            "https://example.test/gtfs.zip",
            "--country",
            "US",
            "--date",
            "2026-06-11",
            "--json-out",
            str(record_path),
            "--markdown-out",
            str(markdown_path),
        ]
    )

    assert code == 1
    record = json.loads(record_path.read_text())
    assert record["findings"]
    assert {entry["verdict"] for entry in record["findings"]} == {STILL_PRESENT}
    assert record["same_bytes_as_baseline"] is True
    assert record["retest"]["country"] == "US"
    assert record["retest"]["source"] == "https://example.test/gtfs.zip"
    assert markdown_path.read_text() == capsys.readouterr().out


def test_the_command_under_another_validator_claims_nothing_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packet = _packet_file(tmp_path, monkeypatch)
    _stub_scoring(monkeypatch, validator="9.9.8", notices=0)
    record_path = tmp_path / "record.json"

    code = _run(
        [
            str(packet),
            "https://example.test/gtfs.zip",
            "--country",
            "US",
            "--json-out",
            str(record_path),
        ]
    )

    assert code == 2
    record = json.loads(record_path.read_text())
    assert {entry["verdict"] for entry in record["findings"]} == {NON_COMPARABLE}


def test_a_refused_packet_costs_no_fetch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_registry(monkeypatch)
    monkeypatch.setattr(cli, "fetch_static", lambda *a, **k: pytest.fail("fetched a feed"))
    monkeypatch.setattr(cli, "run_validator", lambda *a, **k: pytest.fail("ran the validator"))
    empty = _packet()
    empty["work_items"] = []
    refused = tmp_path / "empty.json"
    refused.write_text(json.dumps(empty))
    not_json = tmp_path / "broken.json"
    not_json.write_text("{")
    record_path = tmp_path / "record.json"

    for path in (refused, not_json, tmp_path / "missing.json"):
        argv = [str(path), "https://example.test/gtfs.zip", "--country", "US"]
        assert _run([*argv, "--json-out", str(record_path)]) == 2
    assert not record_path.exists()


def test_a_feed_that_cannot_be_scored_is_exit_2_and_writes_no_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    packet = _packet_file(tmp_path, monkeypatch)

    def unreadable(*_args: Any, **_kwargs: Any) -> FetchResult:
        raise ValueError("response body is not a zip archive")

    monkeypatch.setattr(cli, "fetch_static", unreadable)
    record_path = tmp_path / "record.json"

    code = _run(
        [
            str(packet),
            "https://example.test/gtfs.zip",
            "--country",
            "US",
            "--json-out",
            str(record_path),
        ]
    )

    assert code == 2
    assert not record_path.exists()


def test_the_country_must_be_stated(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exc:
        _run([str(tmp_path / "packet.json"), "https://example.test/gtfs.zip"])
    assert exc.value.code == 2
