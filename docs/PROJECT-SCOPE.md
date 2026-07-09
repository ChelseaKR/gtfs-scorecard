# Project Scope

Last reviewed: 2026-07-08. Base branch: `main`.

This file is a plain-language map of the project as it exists on `main`. It does not replace the README, roadmap, audit docs, or source comments. It points to them so a reviewer can see the whole shape without reading every file first.

## What This Project Is

GTFS Scorecard measures public transit feed quality and publishes daily scorecards. It combines validator output, freshness, rider-facing completeness, realtime checks, accessibility, equity review, and public pages for agencies and advocates.

## Who It Serves

- Transit agencies that need to see feed problems before riders feel them.
- State DOTs, associations, and advocates comparing data quality across feeds.
- Maintainers running scheduled scoring, site generation, and data releases.

## What It Covers

- Agency configuration and daily artifact generation.
- Validator, freshness, accessibility, equity, realtime, and NTD-related checks.
- GitHub Actions for scoring, Pages, dataset release, discovery, and watchdog tasks.
- Public docs for methodology, onboarding, rule pages, and standards.
- Data artifacts, badges, conformance files, and generated outputs.

## How It Is Put Together

- agencies.yaml defines tracked feeds.
- data/artifacts/ stores historical score outputs.
- docs/ explains scoring, onboarding, methodology, and standards.
- scripts and package files drive scoring and site generation.
- Workflows run daily refresh, pages publish, realtime monitor, a11y, and security gates.

Observed source and operations surfaces:

- `Makefile`
- `action.yml`
- `infra/`
- `pipeline/`
- `scripts/`
- `web/`

GitHub workflow files checked:

- `.github/workflows/a11y.yml`
- `.github/workflows/canada-equity.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/codeql.yml`
- `.github/workflows/dataset-release.yml`
- `.github/workflows/discover.yml`
- `.github/workflows/e2e.yml`
- `.github/workflows/equity.yml`
- `.github/workflows/mutation.yml`
- `.github/workflows/onboard.yml`
- `.github/workflows/openssf-scorecard.yml`
- `.github/workflows/otp-qa.yml`
- `.github/workflows/pages.yml`
- `.github/workflows/refresh.yml`
- `.github/workflows/rt-archive.yml`
- `.github/workflows/rt-monitor.yml`
- `.github/workflows/scorecard.yml`
- `.github/workflows/security.yml`
- `.github/workflows/standards-pin.yml`
- `.github/workflows/tiles.yml`
- `.github/workflows/trufflehog.yml`
- `.github/workflows/validator-canary.yml`
- `.github/workflows/watchdog.yml`

## Trust Boundaries

- The scorecard states what a feed contains; it does not certify legal compliance.
- No realtime feed is treated as not published rather than punished by default.
- Generated artifacts should carry validator versions and dates because transit rules move.

## Outside This Scope

- It does not speak for FTA, NTD, or an agency vendor.
- Scores depend on available public feeds and the rule versions in use.
- Large artifact history is data output, not hand-authored documentation.

## Docs And Evidence Checked

This pass checked 131 hand-authored doc or metadata files, 102 test files, and 23 workflow files on `main`. The count excludes vendored provider licenses, dependency folders, generated cache files, and large generated artifact history.

Large content groups were counted rather than listed file by file:

- `docs/standards/`: 12 files

Primary docs checked:

