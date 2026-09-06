"""Snapshot-to-snapshot diff of a feed's quality (the "what changed" view).

The pipeline keeps a dated artifact per agency per day. The trend chart shows the
shape of the score over time; this answers the next question a manager asks:
"what actually changed in my feed between the last two checks?" It compares two
artifacts and reports the change at the level a reader can act on — findings that
newly appeared, findings that cleared, findings whose instance count moved, and
whether the feed file itself was re-published — plus the overall grade, score, and
expiry-window movement.

True GTFS row-level diffing (which stop or route changed) needs the raw feed,
which the project does not archive. This works entirely from the published
artifacts on hand, so it is pure and reproducible.

**Nothing here may be read as a change claim until the pair passes
:func:`compare_contract`.** Two artifacts scored under different rubrics,
scoring profiles, validators, reader archive profiles, or measured-category
sets are two different measurements, and the difference between them is not a
statement about the feed. ``docs/comparison-policy.md`` states the same rule for
the published change views; ``scorecard diff`` applies it to arbitrary pairs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .comparisons import producer_contract

# Letter grades worst-to-best, for deciding whether a grade move is a drop.
_GRADE_ORDER = ["F", "D", "C", "B", "A"]
_MEASURED_CATEGORIES = ("correctness", "freshness", "completeness", "realtime")


@dataclass(frozen=True)
class FindingChange:
    """A single finding that appeared, cleared, or changed in instance count."""

    code: str
    what: str
    severity: str
    prev_count: int | None  # None when the finding is newly appeared
    curr_count: int | None  # None when the finding cleared


#: Field order of :func:`scorecard_pipeline.comparisons.producer_contract`, paired
#: with the reason a reader is given when that field is the one that differs. The
#: reasons are stable strings: they are printed, put in JSON, and asserted on.
_CONTRACT_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("rubric_version", "rubric_version_missing", "rubric_version_mismatch"),
    ("scoring_profile_id", "scoring_profile_id_missing", "scoring_profile_id_mismatch"),
    (
        "scoring_profile_rubric_version",
        "scoring_profile_rubric_version_missing",
        "scoring_profile_rubric_version_mismatch",
    ),
    ("validator_version", "validator_version_missing", "validator_version_mismatch"),
    (
        "reader_archive_profile",
        "reader_archive_profile_unresolved",
        "reader_archive_profile_mismatch",
    ),
)

#: One line per reason, in the vocabulary the audience reads rather than the
#: field name. ``docs/comparison-policy.md`` is the prose version of this table.
CONTRACT_REASON_TEXT: dict[str, str] = {
    "rubric_version_missing": "one artifact does not say which rubric version scored it",
    "rubric_version_mismatch": "the two artifacts were scored under different rubric versions",
    "scoring_profile_id_missing": "one artifact does not name its scoring profile",
    "scoring_profile_id_mismatch": "the two artifacts used different scoring profiles",
    "scoring_profile_rubric_version_missing": (
        "one artifact's scoring profile does not state its rubric version"
    ),
    "scoring_profile_rubric_version_mismatch": (
        "the two scoring profiles state different rubric versions"
    ),
    "validator_version_missing": "one artifact does not say which validator produced it",
    "validator_version_mismatch": "the two artifacts used different gtfs-validator versions",
    "reader_archive_profile_unresolved": (
        "one artifact's reader archive profile could not be resolved, so how the feed "
        "was read is unknown"
    ),
    "reader_archive_profile_mismatch": (
        "the two artifacts read the feed archive under different reader profiles"
    ),
    "measured_category_set_missing": "one artifact measured no category at all",
    "measured_category_set_mismatch": (
        "the two artifacts measured different sets of categories, so their overall "
        "scores have different denominators"
    ),
}


@dataclass(frozen=True)
class ContractCheck:
    """Whether two artifacts are the same measurement, and if not, why not.

    This is the fail-closed half of a diff. ``comparable`` is False whenever any
    part of the producer contract is absent or differs, which deliberately
    includes the case where an artifact simply does not state a field: an
    unstated contract is not a matching one, and guessing that it matches is how
    a methodology change gets published as a change in a feed.
    """

    comparable: bool
    reasons: tuple[str, ...] = ()
    prev_contract: tuple[str, str, str, str, str, tuple[str, ...]] | None = None
    curr_contract: tuple[str, str, str, str, str, tuple[str, ...]] | None = None

    @property
    def explanations(self) -> tuple[str, ...]:
        """Each reason as a sentence, in the order the reasons were recorded."""
        return tuple(CONTRACT_REASON_TEXT.get(reason, reason) for reason in self.reasons)


def compare_contract(prev: dict[str, Any], curr: dict[str, Any]) -> ContractCheck:
    """Decide whether a change between ``prev`` and ``curr`` is about the feed.

    Uses the same :func:`~scorecard_pipeline.comparisons.producer_contract` the
    published change views and the site's "What changed" section already gate
    on, so an arbitrary pair handed to ``scorecard diff`` is held to exactly the
    policy in ``docs/comparison-policy.md`` — not a second, looser one.
    """
    prev_contract = producer_contract(prev)
    curr_contract = producer_contract(curr)
    reasons: list[str] = []
    for index, (_field, missing, mismatch) in enumerate(_CONTRACT_FIELDS):
        left, right = prev_contract[index], curr_contract[index]
        if not left or not right:
            reasons.append(missing)
        elif left != right:
            reasons.append(mismatch)
    prev_measured, curr_measured = prev_contract[5], curr_contract[5]
    if not prev_measured or not curr_measured:
        reasons.append("measured_category_set_missing")
    elif prev_measured != curr_measured:
        reasons.append("measured_category_set_mismatch")
    return ContractCheck(
        comparable=not reasons,
        reasons=tuple(reasons),
        prev_contract=prev_contract,
        curr_contract=curr_contract,
    )


@dataclass
class FeedDiff:
    """The change between two snapshots of one feed, finding-level and overall."""

    prev_date: str
    curr_date: str
    new: list[FindingChange] = field(default_factory=list)
    resolved: list[FindingChange] = field(default_factory=list)
    changed: list[FindingChange] = field(default_factory=list)
    #: Findings whose category the newer artifact did not measure. They did not
    #: clear; nobody looked. Kept out of ``resolved`` so no caller of this
    #: dataclass can report an absence as a result. In practice a shrinking
    #: measured-category set also fails :func:`compare_contract`, so a caller
    #: that gates on the contract first — every caller in this repository does —
    #: sees this list empty; it is the guard for the caller that does not.
    unmeasured: list[FindingChange] = field(default_factory=list)
    score_delta: float = 0.0
    prev_grade: str | None = None
    curr_grade: str | None = None
    feed_bytes_changed: bool = False
    size_delta: int | None = None
    expiry_delta: int | None = None

    @property
    def grade_moved(self) -> bool:
        return (
            self.prev_grade is not None
            and self.curr_grade is not None
            and self.prev_grade != self.curr_grade
        )

    @property
    def grade_dropped(self) -> bool:
        if not self.grade_moved:
            return False
        try:
            return _GRADE_ORDER.index(str(self.curr_grade)) < _GRADE_ORDER.index(
                str(self.prev_grade)
            )
        except ValueError:
            return False

    @property
    def has_findings_change(self) -> bool:
        return bool(self.new or self.resolved or self.changed)

    @property
    def regressed(self) -> bool:
        """Whether this diff is a regression a CI gate should fail on.

        A grade drop, or a finding that newly appeared or grew in count. A
        finding that stopped being measured is deliberately not a regression and
        is deliberately not an improvement either — see ``unmeasured``.
        """
        return bool(
            self.grade_dropped
            or self.new
            or any((c.curr_count or 0) > (c.prev_count or 0) for c in self.changed)
        )

    @property
    def has_changes(self) -> bool:
        """Whether anything worth showing moved between the two snapshots."""
        return (
            self.has_findings_change
            or self.grade_moved
            or round(self.score_delta, 1) != 0.0
            or self.feed_bytes_changed
            or bool(self.expiry_delta)
            # A category going dark is not a finding change, but "nothing
            # changed" would be the wrong thing to say over it.
            or bool(self.unmeasured)
        )


def _findings(artifact: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map each finding code in an artifact to its display fields, across the
    measured categories. The first occurrence of a code wins (a code is not
    expected to repeat across categories)."""
    return {code: finding for code, (_category, finding) in _findings_by_category(artifact).items()}


