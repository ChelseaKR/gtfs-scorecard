# Release checklist and definition of done

Use this checklist for a product release, scoring-methodology change, or public
dataset tag. Routine data refreshes use their existing automated workflow.

## Before merge

- [ ] The change has an issue, ADR, or pull-request rationale and names the user impact.
- [ ] `make verify` passes, including branch coverage, typing, AAA contrast, readability,
  version consistency, and golden output.
- [ ] Browser e2e, 320px reflow/target-size, axe, Lighthouse accessibility, and
  performance budgets pass.
- [ ] Security, dependency, container, workflow, standards-pin, and CodeQL checks pass.
- [ ] Public claims identify their source, date, scope, and limitation; no output implies
  certification, rider service quality, or staff performance.
- [ ] Schema, API, methodology, accessibility, and migration documentation changed with
  the implementation when applicable.
- [ ] Rollback is a revert of the merge commit; any data or infrastructure exception has
  an explicit recovery command and owner.

## Release or deploy

- [ ] Merge only after required checks are green.
- [ ] The Pages workflow passes Lighthouse and the production deploy job.
- [ ] Smoke-test `/`, `/agencies/`, one agency page, `/status/`, and `/api/v1/index.json`.
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
