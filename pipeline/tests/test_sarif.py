"""Contract tests for the SARIF 2.1.0 output.

The assertion that matters most here is the one about an unreadable feed. SARIF
has no shape that says "I did not run", so an empty ``results`` array renders in
GitHub's Security tab exactly like a feed with nothing wrong.
"""

from __future__ import annotations

from typing import Any

import pytest

from scorecard_pipeline.sarif import (
    SARIF_VERSION,
    build_sarif,
    unreadable_feed_sarif,
)
from scorecard_pipeline.validate import NoticeGroup, ValidationReport


def _report(*groups: NoticeGroup, version: str = "8.0.1") -> ValidationReport:
    return ValidationReport(validator_version=version, notices=list(groups))


def _group(
    code: str,
    severity: str = "WARNING",
    total: int = 1,
    samples: list[dict[str, Any]] | None = None,
) -> NoticeGroup:
    return NoticeGroup(code=code, severity=severity, total=total, sample_notices=samples or [])


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    runs = payload["runs"]
    assert len(runs) == 1
    return dict(runs[0])


def _results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return list(_run(payload)["results"])


# --- shape ---------------------------------------------------------------------


def test_the_log_declares_sarif_2_1_0_and_one_run() -> None:
    payload = build_sarif(_report(_group("unused_shape")))
    assert payload["version"] == SARIF_VERSION
    assert payload["$schema"].endswith("sarif-schema-2.1.0.json")
    run = _run(payload)
    assert run["tool"]["driver"]["name"] == "GTFS Scorecard"
    assert run["tool"]["driver"]["version"] == "8.0.1"
    assert run["invocations"][0]["executionSuccessful"] is True


def test_every_result_references_a_declared_rule() -> None:
    payload = build_sarif(
        _report(_group("unused_shape"), _group("expired_calendar", severity="ERROR"))
    )
    declared = {rule["id"] for rule in _run(payload)["tool"]["driver"]["rules"]}
    assert {result["ruleId"] for result in _results(payload)} == declared


def test_one_result_per_notice_code() -> None:
    """N notice codes produce N results, whatever the instance counts are."""
    payload = build_sarif(
        _report(
            _group("unused_shape", total=54, samples=[{"filename": "shapes.txt"}] * 5),
            _group("unknown_column", total=23),
            _group("expired_calendar", severity="ERROR", total=1),
        )
    )
    assert len(_results(payload)) == 3


def test_severity_maps_to_the_sarif_levels() -> None:
    payload = build_sarif(
        _report(
            _group("a", severity="ERROR"),
            _group("b", severity="WARNING"),
            _group("c", severity="INFO"),
        )
    )
    assert [r["level"] for r in _results(payload)] == ["error", "warning", "note"]


def test_the_rule_help_uri_points_at_the_authoritative_rule() -> None:
    payload = build_sarif(_report(_group("expired_calendar", severity="ERROR")))
    rule = _run(payload)["tool"]["driver"]["rules"][0]
    assert rule["helpUri"] == (
        "https://gtfs-validator.mobilitydata.org/rules.html#expired_calendar-rule"
    )
    assert rule["properties"]["authority"]


def test_the_scorecard_wording_reaches_the_rule_and_the_message() -> None:
    payload = build_sarif(
        _report(_group("unused_shape", total=3)),
        findings={
            "unused_shape": {
                "what": "The feed contains route shapes no trip uses.",
                "why": "Harmless to riders, but it bloats the feed.",
            }
        },
    )
    rule = _run(payload)["tool"]["driver"]["rules"][0]
    assert rule["shortDescription"]["text"].startswith("The feed contains route shapes")
    assert rule["fullDescription"]["text"].startswith("Harmless to riders")
    assert "The feed contains route shapes" in _results(payload)[0]["message"]["text"]


# --- locations -----------------------------------------------------------------


