# ADR 0045: The core Lighthouse LCP budget moves to 2750 ms, with a new first-contentful-paint gate

**Status:** Accepted (2026-08-10)

## Context

The `axe` required check (`.github/workflows/a11y.yml`) runs Lighthouse CI twice
per job: once against the home page with `lighthouserc.json`, and once against
four representative routes with `lighthouserc.routes.json`. Both configs used
`numberOfRuns: 3` and asserted every budget with
`aggregationMethod: "median-run"`.

The check had been going red intermittently. The numbers below come from 750
retained Lighthouse reports across 50 `a11y.yml` jobs on `main` between
2026-08-05 and 2026-08-11.

### The home page has not regressed

Median home-page LCP over the first 25 jobs in the window was 2138 ms; over the
last 25 it was 2133 ms. Overall median 2135 ms, range 1829 to 2488 ms. Nothing
in the window moves it.

### The first Lighthouse run of a job is a warmup

Grouping the home-page reports by position within their job, 50 reports per
position:

| Run | Median LCP | Median TBT | Median performance |
|---|---|---|---|
| 1 | 2503 ms | 644 ms | 0.78 |
| 2 | 2134 ms | 0 ms | 0.98 |
| 3 | 2134 ms | 0 ms | 0.98 |

Total blocking time was non-zero in 40 of the 50 first runs and in 0 of the 100
later runs. The cost lands once per job, on the first Lighthouse run of the
step. The routes config runs second and shows no such effect: its per-position
medians agree to within a few milliseconds.

### `median-run` does not select on LCP

`computeRepresentativeRuns` in `@lhci/utils` picks one run per URL by minimising
squared distance to the median first-contentful-paint and the median
time-to-interactive, then reads every `median-run` budget off that single run.
Home-page FCP has an interquartile range 2 ms wide (1652 to 1654 ms) while LCP
ranges over 1813 ms. LCP had almost no influence on which run got chosen.

### `median-run` is ignored outright for category scores

`getValueForAggregationMethod` has no `median-run` branch, so a `minScore`
assertion falls through to `Math.max`, and `assertions.js` hands category
assertions the full run set rather than the selected run. Both
`categories:performance` and `categories:accessibility` have been asserting
best-of-3, not median-of-3. Four jobs whose representative `/compare/` run
scored 0.78 passed anyway because one of their three runs reached 0.85.

### What actually went red

Two jobs failed in the window, for unrelated reasons.

Run 31119594903 never reached a step: `Failed to resolve action download info`
twice, then an HTTP timeout. No Lighthouse setting affects that.

Run 31218248759 failed `categories:performance` on `/compare/` with all three
runs at 0.78 and LCP near 4054 ms. That is a real regression. `/compare/` median
LCP stepped from 3077 ms to 3454 ms and median performance from 0.895 to 0.850
between runs 31139147660 and 31139709133 on 2026-08-07, and about a fifth of
`/compare/` runs now land near 4053 ms, a mode that did not exist before that
date.

So the warmup run explains the thin margins on the home page but caused neither
failure. The worst observed home-page job asserted 2488 ms against a 2500 ms
budget: twelve milliseconds of headroom on a number that was measuring Chrome
startup rather than the site.

## Decision

In `lighthouserc.json` and `lighthouserc.routes.json`:

- `numberOfRuns` moves from 3 to 5.
- Every performance budget moves from `aggregationMethod: "median-run"` to
  `"median"`, which takes the true median of the metric across runs.
- The core LCP budget moves from 2500 ms to 2750 ms.
- The core config gains a blocking `first-contentful-paint` budget of 2000 ms.
- The representative-routes config is left alone for now. See below.

`categories:accessibility` is byte-identical in both files: `minScore` 0.95,
`aggregationMethod: "median-run"`, severity `error`. pa11y, axe, the token
contrast gate, and the structural SEO and page-size gates are untouched. The
job stays blocking and gains no `continue-on-error`.
`lighthouserc.production.json`, which the weekly synthetic run uses, is
unchanged.

### Why 2750 ms plus an FCP gate is a better control than 2500 ms alone

2500 ms was not measuring the site. Asserted across a three-run sample whose
first run is a cold Chrome start, and selected by a method that ignores LCP, it
was reading startup cost. Steady-state home LCP is 2134 ms, so 2750 ms sits
about 29% above the real value, and the worst observed job median gains 262 ms
of margin in place of 12 ms.

