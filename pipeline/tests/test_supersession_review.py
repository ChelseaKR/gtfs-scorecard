"""A retirement that may not be the same agency is held until a person decides.

The regression these guard is the one a human caught by reading a table: a
Connecticut agency retired into a record filed in California. Nothing else in
the pipeline could see it, because both records are well-formed and the alias
chain resolves. The last test in this file is the merge gate itself: it reads
the repository's own registry and review file, so an unreviewed flagged
retirement fails the build instead of publishing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scorecard_pipeline.agencies import read_agencies
from scorecard_pipeline.config import Agency
from scorecard_pipeline.supersession_review import (
    DIFFERENT_COUNTRY,
    DIFFERENT_SUBDIVISION,
    KEEP_SEPARATE,
    NAME_NOT_A_RENAME,
    RETIRE,
    SUBDIVISION_UNKNOWN,
    ReviewedRetirement,
    SupersessionReviewError,
    approved,
    parse_review,
    read_review,
    reads_as_a_rename,
    recorded_retirements,
    review_entry_yaml,
    review_flags,
    review_problems,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _agency(
    agency_id: str,
    name: str,
    *,
    subdivision: str = "US-CA",
    country: str = "US",
    alias_of: str = "",
    feed_status: str = "active",
) -> Agency:
    return Agency(
        id=agency_id,
        name=name,
        static_gtfs_url=f"https://ex.org/{agency_id}.zip",
        alias_of=alias_of,
        feed_status=feed_status,
        country=country,
        subdivision_code=subdivision,
    )


@pytest.mark.parametrize(
    ("retired", "successor"),
    [
        # The same words, one of them respelled or pluralized.
        ("Gloversville Transit Services", "Gloversville Transit System"),
        ("Boston Harbor Islands Ferries", "Boston Harbor Islands Ferry"),
        # A brand, a place, or a mode qualifier added or dropped.
        ("Middletown Area Transit", "Middletown Area Transit (MAT)"),
        ("JTRAN", "City of Jackson (JTRAN)"),
        ("San Mateo County Transit District (samTrans)", "SamTrans"),
        ("Avon Transit Flex", "Avon Transit"),
        ("Bloom Tours", "Bloom Bus"),
        # An acronym expanded into the name it stands for.
        ("UTA", "Utah Transit Authority (UTA)"),
        ("CDTA", "Capital District Transportation Authority"),
        ("Transit Authority of River City", "TARC"),
        # Nothing distinctive to compare: generic words only.
        ("Transit Authority", "Regional Transit"),
    ],
)
def test_a_rename_keeps_something_distinctive_in_common(retired: str, successor: str) -> None:
    assert reads_as_a_rename(retired, successor)


@pytest.mark.parametrize(
    ("retired", "successor"),
    [
        ("Duarte Transit", "Foothill Transit"),
        ("Town of Telluride", "San Miguel County"),
        ("The Current", "Southeast Vermont Transit"),
        ("Kayak Transit (CTUIR)", "City of Milton-Freewater Public Transportation"),
        ("Sarasota County Area Transit", "Breeze Transit"),
        ("The JO", "Johnson County Transit"),
    ],
)
def test_a_merger_or_a_rebrand_does_not_read_as_a_rename(retired: str, successor: str) -> None:
    assert not reads_as_a_rename(retired, successor)


def test_a_successor_in_another_state_is_flagged_even_when_the_name_fits() -> None:
    """The Norwalk case: one name, two cities, two states, one record.

    The names are consistent with a rename, so a name check alone reads this as
    ordinary. The state line is the only thing that says otherwise, which is why
    it is checked on its own.
    """
    retired = _agency("norwalk-transit-district", "Norwalk Transit District", subdivision="US-CT")
    successor = _agency("norwalk-transit-system-nts", "Norwalk Transit System (NTS)")

    assert reads_as_a_rename(retired.name, successor.name)
    assert review_flags(retired, successor) == (DIFFERENT_SUBDIVISION,)


def test_a_successor_in_another_country_is_flagged() -> None:
    retired = _agency("border-transit", "Border Transit", country="US", subdivision="US-WA")
    successor = _agency("border-transit-ca", "Border Transit", country="CA", subdivision="CA-BC")

    assert review_flags(retired, successor) == (DIFFERENT_COUNTRY, DIFFERENT_SUBDIVISION)


def test_a_missing_subdivision_is_reported_but_never_blocks() -> None:
    """A gap in the registry is not evidence of a wrong retirement.

    Blocking on it would teach people to type a location in to clear the gate,
    which is worse than the gap.
    """
    retired = _agency("cue-bus", "CUE Bus", subdivision="")
    successor = _agency("fairfax-cue-bus", "Fairfax CUE Bus (CUE)", subdivision="US-VA")

    assert review_flags(retired, successor) == (SUBDIVISION_UNKNOWN,)
    assert review_problems([retired, successor], {}) == []


def test_a_plain_rename_in_one_state_needs_no_decision() -> None:
    retired = _agency("gloversville-transit-services", "Gloversville Transit Services")
    successor = _agency("gloversville-transit-system", "Gloversville Transit System")

    assert review_flags(retired, successor) == ()


def _retired_pair(**flags: str) -> list[Agency]:
    """A registry of two records, the first retired into the second."""
    return [
        _agency(
            "the-current",
            "The Current",
            subdivision=flags.get("retired_subdivision", "US-VT"),
            alias_of="rockingham-moover",
            feed_status="deprecated",
        ),
        _agency(
            "rockingham-moover",
            flags.get("successor_name", "Rockingham MOOver"),
            subdivision=flags.get("successor_subdivision", "US-VT"),
        ),
    ]


def test_a_flagged_retirement_with_no_decision_fails_the_build() -> None:
    problems = review_problems(_retired_pair(), {})

    assert len(problems) == 1
    assert "the-current retires into rockingham-moover" in problems[0]
    assert "supersession-review.yaml records no decision" in problems[0]


def test_an_approved_retirement_passes() -> None:
    reviewed = {
        "the-current": ReviewedRetirement(
            agency_id="the-current",
            successor_id="rockingham-moover",
            flags=(NAME_NOT_A_RENAME,),
            decision=RETIRE,
            evidence="the successor's feed carries this record's whole route set",
        )
    }

    assert review_problems(_retired_pair(), reviewed) == []


def test_a_record_kept_separate_may_not_be_retired_anyway() -> None:
    """The refusal has to stick, or next month's sync silently re-applies it."""
    reviewed = {
        "the-current": ReviewedRetirement(
            agency_id="the-current",
            successor_id="rockingham-moover",
            flags=(NAME_NOT_A_RENAME,),
            decision=KEEP_SEPARATE,
            evidence="two different agencies",
        )
    }

    problems = review_problems(_retired_pair(), reviewed)

    assert problems == [
        "the-current is recorded in supersession-review.yaml as kept separate from "
        "rockingham-moover, but the registry retires it into rockingham-moover."
    ]


