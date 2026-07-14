# GTFS Scorecard design system

Status: implemented guidance for the public site and generated reports
Design rationale: [ADR 0030 — Rebuild the visual identity on roadway signage](decisions/0030-signage-visual-identity.md)

This system extends the accepted roadway-and-transit-signage identity. It does
not introduce a second brand. Its purpose is to keep a large, evidence-heavy
site recognizable, readable, and action-oriented as new views are added.

## Subject, audience, and job

GTFS Scorecard is a quality report for the people who publish, oversee, and use
public-transit data, especially staff at small and rural agencies. The interface
should feel like a calm service bulletin: operational, legible, and grounded in
the visual language of route maps, stop flags, guide signs, and departure
boards.

The primary report journey answers these questions in order:

1. What is the feed's current condition?
2. What should be fixed first, by whom, and with what likely effort?
3. How do the component scores and route data support that recommendation?
4. Has the feed changed, and did earlier fixes clear?
5. What detailed evidence and standards mapping can a reviewer cite?

The design register is **guidance, not judgment**. Grades are direct, but copy,
spacing, and hierarchy should help an agency act rather than dramatize failure.
Put the next useful action before exhaustive evidence; keep all evidence
available in the same document.

## Sources of truth

| Concern | Canonical source |
| --- | --- |
| Shared tokens, components, themes, responsive and print rules | `web/src/styles.css` |
| Landing-page composition and its mirrored tokens | `web/index.html` |
| Generated markup, including agency reports | `pipeline/src/scorecard_pipeline/render_site.py` |
| Shared header, navigation, footer, and static-page sync | `pipeline/src/scorecard_pipeline/site_shell.py` |
| Theme interaction | `web/src/theme.js` |
| Contrast assertions | `pipeline/scripts/check_contrast.py` |
| Accessibility conformance record | `docs/accessibility.md` |

Do not hard-code a new brand color in a component. Add or reuse a semantic token
in `styles.css`, provide dark and high-contrast values where needed, then add
every text/background use to `check_contrast.py`. If a shared color changes,
review the landing page's intentionally local token mirror as well.

## Color

### Brand and surface tokens

| Token | Light value | Role |
| --- | --- | --- |
| `--paper` | `#f2f3ee` | Enamel sign-blank page ground |
| `--paper-deep` | `#e5e8df` | Recessed or grouped surface |
| `--card` | `#fbfcf8` | Raised content surface |
| `--ink` | `#20241f` | Primary text |
| `--ink-soft` | `#3d4339` | Supporting text that still clears AAA |
| `--line` | `#c6ccbe` | Borders, rules, tracks, and dividers |
| `--green` | `#163a2c` | Primary links and actions |
| `--green-bright` | `#1d4633` | Hover/action emphasis on light surfaces |
| `--board` | `#102a20` | Guide-sign chrome and status-board ground |
| `--board-2` | `#163a2c` | Secondary dark-green board surface |
| `--board-soft` | `#bcccbd` | Muted copy on the board |
| `--amber` | `#fdc70a` | Signal accent, route marker, and dark-chrome focus |
| `--focus` | `#1a3aa8` | Focus ring on light content surfaces |

Amber is an accent, not a warning status. Pine chrome is a stable bookend for
the product, not a decorative dark section to scatter through every page.
Use `--card` for a bounded object and `--paper-deep` for a grouped or recessed
region; do not alternate them solely to make a page look busier.

### Semantic status tokens

| Token | Light value | Meaning |
| --- | --- | --- |
| `--error` | `#8e2a23` | An error or failed requirement |
| `--warning` | `#6b490e` | A warning or at-risk state |
| `--info` | `#3a4753` | Informational or not-yet-checked state |

Every status must also have visible text such as “Error,” “Needs attention,”
or “Not measured.” Color never supplies the status by itself. Dark theme uses
lighter semantic colors for text and separate darker badge fills; do not place
white text on a brightened dark-theme semantic token without checking the
explicit badge override.

### Grade and data colors

