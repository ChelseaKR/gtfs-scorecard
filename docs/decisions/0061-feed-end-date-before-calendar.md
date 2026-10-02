# ADR 0061: Name the date behind an expiry when feed_info ends first

**Status:** Accepted (2026-10-01)

## Context

Freshness scores the days left until the effective expiry, defined in
`docs/rubric.md` as the earlier of `feed_info.feed_end_date` and the last
service date in `calendar.txt` and `calendar_dates.txt`. The rubric chose the
earlier date on purpose, to catch "service that outlives a stale feed_info"
as well as a feed_info window that outlives service.

The rule was silent about which date it used. BART's feed, downloaded on
2026-10-01 from the registry URL (which now redirects to
`google_transit_20260810-20270108_v02.zip`), says `feed_end_date` 20260830 and
`feed_version` 72, while its weekday calendars run to 2027-01-08 and its
Sunday calendars to 2027-01-10. The scorecard published "Service data ended 32
day(s) ago. Trip planners have likely already dropped this feed" with the fix
"Re-export the feed with a calendar that reaches further out." BART's calendar
already reaches further out. The fix it needs is one field.

The question was whether to keep scoring the declared window or to score the
calendar instead.

- The GTFS Schedule
  [reference](https://gtfs.org/documentation/schedule/reference/#feed_infotxt)
  says the dataset "provides complete and reliable schedule information for
  service in the period from the beginning of the `feed_start_date` day to the
  end of the `feed_end_date` day", and that providers may give data outside
  this period "but dataset consumers should treat it mindful of its
  non-authoritative status."
- The MobilityData validator's `feed_expiration_date7_days` and
  `feed_expiration_date30_days` notices read `feed_end_date`, so a validator
  report already treats BART's feed as past its window.
- The California Transit Data Guidelines v4.0 ask for "active service for at
  least 30 days into the future at all times" (a Caltrans Check item). That
  is a statement about the calendar, which BART meets. It does not say what to
  do when feed_info contradicts the calendar.

## Decision

Keep scoring freshness from the earlier date. The reference tells consumers
that schedule data past `feed_end_date` is not authoritative, the canonical
validator agrees, and the rubric already documents the earlier-of rule as
intended. Scoring the calendar would credit a window the feed itself
disclaims.

Stop being silent about it:

- Freshness details add `expiry_limited_by`: `feed_end_date` when feed_info
  ends strictly before the last service date (or states an end with no
  calendar end), `service_calendar` when service ends first (or feed_info states
  no end), `both` when they agree, and null when neither is known.
- When `feed_end_date` is the earlier date, the calendar runs past it, and the
  feed has expired or has under 30 days left, the finding is
  `scorecard_feed_end_date_before_calendar` instead of `scorecard_feed_expired`
  or `scorecard_feed_expiring_soon`. It names both dates in plain language
  ("feed_info.txt says this feed ends on 2026-08-30. Your service calendar runs
  to 2027-01-10.") and its fix is to correct `feed_end_date`, or to end the
  calendar if service really stops.
- The new finding keeps the severity and points of the finding it replaces
  (ERROR and 100 once expired; WARNING and the expiring-soon display estimate
  inside 30 days), and it is an operational code for fix ordering, so scores,
  grades, and fix order do not move.
- A short `feed_end_date` with 30 or more days left raises nothing new. The
  reference recommends publishing service past the window as a preview, so a
  gap there is not a defect on its own.

The new code is wired everywhere the expiry codes are listed: fix ordering,
the consequence basis, the calendar-renewal campaign, the vendor regression
exclusions, the liaison outreach note, the landing freshness set, and the rule
links (pointing at the reference's `feed_info.txt` section). It has its own fix
page.

## Consequences

- BART on the 2026-10-01 download: freshness stays 0.0 and the grade stays
  F 40.8. The top fix changes from "re-export the feed" to "Correct
  feed_end_date in feed_info.txt. Set it to 2027-01-10". With that one field
  corrected and nothing else changed, the same scoring gives freshness 100 and
  about D 65.8.
- Feeds whose calendar ends first, or where the two dates agree (VTA on the
  same day: both 2026-10-25), keep the existing findings and wording.
- The intermittent and planned-service-boundary softening runs before this
  check and is unchanged.
- The resweep path rebuilds freshness from stored `feed_end_date` and
  `last_service_date`, so swept artifacts pick up the new finding without a
  re-fetch.

## Alternatives rejected

- **Score the later of the two dates.** Contradicts the reference's statement
  that data past `feed_end_date` is not authoritative, and the validator
  would still report the feed as expiring.
- **Score the calendar only for California agencies, citing Caltrans.** The
  guideline does not address the conflict, and a jurisdiction overlay needs
  its own contract (ADR 0036).
- **Add the mismatch as a second finding beside the expiry finding.** Two
  cards for one cause, and the expiry card's "re-export" fix would still be
  wrong.
