"""Published grades this project has withdrawn, and why.

On 2026-09-01 the scorer learned to refuse a feed it could not read
(``score.UnreadableFeedError``, tests/test_unmeasurable_feed.py). That stopped
the next fabricated grade. It did nothing about the ones already published, and
it made them permanent: a refused agency writes no artifact, so the daily run
leaves the old letter exactly where it was and warns into a log nobody reads.
Nineteen named transit agencies stayed publicly graded F on data that had never
been read, and would have stayed there indefinitely.

Retracting a published grade is not the same as declining to publish a new one.
A reader who saw the F is owed the correction, not a silent replacement and not
a 404, so a withdrawal is recorded here rather than performed by deleting files
and hoping. Each entry names the exact record it withdraws -- agency, snapshot
date, and the feed hash that record was scored from -- states the verified cause
and the period the grade was public, and says what stands in its place.

Two things follow from an entry, both enforced in ``publish.reindex``:

* While the withdrawn record is still the newest thing on file, the agency's
  mutable current surfaces (``latest.json``, badge, conformance mark) are not
  written, and any that exist are removed, locally and from the object store.
  Reindex re-derives those from the newest dated artifact, so without this the
  next run would rebuild the retracted letter from the evidence file beside it.
* A newer artifact supersedes the withdrawal. The number the pipeline measures
  is published normally; the correction stays on the public record so the change
  reads as a correction rather than a flip.

Dated artifacts are not touched. They are the append-only evidence of what this
project published on a given day, including when it was wrong, and
docs/listing-policy.md already says they are not presented as an agency's
current condition.

The cause on every entry is verified per feed, never assumed. The two causes
below are the only ones found across the nineteen, and they need different
answers: an archive whose tables sit in a subfolder is a readable feed the
reader failed to open, while an archive with no tables at all cannot be given a
number by anyone. The second gets ``not_measured``, not a different score.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

CORRECTIONS_FILENAME = "corrections.yaml"
CORRECTIONS_SCHEMA_VERSION = 1

#: Why a published grade was wrong. Verified per feed from the artifact's own
#: validator findings and, where the feed is still reachable, from the archive.
TABLES_IN_A_SUBFOLDER = "tables_in_a_subfolder"
NO_SCHEDULE_TABLES = "no_schedule_tables"

CAUSES: dict[str, str] = {
    TABLES_IN_A_SUBFOLDER: (
        "the archive wraps its GTFS tables in a folder, and the reader looked for them "
        "at the top level and found none"
    ),
    NO_SCHEDULE_TABLES: (
        "the archive carries no stops and no trips, so there was no service to measure"
    ),
}

#: What stands in the withdrawn grade's place. Neither is a number: a grade
#: taken back because the data behind it was never read cannot be replaced by a
#: different reading of the same nothing. A later run that does read the feed
#: publishes its own measurement and supersedes the withdrawal on its own.
NOT_MEASURED = "not_measured"
DELISTED = "delisted"

OUTCOMES: dict[str, str] = {
    NOT_MEASURED: (
        "this feed still cannot be read, so nothing replaces the grade. Not measured is "
        "the answer, not a different number"
    ),
    DELISTED: (
        "this record is no longer a current listing, so its scorecard is withdrawn and not replaced"
    ),
}

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
_AGENCY_ID = re.compile(r"[a-z0-9][a-z0-9-]*\Z")

_REQUIRED_TEXT = ("agency_id", "agency_name", "snapshot_date", "feed_sha256", "grade", "cause")
_ALLOWED = frozenset(
    {
        "agency_id",
        "agency_name",
        "snapshot_date",
        "feed_sha256",
        "grade",
        "score",
        "published_from",
        "published_until",
        "cause",
        "outcome",
        "evidence",
    }
)


class CorrectionsError(ValueError):
    """The corrections file could not be read as a list of withdrawals."""


@dataclass(frozen=True)
class CorrectionsRecord:
    """Everything the corrections file says: what is withdrawn, and what is not yet.

    ``pending`` exists so the gate below cannot be satisfied by narrowing what it
    looks at. A published grade over a feed with no stops and no trips is either
    withdrawn or named here with a reason, and the second list may only shrink.
    Holding one back is sometimes right; holding one back silently never is.
    """

    withdrawn: dict[str, Correction]
    pending: dict[str, str]

    def covers(self, agency_id: str) -> bool:
        """Whether this record accounts for ``agency_id`` at all."""
        return agency_id in self.withdrawn or agency_id in self.pending


@dataclass(frozen=True)
class Correction:
    """One withdrawn published grade.

    ``snapshot_date`` and ``feed_sha256`` identify the exact record being
    withdrawn, so a later run that scores different bytes, or the same bytes on
    a later day, supersedes the withdrawal instead of being suppressed by it.

    ``evidence`` is required and is the point of the file. A withdrawal with no
    stated reason cannot be checked by the next person, and these entries name
    real agencies.
    """

    agency_id: str
    agency_name: str
    snapshot_date: str
    feed_sha256: str
    grade: str
    score: float | None
    published_from: str
    published_until: str
    cause: str
    outcome: str
    evidence: str

    @property
    def cause_text(self) -> str:
        """The cause in one plain sentence, for a reader rather than a log."""
        return CAUSES[self.cause]

    @property
    def outcome_text(self) -> str:
        """What replaces the withdrawn grade, in one plain sentence."""
        return OUTCOMES[self.outcome]

    def withdraws(self, artifact: Mapping[str, Any]) -> bool:
        """Whether ``artifact`` is the record this entry withdraws.

        Matched on the snapshot date and the feed hash together. A feed that has
        not changed but was re-scored on a later date is a new measurement and
        is published; the same date with different bytes is a different feed.
        """
        feed = artifact.get("feed")
        sha = str(feed.get("sha256", "")) if isinstance(feed, Mapping) else ""
        return str(artifact.get("snapshot_date", "")) == self.snapshot_date and sha == (
            self.feed_sha256
        )


def corrections_path(root: Path) -> Path:
    """Where the withdrawals live: one reviewed file at the repository root."""
    return root / CORRECTIONS_FILENAME


def _text_field(raw: Mapping[str, Any], field: str, label: str) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CorrectionsError(f"{label}: {field} must be a non-empty string")
    return value.strip()


def _checked_shapes(values: Mapping[str, str], label: str) -> None:
    """The four fields whose shape a reader would otherwise have to trust."""
    if not _AGENCY_ID.fullmatch(values["agency_id"]):
        raise CorrectionsError(f"{label}: agency_id is not a published artifact id")
    if not _DATE.fullmatch(values["snapshot_date"]):
        raise CorrectionsError(f"{label}: snapshot_date must be YYYY-MM-DD")
    if not _SHA256.fullmatch(values["feed_sha256"]):
        raise CorrectionsError(f"{label}: feed_sha256 must be a lowercase sha256 digest")
    if values["cause"] not in CAUSES:
        raise CorrectionsError(f"{label}: cause must be one of {', '.join(sorted(CAUSES))}")


def _published_period(raw: Mapping[str, Any], snapshot_date: str, label: str) -> tuple[str, str]:
    """How long the withdrawn grade was public. Missing dates are not invented."""
    published_from = str(raw.get("published_from") or snapshot_date)
    published_until = str(raw.get("published_until") or "")
    for field, value in (("published_from", published_from), ("published_until", published_until)):
        if value and not _DATE.fullmatch(value):
            raise CorrectionsError(f"{label}: {field} must be YYYY-MM-DD")
    return published_from, published_until


def _entry(raw: object, index: int) -> Correction:
    label = f"{CORRECTIONS_FILENAME}, entry {index}"
    if not isinstance(raw, dict):
        raise CorrectionsError(f"{label}: must be a mapping")
    unknown = sorted(set(raw) - _ALLOWED)
    if unknown:
        raise CorrectionsError(f"{label}: unknown field(s) {', '.join(unknown)}")
    values = {field: _text_field(raw, field, label) for field in _REQUIRED_TEXT}
    _checked_shapes(values, label)
    outcome = str(raw.get("outcome") or NOT_MEASURED)
    if outcome not in OUTCOMES:
        raise CorrectionsError(f"{label}: outcome must be one of {', '.join(sorted(OUTCOMES))}")
    raw_score = raw.get("score")
    if raw_score is not None and not isinstance(raw_score, (int, float)):
        raise CorrectionsError(f"{label}: score must be a number")
    published_from, published_until = _published_period(raw, values["snapshot_date"], label)
    return Correction(
        agency_id=values["agency_id"],
        agency_name=values["agency_name"],
        snapshot_date=values["snapshot_date"],
        feed_sha256=values["feed_sha256"],
        grade=values["grade"],
        score=None if raw_score is None else float(raw_score),
        published_from=published_from,
        published_until=published_until,
        cause=values["cause"],
        outcome=outcome,
        evidence=_text_field(raw, "evidence", label),
    )


def _pending(raw: object) -> dict[str, str]:
    """Grades known to be wrong and not yet withdrawn, by id, with the reason."""
    if raw is None:
        return {}
    if not isinstance(raw, list):
        raise CorrectionsError(f"{CORRECTIONS_FILENAME}: not_yet_corrected must be a list")
    pending: dict[str, str] = {}
    for index, item in enumerate(raw, start=1):
        label = f"{CORRECTIONS_FILENAME}, not_yet_corrected entry {index}"
        if not isinstance(item, dict) or set(item) - {"agency_id", "reason"}:
            raise CorrectionsError(f"{label}: must be a mapping of agency_id and reason")
        agency_id = _text_field(item, "agency_id", label)
        reason = _text_field(item, "reason", label)
        if not _AGENCY_ID.fullmatch(agency_id):
            raise CorrectionsError(f"{label}: agency_id is not a published artifact id")
        if agency_id in pending:
            raise CorrectionsError(f"{label}: {agency_id} is listed twice")
        pending[agency_id] = reason
    return pending


def parse_corrections(text: str) -> CorrectionsRecord:
    """The corrections file's contents: withdrawals, and what is held back."""
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:  # pragma: no cover - message varies by parser build
        raise CorrectionsError(f"could not read {CORRECTIONS_FILENAME}: {exc}") from exc
    if raw is None:
        return CorrectionsRecord({}, {})
    if not isinstance(raw, dict) or not set(raw) <= {
        "schema_version",
        "corrections",
        "not_yet_corrected",
    }:
        raise CorrectionsError(
            f"{CORRECTIONS_FILENAME} may contain only schema_version, corrections "
            "and not_yet_corrected"
        )
    if raw.get("schema_version") != CORRECTIONS_SCHEMA_VERSION:
        raise CorrectionsError(f"{CORRECTIONS_FILENAME}: unsupported schema_version")
    listed = raw.get("corrections")
    if not isinstance(listed, list):
        raise CorrectionsError(f"{CORRECTIONS_FILENAME}: corrections must be a list")
    withdrawn: dict[str, Correction] = {}
    for index, item in enumerate(listed, start=1):
        entry = _entry(item, index)
        if entry.agency_id in withdrawn:
            raise CorrectionsError(
                f"{CORRECTIONS_FILENAME}, entry {index}: {entry.agency_id} is withdrawn twice"
            )
        withdrawn[entry.agency_id] = entry
    pending = _pending(raw.get("not_yet_corrected"))
    both = sorted(set(withdrawn) & set(pending))
    if both:
        raise CorrectionsError(
            f"{CORRECTIONS_FILENAME}: {', '.join(both)} is both withdrawn and not yet corrected"
        )
    return CorrectionsRecord(withdrawn, pending)


