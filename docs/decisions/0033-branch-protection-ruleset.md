# 0033 — Branch protection via a ruleset with a scoped Actions bypass

Status: accepted and applied to the live repository (2026-07-10)

Date: 2026-07-05

## Context

A 2026-07-05 conformance audit found branch protection on `main` at its
default (unconfigured) state: zero required status checks, no required
pull-request reviews, `enforce_admins` off, no linear-history requirement.
Every "merge-blocking" gate this repo has built — `ci.yml`'s `pipeline` job,
`security.yml`'s `Secret scan (gitleaks)` and `SAST (Semgrep)` jobs,
`a11y.yml`'s `axe` job, `e2e.yml`'s `e2e` job — runs on every push and PR but
blocks nothing, because nothing requires it to pass before merge
(CICD-11/13, CQ-37/38/40/43).

**The complication that made this not a trivial toggle:** scheduled Actions
originally committed generated JSON data directly to `main`. The 2026-07-10
S3 source-of-truth cutover removed those data commits. The final ruleset
rollout also moved `data/liveness.json` into S3, so automation no longer needs
to write to `main` at all.

Two ways to reconcile the two needs:

- **(a) A GitHub ruleset with `bypass_actors` scoped to the GitHub Actions
  app**, so humans go through PR review + required checks, while the
  data-refresh workflows (which authenticate as the `github-actions[bot]`
  App when using the default `GITHUB_TOKEN`) keep committing straight to
  `main`.
- **(b) Move generated JSON artifacts to a dedicated `data` branch** (or the
  already-built `infra/artifacts` CDN path) and have `pages.yml` assemble
  `code@main` + `data@data` at deploy time, so `main` never receives a bot
  commit and needs no bypass at all.

## Decision

**Option (b), implemented with the existing S3 data plane.** Code stays on
`main`; generated score and liveness state stays in S3; Pages assembles both
at deploy time. Committed as `.github/rulesets/main.json`:

- Administrator recovery bypass: `actor_id: 5`, `actor_type:
  RepositoryRole`. This lets repository administrators recover a broken
  required check or automation path without weakening the normal contributor
  path. Ordinary human contributions remain bound by the rules below.
- The normal human path is fully bound: `pull_request` requires 1 approval,
  dismisses stale reviews on push, requires code-owner review, and requires
  the last pusher not be the sole approver (`require_last_push_approval`).
- `required_status_checks` (strict/up-to-date required) lists the real job
  names as they appear in GitHub's check-run API today: `pipeline`,
  `Secret scan (gitleaks)`, `SAST (Semgrep)`, `axe`, `e2e`, `Dependency audit
  (pip-audit + osv-scanner)`, `Analyze (python)`, `Analyze (actions)`, and
  `standards-pin`. **Every new unconditional PR gate must be appended to this
  list** — an
  unenforced merge-blocking gate is exactly the defect this ADR fixes; don't
  reintroduce it piecemeal.
  - **Updated same-day (still 2026-07-05)** once P1-1/P1-2 landed:
    `Dependency audit (pip-audit + osv-scanner)` and the CodeQL matrix legs
    `Analyze (python)` / `Analyze (actions)` were added — all three run
    unconditionally on every push and PR.
  - **Deliberately not required:** `Dependency review (PRs only)` and
    `zizmor (workflow security lint)` both use a job-level `if:
    github.event_name == 'pull_request'` guard, so they report no status at
    all on a direct push. GitHub's "required status check" enforcement can
    hang a PR indefinitely waiting on a check that a conditional `if:` never
    schedules, depending on how the check is triggered relative to the base
    ref; verify in the live UI that a PR actually shows these as
    green/skipped-as-satisfied before adding them here, rather than assuming.
    `openssf-scorecard.yml` and `trufflehog.yml` are schedule/push-to-main
    only by design (not meaningful per-PR signals) and are not candidates for
    this list. `standards-pin` is self-contained and enforcing, so it is
    required.
- `deletion`, `non_fast_forward`, and `required_linear_history` rules block
  force-push, branch deletion, and merge commits that aren't fast-forwardable
  from the review path — mirroring the classic protection API's
  `allow_force_pushes: false`/`allow_deletions: false`. Only squash and rebase
  merges are allowed, matching the linear-history rule.
