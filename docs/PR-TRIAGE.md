# Open pull-request triage, 2026-08-28

A read-only pass over every open pull request. Merge states were computed
locally with `git merge-tree --write-tree` against the current `origin/main`
rather than taken from the API, because four of the seven reported
`mergeStateStatus: UNKNOWN`. Test results quoted below were produced by
materializing each simulated merge into a scratch tree and running the suite,
not inferred from the diff.

## Headline

`main` is green. `make verify` on a clean `origin/main` checkout exits 0.
Nothing below is failing because the base is broken.

Seven pull requests are open, not six. The seventh is #323, opened after the
brief this triage started from was written.

Three things are worth reading before any merge button is pressed:

1. **#312 is wrong and must not be merged.** It reverts a documented curatorial
   decision and fails a test on `main` that exists to prevent exactly that
   revert. It has never run CI, so nothing said so.
2. **#319 already contains all of #318.** They are not a two-step stack. #319 is
   a rebased superset, so merging both applies the same change twice.
3. **#321 carries a guard no test can reach.** The whole suite stays green when
   the guard is deleted, and the state it fails to catch crashes the site render.

## Group counts

| Group | Count | PRs |
|---|---|---|
| Green, correct, ready to merge | 2 | #322, #323 |
| Ready, minor test-quality follow-up suggested | 2 | #318, #320 |
| Ready except for a real defect to fix first | 1 | #321 |
| Needs a retarget and a conflict resolution | 1 | #319 |
| Do not merge, actively wrong | 1 | #312 |

## Per-PR table

Merge state is computed against `origin/main` as it stands now. "BEHIND" and
"UNKNOWN" from the API are not repeated; what is recorded is whether the merge
actually conflicts.

| PR | Base | Real computed merge state | CI classification | Recommendation |
|---|---|---|---|---|
| #323 | `main` | Clean, no conflict | 16 of 16 pass, genuine | Merge. Test-only, deletes nothing |
| #322 | `main` | Clean, no conflict | 16 of 16 pass, genuine | Merge first. Suite passes, coverage 92.35 over a 92 floor |
| #321 | `main` | Clean, no conflict | 16 of 16 pass, genuine but green over a defect | Fix the unreachable guard test, then merge |
| #320 | `main` | Clean, no conflict | 16 of 16 pass, genuine | Merge. One assertion to tighten, non-blocking |
| #319 | `fix/guardrails-that-can-fail` | **Conflicts** with `main` and with its own declared base | 12 of 12 pass; 4 checks **absent**, not failed | Retarget to `main`, resolve, merge instead of #318 |
| #318 | `main` | Clean, no conflict | 16 of 16 pass, genuine | Close as contained in #319, or merge #318 and drop #319 |
| #312 | `main` | Clean merge, but **fails the test suite** | **0 checks. Never executed** | **Do not merge.** Close or rebuild |

### CI classification detail

- **#319, four absent checks.** CodeQL and its three `Analyze` jobs never
  triggered. `.github/workflows/codeql.yml` is the only workflow whose
  `pull_request` trigger is filtered (`branches: [main]`), and #319's base is
  `fix/guardrails-that-can-fail`. Every other workflow is unfiltered and ran.
  This is absence, not failure, and not starvation.
- **#312, zero checks.** Eight workflow runs exist against its head branch. All
  eight report `conclusion: action_required` with an empty `jobs` array and 0s
  duration: they were created and then held at the workflow-approval gate,
  never executed. The commit is authored by the owner but committed by
  `github-actions[bot]`. So #312's clean-looking state reflects nothing having
  run, not anything having passed. It is absent, not starved: there is no
  budget or spending-limit annotation, and no job was ever created to starve.

## The stack

The four PRs titled Phase 3 through Phase 6 are **not** a stack. No head branch
is a git ancestor of any other. The ancestry matrix over all seven heads is
empty.

```
origin/main (27d5d6c16fb, green)
│
├── #318  fix/guardrails-that-can-fail        Phase 3   1 commit off 741628072a4
│         └─ CONTAINED IN #319 (see below)
│
├── #319  fix/render-failure-names-the-feed   Phase 4   2 commits off 490ee97957e
│         declared base: fix/guardrails-that-can-fail  (NOT an ancestor of it)
│         = a rebased copy of #318's commit + one commit of its own
│
├── #320  feat/disclose-the-realtime-cohort-exclusion   Phase 5   independent
├── #321  feat/publish-ntd-reporter-coverage            Phase 6   independent
├── #322  fix/gates-that-could-not-fail        9 commits, independent
├── #323  chore/agent-worktree-scope-guard     1 commit, independent
└── #312  chore/feed-discovery                 1 commit, independent
```

