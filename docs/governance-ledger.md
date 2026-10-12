# Governance ledger

Delivery-health and conformance measurements for this repository, per
CI-CD-STANDARD §10 and QUALITY-AND-METRICS-STANDARD. This file answers four
questions the roadmap does not: which CI stages apply here, what the pipeline
metrics currently measure, how delivery health looks this quarter, and what the
latest OpenSSF Scorecard run found. Audit findings closed by this file:
CICD-29, QM-11, SEC-38, and the mapping half of QM-01.

Every number below states its measurement date and method. Refresh cadence:
quarterly (next due 2027-01-17), and the Scorecard section monthly (next due
2026-11-02). The first snapshot was taken 2026-07-17 and the second 2026-10-02;
earlier figures stay in place next to the new ones so the trend is readable.

## CI stage declarations (CICD-29)

CI-CD-STANDARD §1 defines nine pipeline stages. Stages 1 through 5 are
mandatory everywhere; 6 through 8 must be declared applicable or N/A with a
reason. As of 2026-10-02 the `main` branch ruleset
(`main-required-checks-and-review`, enforcement: active) requires fifteen status
checks, a pull request with one approving review, and linear history. On
2026-07-17 it required nine checks; six more were added on 2026-08-21 (CodeQL
javascript, both Trivy image scans, terraform fmt + validate, zizmor, and
dependency review). "Merge-blocking" below means required by the ruleset, with
one caveat measured this quarter. The ruleset gives the repository admin role an
"always" bypass, and none of the 121 PRs merged to `main` between 2026-09-02 and
2026-10-02 carries an approving review, so every one of those merges used that
bypass. The same bypass let three commits reach `main` with no pull request on
2026-09-20 (see the 2026-10-02 DORA snapshot).

| Stage | Declaration | Where enforced |
|---|---|---|
| 1 format | applicable | `ruff format --check` via `make verify` (`ci.yml` `pipeline` check, required) |
| 2 lint | applicable | `ruff check` via `make verify` (required); zizmor on workflow changes (`security.yml`, required since 2026-08-21); terraform fmt + validate (`iac.yml`, required since 2026-08-21) |
| 3 type | applicable | `mypy` strict via `make verify` (required) |
| 4 test | applicable | pytest, branch coverage gate 92% (required); browser e2e (`e2e` check, required) |
| 5 security | applicable | gitleaks + Semgrep + pip-audit/osv (required checks); dependency review on PRs (required since 2026-08-21); CodeQL python, actions, and javascript (required; javascript since 2026-08-21); Trivy scans of both Lambda images (required since 2026-08-21); TruffleHog weekly |
| 6 a11y | applicable | axe/pa11y-ci (`axe` check, required); AAA token contrast gate in `make verify`; Lighthouse accessibility ≥ 0.95 gates the Pages deploy |
| 7 perf | applicable (lab budgets) | Lighthouse budgets gate the Pages deploy: performance ≥ 0.90, FCP ≤ 2000 ms, LCP ≤ 2750 ms, CLS ≤ 0.1, TBT ≤ 200 ms (`lighthouserc.json`), asserted as a true median of five runs. The LCP figure moved from 2500 ms on 2026-08-10 with the FCP gate added alongside it; see [ADR 0045](decisions/0045-lighthouse-lcp-budget-and-warmup-run.md). Load testing is N/A: the product is a static site with no server latency contract; the only hosted compute (`infra/`) is unapplied. |
| 8 responsible | applicable (civic repo) | Double-opt-in consent gate on alerts (tested in `tests/test_notify.py`); fail-closed comparison rules; neutral no-shaming framing is a tested product rule; `docs/audits/` pack. AI-evaluation gates are N/A: no AI system exists in the product path, and AI-generated fixes in the graded path are an explicitly cut item (`docs/roadmap.md`). |
| 9 build | applicable | wheel build in CI; SBOM, VEX, provenance attestation, and signed manifest attach on tag via `release-sign.yml` |

## Pipeline metrics ledger (CI-CD-STANDARD §10)

State read 2026-07-17 and again 2026-10-02. "Code scanning" means the weekly
in-repo `openssf-scorecard.yml` run, which uploads SARIF so regressions surface
next to CodeQL findings.

| Metric | Target | Measured by | State 2026-07-17 | State 2026-10-02 |
|---|---|---|---|---|
| Token-Permissions | 10/10 | code scanning | no open alert | no open alert |
| Pinned-Dependencies | ≥ 9/10 | code scanning | no open alert | no open alert |
| Branch-Protection | ≥ 8/10 | scorecard CLI | 8/10 (protection active, not maximal) | 8/10; the CLI warns that protection does not apply to admins and that only one approval is required |
| Dangerous-Workflow | 10/10 | code scanning | no open alert | no open alert |
| Cloud auth via OIDC | 100% | workflow review | `configure-aws-credentials` with `role-to-assume`; no long-lived cloud keys in workflows | holds: all 9 `configure-aws-credentials` steps, across 6 workflows, use `role-to-assume`; no access-key inputs |
| zizmor on workflow PRs | 0 high/critical | `security.yml` job | wired | wired, and a required check since 2026-08-21 |
| `make verify` ≡ CI | identical | `ci.yml` invokes `make verify` | holds | holds (`make -C .. verify` in the `pipeline` job) |
| Deploy reviewer gate | env + ≥ 1 reviewer | environments API | **absent**: `github-pages` has a branch policy but no required reviewer (owner-only setting; see the dated environments audit note under `docs/audits/`) | **still absent**: the only protection rule on `github-pages` is the branch policy |

