"""Tests for the structured license block, its JSON Schema, and the advisory lint (#372).

The properties that matter, in order: a block is validated strictly and nothing
is defaulted; an unknown license never lints clean; the lint and everything
around it stay advisory and change nothing about admission; and the committed
JSON Schema and the parser reach the same verdict.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from scorecard_pipeline.agencies import AgencyConfigError, parse_agencies
from scorecard_pipeline.config import Agency, LicenseBlock
from scorecard_pipeline.license_audit import CLASSES, license_audit
from scorecard_pipeline.license_ledger import (
    ADVISORY_NOTICE,
    ATTRIBUTION_MISMATCH,
    ATTRIBUTION_TEXT_WITHOUT_REQUIREMENT,
    INCONSISTENT_KINDS,
    LICENSE_IDS,
    LICENSE_UNKNOWN,
    NEEDS_REVIEW_STATUS,
    NO_LICENSE_BLOCK,
    NOTE_DISAGREES,
    SHARE_ALIKE_MISMATCH,
    UNKNOWN_WITH_FACTS,
    LicenseBlockError,
    block_to_mapping,
    block_to_yaml_lines,
    check_block,
    json_schema,
    ledger_report,
    lint_ledger,
    parse_block,
    render_schema,
)
from scorecard_pipeline.lint import lint_registry

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = REPO_ROOT / "registry" / "license.schema.json"
TODAY = dt.date(2026, 9, 19)

VALID: dict[str, Any] = {
    "id": "CC-BY-4.0",
    "attribution_required": True,
    "redistribution_allowed": "unknown",
    "share_alike": False,
    "status": "unreviewed",
}


def block(**overrides: Any) -> dict[str, Any]:
    raw = dict(VALID)
    raw.update(overrides)
    return raw


def agency(
    agency_id: str = "demo", note: str = "", license_block: LicenseBlock | None = None
) -> Agency:
    return Agency(
        id=agency_id,
        name=agency_id.title(),
        static_gtfs_url=f"https://example.org/{agency_id}.zip",
        license_note=note,
        license_block=license_block,
    )


def with_block(agency_id: str = "demo", note: str = "", **overrides: Any) -> Agency:
    return agency(agency_id, note, parse_block(block(**overrides), today=TODAY))


def kinds(findings: list[Any]) -> list[str]:
    return [f.kind for f in findings]


# --- strict validation ----------------------------------------------------------


def test_a_minimal_block_parses_and_keeps_unknown_as_unknown() -> None:
    parsed = parse_block(VALID, today=TODAY)
    assert parsed.id == "CC-BY-4.0"
    assert parsed.redistribution_allowed == "unknown"
    assert parsed.share_alike is False
    assert (parsed.name, parsed.terms_url, parsed.reviewed_by) == ("", "", "")


def test_a_full_reviewed_block_parses_and_strips_text() -> None:
    parsed = parse_block(
        block(
            id="other",
            name="  National open data terms  ",
            terms_url="https://data.example.org/terms",
            retrieved_on="2026-09-01",
            attribution="  Credit Demo Transit.  ",
            redistribution_allowed=True,
            status="reviewed",
            reviewed_by=" curator ",
            reviewed_on="2026-09-18",
            reviewer_note="Read the portal terms.",
        ),
        today=TODAY,
    )
    assert parsed.name == "National open data terms"
    assert parsed.attribution == "Credit Demo Transit."
    assert parsed.reviewed_by == "curator"
    assert parsed.redistribution_allowed is True


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("CC-BY-4.0", "must be a mapping"),
        (block(extra="x"), "unknown license field(s): extra"),
        (block(id="cc-by-4.0"), "license.id must be one of"),
        (block(id=["CC0-1.0"]), "license.id must be one of"),
        (block(status="approved"), "license.status must be one of"),
        (block(share_alike="yes"), "must be true, false, or unknown"),
        (block(share_alike="false"), "must be true, false, or unknown"),
        (block(share_alike=None), "must be true, false, or unknown"),
        (block(share_alike=1), "must be true, false, or unknown"),
        (block(attribution_required=0), "must be true, false, or unknown"),
        (block(redistribution_allowed="Unknown"), "must be true, false, or unknown"),
        (block(id="other"), "license.name is required"),
        (block(id="proprietary-terms"), "license.name is required"),
        (block(name="   "), "license.name must be a non-empty string"),
        (block(attribution=""), "license.attribution must be a non-empty string"),
        (block(status="reviewed"), "a reviewed license needs"),
        (block(status="reviewed", reviewed_by="curator"), "license.reviewed_on"),
        (block(reviewed_by="curator"), "may only be set when license.status is 'reviewed'"),
        (block(status="needs_review", reviewed_on="2026-09-01"), "may only be set when"),
        (block(terms_url="ftp://example.org/terms"), "must be an http(s) URL"),
        (block(terms_url="https://example.org/a b"), "must be an http(s) URL"),
        (block(terms_url="https://"), "must be an http(s) URL"),
        (block(retrieved_on="2026-9-1"), "must be an ISO date"),
        (block(retrieved_on="2026-13-01"), "must be a valid ISO date"),
        (block(retrieved_on="2026-09-20"), "must not be in the future"),
        (block(retrieved_on=dt.date(2026, 9, 1)), "quoted ISO date string"),
    ],
)
def test_a_malformed_block_is_rejected_with_a_sentence(raw: Any, message: str) -> None:
    parsed, problems = check_block(raw, today=TODAY)
    assert parsed is None
    assert any(message in problem for problem in problems), problems


@pytest.mark.parametrize("key", ["id", "attribution_required", "redistribution_allowed"])
def test_a_missing_required_key_is_an_error_not_a_default(key: str) -> None:
    """Absence must not read as a value: a term left out is refused, never assumed."""
    raw = dict(VALID)
    del raw[key]
    parsed, problems = check_block(raw, today=TODAY)
    assert parsed is None
    assert f"license missing required field(s): {key}" in problems


def test_share_alike_and_status_are_required_too() -> None:
    for key in ("share_alike", "status"):
        raw = dict(VALID)
        del raw[key]
        assert check_block(raw, today=TODAY)[0] is None


def test_every_problem_is_reported_at_once() -> None:
    _, problems = check_block({"id": "nope", "share_alike": "maybe"}, today=TODAY)
    joined = " ".join(problems)
    assert "license.id must be one of" in joined
    assert "license.share_alike must be true, false, or unknown" in joined
    assert "license missing required field(s)" in joined


def test_parse_block_raises_one_error_naming_every_problem() -> None:
    with pytest.raises(LicenseBlockError, match=r"license\.id must be one of.*license\.status"):
        parse_block({"id": "nope", "status": "nope"})


def test_the_vocabulary_is_the_audits_plus_three_named_states() -> None:
    assert set(LICENSE_IDS) == {c.id for c in CLASSES} | {"proprietary-terms", "other", "unknown"}
    assert len(LICENSE_IDS) == len(set(LICENSE_IDS))


# --- the loader accepts the block and rejects a malformed one --------------------


def _entry(**extra: Any) -> dict[str, Any]:
    return {
        "agencies": [
            {
                "id": "demo",
                "name": "Demo Transit",
                "static_gtfs_url": "https://example.org/gtfs.zip",
                "license_note": "CC BY 4.0",
                **extra,
            }
        ]
    }


def test_the_loader_carries_a_valid_block_and_none_when_absent() -> None:
    (with_one,) = parse_agencies(_entry(license=VALID))
    (without,) = parse_agencies(_entry())
    assert with_one.license_block == parse_block(VALID, today=TODAY)
    assert without.license_block is None


def test_the_loader_refuses_a_malformed_block_and_names_the_record() -> None:
    with pytest.raises(AgencyConfigError, match=r"agency 'demo'.*must be true, false, or unknown"):
        parse_agencies(_entry(license=block(share_alike="yes")))


def test_the_loader_refuses_a_future_review_date() -> None:
    future = (dt.datetime.now(dt.UTC).date() + dt.timedelta(days=2)).isoformat()
    with pytest.raises(AgencyConfigError, match="must not be in the future"):
        parse_agencies(
            _entry(license=block(status="reviewed", reviewed_by="a", reviewed_on=future))
        )


def test_a_block_beside_a_note_never_replaces_the_note() -> None:
    (parsed,) = parse_agencies(_entry(license=VALID))
    assert parsed.license_note == "CC BY 4.0"


# --- the JSON Schema ------------------------------------------------------------


def test_the_committed_schema_is_the_one_the_module_generates() -> None:
    assert SCHEMA_PATH.read_text(encoding="utf-8") == render_schema(), (
        "registry/license.schema.json is generated from license_ledger.py; regenerate it with: "
        "cd pipeline && uv run python -c 'from scorecard_pipeline.license_ledger import "
        'render_schema; print(render_schema(), end="")\' > ../registry/license.schema.json'
    )


def test_the_schema_is_a_valid_draft_2020_12_schema() -> None:
    Draft202012Validator.check_schema(json_schema())
    assert json.loads(SCHEMA_PATH.read_text(encoding="utf-8")) == json_schema()


def test_the_schema_takes_its_vocabulary_from_the_parser() -> None:
    schema = json_schema()
    assert schema["properties"]["id"]["enum"] == list(LICENSE_IDS)
    for key in ("attribution_required", "redistribution_allowed", "share_alike"):
        assert schema["properties"][key]["enum"] == [True, False, "unknown"]
        assert key in schema["required"]
    assert schema["additionalProperties"] is False


# The blocks below are all inside what a JSON Schema can state. Calendar validity
# and "not in the future" stay with the parser, which the schema's description says.
PARITY_BLOCKS: list[Any] = [
    VALID,
    block(share_alike="unknown"),
    block(id="unknown", attribution_required="unknown", share_alike="unknown"),
    block(id="other", name="A national license"),
    block(id="other"),
    block(id="proprietary-terms"),
    block(id="proprietary-terms", name="Bespoke terms"),
    block(id="CC0-1.0", attribution_required=False, share_alike=False),
    block(id="cc0"),
    block(id=None),
    block(share_alike="yes"),
    block(share_alike=None),
    block(share_alike=1),
    block(share_alike=0),
    block(attribution_required="true"),
    block(status="reviewed"),
    block(status="reviewed", reviewed_by="curator", reviewed_on="2026-09-01"),
    block(status="reviewed", reviewed_by="curator"),
    block(status="unreviewed", reviewed_by="curator", reviewed_on="2026-09-01"),
    block(status="needs_review", reviewed_on="2026-09-01"),
    block(status="done"),
    block(terms_url="https://example.org/terms"),
    block(terms_url="http://example.org"),
    block(terms_url="ftp://example.org/terms"),
    block(terms_url="example.org/terms"),
    block(terms_url="https://example.org/a b"),
    block(retrieved_on="2026-09-01"),
    block(retrieved_on="2026-9-1"),
    block(retrieved_on="yesterday"),
    block(name=""),
    block(name="   "),
    block(reviewer_note="Read the terms."),
    block(reviewer_note=""),
    block(extra=True),
    {},
    {"id": "CC0-1.0"},
]


@pytest.mark.parametrize("raw", PARITY_BLOCKS, ids=range(len(PARITY_BLOCKS)))
def test_the_schema_and_the_parser_reach_the_same_verdict(raw: Any) -> None:
    valid_for_schema = Draft202012Validator(json_schema()).is_valid(raw)
    valid_for_parser = check_block(raw, today=TODAY)[0] is not None
    assert valid_for_schema == valid_for_parser, raw


def test_the_battery_covers_both_verdicts() -> None:
    verdicts = {check_block(raw, today=TODAY)[0] is not None for raw in PARITY_BLOCKS}
    assert verdicts == {True, False}


# --- the block as text ----------------------------------------------------------


def test_block_yaml_round_trips_through_the_parser() -> None:
    import yaml

    parsed = parse_block(
        block(
            id="other",
            name="Terms: \"quoted\" & 'odd' - no",
            reviewer_note="line with # hash",
            share_alike="unknown",
        ),
        today=TODAY,
    )
    text = "\n".join(block_to_yaml_lines(parsed, indent=4))
    (loaded,) = yaml.safe_load(text).values()
    assert loaded == block_to_mapping(parsed)
    assert parse_block(loaded, today=TODAY) == parsed


def test_words_yaml_would_read_as_booleans_are_written_quoted() -> None:
    import yaml

    parsed = parse_block(block(id="other", name="no"), today=TODAY)
    loaded = yaml.safe_load("\n".join(block_to_yaml_lines(parsed, indent=0)))["license"]
    assert loaded["name"] == "no"


# --- the advisory lint ----------------------------------------------------------


def test_a_record_with_no_block_is_reported() -> None:
    (finding,) = lint_ledger([agency("bare", "CC BY 4.0; credit the agency.")])
    assert (finding.agency_id, finding.kind) == ("bare", NO_LICENSE_BLOCK)
    assert "license_note reads as CC-BY-4.0" in finding.detail


def test_a_consistent_block_lints_clean() -> None:
    assert lint_ledger([with_block(note="CC BY 4.0; credit the agency.")]) == []
    assert lint_ledger([with_block(note="")]) == []


@pytest.mark.parametrize(
    "note",
    [
        "",
        "No stated data license; requested attribution.",
        "License: https://example.org/terms",
        "Estonia's public-transport open-data terms permit reuse with the data origin cited.",
        "Datenlizenz Deutschland Namensnennung 2.0; no ODbL condition applies.",
    ],
)
def test_negative_control_an_unknown_license_never_lints_clean(note: str) -> None:
    """The control: every way a license can be unknown must show up as a finding.

    A record with no block, a block that says unknown, and a block that says
    unknown and was marked reviewed. If the lint ever passed any of these, an
    unmeasured license would read as a clean one.
    """
    unknown = {
        "id": "unknown",
        "attribution_required": "unknown",
        "redistribution_allowed": "unknown",
        "share_alike": "unknown",
    }
    no_block = lint_ledger([agency("a", note)])
    needs_review = lint_ledger([with_block("a", note, **unknown, status="needs_review")])
    reviewed = lint_ledger(
        [
            with_block(
                "a", note, **unknown, status="reviewed", reviewed_by="c", reviewed_on="2026-09-01"
            )
        ]
    )
    assert kinds(no_block) == [NO_LICENSE_BLOCK]
    assert kinds(needs_review) == [LICENSE_UNKNOWN]
    assert kinds(reviewed) == [LICENSE_UNKNOWN]
    # ...and the same records lint clean once the license is actually known, so
    # the findings above are the unknown license and not the fixture.
    assert lint_ledger([with_block("a", "", id="CC0-1.0", attribution_required=False)]) == []


def test_negative_control_flipping_a_clean_record_to_unknown_makes_it_dirty() -> None:
    clean = with_block("a", "CC BY 4.0")
    assert lint_ledger([clean]) == []
    flipped = dataclasses.replace(clean.license_block, id="unknown")  # type: ignore[type-var]
    dirty = lint_ledger([dataclasses.replace(clean, license_block=flipped)])
    assert LICENSE_UNKNOWN in kinds(dirty)


def test_a_needs_review_status_is_reported_even_for_a_known_license() -> None:
    assert kinds(lint_ledger([with_block("a", "", status="needs_review")])) == [NEEDS_REVIEW_STATUS]


def test_unknown_license_with_a_recorded_fact_is_inconsistent() -> None:
    """Nothing is known about an unknown license, so a fact recorded for it is a
    guess. A permissive-looking one is the case that matters."""
    found = lint_ledger(
        [with_block("a", "", id="unknown", redistribution_allowed=True, share_alike="unknown")]
    )
    assert kinds(found) == [UNKNOWN_WITH_FACTS, LICENSE_UNKNOWN]
    assert "redistribution_allowed" in found[0].detail


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"id": "ODbL-1.0", "share_alike": False}, SHARE_ALIKE_MISMATCH),
        ({"id": "CC-BY-SA-3.0", "share_alike": False}, SHARE_ALIKE_MISMATCH),
        ({"id": "CC-BY-4.0", "share_alike": True}, SHARE_ALIKE_MISMATCH),
        (
            {"id": "CC0-1.0", "attribution_required": True, "share_alike": False},
            ATTRIBUTION_MISMATCH,
        ),
        ({"id": "CC-BY-4.0", "attribution_required": False}, ATTRIBUTION_MISMATCH),
        (
            {"attribution": "Credit Demo.", "attribution_required": False, "id": "CC0-1.0"},
            ATTRIBUTION_TEXT_WITHOUT_REQUIREMENT,
        ),
    ],
)
def test_a_block_that_contradicts_its_own_license_is_inconsistent(
    overrides: dict[str, Any], expected: str
) -> None:
    assert expected in kinds(lint_ledger([with_block("a", "", **overrides)]))


@pytest.mark.parametrize("license_id", ["ODbL-1.0", "CC-BY-SA-4.0", "CC-BY-SA-3.0", "CC-BY-SA"])
@pytest.mark.parametrize("status", ["unreviewed", "needs_review"])
def test_a_share_alike_feed_is_never_a_finding_for_being_share_alike(
    license_id: str, status: str
) -> None:
    """Owner decision, 2026-09-19: share-alike is admitted with a notice. The lint
    records share-alike as a neutral fact and must not flag, exclude, or block a
    record for it. (A needs_review status is its own finding, and only that.)"""
    record = with_block("a", "", id=license_id, share_alike=True, status=status)
    found = kinds(lint_ledger([record]))
    assert found == ([NEEDS_REVIEW_STATUS] if status == "needs_review" else [])
    assert SHARE_ALIKE_MISMATCH not in found
    assert "share_alike" not in " ".join(f.detail for f in lint_ledger([record]))


def test_no_finding_kind_is_about_a_license_being_share_alike() -> None:
    """A source-level guard: every kind is about a missing, unknown, or contradictory
    block, and none names share-alike as a defect."""
    from scorecard_pipeline.license_ledger import KINDS

    assert not [
        kind for kind in KINDS if kind.startswith("share_alike") and kind != SHARE_ALIKE_MISMATCH
    ]


def test_unknown_terms_beside_a_known_license_are_not_a_contradiction() -> None:
    assert (
        lint_ledger([with_block("a", "", share_alike="unknown", attribution_required="unknown")])
        == []
    )


def test_a_named_license_outside_the_vocabulary_is_not_checked_against_it() -> None:
    record = with_block("a", "", id="other", name="A national license", share_alike=True)
    assert lint_ledger([record]) == []


def test_the_free_text_note_disagreeing_with_the_block_is_reported() -> None:
    found = lint_ledger([with_block("a", "ODbL; credit the operator.", id="CC-BY-4.0")])
    assert kinds(found) == [NOTE_DISAGREES]
    assert "ODbL-1.0" in found[0].detail


def test_an_ambiguous_note_does_not_contradict_a_block_that_resolves_it() -> None:
    note = "Datenlizenz Deutschland Namensnennung 2.0; no ODbL condition applies."
    assert lint_ledger([with_block("a", note, id="DL-DE-BY-2.0")]) == []


def test_findings_list_contradictions_before_gaps_and_are_sorted() -> None:
    records = [
        agency("z-bare"),
        with_block(
            "b",
            "",
            id="unknown",
            attribution_required="unknown",
            share_alike="unknown",
            status="needs_review",
        ),
        with_block("a", "", id="ODbL-1.0", share_alike=False),
        agency("a-bare"),
    ]
    found = lint_ledger(records)
    assert kinds(found) == [
        SHARE_ALIKE_MISMATCH,
        NO_LICENSE_BLOCK,
        NO_LICENSE_BLOCK,
        LICENSE_UNKNOWN,
    ]
    assert [f.agency_id for f in found if f.kind == NO_LICENSE_BLOCK] == ["a-bare", "z-bare"]
    assert set(INCONSISTENT_KINDS).isdisjoint({NO_LICENSE_BLOCK, LICENSE_UNKNOWN})


def test_the_report_says_advisory_and_counts_by_kind_and_status() -> None:
    report = ledger_report(
        [agency("bare"), with_block("a", "", status="needs_review"), with_block("b", "")]
    )
    assert report["advisory"] is True
    assert report["notice"] == ADVISORY_NOTICE
    assert "ADVISORY ONLY" in ADVISORY_NOTICE
    assert "changes nothing about which feeds are admitted, scored, or published" in ADVISORY_NOTICE
    assert (report["records"], report["with_block"], report["without_block"]) == (3, 2, 1)
    assert report["by_status"] == {"unreviewed": 1, "needs_review": 1, "reviewed": 0}
    assert report["by_kind"][NO_LICENSE_BLOCK] == 1
    assert report["clean_records"] == 1


# --- advisory means it changes nothing ------------------------------------------


def test_a_license_block_changes_nothing_the_registry_gates_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Give every record each kind of block in turn: the audit and the hygiene
    lint (the two things that read the registry today) must not move at all."""
    from scorecard_pipeline.agencies import read_agencies

    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    records = read_agencies()
    audit_before = license_audit(records)
    lint_before = lint_registry(records)
    canonical_before = [a.is_canonical_feed for a in records]
    for raw in (
        block(id="unknown", attribution_required="unknown", share_alike="unknown"),
        block(id="ODbL-1.0", share_alike=True),
        block(id="CC0-1.0", attribution_required=False, redistribution_allowed=True),
    ):
        stamped = [
            dataclasses.replace(a, license_block=parse_block(raw, today=TODAY)) for a in records
        ]
        assert license_audit(stamped) == audit_before
        assert lint_registry(stamped) == lint_before
        assert [a.is_canonical_feed for a in stamped] == canonical_before


