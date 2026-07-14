# Large-scale fixes

Drafted 2026-07-01. Structural work on correctness, provenance, architecture,
testing, and operability. None of these items appears in the existing planning
set (`roadmap.md`, `feature-roadmap.md`, `RESEARCH-ROADMAP.md`, `follow-ups.md`,
the expansion docs); where one extends an existing item, the delta is stated.
Effort tiers: S ≈ days, M ≈ 1–2 weeks, L ≈ a month, XL ≈ a quarter.

---

## FIX-01 — Record the truth about how each feed was fetched

**Status: DONE (2026-07-02).** Artifacts now carry an additive `fetch` block
(`source` origin/mirror/unknown, `final_url`, `user_agent`, `max_attempts`,
`origin_error`), recorded by `fetch.py` in a `provenance.json` sidecar next to
each snapshot and threaded through `publish.py:build_artifact`; documented in
`docs/api.md`. Kept within schema 1.4 (additive fields per the versioning
rule). The agency-page render line shipped with the confidence read (EXP-01),
and the `/fetcher/` identity page shipped 2026-07-12 (UA policy, cadence,
retry and mirror behavior, contact route, linked from the about page and the
API docs). Still open from the pitch: the honest-UA-first experiment, which
must be measured against fetch success, never assumed.

**Pitch.** Every artifact should say which bytes were graded and how they were
obtained: origin or MobilityData mirror, which User-Agent, after how many
retries.

**Why it matters.** `fetch.py:_download_with_mirror_fallback` silently swaps in
the MobilityData hosted mirror when an origin 403s or times out, but
`FetchResult.url` still records the origin URL, so `publish.py` writes an
artifact indistinguishable from an origin fetch. A mirror can lag the origin;
an agency disputing a grade ("we republished yesterday") deserves to be told
"we scored the mirror copy." Separately, the fetcher presents as Chrome
(`fetch.py:USER_AGENT`) — a documented and defensible choice, but currently
invisible to the server operators who see it. For a project whose brand is
"states it, does not certify it," fetch provenance is the one place the tool
currently does not state it. Affects: agencies disputing grades, researchers
(D3), MobilityData stewards (C1).

**Shape of the work.** Extend `FetchResult` with `source`
(`origin|mirror`), `final_url`, `attempts`, and the header set used; thread it
through `publish.py:build_artifact` into a `provenance.fetch` block (additive,
schema 1.5). Render one quiet line on the agency page (`render_site.py`) and in
the catalog. Publish a `/fetcher/` identity page documenting the UA policy,
polling cadence, and a contact route; optionally attempt an honest
`gtfs-scorecard/<version> (+https://gtfsscorecard.org/fetcher/)` UA first and
record which one succeeded, turning the UA question into measured data.

**Effort:** S–M. **Risks/deps:** none technical; the honest-UA-first experiment
could reduce fetch success and must be measured, not assumed. **Excellent
looks like:** 100% of artifacts carry a fetch-provenance block; the
mirror-scored population is countable from `catalog.json`; the UA policy is
public.

---

## FIX-02 — Content-addressed raw feed archive: make any grade reproducible

**Status: code shipped (2026-07-08), S3 tier still gated.** `archive.py`
stores each fetched feed locally, deduplicated by `feed_sha256`, and writes
through to S3 when `RAW_ARCHIVE_BUCKET` (or `ARTIFACTS_BUCKET`) is set,
following the same optional-tier pattern `vcache.py` uses for the validator
cache: the local copy is the always-on first tier, S3 is the durable second
tier, and every S3 call is best-effort so a storage hiccup never fails a
score. `scorecard reproduce <agency> <date>` (`reproduce.py`) pulls the
archived bytes for a published snapshot, re-runs the validator version that
artifact recorded, rescores, and diffs against the published grade, score,
and category scores. Still open from the pitch: the actual AWS account/bucket
(the same cost gate as `follow-ups.md`'s S3 cutover — without it the archive
is local-only and does not survive a CI runner), and the ADR on public
redistribution of a re-served copy (the archive as shipped is
private-to-pipeline, which needs no license decision).

