"""Authoritative-rule links for scorecard findings.

The scorecard wraps the canonical MobilityData gtfs-validator and adds a
plain-language scoring layer on top. The Cal-ITP / state-DOT audience already
works from the canonical GTFS Validator rules and GTFS Best Practices (the
California statewide GTFS quality reports are structured around exactly those),
so every finding earns credibility by pointing back to its authoritative rule.

This module is the single source of truth for that finding -> rule mapping. It
keys each finding code the scorecard renders a fix page for to one of four
authorities:

- ``VALIDATOR`` — a canonical gtfs-validator notice. The scorecard's code is
  the validator's own notice code, so the link is built deterministically from
  it. A few scorecard-computed findings re-detect a validator concept under a
  scorecard code; those carry the canonical notice in ``canonical`` so the
  audience recognises the alias.
- ``BEST_PRACTICE`` — a GTFS Best Practices recommendation, for scorecard
  completeness checks the validator does not flag (a present-but-empty field is
  valid GTFS, just poorer rider experience).
- ``REFERENCE`` — the GTFS Schedule reference section that defines the field,
  used where no Best Practice states the expectation but the spec field does.
- ``REALTIME_REFERENCE`` — the GTFS-Realtime reference's message definitions,
  for the scorecard's realtime-quality findings. The canonical gtfs-validator
  runs against GTFS Schedule only, so no validator notice applies to a
  realtime finding; Best Practices is Schedule-scoped too, so the message spec
  itself is the honest authority.

Findings with no honest mapping are left out of the table rather than linked to
a tenuous one. ``docs/decisions/0024-validator-rule-links.md`` records why and
how each URL was verified; ``tests/test_rule_links.py`` keeps the table
well-formed.
"""

from __future__ import annotations

from dataclasses import dataclass

# The canonical validator rule reference. RULES.md in the gtfs-validator repo
# now redirects to this hosted page, which is the authoritative, deep-linkable
# source (verified 2026-06-30). Each notice is anchored as "<notice>-rule".
VALIDATOR_RULES_PAGE = "https://gtfs-validator.mobilitydata.org/rules.html"
BEST_PRACTICES_PAGE = "https://gtfs.org/schedule/best-practices/"
SCHEDULE_REFERENCE_PAGE = "https://gtfs.org/schedule/reference/"
REALTIME_REFERENCE_PAGE = "https://gtfs.org/documentation/realtime/reference/"

# RuleLink.kind values.
VALIDATOR = "validator"
BEST_PRACTICE = "best_practice"
REFERENCE = "reference"
REALTIME_REFERENCE = "realtime_reference"

# Human label for each authority, shown next to the link.
AUTHORITY_LABELS = {
    VALIDATOR: "MobilityData GTFS Validator rules",
    BEST_PRACTICE: "GTFS Best Practices",
    REFERENCE: "GTFS Schedule reference",
    REALTIME_REFERENCE: "GTFS-Realtime reference",
}


def validator_rule_url(notice: str) -> str:
    """Deep link to a gtfs-validator notice on the canonical rules page.

    Every notice on rules.html is anchored as ``<notice>-rule``; the validator's
    JSON report uses the same snake_case code, so the scorecard can build the
    link from a finding's code with no extra lookup.
    """
    return f"{VALIDATOR_RULES_PAGE}#{notice}-rule"


@dataclass(frozen=True)
class RuleLink:
    """One finding code's link to its authoritative rule."""

    kind: str  # VALIDATOR | BEST_PRACTICE | REFERENCE
    url: str
    # Canonical validator notice when the scorecard's finding code diverges from
    # it (so the page can show the alias the audience knows); None when the code
    # already is the canonical notice or no validator notice applies.
    canonical: str | None = None

    @property
    def is_validator(self) -> bool:
        return self.kind == VALIDATOR

    @property
    def authority(self) -> str:
        return AUTHORITY_LABELS[self.kind]


