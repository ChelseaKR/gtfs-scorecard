---
date_published: "2026-10-22"
date_modified: "2026-10-22"
---

# GTFS validator and the scorecard grade

If you look after a transit agency's GTFS feed, you may be searching for a GTFS feed validator. The canonical one is the [MobilityData GTFS validator](https://gtfs-validator.mobilitydata.org/). The scorecard does not replace it. It scores on top of that validator rather than re-validating feeds.

The scorecard is a data-quality lens, not an official compliance determination. This page explains where it fits next to the validator, how to check a feed, and what it can and cannot tell you.

## What the validator does and what the scorecard does

The validator owns the specification and best-practice notices as GTFS changes. Its notices come in three severities: error (a specification violation), warning (a specification recommendation or a GTFS Best Practice), and info (worth attention). The full list is on the validator's [rules page](https://gtfs-validator.mobilitydata.org/rules.html).

The scorecard reads those notice codes and links users back to the validator's own rule documentation. When a scorecard check overlaps a validator concept, the validator's notice and rule stay authoritative.

On top of that, the scorecard adds a score, a letter grade, the three fixes that matter most, and the trend for a published feed.

## How to check a feed

- **Before you publish a ZIP:** [check a feed before you publish](/check/). Drop the GTFS zip into the page and it answers five questions: required files, expiry, wheelchair fields, fares, and stop names. The file is read in your browser and nothing is uploaded. This is a preview, not the full validation, and the MobilityData validator stays the authority.
- **If your feed is already published:** find your agency in the [directory of published scorecards](/agencies/). Published feeds are checked daily.
- **To score a feed that is not listed:** [request a full score](/try.html). A scorer fetches the public feed, runs the MobilityData validator, and returns the grade and top fixes as a comment on a GitHub issue. This needs a GitHub account, and the feed URL and the result are public on that issue. Hosted instant scoring is not enabled. You can also run the open-source scorer locally with one command; it needs Java 17 and uv.
- **To gate a CI build:** the [GitHub Action](https://github.com/marketplace/actions/gtfs-scorecard-gate) can fail a build when a feed drops below a grade.

## What the grade adds beyond validator notices

The grade has four categories with fixed weights. Letter grades are A at 90 and above, B at 80, C at 70, D at 60, and F below 60.

- **Correctness (35%)** is how cleanly the feed passes the validator. Each distinct notice code costs points by severity: 12 for an error, 4 for a warning, and 0.5 for an info notice, with a small multiplier when a notice is widespread. Five hundred instances of one warning is one fix, so it does not zero the score.
- **Freshness (20%)** is how far into the future the feed stays usable. A feed that quietly expires is the most common failure, and trip planners then drop the agency.
- **Rider experience completeness (25%)** covers fields riders feel directly: wheelchair boarding on stops, wheelchair access on trips, fare data, readable stop names, trip headsigns, and contact details. Some of these are valid GTFS when left empty, so the validator does not flag them.
- **Realtime quality (20%)** is scored only where the agency publishes open realtime feeds. A missing realtime feed does not lower the grade.

Findings are ranked by how many points they cost, and the top three are written in plain language with an effort hint. A finding that has a [fix guide](/fix/) links to that guide and to its canonical rule. You can also [subscribe to feed alerts](/subscribe.html) to hear before a published feed expires.

## What this page does not claim

- The grade is a data-quality lens, not an official compliance determination. A strong category score does not certify a feed against any guideline, and a weak one does not fail it.
- The weights, deductions, thresholds, grade bands, and fix order are choices made by this project. They are published and inspectable, but they are not an official MobilityData grade.
- California guidance informed those choices. Outside California, a score is a feed-quality assessment under this published profile, not a local compliance determination.
- The pre-publish check is a preview. Request a full score to run the validator over the whole feed.
- For an official assessment, use the sources on the [standards crosswalk](/crosswalk/).

## Read the method

The full methodology, with citations, is in the [scoring rubric](https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/rubric.md). To learn to read a scorecard, see [how to read your scorecard](/how-to-read/). For who maintains the project, see [about](/about/).
