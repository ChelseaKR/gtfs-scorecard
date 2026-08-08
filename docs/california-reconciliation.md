---
date_published: "2026-08-07"
date_modified: "2026-08-07"
---

# Reconciling the California registry against the Caltrans report directory

Caltrans and Cal-ITP publish a
[monthly GTFS quality report](https://reports.dds.dot.ca.gov/) for each
California agency they carry, and the directory of those reports is the closest
thing the state has to a roster of who publishes transit data here. This
scorecard's registry grew from open feed catalogues instead, so the two lists
were assembled by different means and had never been lined up.

That mattered for a specific reason. The California program page counts feed
records, and a feed record is not the same thing as an agency: one operator can
publish several feeds, an old URL can sit beside its replacement, and a park
shuttle can look exactly like a city bus system. Without a stated relationship
to a list the state already keeps, a reader had no way to tell which of those
they were looking at.

This page describes how the crosswalk is built, what counts as a match, and
what is deliberately left unmatched.

## What the two sources are

The monthly reports assess the schedule side against the
[California Transit Data Guidelines](https://dot.ca.gov/cal-itp/california-transit-data-guidelines),
and their own FAQ says the site displays a subset of the Guidelines. Realtime
appears there as a twice-monthly presence check. This scorecard grades daily
across four categories and covers realtime continuously where a usable feed is
configured. The two are complementary: theirs is the state's assessment against
the state's guideline, this is a daily evidence layer alongside it. Nothing in
the crosswalk is a compliance determination, and nothing in it changes a grade.

The directory is keyed on the **organization** that publishes the data ("City of
Alhambra", "Yolo County Transportation District"). This registry is keyed on the
**feed**, and its names are usually service brands ("Alhambra Community
Transit", "Yolobus"). Most of the work below is bridging that difference.

## The snapshot

`data/caltrans-report-directory.json` holds a dated copy of their published
directory: for each agency, its report id, name, report URL, listed technology
vendors, and the feed URLs shown in that report's own "Show Source URLs" panel.
It was read once, on the date recorded in the file, and the reports themselves
remain the authority. Copying it in keeps the crosswalk reproducible offline and
keeps continuous integration free of network calls.

Re-read it when their monthly directory moves on:

```sh
uv run --project pipeline python pipeline/scripts/build_california_crosswalk.py
```

## What counts as a match

`pipeline/scripts/build_california_crosswalk.py` applies these rules in order
and stops at the first one that fires. Each recorded decision carries the rule
that produced it and the evidence in one sentence.

| Rule | What it requires |
|---|---|
| `feed_url` | The registry's feed URL is one of the URLs that agency's own report lists. No judgment involved. |
| `org_name` | The registry name equals the organization name once case, punctuation, and parentheses are removed. |
| `place_name` | A place or brand word shared by both names picks out exactly one organization in their directory. |
| `source_url_token` | A hostname label shared by the registry feed URL and a feed URL in their report picks out exactly one organization. This is what links a brand to the body that runs it. |
| `curated` | A reviewer recorded the decision by hand, with the reason stored beside it. |

Two guards keep the automatic rules from over-claiming. A shared word only
counts when it identifies a single organization in their directory, and
landscape words that recur across the state ("mountain", "airport", "sierra",
"bay") never carry a match on their own. Several registry records mapping to one
organization is allowed and recorded, because that is exactly the duplication
worth surfacing.

Where the automatic rules could not settle a case, the decision was made by
hand and stored in the script's `CURATED` table with its reason. Those are the
brand-to-operator relationships a string comparison cannot see: SolTrans is
Solano County Transit, GTrans is the City of Gardena's service, Caltrain is run
by the Peninsula Corridor Joint Powers Board.

## What is left unmatched, on purpose

A record with a plausible but unsettled candidate is recorded as **uncertain**
and is never counted as a match. The Amtrak San Joaquins feed is one: their
directory carries Amtrak with the national feed, and whether the
state-supported corridor is meant to sit under that entry is not something this
crosswalk can decide.

A record with no counterpart at all is recorded as **absent**. Most of these are
not errors on either side. Their FAQ says entirely on-demand services are out of
scope for the dashboard, and in practice park shuttles, campus shuttles, private
airport and ferry services, and small city circulators are not carried. Those
services are still worth scoring here; they simply have no row in the state's
directory to match.

One absent record turned out to be a real registry error: a Nevada operator was
sitting in the California shard. It is recorded as absent with that reason.

## Duplicate and retired feed records

The crosswalk groups registry records by the organization they matched, which
makes repeated operators visible. Four organizations were represented more than
once among the records the California page counts.

Two of those were exact repeats, the same operator under the same published
name with two feed URLs, and they were the ones that made the page read as
though an agency had expired twice. They are now retained as aliases of the
record they duplicate, using the registry's existing `alias_of` and
`feed_status` fields, and dropped from the program's member list. Three further
repeats outside the page's cohort were retired the same way. Nothing was
deleted: an alias keeps its history and its identity, it just stops being
counted as a separate agency.

The other two are legitimate. Thousand Oaks Transit and its Kanan Shuttle are
distinct services, and several operators publish a GTFS-Flex feed beside their
fixed-route feed. Those records now carry `organization_id` so they group under
one operator, and `feed_variant` so the page says which feed each one is.

That is why the page reports two figures. Feed records are what is measured;
distinct organizations is what a reader means by "how many agencies".

## What the page reports

`data/california-caltrans-crosswalk.yaml` is the generated crosswalk. It is read
at publish time by `pipeline/src/scorecard_pipeline/caltrans_crosswalk.py`, and
the resulting figures are attached to the California rollup artifact under
`reconciliation`. The program page renders them as a stated statistic rather
than leaving the reader to infer it.

A program only gets the section when every one of its members has a crosswalk
decision. A partial figure would read as though it covered the whole cohort, and
the nationwide rollup would end up carrying a California statistic.

## Where this is still incomplete

- Only the page's own cohort is grouped by `organization_id`. Another 35
  organizations are represented by more than one California registry record
  outside that cohort, and grouping them is follow-up work.
- Forty-five records the California page counts are still parked in
  `registry/intake.yaml` without a location, so the state-level machinery does
  not see them as Californian even though the page lists them. They are
  reconciled here; moving them to `registry/us/ca.yaml` is separate work.
- The crosswalk is pinned to one month of their directory. It does not yet
  re-check itself when a new month is published.
