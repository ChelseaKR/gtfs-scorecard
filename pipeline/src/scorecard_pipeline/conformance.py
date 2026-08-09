"""Conformance trust mark: a pass/not-yet credential a feed can earn.

The grade is a gradient. A credential needs a bright line, so an agency can say
"this feed meets the bar" and a state program can point to one. The mark is
awarded when a feed clears three plain requirements at once, each mapped to a
thing a rider actually feels:

- Valid: no validator errors that would break a rider's trip.
- Current: the service calendar has not lapsed and is not about to.
- Accessible: the feed states wheelchair access on most stops and trips.

This extends the same checks the NTD readiness pillars and the grade already
use; it does not move any category score. The framing is a credential to earn,
never a failure to publish: a feed that misses is "not yet", with the gap named.
The accessibility floor measures what the feed publishes, not whether a stop is
physically usable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .metrics import expiry_status, resolve_service_horizon_status

AWARDED = "awarded"
NOT_YET = "not_yet"

# A feed earns the mark when it states wheelchair access on at least this share
# of stops and trips. Presence, not usability: see the module docstring.
ACCESSIBILITY_FLOOR = 90.0


@dataclass(frozen=True)
class Criterion:
    key: str  # valid | current | accessible
    met: bool
    detail: str


@dataclass(frozen=True)
class Conformance:
    awarded: bool
    criteria: list[Criterion]
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "awarded": self.awarded,
            "status": AWARDED if self.awarded else NOT_YET,
            "summary": self.summary,
            "criteria": [{"key": c.key, "met": c.met, "detail": c.detail} for c in self.criteria],
        }


def _valid(artifact: dict[str, Any]) -> Criterion:
    correctness = artifact.get("categories", {}).get("correctness", {})
    if correctness.get("status") != "measured":
        return Criterion("valid", False, "Validation has not run for this feed yet.")
    errors = sum(
        1 for f in correctness.get("findings", []) if str(f.get("severity", "")).upper() == "ERROR"
    )
    if errors:
        plural = "s" if errors != 1 else ""
        return Criterion("valid", False, f"{errors} validator error{plural} to resolve.")
    return Criterion("valid", True, "Passes validation with no errors.")


def _current(artifact: dict[str, Any]) -> Criterion:
    details = artifact.get("categories", {}).get("freshness", {}).get("details", {})
    days = details.get("days_until_expiry")
    status = expiry_status(days)
    if status == "current":
        if (
            resolve_service_horizon_status(details, artifact.get("snapshot_date"))
            == "unusually_distant"
        ):
            return Criterion(
                "current",
                True,
                "The published window is current, but its service end date is unusually "
                "distant; confirm that date is intentional.",
            )
        return Criterion("current", True, f"Service data covers the next {days} days.")
    if status == "expiring_soon":
        return Criterion(
            "current", False, f"Service data runs out in {days} days; renew to qualify."
        )
    if status in ("lapsed", "stale"):
        return Criterion("current", False, f"Service data expired {-int(days)} days ago.")
    return Criterion("current", False, "No service end date could be read.")


def _accessible(artifact: dict[str, Any]) -> Criterion:
    access = (
        artifact.get("categories", {})
        .get("completeness", {})
        .get("details", {})
        .get("accessibility", {})
    )
    stops = access.get("stops_stated_pct")
    trips = access.get("trips_stated_pct")
    if not isinstance(stops, (int, float)) or not isinstance(trips, (int, float)):
        return Criterion("accessible", False, "Accessibility completeness has not been measured.")
    if stops >= ACCESSIBILITY_FLOOR and trips >= ACCESSIBILITY_FLOOR:
        return Criterion(
            "accessible",
            True,
            f"States wheelchair access on {round(stops)}% of stops and {round(trips)}% of trips.",
        )
    floor = round(ACCESSIBILITY_FLOOR)
    return Criterion(
        "accessible",
        False,
        f"States wheelchair access on {round(stops)}% of stops and {round(trips)}% of trips; "
        f"the mark needs {floor}% of each.",
    )


def assess(artifact: dict[str, Any]) -> Conformance:
    """Assess whether a feed earns the conformance mark."""
    criteria = [_valid(artifact), _current(artifact), _accessible(artifact)]
    awarded = all(c.met for c in criteria)
    return Conformance(awarded, criteria, _summary(criteria))


def _summary(criteria: list[Criterion]) -> str:
    met_count = sum(criterion.met for criterion in criteria)
    if met_count == len(criteria):
        return (
            "This feed earns the conformance mark: valid, current, and stating "
            "wheelchair access on nearly every stop and trip."
        )

    gaps = " ".join(criterion.detail for criterion in criteria if not criterion.met)
    if met_count == 0:
        lede = (
            "This feed does not meet the conformance requirements yet. Here is what the mark needs:"
        )
    else:
        requirements_left = len(criteria) - met_count
        count = "One" if requirements_left == 1 else "Two"
        plural = "" if requirements_left == 1 else "s"
        verb = "remains" if requirements_left == 1 else "remain"
        lede = f"{count} requirement{plural} {verb} for this feed to earn the conformance mark."
    return f"{lede} {gaps}"
