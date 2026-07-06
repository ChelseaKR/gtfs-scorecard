# 0031 — Declare the Observability tier: B (frontend) + C (batch), not A

Status: accepted
Date: 2026-07-05

## Context

`OBSERVABILITY-STANDARD.md` (`docs/standards/`, line 17) maps "gtfs-scorecard
(pipeline service)" to **Tier A — Hosted service / Lambda**: full OTel
traces+metrics, structured JSON logs with trace correlation, RED/USE metrics,
`/livez`+`/readyz`, SLOs, burn-rate alerting, dashboards-as-code.

That mapping describes a *possible future* shape of this repo, not its
current one. What is actually deployed today is:

- a scheduled GitHub Actions batch job (`refresh.yml`, `scorecard.yml`) that
  fetches feeds, runs the validator, scores, and publishes JSON artifacts to
  `main` — no long-lived process, no HTTP server, nothing to health-check;
- a static site on GitHub Pages that reads those artifacts client-side;
- `infra/compute` (an SQS + Lambda worker, the thing that *would* make this a
  Tier-A hosted service) is written and reviewable but **not applied** — see
  the roadmap's "built vs deployed" table in `README.md`.

A 2026-07-05 conformance audit named this exact gap (OBS-21): the repo had
never declared a tier, so the standard's Tier-A mapping governed by default,
and every Tier-A control (OTel spans, RED/USE, SLOs, burn-rate alerts,
`/livez`/`/readyz`) scored FAIL — not because the work is bad, but because it
is the wrong bar for what is actually running. `CODE-QUALITY-STANDARD` CQ-45
requires this kind of standard-scope decision to be recorded in an ADR, not
left implicit.

## Decision

Declare, for the deployed system as it exists today:

- **Tier B (frontend)** for `web/`: the Core Web Vitals lab-gate half of
  `OBSERVABILITY-STANDARD.md` §8 applies. `lighthouserc.json` currently
  asserts only `categories:accessibility`; extending it to LCP/INP-proxy
  (TBT)/CLS assertions is tracked as a follow-up (remediation P1-9) and is
  **not yet met** — this ADR declares the tier, it does not claim the gate is
  green.
  - RUM (field p75 Core Web Vitals) is **declined, N/A-with-reason**: this
    site has no analytics/beacon pipeline by design (`web/analytics.js` is a
    static-asset name, not a telemetry client — see `docs/listing-policy.md`
    for the no-tracking posture), and adding one solely to satisfy a field-SLI
    review-gate would be adding surveillance surface to a civic tool for a
    metric the Lighthouse lab gate already regression-tripwires. Revisit if a
    hosted RUM approach ever becomes privacy-compatible (aggregate-only,
    no per-visitor identifiers).
- **Tier C (batch pipeline)** for `pipeline/`: OTel tracing/metrics/SLOs/
  `/livez`+`/readyz` are **N/A — no network surface to health-check, no
  request path to trace**. The opt-in `--log-format json` structlog pattern
  (§3) is the only Tier-C control that applies; `cli.py` currently uses
  `logging.basicConfig` plain-text output (remediation P3, OBS-09/10 —
  cheap, not urgent at this tier, tracked as polish).
- **Tier A is deferred, not rejected.** If `infra/compute` is ever applied
  (making the pipeline a long-lived service rather than a scheduled batch
  job), this ADR is superseded and the repo re-enters Tier A in full: OTel
  spans/metrics, `/livez`/`/readyz` on the new service, SLOs, burn-rate
  alerts. Until then, holding this repo to Tier A punishes the deployment
  choice (boring, cheap, Actions-cron) that `CLAUDE.md`'s cost guardrail and
  ADR 0001 (validator runtime) both deliberately made.
- The declaration lives in `README.md`'s `## Observability` section rather
  than a `docs/ROADMAP.md` file (the standard's literal instruction): this
  repo's existing `docs/roadmap.md` (lowercase) is an infra/scaling plan, not
  a standards Metrics ledger, and duplicating a second differently-named
  roadmap file today would confuse more than it clarifies. A proper Metrics
  ledger (per-control values, stage 6-8 declarations) is tracked as a
  follow-up (remediation P2-6); this ADR and the README section are the
  honest interim declaration the standard's gate (OBS-21) checks for.

## Consequences

- 17 previously-FAIL Tier-A controls (OBS-01…08, 12…20) become declared
  N/A-for-this-deployment-shape rather than silent failures against the
  wrong bar. This is a scoring correction, not new engineering — the audit
  itself notes this single declaration moves overall conformance from ~35%
  to ~39%.
- The two controls that genuinely still apply (Tier B CWV gate, Tier C
  structured logging) remain open work, tracked in the remediation plan
  (P1-9, P3) rather than closed by this ADR.
- If a future contributor stands up `infra/compute`, they must revisit this
  ADR (mark it superseded) before claiming Tier A conformance — applying the
  Terraform without also wiring OTel/SLOs/health probes would recreate
  exactly the "looks more conformant than it is enforced to be" gap this
  audit found elsewhere in the repo.
