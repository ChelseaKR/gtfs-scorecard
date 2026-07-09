# Accessibility Conformance Report (VPAT 2.5 Rev — 508 edition)

**Name of product:** GTFS Scorecard (public website, single-page app, GitHub Action)
**Report date:** 2026-06-22
**Standard evaluated:** Revised Section 508 Standards (36 CFR Part 1194), which
incorporate **WCAG 2.0 Level AA**. The product targets **WCAG 2.2 Level AAA** and
enforces automated accessibility gates described in `docs/accessibility.md`.

**Evaluation methods:** automated checks (`pipeline/scripts/check_contrast.py` for
contrast across every theme; axe-core and Lighthouse in CI — `.github/workflows/a11y.yml`)
plus manual keyboard review. The planned NVDA/Firefox and VoiceOver/Safari passes have
not yet been recorded; `docs/accessibility-testing.md` is the evidence log and must be
completed before this report claims assistive-technology verification.

## Conformance levels used

- **Supports** — meets the criterion without exception.
- **Partially Supports** — meets the criterion for the core experience, with a
  documented exception for which an equivalent accessible path exists.
- **Does Not Support** — does not meet the criterion.
- **Not Applicable** — the criterion does not apply to this product.

## Table 1 — WCAG 2.0 Level A

| Criterion | Level | Conformance | Remarks |
| --- | --- | --- | --- |
| 1.1.1 Non-text Content | A | Supports | Decorative SVG is `aria-hidden`; meaningful images/badges carry text alternatives. |
| 1.2.1–1.2.3 Audio/Video | A | Not Applicable | No audio or video content. |
| 1.3.1 Info and Relationships | A | Supports | Semantic landmarks, headings, `<table>`/list structure, `aria-current`, breadcrumbs. |
| 1.3.2 Meaningful Sequence | A | Supports | DOM order matches reading order; no layout that reorders meaning. |
| 1.3.3 Sensory Characteristics | A | Supports | Instructions never rely on shape/position/color alone. |
| 1.4.1 Use of Color | A | Supports | Grades, severities, and the active nav stop pair color with text/`aria-current`/icons. |
| 1.4.2 Audio Control | A | Not Applicable | No auto-playing audio. |
| 2.1.1 Keyboard | A | Supports | All controls (theme menu, filters, map, forms, nav) are keyboard operable. |
| 2.1.2 No Keyboard Trap | A | Supports | Menus/panels close on Escape and return focus. |
| 2.2.1 / 2.2.2 Timing, Moving Content | A | Supports | No time limits; animation respects `prefers-reduced-motion`. |
| 2.3.1 Three Flashes | A | Supports | No flashing content. |
| 2.4.1 Bypass Blocks | A | Supports | "Skip to content" link plus landmark regions on every page. |
| 2.4.2 Page Titled | A | Supports | Unique, descriptive `<title>` per page. |
| 2.4.3 Focus Order | A | Supports | Logical focus order; drop panels follow their trigger. |
| 2.4.4 Link Purpose (In Context) | A | Supports | Self-describing link text or `aria-label`; external links flagged. |
| 2.5.1–2.5.4 Pointer / Motion | A | Supports | No path-based or motion-actuated gestures required. |
| 3.1.1 Language of Page | A | Supports | `<html lang="en">`. |
| 3.2.1 / 3.2.2 On Focus / On Input | A | Supports | No context change on focus or input. |
| 3.3.1 Error Identification | A | Supports | Forms identify errors in text, set aria-invalid, and move focus to the offending field. |
| 3.3.2 Labels or Instructions | A | Supports | Form fields have visible labels and instructions. |
| 4.1.1 / 4.1.2 Parsing, Name/Role/Value | A | Supports | Valid HTML; ARIA on the theme menu, nav, and interactive widgets. |

## Table 2 — WCAG 2.0 Level AA

| Criterion | Level | Conformance | Remarks |
| --- | --- | --- | --- |
| 1.2.4 / 1.2.5 Captions / Audio Description | AA | Not Applicable | No multimedia. |
| 1.4.3 Contrast (Minimum) | AA | Supports | All themes clear AAA 7:1; gated by `check_contrast.py`. Exceeds the AA 4.5:1 bar. |
| 1.4.4 Resize Text | AA | Supports | Uses relative units and responsive layouts; the recorded human zoom/reflow pass is pending. |
| 1.4.5 Images of Text | AA | Supports | Text is live text; no images of text. |
| 2.4.5 Multiple Ways | AA | Supports | Primary nav, breadcrumbs, search, agency index, map, and footer links. |
| 2.4.6 Headings and Labels | AA | Supports | Descriptive headings and labels throughout. |
| 2.4.7 Focus Visible | AA | Supports | `:focus-visible` outlines >= 3px with >= 3:1 contrast (also meets 2.4.13 AAA). |
| 3.1.2 Language of Parts | AA | Supports | Content is English; no foreign-language passages. |
| 3.2.3 Consistent Navigation | AA | Supports | The wayfinding nav is identical across app and prerendered pages. |
| 3.2.4 Consistent Identification | AA | Supports | Components reused with consistent names/icons. |
| 3.3.3 Error Suggestion | AA | Supports | Forms suggest the correction (e.g. the URL must start with http(s)). |
| 3.3.4 Error Prevention | AA | Supports | Subscribe uses double opt-in; submissions are reversible (pull request). |
| 4.1.3 Status Messages | AA | Supports | `role="status"` on loading and live result counts. |

