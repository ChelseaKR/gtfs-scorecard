# ADR 0050: Two controls that read as enforcement are made able to fail

**Status:** Accepted (2026-08-27)

## Context

This repository keeps finding the same defect in itself: a control that is
present, green, and structurally incapable of failing over the thing it appears
to protect. `test_required_status_checks.py` states the principle for CI jobs,
and ADR 0048 and ADR 0049 applied it to the plain-language gate. Two more
instances were open as issues.

**The complexity register was maintained by hand.**
`docs/lint-complexity-ratchet.md` lists every function over the
`max-complexity = 10` floor, and its own header tells a maintainer to re-run
ruff and rewrite the table whenever a row changes. Nothing enforced that. The
drift was measured twice: on 2026-08-15, 13 of 15 recorded numbers were wrong,
two entries had been refactored under the floor and were still listed, and four
live suppressions had no row at all. Five workdays later, in PR #307, four rows
had drifted again (#309). A register of quality debt whose numbers only move
when somebody remembers a command understates the debt by default, and a ratchet
that can silently loosen is not a ratchet.

**The published weight-sensitivity study graded the wrong number.** `score.py`
documents the failure mode in its own comment: a raw 79.96875 publishes as
"80.0", and grading the unrounded value labelled it C while `docs/rubric.md` and
the published `scoring.json` both say 80 is a B. Nine live artifacts carried a
letter that contradicted their own printed score before `published_overall()`
and `publish._validate_published_overall()` were added.

That guard is real and it is narrow: it runs inside `publish()`. `sensitivity.py`
reimplements its own scoring and grading path, and `cli._cmd_sensitivity` writes
`data/artifacts/sensitivity.json` directly, so the guard never saw it (#310).
The study exists to let a reader judge whether the national grade picture is an
artifact of the category weights, and the how-to-read page quotes its headline.
For a feed on a band edge the study answered backwards. Measured on the
pre-change code, with correctness 91.379 and freshness 60 renormalizing to
exactly 79.96875:

```
ARITHMETIC: correctness up   -> 1 (should be 0)
ARITHMETIC: correctness down -> 0 (should be 1)
```

Both perturbations were counted the wrong way round, because the baseline letter
the study compared against was one band below the letter that feed publishes.

## Decision

**The register is compared with ruff on every run.**
`pipeline/tests/test_complexity_ratchet.py` parses the tracked-exceptions table
and fails when a function over the floor has no row, a row names a function no
longer over the floor, a recorded number disagrees with ruff, the table is out
of its declared descending order, a live `# noqa: C901` has no row, or a figure
quoted in the file's own prose has drifted. Every failure prints the regenerated
table, so a sync is a copy-paste rather than a manual reconciliation.

File and line are deliberately not gated. They churn on every unrelated edit
above a function, and gating them would make the register noisy rather than
accurate. They are still regenerated in the printed table so a sync corrects
them for free.

The prose clause is not decoration. The check's first run found
`docs/lint-complexity-ratchet.md` still describing `render_site` as complexity
54 in its Plan section, three paragraphs below a table that had been corrected
to 55 the same day. A hand-maintained figure drifts wherever it sits.

**Every letter grade outside `score.py` is derived from the published score.**
`sensitivity.published_letter()` rounds through `published_score()` before
grading, and `render_site._grade_band()` does the same. The arithmetic fix alone
would leave the shape intact, so `test_published_grade_path.py` also asserts the
structure: no module outside `score.py` may call `letter_grade` on anything but
a `published_score(...)` result. Before this change that check named three
sites; after it, none.

`_grade_band`'s callers already pass a published score, so rounding there
changes no output. It is done anyway, because a rule with one exception is a
rule the next author has to remember rather than one the suite enforces.

## Consequences

The complexity register cannot understate the debt again without a red build,
and the next person to add a `# noqa: C901` is told to write its row rather than
discovering the convention later. The register's contents are unchanged by this
ADR beyond the one stale prose figure: nothing was refactored here, and the
debt is exactly what it was.

The published sensitivity study now counts churn against the letter each feed
publishes. `max_grade_change_pct` and the per-perturbation counts will move for
feeds sitting on a band edge, which `score.py` names several of at exactly
80.0/B with `margin_to_lower_band: 0.0`. That is a correction to a published
figure, not a methodology change: the rubric, the weights, the bands and the
scores are untouched, and the study now reports what the rubric already said.

Neither change moves a grade, a score, a weight, a threshold, a tier, or an
artifact schema. `sensitivity.json` keeps its shape; the numbers inside it are
corrected.
