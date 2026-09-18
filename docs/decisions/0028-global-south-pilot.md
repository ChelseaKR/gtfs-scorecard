# 0028: Global South Tier — LMIC feed-quality pilot (Tier 3 expansion)

Status: accepted (2026-07)

## Context

GAP-2 research (phase 2 feature expansion) investigated whether the GTFS scorecard can serve the Global South — low- and middle-income countries (LMICs) where informal transit (matatus, jeepneys, colectivos) dominates and where a data-quality tool could have marginal impact. Findings:

- **GTFS is genuinely the lingua franca.** 16+ cities across Africa, Asia, and Latin America have produced informal transit data in GTFS, using the Digital Matatus methodology (Nairobi, 2012–2014) as the canonical playbook.
- **Marginal impact is highest where no data exists.** Informal networks move the majority of riders in fast-growing cities (Dar es Salaam ~98%, Accra ~86%, Nairobi ~70%) yet in most places have no official data. A scorecard's existence/freshness metrics are the first-order value.
- **The scorecard already works.** Rubric categories (correctness, freshness, completeness, realtime) transfer directly; GTFS-Flex (adopted March 2024) gives the vocabulary for flexible/paratransit services.
- **Sustainability is the blocker, not technology.** WhereIsMyTransit (~$27M raised) shut down in 2023; many mapathon feeds go stale without maintenance funding. The scorecard can surface staleness but can't fix under-funding.

## Decision

**Do not build a national, per-country Global South feed-quality overlay.** Instead, ship a **bounded, pilot demonstrator** with 3–5 agencies in high-potential cities, clearly labeled a pilot over a few countries, not a scored national metric.

The scorecard's core rubric is suitable for LMICs as-is. A pilot proves value and surfaces what localization is needed (language, currency, local modes) before scaling.

## Pilot Scope (Tier 3)

**Countries:** Kenya, Ghana, Philippines (one per region; high digital matatus activity + open data momentum)

**Agencies** (3–5, mixed formal + informal):
- **Nairobi, Kenya:** Nairobi City County (formal) + Digital Matatus (informal/community)
- **Accra, Ghana:** Adom Transit (formal minibus) + OpenStreetMap community mapping (informal)
- **Metro Manila, Philippines:** Sakay.ph (formal multi-modal including jeepneys) OR pick one jeepney operator if formal data is unavailable

(These are illustrative; exact agencies TBD per data availability and community partnership.)

**Scope:**
- Use the existing rubric as-is (correctness, freshness, completeness, realtime).
- No custom LMIC-specific scoring (avoid comparing tropics/rural to global standard without research).
- Optional: add a simple **adoption overlay** (e.g., GTFS-Flex coverage, whether informal routes are mapped) to show what features operators are already using.
- Label clearly: "GTFS Scorecard Pilot — Global South (3 cities, proof-of-concept)."

## Governance & Partnerships

- **Timing:** Pilot by end of 2026 (after Canada is stable).
- **Partners:** Contact Digital Transport for Africa, MobilityData's Global South program, or local operators directly.
- **Approval:** Before onboarding any new country, confirm data licensing (CCBYSA or equivalent) and operator/community consent.

## Future: When/If to Scale

Scale to national coverage in a country only if:
1. A local steward (government, transit association, or NGO) commits to maintaining the scorecard for that country.
2. The pilot has shown measurable use (city/state planners referencing findings, operators acting on recommendations).
3. Localization is proven necessary (e.g., non-English UI, country-specific completion metrics).

Otherwise, keep it a curated pilot: value demonstration, not scale.

## Migration Path

If a country proves high-impact (e.g., Kenya's Digital Matatus program adopts the scorecard for route verification), the infrastructure is in place:
- The rubric is language-agnostic (just label findings in Swahili / Akan / Tagalog).
- The data is already in the Mobility Database (6,000+ feeds / 99+ countries).
- The pipeline and artifact model scale without code changes (same as Canada + US).

Keep the landing page and docs updated so the pilot is always visible, and users know how to submit their country/agencies for consideration.

## Non-Decision: Global South Equity Overlay

The GAP-2 research included equity overlays (worldpop/GHS-POP gridded population density). This is deferred:
- A national equity metric for LMICs is complex without country-level census/poverty data.
- The pilot demonstrator should focus on the rubric first, then add equity overlays once operators + partners request them.
- Gridded population fallback (GHS-POP) is available globally but adds scope; skip for Tier 3 MVP.

---

**References:**
- ADR 0015: US equity overlay (ACS tracts; model that worked)
- ADR 0026: Canada equity (CIMD; country-specific approach)
- GAP-2 research: Global South GTFS landscape and marginal impact
- GTFS-Flex (official March 2024): vocabulary for paratransit
