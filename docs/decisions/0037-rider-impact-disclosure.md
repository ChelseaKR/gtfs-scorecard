# ADR 0037: expose a closed rider-impact disclosure on scorecards

**Status:** Accepted (2026-07-12)

## Context

The scorecard is designed for agency managers and staff who support them. Its
grade and prioritized fixes must remain the primary workflow. Riders can still
benefit from a plain summary of the data their trip-planning tools may receive,
but a feed-quality score must not be presented as a rating of transit service.

## Decision

Place a native, closed `details` disclosure immediately after "Top things to
fix" on static and interactive agency scorecards. It summarizes only fields
already published in the scorecard artifact:

- the schedule-data visibility window;
- stated accessibility-data coverage, explicitly distinguished from physical
  usability;
- whether fare information is published or the service is marked fare-free;
- sampled live-arrival availability and scheduled-trip coverage.

Missing or unmeasured fields use neutral "not known from this scorecard" copy.
The disclosure states that it does not rate service reliability and directs
riders to confirm alerts, fares, and accessibility accommodations with the
operator before traveling.

The disclosure adds no route, backend, personal data, analytics, scoring, or
artifact-schema field. Static and browser renderers derive the same copy from
the same existing artifact fields. Native `details` and `summary` provide the
keyboard interaction without custom scripting.

## Consequences

- The agency grade and fixes remain visible before any rider-oriented detail.
- Riders gain a bounded interpretation of what the feed can tell an app.
- Unknown data cannot be mistaken for a negative service finding.
- A future rider-facing service-reliability product requires its own evidence,
  privacy review, and product decision.