def read_corrections(root: Path) -> CorrectionsRecord:
    """The corrections file for a checkout. A missing file means none, not an error."""
    path = corrections_path(root)
    if not path.is_file():
        return CorrectionsRecord({}, {})
    try:
        text = path.read_text()
    except OSError as exc:
        raise CorrectionsError(f"could not read {path}: {exc}") from exc
    return parse_corrections(text)


def load_corrections() -> dict[str, Correction]:
    """Withdrawals on record for this checkout."""
    from .config import repo_root

    return read_corrections(repo_root()).withdrawn


def suppresses_current(correction: Correction | None, artifact: Mapping[str, Any] | None) -> bool:
    """Whether this agency's current surfaces must stay withdrawn.

    True only while the newest artifact on file is the exact record the
    correction withdraws. Anything newer is a real measurement and publishes.
    """
    if correction is None or artifact is None:
        return False
    return correction.withdraws(artifact)


def _newest_artifact(agency_dir: Path) -> dict[str, Any] | None:
    """The newest artifact on file for one agency, dated or current."""
    import json

    candidates = sorted(agency_dir.glob("[0-9][0-9][0-9][0-9]-*.json"))
    latest = agency_dir / "latest.json"
    if latest.is_file():
        candidates.append(latest)
    newest: dict[str, Any] | None = None
    newest_date = ""
    for path in candidates:
        try:
            artifact = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(artifact, dict):
            continue
        date = str(artifact.get("snapshot_date", ""))
        if date >= newest_date:
            newest, newest_date = artifact, date
    return newest