### Documented AA exceptions

- **National map (`/map/`):** the third-party MapLibre canvas is a convenience layer.
  It is `aria-hidden`, kept out of the tab order, and carries no on-canvas controls, so
  nothing focusable is hidden from assistive tech. The conformant primary on the page is
  the filterable agency table (agency, grade, state, score, link), with grade, state, and
  a "Skip to the agency list" bypass; the same grade and state filters drive the map and
  the table together, and grade is drawn as a letter on every marker, never colour alone.
  The page is axe-tested in CI like every other route (ADR 0022).
- **Equity choropleth (`/equity/`):** a static inline-SVG state choropleth of the ACS need
  tiers. Tiers are encoded by colour plus a hatch pattern and named in each state's title
  text; the priority and full per-state tables carry every number the map shows, reached by
  a "Skip to the state tables" bypass. No map library or tiles, so it is fully keyboard- and
  screen-reader-operable.

- **Per-agency route map (`/agency/<id>/`):** each scorecard draws that agency's own
  routes and stops on a MapLibre map. Here the map is purely a visual enhancement and
  is **not** an exception: the canvas is marked `aria-hidden`, carries no focusable
  controls, and is taken out of the keyboard tab order, so it adds nothing for assistive
  tech to trip over. The conformant primary is a semantic, keyboard-navigable route
  table (route name and number, vehicle type, and the line color described in words —
  never color alone) plus a stop count and full stop list, reached by a "Skip to route
  and stop data" bypass link placed before the map. The fly-to is suppressed under
  `prefers-reduced-motion`. This page is in the axe/pa11y gate and passes with zero
  violations, so it Supports without a documented exception.

- **National all-routes map (`/routes/`):** every tracked agency's route shapes are
  drawn on one MapLibre canvas, read from a single PMTiles vector-tile archive. This
  is an **exploratory enhancement, not an AAA-conformant data interface**, and we do
  not claim conformance for the canvas: a national map holds millions of route
  segments and cannot be rendered as a literal data table, so there is no equivalent
  table *on this page*. The canvas is handled like the per-agency map (marked
  `aria-hidden`, no focusable controls, taken out of the tab order, `prefers-reduced-motion`
  honored) and the page itself is in the axe/pa11y gate and passes with zero violations.
  The conformant equivalents exist elsewhere and are linked prominently at the top of
  the page, with a "Skip to the accessible agency list" bypass before the map: the
  sortable, screen-reader-friendly **agencies list (`/agencies/`)**, the
  **leaderboard (`/leaderboard/`)**, and each **per-agency scorecard's route table**
  (`/agency/<id>/`), which together carry the same route, type, grade, and agency
  information in operable, semantic form. We report this page as **Partially Supports**:
  the page chrome conforms; the map widget's internal exploration does not, and is not
  the route to the data.

## Chapter 3 — Functional Performance Criteria

| Criterion | Conformance | Remarks |
| --- | --- | --- |
| 302.1 Without Vision | Not Evaluated | Semantic structure, alt text, and ARIA are present; the planned screen-reader walkthrough is not yet recorded. |
| 302.2 With Limited Vision | Supports | AAA contrast, 200%+ reflow, a color-theme mechanism incl. high contrast. |
| 302.3 Without Perception of Color | Supports | No color-only meaning (1.4.1). |
| 302.4 Without Hearing | Not Applicable | No audio. |
| 302.5 With Limited Hearing | Not Applicable | No audio. |
| 302.6 Without Speech | Not Applicable | No speech input required. |
| 302.7 With Limited Manipulation | Supports | Keyboard operable; >= 44px targets (one documented map exception). |
| 302.8 With Limited Reach and Strength | Supports | No timed or force-based interactions. |
| 302.9 Minimize Photosensitive Seizure | Supports | No flashing (2.3.1). |
| 302.10 With Limited Cognition | Supports | Plain-language summaries, glossary, consistent navigation. |

## Chapter 4 — Hardware

Not Applicable. The product is web content and software; it ships no hardware.

## Chapter 5 — Software

| Provision | Conformance | Remarks |
| --- | --- | --- |
| 502 Interoperability with AT | Supports | Standard HTML/ARIA exposes name/role/value/state to platform AT. |
| 503 Applications | Supports | The single-page app meets the WCAG tables above. |
| 504 Authoring Tools | Not Applicable | The product is not an authoring tool. |
| CLI / GitHub Action | Supports | Output is plain text (job log); the optional `--html` scorecard reuses the agency-page renderer, which passes the axe gate. |

## Chapter 6 — Support Documentation and Services

| Provision | Conformance | Remarks |
| --- | --- | --- |
| 602.2 Accessibility & Compatibility Features | Supports | This report plus `docs/accessibility.md` document features and known limitations. |
| 602.3 Electronic Support Documentation | Supports | Docs are Markdown/HTML meeting the WCAG tables; README and `/how-to-read/` are accessible. |
| 603 Support Services | Supports | A feedback path to report barriers is published at `/accessibility/` and via the accessibility issue template. |

## Revision history

- 2026-06-22 — Initial 508-edition report. Companion to `docs/accessibility.md`
  (WCAG 2.2 AAA detail) and `docs/section-508-plan.md` (remaining work).
