# 0004 — Opt-in alerts: verification gate before a self-serve store

Status: accepted (Stage 1 shipped; SES verified and live 2026-06-17)

## Context

The retention mechanic for the scorecard (see
[`service-plan.md`](../service-plan.md), Stage 1) is an opt-in alert: an agency
hears from us before its feed expires and a trip planner drops it. Two
properties matter most:

1. **No unsolicited mail.** A public agency address must never receive an email
   it did not confirm. Getting this wrong is a trust-ending mistake with exactly
   the audience we need.
2. **Cheap.** The site is static and the budget is single-digit dollars a month.

A fully self-serve flow (an agency subscribes on the site without a maintainer)
needs three live pieces: a claim/verify HTTP endpoint, a dynamic subscription
store, and SES out of the sandbox. SES production access is an external approval
only an operator can request, so building all three at once is not possible in
one pass and would provision infrastructure ahead of need.

## Decision

Build the verification *semantics* first, in the pure, testable core, and defer
the live self-serve plumbing to a separate, operator-gated step.

- Subscriptions stay in the committed `subscriptions.yaml` for now (the existing
  maintainer-managed store). Each subscriber carries `verified` (default
  `false`) and an optional `kinds` list (`expiry`, `regression`).
- `notify.py` enforces the gate: an unverified subscriber is never emailed, and a
  subscriber only receives the alert kinds they opted into. This is correct and
  safe even before any live email round-trip exists, because the default is "do
  not send."
- A verification email renderer is included so the confirm flow is ready for the
  send path.

### Now live (provisioned 2026-06-17)

- **SES sending is on.** `gtfsscorecard.org` is a verified SES identity (Easy
  DKIM, custom MAIL FROM `mail.gtfsscorecard.org`, DMARC); the account already
  has production access. `SES_FROM=alerts@gtfsscorecard.org` is set as a repo
  variable, and the deploy role already carries `ses:SendEmail`. A real send was
  confirmed. The digest path (`scorecard notify --send`) is therefore live for
  verified subscribers.
- **The private store exists.** DynamoDB table `gtfs-scorecard-subscriptions`
  (on-demand, PK `email`) holds real opt-in addresses, which is why they live
  there and never in the public repo. `notify.load_subscribers_from_dynamo`
  reads it, and `scorecard notify --table <name>` (or `SUBSCRIPTIONS_TABLE`)
  uses it instead of the YAML.

### Still deferred (the public surface, applied deliberately)

- A claim/verify endpoint (mirroring `infra/submit`, which is itself written but
  not applied) that records a pending, unverified subscriber and emails a
  tokenized confirm link. It is an unauthenticated, email-triggering, public
  endpoint on a domain whose sending reputation we just established, so it is
  applied as a deliberate step with input validation, locked CORS, and a
  shared-secret, not provisioned blind.
- Granting the daily deploy role `dynamodb:Scan` on the table and passing
  `--table` in the workflow, so scheduled sends read the store. Pointless until
  the table has a verified subscriber, which the endpoint above creates.

## Consequences

- The safety-critical property ships now and is unit-tested: nothing sends to an
  unverified address, and opt-in is per-kind.
- The committed-YAML store does not scale to true self-serve; that is understood
  and is the first task of the live step, not a regression.
- The architecture stays cheap until an agency actually relies on an alert.

## Reviewed residual risk: the subscribe endpoint is public by design

A whole-repo review (2026-06) flagged that the subscribe endpoint is
unauthenticated when `SUBSCRIBE_SHARED_SECRET` is empty, leaving only the per-IP
window and the per-address cooldown between an attacker and a stream of confirm
emails (an SES reputation / email-bomb vector). This is accepted, not a defect:
the form is public and a browser form cannot hold a real secret, so double opt-in
plus rate limiting is the chosen model. The input is now hardened so a registered
address cannot smuggle URL syntax into the confirm link (tightened `EMAIL_RE`,
URL-encoded links).

The vector is also currently dormant: the daily send is gated on `SES_FROM`, so
no confirm email is sent until an operator verifies an SES sender. Before
enabling production SES send, apply at least one of these to bound it, since the
per-IP limit is evadable across addresses and IPs:

- a global per-window cap on confirm emails across all addresses, or
- a CAPTCHA / proof-of-work on the public form, or
- requiring `SUBSCRIBE_SHARED_SECRET` behind a light proxy that can hold it.

## Amendment (2026-07-02): consent now covers rollup subscriptions

The weekly portfolio digest (a cohort-level rollup summary for a program
liaison, `portfolio_digest.py`) reuses this same consent model rather than
inventing a second one. A subscriber opts into a cohort by adding a rollup id to
an optional `rollups: [...]` field on their record (in `subscriptions.yaml` or
the DynamoDB store). Two properties carry over unchanged:

- **Same verified gate.** `build_portfolio_emails` skips any unverified
  subscriber exactly as `build_emails` does, so a rollup digest never reaches an
  address that has not confirmed. Opt-in is the default-off state: no `rollups`
  field means no cohort mail.
- **Per-rollup opt-in.** A subscriber receives only the rollups they named, the
  same granularity the `kinds` field gives for alert types. Following an agency
  for expiry alerts does not enroll anyone in a cohort digest, and vice versa.

The one deliberate difference from the alert digest: a scheduled portfolio digest
is sent on its weekly cadence even when it is all-clear, because the reassurance
of a quiet week is the point of a periodic cohort summary and the volume is low
and opt-in. The alert digest keeps its "silence on all-clear" rule; only the
opted-in weekly rollup sends a steady-state note.