def test_a_decision_stops_covering_a_retirement_whose_reasons_changed() -> None:
    reviewed = {
        "the-current": ReviewedRetirement(
            agency_id="the-current",
            successor_id="rockingham-moover",
            flags=(NAME_NOT_A_RENAME,),
            decision=RETIRE,
            evidence="same operation, different brand",
        )
    }

    problems = review_problems(_retired_pair(successor_subdivision="US-NH"), reviewed)

    assert problems == [
        "the-current was reviewed for name_not_a_rename but is now flagged for "
        "different_subdivision, name_not_a_rename. Review it again and update the entry."
    ]


def test_a_decision_that_names_a_different_successor_is_not_carried_over() -> None:
    reviewed = {
        "the-current": ReviewedRetirement(
            agency_id="the-current",
            successor_id="somewhere-else",
            flags=(NAME_NOT_A_RENAME,),
            decision=RETIRE,
            evidence="reviewed against a different pairing",
        )
    }

    problems = review_problems(_retired_pair(), reviewed)

    assert problems == [
        "the-current was reviewed as retiring into somewhere-else, but the registry "
        "retires it into rockingham-moover. Review the new pairing."
    ]


def test_a_decision_left_behind_after_the_flag_cleared_is_removed() -> None:
    reviewed = {
        "the-current": ReviewedRetirement(
            agency_id="the-current",
            successor_id="rockingham-moover",
            flags=(NAME_NOT_A_RENAME,),
            decision=RETIRE,
            evidence="same operation, different brand",
        )
    }

    problems = review_problems(_retired_pair(successor_name="The Current"), reviewed)

    assert problems == [
        "the-current is no longer flagged for review, so its supersession-review.yaml "
        "entry is stale. Remove the entry."
    ]


