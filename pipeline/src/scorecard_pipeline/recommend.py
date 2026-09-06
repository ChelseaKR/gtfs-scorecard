"""Recommendations beyond the grade.

The four scored categories drive the letter grade. These checks surface
opportunities that the grade deliberately does not move yet — Fares v2 (rider
categories, fare media, tap-to-pay), GTFS-Flex completeness for demand-response
service, and the deeper accessibility fields (route-color contrast, screen-reader
stop names, station pathways). They are computed at score time because they read
the GTFS file, which the renderer does not have, and attached to the artifact as
a separate `recommendations` block so they never change a category score.

Each check is isolated: one failing or absent file must not break a score, so a
check that raises is skipped with a warning rather than aborting the run.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

from .metrics import Finding

log = logging.getLogger(__name__)


def _safe(label: str, fn: Callable[[], list[Finding]]) -> list[Finding] | None:
    """Run one check, returning its findings, or None when it could not run.

    The empty list is a real answer: the check ran and has nothing to suggest.
    None is the other answer, and the two must not be the same value. Returning
    [] for a crash made a feed whose accessibility audit died on a malformed
    table render exactly like a feed with no accessibility gaps at all.
    """
    try:
        return fn()
    except Exception as exc:
        log.warning("recommendation check %s failed: %s", label, exc)
        return None


@dataclass(frozen=True)
class Recommendations:
    """The beyond-the-grade rows, and the checks that could not produce any.

    ``rows`` is the artifact's ``recommendations`` block, unchanged on the wire.
    ``not_measured`` names the category tags whose check raised, so an empty
    ``rows`` can still be told apart from a clean feed. It reaches the artifact
    only when it is non-empty, so a normal run's artifact is unchanged and a
    reader who does see the key knows it means something.
    """

    rows: list[dict[str, object]]
    not_measured: tuple[str, ...] = ()

    def artifact_block(self) -> dict[str, object]:
        """The artifact keys this result contributes.

        ``recommendations_not_measured`` appears only when a check could not
        run, so a normal run's artifact is byte-for-byte what it was.
        """
        block: dict[str, object] = {"recommendations": self.rows}
        if self.not_measured:
            block["recommendations_not_measured"] = list(self.not_measured)
        return block


def gather_recommendations(gtfs_zip_path: str) -> Recommendations:
    """Run the beyond-the-grade checks over a feed and return serialized findings.

    Safe to call in the scoring path: each check is sandboxed, and the result is
    a list of finding dicts (same shape as a category's findings, plus a
    `category` tag) for the artifact's `recommendations` block. The tag lets the
    renderer give the accessibility-depth checks (EXP-05) their own celebrated
    presentation instead of burying them in the generic "beyond the grade" list,
    without changing the on-the-wire shape any existing consumer relies on.

    `not_measured` names the category tags whose check could not run, so an
    empty list of rows for a category is never read as a clean bill of health
    for it."""
    from .accessibility import accessibility_audit
    from .fares import fares_v2_findings
    from .flex import detect_flex, flex_completeness_findings

    checks: list[tuple[str, str, Callable[[], list[Finding]]]] = [
        ("fares", "fares_v2", lambda: fares_v2_findings(gtfs_zip_path)),
        (
            "flex",
            "flex_completeness",
            lambda: flex_completeness_findings(detect_flex(gtfs_zip_path)),
        ),
        ("accessibility", "accessibility", lambda: accessibility_audit(gtfs_zip_path)),
    ]
    tagged: list[tuple[str, Finding]] = []
    not_measured: list[str] = []
    for category, label, check in checks:
        findings = _safe(label, check)
        if findings is None:
            not_measured.append(category)
            continue
        tagged.extend((category, f) for f in findings)
    return Recommendations(
        [{**f.to_json(), "category": category} for category, f in tagged],
        tuple(not_measured),
    )