**Pitch.** Keep the actual GTFS zips (deduplicated by `feed_sha256`) so any
published grade can be re-derived, byte for byte, at any later date.

**Why it matters.** Raw snapshots (`data/raw/`) are gitignored and die with the
CI runner; only the hash survives in the artifact. So the project's own
reproducibility claim ("the grade is reproducible rather than opaque",
`docs/api.md`) holds only for the day of scoring. `timemachine.py`'s docstring
concedes GTFS diffing "needs the raw feed, which is not archived" —
`expansion.md` A2 notes this gap but nothing designs the mechanism. A disputed
grade, a validator-upgrade study (FIX-06), a backfill (EXP-03), and the diff
observatory (EXP-02) all need this store.

**Shape of the work.** An S3 bucket keyed `feeds/<sha256>.zip`, written by the
score job only when the hash is new (most feeds change weekly at most, so
growth is incremental, not 1,166×365/yr); a small index mapping
agency/date→sha256 (already in artifacts). Add `scorecard reproduce
<agency> <date>` to `cli.py`: pull the archived zip, re-run the pinned
validator (`validate.py` already pins by version), re-score, and diff against
the published artifact. Respect `listing-policy.md` deletions and per-feed
license notes when serving copies (serve-to-self is safer than public
redistribution; decide in an ADR).

**Effort:** M. **Risks/deps:** requires the AWS account decision (same gate as
`follow-ups.md` S3 cutover); redistribution rights vary by feed license — the
archive can be private-to-pipeline without weakening reproducibility for the
maintainer, but public reproduction needs the license question answered
(flagged as a legal gate in `04-impact-and-sequencing.md`). **Excellent looks
like:** `scorecard reproduce` returns "identical" for any artifact less than a
year old; storage cost stays single-digit dollars.

---

## FIX-03 — One source of truth for presentation semantics

**Status: done (2026-07-02).** `constants_export.py` renders the Python
definitions (grade bands and ranks, category/severity/tier labels,
`STALE_FEED_DAYS`, the rule-link table, `FIX_DOCS_BASE`) into
`web/src/generated/constants.js`; `app.js` imports it. `scorecard
render-constants` refreshes the file and `render-site` runs it too;
`tests/test_generated_constants.py` fails CI when the committed copy drifts.
The Python-side copies (`cli._GRADE_RANK`, `render_site._GRADE_FLAP`,
`_CHANGE_GRADE_RANK`, `_TIER_LABELS`, the hardcoded band thresholds) now
import from the same definitions.

**Pitch.** Generate the constants the SPA needs from the Python definitions,
instead of maintaining a three-way hand-synced mirror.

**Why it matters.** `metrics.py` (`STALE_FEED_DAYS = 365`) carries a comment
asking humans to keep `web/src/app.js` in sync; `rule_links.py` is mirrored in
`app.js`; category labels live in `app.js`, `site_shell.py`, and
`render_site.py`. Only the nav has a drift test (`tests/test_static_nav.py`) —
which exists precisely because drift already happened. A silent divergence here
mis-explains a grade to exactly the non-expert audience the product serves.

**Shape of the work.** A `scorecard render-constants` step (or part of
`render-site`) that emits `web/src/generated/constants.js` from the Python
enums: expiry buckets and thresholds, grade bands, category labels/order,
severity labels, rule-link rules, `FIX_DOCS_BASE`. `app.js` imports it (it is
already an ES module, no build step needed). A CI test asserts the committed
generated file matches a fresh render, in the same pattern as
`test_static_nav.py`.

**Effort:** M. **Risks/deps:** none; purely mechanical after the first
extraction. **Excellent looks like:** grep finds no presentation constant
defined in two languages; changing `STALE_FEED_DAYS` in one place changes the
SPA, the prerendered pages, and the API docs coherently or fails CI.

