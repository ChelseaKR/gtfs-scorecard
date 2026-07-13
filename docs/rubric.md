# Scoring rubric

How the scorecard turns raw feed data into category scores, an overall
grade, and the "top 3 things to fix". Code in
`pipeline/src/scorecard_pipeline/metrics.py` and `score.py` must stay in
sync with this page; every metric's docstring links back here.

## Sources the rubric maps to

This is a project-authored scoring profile, identified in artifacts as
`gtfs-scorecard-1.1`. Its weights, deductions, thresholds, grade bands, and fix
ranking are GTFS Scorecard choices. California guidance informed those choices
and is the normative quality bar for California agencies; it is not worldwide
authority. A score outside California is a feed-quality assessment under this
published profile, not a local compliance determination.

1. **California Transit Data Guidelines v4.0** (Caltrans, December 2024) —
   the normative quality bar for California agencies.
   https://dot.ca.gov/cal-itp/california-transit-data-guidelines-v4_0
   v4.0 groups expectations into compliance tiers (NTD Mandate, Caltrans
   Check, Recommended, Experimental).
2. **MobilityData gtfs-validator** (v8.0.1, the canonical validator) and its
   notice taxonomy: https://gtfs-validator.mobilitydata.org/rules.html
   Severities: ERROR (spec violations), WARNING (spec recommendations and
   GTFS Best Practices), INFO (worth attention).
3. **Cal-ITP monthly GTFS quality reports** (reports.calitp.org, mirrored at
   reports.dds.dot.ca.gov) — the existing statewide check, built on the same
   validator. Their compliance language: a feed should produce no critical
   validator errors in the previous month.
4. **MobilityData GTFS Grading Scheme** (github.com/MobilityData/gtfs-grading-scheme)
   — the canonical qualitative scheme for rider-facing accuracy. The scorecard
   automates a proxy for all seven of its fields; the field-by-field mapping is in
   [docs/crosswalk.md](crosswalk.md).

## Overall grade

Four categories with fixed weights:

| Category | Weight | Status |
|---|---|---|
| Correctness | 35% | Scored |
| Freshness | 20% | Scored |
| Rider experience completeness | 25% | Scored |
| Realtime quality | 20% | Scored where the agency publishes open RT feeds |

Categories not yet computed are excluded and the remaining weights
renormalized, so an agency is never penalized for a category the scorecard
hasn't measured. The same rule will apply per-agency when an agency has no
realtime feed: "Not yet published" is a neutral status, not a zero.

Letter grades: A ≥ 90, B ≥ 80, C ≥ 70, D ≥ 60, F below.

### Linking findings to their canonical rule

Every finding that has a fix page is linked to its authoritative rule so the
Cal-ITP / state-DOT reader lands on the same source their statewide reports cite.
The mapping lives in `pipeline/src/scorecard_pipeline/rule_links.py` (one entry
per `docs/fixes/<code>.md`, kept in sync by `tests/test_rule_links.py`) and
points each finding at one of three authorities:

- a canonical **gtfs-validator notice** on the validator rules page, for findings
  that are validator notices (the link is `rules.html#<notice>-rule`);
- a **GTFS Best Practice** (gtfs.org), for scorecard completeness checks the
  validator does not flag because the field is valid GTFS when left empty;
- a **GTFS Schedule reference** section, where only the spec field defines the
  expectation.

Scorecard-computed findings that re-detect a validator concept name the canonical
notice as an alias (`scorecard_missing_feed_info_dates` →
`missing_feed_info_date`, `scorecard_no_feed_contact` →
`missing_feed_contact_email_and_url`). The links surface on each `/fix/<code>/`
page and on the agency findings list. See ADR 0024 for the verification record.

### Top 3 fixes

All findings across categories are ranked by score impact (the points the
finding deducts), tie-broken by how many feed rows it touches. The top three
are presented in imperative plain language with an effort hint. Wording for
each validator notice code lives in `notices.py`; codes without curated
wording fall back to a generic line that links the validator's rule
documentation, and the test suite pins that every code observed in the pilot
feeds has curated wording.

## Correctness (35%)