def _findings_by_category(artifact: dict[str, Any]) -> dict[str, tuple[str, dict[str, Any]]]:
    """As :func:`_findings`, but keeping the category each finding came from.

    The category is what separates "this finding cleared" from "we stopped
    measuring the category it lived in", and only the first of those is a
    statement about the feed.
    """
    out: dict[str, tuple[str, dict[str, Any]]] = {}
    for key in _MEASURED_CATEGORIES:
        cat = artifact.get("categories", {}).get(key, {})
        if cat.get("status") != "measured":
            continue
        for f in cat.get("findings", []):
            code = f.get("code")
            if code and str(code) not in out:
                out[str(code)] = (key, f)
    return out


def _measured_categories(artifact: dict[str, Any]) -> set[str]:
    """The categories this artifact actually measured."""
    categories = artifact.get("categories")
    if not isinstance(categories, dict):
        return set()
    return {
        key
        for key in _MEASURED_CATEGORIES
        if isinstance(categories.get(key), dict) and categories[key].get("status") == "measured"
    }


def _count(finding: dict[str, Any]) -> int:
    raw = finding.get("count", 0)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 0


def _expiry_days(artifact: dict[str, Any]) -> int | None:
    days = (
        artifact.get("categories", {})
        .get("freshness", {})
        .get("details", {})
        .get("days_until_expiry")
    )
    if isinstance(days, bool) or not isinstance(days, (int, float)):
        return None
    return int(days)


