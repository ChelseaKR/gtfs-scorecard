"""Which recorded retirements a person has to sign off on before they publish.

A retirement (``alias_of`` plus ``feed_status: deprecated``) stops one record
publishing a current grade and sends its readers to another record's page. The
Mobility Database's ``redirect.id`` is right often enough to follow in bulk, but
it cannot distinguish "this agency renamed itself" from "these two records look
alike". When it gets that wrong the site publishes one agency's grade under
another agency's name, in another agency's state, and nothing in the pipeline
notices: both records are well-formed, and the alias chain resolves.

So a retirement is checked for the two shapes that mean "this may not be the
same agency at all":

- the successor is in a **different subdivision or country** from the record
  retiring into it. Two agencies can share a name; a legitimate rename almost
  never moves an agency across a state line, and when the catalog's own location
  fields disagree with the feed, that disagreement is the thing to look at.
- the successor's **name is not consistent with a rename**. Renames keep a
  distinctive word (Gloversville Transit Services to Gloversville Transit
  System), add or drop a brand or a qualifier (UTA to Utah Transit Authority
  (UTA)), or expand an acronym. A name with nothing distinctive in common is a
  merger, an operator change, or a mistake, and each of those changes what a
  page means to the person reading it.

Flagged retirements are not refused and not applied silently: they are held for
a decision recorded in ``supersession-review.yaml`` at the repository root. The
build gate (``scripts/check_supersession_review.py``) fails while any flagged
retirement in the registry has no decision on record, so the flag cannot be
merged past by ignoring it, and a decision to keep two records separate stays on
record so the weekly automation does not quietly re-apply the retirement next
month.

The flags are a reading aid with teeth, not a verdict. Plenty of flagged
retirements are correct, and saying so in the review file, with the evidence, is
the point.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import Agency

# A successor in another state or country, and a name with nothing in common,
# each mean "check that this is the same agency". Both hold a retirement back.
DIFFERENT_COUNTRY = "different_country"
DIFFERENT_SUBDIVISION = "different_subdivision"
NAME_NOT_A_RENAME = "name_not_a_rename"
# Reported, never blocking: one side has no subdivision recorded, so the
# jurisdictions cannot be compared. That is a gap in the registry, not evidence
# of a wrong retirement, and failing the build on it would only teach people to
# copy a location in to clear the gate.
SUBDIVISION_UNKNOWN = "subdivision_unknown"

BLOCKING_FLAGS = frozenset({DIFFERENT_COUNTRY, DIFFERENT_SUBDIVISION, NAME_NOT_A_RENAME})
_FLAG_ORDER = (DIFFERENT_COUNTRY, DIFFERENT_SUBDIVISION, NAME_NOT_A_RENAME, SUBDIVISION_UNKNOWN)

FLAG_REASONS = {
    DIFFERENT_COUNTRY: "the successor is in a different country",
    DIFFERENT_SUBDIVISION: "the successor is in a different state or province",
    NAME_NOT_A_RENAME: "the successor's name does not read as a rename of this one",
    SUBDIVISION_UNKNOWN: "one of the two records has no subdivision recorded",
}

RETIRE = "retire"
KEEP_SEPARATE = "keep_separate"
DECISIONS = frozenset({RETIRE, KEEP_SEPARATE})

REVIEW_FILENAME = "supersession-review.yaml"

# Words that say what kind of body an agency is, not which agency it is. They
# are dropped before names are compared so "Middletown Area Transit" and
# "Middletown Area Transit (MAT)" read as the same agency, while "Duarte
# Transit" and "Foothill Transit" still read as two.
_GENERIC_NAME_WORDS = frozenset(
    {
        "a",
        "agency",
        "and",
        "area",
        "authority",
        "bus",
        "co",
        "commission",
        "company",
        "corporation",
        "council",
        "department",
        "dept",
        "district",
        "division",
        "inc",
        "line",
        "llc",
        "of",
        "public",
        "region",
        "regional",
        "service",
        "system",
        "the",
        "transit",
        "transport",
        "transportation",
    }
)

# Words an acronym leaves out. Kept separate from the generic set above: those
# are dropped because they do not say which agency it is, these because nobody
# puts them in an initialism.
_ACRONYM_SKIPS = frozenset({"", "a", "and", "of", "the"})

_WORD_SPLIT = re.compile(r"[^a-z0-9]+")


def _singular(token: str) -> str:
    """Fold an obvious English plural, so Ferries and Ferry compare as one word."""
    if token.endswith("ies") and len(token) > 4:
        return f"{token[:-3]}y"
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        return token[:-1]
    return token


def distinctive_words(name: str) -> frozenset[str]:
    """The words in an agency name that say which agency it is."""
    return frozenset(
        word
        for token in _WORD_SPLIT.split(name.lower())
        if token and (word := _singular(token)) not in _GENERIC_NAME_WORDS
    )


def _initials(name: str) -> str:
    """The acronym a name would be shortened to, in the order it is written.

    Built from every word except the small connectives an acronym skips, so
    "Transit Authority of River City" gives TARC and "Utah Transit Authority"
    gives UTA. The generic words are kept here: an agency's initials are made
    of its whole name, not only of the distinctive part.
    """
    return "".join(
        token[0] for token in _WORD_SPLIT.split(name.lower()) if token not in _ACRONYM_SKIPS
    )


def reads_as_a_rename(retired_name: str, successor_name: str) -> bool:
    """Whether one name could be the other one renamed, rather than replaced.

    True when the two names share their whole distinctive vocabulary, when one
    side's distinctive words are all present in the other (a brand or a place
    added or dropped), or when a single-word name is the other's acronym. A name
    made only of generic words has nothing to compare, so it is not treated as
    evidence either way.
    """
    retired = distinctive_words(retired_name)
    successor = distinctive_words(successor_name)
    if not retired or not successor:
        return True
    if retired <= successor or successor <= retired:
        return True
    if len(retired) == 1 and next(iter(retired)) == _initials(successor_name):
        return True
    return len(successor) == 1 and next(iter(successor)) == _initials(retired_name)


def review_flags(retired: Agency, successor: Agency) -> tuple[str, ...]:
    """Why this retirement needs a person's decision, worst first. Empty is clean."""
    flags: set[str] = set()
    if retired.country and successor.country and retired.country != successor.country:
        flags.add(DIFFERENT_COUNTRY)
    if retired.subdivision_code and successor.subdivision_code:
        if retired.subdivision_code != successor.subdivision_code:
            flags.add(DIFFERENT_SUBDIVISION)
    elif retired.subdivision_code != successor.subdivision_code:
        flags.add(SUBDIVISION_UNKNOWN)
    if not reads_as_a_rename(retired.name, successor.name):
        flags.add(NAME_NOT_A_RENAME)
    return tuple(flag for flag in _FLAG_ORDER if flag in flags)


