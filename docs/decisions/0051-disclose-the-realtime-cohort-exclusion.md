# ADR 0051: The corpus aggregates say they exclude the feeds that publish realtime

**Status:** Accepted (2026-08-27)

## Context

`comparisons.eligible_records` requires one homogeneous measured-category set
for any cross-feed aggregate, and picks the largest one. Most feeds have no
measured realtime, so the largest set is the three-category one, and every feed
with measured realtime is excluded. Measured on 2026-08-06 from
`/api/v1/leaderboard.json`:

```
eligible_count: 1638
measured_category_cohorts:
  correctness+freshness+completeness           1638
  correctness+freshness+completeness+realtime   145
exclusion_counts:
  measured_category_set_mismatch                145
```

`/catalog.json` had a non-null `realtime` on 157 of 2,182 rows. So 7% of the
corpus, and the only agencies doing the thing this site spends a page
encouraging, sat outside the `/pulse/` corpus average, outside
`api/v1/trend.json`, and outside the change lists. Of the 24 agencies linked
from `/pulse/` that day, **zero** had measured realtime.

The rule is right and `docs/comparison-policy.md` argues it well: a
three-category overall score and a four-category one are not the same
measurement, and averaging them would be worse than reporting one. Per-agency
alerting is unaffected, because `alerts.py` builds each feed's own
contract-suffixed history rather than reading the cohort.

The consequence was not chosen, and it points against this project's reader.
An agency that adds a realtime feed, the upgrade that costs them the most,
disappears from the headline number on the day they do it. A state program
using the corpus average to argue its cohort is improving cannot see the
improvement it most wants to show. And the page's existing disclosure, which
lists "measured categories Correctness, Freshness, Rider experience", is
accurate without telling a reader that a category is missing because the agency
does *more*, not less.

`comparison-policy.md` said "a small agency without realtime is never excluded
for that reason" and was silent on the inverse, which is the half a reader
needs.

## Decision

State it, on the surfaces that carry the number.

`/pulse/` now says, beside the corpus average, that feeds with measured
realtime are not in it, how many were scored on four categories this run, where
their realtime results are published, and that a feed leaves the average by
publishing realtime rather than by getting worse. `comparison-policy.md` states
the inverse rule in its own words.

The sentence is derived from the `comparison` block the aggregate already
publishes, never hardcoded, and it fails closed: an unreadable or absent cohort
block states no number at all, and no sentence appears when realtime is in the
selected set or when nothing was excluded for that reason. The disclosure
appears because it is true, not as boilerplate.

Nothing else moves. This is issue #248's first option.

## The two options not taken, and why they are not an agent's to take

Issue #248 records three. The other two are:

2. **Aggregate on the shared three categories.** Compute corpus averages from
   correctness, freshness and completeness for all comparable feeds,
   renormalized the way an individual score already is when realtime is absent,
   and keep the four-category overall only on the agency page.
3. **Publish both cohorts.** Show the three-category and four-category averages
   side by side, which would turn the split into a finding.

Both re-base a published methodology number. `docs/rubric.md` gates a scoring
change on the FIX-06 shadow-scoring path with an impact report and a
methodology announcement, and both would change what "the corpus average score"
has meant in every previous publication of it. That is a product decision with
a governance path attached, and it belongs to the maintainer rather than to a
change that can be justified as a disclosure.

Recording them here means the choice stays open and visible instead of being
foreclosed by the cheapest option shipping first.

## Consequences

A reader of `/pulse/` can now tell why the number covers 1,638 feeds rather
than 1,783, and an agency that publishes realtime is told, in the same
paragraph, that leaving the average is not a mark against it. That is the same
neutrality the rubric already commits to for an agency with no realtime feed,
applied to the opposite case.

No score, grade, weight, threshold, cohort rule, or artifact schema moves. The
`comparison` block in the API already carried `measured_category_cohorts` and
`exclusion_counts`, so a machine consumer could always see this; only the human
surface was silent.
