# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/); this project
uses [SemVer](https://semver.org/) (see `README.md`'s Versioning section for
the declared public surface).

> **Known gap, found while writing this file (2026-07-05):** the `v1.0.0`
> and `v1` tags point at a commit (`0d8778530c...`, "make the scorer ref
> track the action version for the Marketplace") that is **not an ancestor
> of `main`'s current history** — `git merge-base --is-ancestor v1.0.0 HEAD`
> returns false, and a tree diff between the tag and `HEAD` touches over
> 28,000 files. The branch was evidently rewritten (rebased or
> history-squashed) at some point after the tag was cut, orphaning it. This
> is a real REL-07/REL-08 problem beyond what the 2026-07-05 audit named
> (lightweight/unsigned tags) — the tag doesn't just lack a signature, it no
> longer corresponds to reachable history. Recommended fix, for a human to
> decide and execute (not done here — retagging is a real git operation
> this remediation pass does not perform): cut a new annotated, signed point
> release (e.g. `v1.0.1` or `v1.1.0`) against current `main` as part of
> landing the real release pipeline (remediation P1-10), and treat `v1.0.0`
> as a permanently historical marker rather than trying to move it.
>
> **Resolved 2026-07-11:** done as recommended. `v1.1.0` is an annotated,
> signed tag on current `main`; the floating `v1` tag was moved to it;
> `v1.0.0` stays as a historical marker.

## [Unreleased]

## [1.2.0] - 2026-07-14

### Added
- Marketplace release metadata and a publication runbook for the composite GTFS
  quality gate, prepared for a protected `v1.2.0` tag and the floating `v1` tag.

### Changed
- Public coverage pages now focus on feeds that need attention and recent changes
  instead of ranking agencies from best to worst.
- Cross-feed comparisons exclude incompatible scoring profiles and duplicate feed
  records. Agency pages no longer present a national percentile as a performance
  judgment.
- Coverage totals now describe feed records or scorecards rather than implying each
  record is a distinct transit agency.
- Unitrans realtime copy now says its UmoIQ feeds require an API key and remain
  unmeasured here; it no longer says the agency publishes no realtime feed.
- Action documentation is prepared for the v1 line (`@v1` and the planned
  `@v1.2.0` release ref) instead of referencing a nonexistent v2 tag.

### Fixed
- Rubric-version copy no longer implies that every historical scorecard was computed
  with the current methodology.

## [1.1.0] - 2026-07-11

Cut from current `main` to re-anchor releases to reachable history:
`v1.0.0` was orphaned by a branch rewrite (see the note above) and stays as
a historical marker. The floating `v1` tag now points at this release. It
prepared the action for Marketplace submission, but the listing remained
unpublished; Marketplace publication is a v1.2.0 release step.

### Added
- Searchable, quality-gated fix library; canonical feed identity ledger;
  reviewed listing-claim/correction workflow; vendor evidence packets; fix
  outcome analytics; program campaign pages; and fair-comparison guardrails.
- GitHub Action gate controls, EXP-16 policy research materials, board-ready
  reports, and transparent project sponsorship documentation.
- Spanish-first `/es/` agency lookup backed by key-parity `en`/`es` locale
  catalogs, with explicit limits on what a scorecard certifies.
- Responsible-technology audit register and consequence, bias, privacy, and
  threat-model reviews; a release checklist; and a reproducible
  `make golden-refresh` command.
- CycloneDX SBOM/VEX release assets and build-provenance attestations.
- `scorecard report` (also `python -m scorecard_pipeline.report`): renders one
  agency's published scorecard as a single self-contained HTML file for a
  board packet or a grant application, printable to PDF, with an optional
  `--brand` YAML (name, logo, accent) so a state program or consultancy can
  put its name on reports for the agencies it supports. See
  `docs/board-report.md`.
- "Fixes shared across this group" section on `/program/<state>/` pages (#23).
- `docs/crosswalk.md` rendered as an on-site `/crosswalk/` page (#22).
- Fix-KB pages and validator rule links for the four highest-prevalence
  realtime gaps (#21).
- California Minimum GTFS Guidelines checklist on agency pages (#19).
- Neutral peer-distribution framing on per-state program pages (#17).
- "Expired over a year" findings split by whether the feed URL itself still
  answers (#16).
- Several more fix-KB gap closures for the most common validator findings
  (#15, #18).
- 2026-07-05 remediation pass (this change): restored the vendored
  `docs/standards/ACCESSIBILITY-STANDARD.md` to its pinned upstream state;
  added a `## Standards conformance` + `## Observability` + `## Versioning`
  section to `README.md`; reconciled `pipeline/pyproject.toml` /
  `CITATION.cff` / `server.json` to one version number with a `make verify`
  drift check; added dependency-audit (pip-audit + osv-scanner), CodeQL
  (python + actions), zizmor, TruffleHog, and OpenSSF Scorecard workflows;
  authored (not yet applied — see the workflow files) a branch-protection
  ruleset; this CHANGELOG and a wheel-build CI step.

### Fixed
- Container ingestion now rejects oversized or suspiciously compressed GTFS
  archives before Java starts. Both production images pass HIGH/CRITICAL Trivy
  scanning with reviewed, expiring VEX entries for unreachable upstream code.
- Standards pinning is self-contained and merge-blocking; Lighthouse now gates
  performance, LCP, CLS, and responsiveness as well as accessibility.
- Workflow shell lint is clean, generated pages are synchronized with the
  merged feature set, and Docker build context is reduced from roughly 400 MB
  to the source and pinned validator inputs actually needed.
- Badge embed's copied Markdown now names the agency and grade instead of
  the generic "GTFS data quality" (#24, and an earlier partial fix).
- `shapes_readiness` allowed in the artifact schema — was failing 100% of
  runs since the prior release that introduced it (#20).

## [1.0.0] - 2026-06-21

First tagged release (`v1`/`v1.0.0`). Summarized
rather than itemized commit-by-commit: the tag predates a history rewrite on
`main` (see the note above), so an exact commit list can't be reconstructed
from `git log` against current history. As of this tag, the repo shipped:

### Added
- The scoring pipeline (fetch → MobilityData validator → score → publish)
  covering Correctness, Freshness, Rider-experience completeness, and
  Realtime quality, with plain-language findings and "top 3 things to fix."
- The static frontend (agency picker, scorecard pages, trend charts) with a
  WCAG-AAA-targeted accessibility posture.
- The composite GitHub Action (`action.yml`) gating a caller's CI on feed
  grade/expiry, packaged for reuse as `ChelseaKR/gtfs-scorecard@v1`.
- NTD certification-readiness signals and the `agencies.yaml` scale-out path
  (grown to roughly 1,100 agencies nationally by 2026-07).
- Realtime drift/plausibility checks, embeddable grade badges, and rollup
  views across agency cohorts.

[Unreleased]: https://github.com/ChelseaKR/gtfs-scorecard/compare/v1.2.0...HEAD
[1.2.0]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.2.0
[1.1.0]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.1.0
[1.0.0]: https://github.com/ChelseaKR/gtfs-scorecard/releases/tag/v1.0.0
