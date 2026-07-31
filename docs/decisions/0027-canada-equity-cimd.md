# 0027: A Canada equity overlay from the CIMD, presented within-Canada

Status: accepted (2026-07)

## Context

ADR 0026 made the scorecard country-aware and shipped the Canada pilot (three
agencies), and its equity update found that Canada is the one country with a
turnkey ACS analogue: the Statistics Canada Canadian Index of Multiple
Deprivation (CIMD), an open, pre-computed, small-area deprivation index. The US
equity overlay does not extend abroad (it is state-level ACS), so a Canadian
agency currently shows no need context. This ADR scopes adding one from the CIMD.

Feasibility is de-risked; both inputs exist and are fetchable under the
serverless model:

- **CIMD data.** StatCan product 45-20-0001 (open.canada.ca dataset
  `ec6dc8e7-...`), distributed as CSV at the Dissemination Area (DA) level
  (~57,000 DAs, 400-700 people each, finer than a US block group), under the
  Open Government Licence. It scores four dimensions (Residential Instability,
  Economic Dependency, Situational Vulnerability, Ethno-cultural Composition) as
  scores and population quintiles. Note: StatCan issued a variable correction to
  the 2021 index files, so the corrected release is the one to ingest.
- **DA geometry.** The 2021 Census DA boundary files (open.canada.ca dataset
  `ef70dc3b-...`) are published as SHP/GML/FGDB and, usefully, an official ESRI
  REST service. The REST service is queryable (spatial filter, GeoJSON output,
  reprojection to lon/lat), so a run can fetch only the DAs near the pilot
  agencies rather than the whole country. Projection is NAD83 Lambert, so request
  `outSR=4326`.

## Decision

Add a Canada equity overlay as its own module, `cimd.py`, mirroring the
tract-level US pattern (`tract_data.py` + `tract_equity.py`) rather than
extending the ACS model:

- **Do not reuse `EquityIndicators`.** CIMD's four quintile dimensions do not map
  onto the ACS poverty / zero-vehicle / disability fields, and forcing them
  together would misrepresent both. `cimd.py` carries its own small indicator
  type (the four CIMD dimensions plus the overall quintile).
- **Present within-Canada, never cross-country.** Per ADR 0026, the tier is a
  within-Canada quintile, shown as a Canadian measure and explicitly not
  comparable to the US ACS need tier. No single global scale.
- **Reuse the geospatial core.** `tract_equity.py`'s point-in-polygon and
  stop-weighted served-area aggregation are country-agnostic; the DA polygons and
  a per-DA CIMD value feed straight into them, producing a stop-weighted
  served-area deprivation quintile per agency.
- **Fetch is gated and CI-only**, like the ACS overlay: the DA-geometry REST
  pull and the CIMD CSV load run in a dedicated workflow, not the daily scoring
  path, and only for states/provinces with tracked agencies. Heavy geometry is
  never committed.

### The one real methodology decision

CIMD gives four dimensions; the overlay needs one served-area need signal. The
transit-relevant dimensions are **Economic Dependency** and **Situational
Vulnerability** (the closest analogues to the US poverty / vehicle-access /
disability signals); Ethno-cultural Composition and Residential Instability are
deliberately not used as "need," to avoid conflating demographic composition with
disadvantage. Proposal: a served-area tier from the stop-weighted quintile of
those two dimensions, labelled as a within-Canada CIMD measure. This is a
methodology choice and must be written up in `rubric.md` with the CIMD citation,
not left implicit in code.

## The build (ready to pick up)

1. `cimd.py`: `parse_cimd(csv_rows) -> {DAUID: CimdIndicators}` (pure, fixture-
   tested); `parse_da_geometry(geojson) -> {DAUID: Polygon}` (pure, like
   `parse_tract_geometry`); `build_das(...)` join; `served_area_cimd(stops, das)`
   reusing `tract_equity` for the stop-weighted quintile; a gated
   `fetch_da_geometry(bbox)` against the StatCan ESRI REST and a `fetch_cimd()`
   CSV load.
2. A `canada-equity` CLI command + workflow (mirror the ACS `equity` command and
   `equity.yml`), publishing a small per-agency `canada-equity.json`.
3. Display: a Canada-specific served-area need line on the Canadian agency pages,
   worded as a within-Canada CIMD measure, alongside (not merged with) the
   existing US equity surfaces.
4. `rubric.md`: the CIMD methodology and its citation.

## Consequences

- Canada becomes the first country with a real equity signal, reinforcing the
  Tier-1 case (turnkey on both feeds and equity), while most other countries
  would still start from population-only geometry (ADR 0026 update).
- The overlay is honestly scoped: within-Canada quintiles, transit-relevant
  dimensions only, gated fetch, no cross-country comparison.
- It adds a second equity model to maintain. That is deliberate: one honest
  country-specific index beats a forced fit onto the US model.

## Alternatives considered

- **Force CIMD into `EquityIndicators`** - rejected: the fields do not
  correspond, so the mapping would be fictional.
- **A global gridded-population proxy (GHS-POP/WorldPop) for Canada too** -
  rejected here: CIMD is a real deprivation index at fine resolution and openly
  licensed, so Canada should use it; the gridded proxy is the fallback for
  countries with no national index (a later, separate decision).

## Related

ADR 0015 (US equity, state-level), 0026 (internationalization; equity-data
update naming CIMD), and the tract-level data layer (`tract_data.py`) this reuses.

Last verified: 2026-07-17. `cimd.py` and the `canada-equity.yml` workflow
(feeding `/api/v1/canada-equity.json`) are present and match this record;
the StatCan sources themselves were not re-fetched in this pass. Recheck
cadence: on any StatCan CIMD revision or 2021 Census boundary-file update.