What it measures: how cleanly the feed passes the canonical MobilityData
validator. This is the same check Caltrans applies ("regularly yields no
errors in the GTFS Schedule Validator", an NTD Mandate / Caltrans Check item
in v4.0) and the same validator behind Cal-ITP's monthly reports.

Scoring: start at 100 and deduct per distinct notice code:

| Severity | Base deduction |
|---|---|
| ERROR | 12 |
| WARNING | 4 |
| INFO | 0.5 |

The deduction scales with how widespread the notice is: x1 for up to 5
instances, x1.5 up to 50, x2 beyond. Score floors at 0.

Why per-code rather than per-instance: small-agency notices usually share one
systemic cause (an export setting, a vendor default). Five hundred instances
of one warning is one fix, and should not zero the score; ten distinct error
codes is a genuinely worse feed than one. The gentle count multiplier keeps
widespread issues ranked above isolated ones.

## Freshness (20%)

What it measures: how far into the future the feed remains usable, the
classic silent failure for small agencies. Caltrans v4.0 requires active
service at least 30 days into the future at all times (a Caltrans Check
item); the validator warns at 30 and 7 days out
(`feed_expiration_date30_days`, `feed_expiration_date7_days`).

Effective expiry = the earlier of `feed_info.feed_end_date` and the last
service date found in `calendar.txt` / `calendar_dates.txt` added service.
Using the earlier of the two catches both failure shapes: a feed_info window
that outlives actual service, and service that outlives a stale feed_info.

Scoring:
- 60 or more days of runway: 100. Sixty days is double the Caltrans
  30-day floor, enough headroom for an agency that exports quarterly.
- 0 to 60 days: linear, so the score itself becomes the early warning
  (30 days of runway scores 50).
- Expired or no determinable end date: 0.
- Recently lapsed intermittent service is softened (floored at 50 with
  planned-transition framing), not zeroed. This applies when the service is
  declared seasonal or on-demand, and also when the calendars themselves
  encode distinct service periods — two or more spans separated by 14+
  service-free days — and the expiry lands exactly on one span's end
  (an academic-term feed pausing for break). The detected case carries its
  own finding code (`scorecard_planned_service_boundary`) with a "confirm
  your next service period is published" nudge. A feed expired more than a
  year is never softened, so this cannot hide a genuinely abandoned feed.
- Missing `feed_info` validity dates: minus 15, because without stated dates
  no app (and no scorecard) can warn the agency before riders notice.

An effective end date more than ten calendar years after the check is reported
as unusually distant. Ten years is a conservative review threshold chosen to
leave ordinary multi-year planning alone while surfacing sentinel-like dates
such as 2100. GTFS does not set this maximum, so this sits outside category
findings as a display and trust advisory. It does not change the freshness
score, grade, top-three fixes, finding prevalence, finding diffs, or fix
receipts. The scorecard keeps the exact end date and raw day count in the
artifact and adds `service_horizon_status` so pages and API consumers can avoid
presenting a very large countdown as evidence that the feed is actively
maintained. Presentation and API builders derive the same status from dated
legacy records whose explicit status is absent; records without usable date
evidence remain unknown.

## Rider experience completeness (25%)

What it measures: the fields riders feel directly, anchored to v4.0
Recommended items. Six components sum to 100; the two accessibility
components carry the most weight (40 together) on purpose — they are both
a values statement and the most common real gap in small-agency feeds.

