"""Detect GTFS-Flex (demand-responsive) service and report whether riders can
tell how to book it.

GTFS-Flex describes dial-a-ride, zone, and on-request service that classic GTFS
cannot. Small and rural agencies increasingly publish it, and a fixed-route lens
leaves their real operation invisible. This detects flex service and, when it is
present, checks the one thing a rider most needs: a way to book a trip. Findings
are framed as fixes, and in this first slice they do not change the grade
(ADR 0007); the value is representation and guidance, not a new penalty. The
gtfs-validator already covers the structural validity of the flex files.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from typing import Any

from .gtfs import read_tables
from .metrics import Finding

# Files unique to GTFS-Flex. Their presence is the standard, reliable signal that
# a feed describes flexible service.
FLEX_FILES = ("locations.geojson", "location_groups.txt", "booking_rules.txt")

# Fields on a booking rule that tell a rider how to reserve a trip.
_CONTACT_FIELDS = (
    "phone_number",
    "info_url",
    "booking_url",
    "message",
    "pickup_message",
    "drop_off_message",
)


@dataclass(frozen=True)
class FlexProfile:
    """What the scorecard knows about a feed's flexible service."""

    has_flex: bool
    has_booking_rules: bool
    booking_reachable: bool
    booking_rule_count: int

    def to_details(self) -> dict[str, Any]:
        return {
            "has_flex": self.has_flex,
            "has_booking_rules": self.has_booking_rules,
            "booking_reachable": self.booking_reachable,
            "booking_rule_count": self.booking_rule_count,
        }


def _zip_names(gtfs_zip_path: str) -> set[str]:
    with zipfile.ZipFile(gtfs_zip_path) as zf:
        return set(zf.namelist())


def _booking_reachable(rows: list[dict[str, str]]) -> bool:
    """True when at least one booking rule lets a rider actually book: it is
    real-time bookable (booking_type 0), or it carries a phone number, link, or
    message that says how."""
    for row in rows:
        if row.get("booking_type", "").strip() == "0":
            return True
        if any(row.get(field, "").strip() for field in _CONTACT_FIELDS):
            return True
    return False


def detect_flex(gtfs_zip_path: str) -> FlexProfile:
    """Detect flexible service in a feed and whether riders can book it.

    Detection is by the flex files (see ADR 0007); ``stop_times.txt`` is not read
    here, so the large-file safety cap is never a factor.
    """
    names = _zip_names(gtfs_zip_path)
    booking = read_tables(gtfs_zip_path, ["booking_rules.txt"])["booking_rules.txt"]
    has_flex = any(name in names for name in FLEX_FILES)
    has_booking = bool(booking)
    return FlexProfile(
        has_flex=has_flex,
        has_booking_rules=has_booking,
        booking_reachable=_booking_reachable(booking) if has_flex else False,
        booking_rule_count=len(booking),
    )


@dataclass(frozen=True)
class FlexCompleteness:
    """How completely a feed describes its flexible service for riders.

    Only meaningful when the feed actually publishes flex. A fixed-route feed
    that does not publish flex is not graded here: ``present`` is False and the
    score does not apply, so demand-responsive coverage is never held against an
    agency that simply does not run it.
    """

    score: float
    present: bool
    components: dict[str, float]
    notes: list[str]

    def to_details(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 1),
            "present": self.present,
            "components": {k: round(v, 2) for k, v in self.components.items()},
            "notes": list(self.notes),
        }