def blocking(flags: Iterable[str]) -> tuple[str, ...]:
    """The flags that hold a retirement back until it is reviewed."""
    return tuple(flag for flag in flags if flag in BLOCKING_FLAGS)


@dataclass(frozen=True)
class ReviewedRetirement:
    """One recorded decision about a flagged retirement.

    ``decision`` is either ``retire`` (the records are the same agency, or the
    merger is real, so the retirement stands) or ``keep_separate`` (they are
    not, so the record keeps its own page and the automation must not re-apply
    the catalog's redirect). ``evidence`` says what the decision rests on, in
    the reviewer's own words, and is required: a decision with no stated reason
    is not reviewable by the next person.
    """

    agency_id: str
    successor_id: str
    flags: tuple[str, ...]
    decision: str
    evidence: str


class SupersessionReviewError(Exception):
    """The review file could not be read as a list of decisions."""


def review_path(root: Path) -> Path:
    """Where the decisions live: one file at the repository root."""
    return root / REVIEW_FILENAME


def _entry(raw: object, index: int) -> ReviewedRetirement:
    label = f"{REVIEW_FILENAME}, entry {index}"
    if not isinstance(raw, dict):
        raise SupersessionReviewError(f"{label}: must be a mapping")
    allowed = {"agency_id", "successor_id", "flags", "decision", "evidence"}
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise SupersessionReviewError(f"{label}: unknown field(s) {', '.join(unknown)}")
    values: dict[str, str] = {}
    for field in ("agency_id", "successor_id", "decision", "evidence"):
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            raise SupersessionReviewError(f"{label}: {field} must be a non-empty string")
        values[field] = value.strip()
    if values["decision"] not in DECISIONS:
        raise SupersessionReviewError(
            f"{label}: decision must be one of {', '.join(sorted(DECISIONS))}"
        )
    flags = raw.get("flags")
    if not isinstance(flags, list) or not flags:
        raise SupersessionReviewError(f"{label}: flags must be a non-empty list")
    unknown_flags = sorted(str(flag) for flag in flags if flag not in _FLAG_ORDER)
    if unknown_flags:
        raise SupersessionReviewError(f"{label}: unknown flag(s) {', '.join(unknown_flags)}")
    return ReviewedRetirement(
        agency_id=values["agency_id"],
        successor_id=values["successor_id"],
        flags=tuple(flag for flag in _FLAG_ORDER if flag in flags),
        decision=values["decision"],
        evidence=values["evidence"],
    )