def diff_artifacts(prev: dict[str, Any], curr: dict[str, Any]) -> FeedDiff:
    """Compute the structured diff from the previous snapshot to the current one.

    Findings are matched by validator code: a code present now but not before is
    *new*, present before but not now is *resolved*, and present in both with a
    different instance count is *changed*. Severity and the plain-language "what"
    come from the current snapshot for new/changed findings and from the previous
    snapshot for resolved ones (its description is the last thing the reader saw).
    """
    prev_by_category = _findings_by_category(prev)
    prev_f = {code: finding for code, (_category, finding) in prev_by_category.items()}
    curr_f = _findings(curr)
    curr_measured = _measured_categories(curr)

    new = [
        FindingChange(
            code=code,
            what=str(f.get("what", "")),
            severity=str(f.get("severity", "INFO")),
            prev_count=None,
            curr_count=_count(f),
        )
        for code, f in curr_f.items()
        if code not in prev_f
    ]
    # A finding that is gone can mean two different things, and only one of them
    # is about the feed. If its category was measured again and the finding is
    # not in the new artifact, it cleared. If the category was NOT measured
    # again, the finding did not clear — we stopped looking, and saying "cleared"
    # would publish an absence as a result. The categories a diff covers can move
    # (realtime is optional, and a realtime endpoint that stops answering makes
    # the category unmeasured), so this is a live shape, not a hypothetical.
    resolved = [
        FindingChange(
            code=code,
            what=str(f.get("what", "")),
            severity=str(f.get("severity", "INFO")),
            prev_count=_count(f),
            curr_count=None,
        )
        for code, (category, f) in prev_by_category.items()
        if code not in curr_f and category in curr_measured
    ]
    unmeasured = [
        FindingChange(
            code=code,
            what=str(f.get("what", "")),
            severity=str(f.get("severity", "INFO")),
            prev_count=_count(f),
            curr_count=None,
        )
        for code, (category, f) in prev_by_category.items()
        if code not in curr_f and category not in curr_measured
    ]
    changed = []
    for code, f in curr_f.items():
        if code not in prev_f:
            continue
        before, after = _count(prev_f[code]), _count(f)
        if before != after:
            changed.append(
                FindingChange(
                    code=code,
                    what=str(f.get("what", "")),
                    severity=str(f.get("severity", "INFO")),
                    prev_count=before,
                    curr_count=after,
                )
            )

    # Worst severity first, then the biggest movers, within each bucket.
    rank = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    new.sort(key=lambda c: (rank.get(c.severity, 9), -(c.curr_count or 0)))
    resolved.sort(key=lambda c: (rank.get(c.severity, 9), -(c.prev_count or 0)))
    unmeasured.sort(key=lambda c: (rank.get(c.severity, 9), -(c.prev_count or 0)))
    changed.sort(
        key=lambda c: (rank.get(c.severity, 9), -abs((c.curr_count or 0) - (c.prev_count or 0)))
    )

    prev_score = float(prev.get("overall", {}).get("score", 0.0))
    curr_score = float(curr.get("overall", {}).get("score", 0.0))

    prev_sha = prev.get("feed", {}).get("sha256")
    curr_sha = curr.get("feed", {}).get("sha256")
    feed_bytes_changed = bool(prev_sha and curr_sha and prev_sha != curr_sha)
    prev_size = prev.get("feed", {}).get("size_bytes")
    curr_size = curr.get("feed", {}).get("size_bytes")
    size_delta = (
        int(curr_size) - int(prev_size)
        if isinstance(prev_size, (int, float)) and isinstance(curr_size, (int, float))
        else None
    )

    prev_days, curr_days = _expiry_days(prev), _expiry_days(curr)
    expiry_delta = (
        curr_days - prev_days if prev_days is not None and curr_days is not None else None
    )

    return FeedDiff(
        prev_date=str(prev.get("snapshot_date", "")),
        curr_date=str(curr.get("snapshot_date", "")),
        new=new,
        resolved=resolved,
        changed=changed,
        unmeasured=unmeasured,
        score_delta=round(curr_score - prev_score, 1),
        prev_grade=prev.get("overall", {}).get("grade"),
        curr_grade=curr.get("overall", {}).get("grade"),
        feed_bytes_changed=feed_bytes_changed,
        size_delta=size_delta,
        expiry_delta=expiry_delta,
    )