- A companion `.github/rulesets/tags.json` protects **fully-qualified
  semver tags** (`refs/tags/v*.*.*`, e.g. `v1.0.0`) and dataset-release tags
  (`refs/tags/dataset-*`) from deletion or being moved — these
  are meant to be immutable the moment they're cut (REL-07).
  **Deliberately excluded: the bare `v1` tag.** GitHub Actions' marketplace
  convention is a floating major-version tag that intentionally moves to
  point at the latest `v1.x.y` on every release (`README.md`'s `uses:
  ChelseaKR/gtfs-scorecard@v1` depends on this). Locking it immutable would
  break that convention, not fix it; the glob `v*.*.*` (which requires two
  literal dots) matches `v1.0.0` but not `v1`, so the floating tag keeps
  moving while the point releases it points to stay pinned.
- **Solo-maintainer self-approval (CQ-43, CICD-12) is a known, accepted gap
  this ruleset cannot close on its own.** With one CODEOWNERS entry
  (`@ChelseaKR`, added alongside this ADR), the "required" reviewer is the
  same person as the author — a required-approval count of 1 does not
  actually prevent self-merge on a solo repo. The standard's own text
  acknowledges this is structurally hard for a solo maintainer and requires
  an **explicit written exception**, not a silent assumption; that exception
  is tracked as remediation P2-2 (`docs/RESPONSIBLE-TECH-AUDITS.md`). This
  ruleset still raises the bar for accidental direct pushes and enforces the
  required-checks list, which is the larger win.
- **Signed commits are deliberately deferred**, not included in this
  ruleset. Enabling SSH/GPG commit signing locally and adding a
  `required_signatures` rule can land a few days after the required-checks
  rollout without blocking it (CQ-41's second half).

## Consequences

- The branch and tag rulesets were applied through the GitHub API on
  2026-07-10 after their configuration PR passed CI and merged:

  ```sh
  gh api repos/ChelseaKR/gtfs-scorecard/rulesets -X POST --input .github/rulesets/main.json
  gh api repos/ChelseaKR/gtfs-scorecard/rulesets -X POST --input .github/rulesets/tags.json
  ```

  The live ruleset API is the enforcement source; these files are the
  reviewable, reproducible configuration. Verification includes reading the
  live rulesets back and running the intraday refresh through its S3 score and
  liveness publish plus Pages deployment path.
- Every future PR now needs the nine listed checks green and one approval
  before merge — including the author's own future PRs, which is the point.
- If `infra/compute`, CodeQL, dependency-audit, zizmor, or container-scan
  jobs land (P1), their exact job/check names must be appended to
  `.github/rulesets/main.json` and the live ruleset updated
  (`gh api .../rulesets/{id} -X PUT`) in the same change that adds the
  workflow — not as a follow-up that might not happen.
- Generated operational state must remain outside `main`. A future workflow
  that needs a direct bot push must introduce and justify its own narrowly
  enforceable protection model before it ships.

## Addendum, 2026-09-06: the `@v1` premise is stale, the exclusion still stands

The reasoning above excludes the bare `v1` tag from
`.github/rulesets/tags.json` on the ground that "`README.md`'s `uses:
ChelseaKR/gtfs-scorecard@v1` depends on this." On 2026-09-06 the public
examples in `README.md` and `docs/ci-action.md` were changed to pin a full
release tag, so that stated premise no longer holds. The exclusion was
re-examined and is kept, for a different and stronger reason.

What was measured on 2026-09-06:

- `v1` and `v1.4.0` point at the same commit (`d800e0b4`, 2026-07-25). `v1` has
  not moved since.
- `main` is 439 commits ahead of that commit.
- `v1.4.0` is the newest published release. It predates the refusal of an
  archive holding no schedule data, so it grades such an archive `F (31.3/100)`
  with `passed=true` — a fabricated grade, and the exact defect class this
  project exists to expose. The refusal is on `main` and in no release.
- Version 1.5.0 is declared in `pipeline/pyproject.toml` and has a `CHANGELOG.md`
  section dated 2026-08-18, but no tag and no release exist for it. The docs
  recommended pinning `@v1.5.0`, a tag that has never existed, and
  `tests/test_action_v2.py` asserted that they do so.

Why the exclusion is kept:

- Every workflow that copied `@v1` out of the docs before 2026-09-06 can
  receive the fabricated-grade fix only by that tag moving. An `update` rule on
  `refs/tags/v1` would strand those consumers on `v1.4.0` permanently. That is
  a worse outcome than a mutable pointer, and it is not reversible for anyone
  who has stopped watching the repository.
- The Marketplace convention argument in the original decision is unchanged;
  it is simply no longer the load-bearing one.

What replaces the removed premise: the project no longer *recommends* the
floating tag, and `tests/test_documented_action_ref.py` fails if any public
example names a floating major again. Keeping the tag movable and keeping it
out of the documented form are separate decisions; both hold.

No ruleset was changed by this addendum. One unrelated finding was recorded and
not acted on: `.github/rulesets/tags.json` carries `"bypass_actors": []`, while
`.github/rulesets/main.json` carries the repository-admin bypass. An empty
bypass list on a tag ruleset means the repository owner cannot delete or move a
mistagged release herself. That is an owner decision, not a docs one.
