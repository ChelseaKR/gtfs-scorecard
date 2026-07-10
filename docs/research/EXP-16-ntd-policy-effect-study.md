# EXP-16: does the NTD GTFS obligation relate to feed quality?

Status: exploratory research, first pass. Drafted 2026-07-09.

## What this document is, and what it deliberately is not

`docs/ideation/03-expansions.md` pitches EXP-16 as a **longitudinal natural
experiment**: track quality before and after the RY2025/RY2026 NTD rule's
effective dates and ask whether the panel moved. `docs/ideation/04-impact-and-sequencing.md`
gates that version behind "needs history spanning the RY2026 effective dates" —
this repo's own daily artifact history currently spans about two weeks
(`2026-06-27` through `2026-07-10`), nowhere near the multi-year window a
before/after design around a 2025-2026 rule change would need. That gate is
real and this document does not pretend otherwise: there is no before/after
study here.

What *is* answerable today, with data the scorecard already has, is a
**cross-sectional** question: among the agencies this scorecard tracks right
now, do agencies with an identifiable NTD reporting relationship score
differently than agencies without one? That is a narrower question than the
original pitch, and it cannot be attributed to the policy even in principle —
a cross-section has no "before." It is still worth doing, because it is the
piece of EXP-16 this repo can do honestly today, and because getting the
non-causal framing right on the easy version is good practice for the harder
version later. Read every number below as **correlational**, not as evidence
that the obligation caused, prevented, or moved anything.

## The real policy context

Three separate FTA/NTD rulemakings matter here, and it is easy to conflate
them. Cited directly rather than assumed:

