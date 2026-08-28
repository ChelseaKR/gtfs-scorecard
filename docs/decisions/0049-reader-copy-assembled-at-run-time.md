# ADR 0049: Copy assembled at run time is measured by exhausting its branches, not by reading its source

**Status:** Accepted (2026-08-27). Extends ADR 0048; does not supersede it.

## Context

ADR 0048 put every `Finding(...)` site under the plain-language gate by reading
the package source. It closed by naming what it did not cover: "Category
summaries, the recommendation block, the consequence prose, and the page chrome
in `render_site.py` are the next families and are not covered here."

Working through that list changed two of its four entries.

**The recommendation block was already covered.** `recommend.gather_recommendations`
authors no wording of its own. It runs the fares, flexible-service and
accessibility checks and serializes the `Finding` objects they return, and ADR
0048 already gates every one of those. There is nothing to add, which is worth
recording so the next reader does not go looking.

**The remaining families are not shaped like findings.** A finding is written
whole at one site. A category summary is not. `metrics.freshness` picks its
sentence from a six-branch chain, `completeness` interpolates a fares sentence
chosen elsewhere, and `rt._realtime_summary` builds a clause list and joins it,
choosing clauses by what the sampling window contained. `consequence_line` and
`absence_notes` do the same: one sentence appended per number the pipeline
actually has.

Reading assembled copy from source would mean reimplementing the assembly. The
guarantee that made source reading worth it, that no rare path is missed, has to
come from somewhere else.

Measuring what the shipped copy actually reads was also overdue. Before this
change, three of the four scored categories led with a sentence no gate had
seen, and `_realtime_summary` was the worst text on the page by the project's
own measure: a semicolon-joined clause list running to 27 words at a Flesch
score as low as -9.8, sitting directly above findings that all clear 50.

## Decision

Two mechanisms, chosen by how the copy is written.

**Copy written at a construction site is read from source**, as in ADR 0048.
`CategoryResult(...)`'s `summary` joins `Finding(...)`'s three fields as a
gated argument, and the evaluator gains what those summaries need:

- A name assigned in several branches now reads as one string per branch rather
  than being refused. ADR 0048 refused a name assigned more than once as
  ambiguous. That was the right call for a finding and the wrong one for a
  summary chosen by an if/elif chain, and reading every branch is strictly more
  coverage than refusing. An assignment the evaluator cannot read still refuses
  the whole name.
- A name may resolve through one further name, with a visited set, so a summary
  that interpolates a sentence built above it resolves to the sentence rather
  than to a numeric stand-in. Before this, `completeness`'s summary was measured
  with its fares sentence replaced by a placeholder.
- Assignments inside a nested function stay in that function's scope. They
  previously leaked into the enclosing one, which invented readings that no page
  can show.

**Copy assembled at run time is measured by running its producer over an input
set that reaches every branch**, and the no-rare-path guarantee is asserted
directly rather than inherited: every authored fragment in the producer's own
source must appear in at least one enumerated output, or `UnmeasuredFragment`
raises naming the fragment and the function. A new branch with new wording that
the input set does not reach fails the gate, so the input set cannot fall behind
the code.

An assembled `summary=` is accounted for only when the function it calls is in
the producer registry. A call to anything else raises like any other
unaccountable shape, so the registry cannot be bypassed by writing a new
assembler.

Outputs are compared with run-time numbers collapsed to a single stand-in, so
two readings that differ only in counts are one measured sentence rather than
dozens.

Three producers are registered: `rt._realtime_summary`,
`consequence.reach_sentence` (with `_percent_phrase`, whose wording it emits),
and `consequence`'s line and absence notes.

## Consequences

The gate reads 294 strings across three families where ADR 0048 left it at 232
across two: 114 curated, 137 authored, 43 assembled. Thirty-eight failures on
the pre-change copy, none after.

`_realtime_summary` is now one short sentence per thing measured instead of a
joined clause list. That is the visible change: the realtime category's lead
sentence reads like the rest of the page. "Vehicle position plausibility was not
measurable" became "We could not check whether vehicles were on their route",
which is also the first version of that sentence a transit manager can act on.

The correctness summary keeps naming MobilityData, and the ridership notes keep
naming the National Transit Database. Both are attributions the reader needs,
and both sentences were restructured around them rather than dropping them. No
threshold moved, and no allowance was added for a proper noun. Where the
formula reads a name as hard, the sentence around it got easier.

The producer registry has a stated cost. Its input sets are hand-written, and a
producer whose branches multiply would need a larger set to stay green. The
fragment assertion makes that cost visible at the moment it is incurred rather
than letting coverage lapse quietly, which is the trade this repo makes
everywhere else.

Two families remain uncovered and are stated rather than implied: the page
chrome in `render_site.py` and `site_shell.py`, and the 41 authored fix guides
in `docs/fixes/`. Neither is finding or category copy, and both are large enough
to be their own work.

No score, grade, weight, threshold, tier, or artifact schema moved.
