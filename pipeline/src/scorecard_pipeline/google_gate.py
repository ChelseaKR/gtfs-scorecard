"""Google/Apple Maps acceptance gate.

Google Transit (which also feeds Apple Maps in many regions) wants a feed to
cover at least four weeks of upcoming service from the day it is published, and
it drops feeds whose calendar has run short or expired. Once a feed's last
service date is inside that window the agency starts to fall out of trip
planners, so this is a gate worth flagging well before it bites.

This module reports forward coverage as a plain number of days and frames it as
something to fix: re-export the feed with a longer calendar before the window
closes. The narrative rationale lives in docs/rubric.md.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from .metrics import resolve_service_horizon_status

# Google Transit asks for at least four weeks (28 days) of service ahead of the
# publish date; feeds shorter than that risk being dropped from Google and Apple
# Maps. See docs/rubric.md for the citation.
MIN_FORWARD_DAYS = 28


def forward_coverage_days(last_service_date: dt.date | None, today: dt.date) -> int | None:
    """Days of service remaining from ``today``.

    Returns ``None`` when the feed has no end date to measure against. A value
    of 0 or less means the last day of service is today or already past.
    """
    if last_service_date is None:
        return None
    return (last_service_date - today).days


@dataclass(frozen=True)
class GoogleGate:
    """Whether a feed clears the Google/Apple Maps coverage window.

    ``status`` is "pass", "at_risk", or "fail". ``days_forward`` is the days of
    service left from today (``None`` when no end date is known). ``detail`` is a
    plain-language note for the agency.
    """

    status: str
    days_forward: int | None
    detail: str


def google_acceptance(
    last_service_date: dt.date | None,
    today: dt.date,
    *,
    min_days: int = MIN_FORWARD_DAYS,
) -> GoogleGate:
    """Check a feed's forward coverage against the Maps acceptance window.

    "pass" means at least ``min_days`` of service remain. "at_risk" means some
    service remains but fewer than ``min_days``, so the feed will fall out of
    Maps soon. "fail" means the feed has expired or carries no end date to check.
    """
    days_forward = forward_coverage_days(last_service_date, today)

    if days_forward is None:
        return GoogleGate(
            status="fail",
            days_forward=None,
            detail=(
                "This feed has no service end date, so Maps cannot tell how far "
                "ahead it runs. Set a feed_info end date and a calendar that "
                "covers at least the next four weeks, then re-export."
            ),
        )

    if days_forward <= 0:
        return GoogleGate(
            status="fail",
            days_forward=days_forward,
            detail=(
                "This feed's last day of service has passed, so Google and Apple "
                "Maps will stop showing your agency. Re-export with a calendar "
                "that covers at least the next four weeks."
            ),
        )

    if days_forward < min_days:
        return GoogleGate(
            status="at_risk",
            days_forward=days_forward,
            detail=(
                f"This feed has {days_forward} days of service left. Maps needs "
                f"at least four weeks ({min_days} days) of upcoming service, so "
                "your agency will fall out of trip planners soon. Re-export with a "
                "longer calendar."
            ),
        )

    return GoogleGate(
        status="pass",
        days_forward=days_forward,
        detail=(
            f"This feed has {days_forward} days of service ahead, clearing the "
            f"four-week ({min_days}-day) window Maps asks for."
        ),
    )


def _iso_date(raw: Any) -> dt.date | None:
    """Parse an ISO date from artifact JSON; anything else is no date."""
    if not isinstance(raw, str):
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def _artifact_expiry(details: dict[str, Any]) -> dt.date | None:
    """The date this feed stops being usable, matching gtfs.FeedDates.effective_expiry.

    A feed drops out of Maps at the earlier of the validity window feed_info
    declares and the last date its calendars actually run. Reading only the
    calendar tail would call a feed whose feed_info expired in 2023 a pass
    because calendar.txt still lists dates in 2030, contradicting the freshness
    card on the same page. Artifacts from schema 1.4 and 1.7 predate the
    published ``effective_expiry_date`` and are still the latest snapshot for
    some feeds, so derive the same minimum from the two dates they do carry.
    """
    published = _iso_date(details.get("effective_expiry_date"))
    if published is not None:
        return published
    declared = _iso_date(details.get("feed_end_date"))
    scheduled = _iso_date(details.get("last_service_date"))
    candidates = [d for d in (declared, scheduled) if d is not None]
    return min(candidates) if candidates else None


def from_artifact(artifact: dict[str, Any], today: dt.date) -> GoogleGate:
    """Read a published artifact's service end date and check the gate.

    Prefers ``effective_expiry_date`` under
    ``artifact["categories"]["freshness"]["details"]``, falling back to the
    earlier of ``feed_end_date`` and ``last_service_date`` for artifacts written
    before that field existed. Missing or unparsable values are treated as no
    end date.
    """
    details = artifact.get("categories", {}).get("freshness", {}).get("details", {})
    if not isinstance(details, dict):
        details = {}

    gate = google_acceptance(_artifact_expiry(details), today)
    if (
        gate.status == "pass"
        and resolve_service_horizon_status(details, artifact.get("snapshot_date"))
        == "unusually_distant"
    ):
        return GoogleGate(
            status=gate.status,
            days_forward=gate.days_forward,
            detail=(
                "This feed clears the four-week coverage window, but its service end date "
                "is unusually distant. Confirm that date is intentional before treating it "
                "as evidence of ongoing maintenance."
            ),
        )
    return gate
