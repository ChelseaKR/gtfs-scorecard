# Interactivity and visualization roadmap

This roadmap plans how to add more interactive data visualization to the
scorecard without breaking its constraints. It is triaged into shippable pieces,
each of which lands as its own pull request.

The work is aimed at one reader in particular: a state liaison or customer
success manager who has the scorecard open on a phone during a check-in call
with a small agency, and needs to show "here is how your data is doing and the
few things to fix" without leaving the conversation to read a table.

## Constraints every idea must respect

These come from the project's quality bar and do not move:

- Static hosting only. The frontend reads pre-computed JSON, GeoJSON, and
  PMTiles artifacts. No API server, no database, no runtime queries.
- Vanilla JavaScript, no build step, no framework. Charts today are hand-rolled
  inline SVG plus CSS bars. Maps use MapLibre GL JS 4.7.1 and PMTiles 3.2.1.
- WCAG 2.2 AAA, visibly. Full keyboard operation, a text alternative for every
  chart and map, colour is never the only signal, `prefers-reduced-motion` is
  honoured, and AAA contrast holds across the light, high-contrast, and dark
  themes.
- Mobile-first, under two seconds on 4G, with a small total CSS and JS budget
  (roughly 130KB today).

## How this was researched

Two inputs fed this plan. First, an inventory of what the site renders today and
how (MapLibre maps, hand-rolled SVG sparklines and choropleths, CSS meter bars,
static HTML tables, and the precomputed JSON flow). Of the comparison and trend pages, two already carry a visual: the equity page a
static SVG choropleth (ADR 0022) and the trend page an autoscaled SVG line chart
with a by-date table. The leaderboard, NTD, and realtime pages are still plain
tables.

Second, a multi-source web
research pass across five angles: accessible interactive visualization, tiny
dependency-free charting, MapLibre and PMTiles interaction patterns, transit and
civic data-quality dashboards, and facilitator-led live sessions. Each claim was
checked with a three-vote adversarial pass; 23 of 25 reviewed claims survived,
and 2 were rejected.

Two of the five angles produced no claims that survived verification: what
comparable transit and civic dashboards (Cal-ITP, MobilityData, the FTA National
Transit Database) actually do, and the facilitator and guided-session patterns.
Recommendations that rest on those angles are marked below as lower confidence.

## The governing principle

Every new visualization ships as a set of three parts, not one:

1. the visual, drawn in SVG (or a map canvas), marked `aria-hidden="true"`;
2. a visually hidden data table carrying the same numbers as text, using the
   USWDS `.usa-sr-only` pattern; and
3. a short plain-language summary line stating the takeaway.

The whole thing stays keyboard-operable. This is the single most reusable and
best-supported pattern found, and the site already does part of it (the trend
sparkline carries its full series in an `aria-label`). Making the three-part
pattern a shared helper is the backbone of the charting work below.

A related finding shapes the approach: the ARIA graphics roles
(`graphics-document`, and the never-standardized `graphics-datachart` and
friends) have weak screen-reader support. They can supplement the markup, but
the hidden data table, not ARIA graphics roles, is what actually delivers the
text alternative for AAA.

Sources: USWDS Data visualizations guidance; UK Government Analysis Function,
"Data visualisation: testing dashboards for design and accessibility"; W3C
WAI-ARIA Authoring Practices; W3C Graphics Module 1.0; Minnesota IT Accessibility
Guide for Interactive Web Maps.

## Verified findings that drive the plan

- Maps can become interactive with no new dependency. MapLibre 4.7.1 already
  supports per-feature hover and selection through `map.setFeatureState`, read
  back in paint properties with a `case` plus `feature-state` expression, and
  the site already uses `maplibregl.Popup`. (W3C and MapLibre docs; confirmed
  against the version in use.)
- For a map to reach AAA, add a keyboard equivalent for click, such as a
  centre-crosshair "press to inspect the feature at centre" model, pair every
  map with a synced data table, and move focus to that table after a filter or
  search runs. (Minnesota IT.)
- Small SVG charts stay tiny and accessible-friendly. Dependency-free sparkline
  libraries run about 1 to 6KB and need no build step, and SVG keeps the data in
  the DOM where the site's existing inline-SVG pattern already lives. The site
  can also keep hand-rolling these, which avoids an unmaintained dependency.