def flex_completeness(profile: FlexProfile) -> FlexCompleteness:
    """Score how completely a flex feed tells riders how to use the service.

    Built on the existing detection (``detect_flex``); it reads only what the
    profile already carries and never re-parses the feed. Components each score
    0..1 and average to a 0..100 score:

    - ``service_zones``: the flex files describe a service area at all.
    - ``booking_rules``: ``booking_rules.txt`` is present.
    - ``booking_reachable``: a rider can actually book (real-time bookable, or a
      phone number, link, or message says how).
    - ``booking_contact``: at least one booking rule carries contact or booking
      info, which here is the reachability signal the profile already records.

    A feed without flex returns ``present=False`` and ``score=0.0`` with a
    neutral note; that score is not applicable and should not be graded.
    """
    if not profile.has_flex:
        return FlexCompleteness(
            score=0.0,
            present=False,
            components={},
            notes=[
                "This feed does not publish flexible service, so flex completeness does not apply."
            ],
        )

    components: dict[str, float] = {
        # Detection fires on a flex file, so a detected flex feed describes a
        # service area in some form.
        "service_zones": 1.0,
        "booking_rules": 1.0 if profile.has_booking_rules else 0.0,
        "booking_reachable": 1.0 if profile.booking_reachable else 0.0,
        "booking_contact": 1.0 if profile.booking_reachable else 0.0,
    }
    score = 100.0 * sum(components.values()) / len(components)

    notes: list[str] = []
    if not profile.has_booking_rules:
        notes.append(
            "Flex zones are published but there is no booking_rules.txt, so "
            "riders can see the area but not how to book."
        )
    elif not profile.booking_reachable:
        notes.append(
            "Booking rules are present but none say how to book, so riders "
            "have no way to reserve a trip."
        )
    else:
        notes.append("Flexible service is described and riders are told how to book it.")

    return FlexCompleteness(
        score=score,
        present=True,
        components=components,
        notes=notes,
    )


def flex_completeness_findings(profile: FlexProfile) -> list[Finding]:
    """Findings for gaps in a flex feed's rider-facing completeness, as fixes.

    Returns nothing for a feed without flex: demand-responsive coverage is not
    expected of every agency. Zero-deduction, like the rest of this slice
    (ADR 0007): they guide without moving the grade.
    """
    if not profile.has_flex:
        return []
    if not profile.has_booking_rules:
        return [
            Finding(
                code="scorecard_flex_completeness_no_booking_rules",
                severity="WARNING",
                count=1,
                what="Flex zones are published but no booking_rules.txt is present.",
                why="Riders can see the service area but not how to book, so they "
                "can't complete a trip.",
                fix="Add booking_rules.txt with how far ahead and how to reserve "
                "(phone, app, or web).",
                effort="A small file; one rule often covers the whole service.",
                deduction=0.0,
            )
        ]
    if not profile.booking_reachable:
        return [
            Finding(
                code="scorecard_flex_completeness_no_contact",
                severity="WARNING",
                count=profile.booking_rule_count,
                what="The booking rules carry no contact or booking info (no phone "
                "number, link, or message).",
                why="Riders need a way to reach the agency to reserve an on-request trip.",
                fix="Add a phone_number, info_url, or message to each booking rule, "
                "or mark it real-time bookable.",
                effort="One or two fields per booking rule.",
                deduction=0.0,
            )
        ]
    return []


def flex_findings(profile: FlexProfile) -> list[Finding]:
    """Rider-facing findings for a feed's flexible service, framed as fixes.

    Zero-deduction in this first slice (ADR 0007): they inform and guide without
    moving the grade.
    """
    if not profile.has_flex:
        return []
    if not profile.has_booking_rules:
        return [
            Finding(
                code="scorecard_flex_no_booking_rules",
                severity="WARNING",
                count=1,
                what="This feed offers flexible service that riders book ahead, but "
                "it has no booking_rules.txt.",
                why="Riders can see the service area but not how or when to book a "
                "trip. Without that, they can't use the service.",
                fix="Add booking_rules.txt saying how far ahead and how to book "
                "(phone, app, or web).",
                effort="A small file; one rule often covers the whole service.",
                deduction=0.0,
            )
        ]
    if not profile.booking_reachable:
        return [
            Finding(
                code="scorecard_flex_booking_unreachable",
                severity="WARNING",
                count=profile.booking_rule_count,
                what="The feed's booking rules don't say how to book (no phone "
                "number, link, or message).",
                why="Riders need a way to reach the agency to reserve an on-request trip.",
                fix="Add a phone_number, info_url, or message to each booking rule, "
                "or mark it real-time bookable.",
                effort="One or two fields per booking rule.",
                deduction=0.0,
            )
        ]
    return [
        Finding(
            code="scorecard_flex_service",
            severity="INFO",
            count=1,
            what="This feed includes flexible (demand-responsive) service, and "
            "riders are told how to book it.",
            why="Dial-a-ride and zone service are described for trip planners, not "
            "just fixed routes.",
            fix="No action needed.",
            effort="None.",
            deduction=0.0,
        )
    ]
