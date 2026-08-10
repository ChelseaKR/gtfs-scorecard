# Honesty-as-a-Feature Standard (draft contribution)

> **This file is a draft.** It is written in `gtfs-scorecard`
> (`docs/standards-contribution/HONESTY-AS-A-FEATURE.md`) as the concrete
> "STANDARDS contribution" named in `docs/ideation/03-expansions.md` (EXP-17)
> and `docs/decisions/0030-honesty-primitives-standard.md`. It is **not** yet
> part of the shared standards project. Landing
> it there — as a new document or a section folded into an existing one — is a
> portfolio-owner decision gated on a second repo being ready to adopt the
> pattern (EXP-17's stated excellence bar), because that repo pins a
> `standards_version` every consuming repo's `docs/standards/.standards-version`
> follows. Everything below is written in `portfolio-standards`' own voice
> (AUTO-GATE / REVIEW-GATE, "Applies to" table) so it can be copied over with
> minimal editing once that gate opens.

This is the canonical definition of **how a repo that emits a machine
judgment about something — a score, a validation pass, an eval result, a
receipt — keeps that judgment honest under scrutiny**. It owns four
primitives: the methodology-changelog format, the provenance-block shape, the
renormalization rule for partial measurement, and no-shaming finding
tiering. The reference implementation is `gtfs-scorecard`
(`pipeline/src/scorecard_pipeline/score.py`, `publish.py`); this standard
describes the shape every repo's own implementation should take, not that
repo's code.

## 1. When this standard applies

| Repo class | Produces a judgment? | Examples |
|---|---|---|
| Scores, grades, or rates a subject on a rubric | **Yes — mandatory** | `gtfs-scorecard` |
| Validates or certifies conformance to a spec | **Yes — mandatory** | `tods-validate` |
| Runs an automated eval and reports a result | **Yes — mandatory** | private sibling project |
| Issues a receipt or attestation about an outcome | **Yes — mandatory** | `outcome-receipts` |
| Pure internal tool, no judgment surfaced to a reader | `N/A (not a judgment-producing repo)` with that reason in the README | rare |

**There is no silent default.** A repo that emits a score, grade, pass/fail,
or certification and has no methodology changelog, no provenance block, and
no stated renormalization/tiering rule **fails review** — it is asking a
reader to trust an opaque verdict, which is the exact failure mode this
standard exists to close.

## 2. Methodology-changelog format — AUTO-GATE on presence, REVIEW-GATE on quality

Every judgment-producing repo publishes a dated, **newest-first**, plain-
language changelog of its own methodology, in the same machine-readable
artifact the judgment ships in (not only in a repo-root `CHANGELOG.md` a
maintainer reads but a consumer of the artifact never sees).

| Rule | Requirement |
|---|---|
| Versioned | Each methodology (rubric, validator ruleset, eval suite, receipt schema) carries its own version identifier, independent of the repo's SemVer/release tag |
| Dated | Each changelog entry carries the date the version took effect |
| Plain-language | Each entry is a sentence or two a non-maintainer reader can act on ("X now counts toward the score; previously it did not"), not a commit-message fragment |
| Co-published | The changelog (or its current-version entry) ships inside the judgment artifact itself, so a consumer reading one snapshot can tell which methodology produced it without cross-referencing the repo |
| Append-only | Prepend new entries; never edit or delete a past entry's stated effective date or summary — a past judgment's own methodology-changelog entry is itself a historical record |

Reference: `gtfs-scorecard`'s `METHODOLOGY_CHANGELOG` /
`methodology_changelog()` in `score.py`, published as part of `scoring.json`.

## 3. Provenance-block shape — AUTO-GATE

Every emitted judgment carries a provenance block with, at minimum:

| Field | Meaning |
|---|---|
| `methodology_version` | The version of the rubric/ruleset/suite/schema that produced this judgment (gtfs-scorecard: `rubric_version`) |
| `tool_version` | The version of any third-party tool the methodology wraps, when one exists (gtfs-scorecard: `validator_version`, the MobilityData `gtfs-validator` build) |
| `input_fingerprint` | A content hash (or equivalent) of the exact input judged (gtfs-scorecard: `feed.sha256`), so the judgment is reproducible and a re-run against the same input is verifiable |
| fetch/access provenance | How the input was obtained, when that is itself contestable — origin vs. a mirror, the exact URL, the client identity (gtfs-scorecard: the `fetch` block — `source`, `final_url`, `user_agent`) |

This is what lets a reader separate "the subject changed" from "the
methodology changed" from "the tool changed" when a judgment's result moves
between two snapshots — the single most common way a machine judgment loses
a skeptical reader's trust.

## 4. Renormalization rule — AUTO-GATE (rule), REVIEW-GATE (disclosure quality)

When a methodology has multiple weighted sub-measures and one is not
computed for a given subject (a category not yet built, a dimension the
subject doesn't expose, a check that could not run):

- **Redistribute that sub-measure's weight** across the sub-measures that
  were computed. A subject is never scored as if a not-yet-measured
  dimension were a zero, and is never silently excluded from the overall
  judgment either.
- **Publish, in the artifact, exactly which sub-measures were and were not
  computed for this subject**, and why (not built yet, not applicable,
  fetch failed). A judgment that hides its own coverage gaps is less honest
  than one with no gaps to hide.

Reference: `gtfs-scorecard`'s `score.py:build_scorecard` (weight
renormalization) and its `confidence` block in `publish.py` (what a given
run could and could not measure — the EXP-01 measurement-confidence read).

## 5. No-shaming finding tiering — REVIEW-GATE

Findings within a judgment are ranked and framed to keep a reader's
attention on what most affects the people downstream of the judged subject,
not on what looks the worst in aggregate:

| Rule | Requirement |
|---|---|
| Impact-first ranking | Rank findings by their effect on the end user of the judged system (a rider, a resident, a claimant), not by raw count or severity label alone |
| A gap the subject cannot yet close is described neutrally | A dimension the subject has not built (gtfs-scorecard: no realtime feed) is stated as "not yet published," never scored or worded as a failure |
| Every finding is an action | Findings are framed as something the subject's owner can do next, never as a verdict on the subject or its operator |
| Count-scaling caution | A high-count, low-severity issue must not be weighted to look worse than a single high-severity one; count should scale a finding's weight sub-linearly, not linearly, past a moderate threshold, so one systemic-but-minor issue cannot dominate the ranking |

Reference: `gtfs-scorecard`'s `score.py:_fix_tier` / `_fix_priority` (tier 0:
subject is broken or expiring; tier 1: user-experience gap; tier 2:
informational) and its count-multiplier tiers in `metrics.py`
(`COUNT_MULTIPLIER_TIERS`, `WIDESPREAD_MULTIPLIER`).

## 6. Adoption note (for the repo landing this standard)

A repo adopts this standard by implementing the four primitives in its own
pipeline's shape and language — not by importing `gtfs-scorecard` code. The
excellence bar (per EXP-17) is a **second** portfolio repo shipping its own
methodology-changelog and provenance-block pattern derived from this
document, independently of `gtfs-scorecard`'s implementation.

---

Draft source: `gtfs-scorecard`, `docs/decisions/0030-honesty-primitives-standard.md`.
Not yet assigned a place in `portfolio-standards`' document index or
`README.md` table; the portfolio owner decides both when landing this.