def test_an_approval_for_a_retirement_the_registry_does_not_record_is_stale() -> None:
    registry = [_agency("the-current", "The Current"), _agency("rockingham-moover", "MOOver")]
    reviewed = {
        "the-current": ReviewedRetirement(
            agency_id="the-current",
            successor_id="rockingham-moover",
            flags=(NAME_NOT_A_RENAME,),
            decision=RETIRE,
            evidence="approved but never applied",
        )
    }

    problems = review_problems(registry, reviewed)

    assert problems == [
        "supersession-review.yaml approves retiring the-current into rockingham-moover, "
        "but the registry does not retire it. Apply the retirement or remove the entry."
    ]


def test_a_decision_about_a_record_that_left_the_registry_is_removed() -> None:
    reviewed = {
        "gone": ReviewedRetirement(
            agency_id="gone",
            successor_id="rockingham-moover",
            flags=(NAME_NOT_A_RENAME,),
            decision=KEEP_SEPARATE,
            evidence="not the same agency",
        )
    }

    problems = review_problems([_agency("rockingham-moover", "MOOver")], reviewed)

    assert problems == [
        "supersession-review.yaml decides gone, which is not in the registry. Remove the entry."
    ]


def test_a_refusal_naming_a_successor_that_left_the_registry_is_removed() -> None:
    reviewed = {
        "the-current": ReviewedRetirement(
            agency_id="the-current",
            successor_id="gone",
            flags=(DIFFERENT_SUBDIVISION,),
            decision=KEEP_SEPARATE,
            evidence="not the same agency",
        )
    }

    problems = review_problems([_agency("the-current", "The Current")], reviewed)

    assert problems == [
        "supersession-review.yaml keeps the-current separate from gone, which is not "
        "in the registry. Remove the entry."
    ]


def test_a_standing_refusal_of_a_retirement_nobody_applied_is_left_alone() -> None:
    """The Norwalk decision: the record keeps its page, and the file says why."""
    registry = [
        _agency("norwalk-transit-system-nts", "Norwalk Transit System (NTS)"),
        _agency("norwalk-transit-system-nts-2242", "Norwalk Transit District", subdivision="US-CT"),
    ]
    reviewed = {
        "norwalk-transit-system-nts": ReviewedRetirement(
            agency_id="norwalk-transit-system-nts",
            successor_id="norwalk-transit-system-nts-2242",
            flags=(DIFFERENT_SUBDIVISION,),
            decision=KEEP_SEPARATE,
            evidence="two different cities named Norwalk, in two states",
        )
    }

    assert review_problems(registry, reviewed) == []


def test_recorded_retirements_ignores_an_alias_that_is_not_a_retirement() -> None:
    """An alias without `feed_status: deprecated` is a duplicate endpoint, not this."""
    registry = [
        _agency("duplicate-endpoint", "Duplicate Endpoint", alias_of="main-record"),
        _agency("main-record", "Main Record"),
    ]

    assert recorded_retirements(registry) == []


def test_recorded_retirements_ignores_a_successor_that_is_not_in_the_registry() -> None:
    registry = [_agency("orphan", "Orphan", alias_of="missing", feed_status="deprecated")]

    assert recorded_retirements(registry) == []


def test_approved_requires_the_same_pairing_and_the_same_reasons() -> None:
    entry = ReviewedRetirement(
        agency_id="the-current",
        successor_id="rockingham-moover",
        flags=(NAME_NOT_A_RENAME,),
        decision=RETIRE,
        evidence="same operation",
    )

    assert approved(entry, "rockingham-moover", (NAME_NOT_A_RENAME,))
    assert not approved(entry, "somewhere-else", (NAME_NOT_A_RENAME,))
    assert not approved(entry, "rockingham-moover", (DIFFERENT_SUBDIVISION, NAME_NOT_A_RENAME))
    assert not approved(None, "rockingham-moover", (NAME_NOT_A_RENAME,))
    # Nothing to decide: an unflagged retirement applies without an entry.
    assert approved(None, "rockingham-moover", ())
    # A refusal never authorizes the retirement it refuses.
    assert not approved(
        ReviewedRetirement(
            agency_id="the-current",
            successor_id="rockingham-moover",
            flags=(NAME_NOT_A_RENAME,),
            decision=KEEP_SEPARATE,
            evidence="not the same agency",
        ),
        "rockingham-moover",
        (NAME_NOT_A_RENAME,),
    )


