# ADR 0049: A checkout is the named user the program tier was waiting for

**Status:** Accepted (2026-09-01). Infrastructure written, not applied; the
purchase surface is built, unlinked, and closed.

## Context

The sustainability plan (`gtfs-scorecard-plans/07-monetization-sustainability.md`)
draws one line and holds it: everything an agency or a rider touches is free
and stays free, and the only things that may carry a price are tools for the
people who manage *many* agencies at once, layered over the same free data.
It names three such tools (a supporter workspace, SLA'd alerts and API, a
white-label instance) and puts one condition on all of them: **build only
when a named program or consultancy is at the table.** No paid surface on
spec.

That condition is right about spend. It has one cost the plan did not price:
getting someone to the table is outreach, and outreach is the step that has
stalled every distribution effort in this portfolio (`DEVREL-PLAN-2026-09-01`
measured four campaigns that each stopped at the publish step). A gate that
can only be opened by a conversation is, for this maintainer, a gate that
stays closed.

Meanwhile the smallest program-facing product already exists as code.
`docs/board-report.md` renders one agency's board report as a self-contained
file and lets a program put its name, logo, and accent on the cover. The
verified paying layer in this market is exactly that document (the work
product an agency hands a board or a grant reviewer; `income-plan-2026-07/09`
N1, `15-EXPANSION-STUDY4` F4), and the only missing piece between it and a
program with twenty agencies is packaging, branding, and delivery.

## Decision

**Replace the conversation with a checkout.** A real Stripe Checkout on a
truthful page *is* the named-user gate. Nothing is built for a buyer until
someone pays; the buyer identifies themselves by paying; fulfilment is
automated so the tier costs no attention after launch.

Concretely, the **program report bundle**:

- `scorecard bundle` renders one program's branded board reports for a
  cohort of up to 100 agencies as one archive with a manifest that names
  every requested id and what happened to it. The core is
  `scorecard_pipeline/bundle.py`; it computes nothing new and talks to no
  payment provider.
- `.github/workflows/report-bundle.yml` is the on-demand fulfilment, the
  same posture as `onboard.yml`: Actions is the compute, so the tier needs
  no always-on server for the work itself.
- `infra/program-bundle` is the only always-on surface: a post-checkout
  form that confirms the Checkout Session is *paid* before dispatching, a
  download route that presigns one archive per 128-bit capability link, a
  Stripe webhook for subscription state, and a weekly refresh. Written, not
  applied.
- `/bundle/` and `/bundle/setup/` read every price from
  `web/bundle/plan.json`, which says `paymentsAvailable: false`. They are
  unlinked, `noindex`, and out of the sitemap until the test-mode loop has
  been exercised end to end.

The gate that replaces the conversation is mechanical:
`infra/program-bundle`'s `payments_enabled` defaults to `"0"`, and
Terraform **preconditions** (which fail a plan, unlike `check` blocks, which
only warn) refuse `"1"` while the Stripe secret, the webhook secret, or any
price id is blank, or while a live key is paired with prices not confirmed
live. The family-greenhouse repository established this pattern; it is copied
here on purpose.

## What stays as it was

- **Agency-facing stays free.** The single report, the board one-pager on
  every agency page, the CLI, the data, the API, the badges, the alerts, and
  one-off scoring are unchanged. The bundle is additive and for someone
  else. If a proposed change to it would gate or degrade an agency's own
  experience, it is not on the table (07's load-bearing constraint).
- **Instant scoring stays free.** It is the funnel; a paywall kills the
  funnel (07). ADR 0029 is untouched.
- **No shaming surface.** A bundle is one report per agency. It has no
  league table and no ranking, and it will not gain one for a buyer.
- **Independence is the product.** Purchase buys no influence over grades,
  methodology, or listing. Every report keeps its attribution to the
  open-source scorecard and cites the public rubric. The page says so in
  the same words `/support/` uses.
- **07's base case holds.** If no one ever buys, the project continues on
  single-digit monthly spend. The bundle costs nothing while unused; the
  only new always-on cost is two pay-per-request tables and three idle
  Lambdas, which is to say nothing.

## Consequences

- A program can become a named user without a meeting. That is the whole
  point, and it is also the risk: the first buyer will be a stranger, so the
  page has to describe exactly what they get, what is not included and why
  (the manifest), when it arrives (two business days, refund if missed),
  and how long the link lives (30 days).
- A page that sells nothing until a server says it may is a page that can
  be deployed early. `/bundle/` ships with this ADR and stays honest by
  construction: no price in HTML, no capability described before the loop
  works.
- The "named user at the table" rule now has two doors, a conversation or
  a checkout. Everything else in 07 (workspace, SLA'd API, white-label)
  keeps the conversation door only until this smaller tier has a buyer;
  `docs/program-plan.md` gates the workspace on exactly that.
- The 60-day window in `gtfs-scorecard-plans/10-next-60-days-2026-08.md`
  says "no paywall". This is not a paywall, but the public surface should
  not change while the TechCA review committee is looking at it, so the
  page stays unlinked until early October regardless of when the loop is
  verified.
- Prices are hypotheses (`docs/program-plan.md` says which). The checkout
  is the experiment; the day-90 table there is the stop rule, so this ADR
  cannot become a tier that sells nothing and is never revisited.