Code scanning also held seven open CodeQL alerts on 2026-10-02, which the
2026-07-17 read did not list. Six are `py/incomplete-url-substring-sanitization`
in test files (`pipeline/tests/test_vendors.py`, `test_vendor_quality.py`,
`test_directory.py`), open since 2026-07-08. One is
`js/clear-text-storage-of-sensitive-data` at `web/src/app.js` line 466, open
since 2026-08-26. None has been triaged in this file yet.

## DORA snapshot, 2026-10-02 (QM-11)

Measured 2026-10-02 over the trailing 30 days (2026-09-02 to 2026-10-02), from
`gh` run and PR data, the same way as the 2026-07-17 snapshot below.

- **Deployment frequency:** continuous. Of the last 100 "Deploy site" runs
  (2026-09-09 to 2026-10-02, all triggered by pushes to `main`), 73 succeeded,
  3 failed, 23 were canceled, and 1 was still pending when read. The intraday
  refresh over the last 7 days: 56 runs, 55 success, 0 failure, 0 canceled,
  1 in progress. The three-hour cron schedules 56 runs a week, which is what
  ran. The July note below expected about a third of its 87 runs, roughly 29,
  so that estimate was low.
- **Lead time for changes:** across the last 30 merged PRs (2026-09-17 to
  2026-10-02), median 90 minutes and mean 14.3 hours from PR open to merge.
  The mean is pulled up by #476, which stayed open 12.4 days while `main` was
  red (below). No PR merged between 2026-09-19 15:24 UTC and 2026-10-02
  01:51 UTC.
- **Change failure rate:** one revert in the window. #481, merged 2026-10-02,
  reverted three commits (ea1f9e7, 6c42a70, d9994f5) pushed straight to `main`
  without a pull request on 2026-09-20. 6c42a70 left an undefined name in
  `cli.py`, so the CI `pipeline` check failed on every `main` push from
  2026-09-20 14:38 UTC until the revert, and on every PR opened from `main`.
  Separately, the `security` workflow's dependency audit failed on every `main`
  push from 2026-09-29 18:00 UTC (osv-scanner on oauthlib 3.3.1, and later
  pip-audit on urllib3 2.7.0) until #482 merged at 05:04 UTC on 2026-10-02. It
  had passed on `main` through 2026-09-29 15:14 UTC. The Trivy image scans
  (`container-scan`) were red on `main` from 2026-09-30 03:39 UTC until the
  same PR. Then #486 merged 55 seconds after it was opened, before its required
  checks finished; its new fix title broke the structural SEO contract, which
  failed the `axe` check and the Deploy site run on `main` until #487 shortened
  the title 30 minutes later. 3 of the last 100 deploy runs failed.
- **Time to restore:** still not instrumented as a metric. Read from run
  history this window: each of the 3 failed deploys was followed by a
  successful one within 34 minutes. Red checks on `main` took longer to
  restore: about 11.5 days for `pipeline`, about 2.5 days for the dependency
  audit, about 2 days for the Trivy scans, and 30 minutes for the SEO contract.
  The site kept publishing data through the intraday refresh throughout, so
  these were delivery-path outages, not site outages.

Context for scale: 121 PRs merged to `main` in the window (UTC dates
2026-09-02 through 2026-10-02), plus the three direct pushes above.

## DORA snapshot, 2026-Q3 to date (QM-11)

Measured 2026-07-17 over the trailing 30 days (2026-06-17 to 2026-07-17), from
`gh` run and PR data. Solo-maintainer, agent-assisted numbers, recorded as
they are.

- **Deployment frequency:** continuous. The site redeploys on merge and on the
  intraday refresh; of the last 100 "Deploy site" runs, 89 succeeded, 9 failed,
  2 were canceled. The intraday refresh over the last 7 days: 78 success,
  8 failure, 1 canceled. Those counts were recorded while the refresh ran
  hourly; it moved to every three hours in 2026-08 (ADR 0010), so the next
  window's run counts will be about a third of these.
- **Lead time for changes:** across the last 30 merged PRs, median 6 minutes
  and mean 54 minutes from PR open to merge. PRs open pre-verified in this
  workflow, so this measures the merge path, not development time.
- **Change failure rate:** no merge to `main` was reverted in the window
  (0 revert commits). 9 of the last 100 deploy runs failed; the intraday
  cadence supersedes a failed deploy within three hours.
- **Time to restore:** not instrumented as a metric yet. The watchdog workflow
  surfaces failed scheduled runs, and the practical restore bound for the site
  is the next intraday refresh, so at most three hours. Recording a measured
  value is future work, not a claim.

Context for scale: 119 PRs merged in the window.

