# Support this project

The scorecard is free for every transit agency, and it stays that way. An agency never pays to be scored or to see its fixes. Sponsorship covers the cost of running the service for everyone.

The public version of this page is [gtfsscorecard.org/support](https://gtfsscorecard.org/support/). This document is the repository copy of the same commitments.

## What sponsorship pays for

The core service costs single-digit dollars a month today. A $75 to $200 monthly
operating envelope would add bounded capacity while keeping hard spending caps:

- Hosting and bandwidth for the static site, the read API, and the grade badges agencies embed.
- The scheduled daily data refresh: fetching more than 2,100 configured feed records
  in the current worldwide coverage, still mostly in the US and Canada. The public
  status page reports the exact current count and records when each run completed.
- Validator compute. Each refresh runs feeds through the canonical MobilityData gtfs-validator.
- Release monitoring and private evidence retention needed to reproduce published checks and audit participant-approved remediation receipts.

A capped hosted one-off scorer remains an option if repeated demand justifies its
abuse controls and operating cost. It is not enabled today; the site currently
offers a local pre-publish check and a GitHub-backed request path. Sponsorship
does not automatically start a cross-agency realtime archive or another
expansion without a named user and a bounded plan.

Every service runs with a hard spending cap. If a cost line grows past this range, the design changes before the bill does.

## What sponsors get

Acknowledgment, deliberately little else. Sponsors are listed on the [/support/](https://gtfsscorecard.org/support/) page and in the repository, with what their support pays for. Sponsorship buys no influence over grades, methodology, or which agencies are listed; the full rubric is public in [docs/rubric.md](rubric.md).

The real return is the tool itself: it stays free for every agency, including the small and rural systems it was built for.

## How to sponsor

- [Open a sponsorship inquiry](https://github.com/ChelseaKR/gtfs-scorecard/issues/new?title=Sponsorship%20inquiry) and we will take it from there. No payment rail is advertised until an account is actually ready to receive funds.

## For programs supporting many agencies

State DOT programs and other organizations supporting many agencies can use the public program rollups, open data, and read API to prepare for agency check-ins. These public tools use the same rubric and remain free.
