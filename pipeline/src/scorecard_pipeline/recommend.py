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

from .metrics import Finding

log = logging.getLogger(__name__)


def _safe(label: str, fn: Callable[[], list[Finding]]) -> list[Finding]:
    try:
        return fn()
    except Exception as exc:
        log.warning("recommendation check %s failed: %s", label, exc)
        return []


def gather_recommendations(gtfs_zip_path: str) -> list[dict[str, object]]:
    """Run the beyond-the-grade checks over a feed and return serialized findings.

    Safe to call in the scoring path: each check is sandboxed, and the result is
    a list of finding dicts (same shape as a category's findings) for the
    artifact's `recommendations` block."""
    from .accessibility import accessibility_audit
    from .fares import fares_v2_findings
    from .flex import detect_flex, flex_completeness_findings

    findings: list[Finding] = []
    findings += _safe("fares_v2", lambda: fares_v2_findings(gtfs_zip_path))
    findings += _safe(
        "flex_completeness", lambda: flex_completeness_findings(detect_flex(gtfs_zip_path))
    )
    findings += _safe("accessibility", lambda: accessibility_audit(gtfs_zip_path))
    return [f.to_json() for f in findings]