def parse_review(text: str) -> dict[str, ReviewedRetirement]:
    """Decisions by retired agency id, from the review file's text."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:  # pragma: no cover - message varies by parser build
        raise SupersessionReviewError(f"could not read {REVIEW_FILENAME}: {exc}") from exc
    if raw is None:
        return {}
    if (
        not isinstance(raw, dict)
        or set(raw) != {"reviewed"}
        or not isinstance(raw["reviewed"], list)
    ):
        raise SupersessionReviewError(
            f"{REVIEW_FILENAME} must contain only a top-level 'reviewed:' list"
        )
    decisions: dict[str, ReviewedRetirement] = {}
    for index, item in enumerate(raw["reviewed"], start=1):
        entry = _entry(item, index)
        if entry.agency_id in decisions:
            raise SupersessionReviewError(
                f"{REVIEW_FILENAME}, entry {index}: {entry.agency_id} is decided twice"
            )
        decisions[entry.agency_id] = entry
    return decisions


def read_review(root: Path) -> dict[str, ReviewedRetirement]:
    """Decisions on record. A missing file means none, not an error."""
    path = review_path(root)
    if not path.is_file():
        return {}
    try:
        text = path.read_text()
    except OSError as exc:
        raise SupersessionReviewError(f"could not read {path}: {exc}") from exc
    return parse_review(text)


def recorded_retirements(agencies: Iterable[Agency]) -> list[tuple[Agency, Agency]]:
    """Every retirement the registry records, as (retired record, successor)."""
    records = list(agencies)
    by_id = {agency.id: agency for agency in records}
    pairs = []
    for agency in records:
        if not agency.alias_of or agency.feed_status != "deprecated":
            continue
        successor = by_id.get(agency.alias_of)
        if successor is not None:
            pairs.append((agency, successor))
    return pairs


def _retirement_problems(
    retired: Agency, successor: Agency, entry: ReviewedRetirement | None
) -> list[str]:
    """What is wrong with one recorded retirement, given its decision (or none)."""
    flags = blocking(review_flags(retired, successor))
    if entry is None:
        if not flags:
            return []
        reasons = "; ".join(FLAG_REASONS[flag] for flag in flags)
        return [
            f"{retired.id} retires into {successor.id} and is flagged for review "
            f"({reasons}), but {REVIEW_FILENAME} records no decision. Review it and "
            f"add an entry, or undo the retirement."
        ]
    if entry.decision == KEEP_SEPARATE:
        return [
            f"{retired.id} is recorded in {REVIEW_FILENAME} as kept separate from "
            f"{entry.successor_id}, but the registry retires it into {successor.id}."
        ]
    problems = []
    if entry.successor_id != successor.id:
        problems.append(
            f"{retired.id} was reviewed as retiring into {entry.successor_id}, but the "
            f"registry retires it into {successor.id}. Review the new pairing."
        )
    if not flags:
        problems.append(
            f"{retired.id} is no longer flagged for review, so its {REVIEW_FILENAME} "
            "entry is stale. Remove the entry."
        )
    elif entry.flags != flags:
        problems.append(
            f"{retired.id} was reviewed for {', '.join(entry.flags)} but is now flagged "
            f"for {', '.join(flags)}. Review it again and update the entry."
        )
    return problems


def _stale_entry_problems(
    entry: ReviewedRetirement, retired: set[str], by_id: Mapping[str, Agency]
) -> list[str]:
    """What is wrong with a decision that no retirement in the registry matches."""
    if entry.agency_id in retired:
        return []
    if entry.agency_id not in by_id:
        return [
            f"{REVIEW_FILENAME} decides {entry.agency_id}, which is not in the registry. "
            "Remove the entry."
        ]
    if entry.decision == RETIRE:
        return [
            f"{REVIEW_FILENAME} approves retiring {entry.agency_id} into "
            f"{entry.successor_id}, but the registry does not retire it. Apply the "
            "retirement or remove the entry."
        ]
    if entry.successor_id not in by_id:
        return [
            f"{REVIEW_FILENAME} keeps {entry.agency_id} separate from "
            f"{entry.successor_id}, which is not in the registry. Remove the entry."
        ]
    return []


def review_problems(
    agencies: Iterable[Agency], reviewed: Mapping[str, ReviewedRetirement]
) -> list[str]:
    """Everything a person still has to decide, or has decided and been overruled on.

    An empty list means every flagged retirement in the registry has a decision
    on record, every decision still matches the registry, and no decision has
    gone stale. Anything else is a merge blocker: the build fails rather than
    publish a retirement nobody looked at.
    """
    records = list(agencies)
    by_id = {agency.id: agency for agency in records}
    pairs = recorded_retirements(records)
    problems: list[str] = []
    for retired, successor in pairs:
        problems.extend(_retirement_problems(retired, successor, reviewed.get(retired.id)))
    retired_ids = {retired.id for retired, _ in pairs}
    for entry in reviewed.values():
        problems.extend(_stale_entry_problems(entry, retired_ids, by_id))
    return sorted(problems)


def approved(entry: ReviewedRetirement | None, successor_id: str, flags: Iterable[str]) -> bool:
    """Whether a decision on record lets this exact flagged retirement be applied."""
    wanted = blocking(flags)
    if not wanted:
        return True
    if entry is None or entry.decision != RETIRE:
        return False
    return entry.successor_id == successor_id and entry.flags == wanted


def review_entry_yaml(
    agency_id: str, successor_id: str, flags: Iterable[str], *, evidence: str = ""
) -> str:
    """The block to paste into the review file once a flagged pair is decided."""
    listed = ", ".join(blocking(flags))
    note = evidence or "why this pairing is right, or why it is not"
    return (
        f"  - agency_id: {agency_id}\n"
        f"    successor_id: {successor_id}\n"
        f"    flags: [{listed}]\n"
        f"    decision: retire  # or keep_separate\n"
        f"    evidence: >-\n"
        f"      {note}\n"
    )