---

## FIX-04 — Decompose the rendering monolith behind golden-file contracts

**Pitch.** Break `render_site.py` (5,238 lines, ~80 functions of f-string
HTML) into per-surface modules with snapshot-tested output.

**Why it matters.** `expansion-ideation-2026-07.md` §E concluded "the pipeline
does not need rethinking" — true for the data plane, but the render layer is
where most feature work now lands (six-hub redesign #240, compare page, NTD
pages all touched it), and it is the largest single file in the repo with no
output-level tests. Every new surface increases the chance a refactor silently
changes a published page. Partial extraction already started (`site_shell.py`,
`pages_tools.py`), proving the seam works.

**Shape of the work.** Continue the extraction along the existing seams:
`render_agency.py` (agency page + brief + vendor/outreach sections),
`render_hubs.py` (pulse/focus/map/changes), `render_docs.py`
(guide/accessibility/fixes), leaving `render_site.py` as the orchestrator.
Before moving anything, capture golden files: render the full site from a
frozen fixture index into `tests/goldens/`, and assert byte-identical output in
CI (the pipeline is already deterministic by design, `publish.py`). Then
refactor freely under the golden gate. Add an HTML validity check (vnu.jar or
html5lib parse) over the rendered output — axe checks accessibility, nothing
currently checks well-formedness.

**Effort:** L. **Risks/deps:** golden files must be deliberately regenerated on
intended copy changes (make it a one-command refresh with a reviewed diff);
sequence before or after FIX-03, not simultaneously. **Excellent looks like:**
no rendering module over ~800 lines; any unintended change to any published
page fails CI with a readable diff.

---

## FIX-05 — Harden the scoring math with property-based and wider mutation testing

**Status: DONE (2026-07-02).** Hypothesis invariant tests live in
`pipeline/tests/test_properties.py` (monotonicity, bounds for
correctness/freshness/realtime, grade-band totality and order, renormalization
envelope, tier-0 fix-priority stability, `_count_multiplier` tiers), bounded by
a 100-example profile inside `make verify`. The frozen ten-feed corpus canary
with exact grade/score literals is `pipeline/tests/test_score_corpus.py`.
`[tool.mutmut]` scope widened to `score.py` + `metrics.py` + `rt.py` with the
property/corpus tests added to the kill signal; first widened baseline (55.5%
killed, survivors triaged as impure rt plumbing + prose strings) recorded in
`docs/mutation-testing.md`. Still weekly/advisory per CODE-QUALITY-STANDARD §10.

**Pitch.** Test the invariants of the grade, not just its examples, and extend
mutation testing beyond `score.py`.

**Why it matters.** The grade is the product. `mutation.yml` covers only the
grade ladder in `score.py`; the deduction arithmetic in `metrics.py`
(`SEVERITY_BASE_DEDUCTION`, `COUNT_MULTIPLIER_TIERS`), the freshness slope, and
the RT component weights in `rt.py` can all be silently mutated today with no
advisory signal. Example-based tests (764 functions, strong) cannot cover the
combinatorial space of notice sets; invariants can.

**Shape of the work.** Add Hypothesis to the dev group
(`pipeline/pyproject.toml`) and write property tests for: monotonicity (adding
a notice never raises `correctness()`; more days-to-expiry never lowers
`freshness()`), bounds (all category scores in [0,100]; weighted overall within
min/max of measured categories under renormalization in
`score.py:build_scorecard`), band consistency (`letter_grade` total and
ordered), and fix-priority stability (tier-0 operational codes always outrank
tier-1 regardless of counts). Extend `[tool.mutmut]` scope to `metrics.py` and
the pure scoring parts of `rt.py`, keeping it weekly/advisory per
CODE-QUALITY-STANDARD §10. Add a frozen mini-corpus regression: score ~10
fixture feeds and assert exact grades, as a cheap cross-module canary.

