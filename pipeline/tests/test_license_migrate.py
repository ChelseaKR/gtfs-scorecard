"""Tests for the license migration: mechanical proposals, a dry run by default, and a
verified, idempotent apply (issue #372)."""

from __future__ import annotations

import difflib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from scorecard_pipeline import license_ledger, license_migrate
from scorecard_pipeline.agencies import read_agencies
from scorecard_pipeline.config import Agency
from scorecard_pipeline.license_audit import license_audit
from scorecard_pipeline.license_ledger import (
    INCONSISTENT_KINDS,
    LICENSE_UNKNOWN,
    NO_LICENSE_BLOCK,
    NOTE_DISAGREES,
    block_to_mapping,
    check_block,
    json_schema,
    lint_ledger,
)
from scorecard_pipeline.license_migrate import (
    OUTCOME_ALREADY,
    OUTCOME_NEEDS_REVIEW,
    OUTCOME_PROPOSED,
    MigrationEntry,
    MigrationError,
    apply_migration,
    migration_report,
    plan_migration,
    propose,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

NVBW_NOTE = (
    "Datenlizenz Deutschland Namensnennung 2.0 per NVBW's licence page; credit the dataset "
    'as "Datensatz der NVBW GmbH". This is the variant without the route network, so no '
    "OpenStreetMap-derived shapes and no ODbL condition apply."
)
ESTONIA_NOTE = "Estonia's public-transport open-data terms permit reuse with the data origin cited."


def agency(agency_id: str, note: str) -> Agency:
    return Agency(
        id=agency_id,
        name=agency_id.title(),
        static_gtfs_url=f"https://example.org/{agency_id}.zip",
        license_note=note,
    )


# --- what is proposed -----------------------------------------------------------


def test_one_named_license_is_proposed_from_the_vocabulary_and_nothing_more() -> None:
    entry = propose(agency("a", "CC BY 4.0; credit the agency."))
    assert entry.outcome == OUTCOME_PROPOSED
    assert entry.block is not None
    assert entry.block.id == "CC-BY-4.0"
    assert (entry.block.attribution_required, entry.block.share_alike) == (True, False)
    # The note says nothing about redistributing feed bytes, so it is not guessed.
    assert entry.block.redistribution_allowed == "unknown"
    assert entry.block.status == "unreviewed"
    assert (entry.block.reviewed_by, entry.block.reviewed_on) == ("", "")
    # It also does not invent what only a reader of the terms can supply.
    assert (entry.block.terms_url, entry.block.retrieved_on, entry.block.attribution) == (
        "",
        "",
        "",
    )


def test_a_share_alike_license_is_recorded_as_a_fact_with_no_verdict() -> None:
    entry = propose(agency("a", "Open Database License (ODbL); credit the operator."))
    assert entry.block is not None
    assert (entry.block.id, entry.block.share_alike) == ("ODbL-1.0", True)
    assert entry.block.status == "unreviewed"
    assert entry.outcome == OUTCOME_PROPOSED


@pytest.mark.parametrize(
    ("note", "reason"),
    [
        ("", "license_note is empty"),
        ("No stated data license; ask the agency.", "license_note says no license is stated"),
        ("License: https://example.org/terms", "license_note is only a link"),
        (ESTONIA_NOTE, "license_note names terms the vocabulary does not hold"),
        (NVBW_NOTE, "license_note names more than one license: ODbL-1.0, DL-DE-BY-2.0"),
    ],
)
def test_anything_ambiguous_is_needs_review_with_every_term_unknown(note: str, reason: str) -> None:
    """Never a guess, and never a permissive default: unknown stays unknown."""
    entry = propose(agency("a", note))
    assert entry.outcome == OUTCOME_NEEDS_REVIEW
    assert entry.block is not None
    assert entry.block.id == "unknown"
    assert entry.block.status == "needs_review"
    assert entry.block.reviewer_note == reason
    assert entry.block.attribution_required == "unknown"
    assert entry.block.redistribution_allowed == "unknown"
    assert entry.block.share_alike == "unknown"


def test_a_record_that_already_has_a_block_is_left_alone() -> None:
    (existing,) = read_agencies_from_text(
        "agencies:\n"
        "  - id: a\n"
        "    name: A\n"
        "    static_gtfs_url: https://example.org/a.zip\n"
        "    license_note: CC BY 4.0\n"
        "    license:\n"
        "      id: CC0-1.0\n"
        "      attribution_required: false\n"
        "      redistribution_allowed: unknown\n"
        "      share_alike: false\n"
        "      status: unreviewed\n"
    )
    entry = propose(existing)
    assert (entry.outcome, entry.block) == (OUTCOME_ALREADY, None)


def read_agencies_from_text(text: str) -> list[Agency]:
    from scorecard_pipeline.agencies import parse_agencies

    return parse_agencies(yaml.safe_load(text))


def test_the_plan_is_sorted_by_id_and_covers_every_record() -> None:
    plan = plan_migration([agency("b", "CC0"), agency("a", "")])
    assert [e.agency_id for e in plan] == ["a", "b"]


# --- the report -----------------------------------------------------------------


def test_a_report_names_its_mode_and_that_nothing_was_written() -> None:
    plan = plan_migration([agency("a", "CC BY 4.0"), agency("b", ""), agency("c", "ODbL")])
    dry = migration_report(plan, applied=False)
    assert (dry["mode"], dry["wrote_registry"], dry["files_changed"]) == ("dry-run", False, 0)
    assert dry["by_outcome"] == {"proposed": 2, "needs_review": 1, "already_structured": 0}
    assert dry["proposed_by_license"] == {"CC-BY-4.0": 1, "ODbL-1.0": 1}
    assert dry["proposed_share_alike"] == 1
    assert "status: reviewed" in dry["never_written"]
    applied = migration_report(plan, applied=True, files_changed=2)
    assert (applied["mode"], applied["wrote_registry"]) == ("apply", True)


def test_the_summary_says_dry_run_first() -> None:
    plan = plan_migration([agency("a", "CC BY 4.0")])
    text = license_migrate.render_summary(migration_report(plan, applied=False))
    assert text.startswith("License migration DRY RUN: nothing was written.")
    assert "listed with a reuse notice, not excluded" in text


# --- the migration over the committed registry ----------------------------------


@pytest.fixture
def committed(monkeypatch: pytest.MonkeyPatch) -> list[Agency]:
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    return read_agencies()


def test_every_proposal_over_the_committed_registry_is_valid_and_never_a_review(
    committed: list[Agency],
) -> None:
    validator = Draft202012Validator(json_schema())
    plan = plan_migration(committed)
    assert len(plan) == len(committed)
    for entry in plan:
        if entry.block is None:
            continue
        mapping = block_to_mapping(entry.block)
        assert validator.is_valid(mapping), entry.agency_id
        assert check_block(mapping)[0] == entry.block, entry.agency_id
        assert entry.block.status in ("unreviewed", "needs_review")
        assert (entry.block.reviewed_by, entry.block.reviewed_on) == ("", "")


def test_the_proposals_agree_with_the_audit_record_for_record(committed: list[Agency]) -> None:
    """The migration and the audit read the same notes through the same vocabulary, so
    their counts must be identical. It also asserts the share-alike count is measured
    from the registry rather than remembered. Only records without a block are
    compared, so the test stays true after a curator applies the migration."""
    unmigrated = [a for a in committed if a.license_block is None]
    audit = license_audit(unmigrated)
    report = migration_report(plan_migration(unmigrated), applied=False)
    audited_known = {k: v for k, v in audit["by_license"].items() if k != "unknown"}
    assert report["proposed_by_license"] == audited_known
    assert report["by_outcome"][OUTCOME_NEEDS_REVIEW] == audit["by_license"].get("unknown", 0)
    assert report["proposed_share_alike"] == audit["share_alike"]["records"]


def test_a_migrated_registry_lints_with_no_contradiction_and_no_unknown_hidden(
    committed: list[Agency],
) -> None:
    """The negative control at registry scale: after the migration, every unknown
    license is still a finding, and the mechanical proposals contradict nothing."""
    import dataclasses

    stamped = [
        dataclasses.replace(a, license_block=e.block) if e.block is not None else a
        for a, e in zip(
            sorted(committed, key=lambda a: a.id), plan_migration(committed), strict=True
        )
    ]
    findings = lint_ledger(stamped)
    assert not [f for f in findings if f.kind in INCONSISTENT_KINDS], findings[:3]
    assert not [f for f in findings if f.kind == NOTE_DISAGREES]
    unknown_records = {
        a.id for a in stamped if a.license_block is not None and a.license_block.id == "unknown"
    }
    assert unknown_records, "the committed registry should hold records with an unknown license"
    assert unknown_records == {f.agency_id for f in findings if f.kind == LICENSE_UNKNOWN}
    assert NO_LICENSE_BLOCK not in {f.kind for f in findings}


# --- the verb writes nothing unless told to --------------------------------------


def _write_legacy_registry(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / "agencies.yaml"
    path.write_text(
        "# The registry.\n"
        "agencies:\n"
        "  # First record, with a comment above it.\n"
        "  - id: rennes\n"
        "    name: STAR Rennes\n"
        "    static_gtfs_url: https://example.org/rennes.zip\n"
        "    country: FR\n"
        "    subdivision_code: FR-BRE\n"
        "    subdivision_name: Bretagne\n"
        "    license_note: >-\n"
        "      Open Database License (ODbL); credit the operator and\n"
        "      preserve share-alike terms.\n"
        "    # a trailing comment inside the record\n"
        "\n"
        "  # Second record.\n"
        "  - id: waltti\n"
        "    name: Waltti\n"
        "    static_gtfs_url: https://example.org/waltti.zip\n"
        "    license_note: CC BY 4.0; credit Waltti.\n"
        "  - id: bare\n"
        "    name: Bare\n"
        "    static_gtfs_url: https://example.org/bare.zip\n"
        "    license_note: No stated data license.\n"
        "    rt_note: 'no realtime'\n"
    )
    return path


def test_the_default_is_a_dry_run_that_writes_nothing(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline.cli import main

    path = _write_legacy_registry(isolated_repo_root)
    before = path.read_bytes()
    assert main(["license-migrate"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("License migration DRY RUN: nothing was written.")
    assert "proposed\twaltti\tUS\tCC-BY-4.0\tshare_alike=false" in out
    assert "proposed\trennes\tFR\tODbL-1.0\tshare_alike=true" in out
    assert "needs_review\tbare\tUS\tunknown\tshare_alike=unknown" in out
    assert path.read_bytes() == before


def test_the_dry_run_json_says_it_wrote_nothing(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline.cli import main

    _write_legacy_registry(isolated_repo_root)
    assert main(["license-migrate", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert (report["mode"], report["wrote_registry"], report["files_changed"]) == (
        "dry-run",
        False,
        0,
    )
    assert len(report["rows"]) == 3


# --- applying, on a scratch copy only --------------------------------------------


def test_apply_inserts_blocks_keeps_every_other_line_and_is_idempotent(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline.cli import main

    path = _write_legacy_registry(isolated_repo_root)
    original = path.read_text()
    assert main(["license-migrate", "--apply"]) == 0
    assert "License migration APPLIED: 1 registry file(s) written." in capsys.readouterr().out

    migrated = path.read_text()
    added = [
        line[2:]
        for line in difflib.ndiff(original.splitlines(), migrated.splitlines())
        if line.startswith("+ ")
    ]
    removed = [
        line
        for line in difflib.ndiff(original.splitlines(), migrated.splitlines())
        if line.startswith("- ")
    ]
    assert removed == [], "the migration must only add lines"
    assert added.count("    license:") == 3
    # Comments and the trailing blank line survive where they were.
    assert "  # First record, with a comment above it." in migrated
    assert "    # a trailing comment inside the record" in migrated
    assert migrated.index("    license:") > migrated.index("# a trailing comment inside")

    loaded = {a.id: a for a in read_agencies()}
    assert loaded["rennes"].license_block is not None
    assert loaded["rennes"].license_block.id == "ODbL-1.0"
    assert loaded["rennes"].license_block.share_alike is True
    assert loaded["bare"].license_block is not None
    assert loaded["bare"].license_block.id == "unknown"
    assert loaded["bare"].license_block.share_alike == "unknown"
    assert loaded["waltti"].license_note == "CC BY 4.0; credit Waltti."

    # Running it twice changes nothing the second time.
    once = path.read_bytes()
    assert main(["license-migrate", "--apply"]) == 0
    assert "nothing to write" in capsys.readouterr().out
    assert path.read_bytes() == once
    assert main(["license-migrate", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["by_outcome"] == {
        "proposed": 0,
        "needs_review": 0,
        "already_structured": 3,
    }


def test_apply_does_not_touch_a_record_that_already_has_a_block(isolated_repo_root: Path) -> None:
    path = _write_legacy_registry(isolated_repo_root)
    text = path.read_text().replace(
        "    license_note: CC BY 4.0; credit Waltti.\n",
        "    license_note: CC BY 4.0; credit Waltti.\n"
        "    license:\n"
        "      id: CC-BY-4.0\n"
        "      attribution_required: true\n"
        "      redistribution_allowed: true\n"
        "      share_alike: false\n"
        "      status: reviewed\n"
        "      reviewed_by: curator\n"
        '      reviewed_on: "2026-09-01"\n',
    )
    path.write_text(text)

    assert apply_migration(plan_migration(read_agencies())) == 1
    after = {a.id: a for a in read_agencies()}
    reviewed = after["waltti"].license_block
    assert reviewed is not None
    assert (reviewed.status, reviewed.reviewed_by, reviewed.redistribution_allowed) == (
        "reviewed",
        "curator",
        True,
    )


def _write_two_shards(root: Path) -> tuple[Path, Path]:
    registry = root / "registry"
    registry.mkdir(parents=True)
    (registry / "index.yaml").write_text("shards:\n  - registry/one.yaml\n  - registry/two.yaml\n")
    one = registry / "one.yaml"
    two = registry / "two.yaml"
    body = (
        "agencies:\n"
        "  - id: {id}\n"
        "    name: {id}\n"
        "    static_gtfs_url: https://example.org/{id}.zip\n"
        "    license_note: CC BY 4.0\n"
    )
    one.write_text(body.format(id="one"))
    two.write_text(body.format(id="two"))
    return one, two


def test_apply_is_all_or_nothing_when_a_record_cannot_be_placed(isolated_repo_root: Path) -> None:
    one, two = _write_two_shards(isolated_repo_root)
    before = (one.read_bytes(), two.read_bytes())
    plan = plan_migration(read_agencies())
    ghost = MigrationEntry("ghost", "US", True, OUTCOME_PROPOSED, plan[0].block, "not in any shard")
    with pytest.raises(MigrationError, match="ghost"):
        apply_migration([*plan, ghost])
    assert (one.read_bytes(), two.read_bytes()) == before


def test_apply_writes_nothing_when_an_edit_fails_its_own_verification(
    isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control for the verifier: a broken insertion must be caught
    before any file changes, in whichever shard it happens."""
    one, two = _write_two_shards(isolated_repo_root)
    before = (one.read_bytes(), two.read_bytes())
    real = license_ledger.block_to_yaml_lines

    def sabotage(block: Any, *, indent: int) -> list[str]:
        lines = real(block, indent=indent)
        return [*lines, f"{' ' * indent}rt_note: injected"]

    monkeypatch.setattr("scorecard_pipeline.license_migrate.block_to_yaml_lines", sabotage)
    with pytest.raises(MigrationError, match="changed beyond its license block"):
        apply_migration(plan_migration(read_agencies()))
    assert (one.read_bytes(), two.read_bytes()) == before


def test_apply_over_the_whole_committed_registry_on_a_scratch_copy(
    isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The strongest check available without rewriting the registry: apply to a copy
    of every shard, then prove each record equals its old self plus its block, no
    line was removed, and a second run is a no-op. The committed files are never
    written."""
    shutil.copytree(REPO_ROOT / "registry", isolated_repo_root / "registry")
    original = {
        p.relative_to(isolated_repo_root): p.read_text(encoding="utf-8")
        for p in (isolated_repo_root / "registry").rglob("*.yaml")
    }
    committed_before = {p: p.read_bytes() for p in (REPO_ROOT / "registry").rglob("*.yaml")}

    plan = plan_migration(read_agencies())
    writable = {e.agency_id: e for e in plan if e.outcome != OUTCOME_ALREADY}
    changed = apply_migration(plan)
    assert changed > 0 or not writable

    for rel, old in original.items():
        new = (isolated_repo_root / rel).read_text(encoding="utf-8")
        assert not [
            line
            for line in difflib.ndiff(old.splitlines(), new.splitlines())
            if line.startswith("- ")
        ], rel
        if rel.name == "index.yaml":
            assert new == old
            continue
        before_records = yaml.safe_load(old)["agencies"]
        after_records = yaml.safe_load(new)["agencies"]
        assert len(before_records) == len(after_records)
        for was, now in zip(before_records, after_records, strict=True):
            expected = dict(was)
            if was["id"] in writable:
                block = writable[was["id"]].block
                assert block is not None
                expected["license"] = block_to_mapping(block)
            assert now == expected

    reloaded = read_agencies()
    assert all(a.license_block is not None for a in reloaded)
    snapshot = {p: p.read_bytes() for p in (isolated_repo_root / "registry").rglob("*.yaml")}
    assert apply_migration(plan_migration(reloaded)) == 0
    assert {
        p: p.read_bytes() for p in (isolated_repo_root / "registry").rglob("*.yaml")
    } == snapshot
    assert {p: p.read_bytes() for p in (REPO_ROOT / "registry").rglob("*.yaml")} == committed_before
