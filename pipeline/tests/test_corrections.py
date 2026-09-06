"""A grade taken back has to stay taken back, and has to be said out loud.

The refusal that landed on 2026-09-01 stopped the scorer minting a grade for a
feed it could not read. It did nothing about the nineteen already published, and
it made them permanent: a refused agency writes no artifact, so the daily run
leaves the old letter exactly where it was and warns into a log. Nineteen named
transit agencies stayed publicly graded F on data nobody had read.

Deleting the files is not enough on its own. ``publish.reindex`` rebuilds
``latest.json`` from the newest dated artifact beside it, so a retraction made by
hand comes back on the next run. The withdrawal has to be something the pipeline
knows about, which is what ``corrections.yaml`` is.

These tests pin four things:

* the record parses strictly, because it names real agencies and a malformed
  entry must fail loudly rather than silently withdraw nothing;
* a withdrawal suppresses the current pointers and survives a reindex;
* it lifts by itself when a real measurement arrives, so the correction never
  becomes a permanent gag on an agency whose feed later reads;
* the corpus has no published grade over an empty feed that the record does not
  cover, in either direction.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import corrections
from scorecard_pipeline.artifact_lifecycle import (
    MUTABLE_PUBLIC_ARTIFACT_NAMES,
    reconcile_retired_current_artifacts,
)
from scorecard_pipeline.corrections import (
    CAUSES,
    OUTCOMES,
    CorrectionsError,
    correction_problems,
    grades_a_feed_with_nothing_in_it,
    parse_corrections,
    read_corrections,
    withdrawn_now,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

SHA = "8f4b6006ba4eb0742185b7c934d5596e0ddf287fd171aaa6f7c8089ba7439b16"

ONE_ENTRY = f"""
schema_version: 1
corrections:
  - agency_id: santa-clarita-transit
    agency_name: Santa Clarita Transit
    snapshot_date: "2026-07-16"
    feed_sha256: {SHA}
    grade: F
    score: 26.2
    published_from: "2026-06-16"
    published_until: "2026-09-05"
    cause: tables_in_a_subfolder
    outcome: not_measured
    evidence: >-
      The archive wraps its tables two folders down and holds 364 real stops.