### Phase 3 is a cumulative subset of Phase 4

This is the cumulative-snapshot shape, and it is present here exactly once.

#319's branch carries two commits. The first, `e01aeb1b502`, is a rebased copy
of #318's only commit `d2d529d68fe`, same message and same content. Verified by
content rather than by SHA:

| File #318 touches | Identical on #319's head? |
|---|---|
| `docs/decisions/0050-controls-that-can-fail.md` | identical blob |
| `pipeline/src/scorecard_pipeline/sensitivity.py` | identical blob |
| `pipeline/tests/test_complexity_ratchet.py` | identical blob |
| `pipeline/tests/test_published_grade_path.py` | identical blob |
| `pipeline/src/scorecard_pipeline/render_site.py` | every added line present |
| `docs/lint-complexity-ratchet.md` | every added line present |
| `CHANGELOG.md` | #318's entry present verbatim |

The two files that "differ" differ only because #319 adds more on top.
Ignoring whitespace, #319's 136-insertion / 108-deletion rewrite of
`render_site.py` reduces to #318's identical change plus a single added line,
`with _rendering_feed(agency_id):`. The remaining deletions are reindentation.
No statement was dropped, reordered, or moved into or out of the loop.

**Consequence.** Merging #319 delivers Phase 3 and Phase 4 together. Merging
both applies Phase 3 twice. Because the repo squash-merges, #318 would not
auto-close on #319 landing, and #319 would not auto-close on #318 landing.

**Auto-close.** #319 is the only PR based on another PR's branch. If #318 is
merged and `fix/guardrails-that-can-fail` deleted, GitHub retargets #319 onto
`main` rather than closing it, and #319 then still presents Phase 3's content as
part of its diff. Nothing else in the queue auto-closes on any other merge.

## Dominant-defect findings

The hunt was for a test that passes in both the fixed and the unfixed state.
Each finding below was proved by mutation: the guard was deleted or the bug
re-introduced, and the suite re-run.

### #321: a guard no test can reach (blocking)

`pipeline/src/scorecard_pipeline/ntd_coverage.py:465`

```python
if sorted(by_tier) != sorted(TIER_ORDER):
    return None
```

Delete those two lines and the entire suite still passes: 16 of 16 in
`pipeline/tests/test_ntd_reporter_publication.py`, and 2,722 tests overall.

The test that claims to hold it,
`test_a_snapshot_missing_a_tier_publishes_nothing` at
`pipeline/tests/test_ntd_reporter_publication.py:97`, builds its payload by
dropping the `atlas_ntd_id` tier, whose count is 33. Dropping it also breaks the
sum, so the *next* guard returns `None` first. The tier-set guard is never the
thing that fires. The candidate set was built so the failure branch is
unreachable.

This is not cosmetic. The committed snapshot has `"catalog_name_fuzzy": 0`. A
snapshot missing *that* key still sums correctly, so the sum guard does not
fire either. With the guard present the result is `None`, which is the intended
fail-closed behaviour. With it gone the result is a `KeyError` raised from
`published_reporter_coverage()` inside `render_site()`, an uncaught crash of the
whole site render.

Fix: have the test drop a zero-count tier, for example `catalog_name_fuzzy`,
so the tier-set guard is the guard actually exercised.

Also on #321, `test_the_tiers_sum_to_the_stated_population` at line 74 is
tautological: it asserts a property the function under test already enforces,
and deleting the sum guard leaves it green. A different test does catch that
one, so this is a note rather than a defect.

### #320: one assertion that certifies nothing (non-blocking)

`pipeline/tests/test_realtime_cohort_disclosure.py:79`,
`assert 'href="/realtime/"' in html`. The pulse page already contains one such
link with the disclosure absent and two with it present, so this line passes in
both states. The two assertions above it do bite, so the test as a whole still
fails correctly. Tighten to a count if it is touched.

### #318: an AST scope gap (non-blocking, currently theoretical)

`_letter_grade_calls` at `pipeline/tests/test_published_grade_path.py:82`
requires `isinstance(node.func, ast.Name)`, so an attribute-style call is
invisible to it. Rewriting `_grade_band` to call `score.letter_grade(...)`
through a module alias re-introduces bug #310 with all six tests passing. Both
live call sites use the bare name, so nothing is wrong today. Handling
`ast.Attribute` would close it.