| Token | Light value | Data meaning |
| --- | --- | --- |
| `--grade-a` | `#1d5c40` | A band / guidance green |
| `--grade-b` | `#2c5f70` | B band / services blue-teal |
| `--grade-c` | `#8a5a14` | C band / caution ochre |
| `--grade-d` | `#9c4511` | D band / construction orange |
| `--grade-f` | `#8e2a23` | F band / regulatory red |

These colors encode measured grade bands, not general component variants.
Always pair them with a grade letter, score, label, pattern, or table value.
Maps and charts must have an adjacent semantic list, legend, table, or other
text equivalent. Do not reuse the grade ramp as a decorative rainbow.

### Themes

The product supports System, Light, Dark, and High contrast. System follows the
OS only when no explicit `data-theme` is present. The dark board stays dark in
all themes; its fixed light text does not inherit `--paper`. New components must
work in all four choices before they are complete.

## Typography

| Role | Family token | Typical use |
| --- | --- | --- |
| Display | `--font-display`: Overpass, then Helvetica/Arial | Page titles, section titles, grade and score numerals |
| Body | `--font-body`: Public Sans, then Helvetica/Arial | Running copy, labels, forms, explanations |
| Utility/data | `--font-mono`: Overpass Mono, then system mono | Stop numbers, kickers, rule codes, timestamps, compact metrics |

Overpass is the subject-specific voice: it descends from the road-sign
letterforms riders already navigate. Public Sans keeps long operational prose
plain. Overpass Mono is for short wayfinding and data labels, not paragraphs.

Use the existing hierarchy before introducing another size:

| Style | Current range |
| --- | --- |
| Board/report title | `clamp(2rem, 5.5vw, 3.4rem)`, 900 weight, tight line height |
| Page title | `clamp(1.9rem, 6vw, 2.7rem)`, 900 weight |
| Section title | `1.35rem`, 700 weight |
| Component title | about `1.05–1.18rem`, 600–700 weight |
| Body | `1rem / 1.55` |
| Supporting copy | `0.8–0.9rem`, using `--ink-soft` |
| Utility label | `0.68–0.8rem`, mono, often uppercase with letter spacing |

Cap running prose with `--measure: 70ch`. Tables, maps, code, charts, and other
data displays may use the full data container; their explanatory prose should
still keep a readable measure. Avoid all-caps body copy and avoid using small
mono text for a critical instruction.

## Spacing, shape, and elevation

Use a quarter-rem base and prefer this working scale: `0.25`, `0.5`, `0.75`,
`1`, `1.5`, `2`, `3`, and `4rem`. Optical micro-adjustments inside type or
icons may use smaller values; new layout gaps should use the scale.

- Component padding is normally `0.75–1.1rem`.
- A related heading and body are normally `0.5–0.9rem` apart.
- Major report sections receive about `2.4rem` of separation, usually carried
  by `.route-rule` rather than an empty decorative panel.
- Default corners use `--radius: 10px`. Pills use a full radius; grade and stop
  markers are circles. Do not introduce unrelated corner families.
- Use `--shadow` only where elevation communicates a bounded, selectable, or
  summary object. Long evidence sections and departure-board rows use rules,
  not a stack of floating cards.

## Layout and breakpoints

The layout is mobile-first. Source order is reading order; CSS must not move a
visually secondary item ahead of a primary item for assistive technology.

| Primitive | Contract |
| --- | --- |
| `.wrap` | `44rem` reading column with `1.1rem` inline padding |
| `main.wrap-wide` | `78rem` data canvas; prose inside keeps its own measure |
| `.section-grid` | One column by default, two columns at `900px` |
| `.site-header > .wrap` | Full chrome lane up to `90rem` |
| `.agency-report` | Inherits the `78rem` wide report canvas; at `64rem` it reserves a readable content column plus the `.report-route` rail |

Existing responsive thresholds are deliberate boundaries, not device labels:

