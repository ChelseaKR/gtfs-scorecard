# Support this project

The scorecard is free for every transit agency, and it stays that way. An agency never pays to be scored or to see its fixes. Sponsorship covers the cost of running the service for everyone.

The public version of this page is [gtfsscorecard.org/support](https://gtfsscorecard.org/support/). This document is the repository copy of the same commitments.

## What sponsorship pays for

The core service costs single-digit dollars a month today. A $75 to $200 monthly
operating envelope would add bounded capacity while keeping hard spending caps:

- Hosting and bandwidth for the static site, the read API, and the grade badges the project publishes.
- The scheduled daily data refresh: fetching more than 2,600 configured feed records
  in the current worldwide coverage, still mostly in the US and Canada. The public
  status page reports the exact current count and records when each run completed.
- Validator compute. Each refresh runs feeds through the canonical MobilityData gtfs-validator.
- Release monitoring and private evidence retention needed to reproduce a published check and to audit a remediation receipt if one is ever submitted.

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

- [Sponsor on GitHub](https://github.com/sponsors/ChelseaKR), or [open a sponsorship inquiry](https://github.com/ChelseaKR/gtfs-scorecard/issues/new?title=Sponsorship%20inquiry) if you would rather talk first or need an invoice. No other payment rail is advertised here until the account behind it can actually receive funds.

The GitHub tiers are sized to real cost lines, so a sponsor can see what a month
buys. The money is one pot and the spending caps hold regardless of which tier
it arrives through; nothing is earmarked.

| Tier | What it is sized to |
| --- | --- |
| $5 a month | The static core: site, daily scoring run, read API, single-digit dollars a month today. |
| $25 a month | The dynamic edges: the subscribe API, the badge and API worker, and the MCP endpoint, which run on per-request compute at about $15 a month at plausible volume. |
| $50 one time | About one month of on-demand scoring at demo-era volume ($20 to $60), the next capacity the project would add. |
| $100 a month | On-demand scoring of any GTFS URL from a web form, every month ([ADR 0029](decisions/0029-instant-score-funnel.md)). Written, not switched on; this is its running cost. |
