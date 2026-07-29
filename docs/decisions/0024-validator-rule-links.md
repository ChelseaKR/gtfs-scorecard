# 0024: Link findings to their canonical MobilityData rule

Status: accepted (2026-06)

## Context

The Cal-ITP / state-DOT audience this scorecard is built for already works from
canonical authorities: the California statewide GTFS quality reports are
structured around MobilityData gtfs-validator notices and GTFS Best Practices.
The scorecard wraps the same validator, but its findings carried only the notice
code as plain text, with no path back to the authoritative rule. Naming the
canonical rule next to each finding is the cheapest credibility win with that
audience, and it lets a reader confirm the scorecard is not inventing checks.

## Decision

Add a single-source-of-truth mapping from each finding the scorecard renders a
fix page for to its authoritative rule, and surface a verified link to that rule.

- `pipeline/src/scorecard_pipeline/rule_links.py` holds the mapping (`RULE_LINKS`)
  and the deterministic URL helper (`validator_rule_url`). Three authorities:
  - **Validator** — a canonical gtfs-validator notice. The scorecard's code is
    the validator's own snake_case notice code, so the link is built as
    `rules.html#<notice>-rule` with no per-code table of URLs to drift.
  - **Best Practices** — for completeness checks the validator does not flag (a
    present-but-empty field is valid GTFS): `gtfs.org/schedule/best-practices/`.
  - **Reference** — the GTFS Schedule reference section that defines the field,
    used where no Best Practice states the expectation: `gtfs.org/schedule/reference/`.
- Where a scorecard-computed code diverges from the notice it maps to
  (`scorecard_missing_feed_info_dates` → `missing_feed_info_date`,
  `scorecard_no_feed_contact` → `missing_feed_contact_email_and_url`), the
  canonical notice is recorded as an alias and named on the page so the audience
  recognises it.
- Findings with no honest mapping are left unlinked rather than pointed at a
  tenuous rule.

### Where links surface

- Every `/fix/<code>/` page gains an "Authoritative rule" section (rendered from
  the mapping in `_fix_rule_reference`, so the Markdown fix docs stay clean).
- The "Validator rule" line on agency findings (the static "Everything we
  checked" list and the feed-diff cards) links the rule via `_rule_ref_link`.
- The interactive app (`web/src/app.js`) links the validator rule for any
  non-`scorecard_` finding code, mirroring the deterministic transform.

## Why link to rules.html, not RULES.md

The task framed the link target as the validator repo's `RULES.md`. That file now
contains a single line redirecting to `https://gtfs-validator.mobilitydata.org/rules.html`,
which is the live, deep-linkable authoritative page (every notice is anchored as
`<code>-rule`). Linking the hosted page is therefore the honest "canonical rule
documentation" and the only target that supports a working anchor.

## Verification

All anchors were verified by hand against the live pages on 2026-06-30, not
inferred:

- The 18 validator notices plus the two aliases (`missing_feed_info_date`,
  `missing_feed_contact_email_and_url`) each have a matching `id="<code>-rule"`
  in `rules.html`.
- The Best Practices anchors (`#tripstxt`, `#fare_attributestxt`) and the
  reference anchors (`#stopstxt`, `#tripstxt`) exist on the respective gtfs.org
  pages, and trip_headsign / fare / wheelchair guidance lives under them.

`tests/test_rule_links.py` keeps the table well-formed offline: every mapped code
has a fix page and every fix page is mapped, validator links are anchored
`<notice>-rule`, scorecard codes that map to a notice name their alias, and the
non-validator links point at gtfs.org sections. The live URLs are intentionally
not fetched in CI (no network); re-verify them when the validator's rules page
layout changes.

**2026-07-05 addition:** four more scorecard-only codes were fetched and
verified live before mapping. `scorecard_feed_expired` and
`scorecard_feed_expiring_soon` are the scorecard's own effective-expiry
computation (the earlier of `feed_info.feed_end_date` and the last
calendar/calendar_dates service day), which is not the same check as any single
validator notice, so neither aliases `expired_calendar` or
`feed_expiration_date7/30_days`; both map to Best Practices'
`#dataset-publishing-general-practices`, confirmed to state the "valid at least
7, ideally 30+ days out" expectation directly. `scorecard_stop_names_all_caps`
maps to Best Practices `#stopstxt`, confirmed to state the "Mixed Case, not ALL
CAPS" expectation directly (a stronger match than the Schedule reference
anchor of the same name, which only defines the field). `scorecard_station_no_pathways`
maps to the Schedule reference `#pathwaystxt`, since Best Practices has no
dedicated pathways section to point to instead.

**2026-07-05 addition (2):** `stop_too_far_from_shape` is a straight validator-
notice alias (its anchor is built the same deterministic way as every other
validator entry, so no separate live check was needed). `scorecard_flex_no_
booking_rules` was fetched and verified live: the Schedule reference page
(`gtfs.org/schedule/reference/`, the same page the Flex extension's fields
fold into) carries a `#booking_rulestxt` anchor; the Best Practices page has no
dedicated GTFS-Flex section, so `REFERENCE` rather than `BEST_PRACTICE` is the
honest kind.

**2026-07-05 addition (3):** added a fourth authority, `REALTIME_REFERENCE`
(`gtfs.org/documentation/realtime/reference/`), for the four `scorecard_rt_*`
findings (rt.py). These score GTFS-Realtime, which the canonical gtfs-validator
does not check and GTFS Best Practices does not cover, so neither existing
non-validator authority is honest for them; the message-definition anchors were
fetched and verified live: `#message-tripupdate`, `#message-vehicleposition`,
and `#message-alert` each resolve to that message's own heading.
`scorecard_rt_trip_coverage` also maps to `#message-tripupdate`: the reference
defines what a TripUpdate is but does not itself state a "100% of operating
trips" expectation (that figure is Caltrans v4.0 guidance, already cited in
rt.py's docstring and named on the fix page), so the message definition is the
closest honest spec anchor rather than a claim that the reference states the
coverage expectation directly.

## Maintenance

When a fix page is added under `docs/fixes/`, add its `RULE_LINKS` entry in the
same change; the test suite fails otherwise. The validator rule URL is built from
the code, so new validator notices need no URL edit.
