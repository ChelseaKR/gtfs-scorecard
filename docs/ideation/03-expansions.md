# Expansions

Drafted 2026-07-01. Seventeen expansions in three horizons: **H1 — deepen the
core** (make the scorecard itself measure and explain more honestly), **H2 —
adjacent capabilities** (new surfaces over data that already exists), and **H3 —
transformative bets** (change what the product is). Everything here is net-new
relative to the existing planning set (`roadmap.md`, `feature-roadmap.md`,
`product-roadmap.md`, `RESEARCH-ROADMAP.md`, and the July expansion docs); where
an idea builds on an existing item, that item's ID is named and the delta is
stated. `RR:R#`/`RR:E#` refer to `RESEARCH-ROADMAP.md`. Effort tiers match
`02-large-scale-fixes.md`: S ≈ days, M ≈ 1–2 weeks, L ≈ a month, XL ≈ a quarter.

Each item chosen to preserve the two guardrails that define the tool: findings
are fixes not failures, and nothing always-on ships ahead of a named user and
the single-digit-dollars-a-month budget.

---

## H1 — Deepen the core

The grade is the product. This horizon makes the grade measure more, explain
more, and admit more about its own limits, without leaving the static-first
architecture or the existing rubric's spirit.

### EXP-01 — A measurement-confidence read on every scorecard

**Pitch.** Show, on each card, how much of the grade the pipeline could actually
measure and from what source, as one legible confidence signal.

**Impact.** A grade presents with uniform authority today whether four categories
were measured or two, whether realtime was sampled across three windows or one,
and whether the agency's own endpoint or the MobilityData mirror was scored. A
confidence read tells a manager and a journalist when a number is provisional —
the honest complement to the letter. It is the rider-facing synthesis of the
plumbing that FIX-01 (fetch source) and FIX-11 (run health) produce.

**Shape.** Derive a per-scorecard `confidence` object in `publish.py` from signals
already computed: which of the four categories are `measured` vs
`not_yet_measured` (`score.py` already tracks this), how many RT windows were
sampled (`rt.py`), fetch source `origin|mirror` (FIX-01), and feed age at
scoring. Render one quiet line plus an expandable "how we measured this" on the
agency page (`render_site.py`), and add the field to the artifact (additive,
schema bump). Never a second grade — a legibility layer on the one grade.

**Effort:** S–M. **Risks/deps:** consumes FIX-01 and FIX-11; copy must not read as
"we distrust this feed" when low confidence is really about our own coverage.
**Excellence bar:** every card states what was and was not measured; a reader can
tell a fully-measured A from a two-category A without opening the docs.

### EXP-02 — The grade story: an agency's history in plain language

**Pitch.** Auto-write a short, honest narrative of how a feed's grade moved and
why, from the dated artifacts.

**Impact.** The trend chart draws the line; nobody reads a line as a story. RR:R4
shipped a cleared-findings diff for a single run; the net-new step is the
longitudinal narrative across many runs — "a C in April; a B when wheelchair
fields appeared on 200 stops in May; a June dip when the feed came within 12 days
of expiring." This is the retention artifact a liaison forwards and a board
packet quotes.

**Shape.** A render over the per-agency artifact history
(`data/artifacts/<agency>/*.json`) that detects grade-band transitions, category
jumps, and cleared/introduced findings between consecutive runs, then composes
3–5 dated plain sentences. Deterministic templating, not free-text generation, so
it is reproducible and cannot invent a cause; each sentence links to the run that
supports it. Any LLM pass is phrasing-only and human-reviewed, never used to
assert causation. Surfaces on the agency page and feeds the board one-pager
(RR:E6).

**Effort:** M. **Risks/deps:** causal language must stay correlational ("improved
after," not "improved because"); wants retained history (fine today, firmer after
FIX-02/EXP-13). **Excellence bar:** a first-time reader understands a year of a
feed's history in four sentences, each traceable to a dated artifact.

### EXP-03 — Fix-effort estimates calibrated from real outcomes

