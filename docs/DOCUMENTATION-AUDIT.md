# Documentation Audit

Last reviewed: 2026-07-08; corrected in review 2026-07-09. Base branch: `main`.

> **Review correction (2026-07-09).** The original sweep's link checker ran on
> a case-insensitive filesystem, so it passed two links in `docs/README.md`
> (`ROADMAP.md`, `ACCESSIBILITY.md`) that resolve to nothing on GitHub's
> case-sensitive hosting; both are fixed. The sweep also edited the vendored
> `docs/standards/README.md`, which is pinned byte-identical to
> `ChelseaKR/portfolio-standards` tag `v1.0.1` and must never be edited
> in-repo (DOC-03; `standards-pin.yml` enforces this once its token exists).
> That edit is reverted here. Its two relative links (`AUDIT-2026-06-21.md`,
> `IMPROVEMENTS-BACKLOG.md`) resolve in the upstream repo, not this one; that
> is a property of vendoring, is excluded from this audit's unresolved-link
> count, and any fix belongs upstream. A case-sensitive re-check on
> 2026-07-09 over root Markdown, `.github` templates, and `docs/**` minus the
> vendored `docs/standards/` found 208 relative links, 0 unresolved after
> these fixes.

This audit records the documentation sweep and remediation loop for this repository. It checks the docs as a system: entry points, root-level process and legal files, project scope, setup and validation notes, safety and privacy posture, architecture and planning docs, local links, and the places where code, tests, workflows, and docs meet.

## Audit Results

| Area | Result | Evidence |
| --- | --- | --- |
| Entry docs | pass | `README.md` present |
| Security/process docs | pass | CONTRIBUTING.md, SECURITY.md, CHANGELOG.md |
| Architecture/planning docs | pass | 2 architecture/interface docs; 17 planning/research docs |
| Safety/privacy/audit docs | pass | 5 safety/privacy/accessibility/audit docs |
| Validation surface | pass | 102 test files; 23 workflow files |
| Local doc links | pass | 208 relative links re-checked case-sensitively 2026-07-09 (vendored `docs/standards/` excluded); 0 unresolved |

## Root-Level Documentation Audit

This section covers hand-authored documentation at the repository root and root-adjacent GitHub templates. It is separate from the `docs/` inventory so README, process, legal, release, and project-specific root files do not get hidden inside the larger docs tree.

| Surface | Result | Evidence |
| --- | --- | --- |
| Root README | pass | Present: `README.md` |
| Root process docs | pass | Present: `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md` |
| Root legal, citation, and conduct docs | pass | Present: `LICENSE`, `NOTICE`, `CITATION.cff`, `CODE_OF_CONDUCT.md` |
| Other root project docs | info | `CLAUDE.md` |
| Root-adjacent GitHub templates | pass | `.github/PULL_REQUEST_TEMPLATE.md`, `.github/CODEOWNERS`, `.github/ISSUE_TEMPLATE/accessibility.md` |
| Root/template doc links | pass | 63 root-level/template links checked; 0 unresolved |

Root-level files checked:

- `CHANGELOG.md`
- `CITATION.cff`
- `CLAUDE.md`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `NOTICE`
- `README.md`
- `SECURITY.md`

Root-adjacent template files checked:

- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/CODEOWNERS`
- `.github/ISSUE_TEMPLATE/accessibility.md`

## Remediation In This PR

- Added missing root-level remediation docs found by the audit loop, including legal, conduct, contribution, or security files where absent.
- Added `docs/PROJECT-SCOPE.md` as the plain-language project and boundary map.
- Added this audit record so future doc changes have a dated baseline.
- Added or refreshed the docs index so scope, audit, and primary docs are easy to find.
- Fixed or added root/doc remediation files: `.github/PULL_REQUEST_TEMPLATE.md`, `NOTICE`.
- Did **not** keep the sweep's edit to `docs/standards/README.md`: that file is vendored and pinned; the edit was reverted in review (see the correction note above).

## Repo Surfaces Checked

Package and workspace metadata:

- `pipeline/pyproject.toml` (the Python package and single version source; see `README.md` Versioning). The web frontend is vanilla JS with no package manifest.

Source and operations surfaces seen at the repo root:

- `data/`
- `infra/`
- `Makefile`
- `pipeline/`
- `scripts/`
- `web/`

Workflow files checked:

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

## Documentation Inventory

| Category | Count | Representative files |
| --- | ---: | --- |
| architecture and interfaces | 2 | `docs/api.md`, `docs/decisions/0013-static-public-api.md` |
| entry points and repo process | 11 | `.github/CODEOWNERS`, `.github/ISSUE_TEMPLATE/accessibility.md`, `.github/PULL_REQUEST_TEMPLATE.md`, `CHANGELOG.md`, `CITATION.cff`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `LICENSE`, plus 3 more |
| operations and release | 3 | `docs/deploy.md`, `docs/fixes/fast_travel_between_consecutive_stops.md`, `docs/fixes/fast_travel_between_far_stops.md` |
| other docs | 94 | `CLAUDE.md`, `docs/OTP_WIRING_PATTERN.md`, `docs/PROJECT-SCOPE.md`, `docs/README.md`, `docs/SIDE_BY_SIDE_COMPARE_DESIGN.md`, `docs/add-your-agency.md`, `docs/ci-action.md`, `docs/conformance.md`, plus 86 more |
| planning and research | 17 | `docs/INTERACTIVITY-ROADMAP.md`, `docs/RESEARCH-ROADMAP.md`, `docs/USER-RESEARCH.md`, `docs/decisions/0030-data-plane-history-remediation.md`, `docs/expansion-ideation-2026-07.md`, `docs/expansion-research-2026-07.md`, `docs/expansion-research.md`, `docs/feature-roadmap.md`, plus 9 more |
| safety, privacy, accessibility, and audits | 5 | `docs/DOCUMENTATION-AUDIT.md`, `docs/accessibility-testing.md`, `docs/accessibility.md`, `docs/decisions/0006-accessibility-sub-score.md`, `docs/standards-proposal-2026-07-05-accessibility.md` |
| grouped generated/source content | 12 | `docs/standards/` counted as a content group, not listed file by file |
| grouped generated/source content | 41 | `pipeline/tests/fixtures/golden_site/` counted as a content group, not listed file by file |
| grouped generated/source content | 1 | `web/agencies/` counted as a content group, not listed file by file |
| grouped generated/source content | 4532 | `web/agency/` counted as a content group, not listed file by file |
| grouped generated/source content | 1 | `web/data/` counted as a content group, not listed file by file |

Full hand-authored doc inventory checked by this pass:

- `.github/CODEOWNERS`
- `.github/ISSUE_TEMPLATE/accessibility.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `CHANGELOG.md`
- `CITATION.cff`
- `CLAUDE.md`
- `CODE_OF_CONDUCT.md`
- `CONTRIBUTING.md`
- `LICENSE`
- `NOTICE`
- `README.md`
- `SECURITY.md`
- `docs/DOCUMENTATION-AUDIT.md`
- `docs/INTERACTIVITY-ROADMAP.md`
- `docs/OTP_WIRING_PATTERN.md`
- `docs/PROJECT-SCOPE.md`
- `docs/README.md`
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
- `docs/decisions/0032-repo-layout.md`
- `docs/decisions/0033-branch-protection-ruleset.md`
- `docs/deploy.md`
- `docs/expansion-ideation-2026-07.md`
- `docs/expansion-research-2026-07.md`
- `docs/expansion-research.md`
- `docs/expansion.md`
- `docs/feature-roadmap.md`
- `docs/feed-discovery.md`
- `docs/feed-supersessions.md`
- `docs/feeds.md`
- `docs/fixes/README.md`
- `docs/fixes/expired_calendar.md`
- `docs/fixes/fast_travel_between_consecutive_stops.md`
- `docs/fixes/fast_travel_between_far_stops.md`
- `docs/fixes/feed_expiration_date30_days.md`
- `docs/fixes/feed_expiration_date7_days.md`
- `docs/fixes/invalid_currency_amount.md`
- `docs/fixes/missing_feed_contact_email_and_url.md`
- `docs/fixes/missing_recommended_field.md`
- `docs/fixes/missing_recommended_file.md`
- `docs/fixes/missing_required_column.md`
- `docs/fixes/missing_timepoint_value.md`
- `docs/fixes/mixed_case_recommended_field.md`
- `docs/fixes/route_color_contrast.md`
- `docs/fixes/scorecard_feed_expired.md`
- `docs/fixes/scorecard_feed_expiring_soon.md`
- `docs/fixes/scorecard_flex_no_booking_rules.md`
- `docs/fixes/scorecard_missing_feed_info_dates.md`
- `docs/fixes/scorecard_missing_headsigns.md`
- `docs/fixes/scorecard_no_fare_data.md`
- `docs/fixes/scorecard_no_feed_contact.md`
- `docs/fixes/scorecard_rt_service_alerts_unreachable.md`
- `docs/fixes/scorecard_rt_trip_coverage.md`
- `docs/fixes/scorecard_rt_trip_updates_unreachable.md`
- `docs/fixes/scorecard_rt_vehicle_positions_unreachable.md`
- `docs/fixes/scorecard_station_no_pathways.md`
- `docs/fixes/scorecard_stop_names_all_caps.md`
- `docs/fixes/scorecard_wheelchair_accessible_unknown.md`
- `docs/fixes/scorecard_wheelchair_boarding_unknown.md`
- `docs/fixes/service_has_no_active_day_of_the_week.md`
- `docs/fixes/service_window_outside_feed_period.md`
- `docs/fixes/stop_too_far_from_shape.md`
- `docs/fixes/stop_too_far_from_shape_using_user_distance.md`
- `docs/fixes/stop_without_stop_time.md`
- `docs/fixes/trip_coverage_not_active_for_next7_days.md`
- `docs/fixes/trip_distance_exceeds_shape_distance_below_threshold.md`
- `docs/fixes/unknown_column.md`
- `docs/fixes/unknown_file.md`
- `docs/fixes/unused_shape.md`
- `docs/follow-ups.md`
- `docs/ideation/01-deep-dive.md`
- `docs/ideation/02-large-scale-fixes.md`
- `docs/ideation/03-expansions.md`
- `docs/ideation/04-impact-and-sequencing.md`
- `docs/ideation/README.md`
- `docs/lint-complexity-ratchet.md`
- `docs/listing-policy.md`
- `docs/mcp.md`
- `docs/mutation-testing.md`
- `docs/product-roadmap.md`
- `docs/roadmap.md`
- `docs/rubric.md`
- `docs/section-508-plan.md`
- `docs/service-plan.md`
- `docs/standards-conformance-gaps.md`
- `docs/standards-contribution/HONESTY-AS-A-FEATURE.md`
- `docs/standards-proposal-2026-07-05-accessibility.md`
- `docs/supersession-flagging.md`
- `docs/vpat.md`
- `infra/README.md`
- `pipeline/tests/goldens/robots.txt`
- `web/llms.txt`
- `web/robots.txt`

