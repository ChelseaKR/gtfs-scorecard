"""Weekly cohort ("portfolio") digest for a program liaison.

`alerts.py` tells one agency what needs attention today. This tells a liaison
what moved across a whole cohort since last week: which feeds a manager fixed,
which slipped, and which newly expired. It is built on the same artifacts and
carries the same fix-framed, no-shaming tone — it leads with what got fixed and,
on a quiet week, says so plainly rather than sending an alarming blank.

The week-over-week diff needs a memory of last week. We keep a small snapshot of
each member's score, grade, and expiry status per rollup in a
`<rollup>.state.json` file under the artifacts `rollups/` directory, written the
same atomic way as the other state files (liveness.py). Building the digest is
pure and testable against fixture artifacts; advancing the snapshot is the
caller's decision (the CLI does it after a real run).
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION
from .alerts import GRADE_ORDER, REGRESSION_POINTS
from .config import artifacts_dir
from .metrics import expiry_status
from .rollups import Rollup, _load_latest, resolve_member_ids

# A score move of at least this many points (or any grade change) is worth
# reporting; smaller wobble is validator noise. Reuses the alerts threshold so
# "moved" means the same thing across the per-agency and cohort views.
SCORE_MOVE_POINTS = REGRESSION_POINTS

# Expiry statuses that mean a feed needs attention (from metrics.expiry_status).
# Reaching one of these is a decline; leaving all of them is a fix.
_ATTENTION_STATUS = frozenset({"expiring_soon", "lapsed", "stale"})
_EXPIRED_STATUS = frozenset({"lapsed", "stale"})

# Movement kinds, split by tone so rendering can lead with the fixes.
_FIXED_KINDS = frozenset({"cleared", "improved"})
_ATTENTION_KINDS = frozenset({"newly_lapsed", "newly_expiring", "declined"})


@dataclass(frozen=True)
class PortfolioMovement:
    """One week-over-week change for a member agency, framed as a fix or a look."""

    agency_id: str
    agency_name: str
    kind: str  # cleared | improved | newly_lapsed | newly_expiring | declined
    headline: str
    detail: str


@dataclass
class PortfolioDigest:
    rollup_id: str
    rollup_name: str
    as_of: dt.date
    first_run: bool
    member_count: int
    movements: list[PortfolioMovement] = field(default_factory=list)
    # The current week's member states, to persist as next week's baseline.
    snapshot: dict[str, dict[str, Any]] = field(default_factory=dict)


def _member_state(latest: dict[str, Any] | None) -> dict[str, Any] | None:
    """The comparable state for one member, or None if the artifact is unusable.

    A missing or malformed artifact (no overall block, non-numeric score) is
    dropped so one bad row never crashes the whole cohort digest."""
    if not latest or "overall" not in latest:
        return None
    overall = latest["overall"]
    try:
        score = float(overall["score"])
        grade = str(overall["grade"])
    except (KeyError, TypeError, ValueError):
        return None
    raw_days = (
        latest.get("categories", {})
        .get("freshness", {})
        .get("details", {})
        .get("days_until_expiry")
    )
    days = (
        int(raw_days)
        if isinstance(raw_days, (int, float)) and not isinstance(raw_days, bool)
        else None
    )
    return {
        "score": score,
        "grade": grade,
        "days_until_expiry": days,
        "expiry_status": expiry_status(days),
    }


def _grade_moved(prev: str, curr: str) -> int:
    """-1 if the grade dropped, +1 if it rose, 0 otherwise (unknown grades = 0)."""
    try:
        delta = GRADE_ORDER.index(curr) - GRADE_ORDER.index(prev)
    except ValueError:
        return 0
    return (delta > 0) - (delta < 0)


_STATUS_PHRASE = {
    "expiring_soon": "expiring soon",
    "lapsed": "expired",
    "stale": "long expired",
}


def _diff_member(
    agency_id: str, name: str, was: dict[str, Any], now: dict[str, Any]
) -> list[PortfolioMovement]:
    """Compare one member's last-week and this-week state into movements."""
    movements: list[PortfolioMovement] = []
    prev_status = str(was.get("expiry_status", "unknown"))
    curr_status = str(now["expiry_status"])

    # Expiry transitions first — the clearest cohort signal.
    if prev_status in _ATTENTION_STATUS and curr_status == "current":
        movements.append(
            PortfolioMovement(
                agency_id,
                name,
                "cleared",
                "Feed is current again",
                f"{name} was {_STATUS_PHRASE.get(prev_status, prev_status)} last week and now "
                "has a fresh service window. Someone re-exported it.",
            )
        )
    elif prev_status not in _EXPIRED_STATUS and curr_status in _EXPIRED_STATUS:
        movements.append(
            PortfolioMovement(
                agency_id,
                name,
                "newly_lapsed",
                "Feed expired this week",
                f"{name}'s schedule stopped covering service since last week. A re-export "
                "with a calendar that reaches further out brings it back.",
            )
        )
    elif prev_status == "current" and curr_status == "expiring_soon":
        movements.append(
            PortfolioMovement(
                agency_id,
                name,
                "newly_expiring",
                "Feed is expiring soon",
                f"{name}'s service window is now inside a month. A calm heads-up now beats a "
                "cliff-edge warning the week it dies.",
            )
        )

    # Score/grade movement, independent of the expiry window.
    delta = now["score"] - was["score"]
    grade_move = _grade_moved(str(was["grade"]), str(now["grade"]))
    if grade_move > 0 or delta >= SCORE_MOVE_POINTS:
        headline = (
            f"Grade rose from {was['grade']} to {now['grade']}"
            if grade_move > 0
            else f"Score rose {delta:.1f} points"
        )
        movements.append(
            PortfolioMovement(
                agency_id,
                name,
                "improved",
                headline,
                f"{name} went from {was['score']:.0f} to {now['score']:.0f} since last week.",
            )
        )
    elif grade_move < 0 or delta <= -SCORE_MOVE_POINTS:
        headline = (
            f"Grade slipped from {was['grade']} to {now['grade']}"
            if grade_move < 0
            else f"Score fell {abs(delta):.1f} points"
        )
        movements.append(
            PortfolioMovement(
                agency_id,
                name,
                "declined",
                headline,
                f"{name} went from {was['score']:.0f} to {now['score']:.0f}. The scorecard's "
                "top fixes point at the likely cause.",
            )
        )
    return movements