- Richer interactive time series (zoom, live-value legend, cursor sync) would
  mean uPlot, at about 48KB. It is Canvas-based with no accessibility tree, so it
  would take a large slice of the byte budget and force a manual table and ARIA
  fallback. It is not the right default here (see decisions below).
- The official `maplibre-gl-compare` plugin gives a swipe slider that syncs two
  maps, useful for before-and-after or two-agency benchmarking. It instantiates
  two map instances and needs a non-swipe alternative, so it is a later,
  gated addition.
- On a static site, application state (selected agency, filters, sort, drilled
  category) can live in the URL and be restored on load, which makes any view
  shareable with no backend. (Lower confidence: this rests on the facilitator
  angle, which did not survive verification, but it is a well-established
  pattern.)

## Decisions and deviations

- National trend chart uses hand-rolled accessible SVG, not uPlot. uPlot's 48KB
  and Canvas rendering conflict with both the byte budget and the AAA text
  alternative. A hand-rolled SVG line with a hidden table stays in the site's
  existing idiom and is cheaper to keep accessible.
- The equity page already renders a static SVG choropleth (ADR 0022), so the work
  there is interactivity, not a new visual: link the choropleth to its state
  table with the same brushing used on the route map.
- A guided product tour (for example Driver.js) is deferred, not scheduled. It
  would add a dependency, it overlaps the existing "how to read" page, and the
  facilitator research angle did not survive verification. Revisit only if a real
  need shows up in use.

## The pull requests

Each lands independently, in this order, so the highest-value and lowest-risk
work ships first.

1. **This roadmap.** Captures the plan and the citations.
2. **Interactive maps.** Feature-state hover and selection on the per-agency
   route and stop map and the national cluster and route maps; linked
   highlighting between a map feature and its table row; a keyboard model for
   selecting a feature; focus moved to the results table after a filter runs.
3. **Interactive and small-multiple sparklines.** Done. The agency trend
   sparkline (static and app) carries a hover readout at every check (a native
   `<title>` dot with date and score), and the app gained the same "Show the
   numbers" keyboard/screen-reader table the static page already had. Small
   autoscaled trend sparklines sit beside rows on the pulse rankings, NTD
   one-fix, and realtime most-reliable tables (an em dash until a feed has two
   checks). The three-part accessible pattern is a shared helper
   (`_spark_svg`/`_spark_mini` in `render_site.py`), which both trend charts
   and the row minis now draw through.
4. **Equity choropleth.** Link the existing static SVG choropleth to its state
   table with the same brushing used on the route map (the choropleth already
   renders).
5. **National trend chart.** The trend page already draws this line, so the work
   is to enhance it: a hover dot at every date and a visible score-range caption.
6. **Deep-link URL state.** Encode the current view (filters, sort, search) in
   the URL so a specific view can be pre-staged or shared before a call. Lower
   confidence, high call-day value.
7. **Compare two agencies.** A no-dependency side-by-side comparison table
   (overall grade, category bars, top fixes), shareable by URL. This replaced the
   planned `maplibre-gl-compare` swipe: that plugin is built for two overlapping
   layers of the same area, but the data keeps only current per-agency geometry
   and agencies sit in different places, and it was the one runtime dependency.
8. **Methodology sandbox.** _(shipped, EXP-06)_ A dependency-free what-if on the
   `/how-to-read/` page: four range sliders reweight the rubric categories and the
   page recomputes, entirely client-side, how many agencies would change letter
   grade. It fetches the published `api/v1/scoring.json` (weights + grade bands)
   and `api/v1/agencies.json` (each agency's measured category scores), so the
   default weights, band thresholds, and the renormalized overall-score formula
   all come from the published data at runtime — the sandbox and the pipeline
   agree by construction (the FIX-03 single-source intent, without a schema
   change). Degrades to the static rubric explanation when scripting or the fetch
   is unavailable.

## Open questions to settle as the work lands

- What is the real remaining CSS and JS headroom under the budget after today's
  code? That decides whether anything heavier than sparkline-class ever fits.
- How should pointer-only interactions (hover popups, the compare swipe) behave
  on touch and by keyboard so they satisfy both the phone demo and AAA?
- Does the equity page need a map to meet its goal, or is a well-summarized,
  sortable table the better minimal and AAA-safe choice?
- What do Cal-ITP, MobilityData, and the NTD actually show for coverage, trend,
  and equity, and which of those patterns are worth adopting? This angle
  returned no verified evidence and is worth a direct look.
