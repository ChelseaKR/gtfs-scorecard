# Product roadmap

Last updated: 2026-07-16

The multiyear arc across all of these is [`multiyear-plan.md`](multiyear-plan.md).

This document describes the user value GTFS Scorecard will test next. The
infrastructure and operating gates are in [`roadmap.md`](roadmap.md). The
immediate delivery order is in [`feature-roadmap.md`](feature-roadmap.md).

## Who it is for

The primary users remain:

- A transit manager who inherited a GTFS export and needs to know what to ask
  their vendor or staff to change.
- A program liaison preparing for an agency check-in who needs a short,
  respectful action queue and evidence that an agreed change reached the feed.

A secondary user is a GTFS consumer deciding whether enough feeds publish a
feature, such as wheelchair information or rider-facing translations, to justify
product work. That decision needs row-level evidence and an honest geographic
denominator; it does not need a new grade.

Riders and community advocates can read the same published facts through the
rider-facing summaries. Private workflow and owner information does not belong
on those surfaces.

## The job now

The scorecard already turns validator output into a grade, plain-language
findings, and prioritized fixes. The next job is narrower and more useful:

> Carry one accepted action from an alert to a comparable recheck of the
> intended published feed, then preserve a reproducible closure receipt.

This is a claim about published-data change. It is not proof of a rider outcome,
vendor causality, compliance, or certification.

## Principles that do not move

- Findings are framed as fixes. Absence of realtime is neutral, never a zero.
- No public leaderboard or individual percentile. Cross-feed evidence requires
  aligned feed identity and measurement contracts.
- MobilityData's canonical validator remains the rule engine. The scorecard
  does not become a validator, editor, or feed host.
- Accessibility data stays prominent.
- Owner and ticket details are private by default. Public evidence is limited
  to what participants may share.
- A closure fails closed when feed identity or comparability is uncertain.
- Plain language, fast pages, mobile use, and open source remain baseline.

## Where the product is today

The service tracks more than 2,200 curated feed records, with numeric latest
scores published for more than 2,100 of them. The public status page reports
the exact current configured and published counts.
It publishes per-agency grades, prioritized fixes, trends,
provenance, finding clearances, board packets, and call-prep views. Program
rollups cover most U.S. states and named cohorts. Alerts, webhooks, and liaison
digests support repeat use.

The distribution surface includes a versioned read API, Parquet data, a
read-only MCP server, badges, and a reusable GitHub Action. The site also offers
self-serve submission, local pre-publish checks, request-backed one-off scoring,
notice-to-fix guidance, detected-tool profiles, and procurement language.

These capabilities support discovery, triage, and evidence. A cleared finding
without accepted ownership still does not establish a verified remediation.

The consumer feature finder now has a primary-navigation entry, language-aware
`translations.txt` filters, CSV export, and the same row contract in
`api/v1/features.json`. The interface states that the corpus is not a census.
The finder has 45 product-need presets. The first 25 compose the existing
accessibility, translation, fare, flexible-service, pathway, payment, mode,
ferry, and generic latest-sample realtime filters. Twenty endpoint-specific
presets add TripUpdates prediction review, VehiclePositions map review,
ServiceAlerts disruption review, the complete three-endpoint stack, and
fresh-header variants. They also compose that evidence with bus, rail, ferry,
translation, fare, and accessibility requirements.

Every preset retains its individual filters and thresholds in shared links.
Generic realtime matches when at least one configured endpoint responded in
the latest scorecard sample. Endpoint-specific filters match only the named
configured endpoint kind. Freshness means the newest measured TripUpdates or
VehiclePositions header was at most 60 seconds old. None of those fields
certifies continuous uptime, service availability, prediction accuracy,
alert content, or scheduled-trip coverage. The presets also do not certify
physical accessibility, service usability, fare correctness, booking
availability, or vessel capacity. The ferry accessibility preset
requires a minimum stated share for both ferry terminals and ferry trips. It
describes published wheelchair fields, not physical accessibility or boarding
usability. The bicycle-aware preset composes the ferry service mode with a
minimum share of ferry trips that state whether bicycles are allowed or
prohibited. This is published policy evidence, not a claim about vessel space,
boarding conditions, or whether a rider can take a bicycle on every trip.
CSV exports repeat the selected geographic cohort and its reviewed-record
denominator on every row, so a shortlist remains interpretable after it leaves
the site.
The European GTFS evidence and beta gate are in
[`global-expansion.md`](global-expansion.md).

## How coverage is chosen

Adding feed records is the most validator-shaped move available. A rule engine
is defined by running against arbitrary feeds, so growth in record count reads
as the same job done at larger scale. `roadmap.md` already cuts coverage growth
as a success measure. This section says what replaces it.

**Complete a cohort; do not scatter.** A cohort is a set of feeds that share
something a claim can be made about: one detected export tool, one support
program, one state or province, one mode. Completing a cohort unlocks a
statement that was previously unavailable, such as which export defect recurs
across a tool's customers, or how a program's feeds moved after an intervention.
The same number of records spread across unrelated regions raises a count and
unlocks nothing. Curation effort should be spent where it closes a cohort.