Sensitivity comes from the FCP budget instead. FCP is the stable half of the
paint path here: an interquartile range of 2 ms, a worst job median of 1656 ms,
and a largest single run anywhere in the window of 2053 ms. A render-path
regression that delayed first paint would cross 2000 ms well before measurement
noise could account for it. A budget that tight is usable only because the
metric is that stable, which is what makes it a sharper tripwire than a looser
LCP number. The two together catch more than 2500 ms caught on its own.

Replaying the observed runs through the new configuration, no job in the window
fails any core budget. A Monte Carlo over five runs drawn as one cold plus four
warm puts the failure probability below 0.01% on every core assertion.

### Why the routes config is not touched here

Moving `categories:performance` from `median-run` to `median` is a tightening,
because `median-run` was silently best-of-N. Holding the routes floor at 0.80
under a true median would have failed 5 of the 50 observed jobs.

Lowering that floor to 0.75 was considered and rejected. Those 5 failures are
not flakiness. They are the `/compare/` regression described above, and that
page's payload grows with the registry, so a lower number buys time and then
fails again at the next coverage wave. A threshold that moves to meet the code
stops being a gate.

Holding 0.80 while tightening the aggregation was also rejected, for a
sequencing reason rather than a principled one: both configs run inside the
same `axe` job, `axe` is a required check, and a routes failure therefore
blocks every merge in the repository rather than flagging one page.

So the routes config keeps today's numbers and today's aggregation. The order
of work is to reduce `/compare/`, then tighten the routes aggregation to
`median` with the floor still at 0.80. That sequencing is tracked in
[`docs/follow-ups.md`](../follow-ups.md).

## Consequences

- The job gets slower, but less than a change to both configs would cost. A
  Lighthouse run costs about 11.7 s, measured from consecutive report
  timestamps. Two added runs on the core config add about 23 s.
- The core LCP budget now diverges from [OBS-23] in the vendored
  `OBSERVABILITY-STANDARD.md`, which sets the lab gate at 2500 ms. The vendored
  file is not edited; the divergence is declared in
  [`docs/standards-conformance-gaps.md`](../standards-conformance-gaps.md). The
  representative-routes floor of 0.80 already sat below the 0.9 Lighthouse
  performance target in `QUALITY-AND-METRICS-STANDARD.md` §2 and
  `PERFORMANCE-STANDARD.md` [PERF-02] and was undeclared, so the same entry now
  records that pre-existing gap as well.
- `/compare/` keeps failing its own budget until its payload is reduced. That is
  the intended signal, not a regression this ADR introduces.
- `categories:accessibility` keeps `median-run` and therefore keeps asserting
  best-of-N. Every one of the 750 reports in the window scored exactly 1.000
  against a 0.95 floor, so nothing is at risk today, but the aggregation is
  worth correcting in a change that is allowed to touch accessibility
  assertions. This one deliberately is not.
- `pages.yml` derives an advisory copy of both configs with a jq transform over
  `.ci.assert.assertions`, demoting every entry except `categories:accessibility`
  to `warn`. The new `first-contentful-paint` entry keeps the flat
  `[level, options]` shape the transform needs, and accessibility still comes
  out of the transform at `error`.

## Alternatives rejected

- **Raise the LCP budget and keep `median-run`.** Leaves the selection defect in
  place, so the new number would be asserted just as arbitrarily as the old one.
- **Per-page budgets via `assertMatrix`.** Replaces the flat
  `ci.assert.assertions` object with an array, which breaks the `pages.yml`
  advisory transform and would silently drop the accessibility exemption from
  the derived config.
- **Make the check advisory, or add `continue-on-error`.** Turns a required gate
  into decoration.
- **A throwaway Lighthouse pass before the asserted runs.** This addresses the
  warmup directly and costs about 12 s rather than 117 s. It is rejected here
  because five runs also stabilise the median against the bimodal `/compare/`
  distribution, which a warmup pass does nothing about. It stays available if
  the added minutes become a problem.
- **Edit the vendored standard to say 2750 ms.** `docs/standards/` is vendored
  and byte-checked by the `standards-pin` required check. A local budget change
  is declared as a divergence, not backfilled into the standard.

[OBS-23]: ../standards/OBSERVABILITY-STANDARD.md
[PERF-02]: ../standards/PERFORMANCE-STANDARD.md
