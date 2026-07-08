# 0033 — Branch protection via a ruleset with a scoped Actions bypass

Status: accepted (ruleset JSON committed; **not yet applied to the live
repo** — see Consequences)

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
workflows commit generated JSON data directly to `main` on an hourly/daily
cadence (`chore(data): intraday refresh`, `chore(rt): realtime health
observations`, plus the daily `scorecard.yml` run and the monthly
`dataset-release.yml`). A naive "require a PR for every push to main" rule
would break every one of these the moment it takes effect.

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

**Option (a).** Committed as `.github/rulesets/main.json`:

- Bypass actor: `actor_id: 15368`, `actor_type: Integration` — the
  `github-actions` GitHub App's numeric ID (verified 2026-07-05 via
  `gh api repos/ChelseaKR/gtfs-scorecard/commits/HEAD/check-runs`, which
  shows every check run's `app.id` as `15368`, `app.slug: "github-actions"`).
  `bypass_mode: always` so scheduled-workflow commits are never blocked.
- Humans are fully bound: `pull_request` rule requires 1 approval, dismisses
  stale reviews on push, requires code-owner review, requires the last
  pusher not be the sole approver (`require_last_push_approval`).
- `required_status_checks` (strict/up-to-date required) lists the real job
  names as they appear in GitHub's check-run API today: `pipeline`,
  `Secret scan (gitleaks)`, `SAST (Semgrep)`, `axe`, `e2e`. **Every new
  blocking job added in P1 (CodeQL, dependency-audit, zizmor, TruffleHog,
  container scan, Scorecard) must be appended to this list** — an
  unenforced merge-blocking gate is exactly the defect this ADR fixes; don't
  reintroduce it piecemeal.
  - **Updated same-day (still 2026-07-05)** once P1-1/P1-2 landed:
    `Dependency audit (pip-audit + osv-scanner)` and the CodeQL matrix legs
    `Analyze (python)` / `Analyze (actions)` were added — all three run
    unconditionally on every push and PR.
  - **Deliberately NOT added yet:** `Dependency review (PRs only)` and
    `zizmor (workflow security lint)` both use a job-level `if:
    github.event_name == 'pull_request'` guard, so they report no status at
    all on a direct push. GitHub's "required status check" enforcement can
    hang a PR indefinitely waiting on a check that a conditional `if:` never
    schedules, depending on how the check is triggered relative to the base
    ref; verify in the live UI that a PR actually shows these as
    green/skipped-as-satisfied before adding them here, rather than assuming.
    `openssf-scorecard.yml` and `trufflehog.yml` are schedule/push-to-main
    only by design (not meaningful per-PR signals) and are never candidates
    for this list. `standards-pin.yml` is soft-gated behind a secret that
    doesn't exist yet (see its own header comment) and must not be added
    until it's actually enforcing.
- `deletion`, `non_fast_forward`, and `required_linear_history` rules block
  force-push, branch deletion, and merge commits that aren't fast-forwardable
  from the review path — mirroring the classic protection API's
  `allow_force_pushes: false`/`allow_deletions: false`, which already passed.
- A companion `.github/rulesets/tags.json` protects **fully-qualified
  semver tags** (`refs/tags/v*.*.*`, e.g. `v1.0.0`) and dataset-release tags
  (`refs/tags/dataset-*`) from deletion or being moved, once applied — these
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

- **This ADR and the two JSON files are the committed-artifact half of the
  fix (CICD-12's requirement, and the audit's evidence trail). Applying
  them live is a separate, human-run step**, deliberately left undone by
  this change: creating a ruleset is a real, immediately-enforced
  modification to how `main` accepts changes, and this repo's remediation
  ground rules explicitly reserve write-effect GitHub API calls (creating
  rulesets, toggling branch protection) for the repo owner to run
  themselves, not for an automated pass to execute silently. Apply with:

  ```sh
  gh api repos/ChelseaKR/gtfs-scorecard/rulesets -X POST --input .github/rulesets/main.json
  gh api repos/ChelseaKR/gtfs-scorecard/rulesets -X POST --input .github/rulesets/tags.json
  ```

  Verify afterward with `gh api repos/ChelseaKR/gtfs-scorecard/rulesets` and
  a real PR (confirm required checks show up and a scheduled data-refresh
  run still lands on `main` without needing a PR).
- Every future PR now needs the five listed checks green and one approval
  before merge — including the author's own future PRs, which is the point.
- If `infra/compute`, CodeQL, dependency-audit, zizmor, or container-scan
  jobs land (P1), their exact job/check names must be appended to
  `.github/rulesets/main.json` and the live ruleset updated
  (`gh api .../rulesets/{id} -X PUT`) in the same change that adds the
  workflow — not as a follow-up that might not happen.
- If option (b) (a dedicated `data` branch) is ever preferred instead — e.g.
  because the bypass-actor scope is judged too broad, since it also
  bypasses review for *any* Actions-authored commit, not only the data-bot's
  — this ADR should be superseded, not edited, per the append-only ADR
  convention (CQ-46).