def findings_no_longer_measured(prev: dict[str, Any], curr: dict[str, Any]) -> list[FindingChange]:
    """Findings in ``prev`` whose category ``curr`` did not measure.

    Deliberately usable on a pair that is **not** comparable, which is the pair
    it matters for. A shrinking measured-category set is itself a contract
    change, so ``compare_contract`` refuses the pair — and a bare refusal would
    leave the reader thinking those findings went away. They did not. Nobody
    looked. This is the sentence that says so, and it is a statement about our
    own coverage, never a change claim about the feed.
    """
    curr_f = _findings(curr)
    curr_measured = _measured_categories(curr)
    changes = [
        FindingChange(
            code=code,
            what=str(f.get("what", "")),
            severity=str(f.get("severity", "INFO")),
            prev_count=_count(f),
            curr_count=None,
        )
        for code, (category, f) in _findings_by_category(prev).items()
        if code not in curr_f and category not in curr_measured
    ]
    rank = {"ERROR": 0, "WARNING": 1, "INFO": 2}
    changes.sort(key=lambda c: (rank.get(c.severity, 9), -(c.prev_count or 0)))
    return changes


def contract_fields(contract: tuple[str, str, str, str, str, tuple[str, ...]]) -> dict[str, Any]:
    """The producer-contract tuple as named fields, for JSON and for printing."""
    return {
        "rubric_version": contract[0],
        "scoring_profile_id": contract[1],
        "scoring_profile_rubric_version": contract[2],
        "validator_version": contract[3],
        "reader_archive_profile": contract[4],
        "measured_categories": list(contract[5]),
    }


def _change_json(change: FindingChange) -> dict[str, Any]:
    return {
        "code": change.code,
        "what": change.what,
        "severity": change.severity,
        "prev_count": change.prev_count,
        "curr_count": change.curr_count,
    }


