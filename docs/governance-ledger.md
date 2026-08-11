# Governance ledger

Delivery-health and conformance measurements for this repository, per
CI-CD-STANDARD §10 and QUALITY-AND-METRICS-STANDARD. This file answers four
questions the roadmap does not: which CI stages apply here, what the pipeline
metrics currently measure, how delivery health looks this quarter, and what the
latest OpenSSF Scorecard run found. Audit findings closed by this file:
CICD-29, QM-11, SEC-38, and the mapping half of QM-01.

Every number below states its measurement date and method. Refresh cadence:
quarterly (next due 2026-10-17), and the Scorecard section monthly.

## CI stage declarations (CICD-29)

CI-CD-STANDARD §1 defines nine pipeline stages. Stages 1 through 5 are
mandatory everywhere; 6 through 8 must be declared applicable or N/A with a
reason. As of 2026-07-17 the `main` branch ruleset
(`main-required-checks-and-review`, enforcement: active) requires nine status
checks, a pull request, and linear history, so "merge-blocking" below means
enforced by the ruleset, not aspirational.

| Stage | Declaration | Where enforced |
|---|---|---|
| 1 format | applicable | `ruff format --check` via `make verify` (`ci.yml` `pipeline` check, required) |
| 2 lint | applicable | `ruff check` via `make verify` (required); zizmor on workflow changes (`security.yml`) |
| 3 type | applicable | `mypy` strict via `make verify` (required) |
| 4 test | applicable | pytest, branch coverage gate 92% (required); browser e2e (`e2e` check, required) |
| 5 security | applicable | gitleaks + Semgrep + pip-audit/osv (required checks); CodeQL python and actions (required); TruffleHog weekly; trivy container scan |
| 6 a11y | applicable | axe/pa11y-ci (`axe` check, required); AAA token contrast gate in `make verify`; Lighthouse accessibility ≥ 0.95 gates the Pages deploy |
| 7 perf | applicable (lab budgets) | Lighthouse budgets gate the Pages deploy: performance ≥ 0.90, FCP ≤ 2000 ms, LCP ≤ 2750 ms, CLS ≤ 0.1, TBT ≤ 200 ms (`lighthouserc.json`), asserted as a true median of five runs. The LCP figure moved from 2500 ms on 2026-08-10 with the FCP gate added alongside it; see [ADR 0045](decisions/0045-lighthouse-lcp-budget-and-warmup-run.md). Load testing is N/A: the product is a static site with no server latency contract; the only hosted compute (`infra/`) is unapplied. |
| 8 responsible | applicable (civic repo) | Double-opt-in consent gate on alerts (tested in `tests/test_notify.py`); fail-closed comparison rules; neutral no-shaming framing is a tested product rule; `docs/audits/` pack. AI-evaluation gates are N/A: no AI system exists in the product path, and AI-generated fixes in the graded path are an explicitly cut item (`docs/roadmap.md`). |
| 9 build | applicable | wheel build in CI; SBOM, VEX, provenance attestation, and signed manifest attach on tag via `release-sign.yml` |

## Pipeline metrics ledger (CI-CD-STANDARD §10)

State read 2026-07-17. "Code scanning" means the weekly in-repo
`openssf-scorecard.yml` run, which uploads SARIF so regressions surface next to
CodeQL findings.

| Metric | Target | Measured by | State 2026-07-17 |
|---|---|---|---|
| Token-Permissions | 10/10 | code scanning | no open alert |
| Pinned-Dependencies | ≥ 9/10 | code scanning | no open alert |
| Branch-Protection | ≥ 8/10 | scorecard CLI | 8/10 (protection active, not maximal) |
| Dangerous-Workflow | 10/10 | code scanning | no open alert |
| Cloud auth via OIDC | 100% | workflow review | `configure-aws-credentials` with `role-to-assume`; no long-lived cloud keys in workflows |
| zizmor on workflow PRs | 0 high/critical | `security.yml` job | wired |
| `make verify` ≡ CI | identical | `ci.yml` invokes `make verify` | holds |
| Deploy reviewer gate | env + ≥ 1 reviewer | environments API | **absent**: `github-pages` has a branch policy but no required reviewer (owner-only setting; see the dated environments audit note under `docs/audits/`) |

## DORA snapshot, 2026-Q3 to date (QM-11)

Measured 2026-07-17 over the trailing 30 days (2026-06-17 to 2026-07-17), from
`gh` run and PR data. Solo-maintainer, agent-assisted numbers, recorded as
they are.

- **Deployment frequency:** continuous. The site redeploys on merge and on the
  intraday refresh; of the last 100 "Deploy site" runs, 89 succeeded, 9 failed,
  2 were cancelled. The intraday refresh over the last 7 days: 78 success,
  8 failure, 1 cancelled. Those counts were recorded while the refresh ran
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

## OpenSSF Scorecard report, 2026-07-17 (SEC-38)

Run with scorecard CLI v5.5.0 against commit `ad70cbc606a`. Aggregate: 5.5/10.
Four checks returned "inconclusive" (-1) because the CLI could not enumerate
this artifact-heavy repository's files remotely; for those, the weekly in-repo
run feeding code scanning is authoritative, and its currently open alerts are
exactly: Branch-Protection, CII-Best-Practices, Code-Review,
Dependency-Update-Tool, Fuzzing, Maintained.

| Check | Score | Note |
|---|---|---|
| Binary-Artifacts | 10 | none in repo |
| Branch-Protection | 8 | ruleset active; not maximal |
| CI-Tests | 10 | 15/15 recent merged PRs CI-checked |
| CII-Best-Practices | 0 | no badge pursued; decide at next review |
| Code-Review | 0 | solo maintainer; agent PRs are reviewed by an independent reviewer before merge, which this check cannot see. The two-human-reviewer requirement carries the documented solo-maintainer exception in `docs/RESPONSIBLE-TECH-AUDITS.md`. |
| Contributors | 3 | single maintainer, expected |
| Dangerous-Workflow | inconclusive (CLI) | no open code-scanning alert |
| Dependency-Update-Tool | 0 | `renovate.json` is committed at the root, yet both the CLI and the in-repo run report no tool. Whether the Renovate app is installed on the repository is an owner-side question this pass could not verify. |
| Fuzzing | 0 | genuinely absent; the GTFS zip/CSV parsers are a plausible fuzz target, unscheduled |
| License | 10 | |
| Maintained | 0 | the repository object was recreated 2026-07-04, and the check scores any repo under 90 days old as zero; misleading here |
| Packaging | inconclusive (CLI) | release pipeline publishes signed artifacts via `release-sign.yml` |
| Pinned-Dependencies | inconclusive (CLI) | no open code-scanning alert |
| SAST | 10 | run on all commits |
| Security-Policy | 10 | |
| Signed-Releases | 8 | 5 of 5 releases signed |
| Token-Permissions | inconclusive (CLI) | no open code-scanning alert |
| Vulnerabilities | 10 | 0 known |

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