**Effort:** M. **Risks/deps:** none; Hypothesis runtime is bounded with
profiles. **Excellent looks like:** a deliberate off-by-one in any deduction
constant is caught by at least one of property tests, corpus canary, or weekly
mutation report.

---

## FIX-06 — Governed validator and rubric upgrades: shadow runs and impact reports

**Status: DONE (2026-07-02).** Shipped as `pipeline/src/scorecard_pipeline/canary.py`
(`scorecard canary --candidate-version <X.Y.Z>`) plus the manual-dispatch
`validator-canary.yml` workflow: a deterministic ~100-agency sample is
dual-scored with the pinned and candidate validators (the baseline half rides
`vcache.py`), and the run emits a Markdown + JSON impact report — grade-shift
histogram, band moves, notice-code drivers — with a ready-to-paste
`METHODOLOGY_CHANGELOG` entry. `docs/rubric.md` ("Governed upgrades") now gates
`VALIDATOR_VERSION` bumps on an attached report.

**Pitch.** Never change the measuring stick blind: before bumping
`VALIDATOR_VERSION` or the rubric, dual-score a national sample and publish
the grade-shift histogram.

**Why it matters.** `validate.py` pins 8.0.1; every validator release adds,
removes, or reclassifies notices, which silently moves grades for 1,166
agencies at once. RR:R9 (shipped) lets a reader *see* which version produced a
grade; nothing governs *changing* it — and `roadmap.md`'s own "rubric fairness"
governance section promises a public changelog on weight changes without a
mechanism to know what a change does before it lands. An unexplained
methodology-driven grade drop is exactly the event that would burn trust with
liaisons (F1) and journalists (E4).