**Status: Done (2026-07-04).** `effort_calibration.py` derives per-notice-code
runs-to-clear episodes from the same dated-artifact walk the fix log runs
(`publish.rebuild_index`), pooling them corpus-wide into
`data/effort-calibration.json`. An episode opens the run a code first appears
and closes the run it is verified gone (its category measured), mirroring the
fix log's rule (`fixlog.diff_receipts`); recurrences are separate episodes and
never-cleared episodes are counted as "still open" but excluded from the
median. Codes with at least `MIN_SAMPLES` (5) closed episodes earn a week-
rounded empirical band shown beneath the hand-authored effort hint on the
findings list, the agency top-fixes, and the brief/board "effort" lines. The
band is additive and gated on the calibration file existing, so renders
without it are unchanged.

**Pitch.** Replace hand-authored effort hints with empirical ones: how long
agencies actually take to clear each finding, measured across the corpus.

**Impact.** Every fix carries an effort hint today ("likely a one-line export
setting"), authored by judgment. With history retained, the corpus can state the
truth — the median feed clears `missing_feed_contact` in about two weeks;
`route_color_contrast` lingers for months. Data-grounded effort estimates make
the top-three list credible and help a liaison triage. Distinct from RR:R5, which
names the export setting, not the duration.

**Shape.** A batch over the artifact history (needs FIX-02's archive or at least
retained artifacts) measuring, per notice code, the distribution of runs-to-clear
after a code first appears; surface an empirical effort band on each finding
beside the hand-authored hint ("agencies usually clear this within N weeks").
Recompute monthly with the dataset release (`dataset.py`).

**Effort:** M. **Risks/deps:** hard-depends on retained history (FIX-02, EXP-13);
low-sample codes need a confidence floor before display. **Excellence bar:** the
effort hint on any common finding is backed by a measured clear-time distribution,
not a guess, and refreshes monthly.

### EXP-04 — Freshness that understands service calendars, not just expiry dates

**Status: Done (2026-07-02).** `gtfs.read_feed_dates` now merges
`calendar.txt`/`calendar_dates.txt` service spans and sets
`FeedDates.seasonal_boundary` when the feed encodes distinct service periods
(two-plus spans, 14+ service-free days between them) and the effective expiry
lands on a span end. `metrics.freshness` reframes a recent lapse at such a
boundary as a planned transition (`scorecard_planned_service_boundary`,
"confirm your next service period is published", score floored at 50); the
`STALE_FEED_DAYS` hard floor still applies so a feed dead over a year is never
softened, and the flag round-trips through the freshness sweep. Continuous
calendars are unchanged. RR:R3 alert-tier wiring remains open.

**Pitch.** Distinguish a feed that legitimately changes for a school break or
summer service from one silently drifting toward expiry.

**Impact.** Freshness buckets on days-to-expiry today (`metrics.py`,
`STALE_FEED_DAYS`). A campus or rural agency — Unitrans is literally a university
system with academic-term service — making a real seasonal change can read as
"expiring soon" while doing exactly the right thing. A calendar-aware model
reduces false alarms for the agencies least able to absorb a frightening email,
and it is the honest reading of what the calendar actually encodes.

**Shape.** Parse `calendar.txt`/`calendar_dates.txt` service spans and detect
scheduled service boundaries; when a feed's end date coincides with a known
service-pattern change, frame it as a planned transition with a "confirm your next
service period is published" nudge instead of a lapse warning. Wire into the
freshness copy and the tiered expiry alerts (RR:R3) so the alert tone matches
reality. Conservative default: unknown pattern → treat as expiry.

**Effort:** M. **Risks/deps:** must not become a loophole that hides a genuinely
lapsing feed. **Excellence bar:** a legitimately seasonal feed no longer receives
cliff-edge expiry language; a truly lapsing feed is unaffected.

### EXP-05 — Accessibility completeness with depth, as a celebrated sub-score

**Pitch.** Move accessibility scoring past field-presence to field-plausibility
and pathway connectivity, using a second dedicated validator lens.

**Impact.** Completeness checks that `wheelchair_boarding` is populated
(`completeness.py`, `accessibility.py`); it cannot distinguish "every stop marked
unknown" from a real accessibility picture, or tell whether a station's
pathways/levels graph actually connects. Accessibility is the project's stated
values gap and prominent by design (ADR 0006, ADR 0009). The BlinkTag
`gtfs-accessibility-validator` cited in `RESEARCH-ROADMAP.md`'s research basis
checks exactly these fields; adopting it as a second lens deepens the one category
the project most wants to lead on.

**Shape.** Integrate the accessibility validator as an additional subprocess lens
(same pattern as `validate.py` wrapping gtfs-validator); surface pathway-graph
connectivity and wheelchair-field plausibility as adoption-framed signals; keep it
a celebrated sub-score, never a failing grade for a small agency; keep the "states
it, does not certify usability" caveat loud (RR:R8). Cross-link
OpenSidewalks/OpenThePaths in the access methodology as the sidewalk-to-stop
frontier the feed itself cannot see (named in `expansion-research-2026-07.md`).

**Effort:** M. **Risks/deps:** a second validator toolchain in the pipeline
(packaging, runtime budget); must not shame. **Excellence bar:** an agency can see
not just whether it filled accessibility fields but whether they hold together,
framed as progress.

### EXP-06 — An interactive methodology sandbox

**Pitch.** Let a skeptic re-weight the rubric in the browser and watch the
leaderboard reorder, live.

**Impact.** The weights (35/20/25/20) are judgment calls, honestly documented.
FIX-07 quantifies robustness in a static study; the interactive version hands the
argument to the reader. It is the strongest possible expression of "reproduce or
contest the grade" (`score.py:methodology` docstring) and it disarms the "the
weights are arbitrary" critique by making the arbitrariness explorable.
Pre-arms the press explainer (RR:E3).

**Shape.** A `/how-to-read/` (or `/methodology/`) widget in the static SPA that
loads the published `scoring.json` methodology contract and a national snapshot,
recomputes overall scores client-side under user-set weights, and shows how many
agencies change band. No backend — the recompute is trivial arithmetic over the
already-published category scores, the same client-side-compute pattern the
shipped `/query/` DuckDB-WASM page established. Depends on the single-source
constants of FIX-03 so the widget and the pipeline agree by construction.

**Effort:** M. **Risks/deps:** FIX-03 prevents drift between the sandbox and the
pipeline. **Excellence bar:** a reader can answer "would my agency's rank survive
different weights?" in the browser, without trusting the maintainer.

---

## H2 — Adjacent capabilities

New surfaces and audiences built over data the pipeline already produces. None
requires new always-on infrastructure; each opens a role the tool underserves.

### EXP-07 — A national vendor-regression radar, public and constructive

**Pitch.** Detect the day a scheduling-vendor export change quietly breaks the
same finding across many of its feeds, and surface it constructively rather than
as a public shaming.

**Impact.** `roadmap.md` Year 2 names "catch the day a vendor software update
quietly breaks fare data for forty customers at once" as private vendor signal,
and `anomaly.py` exists. The net-new step is a standing radar: a cross-corpus
daily scan keyed on the detected producing tool (`tool_profiles.py`, shipped for
RR:R5) that flags correlated regressions, routes them as vendor-constructive
worklists (RR:E4), and publishes a de-identified aggregate "national anomaly
digest" that never names an agency as failing.

**Shape.** A daily job over the run's findings, grouped by producing tool and
notice code, testing for a same-day spike in a code's incidence within a vendor
cohort; emit a private per-vendor worklist (feeds RR:E4) and a public aggregate
digest ("a fares regression appeared in ~30 feeds from one export tool on
<date>"). Reuse `anomaly.py` and `findings_national.py`.

**Effort:** M–L. **Risks/deps:** statistical care against false alarms; public
copy stays aggregate and no-shaming; the outward vendor framing is gated on the
RR:E4 vendor interview. **Excellence bar:** a correlated multi-feed regression is
detected within a day and reaches the vendor as a fix list before it reaches a
journalist as a story.

### EXP-08 — A community-contributable notice-to-fix knowledge base

**Pitch.** Turn `docs/fixes/` from a maintainer-authored set into a moderated,
vendor-keyed, community-contributable base of "here is exactly how I fixed this in
tool X."

**Impact.** `roadmap.md` calls the notice-to-fix KB "the most durable value-add …
worth starting in Year 1 and never finishing"; 28 entries exist in `docs/fixes/`.
FIX-08 governs coverage as a metric. The net-new step is the contribution
mechanism: the fastest route to full, vendor-specific coverage is to let the
liaisons and managers who actually cleared a finding contribute the recipe,
moderated. It compounds with RR:R5 — a recipe keyed to the detected vendor is
shown to exactly the agencies on that vendor.

**Shape.** A structured contribution flow (issue template → moderated PR) for a
`docs/fixes/<code>.md` recipe tagged by vendor/tool; render vendor-matched recipes
on the agency fix surface via `tool_profiles.py`; a lightweight review rubric
(plain-language, no-shaming, correct). Every entry human-reviewed; contributor
credited.

**Effort:** M. **Risks/deps:** sustained moderation load; recipe-correctness
liability (each recipe states "verify against the canonical validator").
**Excellence bar:** the top uncurated codes from FIX-08's queue get
practitioner-written, vendor-specific recipes, and an agency sees the recipe for
its detected tool.

### EXP-09 — A citable, per-agency feed-quality record

**Pitch.** Give every agency a stable, permanent, referenceable record of its
feed quality over time, not just a live page.

**Impact.** RR:E7 makes the whole dataset citable; the net-new granularity is the
per-agency permalink a manager, board, or NTD narrative can cite ("…/agency/<id>/
record, as of <date>, rubric 1.1, validator 8.0.1"). It is the honesty ethos
applied to citation: a claim about a feed's quality resolves to a fixed,
versioned, reproducible record, not a URL whose content silently changed.

**Shape.** A per-agency record artifact and page pinning grade, category scores,
methodology version, validator version, and the provenance block (FIX-01),
addressable by date; a "cite this" affordance emitting a formatted reference (the
repo already ships `CITATION.cff`). Backed by the archive (FIX-02) so the cited
state is byte-reproducible.

**Effort:** S–M. **Risks/deps:** leans on FIX-02 for reproducibility and FIX-10
for a schema-stable shape. **Excellence bar:** any quality claim about an agency
resolves to a fixed, dated, reproducible record with its methodology stamped.

### EXP-10 — A consumer-facing data freshness and uptime commitment

**Pitch.** Publish a plain, machine-readable statement of how fresh the data is
meant to be and how it has actually performed, so a downstream consumer can depend
on it.

**Impact.** FIX-11 builds the internal status surface; the net-new step is the
outward commitment the app developer (RR:D1) and researcher (RR:D3) need before
they build on the feed. "Refreshed daily" is a README claim; a published,
historical refresh record makes it a dependable one, in keeping with the
`OBSERVABILITY-STANDARD` in `docs/standards/`.

**Shape.** A `/status/` section (extends FIX-11) plus a machine-readable
`status.json` publishing the intended cadence per tier (ADR 0010, `cadence.py`),
the historical refresh-success record, and a stated degradation policy. No promise
the static architecture cannot keep; the point is to state the real commitment
honestly.

**Effort:** S. **Risks/deps:** depends on FIX-11's run-summary data. **Excellence
bar:** a consumer can read the actual freshness track record before depending on
the data, and the stated commitment matches measured reality.

### EXP-11 — A closed-loop guided fix with a verification receipt

**Pitch.** Walk a manager from a named finding, through the exact export setting
and a safe auto-patch, to a dated receipt proving it cleared — one continuous
loop.

**Impact.** The pieces exist separately: `autofix.py` produces conservative
patches for mechanically-certain cases; RR:R5/`tool_profiles.py` names the vendor
export setting; RR:R4 shows cleared findings. The net-new value is stitching them
into one guided session that ends in a linkable "fix receipt" (the
`expansion-ideation-2026-07.md` "fix verification as a product" note). This is the
retention moment the whole product is built around, made whole, while staying
firmly on the safe side of the no-editor red line: the tool never publishes for
the agency.

**Shape.** A guided flow on the agency page: (1) the finding in plain language,
(2) the tool-specific setting (`tool_profiles.py`) or a downloadable `autofix.py`
patch for the mechanically-safe cases only, (3) after the agency republishes, an
auto-detected cleared-finding receipt (RR:R4) with a permalink for a board packet
or NTD narrative (pairs with RR:E6 and EXP-09). Explicit boundary copy: the
scorecard shows the fix; the agency owns the publish. The shipped `/check/`
client-side page is the safe upload surface.

**Effort:** M. **Risks/deps:** brushes the "no feed editor" red line — the
guardrail is that `autofix.py` stays conservative and the agency always publishes.
**Excellence bar:** a manager goes from "what is wrong" to "proof it is fixed"
without leaving the tool and without the tool ever touching their published feed.

### EXP-12 — A scheduled portfolio digest for liaisons and state programs

**Pitch.** Email a liaison a weekly "what moved in your cohort" digest, the way
the agency alert loop already emails managers.

**Impact.** The alert stack (`alerts.py`, `notify.py`, SES) serves the agency
(RR:R2/R3); the supporter (RR:F1) and state-program (RR:C2) personas have a rollup
page but no push. RR:E1 (supporter workspace) is the L-sized destination; this is
the S/M push primitive that makes the workspace worth returning to — month-over-
month cohort movement, newly-lapsed feeds, newly-cleared fixes, delivered rather
than polled.

**Shape.** A scheduled job over the rollup artifacts (`rollups.py`,
`rollups.yaml`) that diffs cohort state week-over-week and sends a plain-language
digest via the existing SES path (ADR 0004 opt-in model), reusing the subscription
store. No new infrastructure; a second consumer of the alert stack.

**Effort:** S–M. **Risks/deps:** the consent model (ADR 0004) extends to cohorts;
the digest must stay no-shaming even in a portfolio view. **Excellence bar:** a
liaison learns what changed across their portfolio without opening the site, in a
weekly note framed as fixes.

---

## H3 — Transformative bets

Directions that change what the product is. Each is deliberately gated — on real
data, a named user, infrastructure spend, or the portfolio owner's intent — and
each is listed here to be evaluated, not started.

### EXP-13 — Predict which feeds are about to lapse, before the date says so

**Pitch.** Use each feed's behavioral history to flag the feeds most likely to
silently expire, ahead of the deterministic expiry window.

**Impact.** RR:R3's tiered alerts fire off the current end date — deterministic.
The net-new capability is predictive: a feed whose export cadence has slowed, that
historically renews late, or that shows a pre-lapse pattern can be flagged as
at-risk weeks before the date-based alert would fire, giving a liaison time to
intervene where it matters most. This is the longitudinal panel earning its keep.

**Shape.** Start with transparent heuristics, not a black box, per the honesty
ethos: renewal-cadence trend, historical lateness, gaps between publishes, scored
into an inspectable "lapse risk" surfaced privately to liaisons in the rollup and
the portfolio digest (EXP-12). Hard-depends on retained history (FIX-02, the
`roadmap.md` Year 2 Parquet dataset).

**Effort:** L. **Risks/deps:** needs meaningful history depth (real-data + time
gate); the model must be explainable and must never become a scary opaque score
shown to an agency. **Excellence bar:** at-risk feeds are flagged to their
supporters earlier than the date-based alert, each with a stated, inspectable
reason.

### EXP-14 — A place-based "open mobility data health" index across standards

**Pitch.** Score not just one GTFS feed but a place's whole open-mobility data
picture — GTFS Schedule, GTFS-RT, GTFS-Flex, Fares v2, and GBFS — as one honest
health read.

**Impact.** The scorecard grades one standard per agency; a rider in a city
experiences all of it at once. `gbfs.py` already exists, and
`expansion-research-2026-07.md` names GBFS as "the adjacent corpus" and "a second
product surface, not a feature." The transformative step is the join: a
place-level view of how complete and fresh a community's open mobility data is
across standards, reusing the entire scorecard pattern (validate, score, plain
language, no-shaming) on a wider corpus. It is the `tods-validate` / `fare-
assistant` neighborhood of the portfolio, unified around one place.

**Shape.** A place (city/region) aggregation pulling the GTFS grade, GBFS validity
(MobilityData's canonical GBFS validator, cited in the research doc), and adoption
signals (`flex.py`, `fares.py`) into one place-scoped health card, adoption-
framed. Scope strictly after Canada scales; treat as a second product surface with
its own registry, not a bolt-on.

**Effort:** XL. **Risks/deps:** a named place-level user must ask first; a second
validator toolchain (GBFS); genuine risk of becoming a general platform — check
every step against the two core personas. **Excellence bar:** a place-level reader
sees one honest, multi-standard data-health picture with no standard shamed for
absence.

### EXP-15 — A reproducible "stand up your own scorecard" template

**Pitch.** Package the whole system as a forkable civic-data template so any
state, country, or program can run its own instance from a config and a deploy.

**Impact.** `roadmap.md` Year 3 plans white-label deployments as a service the
maintainer runs. The net-new framing is reproducibility-as-a-feature: a documented,
forkable template (the pipeline is already a runtime-agnostic CLI per ADR 0001)
that a WSDOT or a National RTAP stands up themselves — branded, with their own
registry and object storage. It converts a single-maintainer sustainability risk
into a distributed one and expresses the portfolio ethos (reproducibility) at the
system level.

**Shape.** Extract the region-specific pieces (California guideline citations,
registry, branding) behind config; ship a quickstart/cookiecutter and a "run your
own" guide; make the rubric's region profile pluggable (extends RR:E11 per-state
profiles). Delivered as documentation and configuration, not a fork, because the
core is already static artifacts plus a stateless pipeline.

**Effort:** L. **Risks/deps:** pluggable region rubric (RR:E11) is a prerequisite;
support burden of external instances; must not fragment the methodology (version
the shared rubric). **Excellence bar:** a third party stands up a branded,
correctly-cited instance from the template in a day, tracking the shared rubric
version.

### EXP-16 — A policy-effect study surface: did the NTD obligation move quality?

**Pitch.** Use the longitudinal national panel to measure, honestly, whether the
RY2025/RY2026 NTD obligation actually changed feed quality — and publish the
analysis with its caveats loud.

**Impact.** `national_trend.py` / ADR 0020 track the national quality trend; the
NTD final rule (cited in `RESEARCH-ROADMAP.md`'s research basis) creates a dated
obligation for exactly this audience. The net-new capability is treating the trend
as a natural experiment: a transparent before/after analysis around the RY2026
effective dates, framed with heavy attribution caveats (correlation, coverage
bias, the covered-set caveat). It serves the researcher (RR:D3) and journalist
(RR:E4) with something no vendor can produce, because only an independent daily
panel exists.

**Shape.** A `/research/` or methodology surface computing quality trajectories
for cohorts (reporters vs non-reporters, by size band) around the rule's effective
dates, with the honesty caveats prominent and the dataset (RR:E7) and per-agency
records (EXP-09) linked for replication. Deterministic, reproducible, no causal
overclaim.

**Effort:** M–L. **Risks/deps:** strong risk of overclaiming causation — the
honesty bar is the whole point; needs history spanning the effective dates (time
gate). **Excellence bar:** a published, replicable analysis that states plainly
what the panel can and cannot attribute to the policy, and hands the reader the
data to check it.

### EXP-17 — Extract the honesty primitives as a shared portfolio pattern

**Pitch.** Lift the reusable "honesty-as-a-feature" machinery out of this repo and
into a shared pattern the portfolio's other civic-eval tools adopt.

**Impact.** This repo holds, in code, the primitives the whole portfolio's ethos
calls for: a machine-readable methodology changelog (`score.py`), provenance
stamping on every artifact (`publish.py`: `rubric_version` / `validator_version` /
`feed_sha256`), renormalized scoring that never punishes the unmeasured
(`score.py:build_scorecard`), and no-shaming fix tiers (`score.py:_fix_tier`).
Sibling repos (`tods-validate`, `govchat-eval`, `outcome-receipts`) face the same
"state it, do not certify it" problem. Codifying these in the shared `STANDARDS`
(`/Users/chelsea/portfolio/STANDARDS`) makes the flagship's hardest-won ideas
portable — which is the portfolio's actual thesis.

**Shape.** An ADR here plus a `STANDARDS` contribution codifying the pattern
(methodology-changelog format, provenance-block shape, renormalization rule,
no-shaming tiering, static data contract + published schema); optionally a small
shared package. The reference implementation stays in this repo; the standard
travels. Purely additive — a portfolio-level act, gated on the maintainer's
cross-repo intent.

**Effort:** M. **Risks/deps:** cross-repo coordination (a portfolio-owner gate);
premature-abstraction risk — extract only what two repos already share.
**Excellence bar:** a second portfolio repo adopts the methodology-changelog +
provenance pattern from the shared standard, not by copying this repo's code.