### What is sound

Everything else bites, proved by mutation. #318's complexity ratchet is exact
equality against live ruff output on every run, not a loose ceiling: ruff
reports 15 functions over the floor and the register has 15 rows, and restoring
`main`'s stale register reproduces the #309 drift as a failure. #319's
`_rendering_feed` context manager fails 3 of 4 tests when collapsed to a bare
`yield`. #320 fails on all four mutations tried. #321 bites on five separate
mutations beyond the one gap above. #323's worktree-scope test is not vacuous:
it parses 187 gate source files, finds 38 that bind a repository-root anchor,
and correctly classifies the 2 root-anchored glob calls that exist.

### The golden-regeneration hatch

None of #318, #319, #320, or #321 re-opens it, and none closes it. All four
inherit `main`'s `pipeline/tests/test_report_golden.py` byte for byte.

Worth stating plainly: **the hatch is open on `main` today.**
`REPORT_GOLDEN_REGEN` set in a CI environment still turns every report-golden
assertion into a write. The only change that closes it is commit `86c61c7def0`,
which is on #322's branch and not on `main`. That is an argument for merging
#322 early.

The goldens #320 and #321 do touch belong to `test_render_golden.py`, which has
no environment-variable write path at all. Both update goldens by committing new
expected bytes, which is the reviewed path. Confirmed the comparison still
bites: with #321's code applied and the pre-PR goldens restored, the golden test
fails naming `ntd/index.html` and `ntd.json`.

### #323's prose figures are stale

The docstring states that a 2026-08-28 audit found 49 leftover worktrees holding
41 GB. The real figures today are **36** worktrees holding **30 GB**. The test
logic is unaffected. Worth correcting since the number is the stated motivation.

A smaller note: `GATE_TREES` names `pipeline/scripts`, `pipeline/tests`, and
`scripts`, omitting `pipeline/src`. That is a scope that narrows by omission, the
shape #322's own CQ-38 comment argues against. It drops 0 call sites today, so
it is latent rather than live.

## #312 is actively wrong

`registry/us/ca.yaml` changes `city-of-wasco`'s `static_gtfs_url` from the
Caltrans DDS URL to the calitp.org mirror. `pipeline/tests/test_agencies.py:455`
asserts that exact URL must stay as it is. Run against #312's merged tree:

```
FAILED tests/test_agencies.py::test_repo_registry_tracks_calitp_hosting_migration
  - https://gtfs.dds.dot.ca.gov/gtfs_files/WascoDialaRideFlex.zip
  + https://gtfs.calitp.org/production/WascoDialaRideFlex.zip
```

The change reverts a deliberate curatorial decision, and in the same diff it
deletes the paragraph that recorded why the decision was made. It also deletes a
worked root-cause analysis of a feed-matcher bug, including the reasoning about
a generic token in `_name_tokens()` and the name of the regression test written
for it, replacing it with a bare one-line entry.

Its counts also shrink sharply against the previous run of the same report, from
five likely-replaced agencies to one and from 459 still-on-listed-URL to 320,
which suggests the discovery run behind it covered a smaller population than the
run it overwrites.

Because no workflow ever executed for this PR, none of that was reported by CI.

Recommendation: close it. If the Mobility Database moves are still wanted,
regenerate the report from a full run, and teach `discover` to skip any agency
whose `operating_note` or `license_note` already names the current host, which
is the follow-up the deleted paragraph itself proposed.

## Leftover agent worktrees

`git worktree list` reports 44 entries. One is the main working tree, one is the
scratch tree this report was written in, six are older non-agent trees, and
**36** are agent worktrees under
`/Users/chelsea/portfolio/gtfs-scorecard/.claude/worktrees/`.

Every one of them was inspected read-only. Nothing was deleted, pruned, reset,
stashed, or committed.

| Classification | Count |
|---|---|
| Merged into `main` **and** clean, so safe to remove | **0** |
| Merged but holding uncommitted changes | 11 |
| Unmerged, working tree clean | 24 |
| Unmerged **and** holding uncommitted changes | 1 |
| Total agent worktrees | 36 |

**No agent worktree is safely deletable.** All 36 hold either commits that are
not on `main` or uncommitted changes, usually the former.

### The largest at-risk worktree

```
/Users/chelsea/portfolio/gtfs-scorecard/.claude/worktrees/agent-ac8607a79812f76b5
```

It holds 1,597 lines of untracked work in three files, none of which exists on
`origin/main` in any form:

