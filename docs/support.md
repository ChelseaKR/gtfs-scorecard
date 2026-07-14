# Support this project

The scorecard is free for every transit agency, and it stays that way. An agency never pays to be scored or to see its fixes. Sponsorship covers the cost of running the service for everyone.

The public version of this page is [gtfsscorecard.org/support](https://gtfsscorecard.org/support/). This document is the repository copy of the same commitments.

## What sponsorship pays for

Running the service costs roughly $75 to $200 a month, all of it infrastructure:

- Hosting and bandwidth for the static site, the read API, and the grade badges agencies embed.
- The scheduled daily data refresh: fetching about 1,140 configured feeds in the current worldwide coverage, still mostly in the US and Canada. The public status page records when each run actually completed.
- Validator compute. Each refresh runs feeds through the canonical MobilityData gtfs-validator. A capped hosted one-off scorer is planned but is not enabled today; the site currently offers a local pre-publish check and a GitHub-backed request path.
- Realtime sampling around the clock, the largest planned line item and the first thing new sponsorship unlocks.

Every service runs with a hard spending cap. If a cost line grows past this range, the design changes before the bill does.

## What sponsors get

Acknowledgment, deliberately little else. Sponsors are listed on the [/support/](https://gtfsscorecard.org/support/) page and in the repository, with what their support pays for. Sponsorship buys no influence over grades, methodology, or which agencies are listed; the full rubric is public in [docs/rubric.md](rubric.md).

The real return is the tool itself: it stays free for every agency, including the small and rural systems it was built for.

## How to sponsor

- [Open a sponsorship inquiry](https://github.com/ChelseaKR/gtfs-scorecard/issues/new?title=Sponsorship%20inquiry) and we will take it from there. No payment rail is advertised until an account is actually ready to receive funds.

## For programs and consultancies

Organizations that support many agencies at once, such as state DOT programs and consultancies, sometimes need more than the public site: portfolio views across a region, or help reading results during agency check-ins. Paid services like that exist alongside the free tool and never replace it. Nothing is subtracted from the free tier to create them.

See the current [consulting services and pricing](https://chelseakr.com/consulting/), or write to [Chelsea Kelly-Reif](mailto:ckellyreif@gmail.com) to start that conversation.