| Component | Points | How scored |
|---|---|---|
| `wheelchair_boarding` on stops | 25 | share of stops marked 1 or 2 (blank/0 = unknown earns nothing) |
| `wheelchair_accessible` on trips | 15 | share of trips marked 1 or 2 |
| Fare data present | 15 | fare_attributes.txt or Fares v2 files non-empty; an agency marked fare-free is credited here, not docked |
| Readable stop names | 15 | share of stop names not written in ALL CAPS (4+ letter words; short tokens like "4 & B" don't count) |
| Headsigns | 15 | share of trips with trip_headsign |
| Contact | 15 | half for a working agency_url, half for feed_contact_email/url in feed_info (v4.0 Recommended) |

### Reported but not graded

Seven further signals are computed and shown on the agency page, but carry no
points in this version, so they never move the grade. They surface real,
rider-facing detail and are framed as fixes. Each stays ungraded on purpose until
there are enough real feeds to calibrate a fair weight, and each has an ADR.

- **Accessibility sub-score** (ADR 0006). The two accessibility components above
  are also reported as their own 0-100 sub-score, so a reader sees accessibility
  on its own rather than blended into completeness. It reflects the same graded
  points and adds none; the chip and the sub-score key off it directly. The
  number states what the feed publishes, not whether a stop is physically usable.
- **Accessibility depth signals** (EXP-05, `pipeline/src/scorecard_pipeline/accessibility.py`).
  A second lens on the same category, modeled on the BlinkTag
  `gtfs-accessibility-validator`, that looks past whether an accessibility field
  is populated and asks whether it holds together: route-color/text-color
  contrast against the WCAG 4.5:1 bar, stop names a screen reader is likely to
  mispronounce with no `tts_stop_name` override, and whether a feed that models
  stations or entrances also carries `pathways.txt`/`levels.txt` so a wheelchair
  user's step-free route inside the station is describable. Shown as a small,
  zero-deduction "accessibility depth signals" list nested inside the
  accessibility sub-score above, framed as progress to make, never as a
  deduction or a failing grade for a small agency. Same "states it, does not
  certify usability" caveat as the sub-score above it.
- **Fare-free** (docs/add-your-agency.md). An agency that runs fare-free by policy
  is credited for the fare component and shown a neutral note in place of the
  "no fare data" finding. A deliberate policy is not a gap, the same way a missing
  realtime feed is shown neutrally.
- **Flexible service** (ADR 0007). Demand-responsive service (dial-a-ride, zones,
  on-request) is detected from the flex files, and the feed is checked for whether
  a rider can actually book a trip (a real-time rule, or a phone, link, or message
  saying how). A flex feed with no booking rules, or rules that never say how to
  book, gets a finding. Shown with a "Flexible service" chip.
- **Fares model** (ADR 0008). The fare model is classified as none, legacy (Fares
  v1), or Fares v2, and v2 feeds are checked for whether products are applied to
  trips via leg rules. A feed that publishes fare products but no leg rules shows
  riders no fare even though the validator passes it, so it gets a finding.
- **Station pathways and levels** (ADR 0009). For feeds that model stations or
  entrances, whether pathways and levels are present, including a step-free
  (elevator) route. A station feed with no pathways gets a finding; a flat
  stop-only feed, which is most small agencies, is never flagged. Shown with a
  "Station pathways" chip.
- **Shapes readiness** (US agencies, schema 1.5). Whether every trip carries a
  shape in shapes.txt, read against FTA's NTD shapes requirement (Full
  Reporters RY2025; Reduced, Rural, and Tribal Reporters RY2026). Like the
  NTD-readiness pillars, it is a data-quality heads-up, never an official
  determination.


## Realtime quality (20%)

Scored for agencies that publish openly accessible GTFS-Realtime feeds;
agencies without them keep the category out of their weighting entirely
(see Overall grade). The pipeline samples each endpoint a few times, at
least 30 seconds apart (docs/feeds.md polling etiquette), archiving the
raw protobufs.

| Component | Points | How scored |
|---|---|---|
| Reachability | 25 | each of TripUpdates / VehiclePositions / ServiceAlerts reachable and parseable on every sample |
| Freshness | 25 | worst header-timestamp lag across samples; full credit at 60s or less (v4.0 asks for a 20s publish frequency; 60s allows fetch latency), zero at 10 minutes |
| Trip coverage | 35 | share of trips scheduled during the sampling window (agency-local time, including after-midnight service) that appear in TripUpdates; v4.0 expects 100% |
| Position plausibility | 15 | share of sampled vehicle positions within 250 m of their assigned trip's published route shape |

Components a window can't measure (no trips scheduled, no vehicles seen,
no shapes in the feed) drop out and the rest renormalize to 100; the
summary says so.