def _side_json(artifact: dict[str, Any], check: ContractCheck, *, previous: bool) -> dict[str, Any]:
    contract = check.prev_contract if previous else check.curr_contract
    overall = artifact.get("overall")
    overall = overall if isinstance(overall, dict) else {}
    return {
        "snapshot_date": str(artifact.get("snapshot_date") or ""),
        "agency_id": str((artifact.get("agency") or {}).get("id") or "")
        if isinstance(artifact.get("agency"), dict)
        else "",
        "grade": overall.get("grade"),
        "score": overall.get("score"),
        "feed_sha256": (artifact.get("feed") or {}).get("sha256")
        if isinstance(artifact.get("feed"), dict)
        else None,
        "contract": contract_fields(contract) if contract is not None else None,
    }


def diff_json(prev: dict[str, Any], curr: dict[str, Any]) -> dict[str, Any]:
    """The machine-readable diff, fail-closed on the comparability contract.

    When the pair is not comparable the payload carries ``comparable: false``,
    the reasons, and both contracts — and **no** ``overall`` or ``findings``
    key at all. An empty findings list would be read as "nothing changed", which
    is the one thing that must not be said across a contract boundary.
    """
    check = compare_contract(prev, curr)
    payload: dict[str, Any] = {
        "comparable": check.comparable,
        "reasons": list(check.reasons),
        "explanations": list(check.explanations),
        "prev": _side_json(prev, check, previous=True),
        "curr": _side_json(curr, check, previous=False),
    }
    if not check.comparable:
        # Not a change claim, and kept out of any "findings" object for that
        # reason: these are the findings whose category the newer run did not
        # measure, listed so a refusal does not read as a clean bill of health.
        payload["no_longer_measured"] = [
            _change_json(c) for c in findings_no_longer_measured(prev, curr)
        ]
        return payload
    diff = diff_artifacts(prev, curr)
    payload["overall"] = {
        "score_delta": diff.score_delta,
        "grade_from": diff.prev_grade,
        "grade_to": diff.curr_grade,
        "grade_moved": diff.grade_moved,
        "grade_dropped": diff.grade_dropped,
        "expiry_delta": diff.expiry_delta,
        "feed_bytes_changed": diff.feed_bytes_changed,
        "size_delta": diff.size_delta,
    }
    payload["findings"] = {
        "new": [_change_json(c) for c in diff.new],
        "cleared": [_change_json(c) for c in diff.resolved],
        "changed": [_change_json(c) for c in diff.changed],
    }
    payload["regressed"] = diff.regressed
    payload["has_changes"] = diff.has_changes
    return payload


def _contract_lines(check: ContractCheck) -> list[str]:
    """Both contracts, field by field, marking the fields that differ."""
    lines: list[str] = []
    prev = contract_fields(check.prev_contract) if check.prev_contract else {}
    curr = contract_fields(check.curr_contract) if check.curr_contract else {}
    for key in prev:
        left, right = prev.get(key), curr.get(key)
        left_text = ", ".join(left) if isinstance(left, list) else (left or "(not stated)")
        right_text = ", ".join(right) if isinstance(right, list) else (right or "(not stated)")
        marker = "  " if left == right else "! "
        lines.append(f"  {marker}{key}: {left_text} -> {right_text}")
    return lines


def _count_phrase(change: FindingChange) -> str:
    before, after = change.prev_count, change.curr_count
    if before is None:
        return f"{after} instance(s)"
    if after is None:
        return f"was {before} instance(s)"
    direction = "up" if after > before else "down"
    return f"{before} -> {after} instance(s), {direction}"