"""


def _artifact(
    agency_id: str = "santa-clarita-transit",
    *,
    date: str = "2026-07-16",
    sha: str = SHA,
    stops: int = 0,
    trips: int = 0,
    grade: str = "F",
) -> dict[str, Any]:
    return {
        "agency": {"id": agency_id, "name": "Santa Clarita Transit"},
        "snapshot_date": date,
        "feed": {"sha256": sha},
        "overall": {"grade": grade, "score": 26.2},
        "categories": {
            "completeness": {
                "status": "measured",
                "score": 0.0,
                "details": {"stops": stops, "trips": trips},
            }
        },
    }


# --- the record parses strictly ----------------------------------------------


def test_one_entry_round_trips() -> None:
    entry = parse_corrections(ONE_ENTRY).withdrawn["santa-clarita-transit"]
    assert entry.grade == "F"
    assert entry.score == 26.2
    assert entry.cause in CAUSES
    assert entry.outcome in OUTCOMES
    assert "364 real stops" in entry.evidence


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("cause: tables_in_a_subfolder", "cause"),
        ("outcome: not_measured", "outcome"),
        ("feed_sha256: " + SHA, "feed_sha256"),
        ('snapshot_date: "2026-07-16"', "snapshot_date"),
    ],
)
def test_a_malformed_field_is_refused_not_ignored(mutation: str, message: str) -> None:
    """A withdrawal that parses to nothing is worse than one that fails."""
    field = mutation.split(":", 1)[0]
    broken = ONE_ENTRY.replace(mutation, f"{field}: not-a-valid-value")
    with pytest.raises(CorrectionsError, match=message):
        parse_corrections(broken)


def test_an_entry_with_no_evidence_is_refused() -> None:
    """These name real agencies. A withdrawal with no stated reason is not reviewable."""
    broken = "\n".join(
        line for line in ONE_ENTRY.splitlines() if "evidence" not in line and "364" not in line
    )
    with pytest.raises(CorrectionsError, match="evidence"):
        parse_corrections(broken)


def test_an_unknown_field_is_refused() -> None:
    with pytest.raises(CorrectionsError, match="unknown field"):
        parse_corrections(ONE_ENTRY + "    notes: something\n")


def test_the_same_agency_cannot_be_withdrawn_twice() -> None:
    doubled = ONE_ENTRY + ONE_ENTRY.split("corrections:", 1)[1]
    with pytest.raises(CorrectionsError, match="withdrawn twice"):
        parse_corrections(doubled)


def test_a_missing_file_is_no_withdrawals_not_an_error(tmp_path: Path) -> None:
    record = read_corrections(tmp_path)
    assert record.withdrawn == {} and record.pending == {}


# --- a withdrawal suppresses, and lifts by itself ----------------------------


def test_the_withdrawal_matches_only_the_record_it_names() -> None:
    entry = parse_corrections(ONE_ENTRY).withdrawn["santa-clarita-transit"]
    assert entry.withdraws(_artifact()) is True
    assert entry.withdraws(_artifact(date="2026-09-04")) is False
    assert entry.withdraws(_artifact(sha="0" * 64)) is False


def test_a_withdrawn_agency_is_named_while_the_old_record_is_newest(tmp_path: Path) -> None:
    agency_dir = tmp_path / "santa-clarita-transit"
    agency_dir.mkdir()
    (agency_dir / "2026-07-16.json").write_text(json.dumps(_artifact()))
    (agency_dir / "latest.json").write_text(json.dumps(_artifact()))
    assert withdrawn_now(parse_corrections(ONE_ENTRY).withdrawn, tmp_path) == (
        "santa-clarita-transit",
    )


def test_the_withdrawal_lifts_when_a_real_measurement_arrives(tmp_path: Path) -> None:
    """The point of scoping it to one record.

    A correction is not a permanent gag. When a run reads the feed and writes a
    newer artifact, that measurement publishes and the correction stays beside
    it as the public record of the change.
    """
    agency_dir = tmp_path / "santa-clarita-transit"
    agency_dir.mkdir()
    (agency_dir / "2026-07-16.json").write_text(json.dumps(_artifact()))
    (agency_dir / "2026-09-10.json").write_text(
        json.dumps(_artifact(date="2026-09-10", sha="a" * 64, stops=364, trips=898, grade="C"))
    )
    assert withdrawn_now(parse_corrections(ONE_ENTRY).withdrawn, tmp_path) == ()


def test_reconcile_removes_a_withdrawn_agency_current_pointers(tmp_path: Path) -> None:
    """The file operation, with no registry loaded at all.

    Twelve of the nineteen are in no registry, which is exactly why the
    withdrawal cannot be derived from registry membership.
    """
    agency_dir = tmp_path / "santa-clarita-transit"
    agency_dir.mkdir()
    for name in MUTABLE_PUBLIC_ARTIFACT_NAMES:
        (agency_dir / name).write_text("{}")
    (agency_dir / "2026-07-16.json").write_text(json.dumps(_artifact()))

    plan = reconcile_retired_current_artifacts(tmp_path, {}, ("santa-clarita-transit",))

    assert plan.agency_ids == ("santa-clarita-transit",)
    assert plan.removed_files == len(MUTABLE_PUBLIC_ARTIFACT_NAMES)
    assert not any((agency_dir / name).exists() for name in MUTABLE_PUBLIC_ARTIFACT_NAMES)
    # Dated evidence is untouched.
    assert (agency_dir / "2026-07-16.json").is_file()
    assert json.loads(plan.manifest_path.read_text())["agency_ids"] == ["santa-clarita-transit"]


def test_reconcile_without_a_registry_still_withdraws_nothing_else(tmp_path: Path) -> None:
    """Narrowness. An empty registry must not turn every directory into a deletion."""
    for name in ("santa-clarita-transit", "some-other-agency"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "latest.json").write_text("{}")

    reconcile_retired_current_artifacts(tmp_path, {}, ("santa-clarita-transit",))

    assert not (tmp_path / "santa-clarita-transit" / "latest.json").exists()
    assert (tmp_path / "some-other-agency" / "latest.json").is_file()


def test_a_reserved_namespace_can_never_be_withdrawn(tmp_path: Path) -> None:
    assert reconcile_retired_current_artifacts(tmp_path, {}, ("rollups", "..")).agency_ids == ()


# --- the corpus, in both directions ------------------------------------------


def test_the_shipped_record_parses() -> None:
    record = read_corrections(REPO_ROOT)
    assert record.withdrawn, "corrections.yaml records no withdrawals"
    assert all(entry.evidence for entry in record.withdrawn.values())
    assert all(reason for reason in record.pending.values())


def test_no_published_grade_over_an_empty_feed_is_left_uncorrected() -> None:
    """The ratchet, in the direction that matters to an agency.

    A published ``latest.json`` that grades a feed with no stops and no trips is
    a letter derived from a feed nobody read. ``score_feed_content`` refuses to
    produce one now, so any that remain arrived before that refusal and must be
    named in ``corrections.yaml`` rather than left standing.
    """
    artifacts = REPO_ROOT / "data" / "artifacts"
    record = read_corrections(REPO_ROOT)
    stranded = sorted(
        path.parent.name
        for path in artifacts.glob("*/latest.json")
        if not record.covers(path.parent.name)
        and grades_a_feed_with_nothing_in_it(json.loads(path.read_text()))
    )
    assert not stranded, (
        f"{len(stranded)} published scorecard(s) grade a feed with no stops and no "
        "trips and appear nowhere in corrections.yaml: " + ", ".join(stranded)
    )


def test_every_withdrawn_grade_is_actually_gone_from_the_published_corpus() -> None:
    """The other direction. A record that says withdrawn while the file is still
    there is worse than no record at all."""
    problems = correction_problems(read_corrections(REPO_ROOT), REPO_ROOT / "data" / "artifacts")
    assert problems == []


def test_the_index_does_not_still_list_a_withdrawn_grade() -> None:
    """Deleting latest.json is only half a withdrawal; the index is the other half.

    ``rebuild_index`` leaves a withdrawn id out of ``index.json`` on purpose
    (``publish._indexable_agency_dirs``), so the committed snapshot must agree.
    An id that stays in the index with its current pointers gone is not a
    quieter version of a withdrawal, it is a corpus that contradicts itself:
    ``activation.materialize_local_current_artifacts`` walks the index and reads
    each id's ``latest.json``, so a stale entry aborts the site build with
    "authoritative current artifact is malformed" -- the deploy and
    accessibility workflows both run that materializer before rendering.
    """
    artifacts = REPO_ROOT / "data" / "artifacts"
    indexed = set(json.loads((artifacts / "index.json").read_text())["agencies"])
    still_listed = sorted(indexed & set(read_corrections(REPO_ROOT).withdrawn))
    assert not still_listed, (
        f"{len(still_listed)} withdrawn grade(s) are still in index.json: "
        + ", ".join(still_listed)
    )


def test_every_indexed_agency_still_has_a_current_scorecard() -> None:
    """The same parity, stated without reference to why an id might be missing.

    Whatever removed the file -- a withdrawal, a retirement, a hand edit -- an
    index entry with no ``latest.json`` behind it fails the materializer, and it
    fails it in a job that runs long after the change that caused it.
    """
    artifacts = REPO_ROOT / "data" / "artifacts"
    indexed = json.loads((artifacts / "index.json").read_text())["agencies"]
    assert len(indexed) > 1000, "the index was not read; this check is not running"
    orphaned = sorted(a for a in indexed if not (artifacts / a / "latest.json").exists())
    assert not orphaned, (
        f"{len(orphaned)} agency id(s) are in index.json with no latest.json beside "
        "them: " + ", ".join(orphaned)
    )


def test_the_corpus_check_is_actually_reading_artifacts() -> None:
    """Guard on the two ratchets above: neither can pass by reading nothing."""
    artifacts = REPO_ROOT / "data" / "artifacts"
    assert sum(1 for _ in artifacts.glob("*/latest.json")) > 1000


def test_a_not_measured_entry_that_lost_its_evidence_is_reported(tmp_path: Path) -> None:
    """A record that is still a listing keeps its dated artifacts.

    `not_measured` says the feed cannot be read *yet*: the listing stands and a
    later run supersedes the withdrawal. Its dated artifacts are the evidence of
    what was published while it was wrong, and they are deliberately not deleted,
    so their absence means something removed them that should not have.
    """
    problems = correction_problems(parse_corrections(ONE_ENTRY), tmp_path)
    assert problems and "artifact directory is gone" in problems[0]


def test_a_delisted_entry_may_have_no_artifact_directory_left(tmp_path: Path) -> None:
    """The completed state of the twelve, and it must not read as a stale entry.

    Twelve of the nineteen withdrawn records are in no registry, and their
    directories held nothing but the four current pointers the withdrawal
    removes: no dated artifact was ever written for them. So a completed
    withdrawal takes the directory with it, and git does not carry an empty
    directory, so the id leaves the tree.

    This is the shape that passed on the machine the change was written on and
    failed in CI, because the local checkout still had the emptied directories
    sitting on disk. `tmp_path` has no directory at all, which is what a fresh
    clone sees.
    """
    delisted = ONE_ENTRY.replace("outcome: not_measured", "outcome: delisted")
    assert correction_problems(parse_corrections(delisted), tmp_path) == []


def test_grades_a_feed_with_nothing_in_it_is_narrow() -> None:
    """It must not catch a real feed that scored badly for real reasons."""
    assert grades_a_feed_with_nothing_in_it(_artifact()) is True
    assert grades_a_feed_with_nothing_in_it(_artifact(stops=364, trips=898)) is False
    assert grades_a_feed_with_nothing_in_it({"categories": {}, "overall": {}}) is False


def test_every_cause_and_outcome_has_reader_facing_wording() -> None:
    """These strings reach a page an agency may read about itself."""
    for entry in read_corrections(REPO_ROOT).withdrawn.values():
        assert entry.cause_text and entry.cause_text[0].islower()
        assert entry.outcome_text
    assert set(CAUSES) == {corrections.TABLES_IN_A_SUBFOLDER, corrections.NO_SCHEDULE_TABLES}
    assert set(OUTCOMES) == {corrections.NOT_MEASURED, corrections.DELISTED}


# --- the page a reader who saw the old grade lands on ------------------------


def test_the_corrections_page_names_the_agency_the_grade_and_the_period() -> None:
    """The owner's requirement, checked as output rather than as intent.

    A reader who saw the F has to be able to find out what happened to it. Names
    the site never prints are names nobody can look up, so the page is asserted
    against the shipped record rather than a fixture.
    """
    from scorecard_pipeline.render_site import _render_corrections
    from scorecard_pipeline.site_shell import esc

    record = read_corrections(REPO_ROOT)
    entries = sorted(record.withdrawn.values(), key=lambda entry: entry.agency_name)
    html = _render_corrections(entries)

    santa_clarita = record.withdrawn["santa-clarita-transit"]
    assert "Santa Clarita Transit" in html
    assert santa_clarita.published_from in html and santa_clarita.published_until in html
    assert "26.2" in html
    assert esc(santa_clarita.cause_text) in html
    assert esc(santa_clarita.outcome_text) in html
    assert esc(santa_clarita.evidence) in html
    # Every withdrawn agency is named, not just a count.
    for entry in entries:
        assert esc(entry.agency_name) in html
    # And the page says what to do about it.
    assert "listing-policy.md" in html


def test_the_corrections_page_renders_with_nothing_withdrawn() -> None:
    """A standing commitment, not a page that appears after a bad enough mistake."""
    from scorecard_pipeline.render_site import _render_corrections

    html = _render_corrections([])
    assert "No published grade has been withdrawn" in html