def _modules_matching(pattern: str) -> list[str]:
    src = REPO_ROOT / "pipeline" / "src" / "scorecard_pipeline"
    return sorted(
        path.name
        for path in src.glob("*.py")
        if re.search(pattern, path.read_text("utf-8"), re.MULTILINE)
    )


def test_only_the_ledger_the_loader_and_the_notice_read_a_block() -> None:
    """Nothing that fetches, validates, scores, ranks, or admits may read a license
    block; the one thing a block changes is the reuse notice.

    A source scan rather than a behavior test, because the property is about every
    code path, including ones no test exercises. If a later change needs the block
    for a decision, this fails and the change has to say so.
    """
    readers = _modules_matching(r"license_block")
    assert readers == [
        "agencies.py",
        "config.py",
        "license_ledger.py",
        "license_migrate.py",
        "license_notice.py",
    ]
    # The ledger modules are reached only by the loader, the CLI verbs, and the
    # notice; the notice only by the two publishers that print it.
    assert _modules_matching(r"^\s*from \.license_(?:ledger|migrate) import") == [
        "agencies.py",
        "cli.py",
        "license_migrate.py",
        "license_notice.py",
    ]
    assert _modules_matching(r"^\s*from \.license_notice import") == [
        "dataset.py",
        "render_site.py",
    ]


