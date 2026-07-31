# From scorecard to service

This is the plan for turning the scorecard from a thing you look at into a thing
agencies and the people who support them rely on. It builds on
[`product-roadmap.md`](product-roadmap.md) (user value over time) and
[`roadmap.md`](roadmap.md) (infrastructure), and is grounded in what the rest of
the GTFS ecosystem already does, so the scorecard fills a real gap rather than
rebuilding what exists.

## The gap this fills

California already publishes an official monthly GTFS quality report per agency
(for example, [Santa Barbara MTD, June 2025](https://reports.dds.dot.ca.gov/gtfs_schedule/2025/06/293/index.html)).
It is thorough and free. It is also technical: it lists validator notices like
`foreign_key_violation`, shows realtime-completeness percentages with no
benchmark, and runs a 24-item pass/fail checklist with no statement of which
item a rider would feel first or what to do about it. A manager at a 20-bus
agency cannot act on it.

Commercial platforms ([Optibus/Trillium](https://trilliumtransit.com/gtfs/gtfs-manager/),
[Swiftly](https://www.goswift.ly/platform)) monitor GTFS well, but as features of
paid products that small and rural agencies do not buy. The canonical
[GTFS validator](https://gtfs-validator.mobilitydata.org/rules.html) and the
[Mobility Database](https://mobilitydatabase.org/) are the right foundation to
build on, not to duplicate.

So the scorecard's job is narrow and unclaimed: **the free, plain-language
monitoring-and-prep layer on top of the canonical validator, made for the people
who support small agencies.** Not another validator. Not a creation tool.

## Who relies on it, and when

- An agency manager visits when something feels wrong, or once after a vendor
  export. They become a returning user only if the tool tells them something
  before it bites: "your feed expires in 12 days." An
  [expired feed gets the agency dropped from Google trip planning](https://support.google.com/transitpartners/answer/10761734),
  which is the concrete, feared consequence that makes monitoring worth opting
  into.
- A state liaison or customer-success role opens it before a check-in call. They
  become a returning user if the tool prepares the call: the agency's grade,
  what changed since last month, the three things to raise.

The service has to serve both as habits, not one-time visits.

## Stages

Each stage is shippable on its own and checked against the principles in
[`product-roadmap.md`](product-roadmap.md): findings framed as fixes, no
shaming, accessibility first.

### Stage 1 — Turn the scorecard into a monitor

Let an agency claim its page and opt into alerts. The expiry warning is the
anchor because the consequence is concrete; regression alerts ("your grade fell
from B to D this week") and a periodic all-clear round it out. This is what makes
an agency return.

- **Claim and verify.** An agency proves control of its email (double opt-in to
  an address at the agency domain, or a token placed in `feed_info`). Verification
  is a hard gate: nothing is emailed to an unverified address.
- **Opt-in granularity.** A subscriber chooses which alert kinds they want
  (expiry only, or expiry and regression) and which agencies they follow.
- **Built so far:** the alert digest (`alerts.py`); per-subscriber filtering, the
  verification gate, and per-kind opt-in (`notify.py`). **Live infrastructure:**
  SES sending is verified for `gtfsscorecard.org` and the digest send path works;
  the private opt-in store is a DynamoDB table the pipeline reads
  (`scorecard notify --table`). What remains is the public self-serve claim/verify
  endpoint, applied deliberately. See [ADR 0004](decisions/0004-opt-in-alerts.md).

### Stage 2 — Map the grade to the standards agencies answer to

The rubric is currently the scorecard's own. Make it a crosswalk to the two
authorities this audience is measured against, so the grade is credible rather
than invented.

- The [California Transit Data Guidelines](https://dot.ca.gov/cal-itp/california-transit-data-guidelines-faqs-v4_0)
  and [Minimum GTFS Guidelines](https://dot.ca.gov/cal-itp/california-minimum-general-transit-feed-specification-gtfs-guidelines-v2_0):
  show the grade alongside the official checklist so a manager sees "scorecard B,
  and here is where you stand on the state's checklist."
- The [MobilityData GTFS Grading Scheme](https://github.com/MobilityData/gtfs-grading-scheme),
  which covers the qualitative, rider-facing checks (signage and name accuracy,
  headsigns) that an automated validator cannot catch. The Rider-experience
  category should align with it explicitly and automate what it can.

**Built so far:** the crosswalk is written ([crosswalk.md](crosswalk.md)) and
rendered as an on-site page at `/crosswalk/`, and agency pages carry the
California Minimum GTFS Guidelines checklist.

### Stage 3 — The supporter workspace

For liaisons and customer-success roles: a cohort dashboard (the rollups exist),
plus what a call actually needs — "what changed since last month" per agency, a
one-click call-prep export, private notes per agency, and shared-fix detection
across a portfolio ("one export setting fixes these five agencies"). This is the
feature that puts the supporter audience in the tool daily, and they are the
distribution channel to agencies.

**Built so far:** the weekly portfolio digest for liaisons (scheduled in the
daily workflow, Mondays), the call-prep brief at `/agency/<id>/brief/`,
shared-fix detection on every program page, and the client-side supporter
workspace: saved cohorts and per-agency private notes, kept in the browser's
own storage so nothing personal ever reaches the pipeline. Custom
MPO-boundary cohorts remain open (RR:E10).

### Stage 4 — Close the loop on fixes

Finding to plain-language fix guide to re-check to "you fixed it, your grade went
up." Tailor the guidance to where the data is produced: detect the export tool
from the feed and point at its settings. The confirmed fix is what turns a
one-time fixer into an advocate.

### Stage 5 — Realtime depth and the compliance hook

Finish realtime scoring (scoped; gated on keyless or key-managed endpoints), and
flag the RY2026 NTD requirement to provide a stable `agency_id` for every
represented reporter and crosswalk it to the NTD ID on P-50. The feed value does
not have to equal the five-digit NTD ID.
Rural agencies are struggling with it, it is federal, and it lives in a GTFS
field — so it gives agencies a compliance reason to care, not only a quality one.

**Built so far:** the `agency_id` presence pillar and equality flag. Presence is
checked for every US feed and affects only the NTD-readiness status. When an
agency's five-digit NTD ID is on file (`ntd_id` in the registry), the scorecard
also compares it with the feed value. A difference is allowed, carries no score,
and points the reader to the required P-50 crosswalk. See
[ADR 0016](decisions/0016-ntd-id-alignment.md).

### Stage 6 — Generalize beyond California, deliberately

Per-state guideline profiles so the rubric cites the right authority for each
state, and a partnership with [National RTAP](https://www.nationalrtap.org/Resource-Center/Topic-Guides/funding),
which already hosts rural agencies' GTFS for free and runs weekly support
sessions — both a data source and a channel to exactly these users nationwide.

## Trust and governance

These are adoption blockers for public agencies, not afterthoughts.

- Claim and verify before any alert; honor delisting requests (see
  [`listing-policy.md`](listing-policy.md)).
- Keep the "data-quality lens, not a compliance determination" framing, and never
  publish a bare failing grade without the fix and the context next to it.
- Accessibility stays visibly first-class (WCAG 2.2 AAA).

## Architecture, kept cheap

The public site stays static. Stage 1, now live, adds a small verify function
and a DynamoDB subscription store the daily run reads; everything else (scoring,
rollups, static pages) stays in the daily batch. The discipline holds:
single-digit dollars a month until something is genuinely relied on. A fuller
agency datastore, beyond opt-in subscriptions, waits until claimed agencies and
notes demand it.

## How it gets adopted

Not by agencies finding it, but by the people who support them bringing it:
state data programs, regional associations, the
[MobilityData](https://mobilitydata.org/what-we-do/) community, and RTAP's weekly
sessions. Plus badge backlinks from agencies proud of a good grade, and filling
the actionability gap the official monthly report leaves.

## Sustaining it

This is public-interest infrastructure, not a venture product. The agency-facing
scorecard stays free. Realistic support: operating it under a state data program
or with National RTAP; federal technical-assistance and innovation funding
([FTA 5311(b)(3) RTAP](https://www.transit.dot.gov/funding/grants/rural-transportation-assistance-program-5311b3),
[FTA 5312](https://www.transit.dot.gov/funding/grants/public-transportation-innovation-5312));
and open-source contribution with sponsored hosting.

## What "started" looks like (next 90 days)

1. Claim, verify, and expiry-alert opt-in (Stage 1).
2. The California Guidelines crosswalk on each scorecard (Stage 2).
3. One supporter cohort workspace with "what changed" and a call-prep export
   (Stage 3).
4. A claim/delisting policy page and an accessibility audit, so it is safe to
   show real agencies their grades.

This is the smallest sequence that makes an agency come back and a supporter open
it before a call.
