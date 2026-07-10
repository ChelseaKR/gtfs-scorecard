# ADR 0030: Remediating the accumulated git-committed data history

Status: accepted and executed 2026-07-10 · Date: 2026-07-08

## Context

`docs/ideation/02-large-scale-fixes.md` FIX-13 asks the project to decide,
"once and deliberately," what to do about the data that has already
accumulated in git, not just about future writes. ADR 0002 already decided to
stop *future* artifact commits once the S3 cutover lands; that cutover was
completed on 2026-07-10 and is recorded in `docs/follow-ups.md`. This ADR is scoped to the
part ADR 0002 did not cover: the history that already exists, and the
prerendered pages, both of which keep growing regardless of the S3 decision.

Measured at the time of writing:

- `.git` is 884 MB (the ideation doc's 521 MB estimate from 2026-07-01 has
  already grown ~70% in a week).
- `data/artifacts` is 534 MB of committed, generated JSON.
- `web/agency/` carries 1,449 committed prerendered directories, one per
  agency, regenerated deterministically by `render_site.py` on every run.
- The collect workflow commits on a cadence of multiple times a day
  (`chore(data): intraday refresh`, `chore(rt): realtime health
  observations`, `chore(data): daily scorecard refresh` all appear in the last
  15 commits on `main`), so `git log --oneline main` is dominated by data
  noise rather than code changes.
- No `dataset-YYYY-MM` citation tags exist yet in this repository (`git tag
  -l`, `git ls-remote --tags origin` both return zero), so the citation-tag
  concern the ideation doc raises is currently theoretical, not yet a
  constraint with live external links pointing at it. It still governs how
  this ADR treats history rewriting, since the practice is intended to start.

Three sub-decisions are in scope, as framed by the ideation doc:

1. Whether to move data commits to an orphan `data` branch, a separate
   `gtfs-scorecard-data` repo, or leave them in `main`'s history as-is.
2. Whether to stop committing the 1,449 prerendered `web/agency/` pages and
   build them in CI (`pages.yml`) instead, since `render-site` already
   regenerates them deterministically from the artifacts.
3. Whether to rewrite existing git history at all.

## Decision

**(a) Data commits: stop future ones via the S3 cutover (already decided in
ADR 0002); do not fork a `data` branch or separate repo for the existing
history.** The S3 cutover (`follow-ups.md` steps 1–3) already gives `main` a
clean way to stop absorbing daily JSON churn without inventing a second
repository or an orphan branch to maintain. A separate `data` repo or orphan
branch would need its own CI wiring, its own access model, and a cross-repo
reference from `main` — real ongoing maintenance cost — to solve a problem
the S3 bucket already solves for new writes. It would do nothing for the
history already in `main`. Once the cutover lands, do not additionally split
history off; let the existing `data/artifacts` tree in `main`'s history simply
stop growing.

**(b) Prerendered pages: build them in CI instead of committing them.** Unlike
raw data artifacts, `web/agency/**` is a pure derived output of
`render_site.py` over data already in `data/artifacts`/S3 — the render is
already deterministic and idempotent (a precondition this project already
relies on elsewhere, e.g. FIX-04's golden-file plan). Committing it buys
nothing S3 or a CI build step doesn't: GitHub Pages already deploys a
generated `_site/` directory (`pages.yml` runs `render-site` and copies
`data/artifacts` into `_site/` before deploy), so the pages job already has
every input it needs to also render `web/agency/**` into `_site/agency/**`
without those 1,449 directories ever needing to sit in `main`. This is the
main lever for stopping repo growth for clones, since prerendered pages grow
1:1 with registry size the same way artifacts do, and the registry is what's
scaling.

**(c) Do not rewrite existing history.** `dataset-YYYY-MM` citation tags are
committed practice per the ideation doc even though none exist yet, and PR
links, commit SHAs referenced in `docs/decisions/*.md`, and any external
fork/clone all depend on today's history staying resolvable. A rewrite
(`git filter-repo`, BFG, or a fresh orphan `main`) would need every consumer
to re-clone and would break any SHA already cited anywhere — for a project
whose stated differentiator is "reproduce or contest the grade"
(`score.py:methodology()`), silently invalidating old references would work
against the project's own trust story. The existing 884 MB `.git` is a sunk
cost for anyone who has already cloned; it is not sunk for anyone cloning
fresh after (b) takes effect and future commits stop adding both artifacts
and prerendered pages, which is where the ongoing growth actually comes from.

## Sequencing

This decision is made now; execution is gated on `follow-ups.md`'s S3 cutover
so there is one migration story instead of two:

1. Finish the S3 cutover (`follow-ups.md` steps 1–3): Pages read role, `pages.yml`
   assembling `data/artifacts` from S3, then dropping `data/artifacts` from the
   collect job's `git add` path list.
2. In the same `pages.yml` change (or immediately after), add a `render-site`
   invocation to the pages job that writes `web/agency/**` (and any other
   `render_site.py` output currently committed) into `_site/` at deploy time,
   then stop committing `web/agency/**` from the collect/render job the same
   way step 1 stops committing `data/artifacts`.
3. Do not touch existing git history. Existing tags, PR links, and commit SHAs
   keep resolving to exactly what they resolve to today.
4. Re-measure `.git` growth rate a month after step 2 ships; if growth has not
   flattened, re-open this ADR rather than reaching for history rewriting.

## Consequences

- No new repository or branch to maintain; the S3 cutover already in flight
  becomes the single migration that also ends the accumulated-history
  problem's contribution rate, once it also covers prerendered pages.
- `git log --oneline main` stops accumulating `chore(data)`/`chore(rt)` noise
  once step 1 lands, and stops accumulating a `web/agency/**` diff on every
  render once step 2 lands; a fresh clone's growth rate approaches zero for
  both artifacts and pages, though the existing 884 MB of history remains in
  every clone (accepted per (c)).
- `pages.yml` gains a `render-site`-for-deploy step; the pipeline itself
  learns nothing about S3 or CI-only rendering (consistent with ADR 0001/0002's
  "the pipeline stays a filesystem CLI" principle) — only the deploy workflow's
  assembly step changes what it copies into `_site/`.
- Anyone relying on `web/agency/**` being present in a `git clone` of `main`
  (rather than fetched from the deployed site) loses that after step 2; no
  current consumer identified in this repo depends on that (the SPA and the
  MCP server both read `data/artifacts`/S3, not the prerendered HTML).
- This ADR does not shrink the existing 884 MB `.git` for people who already
  have it cloned; it only stops it from getting materially worse. Anyone who
  needs a small clone can still do a shallow or partial clone
  (`git clone --depth 1` / `--filter=blob:none`) today, independent of this
  decision.