def test_a_sample_with_a_file_and_a_row_becomes_a_line_location() -> None:
    payload = build_sarif(
        _report(_group("stop_too_far", samples=[{"filename": "stops.txt", "csvRowNumber": 42}]))
    )
    location = _results(payload)[0]["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == "stops.txt"
    assert location["region"]["startLine"] == 42


def test_a_notice_without_row_context_still_produces_a_file_level_result() -> None:
    payload = build_sarif(_report(_group("unknown_column", samples=[{"filename": "trips.txt"}])))
    location = _results(payload)[0]["locations"][0]["physicalLocation"]
    assert location["artifactLocation"]["uri"] == "trips.txt"
    assert "region" not in location


def test_a_notice_with_no_file_at_all_still_produces_a_result_and_says_so() -> None:
    payload = build_sarif(_report(_group("missing_required_file", samples=[{"tripId": "T1"}])))
    result = _results(payload)[0]
    assert "locations" not in result
    assert "reported no file for this notice" in result["message"]["text"]


def test_the_base_directory_prefixes_the_member_path() -> None:
    """A feed committed under gtfs/ must annotate gtfs/stops.txt, not stops.txt."""
    payload = build_sarif(
        _report(_group("stop_too_far", samples=[{"filename": "stops.txt", "csvRowNumber": 7}])),
        base="gtfs/",
    )
    uri = _results(payload)[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
    assert uri == "gtfs/stops.txt"


# --- the count is never presented as complete when it is sampled ---------------


def test_a_sampled_notice_says_how_many_it_could_locate() -> None:
    """23 instances and 5 samples must not read as 5 problems."""
    payload = build_sarif(
        _report(
            _group(
                "unused_shape",
                total=23,
                samples=[{"filename": "shapes.txt", "csvRowNumber": n} for n in range(1, 6)],
            )
        )
    )
    result = _results(payload)[0]
    assert "23 instances" in result["message"]["text"]
    assert "5 of them are located below" in result["message"]["text"]
    assert result["properties"]["instanceCount"] == 23
    assert len(result["locations"]) == 5


def test_a_fully_located_notice_makes_no_sampling_caveat() -> None:
    payload = build_sarif(
        _report(_group("stop_too_far", total=1, samples=[{"filename": "stops.txt"}]))
    )
    text = _results(payload)[0]["message"]["text"]
    assert "1 instance" in text
    assert "located below" not in text


# --- fingerprints --------------------------------------------------------------


def test_fingerprints_are_identical_across_two_runs_of_the_same_report() -> None:
    def build() -> list[str]:
        payload = build_sarif(
            _report(
                _group("unused_shape", samples=[{"filename": "shapes.txt", "csvRowNumber": 9}]),
                _group("unknown_column", samples=[{"filename": "trips.txt"}]),
            )
        )
        return [r["partialFingerprints"]["gtfsScorecardNotice/v1"] for r in _results(payload)]

    assert build() == build()


def test_the_fingerprint_survives_the_instance_count_moving() -> None:
    """A partly-fixed finding must not resurface as a brand-new alert."""

    def fingerprint(total: int) -> str:
        payload = build_sarif(
            _report(
                _group(
                    "unused_shape",
                    total=total,
                    samples=[{"filename": "shapes.txt", "csvRowNumber": 9}],
                )
            )
        )
        return str(_results(payload)[0]["partialFingerprints"]["gtfsScorecardNotice/v1"])

    assert fingerprint(54) == fingerprint(12)


def test_different_files_get_different_fingerprints() -> None:
    def fingerprint(filename: str) -> str:
        payload = build_sarif(
            _report(_group("stop_too_far", samples=[{"filename": filename, "csvRowNumber": 3}]))
        )
        return str(_results(payload)[0]["partialFingerprints"]["gtfsScorecardNotice/v1"])

    assert fingerprint("stops.txt") != fingerprint("stop_times.txt")


# --- the case this file exists for ---------------------------------------------


def test_an_unreadable_feed_is_never_a_clean_looking_run() -> None:
    payload = unreadable_feed_sarif("response body is not a zip")
    run = _run(payload)
    assert run["results"] == []
    invocation = run["invocations"][0]
    assert invocation["executionSuccessful"] is False
    notification = invocation["toolExecutionNotifications"][0]
    assert notification["level"] == "error"
    assert "response body is not a zip" in notification["message"]["text"]
    assert "the absence of results means nothing" in notification["message"]["text"]


def test_a_genuinely_clean_feed_is_a_successful_run_with_no_results() -> None:
    """The negative control: the refusal must not swallow a real clean feed."""
    payload = build_sarif(_report())
    run = _run(payload)
    assert run["results"] == []
    assert run["invocations"][0]["executionSuccessful"] is True
    assert "toolExecutionNotifications" not in run["invocations"][0]


@pytest.mark.parametrize("severity", ["ERROR", "WARNING", "INFO", "SOMETHING_NEW"])
def test_an_unknown_severity_becomes_a_note_rather_than_being_dropped(severity: str) -> None:
    payload = build_sarif(_report(_group("x", severity=severity)))
    assert len(_results(payload)) == 1


# --- the CLI seam --------------------------------------------------------------


def _try_args(tmp_path: Any, **overrides: Any) -> Any:
    import argparse

    defaults = dict(
        url="https://example.org/gtfs.zip",
        name=None,
        date=None,
        country="US",
        large_feed=False,
        html=None,
        comment=None,
        page_url=None,
        json_out=None,
        min_grade=None,
        min_days_to_expiry=None,
        sarif=str(tmp_path / "out.sarif"),
        sarif_base="",
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_try_writes_sarif_from_the_validator_report_not_the_artifact(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The samples the artifact drops are exactly what SARIF needs.

    `build_artifact` aggregates each notice code to a count, so a SARIF built
    from an artifact could never carry a file or a row. This asserts the wiring
    reads the report instead.
    """
    import argparse
    import json

    from scorecard_pipeline import cli

    artifact = {
        "agency": {"name": "Example Transit"},
        "feed": {"static_url": "https://example.org/gtfs.zip"},
        "overall": {"grade": "C", "score": 72.5},
        "categories": {
            "correctness": {
                "status": "measured",
                "score": 70,
                "findings": [
                    {
                        "code": "stop_too_far",
                        "count": 2,
                        "severity": "WARNING",
                        "what": "Some stops are far from their trips.",
                        "why": "Riders are sent to the wrong place.",
                    }
                ],
            }
        },
        "top_fixes": [],
    }
    report = _report(
        _group(
            "stop_too_far",
            total=2,
            samples=[{"filename": "stops.txt", "csvRowNumber": 12}],
        )
    )
    monkeypatch.setattr(cli, "run_adhoc_detailed", lambda *_a, **_k: (artifact, report))
    args = _try_args(tmp_path)
    assert cli._cmd_try(args, argparse.ArgumentParser()) == 0

    payload = json.loads((tmp_path / "out.sarif").read_text())
    result = payload["runs"][0]["results"][0]
    assert result["ruleId"] == "stop_too_far"
    assert result["locations"][0]["physicalLocation"]["region"]["startLine"] == 12
    # The scorecard's own wording travelled with it.
    assert "Some stops are far from their trips." in result["message"]["text"]
    assert payload["runs"][0]["invocations"][0]["executionSuccessful"] is True


def test_a_refused_feed_writes_an_unsuccessful_sarif_not_an_empty_clean_one(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole reason `--sarif` is passed before the scorer can refuse.

    Without this, a feed the scorer would not read produces no SARIF at all and
    the upload step either fails opaquely or, worse, reuses a stale file. With
    an empty successful SARIF it would produce a green Security tab.
    """
    import argparse
    import json

    from scorecard_pipeline import cli

    def _refuse(*_args: Any, **_kwargs: Any) -> Any:
        raise ValueError("response body is not a zip")

    monkeypatch.setattr(cli, "run_adhoc_detailed", _refuse)
    args = _try_args(tmp_path)
    assert cli._cmd_try(args, argparse.ArgumentParser()) == 1

    payload = json.loads((tmp_path / "out.sarif").read_text())
    run = payload["runs"][0]
    assert run["results"] == []
    assert run["invocations"][0]["executionSuccessful"] is False
    assert (
        "response body is not a zip"
        in (run["invocations"][0]["toolExecutionNotifications"][0]["message"]["text"])
    )


def test_no_sarif_flag_writes_no_sarif(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    import argparse

    from scorecard_pipeline import cli

    monkeypatch.setattr(
        cli,
        "run_adhoc_detailed",
        lambda *_a, **_k: (
            {
                "agency": {"name": "X"},
                "feed": {"static_url": "u"},
                "overall": {"grade": "A", "score": 95.0},
                "categories": {},
                "top_fixes": [],
            },
            _report(),
        ),
    )
    assert cli._cmd_try(_try_args(tmp_path, sarif=None), argparse.ArgumentParser()) == 0
    assert not (tmp_path / "out.sarif").exists()


# --- structural conformance ----------------------------------------------------

#: A structural subset of the SARIF 2.1.0 schema, not the whole thing.
#:
#: The full schema is roughly 200 KB of JSON. Fetching it at test time would make
#: a merge gate depend on someone else's uptime, and vendoring it would put a
#: large third-party document in the tree for one assertion. So this encodes the
#: parts of the spec this writer can actually get wrong: the required properties
#: on the log, the run, the tool driver, and each result, the closed `level`
#: enumeration, and the requirement that every `ruleId` resolve to a declared
#: rule. `additionalProperties` stays open, because the spec's own objects are.
#:
#: What this does NOT prove is full SARIF conformance. If that is wanted, the
#: honest way is to vendor the schema deliberately and say so.
_SARIF_STRUCTURE: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": ["version", "runs"],
    "properties": {
        "version": {"const": "2.1.0"},
        "runs": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["tool", "results"],
                "properties": {
                    "tool": {
                        "type": "object",
                        "required": ["driver"],
                        "properties": {
                            "driver": {
                                "type": "object",
                                "required": ["name"],
                                "properties": {
                                    "name": {"type": "string", "minLength": 1},
                                    "rules": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "required": ["id"],
                                            "properties": {
                                                "id": {"type": "string", "minLength": 1},
                                                "helpUri": {
                                                    "type": "string",
                                                    "pattern": "^https://",
                                                },
                                            },
                                        },
                                    },
                                },
                            }
                        },
                    },
                    "invocations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["executionSuccessful"],
                            "properties": {"executionSuccessful": {"type": "boolean"}},
                        },
                    },
                    "results": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["message"],
                            "properties": {
                                "ruleId": {"type": "string", "minLength": 1},
                                "level": {"enum": ["none", "note", "warning", "error"]},
                                "message": {
                                    "type": "object",
                                    "required": ["text"],
                                    "properties": {"text": {"type": "string", "minLength": 1}},
                                },
                                "locations": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "physicalLocation": {
                                                "type": "object",
                                                "required": ["artifactLocation"],
                                                "properties": {
                                                    "artifactLocation": {
                                                        "type": "object",
                                                        "required": ["uri"],
                                                        "properties": {
                                                            "uri": {
                                                                "type": "string",
                                                                "minLength": 1,
                                                            }
                                                        },
                                                    },
                                                    "region": {
                                                        "type": "object",
                                                        "properties": {
                                                            "startLine": {
                                                                "type": "integer",
                                                                "minimum": 1,
                                                            }
                                                        },
                                                    },
                                                },
                                            }
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            build_sarif(
                _report(
                    _group(
                        "stop_too_far",
                        severity="ERROR",
                        total=9,
                        samples=[{"filename": "stops.txt", "csvRowNumber": 4}],
                    ),
                    _group("unknown_column", severity="INFO", total=3),
                )
            ),
            id="findings",
        ),
        pytest.param(build_sarif(_report()), id="clean feed"),
        pytest.param(unreadable_feed_sarif("no zip"), id="unreadable feed"),
    ],
)
def test_the_output_matches_the_sarif_structure(payload: dict[str, Any]) -> None:
    import jsonschema

    jsonschema.validate(payload, _SARIF_STRUCTURE)
    run = payload["runs"][0]
    declared = {rule["id"] for rule in run["tool"]["driver"].get("rules", [])}
    assert {result["ruleId"] for result in run["results"]} <= declared


def test_the_structure_check_can_fail() -> None:
    """The negative control: a schema that accepts anything proves nothing."""
    import jsonschema

    broken = build_sarif(_report(_group("x")))
    broken["runs"][0]["results"][0]["level"] = "critical"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(broken, _SARIF_STRUCTURE)