def withdrawn_now(withdrawn: Mapping[str, Correction], artifact_root: Path) -> tuple[str, ...]:
    """Corrected agencies whose newest artifact on file is still the withdrawn one.

    The withdrawal is scoped to the record it names, so it lifts by itself. A run
    that reads the feed writes a newer artifact, that artifact becomes the newest
    on file, and this stops returning the id: the measurement publishes normally
    and the correction stays on the public record beside it.
    """
    return tuple(
        sorted(
            agency_id
            for agency_id, entry in withdrawn.items()
            if (artifact_root / agency_id).is_dir()
            and suppresses_current(entry, _newest_artifact(artifact_root / agency_id))
        )
    )


def correction_problems(record: CorrectionsRecord, artifact_root: Path) -> list[str]:
    """Everything about the corrections file that a build must not merge past.

    Three directions, because any one alone would rot. An entry whose withdrawn
    record is still published has not taken effect. A published ``latest.json``
    that grades a feed with no stops and no trips, with nothing said about it
    anywhere in this file, is the state the file exists to end. And a
    ``not_measured`` entry with no artifact directory has lost the dated
    evidence it is a correction to.

    The directory check is deliberately not asked of a ``delisted`` entry.
    Twelve of the nineteen withdrawn records are in no registry, and their
    directories held nothing but the four current pointers this withdrawal
    removes -- no dated artifact was ever written for them -- so a completed
    withdrawal takes the directory with it. Git does not carry an empty
    directory, so those ids leave the tree entirely. Asked of them, this check
    fires on exactly the state the file exists to produce, and it does so only
    in a fresh checkout: an empty directory left behind locally makes it pass on
    the machine the change was written on. A ``not_measured`` record is
    different. It is still a listing, its dated artifacts were kept on purpose,
    and their absence means something was deleted that should not have been.
    """
    problems: list[str] = []
    for agency_id, entry in sorted(record.withdrawn.items()):
        if not (artifact_root / agency_id).is_dir():
            if entry.outcome == NOT_MEASURED:
                problems.append(
                    f"{CORRECTIONS_FILENAME} withdraws {agency_id} as {NOT_MEASURED}, but its "
                    "artifact directory is gone. A record that is still a listing keeps its "
                    "dated evidence."
                )
            continue
        current = artifact_root / agency_id / "latest.json"
        if current.is_file():
            import json

            try:
                artifact = json.loads(current.read_text())
            except (OSError, ValueError):
                continue
            if entry.withdraws(artifact):
                problems.append(
                    f"{agency_id} still publishes the grade {CORRECTIONS_FILENAME} "
                    f"withdraws ({entry.grade}, {entry.snapshot_date}). Run "
                    "`scorecard reindex` so the withdrawal takes effect."
                )
    problems.extend(_uncorrected(record, artifact_root))
    return sorted(problems)


