# ADR 0047: An alert reads a planned service boundary from the published scorecard, never from its own inference

**Status:** Accepted (2026-08-27)

## Context

EXP-04 shipped on 2026-07-02. `gtfs.read_feed_dates` detects when a feed's own
calendars encode distinct service periods and the effective expiry lands on one
of those boundaries, and `metrics.freshness` reframes a recent lapse there as a
planned transition: the finding `scorecard_planned_service_boundary`, the
sentence "confirm your next service period is published", and a score floored
at 50 instead of a silent-expiry reading. A service the registry declares
seasonal or demand-response gets the same treatment under
`scorecard_intermittent_calendar_ended`. Its status note closed with one open
item: "RR:R3 alert-tier wiring remains open."

That gap had a cost, and it fell on the reader this project is built for. On
the morning after a university system's spring term ended, its scorecard page
said the calendar had reached a scheduled service boundary and asked the agency
to publish the next period. The alert email sent the same morning said "The
schedule stopped covering service 12 day(s) ago. Trip planners may have already
dropped this agency." Two surfaces, one feed, opposite diagnoses, and the
frightening one is the one that arrives unprompted in an inbox.

The weekly cohort digest had the same split. A liaison reading "Feed expired
this week" about a campus system in the week its term ended makes a call that
wastes the call and some goodwill.

## Decision

Every alert surface asks one module, `service_periods`, whether a closing
calendar is a transition between the feed's own service periods or a lapse. The
answer changes wording only.

**What it may change.** The headline, the detail sentence, and the fix line of
an expiry alert item; the headline and detail of a `newly_lapsed` or
`newly_expiring` cohort movement; and one explanatory line at the top of the
digest's expiry section when a planned boundary is grouped there.

**What it may never change.** Whether an item is raised, which lead-time tier
it lands in, how it sorts, its `days_until_expiry`, its kind, its scorecard
link, or whether the agency and the liaison hear about it. A softer sentence is
not a quieter alert.

**Where the answer comes from.** Only from what a published artifact already
states. Four limits keep the softer wording from becoming a hiding place:

1. **After the calendar closes, defer to the score.** "Planned" requires that
   `metrics.freshness` already published one of the two findings. The alert does
   not re-derive the conclusion from the same inputs, so there is exactly one
   place in the codebase that decides what a closed calendar means.
2. **Before the calendar closes, use the published facts.** There is no finding
   yet, so the artifact's own `service_type` and `seasonal_boundary` values
   stand in. Those are the two inputs `metrics.freshness` would use, read from
   the record rather than recomputed.
3. **A year-old lapse is never planned.** The `STALE_FEED_DAYS` floor is applied
   before anything else is read, so it holds even for a malformed or
   hand-edited artifact carrying a planned finding code it should not.
4. **No end date is never planned.** Without a date there is no boundary to have
   reached, and `scorecard_no_expiry_date` is already the worst freshness result
   the rubric has.

Anything unreadable falls through to the existing lapse wording, so the strict
sentence is the default for every feed and the softer one has to be earned.

## Consequences

A campus or seasonal system stops being told trip planners have dropped it in
the week its term ended, on the surface where that sentence did the most
damage. The email now says what the page says. A liaison's caseload names the
transition, so the call they make is the useful one: has the next period been
exported yet.

Nothing is hidden. A planned boundary is still an alert, still in the same
tier, still in the same section of the same email, and still tells the agency
riders cannot plan a trip until the next period is published. The cost of the
old wording was accuracy, not urgency, and only accuracy changed.

The asymmetry is deliberate and is what the tests assert hardest. Reading a
genuine lapse as planned would let an abandoned feed be described gently, so
every path to "planned" is tested against a hostile artifact. Reading a planned
boundary as a lapse is only the previous behaviour, so those tests assert the
softer wording is reached exactly when the published record supports it.

`portfolio_digest`'s persisted weekly snapshot gains a `planned_boundary` key.
It is read only from the current week's artifact, so a snapshot written before
the field existed diffs correctly with the key simply absent on the prior side.

This is a wording change on the private, opt-in alert channel and the cohort
digest. No score, grade, category, weight, threshold, tier boundary, or public
page moved, and no new signal was computed from any feed.