def _v(notice: str, *, canonical: str | None = None) -> RuleLink:
    """A validator-notice link. ``canonical`` is set only when the scorecard's
    finding code differs from the notice it maps to."""
    return RuleLink(kind=VALIDATOR, url=validator_rule_url(notice), canonical=canonical)


# Finding code -> authoritative rule. Keys are the codes the scorecard renders a
# fix page for (docs/fixes/<code>.md); tests assert every key has a fix page and
# vice versa for scorecard_* codes. The web app reads this same table from
# web/src/generated/constants.js (rendered by `scorecard render-constants`), so
# there is no hand-kept mirror to sync.
RULE_LINKS: dict[str, RuleLink] = {
    # --- Canonical gtfs-validator notices (code == notice) --------------------
    "big_gap_in_service": _v("big_gap_in_service"),
    "equal_shape_distance_same_coordinates": _v("equal_shape_distance_same_coordinates"),
    "expired_calendar": _v("expired_calendar"),
    "fast_travel_between_consecutive_stops": _v("fast_travel_between_consecutive_stops"),
    "fast_travel_between_far_stops": _v("fast_travel_between_far_stops"),
    "feed_expiration_date7_days": _v("feed_expiration_date7_days"),
    "feed_expiration_date30_days": _v("feed_expiration_date30_days"),
    "invalid_currency_amount": _v("invalid_currency_amount"),
    "missing_feed_contact_email_and_url": _v("missing_feed_contact_email_and_url"),
    "missing_recommended_field": _v("missing_recommended_field"),
    "missing_recommended_file": _v("missing_recommended_file"),
    "missing_required_column": _v("missing_required_column"),
    "missing_timepoint_value": _v("missing_timepoint_value"),
    "mixed_case_recommended_field": _v("mixed_case_recommended_field"),
    "route_color_contrast": _v("route_color_contrast"),
    "service_has_no_active_day_of_the_week": _v("service_has_no_active_day_of_the_week"),
    "service_window_outside_feed_period": _v("service_window_outside_feed_period"),
    "stop_too_far_from_shape": _v("stop_too_far_from_shape"),
    "stop_too_far_from_shape_using_user_distance": _v(
        "stop_too_far_from_shape_using_user_distance"
    ),
    "stop_without_stop_time": _v("stop_without_stop_time"),
    "trip_coverage_not_active_for_next7_days": _v("trip_coverage_not_active_for_next7_days"),
    "trip_distance_exceeds_shape_distance_below_threshold": _v(
        "trip_distance_exceeds_shape_distance_below_threshold"
    ),
    "unknown_column": _v("unknown_column"),
    "unknown_file": _v("unknown_file"),
    "unused_shape": _v("unused_shape"),
    # --- Scorecard-computed findings that alias a validator notice ------------
    # The scorecard derives freshness and contact itself, but each maps cleanly
    # onto a canonical notice the audience already knows.
    "scorecard_missing_feed_info_dates": _v(
        "missing_feed_info_date", canonical="missing_feed_info_date"
    ),
    "scorecard_no_feed_contact": _v(
        "missing_feed_contact_email_and_url", canonical="missing_feed_contact_email_and_url"
    ),
    # --- Scorecard-specific completeness findings (no validator notice) -------
    # A present-but-empty field is valid GTFS, so the validator says nothing;
    # the expectation lives in GTFS Best Practices or the Schedule reference.
    "scorecard_missing_headsigns": RuleLink(
        kind=BEST_PRACTICE, url=f"{BEST_PRACTICES_PAGE}#tripstxt"
    ),
    "scorecard_no_fare_data": RuleLink(
        kind=BEST_PRACTICE, url=f"{BEST_PRACTICES_PAGE}#fare_attributestxt"
    ),
    "scorecard_wheelchair_boarding_unknown": RuleLink(
        kind=REFERENCE, url=f"{SCHEDULE_REFERENCE_PAGE}#stopstxt"
    ),
    "scorecard_wheelchair_accessible_unknown": RuleLink(
        kind=REFERENCE, url=f"{SCHEDULE_REFERENCE_PAGE}#tripstxt"
    ),
    # Freshness: the scorecard's own effective-expiry date (the later of
    # feed_info.feed_end_date and the last calendar/calendar_dates service day),
    # which is not the same computation as any single validator notice, so it is
    # not aliased to expired_calendar or feed_expiration_date7/30_days. Best
    # Practices states the expectation directly under general publishing
    # practices: a feed should stay valid at least 7, ideally 30+, days out.
    "scorecard_feed_expired": RuleLink(
        kind=BEST_PRACTICE, url=f"{BEST_PRACTICES_PAGE}#dataset-publishing-general-practices"
    ),
    "scorecard_feed_expiring_soon": RuleLink(
        kind=BEST_PRACTICE, url=f"{BEST_PRACTICES_PAGE}#dataset-publishing-general-practices"
    ),
    # Rider experience completeness: readability (mixed-case names) and station
    # navigation, neither of which the validator flags.
    "scorecard_stop_names_all_caps": RuleLink(
        kind=BEST_PRACTICE, url=f"{BEST_PRACTICES_PAGE}#stopstxt"
    ),
    "scorecard_station_no_pathways": RuleLink(
        kind=REFERENCE, url=f"{SCHEDULE_REFERENCE_PAGE}#pathwaystxt"
    ),
    # GTFS-Flex (docs/decisions/0007-gtfs-flex-awareness.md): zero-deduction
    # completeness findings, so a rider can actually use a service the feed
    # already advertises. booking_rules.txt is a Schedule reference field (the
    # Flex extension folds into the standard reference page), not a stated Best
    # Practice, so REFERENCE is the honest kind.
    "scorecard_flex_no_booking_rules": RuleLink(
        kind=REFERENCE, url=f"{SCHEDULE_REFERENCE_PAGE}#booking_rulestxt"
    ),
    # Realtime quality (rt.py): reachability of each of the three GTFS-Realtime
    # feed types, and how much of the schedule TripUpdates actually covers. The
    # canonical validator scores GTFS Schedule only, so these have no validator
    # notice or Best Practice to alias; the message spec itself is the honest
    # authority for each feed type.
    "scorecard_rt_trip_updates_unreachable": RuleLink(
        kind=REALTIME_REFERENCE, url=f"{REALTIME_REFERENCE_PAGE}#message-tripupdate"
    ),
    "scorecard_rt_vehicle_positions_unreachable": RuleLink(
        kind=REALTIME_REFERENCE, url=f"{REALTIME_REFERENCE_PAGE}#message-vehicleposition"
    ),
    "scorecard_rt_service_alerts_unreachable": RuleLink(
        kind=REALTIME_REFERENCE, url=f"{REALTIME_REFERENCE_PAGE}#message-alert"
    ),
    # Trip coverage: the reference defines TripUpdate but does not itself state
    # a "100% of operating trips" expectation (that figure is Caltrans v4.0
    # guidance, cited in rt.py and shown on the fix page); the message
    # definition is still the closest spec anchor for what a TripUpdate is.
    "scorecard_rt_trip_coverage": RuleLink(
        kind=REALTIME_REFERENCE, url=f"{REALTIME_REFERENCE_PAGE}#message-tripupdate"
    ),
}


def rule_link_for(code: str) -> RuleLink | None:
    """The authoritative rule for a finding code, or None if unmapped.

    Falls back to building a validator-notice link for any non-scorecard code
    not in the curated table: those codes are raw gtfs-validator notices and the
    rules page anchors every notice as ``<code>-rule``, so the link is correct
    even for notices that don't yet have a curated fix page.
    """
    if code in RULE_LINKS:
        return RULE_LINKS[code]
    if code and not code.startswith("scorecard_"):
        return _v(code)
    return None