def render_diff_text(prev: dict[str, Any], curr: dict[str, Any]) -> str:
    """The diff as plain text for a terminal or a CI log."""
    check = compare_contract(prev, curr)
    prev_date = str(prev.get("snapshot_date") or "the older artifact")
    curr_date = str(curr.get("snapshot_date") or "the newer artifact")
    out = [f"Comparing {prev_date} -> {curr_date}"]
    if not check.comparable:
        out.append("")
        out.append("NOT COMPARABLE. No change is being claimed about this feed.")
        out.append(
            "  These two artifacts are different measurements, so the difference "
            "between them is not a statement about the feed."
        )
        for reason, sentence in zip(check.reasons, check.explanations, strict=True):
            out.append(f"  - {sentence} [{reason}]")
        out.append("")
        out.append("Producer contract:")
        out.extend(_contract_lines(check))
        dark = findings_no_longer_measured(prev, curr)
        if dark:
            out.append("")
            out.append(f"Not measured in the newer artifact ({len(dark)}):")
            out.extend(f"  - {c.code} [{c.severity}] {_count_phrase(c)}" for c in dark)
            out.append(
                "  These did not clear. The category they belong to was not measured "
                "in the newer artifact, so nothing was looked at."
            )
        return "\n".join(out) + "\n"

    diff = diff_artifacts(prev, curr)
    out.append("")
    if diff.grade_moved:
        direction = "down" if diff.grade_dropped else "up"
        out.append(f"Grade {diff.prev_grade} -> {diff.curr_grade} ({direction})")
    else:
        out.append(f"Grade {diff.curr_grade} (unchanged)")
    out.append(f"Score {diff.score_delta:+.1f}")
    if diff.expiry_delta is not None:
        out.append(f"Days of service left {diff.expiry_delta:+d}")
    out.append("Feed file re-published" if diff.feed_bytes_changed else "Feed file byte-identical")
    for label, changes in (
        ("New findings", diff.new),
        ("Cleared findings", diff.resolved),
        ("Changed counts", diff.changed),
    ):
        if changes:
            out.append("")
            out.append(f"{label} ({len(changes)}):")
            out.extend(f"  - {c.code} [{c.severity}] {_count_phrase(c)}" for c in changes)
    if not diff.has_changes:
        out.append("")
        out.append("Nothing changed: the same feed file, the same grade, the same findings.")
    return "\n".join(out) + "\n"


def render_diff_markdown(prev: dict[str, Any], curr: dict[str, Any]) -> str:
    """The diff as Markdown, for a job summary or a pull-request comment."""
    check = compare_contract(prev, curr)
    prev_date = str(prev.get("snapshot_date") or "the older artifact")
    curr_date = str(curr.get("snapshot_date") or "the newer artifact")
    out = [f"### Feed comparison: {prev_date} → {curr_date}", ""]
    if not check.comparable:
        out.append("**Not comparable — no change is being claimed about this feed.**")
        out.append("")
        out.append(
            "These two artifacts are different measurements, so the difference "
            "between them is not a statement about the feed."
        )
        out.append("")
        out.extend(
            f"- {sentence} (`{reason}`)"
            for reason, sentence in zip(check.reasons, check.explanations, strict=True)
        )
        dark = findings_no_longer_measured(prev, curr)
        if dark:
            out.append("")
            out.append(f"**Not measured in the newer artifact ({len(dark)})**")
            out.append("")
            out.extend(f"- `{c.code}` ({c.severity}) — {_count_phrase(c)}" for c in dark)
            out.append("")
            out.append(
                "_These did not clear. The category they belong to was not measured "
                "in the newer artifact, so nothing was looked at._"
            )
        return "\n".join(out) + "\n"

    diff = diff_artifacts(prev, curr)
    grade = f"{diff.prev_grade} → {diff.curr_grade}" if diff.grade_moved else f"{diff.curr_grade}"
    out.append("| Grade | Score | Feed file |")
    out.append("| --- | --- | --- |")
    out.append(
        f"| {grade} | {diff.score_delta:+.1f} | "
        f"{'re-published' if diff.feed_bytes_changed else 'byte-identical'} |"
    )
    for label, changes in (
        ("New findings", diff.new),
        ("Cleared findings", diff.resolved),
        ("Changed counts", diff.changed),
    ):
        if changes:
            out.append("")
            out.append(f"**{label} ({len(changes)})**")
            out.append("")
            out.extend(f"- `{c.code}` ({c.severity}) — {_count_phrase(c)}" for c in changes)
    if not diff.has_changes:
        out.append("")
        out.append("Nothing changed: the same feed file, the same grade, the same findings.")
    return "\n".join(out) + "\n"