def test_the_registry_loader_and_lint_strict_are_untouched() -> None:
    from scorecard_pipeline.cli import STRICT_LINT_KINDS

    strict = set(STRICT_LINT_KINDS)
    assert strict == {
        "feed_descriptor_name",
        "duplicate_mdb_id",
        "duplicate_feed_url",
        "literal_credential",
    }


# --- the verb -------------------------------------------------------------------


def _write_registry(root: Path, with_a_block: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    block_text = (
        "    license:\n"
        "      id: CC-BY-4.0\n"
        "      attribution_required: true\n"
        "      redistribution_allowed: unknown\n"
        "      share_alike: false\n"
        "      status: unreviewed\n"
        if with_a_block
        else ""
    )
    (root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: waltti\n"
        "    name: Waltti\n"
        "    static_gtfs_url: https://example.org/waltti.zip\n"
        "    license_note: CC BY 4.0; credit Waltti.\n" + block_text + "  - id: bare\n"
        "    name: Bare\n"
        "    static_gtfs_url: https://example.org/bare.zip\n"
        "    license_note: No stated data license.\n"
    )


def test_the_verb_says_it_is_advisory_and_exits_zero_on_findings(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline.cli import main

    _write_registry(isolated_repo_root, with_a_block=True)
    assert main(["license-lint"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("License ledger lint. ADVISORY ONLY.")
    assert "changes nothing about which feeds are admitted, scored, or published" in out
    assert "Records: 2. With a structured license block: 1. Without: 1." in out
    assert "Blocks by status: unreviewed 1, needs_review 0, reviewed 0." in out
    assert "1 no_license_block rows not listed; pass --all to list them." in out


def test_the_verb_lists_the_records_without_a_block_only_on_request(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline.cli import main

    _write_registry(isolated_repo_root, with_a_block=False)
    assert main(["license-lint", "--all"]) == 0
    out = capsys.readouterr().out
    assert "no_license_block\tbare\tlicense_note is unknown (no_license_stated)" in out
    assert "no_license_block\twaltti\tlicense_note reads as CC-BY-4.0" in out


def test_the_verb_prints_json_that_carries_the_notice(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline.cli import main

    _write_registry(isolated_repo_root, with_a_block=False)
    assert main(["license-lint", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["advisory"] is True
    assert report["notice"] == ADVISORY_NOTICE
    assert report["by_kind"][NO_LICENSE_BLOCK] == 2


def test_the_verb_has_no_strict_mode() -> None:
    """An admission rule is a separate change. If a blocking flag appears here,
    this test is the place a reviewer notices."""
    from scorecard_pipeline.cli import main

    with pytest.raises(SystemExit) as raised:
        main(["license-lint", "--strict"])
    assert raised.value.code == 2


def test_lint_strict_does_not_look_at_license_blocks(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline.cli import main

    _write_registry(isolated_repo_root, with_a_block=False)
    before = main(["lint", "--strict"])
    _write_registry(isolated_repo_root, with_a_block=True)
    after = main(["lint", "--strict"])
    assert before == after == 0
    capsys.readouterr()


def test_the_committed_registry_lints_without_error_and_stays_advisory(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline.cli import main

    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    assert main(["license-lint"]) == 0
    assert "ADVISORY ONLY" in capsys.readouterr().out
