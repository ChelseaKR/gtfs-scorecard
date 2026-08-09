# 0030 — Extract the honesty-as-a-feature primitives into a shared portfolio standard

Status: proposed (ADR + draft standards contribution written; landing in
`portfolio-standards` and adoption by a second repo is a separate,
portfolio-owner-gated act — see "Consequences")

## Context

This repo's actual differentiator is not the scoring pipeline; it is a small
set of "state it, do not certify it" primitives that keep a grade honest under
scrutiny (`docs/ideation/03-expansions.md`, EXP-17):

- **A machine-readable methodology changelog**
  (`pipeline/src/scorecard_pipeline/score.py:METHODOLOGY_CHANGELOG`,
  `methodology_changelog()`) — a dated, newest-first, plain-language log of
  every rubric-version change, published in `scoring.json` so a reader can
  tell a score change apart from a rule change.
- **A provenance block on every artifact**
  (`pipeline/src/scorecard_pipeline/publish.py:build_artifact`) — the
  `rubric_version`, `validator_version`, and the feed's `sha256`, plus a fetch
  block (`source`, `final_url`, `user_agent`) recording how the graded bytes
  were obtained. This is what makes a snapshot citable and a trend separable
  into "the feed changed" vs. "the methodology changed."
- **Renormalized scoring that never punishes the unmeasured**
  (`score.py:build_scorecard`) — weights of any not-yet-measured category are
  redistributed across the measured ones, so an agency with no realtime feed
  is never scored as if realtime were a zero.
- **No-shaming fix tiers** (`score.py:_fix_tier`, `_fix_priority`) — findings
  are ranked by rider impact (feed-broken > rider-experience gap >
  informational), and every finding is framed as a fix, never a failure
  (`CLAUDE.md`, "Writing style").

`docs/ideation/03-expansions.md` (EXP-17) names three sibling repos —
`tods-validate`, a private sibling project, and `outcome-receipts` — that face
the identical "state it, do not certify it" problem: each produces a machine judgment about
something (a validator run, an eval score, a receipt) that is easy to
over-claim as certification rather than a measurement with edges. This repo
already paid down the hard design cost of that problem. Leaving the pattern
implicit in `score.py`/`publish.py` means each sibling repo either re-derives
it from scratch or, worse, ships a differently-shaped and differently-honest
version of the same idea.

The shared standards project is the portfolio's existing mechanism for exactly this:
a cross-cutting rigor stated once, referenced by every repo, with per-repo
values recorded locally (`STANDARDS/README.md`, "reference, don't repeat").
It is a separate git repository with its own release cadence — repos pin a
`standards_version` (this repo: `docs/standards/.standards-version`) that
Renovate bumps — so a change there has a blast radius across every consuming
repo, not just this one.

## Decision

1. **This ADR is the record that the pattern is being extracted**, and names
   exactly what generalizes and what does not (see "What travels" below).
2. **The reference implementation stays in this repo.** `score.py` and
   `publish.py` remain the canonical, running example; the standard describes
   the shape, it does not fork the code. Sibling repos adopt the *pattern*
   (their own methodology changelog, their own provenance block, their own
   renormalization and tiering, in whatever language/format fits their
   pipeline), not this repo's Python.
3. **The actual `STANDARDS` contribution is drafted, not landed, by this
   PR.** A ready-to-copy draft standard lives at
   `docs/standards-contribution/HONESTY-AS-A-FEATURE.md` in this repo. Landing
   it in `portfolio-standards` (a separate repository with its own
   `standards_version` that every pinning repo consumes) is a portfolio-level
   act that belongs to the portfolio owner, not to a single-repo change —
   consistent with EXP-17's own gating note ("a portfolio-level act, gated on
   the maintainer's cross-repo intent") and its stated risk ("premature-
   abstraction risk — extract only what two repos already share"). This repo
   is the first of the two; a second repo has not yet adopted the pattern, so
   the extraction is deliberately staged as draft-then-land rather than
   landed unilaterally from here.

### What travels (the shape, not the code)

- **Methodology-changelog format**: an ordered, newest-first list of dated
  entries, each carrying the methodology's own version identifier and a
  plain-language summary of what changed and why — published in the same
  machine-readable artifact the judgment itself ships in, not buried in a
  CHANGELOG only a maintainer reads.
- **Provenance-block shape**: every emitted judgment carries (a) the version
  of the methodology that produced it, (b) the version of any third-party
  tool it wraps, and (c) a content hash or equivalent fingerprint of the
  input, so a result is reproducible and a drift in output is attributable to
  a named cause (input changed / methodology changed / tool changed).
- **Renormalization rule**: when a methodology has multiple weighted
  sub-measures and one is not computed for a given subject, redistribute its
  weight across the measures that were computed rather than scoring the
  missing one as a zero or excluding the subject entirely. State plainly, in
  the published output, which sub-measures were and were not computed.
  Publishing what could not be assessed, not just what was, is what earns the
  reader's trust — see also `docs/decisions/*` measurement-confidence work in
  this repo.
- **No-shaming tiering**: rank findings by the impact on the end user of the
  measured system, not by raw count or by how bad the finding looks; frame
  every finding as an action the subject can take, never as a verdict on the
  subject. A subject that has not yet built a capability (this repo: no
  realtime feed) is described neutrally, not penalized for the gap.

## Alternatives considered

- **Land directly in `portfolio-standards` from this PR.** Rejected for this
  PR: that repository has its own working state and release process
  (Renovate-bumped `standards_version` consumed by every pinning repo), and
  is out of scope for a change scoped to this repo's worktree. It also
  front-runs EXP-17's own excellence bar — a second repo adopting the pattern
  — with zero adopters, which is exactly the premature-abstraction risk the
  ideation entry flags.
- **A shared code package instead of a written standard.** EXP-17 calls this
  out as optional. Rejected for now: `tods-validate`, `a private sibling project`, and
  `outcome-receipts` are not confirmed to share a language or pipeline shape
  with this repo's Python; a written standard (values and shapes, not an
  importable module) is adoptable regardless of implementation language,
  matching how every other `STANDARDS` document already works.
- **Do nothing until a sibling repo asks for it.** Rejected: EXP-17 already
  identifies the concrete sibling repos and the shared problem; writing the
  draft now means the next repo to hit "state it, do not certify it" has
  something to read instead of re-deriving it.

## Consequences

- This repo gains a named, citable record (this ADR) of which of its own
  primitives are considered portfolio-generalizable, which constrains future
  changes to `score.py`/`publish.py`: a change to the changelog format,
  provenance-block shape, or tiering rule is now a change to a documented
  pattern, not just an internal implementation detail.
- `docs/standards-contribution/HONESTY-AS-A-FEATURE.md` is a draft artifact
  for the portfolio owner to review and, when a second repo is ready to
  adopt the pattern, copy into `portfolio-standards` as a new standard (or a
  section of an existing one) and cut a `standards_version` bump. Until that
  happens, the draft has no effect outside this repo — it is documentation,
  not a live standard.
- No code changes. `score.py` and `publish.py` are unchanged; this is a
  documentation-only extraction of an existing pattern.