def test_parse_review_reads_decisions_by_retired_record() -> None:
    text = (
        "reviewed:\n"
        "  - agency_id: the-current\n"
        "    successor_id: rockingham-moover\n"
        "    flags: [name_not_a_rename]\n"
        "    decision: retire\n"
        "    evidence: the successor's feed carries this record's routes\n"
    )

    reviewed = parse_review(text)

    assert reviewed["the-current"].decision == RETIRE
    assert reviewed["the-current"].flags == (NAME_NOT_A_RENAME,)
    assert reviewed["the-current"].evidence.startswith("the successor's feed")


def test_parse_review_treats_an_empty_file_as_no_decisions() -> None:
    assert parse_review("") == {}


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("decisions: []\n", "must contain only a top-level 'reviewed:' list"),
        ("reviewed:\n  - not a mapping\n", "entry 1: must be a mapping"),
        (
            "reviewed:\n  - agency_id: a\n    successor_id: b\n    flags: [name_not_a_rename]\n"
            "    decision: retire\n    evidence: why\n    note: extra\n",
            "unknown field(s) note",
        ),
        (
            "reviewed:\n  - agency_id: a\n    successor_id: b\n    flags: [name_not_a_rename]\n"
            "    decision: retire\n",
            "evidence must be a non-empty string",
        ),
        (
            "reviewed:\n  - agency_id: a\n    successor_id: b\n    flags: [name_not_a_rename]\n"
            "    decision: maybe\n    evidence: why\n",
            "decision must be one of",
        ),
        (
            "reviewed:\n  - agency_id: a\n    successor_id: b\n    flags: []\n"
            "    decision: retire\n    evidence: why\n",
            "flags must be a non-empty list",
        ),
        (
            "reviewed:\n  - agency_id: a\n    successor_id: b\n    flags: [looks_odd]\n"
            "    decision: retire\n    evidence: why\n",
            "unknown flag(s) looks_odd",
        ),
        (
            "reviewed:\n  - agency_id: a\n    successor_id: b\n    flags: [name_not_a_rename]\n"
            "    decision: retire\n    evidence: why\n"
            "  - agency_id: a\n    successor_id: c\n    flags: [name_not_a_rename]\n"
            "    decision: retire\n    evidence: why\n",
            "a is decided twice",
        ),
    ],
)
def test_parse_review_rejects_a_file_it_cannot_act_on(text: str, message: str) -> None:
    with pytest.raises(SupersessionReviewError) as excinfo:
        parse_review(text)
    assert message in str(excinfo.value)


def test_read_review_treats_a_missing_file_as_no_decisions(tmp_path: Path) -> None:
    assert read_review(tmp_path) == {}


def test_read_review_reads_the_repository_file() -> None:
    reviewed = read_review(REPO_ROOT)

    assert reviewed["norwalk-transit-system-nts"].decision == KEEP_SEPARATE
    assert all(entry.evidence.strip() for entry in reviewed.values())


def test_review_entry_yaml_is_a_block_the_file_accepts() -> None:
    block = review_entry_yaml("the-current", "rockingham-moover", (NAME_NOT_A_RENAME,))

    reviewed = parse_review(f"reviewed:\n{block}")

    assert reviewed["the-current"].flags == (NAME_NOT_A_RENAME,)
    assert reviewed["the-current"].decision == RETIRE


def test_the_registry_records_no_retirement_nobody_reviewed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The merge gate. A flagged retirement fails the build until it is decided.

    This is the check that would have stopped a Connecticut agency shipping as
    Californian, and it runs against the repository's own registry rather than a
    fixture, so it fails on the next batch too.
    """
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))

    problems = review_problems(read_agencies(), read_review(REPO_ROOT))

    assert problems == []


def test_no_retirement_in_the_registry_crosses_a_state_line_unreviewed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Named separately from the gate because it is the specific defect found.

    Every recorded retirement either stays inside one subdivision or has a
    decision in the review file saying why crossing one is right.
    """
    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    reviewed = read_review(REPO_ROOT)

    crossing = [
        (retired.id, successor.id)
        for retired, successor in recorded_retirements(read_agencies())
        if DIFFERENT_SUBDIVISION in review_flags(retired, successor)
        or DIFFERENT_COUNTRY in review_flags(retired, successor)
    ]

    assert [pair for pair in crossing if pair[0] not in reviewed] == []