def grades_a_feed_with_nothing_in_it(artifact: Mapping[str, Any]) -> bool:
    """Whether a published scorecard carries a letter for a feed with nothing in it.

    The shape ``score_feed_content`` now refuses to produce: a measured rider
    experience over zero stops and zero trips, with a letter beside it.
    """
    categories = artifact.get("categories")
    overall = artifact.get("overall")
    if not isinstance(categories, Mapping) or not isinstance(overall, Mapping):
        return False
    completeness = categories.get("completeness")
    if not isinstance(completeness, Mapping) or completeness.get("status") != "measured":
        return False
    details = completeness.get("details")
    if not isinstance(details, Mapping):
        return False
    return details.get("stops") == 0 and details.get("trips") == 0 and "grade" in overall


def _uncorrected(record: CorrectionsRecord, artifact_root: Path) -> Iterable[str]:
    """Published grades over an empty feed that the record says nothing about."""
    import json

    if not artifact_root.is_dir():
        return []
    stranded = []
    for path in sorted(artifact_root.glob("*/latest.json")):
        agency_id = path.parent.name
        if record.covers(agency_id):
            continue
        try:
            artifact = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if grades_a_feed_with_nothing_in_it(artifact):
            stranded.append(agency_id)
    if not stranded:
        return []
    return [
        f"{len(stranded)} published scorecard(s) grade a feed with no stops and no "
        f"trips and are neither withdrawn nor listed under not_yet_corrected in "
        f"{CORRECTIONS_FILENAME}: {', '.join(stranded)}"
    ]