Schedule-vs-RT drift is also computed from each window: every sampled
TripUpdates prediction is compared with the static schedule (direct delay
fields used as-is; absolute predicted times resolved against the sample's
service date and the previous one, with a 6 hour sanity bound). The
distribution — observation count, median, p90 of absolute drift, and the
share inside the standard on-time band of 1 minute early to 5 minutes
late — is published in the category details and summary. Drift describes
operations at least as much as data quality, so it carries no points; it
becomes a finding only when p90 exceeds 30 minutes, which usually means
predictions are keyed to the wrong trips.

Service-alert content is also observed from each window's newest alerts
snapshot: how many published alerts carry plain header text, a description,
a stated cause and effect, and route or stop scoping, and how many ended
more than 30 days before the sample and are still being served. Alerts are
the one realtime payload riders read verbatim, so these observations are
published in the category details, and an ended-weeks-ago alert or a
textless alert appears as a fix with no point deduction. The checks are
mechanical (presence and dates, never style). Content carries no points
today; if a weight is ever proposed it enters through the governed
shadow-scoring path below, announced before it takes effect, like any
other rubric change. An agency publishing no alerts feed, or an empty one
(no current disruptions), is a normal state and is never penalized.

Agencies whose realtime exists but is key-gated show a neutral note in
place of a score until access is arranged.

Note: v4.0 sets no numeric latency threshold for RT staleness; the 20-second
publish frequency is its only numeric RT requirement. Do not cite a latency
number to Caltrans.

## Equity context (overlay, not graded)

The equity overlays add context, never points: the grade is the same whether a
feed serves a high-need area or a low-need one. They answer a different question
than the rubric, namely where weak data meets high transit need.

United States: per-state (and, where built, per-tract) American Community Survey
indicators (poverty rate, zero-vehicle households, and disability), mapped to a
need tier over the areas a feed's stops fall in (ADR 0015).

Canada: the Statistics Canada Canadian Index of Multiple Deprivation (CIMD, 2021,
Open Government Licence) at the Dissemination Area level. The served-area tier is
the stop-weighted quintile of the two transit-relevant CIMD dimensions, economic
dependency and situational vulnerability; the other two (residential instability
and ethno-cultural composition) are not treated as need, to avoid conflating
demographic composition with disadvantage. It is a within-Canada measure and is
not comparable to the US ACS tier (ADR 0027). The CIMD excludes the territories,
so a feed in Yukon, the Northwest Territories, or Nunavut reads as no-coverage
rather than a low score. Source: Statistics Canada, product 45-20-0001.

## Governed upgrades (validator and rubric changes)

The measuring stick never changes blind. Every validator release adds, removes,
or reclassifies notices, which moves grades for every tracked agency at once —
so a `VALIDATOR_VERSION` bump (or a rubric-weight change) must attach a canary
impact report before it lands. Run `scorecard canary --candidate-version
<X.Y.Z>` (or dispatch the `validator-canary.yml` workflow): it dual-scores a
deterministic ~100-agency sample with the pinned and candidate validators over
identical feed bytes, and publishes the grade-shift histogram, the agencies
that changed band, and the notice-code drivers, plus a ready-to-paste
`METHODOLOGY_CHANGELOG` entry (`score.py`). Prepending that dated entry in the
same commit keeps every historical grade discontinuity attributable: a trend
reader can always tell a feed change apart from a methodology change.

The rubric itself is versioned: the current `RUBRIC_VERSION` is `1.1`
(`pipeline/src/scorecard_pipeline/__init__.py`), stamped on every artifact,
and the dated `METHODOLOGY_CHANGELOG` in `score.py` records what each version
changed, so a trend reader can tell a feed change apart from a methodology
change.

Every artifact also carries a `scoring_profile` block with the stable profile
identifier `gtfs-scorecard-1.1`, the rubric version, and this provenance boundary.
The profile metadata is additive: it does not recalculate, rename, or move the
overall score, category scores, grade, or top fixes. Jurisdiction overlays are
not implemented by this contract.

Last verified: 2026-07-06 (guidelines v4.0, validator v8.0.1, rubric v1.1) ·
Recheck cadence: before each phase and before the rubric is cited publicly.
