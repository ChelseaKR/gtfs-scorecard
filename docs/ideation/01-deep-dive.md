# Deep dive: current state as read on 2026-07-01

An assessment from a full read of the repository (code, CI, docs, git history),
not from its own documentation's claims. File paths are cited so every statement
can be checked.

## What this actually is now

The README's framing ("a scorecard for two pilot agencies, generalizing") is
long outdated in the best way. As of 2026-07-01 this is a **live national data
product**: ~1,166 active agencies in `agencies.yaml` (a 447 KB registry),
~1,449 prerendered agency pages under `web/agency/`, a daily 12-shard scoring
run (`.github/workflows/scorecard.yml`), an hourly cadence-tiered intraday
refresh (`refresh.yml`, ADR 0010), realtime health monitoring, a versioned read
API (`docs/api.md`, schema 1.4), a Parquet export, monthly citable dataset
releases (`dataset-release.yml`), a GitHub Marketplace CI action (`action.yml`),
and a read-only MCP server (`pipeline/src/scorecard_pipeline/mcp_server.py`,
shipped in PR #223/#242). The git log shows dozens of substantive PRs in the
last two weeks alone, interleaved with automated `chore(data)` refresh commits.

## Architecture, as read

- **Registry and config.** `agencies.yaml` (curated; per-agency `service_type`,
  `operating_note`, `ntd_note`, `state`, `country`, `mdb_id`), `rollups.yaml`
  (program cohorts), `subscriptions.yaml` (opt-in alerts).
- **Ingestion.** `fetch.py` downloads with a browser-identical User-Agent and
  falls back to the MobilityData hosted mirror on origin failure
  (`_download_with_mirror_fallback`). All fetching funnels through
  `net.py:safe_get` — an SSRF guard (scheme/host/redirect validation) with a
  512 MB download cap and WAF-aware retry policy.
- **Validation.** `validate.py` wraps the canonical MobilityData gtfs-validator
  as a subprocess, pinned at `VALIDATOR_VERSION = "8.0.1"`, with an S3-backed
  result cache (`vcache.py`) so unchanged feeds skip the Java run.
- **Scoring.** `metrics.py` (correctness: per-distinct-code deductions, ERROR 12
  / WARNING 4 / INFO 0.5, count multipliers 1.0/1.5/2.0; freshness: expiry
  buckets `current/expiring_soon/lapsed/stale`, `STALE_FEED_DAYS = 365`),
  `completeness.py`, `rt.py`/`rt_drift.py` (sampled realtime quality), then
  `score.py` (weights 35/20/25/20 renormalized over measured categories, grade
  bands, rider-impact-first fix tiers, and a machine-readable
  `METHODOLOGY_CHANGELOG`). `notices.py` translates validator codes into
  what/why/fix/effort language — 22 curated entries, generic fallback otherwise.
- **Publishing.** `publish.py` writes schema-1.4 JSON artifacts with provenance
  (`rubric_version`, `validator_version`, `feed_sha256`), deterministically and
  idempotently. Artifacts are committed to git under `data/artifacts/` and also
  mirror-able to S3 (gated, unapplied — `docs/follow-ups.md`).
- **National layers.** NTD readiness and crosswalk (`ntd.py`,
  `ntd_crosswalk.py`), ACS equity overlay plus tract refinement (`equity.py`,
  `tract_equity.py`), Canada CIMD (`cimd.py`, ADR 0027), ridership weighting
  (`ridership.py`, ADR 0021), national problems KB (`findings_national.py`),
  adoption detection for flex/fares/pathways (`flex.py`, `fares.py`,
  `pathways.py`), vendor aggregation (`vendors.py`).
- **Rendering and distribution.** `render_site.py` (5,238 lines) prerenders the
  full crawlable site; `site_shell.py` and `pages_tools.py` are partial
  extractions. `web/src/app.js` is a 1,700-line no-build hash-routed SPA reading
  the same artifacts. Distribution surfaces: static `/api/v1/`,
  `agencies.parquet` + DuckDB query layer (`warehouse.py`), Atom change feed
  (`atomfeed.py`), badges (`badge.py`), `llms.txt`, MCP.
- **Operations.** 16 workflows including `watchdog.yml` (independent uptime
  check), `discover.yml` (moved-feed PRs), `onboard.yml` (issue-driven scoring
  with untrusted-input handling), `mutation.yml` (weekly, advisory, scoped to
  `score.py`), `a11y.yml` (axe), and a merge gate of ruff + ruff-format + strict
  mypy + pytest at 92% branch coverage + an AAA contrast check
  (`pipeline/scripts/check_contrast.py`, `Makefile:verify`).
- **Infra.** Terraform for the artifacts CDN, submission endpoint, SES alerts,
  and SQS fan-out compute (`infra/`), all built and deliberately unapplied;
  `follow-ups.md` documents each cutover as a migration, not an apply.

## What is genuinely strong

1. **Honesty is implemented, not asserted.** The methodology is published as
   machine-readable JSON (`score.py:methodology()`), every artifact carries the
   rubric and validator versions that produced it, unmeasured categories
   renormalize instead of penalizing, and the fix-priority tiers encode the
   no-shaming principle in code (`score.py:_fix_tier`). This is the portfolio
   ethos executed at the code level.
2. **Test discipline is real.** 80 test files, 764 test functions, a 92% branch
   coverage merge gate, advisory mutation testing on the grade ladder, and
   drift-catcher tests like `tests/test_static_nav.py`. The task brief's "693
   tests" figure is already stale; the suite has grown.
3. **Static-first economics have held.** ~1,166 agencies on GitHub Actions +
   Pages with zero always-on backend, kept honest by ADRs (0002, 0003, 0010)
   that pre-write every scaling cutover.
4. **Decision hygiene.** 28 ADRs in `docs/decisions/`, each planning doc
   cross-referencing rather than duplicating, and a same-day implementation log
   at the bottom of `expansion-ideation-2026-07.md`.

## Structural debt actually observed

1. **Git is the data plane, and it is filling up.** `.git` is 521 MB;
   `data/artifacts/` is 382 MB of committed JSON; `web/agency/` holds 1,449
   committed prerendered pages; hourly refresh commits pollute `git log`.
   `follow-ups.md` plans to stop committing *future* artifacts, but nothing
   addresses the accumulated history or the committed prerendered site.
2. **A provenance gap in fetching.** `_download_with_mirror_fallback` returns
   bytes only; `FetchResult.url` records the origin URL even when the
   MobilityData mirror was scored. An artifact cannot say whether the grade
   reflects the agency's own endpoint or a mirror copy. Related honesty tension:
   the fetcher presents as Chrome (`fetch.py:USER_AGENT`) — a documented,
   defensible choice, but currently invisible to the people whose servers see it.
3. **Grades are not reproducible after the fact.** Raw snapshots
   (`data/raw/`) are gitignored and discarded on ephemeral CI runners; only
   `feed_sha256` survives. `timemachine.py`'s own docstring concedes that true
   GTFS diffing "needs the raw feed, which is not archived."
4. **A three-way presentation mirror maintained by hand.** `metrics.py`
   (`STALE_FEED_DAYS`: "so the web app's mirror of it (web/src/app.js) stays in
   sync"), `rule_links.py` mirrored in `app.js`, category labels duplicated in
   `app.js` and `site_shell.py`. Only the nav has an automated drift test.
5. **`render_site.py` is a 5,238-line f-string monolith.** Partial extraction
   exists (`site_shell.py`, `pages_tools.py`), but ~80 rendering functions
   remain in one file with no snapshot/golden-file coverage of the HTML output.
6. **Frontend logic is untested.** `app.js` (1,700 lines) has no JS test
   harness; a11y is checked by axe, but routing, failure states, and
   SPA/prerendered parity are unverified.
7. **The data contract is only partially machine-enforced.** JSON Schemas exist
   for `catalog.json` and `directory.json` (`web/schemas/`), but not for the
   per-agency artifact — the primary contract — and I found no CI step
   validating published output against any schema (stated with uncertainty; it
   may live somewhere I did not read).
8. **Translation coverage is thin relative to the promise.** 22 curated
   translations in `notices.py` against a validator taxonomy of roughly 300
   rules; everything else falls back to a generic line, on a product whose
   stated differentiator is exactly this layer.
9. **Validator upgrades are ungoverned.** The pin at 8.0.1 is correct, but there
   is no process for measuring what a version bump does to the national grade
   distribution before it ships (R9 stamps versions; nothing governs changes).
10. **Mutation testing scope is narrow.** `score.py` only; the deduction math in
    `metrics.py` and the RT component weights in `rt.py` — where a silent bug
    equally mis-grades — are outside it.
11. **Operational visibility is private.** `watchdog.yml` emails the owner;
    per-shard failure, fetch-outcome rates (403/timeout/mirrored), and partial
    degradation of the daily run have no public surface, on a product whose
    users are asked to trust daily numbers.

## Strategic position in the portfolio

This is the portfolio's flagship demonstration that "honesty as a feature" can
run at national scale on static infrastructure. It is the most production-real
of the 21 repos: a live domain, a citable dataset, three distribution channels
(web, API/Parquet, MCP), and a federal-policy tailwind (NTD RY2026). Its risks
are correspondingly operational rather than product-shaped: a single
maintainer, a git-as-database runway measured in months at current commit
rates, and public claims (AAA, daily freshness, reproducibility) whose
enforcement is partly manual. The fixes in `02-large-scale-fixes.md` are chosen
to convert those claims from asserted to enforced; the expansions in
`03-expansions.md` build on surfaces that already exist rather than opening new
fronts.