def build_portfolio_digest(
    rollup: Rollup,
    today: dt.date | None = None,
    previous_snapshot: dict[str, dict[str, Any]] | None = None,
) -> PortfolioDigest:
    """Diff a rollup's members against last week's snapshot into a digest.

    Loads each member's latest.json (reusing the rollup's member resolution),
    reads its score/grade/expiry status, and compares it to `previous_snapshot`.
    With no prior snapshot it is a first run: the current state is captured but
    no movement is reported (there is nothing to diff against yet). The returned
    digest carries the fresh snapshot for the caller to persist.
    """
    as_of = today or dt.date.today()
    previous = previous_snapshot or {}
    first_run = not previous

    current: dict[str, dict[str, Any]] = {}
    names: dict[str, str] = {}
    for agency_id in resolve_member_ids(rollup):
        latest = _load_latest(agency_id)
        state = _member_state(latest)
        if state is None:
            continue  # missing or malformed artifact: drop the row, don't crash
        current[agency_id] = state
        names[agency_id] = str(latest["agency"].get("name", agency_id)) if latest else agency_id

    movements: list[PortfolioMovement] = []
    if not first_run:
        for agency_id in sorted(current):
            was = previous.get(agency_id)
            if not was:
                continue  # a newly tracked member has no week-over-week history yet
            movements.extend(_diff_member(agency_id, names[agency_id], was, current[agency_id]))

    return PortfolioDigest(
        rollup_id=rollup.id,
        rollup_name=rollup.name,
        as_of=as_of,
        first_run=first_run,
        member_count=len(current),
        movements=movements,
        snapshot=current,
    )


def render_portfolio_digest(digest: PortfolioDigest) -> str:
    """Render the cohort digest as plain-language Markdown.

    Fix-framed: the fixed-this-week block comes first, then the feeds worth a
    look. A first run says it is a baseline; a quiet week says all clear plainly
    rather than sending an alarming blank."""
    lines = [
        f"# Portfolio digest: {digest.rollup_name} — {digest.as_of.isoformat()}",
        "",
    ]

    if digest.first_run:
        lines.append(
            f"First digest for {digest.rollup_name} ({digest.member_count} feed(s) tracked). "
            "Next week's will show what changed."
        )
        lines.append("")
        return "\n".join(lines)

    if not digest.movements:
        lines.append(
            f"All {digest.member_count} feed(s) in {digest.rollup_name} held steady this week. "
            "Nothing newly expired and no grades dropped."
        )
        lines.append("")
        return "\n".join(lines)

    fixed = [m for m in digest.movements if m.kind in _FIXED_KINDS]
    attention = [m for m in digest.movements if m.kind in _ATTENTION_KINDS]

    summary_parts = []
    if fixed:
        summary_parts.append(f"{len(fixed)} improved")
    if attention:
        summary_parts.append(f"{len(attention)} worth a look")
    lines.append(f"Across {digest.member_count} feed(s): " + ", ".join(summary_parts) + ".")
    lines.append("")

    def _emit(item: PortfolioMovement) -> None:
        lines.append(f"### {item.agency_name}")
        lines.append(f"**{item.headline}.** {item.detail}")
        lines.append("")

    # Lead with what got fixed.
    if fixed:
        lines.append("## Fixed this week")
        lines.append("")
        for item in fixed:
            _emit(item)
    if attention:
        lines.append("## Worth a look")
        lines.append("")
        for item in attention:
            _emit(item)
    return "\n".join(lines)


# --- snapshot persistence (same atomic pattern as liveness.save_state) --------


def state_path(rollup: Rollup) -> Path:
    """Where a rollup's week-over-week snapshot lives (beside its rollup JSON)."""
    return artifacts_dir() / "rollups" / f"{rollup.id}.state.json"


def load_snapshot(rollup: Rollup, path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Read last week's member snapshot; an absent file means a first run."""
    p = path or state_path(rollup)
    try:
        raw = json.loads(p.read_text())
    except (FileNotFoundError, ValueError):
        return {}
    members = raw.get("members")
    return members if isinstance(members, dict) else {}


def save_snapshot(
    rollup: Rollup,
    snapshot: dict[str, dict[str, Any]],
    as_of: dt.date,
    path: Path | None = None,
) -> Path:
    """Persist this week's snapshot as next week's baseline, atomically."""
    p = path or state_path(rollup)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "rollup": rollup.id,
        "as_of": as_of.isoformat(),
        "members": snapshot,
    }
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(p)
    return p
