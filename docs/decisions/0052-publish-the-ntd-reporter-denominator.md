# ADR 0052: The NTD page publishes the reporter denominator, in reporter units, or nothing

**Status:** Accepted (2026-08-27)

## Context

`/ntd/` says "45.0% of 1,125 tracked feeds look ready to certify against four
feed checks for RY2026". The sentence is careful and the denominator is stated:
it is this project's registry.

It is not the denominator the reader wants. The RY2026 rule applies to NTD
*reporters*, not to feeds this project happened to discover, and an FTA reviewer
or a Caltrans district liaison opening the page asks one question first: how
many reporters obligated to publish GTFS have nothing discoverable at all. That
population is the one that cannot be "one fix from ready", because there is no
feed to fix (#278).

The page could not see them, and the reason was structural. ADR 0018 populates
`ntd_id` from a feed outward: the Transitland crosswalk maps a feed's URL to its
operator's NTD ID, and any URL the Atlas links to more than one ID is dropped.
That is the right conservative call for stamping IDs, and it closes the
population by construction. A reporter with no feed in the Atlas can never enter
the crosswalk, so it can never be counted as missing.

The join was run the other way on 2026-08-15. `ntd_coverage.py` starts from
FTA's own RY2024 reporter roster, places each reporter in exactly one match
tier, and the write-up is
`docs/findings/2026-08-15-ntd-reporters-without-a-discoverable-feed.md`. The
work landed, and `data/ntd/PROVENANCE.md` then said in as many words what
happened to it: "Neither is read by the pipeline, the site, or the public API."

An answer nobody can read is not published.

## Decision

Publish it, on `/ntd/` and in `ntd.json`, from the committed snapshot, with
three guardrails the issue attaches to the number.

**Reporter counts are reporter counts.** The section says so, states its own
denominator, and says plainly that the 1,253 reporters and the 1,125 tracked
feeds are different units that are never added: one operator can publish several
feed records, and a regional feed can carry many operators. The existing
tracked-feed line is untouched beside it, because it is a different, honest
measurement.

**The range is published at both ends.** Between 473 and 641 reporters have no
feed discoverable in any open catalogue read. The low end counts a shared rare
word in an agency name as a match; the high end does not. That gap is how wide a
name-based join is, and the 168 reporters matched on name overlap alone are
reported on their own line and counted on neither side. Averaging the ends, or
publishing one of them alone, would be the overclaim.

**A reporter with no discoverable feed is a measurement limit, not a finding.**
Nobody is graded, nothing is shown as a zero, and the page says the fix may
belong to FTA's own crosswalk or to a catalogue rather than to the agency. This
is the neutral-treatment rule the rubric already applies to an agency without
realtime, with more force: the observation here is about discoverability, and
the agency may have done nothing wrong at all.

**It fails closed.** `published_reporter_coverage` returns nothing, and the
section does not render, when the snapshot is missing or unreadable, when it
does not declare `unit: ntd_reporters`, when its tier set is incomplete, or when
its tiers do not sum to its own `obligated_reporters`. Publishing nothing is the
honest outcome, because a reporter count that does not reconcile would still
read to a visitor as the real denominator.

## Consequences

`/ntd/` answers the reporter-side question for the first time, and
`ntd.json` carries the same counts under an additive `reporter_coverage` block.
The snapshot is now a published input rather than analysis output, which
`data/ntd/PROVENANCE.md` records along with the reconciliation rule that guards
it.

The number is bounded by things this ADR does not fix and should not imply it
does. The Mobility Database leg is deliberately weaker than it could be, because
`files.mobilitydatabase.org/robots.txt` disallows the v2 catalog; the finding
prices that decision at roughly 187 reporters and leaves it open. The strong
tiers miss whenever an agency's legal name and its brand differ, which is
common. And the snapshot is RY2024, retrieved once. None of that is hidden: the
page dates the snapshot and points at the provenance file, and the finding
carries the full method.

Refreshing the snapshot is still a manual, network-touching act run by
`pipeline/scripts/ntd_reporter_coverage.py`. Nothing here schedules it, and a
future report year is a curation decision rather than a code change.

No score, grade, weight, threshold, tier, cohort rule, or per-agency artifact
schema moves. No agency is graded on any number in this section.
