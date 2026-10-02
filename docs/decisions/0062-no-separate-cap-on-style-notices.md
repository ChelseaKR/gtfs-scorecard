# ADR 0062: No separate cap on style notices

**Status:** Accepted (2026-10-01)

## Context

An outside review of VTA's grade raised a rubric question. VTA's published
artifact (snapshot 2026-08-07, rubric 1.3) has a complete rider-experience
layer (completeness 100, accessibility marked on every stop) and grades
F 49.4. The review read the F as driven largely by 9,620
`mixed_case_recommended_field` notices, and asked that a capitalization style
notice not be able to sink an otherwise complete feed. The proposed fix was to
cap what that notice, and similar cosmetic recommendation-level notices, can
cost correctness.

The arithmetic says otherwise. Correctness deducts per distinct notice code,
not per instance (`docs/rubric.md`, Correctness): a WARNING code costs 4
points, times 2 once it passes 50 instances, so 8 at most. That bound is
already a cap.

| VTA | Correctness | Freshness | Completeness | Overall |
|---|---|---|---|---|
| Published 2026-08-07 | 39.5 | 3.3 | 100.0 | F 49.4 |
| Same, mixed-case notice removed | 47.5 | 3.3 | 100.0 | F 52.9 |
| Same, freshness at 100 | 39.5 | 100.0 | 100.0 | C 73.5 |
| Live feed scored 2026-10-01 | 47.5 | 40.0 | 100.0 | D 62.0 |

In the published artifact the mixed-case notice cost 8.0 of the 60.5
correctness points lost; the other 52.5 came from 13 other codes, including
shape-distance, stop-placement, and expired-calendar warnings that are not
style. Its 3.5 overall points (realtime is unmeasured for VTA, so correctness
carries 35/80 of the weight) could not move the grade out of F. The F came from
freshness: the feed then had two days of runway. On the live feed of 2026-10-01
(version 2026-08-27_10:32), the mixed-case notice (8,243 instances) again costs
8.0 points, and VTA grades D 62.0 with "runs out in 24 days" as its top fix.

A wider cap over a group of presentation notices was also checked. On the
published artifact the candidates (`mixed_case_recommended_field`,
`route_long_name_contains_short_name`, `route_short_name_too_long`,
`trip_headsign_matches_intermediate_stop`) total 19 points. Capping the group
at 8 would raise correctness by 11 and the overall score by about 4.8, to
F 54.2. On the live feed the same group totals 17 points.

## Decision

Apply no separate cap to style notices in this rubric version. Document the
bound the per-code rule already gives, with VTA as the worked example, in
`docs/rubric.md`.

The premise behind the cap did not hold for the feed that raised it. A group
cap would be a new judgment about which validator notices are "cosmetic", and
GTFS Best Practices does not treat capitalization as cosmetic: it asks for
mixed case on "all customer-facing text strings", and the scorecard's own fix
page explains that screen readers can spell out ALL CAPS letter by letter.
Grouping and discounting validator notices would also step away from the
ecosystem boundary in `docs/rubric.md`, where the canonical validator owns
which notices exist and at what severity.

## Consequences

- No score changes. VTA's grade moves only with its feed: publishing service
  60 or more days out would take the live feed from D 62.0 to about C 77.
- The rubric now states the per-code bound in words, so a reader who sees
  thousands of instances of one notice can tell it costs at most 8 points.
- If a later review finds a feed where presentation notices together decide a
  letter band, the group-cap option can return through the governed
  rubric-change path with a canary impact report, not as a one-off.

## Alternatives rejected

- **Cap `mixed_case_recommended_field` alone below 8.** Moves VTA by under 3
  points and treats one accessibility-relevant best practice as less than any
  other warning.
- **Cap a style group at 8.** Measured above: VTA stays F on the published
  artifact, and the group's membership would be a scorecard judgment layered
  over the validator's severities.
- **Weight correctness down when completeness is 100.** Couples two
  independent categories; a complete accessibility layer does not make a
  misplaced stop correct.