1. **The base GTFS requirement (Report Year 2023).** FTA's "National Transit
   Database Reporting Changes and Clarifications" rule
   ([Federal Register 2022-14502](https://www.federalregister.gov/documents/2022/07/07/2022-14502/national-transit-database-reporting-changes-and-clarifications))
   requires NTD reporters that operate a fixed-route mode — both **Full
   Reporters** and **Reduced Reporters** — to establish and maintain a
   web-hosted, public-domain GTFS dataset for that service, effective RY2023.
   This is the operative obligation: publish and keep current a GTFS feed, or
   FTA cannot certify the agency's D-10/P-50 submission.
2. **The RY2025/RY2026 final rule.** ([Federal Register 2025-12813](https://www.federalregister.gov/documents/2025/07/10/2025-12813/national-transit-database-reporting-changes-and-clarifications-for-report-years-2025-and-2026),
   July 2025) tightens the existing requirement rather than creating a new
   population of obligated agencies:
   - Adds a **shapes.txt** requirement inside the GTFS submission, phased in
     by reporter type: RY2025 for Full Reporters, RY2026 for Reduced, Rural,
     and Tribal reporters.
   - Considered, and **declined**, requiring `agency_id` to equal the
     five-digit NTD ID inside the feed itself, after 15 of 18 commenters
     opposed a mandated feed-side change. FTA instead links `agency_id` to
     the NTD ID internally via the P-50 form. (This repo's own
     [ADR 0016](../decisions/0016-ntd-id-alignment.md) tracks the same
     correction — an earlier draft of that ADR said FTA "requires" the
     alignment in-feed, which was the October 2024 *proposed* rule, not what
     the final rule adopted.)
   - Adds a **Reduced Reporter Exemption for Operators Predominantly Serving
     Rural Areas**, a genuine waiver from the GTFS requirement for an
     estimated 10-15 agencies meeting five specified criteria, effective
     RY2025.
3. **Who is a "reporter" at all, before any GTFS rule applies.** NTD
   reporting status itself (Full/Reduced/Rural/Tribal) is a separate,
   upstream gate driven by whether an agency receives or benefits from FTA
   Chapter 53 (Urbanized Area 5307 or Rural 5311) formula funds and how much
   service it operates — not by anything this repo measures. An agency this
   scorecard tracks that receives no federal transit funding, or that
   operates no fixed-route service (demand-response-only, for example), is
   not covered by the GTFS requirement at all, obligation or no.

So "does the obligation move quality" really asks about a population defined
one step upstream of GTFS quality itself: NTD reporting status, funding, and
service mode. This scorecard's dataset does not record any of those three
directly. What it has is a **proxy**, described next, and the proxy's gap
from the real obligation is itself the first limitation.

## The obligation proxy, and why it is imperfect

`agencies.yaml` carries an optional `ntd_id` field. Per
[ADR 0018](../decisions/0018-national-rt-and-ntd-crosswalk.md), it is
populated by an exact, unambiguous join between this registry's
`static_gtfs_url` and the Transitland Atlas's `us_ntd_id` field on US
operators — an Atlas record only carries an NTD ID if the operator is
NTD-registered, so a populated `ntd_id` is a real (if partial) signal of NTD
reporting status. A shared regional feed that the Atlas links to more than
one NTD ID is dropped rather than guessed, so ambiguous cases end up
unmatched, not falsely matched.

This proxy has three known failure modes, all of which push in the direction
of **undercounting** true NTD reporters, not overcounting them:

- **Exact-URL matching only.** An agency that is a genuine NTD reporter but
  whose feed URL does not exactly match its Atlas record (a redirect, a
  recent URL change, a host-case difference the normalizer misses) is left
  unmatched and lands in the "not obligated" bucket despite being obligated.
- **Curated pilots aside, matching depends on Atlas coverage.** The two
  hand-curated pilots (Unitrans `90142`, Yolobus `90090`) are always correct;
  everything else depends on whether Transitland's Atlas has both the
  operator and an exact feed-URL match.
- **No mode data.** Neither `agencies.yaml` nor the scored artifact records
  whether an agency's service is fixed-route, demand-response, or rail. Since
  the whole scored dataset already selects for agencies that publish a GTFS
  *schedule* at all, most tracked agencies are plausibly fixed-route-ish by
  construction, but this is inference, not a recorded fact.

So the two groups compared below are **"matched to an NTD ID via an exact
feed-URL join"** versus **"not matched"** — a proxy for "has an NTD GTFS
obligation," not the obligation itself. Every finding below should be read
with that substitution in mind. Because the failure modes undercount rather
than overcount matches, the "not matched" group almost certainly contains
some real NTD reporters, which would tend to shrink any true gap between the
groups, not manufacture one.

## Data and methodology

Source: this repo's own daily-scored artifacts in `data/artifacts/<agency>/`
(schema versions 1.4 and 1.7 present in the current panel) and the
`agencies.yaml` registry, both read as of the artifact dated **2026-07-09/10**
per agency (each agency's most recent scored date; not a fixed calendar day,
since agencies are re-scored on a rolling basis).

- **Registry:** 1,488 entries (matches the ~1,490 figure `CLAUDE.md` cites).
- **Scored:** 1,449 of those have at least one artifact on disk (39 do not —
  newly added or not yet successfully fetched; excluded here).
- **US-scoped:** 3 entries are Canadian pilots (`country: CA`); NTD is a US
  program, so they are excluded, leaving **1,446** agencies.
- **NTD-ID-matched (the obligation proxy):** **82** agencies (5.7% of the
  US-scoped set).
- **Not matched:** **1,364** agencies (94.3%).

That split is itself informative about the panel's composition: this
scorecard's cohort, drawn mostly from the Mobility Database catalog, is
overwhelmingly small and rural operators the Atlas has not (yet, or ever)
linked to an NTD ID — consistent with the tool's own stated audience.

Statistics were computed with a small, dependency-free script,
[`pipeline/scripts/ntd_obligation_analysis.py`](../../pipeline/scripts/ntd_obligation_analysis.py),
because the pipeline's runtime environment has no `numpy`/`scipy`. It
implements descriptive statistics, a Mann-Whitney U test (rank-based, robust
to the skewed, non-normal score distributions actually observed, with a
tie-corrected normal approximation for the p-value), a Welch's t-test as a
parametric cross-check, rank-biserial correlation and Cohen's *d* as effect
sizes. Run it yourself from a repo checkout with `python3
pipeline/scripts/ntd_obligation_analysis.py` (needs only PyYAML). It is a
one-off analysis script, not a maintained pipeline module, and is not wired
into CI.

## Findings

All numbers from the run recorded 2026-07-09; rerun the script against a
later artifact set and the exact figures will drift as the daily panel
updates, though the qualitative pattern should be stable over short periods.

### Overall score: no detectable difference

| | n | mean | median | IQR |
|---|---|---|---|---|
| NTD-ID-matched | 82 | 59.3 | 59.0 | [46.1, 75.5] |
| Not matched | 1,364 | 60.8 | 60.2 | [46.4, 78.0] |

Mann-Whitney: z = -0.86, p = 0.39. Welch's t: t = -0.72, p = 0.47, Cohen's
*d* = -0.08 (negligible). The two groups' overall scores are statistically
indistinguishable in this sample. Grade distributions are similarly close:
matched agencies are 51% F / 13% D / 23% C / 10% B / 2% A; not-matched are
49% F / 11% D / 19% C / 17% B / 4% A. If anything, the not-matched group has
a slightly fatter A/B tail, the opposite of what an "obligation raises
quality" story would predict, though the overall-score gap is not
statistically significant either way.

### The one category with a real gap: Correctness, and it runs the "wrong" way

| Correctness | n | mean | median | IQR |
|---|---|---|---|---|
| NTD-ID-matched | 82 | 66.1 | 69.2 | [55.6, 82.7] |
| Not matched | 1,364 | 74.6 | 79.0 | [66.7, 88.0] |

Mann-Whitney: z = -3.86, **p = 0.0001**, rank-biserial r = 0.25 (small-to-
medium effect). This is the only category-level gap in the data that clears
a conventional significance threshold, and NTD-ID-matched agencies score
*lower*, not higher.

The other three categories show no meaningful gap: Freshness (z = -0.14, p =
0.89), Rider-experience completeness (z = 1.83, p = 0.068 — a mild trend
toward matched agencies scoring higher, not conventionally significant),
Realtime (z = 0.51, p = 0.61, and only 21 matched / 83 unmatched agencies
have a measured Realtime category at all, so this comparison is
underpowered regardless).

**A plausible, code-verifiable mechanism for the Correctness gap that has
nothing to do with the NTD obligation:** `pipeline/src/scorecard_pipeline/metrics.py`'s
`correctness()` deducts per distinct validator notice *code*, but scales that
deduction up to 2x via `_count_multiplier(group.total)` when a notice code's
*instance count* is high (see `metrics.py:108-136` and the `_count_multiplier`
helper at `metrics.py:31-35`). Instance counts scale mechanically with feed
size — more stops, more trips, more stop_times rows mean more chances to
trip the same underlying defect. And NTD-ID-matched agencies in this dataset
are dramatically larger:

| Stop count (a size/resourcing proxy) | n | mean | median | IQR |
|---|---|---|---|---|
| NTD-ID-matched | 79 | 2,056 | 545 | [216, 2,678] |
| Not matched | 1,341 | 506 | 132 | [31, 401] |

Median stop count is over 4x higher for matched agencies (545 vs 132); mean
is over 4x higher (2,056 vs 506). A larger system with the exact same
underlying per-stop or per-trip defect rate as a small one will generate more
notice instances, trip the count-multiplier tiers more often, and score
*lower* on Correctness for reasons that are about scale, not about care. This
does not prove the size confound fully explains the gap — it is offered as a
concrete, verifiable mechanism, not a settled account — but it is a real
structural reason a naive reading ("obligated agencies validate worse") would
be wrong.

### Size and resourcing move together with the obligation proxy, as expected

Beyond stop count, NTD-ID-matched agencies are far more likely to publish a
measured GTFS-Realtime feed: 21/82 (26%) versus 83/1,364 (6%) of not-matched
agencies. Realtime publication requires ongoing vehicle-tracking
infrastructure that small agencies typically lack the budget or staff for, so
this tracks the same underlying size/resourcing axis as stop count. Both
findings are consistent with the obvious selection story: agencies large
enough to be NTD reporters (which itself requires meeting a funding
threshold) are also large enough to have more GTFS infrastructure and more
staff capacity, independent of anything the GTFS-specific mandate itself did.

### The one metric built directly around the actual obligation: no gap at all

The scorecard's own `ntd_readiness` block (`published`/`valid`/`current`
pillars, the same three things FTA's P-50/D-10 certification actually checks)
is the closest thing in this dataset to a direct read on "is this agency
meeting the GTFS obligation right now." On that metric:

| NTD readiness | ready | not_ready | at_risk |
|---|---|---|---|
| NTD-ID-matched (n=82) | 49% | 34% | 17% |
| Not matched (n=1,364) | 49% | 44% | 7% |

The `ready` share is **identical** to the percentage point: 49% either way.
Matched agencies show a somewhat different split of the *not-ready* 51% (more
`at_risk`, i.e. expiring soon rather than already expired, fewer flatly
`not_ready`), but the headline certifiability rate does not move at all
between the two groups in this sample.

### Data-quality caveats specific to this comparison

- **Confidence/schema coverage differs by group, mildly.** 35% of matched
  agencies' latest artifacts carry the newer `schema_version` 1.7 (with a
  `confidence` block) versus 23% of not-matched agencies; the rest are on the
  older 1.4 schema. Date ranges for the "latest artifact" are similar across
  both groups (both span 2026-06-27 to 2026-07-10, both median 2026-07-09),
  so this is a modest imbalance in re-scoring recency, not a large one, but it
  means the `confidence.level` breakdown above is only representative of the
  minority of agencies re-scored under the newer schema and is not treated as
  a primary finding here.
- **100% feed reachability in both groups** is a coincidence of this
  snapshot's `feed.reachable` flag, not a claim that every agency's own URL
  is always up; some of these are scored off the Mobility Database's mirror
  when the origin URL fails (see `fetch.source` in individual artifacts).

## What this study does not show

Stated plainly, because the roadmap explicitly names overclaiming causation
as the risk to guard against here:

- **This is not a before/after study.** It compares two groups at
  (approximately) one point in time. It cannot say whether any agency's
  quality changed after becoming NTD-obligated, before the obligation
  existed, or as a result of the RY2023, RY2025, or RY2026 rules
  specifically. The longitudinal version EXP-16 originally pitched still
  needs history this panel does not yet have.
- **"NTD-ID-matched" is not "NTD-obligated."** It is a URL-join proxy with a
  known undercounting bias (see above). Some not-matched agencies are surely
  real NTD reporters this join simply missed.
- **Size, resourcing, and urbanicity are real, uncontrolled confounders.**
  NTD reporting status is itself gated on receiving federal formula transit
  funding above a threshold, which independently correlates with agency
  size, professionalized IT/GIS capacity, and urban service area — all of
  which plausibly affect GTFS quality on their own, with no reference to the
  GTFS-specific mandate. The stop-count and realtime-publication gaps above
  are direct evidence this confound is present and large in this dataset,
  not just a theoretical worry.
- **Selection into "matched," not just selection into "obligated," is a
  second, distinct source of confounding.** An agency's feed URL being
  exact-joinable to the Transitland Atlas is not random either. An agency
  whose feed URL is stable enough to exact-match a catalog record may be
  systematically more likely to also run a well-maintained pipeline, which
  would inflate any correlation between "matched" and "higher quality" for
  reasons unrelated to NTD reporting status at all. (This may partly explain
  why the Correctness result runs the other way; it is not a clean
  confirmation of the size story either.)
- **No causal design was attempted.** There is no control group, no
  pre/post comparison, no instrument, and no adjustment for the confounders
  named above. A statistically significant gap (Correctness) and a null gap
  (overall score, Freshness, NTD readiness) are reported with equal
  prominence on purpose: a "the policy is working" narrative and a "the
  policy is not working" narrative would both be overclaims from this data.

**The honest summary:** among agencies this scorecard tracks, agencies
matched to an NTD ID look larger, more likely to publish realtime data, and
score lower on the validator-notice-based Correctness category (plausibly for
mechanical, feed-size reasons this repo's own scoring code can explain) — but
are statistically indistinguishable from unmatched agencies on overall score,
Freshness, and the specific `ready`/`not_ready` NTD-certification-readiness
read that most directly operationalizes the obligation itself. None of this
establishes that the NTD GTFS obligation raised, lowered, or left unchanged
any agency's data quality. It describes what the obligation-proxy groups look
like today, nothing more.

## Reproducing this

```
python3 pipeline/scripts/ntd_obligation_analysis.py
```

Run from a repo checkout with the daily `data/artifacts/` panel and
`agencies.yaml` present (both already tracked in this repo). The script reads
only files already on disk; it makes no network calls. Numbers will drift
day to day as the panel is re-scored; rerun it against a fresh checkout to
check today's figures rather than trusting the table above indefinitely.

## If this becomes worth deepening

The real EXP-16 (the before/after natural-experiment version) stays gated on
accumulated history spanning the RY2025/RY2026 effective dates, per
`docs/ideation/04-impact-and-sequencing.md`. When that history exists, a
worthwhile next step would pair it with a **matched comparison** (matching
NTD-ID-matched and not-matched agencies on stop count and realtime
publication before comparing quality trajectories) to at least partially
address the resourcing confound documented here, rather than the raw
cross-sectional split used in this first pass. A cleaner obligation label
(sourced from an actual NTD reporter list rather than a feed-URL join) would
also directly shrink the proxy-quality problem, independent of any causal
design question.
