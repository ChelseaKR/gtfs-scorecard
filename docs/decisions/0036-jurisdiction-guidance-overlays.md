# ADR 0036: layer jurisdiction guidance over one scoring contract

**Status:** Accepted (2026-07-12)

## Context

The original standards section mixed universal GTFS practices, a US federal NTD
requirement, California guidance, and state support programs. That presentation
worked for the original California audience but could show US language on the
interactive page for a Canadian agency. The printable Canadian brief also emitted
an empty NTD section.

The scorecard now tracks agencies beyond the United States. Guidance must become
more locally useful without implying that the project has authority to define a
country's compliance rules, and without changing the existing scoring rubric.

## Decision

Keep one versioned scoring contract. Add presentation-only guidance in four
explicit layers:

1. a universal core of GTFS Schedule, GTFS-Realtime, and MobilityData references;
2. the FTA NTD requirement for US agencies only;
3. jurisdiction guidelines keyed by ISO 3166-2 subdivision code, beginning with
   `US-CA`;
4. separately typed support resources, which are never described as scoring or
   compliance authorities.

Python is the source of truth. The constants generator publishes the same records
to the browser app. Both renderers default a missing historical country to `US`,
use `subdivision_code` when present, and temporarily accept known state names as
a US-only migration fallback.

The printable brief and NTD readiness section have an explicit country guard.
Canadian pages receive the universal core and no NTD wording.

## Consequences

- Adding a jurisdiction requires a cited record and an applicability test.
- A support link cannot silently become a guideline.
- Global expansion does not fork grades or thresholds.
- A future change to jurisdiction-specific scoring would require a separate
  scoring-profile decision and schema work; this ADR does not authorize it.