| Threshold | Behavior |
| --- | --- |
| `38rem` | Compact card grids may become two columns |
| `40rem` / `640px` | Dense rows stack; tables scroll within their own region; map controls become full width |
| `900px` | Independent data sections may sit side by side |
| `64rem` / `1024px` | Agency report becomes two columns and the report route becomes a sticky right rail |
| `1400px` | Primary route-stop navigation collapses to the operable menu before it can overflow |

Prefer these thresholds for new components. Add a local breakpoint only when
the content itself no longer fits, and record the reason beside the rule.
Never solve overflow by shrinking body text or interactive targets.

## Reusable primitives

### Product chrome

- `.site-header`, `.nav-stops`, and `.nav-stop` form one wayfinding route. The
  current section uses `aria-current="page"` and a filled stop pip.
- `.nav-menu-btn` controls the same navigation below `1400px`; `nav.js` owns its
  expanded state. The no-script fallback exposes the links rather than hiding
  them behind an inert button.
- `.site-footer` repeats the pine-and-amber bookend. Keep footer groups named;
  do not return to one unstructured wall of links.
- `.breadcrumb`, `.skip-link`, and `.skip-link-inline` provide location and
  bypass routes. They are functional navigation, not optional polish.

### Page and report hierarchy

- `.page-title`, `.page-lede`, `.section-title`, `.fineprint`, and
  `.plain-summary` cover the standard prose hierarchy.
- `.board-hero` is the agency report's condition read: agency, snapshot, grade,
  score, trend, and short state chips. It appears once per report.
- `.route-rule` marks a major change of subject. Do not place it between every
  small component.
- `.grade-chip` is a compact route-roundel grade; `.reel` is the larger
  decision-critical grade display. Both must contain the grade letter.

### Action and evidence

- `.alerts` / `.alert` present the prioritized fixes as service alerts.
- `.fixloop` explains change → publish → verify without duplicating the top-fix
  prose as another competing card stack.
- `.platforms` / `.platform` present category scores as departure-board rows.
- `.findings` / `.finding` hold exhaustive validator evidence.
- `.feed-details` groups a bounded explanatory or standards section.
- `.ntd-status` and its labelled variants communicate status in text and color.
- Native `<details>/<summary>` is the default progressive-disclosure primitive
  for long supporting material. The summary remains at least `44px` tall and
  the closed state must not hide the report's next required action.

### Data and controls

- `.service-chart`, `.bucket-chart`, and `.movement-chart` reuse the route/stop
  visual grammar. Supply text and numeric values alongside marks.
- `.table-wrap` owns horizontal overflow for a genuinely wide table. Do not
  make the whole page scroll sideways.
- Buttons, chips, inputs, selects, file controls, copy actions, and disclosure
  summaries have a `44px` minimum target. Preserve visible hover, pressed,
  disabled, and `:focus-visible` states.
- A map is progressive enhancement. Keep the route table, stop list, agency
  list, or other equivalent data in the document.

## Signature pattern: report route

`.report-route` turns the long agency report into a route the reader can scan
without turning it into a generic dashboard. It is an in-page `<nav>` labelled
“Report sections”; each link is a stop on one continuous line.

The canonical order and targets are:

| Stop | Target | Presence |
| --- | --- | --- |
| Overview | `#report-overview` | Always |
| Fixes | `#fixes-h` | Always, including all-clear reports |
| Scores | `#cats-h` | Always |
| Routes | `#map-h` | Only when the route/map section exists |
| History | `#trend-h` | When the report has history |
| Evidence | `#findings-h` | Always |
| Standards | `#standards-h` | Always |

Implementation rules:

- Generate stops from the same conditions that generate their sections; never
  emit a dead anchor.
- Keep stop order identical to document order. Do not use CSS ordering.
- At `64rem` and wider, the route is a sticky right rail in reserved layout
  space; it must not cover content or become the page's primary scroll
  container.
- Below `64rem`, it becomes a horizontally scrollable stop strip above the
  report body. Focused links must scroll into view, and the page itself must
  not gain horizontal overflow.
