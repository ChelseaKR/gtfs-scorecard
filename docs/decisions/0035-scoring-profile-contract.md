# 0035: Identify the scoring profile on every artifact

Status: accepted (2026-07)

## Context

The artifact already records `rubric_version` and `validator_version`, but a
global consumer cannot tell from those fields alone whether a grade claims to
be a universal standard, a jurisdictional compliance result, or this project's
own scoring contract. The current thresholds and weights were informed by
California guidance. They remain useful outside California when their origin
and limits are stated accurately.

## Decision

Add a required, top-level `scoring_profile` block to every newly produced
per-agency artifact:

```json
{
  "id": "gtfs-scorecard-1.1",
  "rubric_version": "1.1",
  "provenance": "GTFS Scorecard's project-authored weights, deductions, thresholds, grade bands, and fix ranking, informed by the California Transit Data Guidelines and the MobilityData gtfs-validator. It is not a worldwide standard or a compliance determination."
}
```

The `gtfs-scorecard` prefix names this project rather than implying an official
GTFS core standard. The profile identifier follows the rubric version because a
change to scoring semantics already requires a rubric-version change. It is separate from
`schema_version`, which describes the artifact shape. The existing top-level
`rubric_version` remains for compatibility.

This change only labels the current scoring contract. It does not recalculate
or move `overall`, `categories`, `top_fixes`, or any grade field. It does not
implement jurisdiction overlays or vary the score by agency location.

## Consequences

- API consumers can compare artifacts under an explicit scoring contract.
- California thresholds are described as provenance and project choices, not
  worldwide authority.
- Existing consumers that tolerate additive fields continue unchanged.
- A future jurisdiction overlay needs its own contract and decision; it cannot
  silently alter `gtfs-scorecard-1.1`.
