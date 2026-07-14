# Board-ready report

Generate one agency's scorecard as a single HTML file you can attach to a
board packet, drop into a federal grant application, or print to PDF from any
browser. Everything the document needs travels inside the file: no
stylesheets to fetch, no scripts, no network in the boardroom.

The site already offers a printable board one-pager at
`/agency/<id>/board/`. This report is its offline companion. It renders the
same published artifact fields, so the file and the live page can never tell
different stories.

See the [live Unitrans board one-pager](https://gtfsscorecard.org/agency/unitrans/board/)
for a public example. The workshop package also includes a custom-branded,
self-contained sample generated with this tool.

## What the report contains

- The agency name, check date, overall grade, and trend since the last check.
- The four category scores (Correctness, Freshness, Rider experience,
  Realtime quality) with the same plain-language summaries the site shows.
  A category the pipeline has not measured yet shows "Not yet published" and
  never counts against the grade.
- The top three things to fix, each with its estimated effort, framed so a
  board can see what it is approving.
- NTD GTFS readiness for US agencies: the published, valid, current, and
  agency_id-presence pillars, plus the shapes.txt line for the FTA requirement that reaches
  Reduced, Rural, and Tribal reporters in Report Year 2026. Grant reviewers
  and boards ask about this first, so it gets its own page.
- Score history as a table, once the agency has been checked more than once.
- A methodology footer citing the public rubric, the rubric and validator
  versions, the generation timestamp, and the live scorecard URL.

Every number comes from the agency's published artifact and history. The
generator computes nothing new.

## Generate one

From `pipeline/`:

```
uv run scorecard report --agency unitrans
uv run python -m scorecard_pipeline.report --agency unitrans --out unitrans-report.html
```

Both forms do the same thing. The default output path is
`<agency>-board-report.html` in the current directory.

## Put your program's name on it

A state DOT program or a consultancy preparing packets for the agencies it
supports can brand the cover. Write a small YAML file:

```yaml
name: Example State Transit Program
logo: logo.svg          # optional; svg, png, or jpeg, path relative to this file
accent: "#2c5f70"       # optional; any #rrggbb color
```

Then pass it:

```
uv run scorecard report --agency unitrans --brand brand.yaml
```

The logo is embedded in the file, so the report stays self-contained. The
accent colors only the cover band and section rules, never text, so any
accent keeps the document readable at WCAG AAA contrast. The footer keeps
its attribution to the open-source scorecard either way.

## Printing

Open the file in a browser and print to PDF. The print stylesheet keeps each
section on one page where it fits, starts the NTD and history sections on
fresh pages, and writes out the footer's link addresses so citations survive
on paper.

## Accessibility

The document uses semantic headings, real tables with header scopes, and
plain-text status labels alongside any styling, so nothing depends on color
alone. The default palette clears the repo's AAA contrast gate
(`pipeline/scripts/check_contrast.py`).