- The line and pips are decorative. Link text supplies the name; focus and
  target states use shape/weight as well as color.
- Give target sections enough `scroll-margin` that headings are not obscured
  by chrome. The destination heading or overview container is the focusable or
  perceivable target, not a visually empty spacer.
- The route works as ordinary anchor navigation with JavaScript disabled. A
  future scrollspy may add `aria-current="location"`, but must not be required
  to navigate.
- Hide `.report-route` in print; the printable brief and board report have
  their own compact information architecture.

## Responsive, accessibility, motion, and print

- Meet WCAG 2.2 AAA where the project claims it. Normal text pairs target `7:1`;
  large text targets `4.5:1`; focus indicators clear `3:1` against adjacent
  colors. Run the contrast script instead of estimating.
- Landmarks, heading order, accessible names, table headers, list semantics,
  meter values, `aria-expanded`, `aria-pressed`, and `aria-current` must match
  the visible state. Never add ARIA to repair invalid native HTML.
- Keyboard order follows DOM order. Menus, disclosures, filters, copy actions,
  and route rows remain usable with Tab, Shift+Tab, Enter, Space, and Escape as
  applicable. Focus is always visible.
- Test at `200%` zoom and at `320px` CSS width. Content reflows without loss;
  only true data tables use contained horizontal scrolling.
- Motion is optional reinforcement. Load reveals run only under
  `prefers-reduced-motion: no-preference`; reduced motion removes animation and
  smooth scrolling. The measured grade must be correct before any animation.
- Print removes site chrome, route navigation, filters, bypass links, and
  decorative route rules; removes shadows; uses black on white; and avoids
  breaking a bounded report item across pages where practical.
- Third-party map canvases are never the only route to information. Preserve a
  visible loading/fallback message and the accessible data alternative.

## Visual QA matrix

Run the matrix after changing tokens, chrome, shared components, or generated
report markup. Use representative data states, not only the cleanest agency.

| Surface | Desktop check (`1440×900`) | Mobile check (`390×844`) | Required variants |
| --- | --- | --- | --- |
| Landing page | Hero hierarchy, proof band, section rhythm, footer, no lazy-render blank gaps after scrolling | No clipped hero, reachable navigation/actions, readable samples | System/light/dark/contrast; reduced motion |
| Agency directory | Search/facets, grade rows, expired groups, readable density | `44px` controls, cards stack, no page overflow | Empty search, expired, long agency name |
| Agency report | Overview and top fix dominate; report route sticks without overlap; wide evidence uses available space | Report route remains usable; alerts stack; maps/tables contain overflow | A–F, all-clear, no map, no history, long finding, non-US |
| Tools/check/try | One primary action, form labels and errors, code and upload regions | Inputs and buttons fill safely; keyboard is not obscured | Loading, success, validation error, no JavaScript |
| Charts/maps/tables | Labels and numeric values match the visual; data alternative is discoverable | Legends wrap; table/map region, not page, scrolls | No data, single item, many items, map load failure |
| Header/footer | Active section and theme control are clear; no nav overflow | Menu opens, closes, traps no focus, and leaves all links reachable | JavaScript off; long localized labels |
| Brief/board report | Screen preview has the same content hierarchy as print | No accidental mobile-only clipping | US Letter print/PDF, black and white, page breaks |

For every row, also check keyboard-only use, visible focus, `200%` zoom, and a
screen-reader landmark/heading pass. Regenerate representative static pages
before screenshot review so the QA covers source output rather than stale HTML.

## Release gate

A design-system change is ready when:

1. It reuses or deliberately extends the tokens and primitives above.
2. Light, dark, high-contrast, and OS-following themes render correctly.
3. Keyboard, target size, focus, reflow, reduced-motion, and no-script behavior
   have been checked.
4. `pipeline/scripts/check_contrast.py` passes for every affected pair.
5. Generated pages have been rebuilt and a representative desktop/mobile
   screenshot set has been reviewed.
6. Print output remains legible when the changed component can appear in a
   brief, board report, or handout.