## OpenSSF Scorecard report, 2026-10-02 (SEC-38)

Run 2026-10-02 with scorecard CLI v5.5.0 against commit `370e5107cc7`, the same
method as the 2026-07-17 run against `ad70cbc606a`. Aggregate: 6.1/10, up from
5.5. The public securityscorecards.dev API has no entry for this repository
(HTTP 404), because the in-repo workflow runs with `publish_results: false`, so
the CLI run is the only aggregate available. The same four checks as in July
returned "inconclusive" (-1) because the CLI could not enumerate this
artifact-heavy repository's files remotely; for those, the weekly in-repo run
feeding code scanning is authoritative. Its open alerts on 2026-07-17 were
Branch-Protection, CII-Best-Practices, Code-Review, Dependency-Update-Tool,
Fuzzing, and Maintained. On 2026-10-02 they are the same minus Maintained,
which closed at 03:36 UTC that day. A SAST alert first raised 2026-07-09 also
closed on 2026-10-02; it is not on the July list, and the alerts API does not
show whether it was open on 2026-07-17. A CI-Tests alert was open from
2026-09-05 to 2026-09-14.

| Check | 2026-07-17 | 2026-10-02 | Note (2026-10-02) |
|---|---|---|---|
| Binary-Artifacts | 10 | 10 | none in repo |
| Branch-Protection | 8 | 8 | ruleset active; not maximal. The CLI also reports a required code-owner review with no CODEOWNERS file, but `.github/CODEOWNERS` exists; this is the same remote file-listing limit. |
| CI-Tests | 10 | 10 | 8/8 recent merged PRs CI-checked (15/15 in July) |
| CII-Best-Practices | 0 | 0 | no badge pursued; the decision deferred in July is still open |
| Code-Review | 0 | 0 | 0 of the last 30 changesets approved. Solo maintainer; agent PRs are reviewed by an independent reviewer before merge, which this check cannot see. The two-human-reviewer requirement carries the documented solo-maintainer exception in `docs/RESPONSIBLE-TECH-AUDITS.md`. The three direct pushes of 2026-09-20 had no review of any kind. |
| Contributors | 3 | 3 | single maintainer, expected |
| Dangerous-Workflow | inconclusive (CLI) | inconclusive (CLI) | no open code-scanning alert |
| Dependency-Update-Tool | 0 | 0 | `renovate.json` is committed at the root, yet both the CLI and the in-repo run report no tool, and no Renovate or Dependabot PR has ever been opened here. Whether the Renovate app is installed is still an owner-side question this pass could not verify. |
| Fuzzing | 0 | 0 | genuinely absent; the GTFS zip/CSV parsers are a plausible fuzz target, unscheduled |
| License | 10 | 10 | |
| Maintained | 0 | 10 | the repository object was recreated 2026-07-04 and turned 90 days old on 2026-10-02; 30 commits and 30 issue events in the last 90 days |
| Packaging | inconclusive (CLI) | inconclusive (CLI) | release pipeline publishes signed artifacts via `release-sign.yml` |
| Pinned-Dependencies | inconclusive (CLI) | inconclusive (CLI) | no open code-scanning alert |
| SAST | 10 | 10 | run on all commits |
| Security-Policy | 10 | 10 | |
| Signed-Releases | 8 | 4 | 3 of the last 5 releases signed. The two monthly dataset releases (`dataset-2026-07`, `dataset-2026-08`) carry no signature, and none of the five carries provenance. |
| Token-Permissions | inconclusive (CLI) | inconclusive (CLI) | no open code-scanning alert |
| Vulnerabilities | 10 | 10 | 0 known at the measured commit |

## Acceptance tests to features (QM-01 mapping)

A starter map from the browser acceptance suites in `pipeline/tests/e2e/` to
the user-facing claim each one holds in place. Unit and golden suites back the
scoring math itself (`test_score_corpus.py`, `test_properties.py`, and the
golden site fixtures pin the grade ladder and deterministic rendering).

| Suite | User-facing claim it exercises |
|---|---|
| `test_routes.py` | every SPA route renders real content; the boot spinner never persists |
| `test_parity.py` | the prerendered agency page and the SPA route show the same grade, category scores, and top-3 fixes |
| `test_failure.py` | a total artifact-fetch failure announces itself to assistive tech instead of spinning silently |
| `test_forms.py` | the public submit/subscribe/try forms recover from errors; mobile appearance controls work |
| `test_keyboard.py` | the WCAG 2.2 keyboard-operability claim in `docs/vpat.md`, as an executable check |
| `test_mobile.py` | mobile-first layout, 320 px reflow, and minimum target sizes across every page family |
| `test_locale.py` | locale-aware presentation (EN/ES) behaves in a real browser |
| `test_offline.py` | a visited page stays readable offline and labels itself as a saved copy |
| `test_service_horizon.py` | the legacy service-horizon fallback in the live JavaScript renderer |

Gaps this map makes visible: no browser suite exercises the alert email
content end to end (unit tests cover it), and cross-browser coverage is
Chromium-only. Both are recorded here as open, not silently skipped.
