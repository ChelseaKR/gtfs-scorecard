# DPIA-lite

**Date:** 2026-07-10  
**Privacy risk:** Low, with opt-in alert data as the only persistent personal-data path.

## Data inventory

| Data | Purpose | Retention/access |
| --- | --- | --- |
| Public GTFS and GTFS-Realtime | Validate and score agency feeds | Public artifacts; dated history follows documented lifecycle |
| Public agency metadata | Directory, identity, corrections | Public registry and reviewed Git history |
| Subscriber email and selected alerts | Deliver requested feed-health notices | Double opt-in store; delivery process only; removable |
| Request IP counter | Abuse prevention for instant scoring | Fixed-window count with TTL; no public output |
| Page-view and bundle-checkout-click events (added 2026-09-13, [ADR 0055](../decisions/0055-cookieless-site-measurement.md)) | Learn which pages are landed on and whether the paid bundle page is reached and acted on | PostHog Cloud US, one year; page path and type, referring domain, plan id; no cookie, a tab-scoped random visit id, no person profile, client IP discarded at ingestion; off under Global Privacy Control or Do Not Track; stated at `/about/#privacy` |
| Operational logs | Diagnose scheduled jobs | Provider retention; do not log tokens, feed credentials, or private proof |

## Necessity and minimization

The public product works without an account. It does not collect rider journeys,
location histories, demographics, payment data, or agency credentials. Correction issues
request public facts only; private proof is kept out of public issues.

## Rights and controls

Subscribers confirm before delivery and can unsubscribe. Agencies and the public can
request factual correction or removal review. A data breach involving subscription or
private proof is an incident requiring credential rotation, affected-person notice review,
and deletion of unnecessary retained copies.