This rule sits alongside the existing steward gate rather than replacing it. A
cohort usually arrives with a steward attached, because the person who can
verify sources and licensing regionally is generally the person who defines the
cohort.

Three coverage axes are worth work. Record breadth is not one of them.

- **Consequence.** What a finding costs: affected routes, affected boardings
  where a reporter match is unambiguous, and served-area need. Today a finding
  states what is wrong; it should also state what it costs. Ridership is a
  United States federal concept and the equity overlays are North American, so
  this layer must degrade to an honest absence elsewhere rather than a zero.
  That constraint argues for completing North American cohorts first.
- **Corpus over time.** Patterns that require the whole corpus scored daily, of
  which same-day vendor regression is the shipped example. Public reporting here
  stays gated on cohort comparability and the non-ranking rule below.
- **Outcome.** Findings that reached a verified closure, with observed time to
  close and playbooks ordered by evidence.

The public headline number should follow. Reporting record count as the
top-line figure states the validator-shaped measure while this document argues
the opposite. Outcome coverage is the honest headline once the pilot produces
enough closures to report one.

Nothing here relaxes the existing guardrails. Vendor and program evidence stays
aggregate and non-ranking, small samples do not support claims about a named
organization, and no cohort statement is published while the measurement
contract across its members is not comparable.

## Now: prove the alert-to-closure workflow

Run a 90-day concierge pilot with one support-program liaison and two feed
maintainers or vendors. Create at least six requests and test the complete
workflow:

1. Preserve exact before evidence for the intended feed and finding.
2. Confirm an accepted owner or responsible role in the participant's existing
   work channel.
3. Send a concrete request with a recheck condition.
4. Recheck newly published bytes from the same feed identity.
5. Issue a receipt only when the evidence remains comparable.

Product work during the pilot is limited to gaps a real request exposes. Likely
small additions include a private request manifest, a participant-safe receipt
view, or a better handoff template. The pilot does not justify a new ticket
system or a broad workflow dashboard.

Consumer feedback may trigger bounded maintenance on the existing finder when
the response is additive, ungraded, and uses the current artifact pipeline. It
does not waive the identity, license, localization, or regional-coverage gates.

The pilot passes with three verified closures across two participant
organizations, zero false closures, reproducible evidence, and no more than
twenty minutes of hands-on support per request by the third cycle. The complete
gate is in [`roadmap.md`](roadmap.md#5-decide-at-day-90).

## Next: turn proven practice into a product

Only after the pilot passes:

- Publish an open closure-receipt schema and deterministic verifier.
- Give agencies a portable quality passport for their verified feed identity
  and permissioned closure history.
- Rank repair guidance by observed results instead of author confidence.
- Automate one existing handoff channel selected from pilot evidence.
- Add a procurement acceptance record for contracted feed changes.
- Extend program views with aggregate remediation evidence when cohorts are
  comparable and privacy thresholds are met.

Success means a participant can repeat the workflow with less facilitation and
still produce a valid receipt. Usage of the scorecard alone is not enough.

## Later: options with named gates

- **Vendor and program learning:** after enough comparable closures exist to
  report a pattern without ranking individual organizations.
- **Verified self-management:** after manual claims and corrections create a
  measured operating burden.
- **Regional instances and guidance:** after a named program commits to local
  review and ongoing operation.
- **European GTFS beta:** after the reviewed cohort meets the source, license,
  identity, freshness, and country-spread gate in `global-expansion.md`.
- **Full interface localization:** after a named language steward owns human
  review and the pseudolocale, RTL, and locale-acceptance gates.
- **Broader curation:** after a local steward owns source and regional context.
- **Deeper realtime maturity:** after a program names the support decision the
  sampling will inform and funds a bounded collection plan.
- **Research use of the longitudinal record:** after privacy, licensing, and
  citation requirements are settled.

## Shipped, maintenance, gated, and cut

| Disposition | Product work |
| --- | --- |
| Shipped baseline | Scorecards, finding clearances, alerts, program views, knowledge base, API, data exports, MCP, badges, Marketplace Action, onboarding, and pre-publish checks. |
| Active now | Participant recruitment, six concierge requests, exact-feed rechecks, and audited closure receipts. |
| Maintenance | Alert tuning, source curation, consumer feature measurement, accessibility, security, release health, and bounded reliability work. |
| Demand-gated | Hosted one-off capacity, self-management, regional instances, European GTFS curation, full localization, deeper realtime, and research products. |
| Cut or parked | General editor or host, second validator, public rankings, public feed archive, cross-agency realtime archive, replacement ticketing, consumer-app scraping, and multimodal platform expansion. |

## What the product will not claim

- A grade is not a compliance determination or certification.
- A finding that disappeared is not a verified remediation unless it is linked
  to accepted work and a comparable recheck.
- A published-data fix does not prove a rider outcome.
- A small set of closures does not establish vendor performance.
- Corpus size does not make the registry a census of a country or region.
- A European GTFS beta would not cover NeTEx-only transport data or all European
  public transport.

The product earns its next phase by proving closure, not by adding another
surface to the existing scorecard.