| File | Lines |
|---|---|
| `pipeline/scripts/cohort_completeness.py` | 983 |
| `pipeline/tests/test_cohort_completeness.py` | 317 |
| `docs/cohort-completeness.md` | 297 |

That is 1,597 exactly. It is the largest body of content in any worktree that
exists nowhere else, and it is one `rm -rf` away from being gone.

A second worktree, `agent-ac4daf82b3ec03718`, shows a larger raw uncommitted
count of 10,899 lines, but 9,763 of those are a regenerated
`data/feed-publishers.json` that is already committed on `main`. Its genuinely
unique content is a 93-line ADR draft.

### What #323 actually does

#323 adds one file, `pipeline/tests/test_agent_worktree_scope.py`, 206 lines,
and changes nothing else. **It deletes no worktree and removes no data.** It
asserts three things: that `.claude/worktrees/` stays listed in `.gitignore`,
that `.semgrepignore` keeps deferring to `.gitignore`, and that no gate script
walks the repository root recursively. It is a scope guard, and it is safe.

Nothing in the open queue deletes a worktree.

## The `ovapi-netherlands` record loss

**Still live.** No open PR stops it.

The `deploy`-gating half of #314 works and must not be undone. #314 merged
2026-08-27 as `a8d9d1f2106`, adding one line to the `deploy` job of
`.github/workflows/scorecard.yml`:

```yaml
if: ${{ !cancelled() && needs.collect.result == 'success' }}
```

Before it, `deploy` inherited an implicit `success()` evaluated over its whole
ancestry, so one dead score shard skipped the publish. Verified against live
runs: the same shard died on 08-26, 08-27, and 08-28; on 08-26 `deploy` was
skipped, and on both later runs it succeeded.

**No open PR reverts or weakens that gating.** Only #322 touches any workflow
file, and it is built on top of #314: the ceiling and the `if:` line both
survive on its branch, and its `test_workflow_safety.py` change is additive, so
#314's two regression tests remain.

The memory-ceiling half does not work. `SCORECARD_VALIDATOR_MEMORY_MB: "10240"`
bounds virtual address space through `prlimit --as`, not resident memory. Two
scheduled runs with it in force died identically, with no validator error
raised.

**The `upload-artifact` step is not guarded by `if: always()`.** It carries no
`if:` at all, so it inherits `success()`. More importantly, `if: always()` would
not help: in the failing job the runner's own `Post` cleanup hooks were
*skipped*, which means the runner process itself is gone. There is nothing left
to evaluate an `always()` condition. The upload happens once, at the end of the
job, with no incremental or checkpointed path.

**The figure is 63, not about 65.** The shard that dies is index 16 of 32,
planned round-robin over `2,012` canonical ids, and it holds `63` of them.
`ovapi-netherlands` sits 42nd inside it. Confirmed against production: the
failing job's name matches the computed contents of that shard, and the run
produced 31 artifact bundles out of 32. The "about 65" came from the incident
doc's own `2100 / 32` estimate over the pre-filter corpus size. Of the 63, at
most 42 were already computed and then discarded. "Lost" means not refreshed
rather than deleted, since `collect` rehydrates from S3, so the harm is 63
records silently serving stale data for that day.

**#322 makes the loss visible. It does not prevent it.** It teaches
`merge_run_summaries` an expected shard count so a missing shard degrades the
run instead of being summed over, and it adds a shortfall branch and warning
annotations. None of that touches the single end-of-job upload. The two changes
that would actually bound the loss, an incremental per-agency upload or putting
`large_feed` records on their own shard, are recorded in the incident doc as
open maintainer decisions and are in no open PR.

## Non-diff hazards

### CHANGELOG placement: clear

On `main`, `## [Unreleased]` is at line 28 and the newest released heading,
`## [1.5.0] - 2026-08-18`, is at line 80. All four CHANGELOG hunks land between
lines 29 and 43, inside Unreleased. **No hunk lands in a released section.**

### Same-file collisions: present, but they fail loudly

Six files are touched by more than one PR. Every pair that shares `CHANGELOG.md`
and `docs/feature-roadmap.md` conflicts on the second merge, which is the safe
outcome: a human sees it.

| Sequence | Result |
|---|---|
| #318 then #319, #320, or #321 | conflicts in `CHANGELOG.md`, `docs/feature-roadmap.md` |
| #319 then #320 or #321 | same two conflicts |
| #320 then #321 | same two conflicts |
| #312 then #319 | same two conflicts |
| anything then #322 or #323 | clean |

