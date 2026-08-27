"""Is this feed's closed calendar a planned service boundary, or a lapse?

`metrics.freshness` already answers that question when it scores a feed. A
campus or rural system whose calendars encode distinct service periods, and
whose expiry lands on one of those boundaries, gets the finding
`scorecard_planned_service_boundary` and planned-transition wording. A service
the registry declares seasonal or demand-response gets
`scorecard_intermittent_calendar_ended` for the same reason. Both are floored
rather than scored as a silent expiry (EXP-04, docs/ideation/03-expansions.md).

The alert stack never read either signal, which is the open half of EXP-04 and
of RR:R3. So a university system on its summer break received "trip planners
may have already dropped this agency" on the same morning its own scorecard
page said "confirm your next service period is published". Two surfaces, one
feed, opposite diagnoses, and the frightening one arrived by email.

This module is the single place every alert surface asks, and it answers only
from what a published artifact already states. It infers nothing new from the
feed, and it never decides whether an agency hears about a feed at all: a
planned boundary changes the wording of an alert, never its urgency, its
lead-time tier, its ordering, or whether it is sent. `alerts.py` and
`portfolio_digest.py` both read it, so the email and the weekly cohort digest
cannot disagree with each other or with the page.

Four deliberate limits keep the softer wording from becoming a hiding place:

- After the calendar has closed, "planned" requires that the scoring path
  already published one of the two findings. Nothing here re-derives it.
- Before the calendar closes there is no such finding yet, so the published
  `service_type` and `seasonal_boundary` facts stand in. Those are the same
  two inputs `metrics.freshness` uses, read from the artifact rather than
  recomputed.
- A feed lapsed a year or more is never planned, whatever the artifact says.
  That mirrors the `STALE_FEED_DAYS` hard floor in scoring, and it holds even
  for a malformed or hand-edited artifact that carries a planned code it
  should not.
- A feed with no readable end date is never planned. Without a date there is
  no boundary to have reached, and that case is already the worst freshness
  result the rubric has.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .metrics import STALE_FEED_DAYS

# The two freshness findings `metrics.freshness` publishes when a closed
# calendar is a transition between service periods rather than a lapse.
PLANNED_FINDING_CODES = frozenset(
    {
        "scorecard_planned_service_boundary",
        "scorecard_intermittent_calendar_ended",
    }
)

# Registry-declared service types whose calendars are expected to run in
# distinct periods (config.Agency.service_type).
INTERMITTENT_SERVICE_TYPES = frozenset({"seasonal", "demand_response"})


@dataclass(frozen=True)
class ServicePeriodRead:
    """What a published artifact says about why this feed's calendar is closing.

    ``planned`` is the only field an alert needs to choose its wording.
    ``declared`` separates a registry declaration ("this is a summer trolley")
    from a pattern the feed's own calendars encode ("this looks like academic
    terms"), because the two deserve different sentences. ``service_type`` is
    carried through so a declared read can name the service in plain words.
    """

    planned: bool
    declared: bool = False
    service_type: str = "fixed"

    @property
    def service_noun(self) -> str:
        """How to name a declared intermittent service in a sentence."""
        return "on-demand" if self.service_type == "demand_response" else "seasonal"


UNPLANNED = ServicePeriodRead(planned=False)


def _freshness_block(artifact: dict[str, Any] | None) -> dict[str, Any]:
    """The freshness category block, or an empty mapping for any other shape."""
    if not isinstance(artifact, dict):
        return {}
    categories = artifact.get("categories")
    if not isinstance(categories, dict):
        return {}
    freshness = categories.get("freshness")
    return freshness if isinstance(freshness, dict) else {}


def _published_finding_codes(freshness: dict[str, Any]) -> set[str]:
    """Finding codes the freshness card published, ignoring malformed rows."""
    findings = freshness.get("findings")
    if not isinstance(findings, list):
        return set()
    return {
        str(finding.get("code"))
        for finding in findings
        if isinstance(finding, dict) and finding.get("code")
    }


def read_service_period(
    artifact: dict[str, Any] | None,
    days_until_expiry: int | None,
) -> ServicePeriodRead:
    """Classify why this feed's calendar is closing, from the artifact alone.

    ``days_until_expiry`` is passed in rather than re-read so every caller
    classifies against the same number it is about to print; ``None`` means no
    end date could be read at all. Anything this function cannot confirm from
    the published record reads as unplanned, which keeps the existing lapse
    wording as the default for every feed.
    """
    # A feed with no readable end date is the worst freshness case there is
    # (`scorecard_no_expiry_date`, scored at zero), and nothing about it is
    # planned: without a date there is no boundary to have reached.
    if days_until_expiry is None:
        return UNPLANNED
    # The hard floor next, so no later branch can soften a long-dead feed.
    if days_until_expiry <= -STALE_FEED_DAYS:
        return UNPLANNED

    freshness = _freshness_block(artifact)
    details = freshness.get("details")
    if not isinstance(details, dict):
        return UNPLANNED

    service_type = str(details.get("service_type") or "fixed")
    declared = service_type in INTERMITTENT_SERVICE_TYPES

    if days_until_expiry <= 0:
        # The calendar has closed. The scoring path has already decided whether
        # that was a transition, so defer to what it published rather than
        # reaching a second opinion from the same inputs.
        if not _published_finding_codes(freshness) & PLANNED_FINDING_CODES:
            return UNPLANNED
        return ServicePeriodRead(planned=True, declared=declared, service_type=service_type)

    # The calendar is still open, so there is no finding to defer to. The two
    # facts `metrics.freshness` would use are published on the same card.
    detected = details.get("seasonal_boundary") is True
    if not (declared or detected):
        return UNPLANNED
    return ServicePeriodRead(planned=True, declared=declared, service_type=service_type)
