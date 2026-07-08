# Security policy

## Reporting a vulnerability

Please report security issues privately rather than in a public issue. Use
GitHub's [private vulnerability reporting](https://github.com/ChelseaKR/gtfs-scorecard/security/advisories/new)
on this repository.

**Response SLA:** acknowledgement within **72 hours**; a fix or a concrete
remediation plan within **14 days** for HIGH-severity-or-above reports (lower
severity reports get a plan, not necessarily a fix, on that timeline).

**If GitHub's private vulnerability reporting is unavailable** (it has
regressed before, during a 2026-07 account migration — this is not a
hypothetical): use the contact form or email on
[chelseakr.com](https://chelseakr.com) as a fallback channel. Mark the
message clearly as a security report so it isn't triaged as general
contact.

## Scope notes

- The CI action (`action.yml`) fetches and scores a GTFS feed from a URL you
  provide. It runs the MobilityData validator and the scorer over the
  downloaded data; it does not execute feed contents. Treat feed URLs in a
  workflow as you would any external input.
- The pipeline fetches agency feeds over HTTP with conservative connect/read
  timeouts and a download size cap, and guards against fetching internal or
  non-public addresses (see `pipeline/src/scorecard_pipeline/net.py`).
- The frontend reads only published JSON artifacts and escapes feed-sourced
  strings and URLs before rendering them.