The dangerous case is the pair that merges clean and breaks anyway. Five PRs
touch `pipeline/src/scorecard_pipeline/render_site.py`, and the pairs involving
#322 all merge clean. Each was materialized and run:

| Simulated merge | Result |
|---|---|
| #322 alone onto `main` | suite passes, coverage 92.34 |
| #318 + #322 | suite passes, coverage 92.35 |
| #320 + #322 | suite passes, coverage 92.35 |
| #321 + #322 | suite passes, coverage 92.36 |

All four merged files compile and contain no duplicated top-level definition.
The single failure seen in these runs,
`test_action_source_archive_is_runtime_bounded`, runs `git archive HEAD` and
fails only because the scratch tree has no `.git`. It passes on the clean
checkout.

This one is worth watching rather than dismissing: #322 puts `render_site.py`
inside the coverage floor, and the resulting margin is 0.34 points over a 92
floor. Any later change adding uncovered lines to that file lands close to the
edge.

### Generated output

- **#320 and #321** touch goldens under `pipeline/tests/goldens/` but different
  files, so they do not collide. Both regenerate correctly from their own
  source, confirmed by restoring the pre-PR goldens and watching the comparison
  fail. #321's feature was checked against the real committed snapshot rather
  than only its fixture: `data/ntd/reporter-coverage-ry2024.json` declares
  `unit: ntd_reporters` and its tiers sum to its stated population, so the
  feature publishes in production rather than silently failing closed.
- **#312** rewrites two generated documents, and that is where its damage is.
  See above.

## Safe order of operations

1. **Merge #322 first.** It is green, it merges clean, it closes the golden
   regeneration hatch that is open on `main` today, and every other PR merges
   cleanly on top of it. Merging it first also means the shard-loss reporting is
   in place before anything else moves.
2. **Merge #323.** Independent, test-only, clean after #322. Optionally correct
   the 49 and 41 GB figures in its docstring to 36 and 30 GB first.
3. **Decide Phase 3 and Phase 4 as one item.** Preferred: retarget #319 to
   `main`, resolve its `CHANGELOG.md` and `docs/feature-roadmap.md` conflicts,
   merge it, and close #318 as contained. Do not merge both.
4. **Fix #321's unreachable guard test, then merge #321.** The one-line change
   is to drop a zero-count tier in the test payload. **This merge needs a
   regeneration step**: re-run the render and confirm `pipeline/tests/goldens/ntd.json`
   and `pipeline/tests/goldens/ntd/index.html` match, since #320 also edits
   `render_site.py`.
5. **Merge #320.** After any of #318, #319, or #321 has landed, **its
   `CHANGELOG.md` and `docs/feature-roadmap.md` hunks need repositioning** by
   hand. Keep both entries under `[Unreleased]`; do not let a resolution push
   either one below the `## [1.5.0]` heading. After resolving, regenerate and
   confirm `pipeline/tests/goldens/pulse/index.html`.
6. **Close #312.** Do not merge it. If the feed moves are still wanted,
   regenerate from a complete discovery run on a fresh branch.

Whichever of the CHANGELOG-touching PRs lands second, third, and fourth will
conflict. That is expected and safe. The thing to check on each resolution is
that the entry stays inside `[Unreleased]` and that the goldens are regenerated
rather than hand-merged.

## What was verified here, and what was taken on trust

### Verified directly

- The open set: 7 PRs, listed by `gh pr list`.
- `main` is green: `make verify` run to completion on a clean `origin/main`
  worktree, exit 0.
- Every merge state in the table: computed with
  `git merge-tree --write-tree --messages` against current `origin/main`, and
  for #319 also against its declared base.
- Pairwise and sequential merge outcomes: simulated with `git commit-tree` on
  the first merge's tree, then `git merge-tree` for the second.
- The four merged trees involving #322: materialized into a scratch tree and the
  full suite run with the coverage floor applied.
- #319 contains #318: compared blob by blob and line by line, plus a
  whitespace-insensitive diff of the `render_site.py` rewrite.
- The ancestry matrix over all seven heads: `git merge-base --is-ancestor`.
- #312's failure: run against its own merged tree, failing test named above.
- Every defect finding: proved by mutating the source and re-running.
- All 36 agent worktrees: `git -C <path>` status, log, and diff, read-only. Line
  counts computed per file, and each untracked file checked for existence on
  `origin/main`.