- `.github/ISSUE_TEMPLATE/accessibility.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `CHANGELOG.md`
- `CITATION.cff`
- `CLAUDE.md`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `README.md`
- `SECURITY.md`
- `docs/INTERACTIVITY-ROADMAP.md`
- `docs/OTP_WIRING_PATTERN.md`
- `docs/RESEARCH-ROADMAP.md`
- `docs/SIDE_BY_SIDE_COMPARE_DESIGN.md`
- `docs/USER-RESEARCH.md`
- `docs/accessibility-testing.md`
- `docs/accessibility.md`
- `docs/add-your-agency.md`
- `docs/api.md`
- `docs/ci-action.md`
- `docs/conformance.md`
- `docs/crosswalk.md`
- `docs/decisions/0001-validator-runtime.md`
- `docs/decisions/0002-artifacts-to-s3.md`
- `docs/decisions/0003-fan-out-compute.md`
- `docs/decisions/0004-opt-in-alerts.md`
- `docs/decisions/0005-competitive-positioning.md`
- `docs/decisions/0006-accessibility-sub-score.md`
- `docs/decisions/0007-gtfs-flex-awareness.md`
- `docs/decisions/0008-fares-v2-awareness.md`
- `docs/decisions/0009-pathways-levels-awareness.md`
- `docs/decisions/0010-update-cadence.md`
- `docs/decisions/0011-mobility-feed-api-reuse.md`
- `docs/decisions/0012-realtime-monitoring-cron.md`
- `docs/decisions/0013-static-public-api.md`
- `docs/decisions/0014-routing-qa-without-otp.md`
- `docs/decisions/0015-equity-overlay-state-level.md`
- `docs/decisions/0016-ntd-id-alignment.md`
- `docs/decisions/0017-persona-surfaces.md`
- `docs/decisions/0018-national-rt-and-ntd-crosswalk.md`
- `docs/decisions/0019-national-problems-kb.md`
- `docs/decisions/0020-national-quality-trend.md`
- `docs/decisions/0021-ridership-weighting.md`
- `docs/decisions/0022-equity-choropleth.md`
- `docs/decisions/0023-national-all-routes-pmtiles.md`
- `docs/decisions/0024-validator-rule-links.md`
- `docs/decisions/0025-access-to-opportunity-scope.md`
- `docs/decisions/0026-internationalization.md`
- `docs/decisions/0027-canada-equity-cimd.md`
- `docs/decisions/0028-global-south-pilot.md`
- `docs/decisions/0029-instant-score-funnel.md`
- `docs/decisions/0030-data-plane-history-remediation.md`
- `docs/decisions/0030-honesty-primitives-standard.md`
- `docs/decisions/0030-signage-visual-identity.md`
- `docs/decisions/0031-observability-tier.md`
- Plus 76 more files in the same inventory.

Representative test files checked:

- `pipeline/tests/e2e/test_failure.py`
- `pipeline/tests/e2e/test_keyboard.py`
- `pipeline/tests/e2e/test_parity.py`
- `pipeline/tests/e2e/test_routes.py`
- `pipeline/tests/test_access.py`
- `pipeline/tests/test_accessibility.py`
- `pipeline/tests/test_adhoc.py`
- `pipeline/tests/test_adoption.py`
- `pipeline/tests/test_agencies.py`
- `pipeline/tests/test_alerts.py`
- `pipeline/tests/test_anomaly.py`
- `pipeline/tests/test_archive.py`
- `pipeline/tests/test_atomfeed.py`
- `pipeline/tests/test_autofix.py`
- `pipeline/tests/test_badge.py`
- `pipeline/tests/test_cadence.py`
- `pipeline/tests/test_canary.py`
- `pipeline/tests/test_cemv.py`
- `pipeline/tests/test_cimd.py`
- `pipeline/tests/test_cli.py`
- `pipeline/tests/test_cli_skip.py`
- `pipeline/tests/test_completeness.py`
- `pipeline/tests/test_conformance.py`
- `pipeline/tests/test_dataset.py`
- `pipeline/tests/test_directory.py`
- `pipeline/tests/test_effort_calibration.py`
- `pipeline/tests/test_equity.py`
- `pipeline/tests/test_fares.py`
- `pipeline/tests/test_fares_v2.py`
- `pipeline/tests/test_feedapi.py`
- `pipeline/tests/test_feeddiff.py`
- `pipeline/tests/test_fetch.py`
- `pipeline/tests/test_findings_national.py`
- `pipeline/tests/test_fixlog.py`
- `pipeline/tests/test_flex.py`
- `pipeline/tests/test_flex_completeness.py`
- `pipeline/tests/test_gbfs.py`
- `pipeline/tests/test_generated_constants.py`
- `pipeline/tests/test_geo.py`
- `pipeline/tests/test_google_gate.py`
- `pipeline/tests/test_gtfs.py`
- `pipeline/tests/test_infra_handlers.py`
- `pipeline/tests/test_lapse_risk.py`
- `pipeline/tests/test_lint.py`
- `pipeline/tests/test_liveness.py`
- Plus 57 more test files.

## Validation Notes

For this docs PR, validation means the scope file was generated from the clean `origin/main` worktree, reviewed against repo metadata and docs inventory, and checked with `git diff --check`. Project test suites are still the authority for code behavior, because this PR changes documentation only.
