# Data visualization

The scorecard uses charts to answer a question faster than prose or a table can.
Charts do not replace exact values, fix guidance, or downloadable data.

## Visual grammar

Choose the form from the relationship in the data:

| Question | Form | Used for |
| --- | --- | --- |
| How did a value change over time? | Line with a dot for every check | Agency and national score history |
| How do percentages compare? | Zero-based horizontal route bars | Capability adoption and problem prevalence |
| How are records distributed across ordered ranges? | Zero-based bucket columns | Current scorecard age |
| Where does one agency sit in a distribution? | Marker on a fixed 0–100 strip | National and size-peer percentiles |
| What is the composition of a whole? | Proportional labelled bands | Grade distribution |
| Which direction did a selected set move? | Two-part movement band | Material national score changes |
| Where is a condition concentrated? | Geographic map with a visible legend | Feed expiry and equity by state |
| What are the exact records? | Table or semantic list | Rankings, state detail, findings, and chart data |

Do not use pie charts, 3D effects, dual axes, area fills that imply volume, or
gauges. Category score meters are zero-based bars and always print the score.

## Shared patterns

`web/src/styles.css` owns the visual grammar so generated pages and the
interactive app stay aligned:

- `.service-chart` and `.service-bars` render ranked percentages. The line
  begins at a circular stop marker, a restrained transit reference that also
  makes the zero baseline visible.
- `.percentile-strip` renders position. It uses a point because a percentile is
  where an agency sits, not an amount it has accumulated.
- `.bucket-chart` renders ordered ranges. It prints the count above every
  zero-based column and names every bucket below it.
- `.movement-chart` summarizes the direction of material changes and states
  that quiet feeds are outside that selected set.
- `.grade-distribution` renders composition with a labelled segment per grade.
- `.trend-chart` and `.trend-data` pair a line with its full numeric table.

Python chart helpers live in `pipeline/src/scorecard_pipeline/render_site.py`.
Interactive equivalents live in `web/src/app.js`. Add a shared pattern before
introducing page-specific chart markup.

## Accessibility and correctness

- Build every chart from semantic HTML or give an SVG a concise accessible
  name. Decorative tracks, fills, and markers are hidden from assistive tech.
- Keep labels and exact values visible. Color reinforces meaning and never
  carries it alone.
- Use a zero baseline for bars. Use a marker, not a filled bar, for position.
- Give time-series charts a numeric table and a plain-language change summary.
- Preserve source order as reading order. Sorting a chart must not make its
  text equivalent disagree.
- Avoid hover-only data. Native titles may supplement, but never contain the
  only copy of, a value.
- Charts must fit at 320 CSS pixels without page-level horizontal scrolling,
  remain legible in light, dark, and high-contrast themes, and print without
  losing labels.
- Do not animate measured values. Reduced-motion preferences must remove any
  surrounding reveal movement.

## Page-level intent

- Agency: lead with grade and score, then show trend, category profile, and
  percentile context. Findings remain an action list, not a chart.
- Program: show grade composition before the worst-first worklist. The chart
  explains the group; the list tells a liaison whom to call.
- National overview: use maps for location, grade bands for composition, lines
  for time, route bars for ranked adoption, prevalence, accessibility coverage,
  and realtime reliability, and bucket columns for operational freshness.
- Comparison and data pages: prefer tables when users need to inspect many
  fields or copy exact records. Small bars can support a row, but must not make
  the table harder to scan.

When a new visualization is proposed, write down the user question, the data
relationship, the text equivalent, and the mobile behavior before choosing the
chart type.