- #323's content: the full diff read; it adds one test file and nothing else.
- The 49 and 41 GB figures: recounted and re-measured.
- The `ovapi-netherlands` shard size: recomputed from the registry and the
  sharding function, and cross-checked against the live failing job's name and
  against the artifact-bundle count.
- CI classification: per-PR check rollups, per-run job listings, and the
  `pull_request` branch filter of every workflow.
- #321's real snapshot validating against its own guards.
- CHANGELOG heading positions and each hunk's landing line.

### Taken on trust

- **Live GitHub run history.** Job step ledgers, conclusions, and durations were
  read through the API but not re-executed. The claim that the runner process
  dies rests on GitHub's own step records showing the `Post` hooks skipped.
- **The incident document's account** of the underlying cause of the runner
  death. Its blast-radius arithmetic was rechecked and corrected; its
  description of the trigger was not independently reproduced, and the incident
  record itself calls the trigger unconfirmed.
- **Whether the discovery run behind #312 was partial.** The count drop is real
  and observable in the diff. The reason for it is inferred, not confirmed.
- **The repository-admin ruleset bypass** was left alone by design. No open PR
  touches `.github/rulesets/main.json` or any repository setting, and #322's new
  required-status-check test asserts only that the ruleset is enforcing and
  scoped to `main`. It makes no assertion about bypass actors, so nothing here
  removes it.
- **Nothing was executed against production**, and no GitHub state was modified.
  Every `gh` call in this pass was a read.

## Correction, 2026-08-29

Appended, not edited. The pass above was accurate when it was written. Two of
its recommendations were overtaken by merges made after it, and one of them now
points the wrong way hard enough to lose work, so the record says so here rather
than being rewritten above.

### #319 was merged into #318's branch, not into `main`

The triage recommended retargeting #319 to `main`, merging it, and closing #318
as contained in it. What actually happened on 2026-08-29T02:36:36Z is the
inverse: #319 was merged **into its declared base**, `fix/guardrails-that-can-fail`,
which is #318's own branch. Squash commit `b6c57c218c0`.

That commit is not an ancestor of `main`:

```
$ git merge-base --is-ancestor b6c57c218c0 origin/main ; echo $?
1
```

So Phase 4 is not on `main`, and the only open pull request carrying it is
**#318**. The containment relation the triage described has reversed: #318 now
contains #319, having absorbed it. Its branch holds three commits off `main`,
the Phase 3 work, a merge of `main`, and #319's squash, and its diff is the
union of both phases across nine files.

**#318 must not be closed.** Closing it now drops Phase 3 and Phase 4 together,
and Phase 4 exists on no other open branch.

### #322 and #326 have since merged to `main`

`af0735f0f3c` and `63927943695`. The triage's "merge #322 first" is done. #326
was opened after this pass and is not covered by it.

### What still holds

- **#312 must not be merged.** Re-confirmed on 2026-08-29 against a fresh rebase
  onto `main`: `tests/test_agencies.py::test_repo_registry_tracks_calitp_hosting_migration`
  fails, 1 failed and 92 passed. The registry hunk sets `city-of-wasco`'s
  `static_gtfs_url` to `https://gtfs.calitp.org/production/WascoDialaRideFlex.zip`,
  which is the value that test exists to forbid, and it leaves the entry's
  `license_note` citing the Caltrans DDS index it no longer points at, so the
  published attribution would name a source the URL has left.
- **#321's guard could not fail, and now can.** Re-confirmed by deleting the
  two-line tier-set comparison in `ntd_coverage.py`: before the fix the pull
  request's own suite stayed green at 16 passed. The state it failed to catch
  was reproduced directly rather than reasoned about, a snapshot missing the
  zero-count `catalog_name_fuzzy` tier sums to its own denominator, passes the
  reconciliation guard, and raises `KeyError('catalog_name_fuzzy')` out of
  `published_reporter_coverage`, which is a site render that dies where a page
  should have published nothing. The missing-tier test now subtracts the dropped
  tier's count from the denominator so the reconciliation guard cannot fire, and
  is parametrized over every tier rather than one named by hand. Deleting the
  guard against the repaired test fails 10 of 25, one per tier.

### Revised order

Measured by materializing each merge in sequence rather than predicted from the
file lists: **#323, #318 (Phase 3 and Phase 4 together), #325, #324** apply
cleanly in that order. **#320 and #321 then conflict**, with each other and with
#318, in `CHANGELOG.md` and `docs/feature-roadmap.md`. Both are the same shape,
two sides appending a new entry at the same anchor, so the resolution keeps both
entries and drops neither side's file. Close #312.
