# Release checklist and definition of done

Use this checklist for a product release, scoring-methodology change, or public
dataset tag. Routine data refreshes use their existing automated workflow.

## Tag namespaces

Three tag schemes share this repository's tag namespace. Nothing said so until
2026-09-06, and the prefixes are the only thing keeping them apart, so they are
written down here.

| Pattern | Example | What it is | Moves? | Protected |
|---------|---------|------------|--------|-----------|
| `vX.Y.Z` | `v1.4.0` | A product and Action release. Signed and annotated; carries the bounded Action distribution tree. | No — immutable once cut | Yes, by `.github/rulesets/tags.json` (`refs/tags/v*.*.*`) |
| `vX` | `v1` | The GitHub Actions Marketplace floating major. Points at the newest `v1.x.y`. | Yes, on every Action release | No, deliberately — see below |
| `dataset-YYYY-MM` | `dataset-2026-08` | A monthly citable snapshot of the published corpus, with flat exports, data dictionary, methodology version, and citation metadata. | No | Yes, by the same ruleset (`refs/tags/dataset-*`) |

The ruleset's `v*.*.*` glob requires two literal dots, so it covers `v1.4.0`
and never `v1`. That is what lets the point releases stay frozen while the
floating major keeps moving. `dataset-*` is a separate include in the same
ruleset; a dataset tag is a citation target, so moving one would falsify a
citation, and it is immutable for that reason rather than the Marketplace's.

A version can exist without a tag. `pipeline/pyproject.toml` is the one version
declaration everything else agrees with (`scripts/check_versions.py`), and it
is bumped when the `CHANGELOG.md` section is written, which is before the tag
is cut — sometimes long before. Version 1.5.0 is declared and changelogged and
has no tag or release. Documentation that tells a consumer which ref to use
must therefore name a tag that exists, not the declared version;
`tests/test_documented_action_ref.py` holds that.

### Why the floating major is kept but not recommended

Keeping `v1` movable and not recommending it are two different decisions, and
both hold at once:

- **Kept movable.** Every consumer who already copied `@v1` from these docs can
  only ever receive a fix through that tag moving. Freezing it would strand
  them on whatever `v1.x.y` it points at, permanently.
- **Not recommended.** A pointer that changes what a workflow runs with no
  commit and no diff on the consumer's side is not a contract. The public
  examples in `README.md` and `docs/ci-action.md` name a full release tag.

`docs/decisions/0033-branch-protection-ruleset.md` records the ruleset side of
this, including a 2026-09-06 addendum on what changed when the docs stopped
recommending `@v1`.

## Before merge

- [ ] The change has an issue, ADR, or pull-request rationale and names the user impact.
- [ ] `make verify` passes, including branch coverage, typing, AAA contrast, readability,
  version consistency, and golden output.
- [ ] Browser e2e, 320px reflow/target-size, axe, Lighthouse accessibility, and
  performance budgets pass.
- [ ] The fresh site passes the blocking structural SEO gate, including local
  links and fragments, duplicate IDs, metadata, canonical aliases, sitemap and
  robots parity, reciprocal HTTPS language links, required structured-data
  identity and dates, and the no-tracking contract. Confirm the generated
  report is retained for 14 days.
- [ ] Security, dependency, container, workflow, standards-pin, and CodeQL checks pass.
- [ ] Public claims identify their source, date, scope, and limitation; no output implies
  certification, rider service quality, or staff performance.
- [ ] Schema, API, methodology, accessibility, and migration documentation changed with
  the implementation when applicable.
- [ ] Public pages contain no analytics loader, tracking cookie, or visitor beacon.
  Search Console DNS verification and sitemap submission remain external owner
  tasks; no Search Console credentials or configuration are added to the repo.
- [ ] Rollback is a revert of the merge commit; any data or infrastructure exception has
  an explicit recovery command and owner.

## Release or deploy

- [ ] Merge only after required checks are green.
- [ ] The Pages workflow passes Lighthouse and the production deploy job.
- [ ] Smoke-test `/`, `/agencies/`, one agency page, `/status/`, and `/api/v1/index.json`.
- [ ] Confirm the weekly production Lighthouse job covers its four representative
  routes with three runs each and retains its reports for 90 days.
- [ ] For a SemVer tag, confirm `release-sign.yml` attaches the signed manifest,
  CycloneDX SBOM, VEX, and GitHub provenance attestations.
- [ ] For an Action release, publish the SemVer tag from GitHub's release form with
  **Publish this Action to the GitHub Marketplace** selected, choose the action's
  categories, and move the floating major tag only after the protected release tag
  is published.
- [ ] Before tagging an Action release, inspect the `export-ignore`-bounded source archive.
  It should contain only `action.yml`, `action/`, the runtime `pipeline/` package, and
  license/security files, and compress below 10 MB. Never make every Action consumer
  download the scored artifact corpus.
- [ ] For a dataset tag, confirm the flat exports, data dictionary, methodology version,
  and citation metadata are attached.

## Post-release

- [ ] Record material user-facing changes in `CHANGELOG.md`.
- [ ] For an Action release, open the Marketplace listing and run one workflow against
  both the protected patch tag and the floating major tag.
- [ ] Confirm the watchdog and next scheduled refresh remain healthy.
- [ ] Revert immediately if the primary agency lookup, scorecard, form submission,
  accessibility gate, or public API fails in production.

Definition of done means the implementation, tests, generated artifacts, documentation,
security evidence, deploy, and live verification all agree. A green unit suite alone is
not done.
