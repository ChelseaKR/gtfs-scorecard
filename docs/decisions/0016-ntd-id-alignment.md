# 0016: Required agency_id presence with optional NTD-ID equality

Status: accepted (updated 2026-07)

## Context

Every RY2026 NTD GTFS submission must provide a stable `agency_id` value for
each reporter represented in the feed. Each value must be unique among those
reporters and crosswalked to the reporter's five-digit NTD ID on the P-50 form.
The feed's `agency_id` does **not** have to equal the NTD ID.

Equality is still a convenient convention for some single-reporter feeds, and
the service plan (Stage 5) calls for showing it. The scorecard must distinguish
that optional, neutral comparison from required presence and the required P-50
crosswalk.

> **Update (2026-07-13):** the original draft said FTA requires `agency_id` to
> equal the NTD ID. A June correction then overcorrected by describing
> `agency_id` presence itself as optional. Current RY2026 policy requires the
> stable feed value and P-50 crosswalk, but not equality between the two
> identifiers. The decision below records that distinction.

Two facts shape how we can check it:

- Presence is observable from agency.txt, whether or not the registry has the
  reporter's NTD ID.
- The base GTFS Schedule specification permits `agency_id` to be omitted from a
  single-agency feed, but an RY2026 NTD submission requires the value. A feed can
  therefore be valid GTFS while still not ready for that NTD submission.

## Decision

Treat `agency_id` presence as a fourth NTD readiness pillar. Add the NTD ID to
the registry as an optional `ntd_id` and compare equality separately as a
standalone, zero-deduction flag in the same section.

- `gtfs.read_agency_ids` reads the distinct `agency_id` values from agency.txt.
- `ntd.assess_id_alignment(feed_agency_ids, ntd_id)` returns one of `aligned`,
  `mismatch`, `missing`, or `unknown`. Missing presence names the required fix;
  mismatch is allowed and asks only for confirmation of the P-50 crosswalk.
- The result rides on the artifact as `ntd_id_alignment`. The presence verdict
  joins published, valid, and current in `ntd_readiness`; the equality row
  renders below those pillars only when there is a value to compare.

Presence affects the NTD-readiness status but not any category grade. Equality
does not affect either.

## Why equality stays a separate flag

Presence is observable from every feed and required in RY2026, so it belongs in
readiness. Equality is only checkable when the registry has the NTD ID and is not
required. Folding equality into readiness would penalize legitimate values and
shared regional feeds. Keeping it adjacent makes the optional convention visible
without misrepresenting it as a filing rule.

## Why neutral when the NTD ID is unknown

When we have no NTD ID on file we cannot compare equality, so that status is
`unknown` with no penalty. The presence pillar still reports whether agency.txt
provides a value. This mirrors the state-level equity overlay degrading to
"unknown" rather than failing
([ADR 0015](0015-equity-overlay-state-level.md)).

## Consequences

- Every US artifact gets an agency_id presence read. The two pilots (Unitrans
  `90142`, Yolobus `90090`) also get a real equality comparison; everyone else
  sees a neutral equality note until their NTD ID is curated in.
- Adding an NTD ID is a one-line registry edit (`ntd_id: "NNNNN"`), so a curator
  or supporter can turn on equality comparison without code.
- Zero category-grade impact, consistent with the other attached blocks
  (recommendations, conformance, routability).
- Older artifacts with `feed_agency_ids` are re-presented with the current
  presence and equality wording without waiting for a rescore.

Last verified: 2026-07-17. `ntd.py` and the registry `ntd_id` field match this
record; the RY2026 policy wording was last checked against FTA guidance in the
2026-07-13 update above, and transit.dot.gov answers automated re-checks with
403. Recheck cadence: each NTD reporting-year policy update, and before any
RY-cycle outreach that cites the requirement.