**Shape of the work.** A manual-dispatch `validator-canary.yml`: run old and
new jars over a stratified sample (~100 feeds via `shards.py` logic, reusing
`vcache.py` so the old-version half is nearly free), diff per-agency grades and
per-code notice populations, and emit a Markdown impact report. Gate any
`VALIDATOR_VERSION` bump on an attached report; append the observed national
effect to `score.py:METHODOLOGY_CHANGELOG` ("validator 8.0.1→8.1: median grade
unchanged, 12 agencies moved one band, driven by <code>"). Same harness serves
rubric-weight changes.

**Effort:** M. **Risks/deps:** none beyond CI minutes for the canary run; pairs
with FIX-02 for perfectly-controlled comparisons. **Excellent looks like:** no
methodology change ships without a published, dated impact report; a trend
reader can attribute every historical grade discontinuity.

---

## FIX-07 — Honesty at the band edge: grade margins and weight sensitivity

**Status: Done (2026-07-02).** `overall.margin_to_next_band` and
`overall.margin_to_lower_band` ride on every artifact
(`score.py:grade_margins`); `scorecard sensitivity` publishes
`data/artifacts/sensitivity.json`. The original rubric 1.1 study covered 1,449
feed records and found at most 8.1% letter churn under a single ±20%
renormalized weight perturbation. It is historical, not a current-contract
claim; rubric 1.2 publishes no headline until its guarded cohort is rescored. The
`/how-to-read/` page explains both with the encouragement framing.

**Pitch.** Publish how close each grade sits to its band boundary, and how
robust the national picture is to the rubric's own parameter choices.

**Why it matters.** `score.py:GRADE_BANDS` makes 89.9 a B and 90.1 an A; the
letter hides that these are the same feed. The weights (35/20/25/20) and
deduction constants are judgment calls, honestly documented in `rubric.md`, but
their *consequences* are not: nobody can see whether the leaderboard order
would survive plausible alternative weights. This is the natural next step of
the project's own "reproduce or contest the grade" stance
(`score.py:methodology()` docstring), and it pre-arms the press-explainer
(RR:E3) with real numbers.

**Shape of the work.** Additive artifact fields: `overall.margin_to_next_band`
and `overall.margin_to_lower_band` (one subtraction each). A yearly (or
per-rubric-change) sensitivity job: rescore the latest national snapshot under
perturbed weights (±20% per category, renormalized) and publish the share of
agencies whose letter changes, as a section on `/how-to-read/`. UI copy for
near-boundary grades: "a B, 0.4 points from an A" — encouragement framing that
also happens to be the truth.

**Effort:** S (margins) + M (sensitivity study). **Risks/deps:** copy must be
worded so a margin never reads as "almost failing" (no-shaming check);
sensitivity results might be uncomfortable — publishing them anyway is the
point. **Excellent looks like:** every scorecard states its margin; the
methodology page quantifies rubric robustness with a dated study.

---

## FIX-08 — A measured, prioritized path to full plain-language coverage

**Status: DONE (2026-07-02) — governance mechanics.**
`findings_national.plain_language_coverage` computes distinct-code and
instance-weighted coverage over the national rollup plus the uncurated queue
(codes ranked by national instance count); `/problems/` publishes both numbers
and the top of the queue, noting uncurated codes fall back to generic text.
`scripts/check_readability.py` gates every curated `what`/`why`/`fix` string
(avg sentence length <= 22 words, Flesch-style floor >= 50) in `make verify`
and CI, after the contrast check; seven existing strings were rewritten to
clear the bar. The weekly advisory check shipped 2026-07-12:
`scorecard coverage-check` compares instance-weighted coverage against a
saved baseline (advanced Mondays in the daily workflow, persisted through
S3) and raises a workflow warning on any drop, never a failure. First
measured value: 33.3% instance-weighted, 44 of 118 codes. Still open from
the pitch: the mass curation itself (the queue's entries becoming
`notices.py` entries and fix pages), which is sustained editorial work.

**Pitch.** Turn "grow the translation table" from an intention into a managed
metric: instance-weighted coverage, a frequency-ranked curation queue, and a
readability gate.

**Why it matters.** The product's stated differentiator is the plain-language
layer, yet `notices.py` curates 22 codes against a validator taxonomy of ~300;
everything else gets a generic fallback. `product-roadmap.md` Year 1 already
plans "the knowledge base toward the whole taxonomy" — the net-new part here is
governance: today nobody can say what fraction of the findings a real reader
encounters are actually translated, so the gap can't be managed down.

**Shape of the work.** Compute coverage two ways from data already on hand
(`findings_national.py` aggregates national notice populations):
distinct-code coverage and instance-weighted coverage ("% of all findings shown
nationally that have curated language"). Publish both on `/problems/` and fail
a weekly advisory check if instance-weighted coverage drops. Generate the
curation queue automatically: top uncurated codes by national instance count,
each becoming a `notices.py` entry plus a `docs/fixes/<code>.md` page (28 exist
today). Add a readability check to `make verify` for the `what/why/fix` strings
(sentence length / syllable heuristic, pure-Python, same shape as
`scripts/check_contrast.py`) so the plain-language promise is enforced, not
just intended. Drafting can be LLM-assisted but every entry is human-reviewed
before merge — stated in the PR template.

**Effort:** M. **Risks/deps:** curation is sustained editorial work; the metric
makes the debt visible, which is the feature. **Excellent looks like:**
instance-weighted coverage ≥95% and displayed publicly; no curated string
regresses below the readability bar.

---

## FIX-09 — A behavioral test harness for the frontend

**Status.** Done (2026-07-02). `pipeline/tests/e2e/` runs pytest-playwright
against the locally served site (assembled the way pages.yml assembles it):
route smoke tests, the artifact-404 failure path (visible `role="alert"`
error, no stuck spinner), keyboard-only picker/filter/compare flows, and
SPA/prerendered parity on grade, category scores, and top-3 fixes for three
agencies. A separate `.github/workflows/e2e.yml` workflow and `e2e` dependency
group keep ci.yml and the coverage gate untouched (`-m "not e2e"` by default).

**Pitch.** Put the 1,700-line `web/src/app.js` and the prerendered pages under
browser tests: routing, keyboard flows, failure states, and SPA/static parity.

**Why it matters.** The merge gate is thorough for Python (92% branch, strict
mypy) and for contrast/axe, but no test executes the SPA's logic: hash routing,
`DATA_BASES` fallback resolution, the "Loading scorecards…" failure path the
README itself warns about, or whether the SPA and the prerendered page for the
same agency present the same grade and fixes. WCAG 2.2 AAA is claimed
(`docs/vpat.md`); keyboard operability of interactive surfaces is exactly the
kind of claim that regresses silently. This complements RR:R6 (a human AT
pass): R6 proves it once, this keeps it proven.

**Shape of the work.** Playwright (or the lighter `pytest-playwright`) in a new
CI job over a locally served fixture site: route smoke tests for `#/`,
`#/agency/<id>`, `#/programs`; a fetch-failure test (artifacts 404 → visible,
announced error, not a spinner); keyboard-only traversal of the picker,
findings table filters, and compare form; a parity assertion that grade,
category scores, and top-3 fixes match between `web/agency/<id>/` and the SPA
for three fixture agencies. Keep it a separate workflow so `ci.yml` stays fast.

**Effort:** M. **Risks/deps:** flakiness discipline (fixture data only, no
network); a first real browser dependency in CI. **Excellent looks like:** a
route regression, a broken fetch fallback, or an SPA/static grade mismatch
fails a PR before a human sees it.

---

## FIX-10 — Machine-enforce the data contract end to end

**Status: Done (2026-07-02).** `web/schemas/artifact.schema.json` (Draft
2020-12, closed top level) now covers the per-agency artifact;
`publish.publish()` validates every artifact against it before writing, so the
daily collect run cannot publish a shape change without a schema update.
`tests/test_schemas.py` validates all published document types — every
`latest.json` under `data/artifacts/`, `catalog.json`, and `directory.json` —
against the published schemas and checks each schema itself. The first
validation run surfaced the predicted payoff: `ntd_ready` is null for non-US
agencies (ADR 0026) but the catalog/directory schemas said non-nullable string;
both schemas were corrected. Follow-up closed 2026-07-12: `rollup.schema.json`
and `rollup-index.schema.json` now cover the program rollups and their index,
validated in `tests/test_schemas.py` against a direct `build_rollup()` call,
every published rollup, and the golden-site fixtures. Still open: wiring
schema-version bumps to a required schema diff in PRs.

**Pitch.** A JSON Schema for the per-agency artifact — the primary public
contract — validated in CI against everything the pipeline publishes.

**Why it matters.** `docs/api.md` documents schema 1.4 carefully and publishes
schemas for `catalog.json` and `directory.json` (`web/schemas/`), but the
per-agency artifact (`latest.json`, `<date>.json`) — the shape consumers, the
SPA, the MCP server (`mcp_server.py`), and the DuckDB layer all read — has no
schema, and I found no CI step validating any published output against the
schemas that do exist. The contract is currently enforced by prose and by
consumers noticing.

**Shape of the work.** Write `web/schemas/artifact.schema.json` (and
`rollup.schema.json`) from `publish.py:build_artifact`'s actual shape; add a
collect-job step (and a unit test) that validates every artifact, catalog,
directory, and rollup produced in that run; wire schema-version bumps to a
required schema diff in the PR. Publish all schemas at `/schemas/` as api.md
already promises for the two that exist. Consider generating the schema from
typed dataclasses to avoid a second hand-synced artifact (ties into FIX-03's
single-source principle).

**Effort:** M. **Risks/deps:** the first validation run will likely surface
real shape inconsistencies in older dated artifacts — treat that as the payoff,
not a blocker; validate current-run output first, backfill later. **Excellent
looks like:** a field rename cannot reach production without a schema-version
bump and changelog entry; consumers can validate against `/schemas/` for every
published document type.

---

## FIX-11 — Operational transparency: a public pipeline-health surface

**Status: Done (verified 2026-07-12).** `run_summary.py` builds a per-shard
outcome record inside `run_agency`, the collect job merges shards into
`data/artifacts/run/latest.json`, and `/status/` renders the commitment,
the historical refresh record, and today's shard outcomes publicly.

**Pitch.** Publish what the pipeline itself did each day — shard outcomes,
fetch failures, mirror fallbacks, validator cache hits — as a status page and
artifact.

**Why it matters.** Users are asked to trust daily numbers, but the operational
evidence is private: `watchdog.yml` emails the owner, shard logs live in
Actions. If 1 of 12 shards fails, ~97 agencies silently show yesterday's data
with no indication anywhere (I could not find a partial-degradation check in
`scorecard.yml`'s collect job — stated with uncertainty). For a
single-maintainer project, a public health surface is also the honest answer
to "what happens when she's on vacation": degradation is visible, not hidden.
The OBSERVABILITY-STANDARD in `docs/standards/` points this direction; nothing
in the roadmaps builds it.

**Shape of the work.** Each shard already knows its outcomes; emit a
`run-summary.json` per shard (scored / reused / unreachable / mirrored /
cache-hit counts, wall-clock), merge in collect into
`data/artifacts/run/latest.json`, and render `/status/`: last daily run time,
per-shard result, count and list of feeds unreachable today, staleness
distribution of `retrieved_at` across the catalog. Make collect fail loudly (or
badge the site) when >N% of agencies were not refreshed. Feeds into FIX-01's
provenance work naturally.

**Effort:** M. **Risks/deps:** copy must distinguish "our pipeline failed" from
"the agency's feed failed" as carefully as the scorecards do. **Excellent looks
like:** any consumer can answer "how fresh is this dataset right now?" from
`/status/` without trusting the maintainer's word.

---

## FIX-12 — Registry at scale: shard and schema-gate `agencies.yaml`

**Status: Done (2026-07-12).** The schema gate landed first: malformed entries,
cross-shard duplicate ids and aliases, unsafe manifest paths, partial
migrations, and unlisted shards all fail before the process registry changes.
The dedicated mechanical migration then preserved all 1,149 agency identities,
moved 1,082 located entries into 59 country/subdivision shards, and kept 67
honestly unlocated entries in `registry/intake.yaml`. Entry blocks were moved
textually so comments and formatting survived; comparison with the pre-split
registry found no non-location field drift. `registry/index.yaml` is the one
explicit production manifest. The submission handler appends only to intake
and checks published ids for duplicates already in curated shards, while
`discover`, `backfill-state`, and `ntd-crosswalk` edit only manifest-listed
shards. The weekly discovery workflow, secret scanner, SAST boundary,
contributor guide, and field reference all follow the new layout.

**Pitch.** Split the 447 KB single-file registry into per-state files with a
validated schema, so curation scales past one careful maintainer.

**Why it matters.** The former `agencies.yaml` held more than a thousand entries
and had three writers: curators, `discover.yml`, and the submission flow. PR
review of a 447 KB YAML diff was where a bad URL or duplicate id could slip
through, and unrelated contributions collided in one file. RR:R12 (mdb
pinning) improved the entries; this work fixed the container.

**Shape of the work.** `registry/<country>/<state>.yaml` loaded and merged by
`agencies.py` (keep reading the legacy single file during transition); a
registry schema (id format, URL well-formedness, enum fields like
`service_type`, uniqueness across shards) enforced by a fast CI check and by
`scorecard sync`/`discover` when they propose entries; a one-time mechanical
split commit. CODEOWNERS per state directory becomes possible if contributors
ever materialize.

**Effort:** M. **Risks/deps:** touch every code path that reads the registry
(`config.py`, `agencies.py`, shards, discover, submissions); do it in one
mechanical PR with the schema check landing first. **Excellent looks like:** an
add-an-agency PR touches one small file, fails CI on any malformed field, and
never conflicts with an unrelated agency's edit.

---

## FIX-13 — Repository data-plane remediation beyond the planned S3 cutover

**Status: ADR written (2026-07-08) — decision made, execution still gated on
the S3 cutover.** `docs/decisions/0030-data-plane-history-remediation.md`
decides: (a) no orphan `data` branch or separate repo — the S3 cutover already
in flight (`follow-ups.md`) is the one mechanism needed to stop future data
commits; (b) prerendered `web/agency/**` pages move to a CI render step in
`pages.yml` instead of staying committed, once the cutover lands; (c) no
history rewrite — existing SHAs, PR links, and the not-yet-started
`dataset-YYYY-MM` tag scheme must keep resolving. Re-measured at write time:
`.git` is now 884 MB (up from the 521 MB noted below a week earlier),
`data/artifacts` is 534 MB, `web/agency/` still carries 1,449 committed
directories. Execution (the actual `pages.yml` change and dropping
`web/agency/**` from the collect job's `git add`) is deferred until
`follow-ups.md` steps 1–3 (the S3 cutover itself) ship, per the sequencing
this item always called for — that part remains a maintainer-scheduled
migration, not done here.

**Update (2026-07-12):** the gate cleared and most of the execution landed
with the cutover. `follow-ups.md` records the S3 source of truth complete as
of 2026-07-10, automation no longer writes to `main` (#63), and `pages.yml`
renders and assembles the site in CI from S3-hydrated artifacts. The
committed `data/artifacts/**` snapshot now serves as the fork fallback when
no bucket is configured, and the committed `web/agency/**` copies are frozen
at the cutover date. Whether to prune those committed copies (and reclaim the
git history size named below) stays a maintainer decision per ADR 0030's
no-rewrite rule.

**Update (2026-07-14):** the release tree is now bounded to the curated registry.
The 322 orphan artifact directories and their generated pages were removed from
the current tree; 1,128 scored feed records remain. The deploy also copies raw
artifact directories only when `index.json` names them. Git history and the S3
archive were not rewritten.

**Pitch.** Decide, once and deliberately, what to do about the data already in
git — 521 MB of `.git`, 382 MB of committed artifacts, 1,449 prerendered pages,
and hourly `chore(data)` commits — not just about future writes.

**Why it matters.** `follow-ups.md` stops *future* artifact commits after the
S3 cutover, but the accumulated history stays in every clone forever, the
committed prerendered site under `web/` keeps growing with the registry, and
the code history is already hard to read through refresh noise (see `git log`).
At current cadence the repo trends toward GitHub's soft limits within months.
This is also a citability question: monthly `dataset-YYYY-MM` tags currently
point into this history, so any history surgery must preserve what citations
resolve to.

**Shape of the work.** An ADR weighing: (a) data commits to an orphan
`data` branch or a separate `gtfs-scorecard-data` repo (keeps `main` a code
repo; cheap, no history rewrite); (b) prerendered pages built in `pages.yml`
rather than committed (they are derived artifacts; `render-site` already
regenerates them deterministically — CI-build them like `_site/` instead of
tracking 1,449 directories); (c) whether to rewrite history at all — likely
no, because dataset tags and PR links must keep resolving; document the
decision either way. Sequence after the S3 cutover so there is only one
migration story.

**Effort:** M–L, mostly decision and migration care rather than code.
**Risks/deps:** maintainer decision required (history and tag continuity are
irreversible choices); depends on `follow-ups.md` steps 1–3. **Excellent looks
like:** `git log --oneline main` reads as a code history; a fresh clone is
<100 MB; every existing dataset citation still resolves.
