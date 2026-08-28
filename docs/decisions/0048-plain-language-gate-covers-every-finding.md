# ADR 0048: The plain-language gate reads every finding the scorecard publishes, and refuses what it cannot read

**Status:** Accepted (2026-08-27)

## Context

`CLAUDE.md` states the promise the whole product rests on: every metric carries
a plain-language explanation, a reason a rider or agency should care, and a
concrete fix. FIX-08 shipped the mechanism that was supposed to hold that
promise mechanically. `scripts/check_readability.py` is merge-blocking through
`make verify` and `ci.yml`, it measures average sentence length and a Flesch
reading-ease estimate, and its closing line has always read:

> All 38 curated translations clear the plain-language bars.

The word doing the work in that sentence is "curated". The gate iterated
`notices.TRANSLATIONS`, the table of wording for MobilityData validator notice
codes. It never read the other family.

Roughly half the finding text on an agency page is not a validator translation.
It is written inline at a `Finding(...)` call in the scorers themselves:
`accessibility.py`, `completeness.py`, `fares.py`, `flex.py`, `metrics.py`,
`pathways.py`, `routability.py`, `rt.py`. Those are the wheelchair findings, the
fare-media findings, the step-free-route findings, the realtime findings, and
the expired-calendar findings. Forty construction sites, 118 measurable
strings, none of them ever seen by the gate whose job is to see them.

Measured against the bars the gate already enforced, 23 of those strings missed
one or both, 29 breaches in total. The two worst were on the copy that matters
most to the reader this project is built for:

- `scorecard_planned_service_boundary.why`, shipped the same day as ADR 0047,
  ran to a 32-word sentence at Flesch 36.9. It was the sentence written to stop
  a campus system being told its feed had lapsed.
- `scorecard_station_missing_step_free_data.why`, the finding that tells a
  wheelchair user's agency why pathways and levels matter, ran 28 words.

This is the defect class the repo keeps finding in itself: a guardrail that is
present, green, and structurally incapable of failing over most of the surface
it appears to protect. `test_required_status_checks.py` states the principle
for CI jobs already: there is no third option where something quietly runs and
blocks nothing.

## Decision

The gate measures an inventory, not a table.

`scorecard_pipeline.reader_copy` enumerates both families of reader-facing
finding copy: the curated table, read at run time, and every `Finding(...)`
construction site in the package, read from the source with `ast`. Source
rather than execution is deliberate. A scorer emits its finding only when a feed
trips it, so a fixture-driven sweep would under-cover precisely the rare
findings nobody re-reads.

The inventory fails closed. Each `what`, `why` and `fix` argument must land in
one of three accounted-for shapes:

1. **Authored.** A literal, an f-string, a conditional over literals, or a
   concatenation of those. Values the feed supplies at run time become a fixed
   stand-in, so the gate judges the sentence rather than the numbers. A sentence
   that can read two ways is measured both ways, not once and luckily.
2. **Taken from the curated table.** `what=t.what`, where the attribute name is
   the field being filled. The table is measured directly.
3. **Read back from a published artifact.** `d["what"]` or `d.get("what", ...)`,
   where the key is the field being filled. That copy was authored somewhere
   this inventory already reads.

Anything else raises `UnreadableCopy` naming the file, the line and the field.
A near-miss is not a deferral: `what=t.summary` and `d.get("summary", "")` both
raise, because a deferral that matches loosely is a hole the next author falls
into.

Deferrals are printed, never silent. The gate ends with what it did not measure
and why, so the six deferred fields are a stated exclusion rather than an
absence a reader has to notice.

Two exclusions are kept from the previous gate and restated rather than quietly
inherited. Effort hints stay out: they are fragments ("One setting."), not
prose. The generated fallback for a notice code with no curated entry stays out
because it is assembled from the code and a rule URL, so measuring it would
measure the code rather than the writing. The curated-coverage metric on
`/problems/` remains its measure, as FIX-08 intended.

The thresholds do not move. Every string that missed a bar was rewritten
instead, which is what the gate's own comment has always instructed: never
loosen them to admit one hard string.

## Consequences

The claim the gate makes is now the claim it can support. It reads 232 strings
where it read 114, and its closing line names both families and their counts.

Twenty-three findings read better on every agency page that carries them. The
planned-service-boundary sentence is three short sentences instead of one
32-word sentence with an em dash in the middle, and it keeps ADR 0047's meaning
exactly: a planned change, not a lapse, and the next period still has to be
published. The step-free-route finding, the fare-discount finding, the
single-stop-trip finding and the realtime findings all say the same thing in
words a manager can read once.

Every new `Finding(...)` is now gated. An author who writes a dense sentence
gets a failing `make verify` with the measured numbers and the string's label;
an author who builds copy in a shape the inventory cannot read gets a failure
naming the site rather than a silent pass. The second half is the part that
makes this a ratchet rather than a snapshot: coverage cannot quietly narrow
again, because narrowing it requires a shape that raises.

The inventory has two stated limits. A value interpolated at run time is
measured as a stand-in, so a finding whose interpolated phrase is itself dense
is under-measured; this is visible in the source and bounded, because a phrase
assigned once in the same function is resolved properly rather than stubbed. And
the inventory covers finding copy only. Category summaries, the recommendation
block, the consequence prose, and the page chrome in `render_site.py` are the
next families and are not covered here.

No score, grade, weight, threshold, tier, or artifact schema moved. This is a
gate and the wording it gates.