Grouped content counts:

- `docs/standards/`: 12 files
- `pipeline/tests/fixtures/golden_site/`: 41 files
- `web/agencies/`: 1 files
- `web/agency/`: 4532 files
- `web/data/`: 1 files

## Link Check

- Original sweep (2026-07-08): 328 local links checked in authored Markdown docs, case-insensitively.
- Review re-check (2026-07-09): 208 relative links checked case-sensitively across root Markdown, `.github` templates, and `docs/**` excluding the vendored `docs/standards/`; the count differs from the original sweep because the scopes differ (the re-check excludes vendored standards and counts only relative links, not anchors or external URLs).
- Unresolved authored-doc links after remediation and review fixes: 0.
- Root-level/template unresolved links after remediation: 0.

Audit scope notes:

- Generated sites, deployed app routes, raw third-party HTML captures, and golden fixture websites were inventoried as product or data surfaces but excluded from authored-doc link failure counts.
- The vendored `docs/standards/*.md` files are pinned byte-identical to upstream and excluded from in-repo link remediation; their relative links resolve in `ChelseaKR/portfolio-standards`.
- Grouped content directories are counted rather than listed file by file, so they stay visible without flooding the inventory.

## Validation Notes

- The audit was generated from a clean worktree based on `origin/main` for this PR branch.
- Ran a local relative-link check over hand-authored Markdown and MDX docs.
- Ran an explicit root-level documentation presence and link check for README, process, legal, project, and template docs.
- Ran `git diff --check` across the PR worktrees after remediation.
- Product test suites remain the authority for runtime behavior; this PR changes documentation only.
