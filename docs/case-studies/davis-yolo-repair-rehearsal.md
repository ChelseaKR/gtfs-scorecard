# Davis–Yolo safe repair rehearsal

**Observed:** July 18, 2026

**Status:** independent demonstration, not an agency-published change

This rehearsal asks a narrow question: what can GTFS Scorecard change with
confidence before a feed owner is available to validate anything?

The answer is deliberately small. The tool may trim surrounding whitespace and
recase text that is unambiguously uppercase. It must not guess whether a stop or
vehicle is accessible, invent a fare or technical contact, delete an apparently
unused record, or state a feed-validity window it does not know.

## Results

| Feed | Safe edits | Original | Corrected demonstration | Change |
|---|---:|---:|---:|---:|
| Unitrans | 5 whitespace trims | B, 80.8 | B, 80.8 | 0.0 |
| Yolobus | 2 whitespace trims; 27 case edits | C, 76.4 | C, 77.2 | +0.8 |

Realtime is excluded from both local rescoring runs because a local zip has no
realtime endpoint configuration. The Yolobus rehearsal grade is therefore not
the same measurement as its public scorecard, where realtime can be sampled.

The Unitrans result is a useful non-result: five certain cleanups do not move the
rubric. The score stays put instead of rewarding cosmetic work while higher
impact findings remain unresolved.

For Yolobus, the corrected copy reduced
`mixed_case_recommended_field` from 15 notices to 2 and raised correctness from
90.0 to 92.0. The remaining two notices are abbreviated stop names that deserve
human review rather than automatic rewriting.

## The failed first attempt

The first Yolobus rehearsal exposed a defect in Scorecard's own autofix. It
recased `route_long_name`, but the validator notices were primarily attached to
`route_desc`. The corrected copy looked different while all 15 notices stayed
open.

The recipe now handles both fields. The feeds were regenerated and rescored
after that change. Verification did not merely decorate the result; it changed
the implementation.

## Reproduce the method

Download each public feed to a local path, then run:

```console
scorecard autofix original.zip --out corrected.zip --report autofix.md
scorecard try original.zip --date 2026-07-18 --json-out original.json
scorecard try corrected.zip --date 2026-07-18 --json-out corrected.json
```

The machine-readable [receipt](davis-yolo-repair-rehearsal.json) records the
source URLs, exact SHA-256 values, rubric and validator versions, category
scores, changes, and limits. The source sites state no reusable data license,
so this repository preserves hashes and method without redistributing either
agency's original or corrected zip.

## What remains unknown

- Accessibility findings describe fields in the feed, not verified physical
  accessibility. Only the feed owner can supply or approve those values.
- Fare, contact, and validity metadata need an authoritative source.
- Unused shapes and stops require operational review before deletion.
- Unitrans moved passenger predictions from UmoIQ to Swiftly in March 2026, but
  no public Swiftly GTFS-Realtime endpoint is documented. Its realtime category
  remains unmeasured and neutral.
