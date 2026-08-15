# NTD reporters with no discoverable GTFS feed

Published 2026-08-15. Report Year 2024 data. Reproduce with
`cd pipeline && uv run python scripts/ntd_reporter_coverage.py`.

## The question this answers, and why it could not be asked before

Since Report Year 2023, an NTD reporter operating fixed-route or deviated
fixed-route service has to publish and maintain a public, valid, current GTFS
feed and certify it on the D-10 form. The scorecard has always been able to
answer "how ready is this feed to certify" for a feed it already tracks. The
page at `/ntd/` says so plainly, and its denominator is our registry.

It could not answer the question a district liaison or an FTA reviewer asks
first: which obligated reporters have nothing to certify at all. The reason was
the direction of the only join in the codebase. `ntd_crosswalk` populates an
`ntd_id` outward from a feed we already hold, so a reporter with no feed can
never enter the crosswalk and can never be counted. The population was closed by
construction, and 83 registry records carrying an `ntd_id` was as far as it
reached.

This finding runs the join the other way, from FTA's own reporter roster
outward.

## Method

The left side is the FTA NTD Annual Database Agency Information table for RY2024
(2,914 rows, 2,867 distinct reporters). A reporter is treated as in scope when
the Service by Mode table records at least one fixed-route mode for it in
RY2024. That gives **1,253 reporters**.

The right side is three open catalogues, consulted in order: this project's
registry, the Transitland Atlas, and the Mobility Database.

Each reporter lands in exactly one match tier. The tiers are ordered by how much
the evidence is worth, so a reader who trusts less of it can read a different
number off the same table.

| Tier | Reporters | Evidence |
| --- | --- | --- |
| `registry_ntd_id` | 63 | A registry record carries this NTD ID. |
| `registry_name_exact` | 423 | Exact normalized name, same state. |
| `registry_domain` | 50 | The reporter's own website domain serves one of our feed URLs. |
| `registry_name_fuzzy` | 37 | Name overlap of 0.6 or more, same state. |
| `atlas_ntd_id` | 33 | The Transitland Atlas ties this NTD ID to an operator with a static feed. |
| `catalog_name_exact` | 173 | Exact normalized name in the Mobility Database, same state. |
| `catalog_domain` | 14 | Website domain match in the Mobility Database. |
| `catalog_name_fuzzy` | 6 | Name overlap of 0.6 or more in the Mobility Database. |
| `weak_shared_token` | 211 | One long, locally rare word in common. Needs a human. |
| `no_candidate` | 243 | Nothing found in any of the three. |

## What the numbers say

Of 1,253 RY2024 fixed-route NTD reporters:

- **573** have a feed record in the GTFS Scorecard registry on strong evidence.
- **226** have a feed in the Transitland Atlas or the Mobility Database that we
  do not track. That is our coverage gap, and it is the most immediately
  actionable number here.
- **243 to 454** have no discoverable feed in any of the three catalogues. The
  low end counts a shared rare word as a match; the high end does not. The
  distance between them is the honest width of a name-based join, and it is
  wide.

Taking the conservative end of that range, the 243 reporters with no candidate
anywhere are mostly small and mostly local: 125 are a city, county, or local
government unit, 44 an independent transit authority, 28 a tribe, and 24 a
private non-profit. By reporter type they are 103 Reduced Reporters, 103 Rural
Reporters, and 37 Full Reporters. North Carolina (20), Texas (18), Minnesota
(15), and Michigan (14) lead the state counts. 238 of the 243 publish an agency
website in their own NTD filing, so a discovery pass has somewhere to start.

## Why the weak tier is quarantined

Two real examples from this run. "Sitka Tribe of Alaska" was paired with the
registry record `ride-sitka`, which is almost certainly right. "Makah Tribal
Council" was paired with `kalispel-tribal-transit`, which is wrong: the two
share the word "tribal" and nothing else. Both matches were produced by the same
rule. A rule that cannot separate those two cases has not earned the right to
move a headline number, so its 211 rows are reported on their own line and
counted on neither side of the range.

The strong tiers have the opposite failure. They miss whenever a reporter's
legal name and its brand differ, which is common. Salem Area Mass Transit
District publishes as Cherriots. The Municipality of Anchorage publishes as
Anchorage People Mover. Each of those is a false negative that only a
name crosswalk or a human can fix.

## Limits, stated rather than implied

The in-scope population is a lower bound. NTD has no distinct mode code for
deviated fixed route, so agencies report it under Bus or under Demand Response.
Demand Response is excluded here, which means some obligated reporters are not
in the 1,253.

A reporter in `no_candidate` may well publish a feed that no open catalogue has
indexed. This measures catalogue coverage, not agency behaviour. It is not a
compliance determination, nobody is graded on it, and no score moves because of
it. Where the gap is real, the fix may belong to FTA's own crosswalk or to a
catalogue rather than to the agency.

Report Year 2024 is the most recent annual database available. A reporter that
started publishing in 2025 or 2026 still appears in the roster, and its feed, if
catalogued, still matches.

Every count above is a count of **NTD reporters**. The registry counts **feed
records**, a different unit: regional feeds, modal variants, and retired aliases
are separate records for one operator. The 1,133 US feed records in the registry
and the 1,253 obligated reporters are not two measurements of the same thing and
must never be added, differenced, or compared as a ratio.

## What this does not change yet

The `/ntd/` page and `api/v1` are untouched. The line they publish today,
"45.0% of 1125 tracked feeds look ready to certify", is a different and honest
measurement against a different denominator, and re-basing it onto the reporter
population would be the wrong fix. Publishing the reporter counts alongside it,
each with its own denominator named, is tracked in issue #278.

## Sources

Retrieval dates, exact URLs, row counts, byte hashes, and licence terms are in
`data/ntd/PROVENANCE.md`. All four sources are public and free; two are US
Government works in the public domain.
