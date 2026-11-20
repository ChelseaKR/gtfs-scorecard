# GTFS Scorecard Accessibility Conformance Report

Accessibility Conformance Report (ACR), based on the VPAT® 2.5 Rev WCAG edition.

VPAT® is a registered service mark of the Information Technology Industry Council (ITI).

**Name of product/version:** GTFS Scorecard, the public website at gtfsscorecard.org
(release 1.5.1, rubric 1.5), including the interactive app at `/app/`, the alert and
bundle-download pages served by the site's own API, and the GitHub Action's text output.

**Report date:** 2026-11-20

**Product description:** a free, open-source data-quality scorecard for transit
agencies' GTFS Schedule and GTFS-Realtime feeds. Every page is static HTML with light
JavaScript; there is no sign-in. Readers search for an agency, read its grade and the
fixes it needs, print a brief, sign up for feed-health email alerts, and buy program
report bundles through Stripe Checkout.

**Contact information:** report a barrier from the site's
[accessibility page](https://gtfsscorecard.org/accessibility/), which opens the
repository's accessibility issue template, or through the contact link on
[chelseakr.com](https://chelseakr.com) if you would rather not file a public issue.

**Notes:**

- **The remarks describe the site after branch `a11y/acr-2026-11`.** Three fixes on
  that branch (Appendix A) are part of what this report claims. Until the branch is
  merged and deployed, the live site differs on the rows marked "after the 2026-11-20
  fixes".
- **Two agency pickers are rated as they will be after the agency-search branch lands.**
  `feat/agency-search-typeahead-2026-11` replaces the home page search with a
  find-as-you-type combobox and the alerts form's agency `<select>` with the same
  combobox. Rows 1.4.13, 2.1.1, 2.4.7, 2.5.8, 3.2.2, 3.3.1, 3.3.7, 4.1.2 and 4.1.3
  cite it. Until it
  merges, the home page search is a text field with a button list of results and the
  alerts form uses a native `<select>`; both were also checked and conform, so no row
  changes level either way.
- **No screen-reader walkthrough has been recorded yet.** Rows whose evidence is the
  accessibility tree, axe and code reading, rather than what NVDA or VoiceOver actually
  announce, say so in their remarks ("screen-reader confirmation pending"). Appendix B
  lists the walkthrough that would confirm them. Until it is done this report is not a
  screen-reader attestation, and `docs/accessibility-testing.md` stays the place its
  results are logged.
- The site targets WCAG 2.2 AAA. AAA detail lives in `docs/accessibility.md`; this
  report covers Level A and AA only.
- Third-party content: Stripe Checkout (payment), the OpenFreeMap basemap tiles under
  the MapLibre maps, and GitHub (issue forms, source links). Stripe Checkout and GitHub
  are outside this report. The maps are covered below because they sit on our pages.

## Evaluation methods used

Run on 2026-11-20 against `origin/main` at `e1c47cf4be1` plus the branch's fixes, with
the agency-search branch (`10b3fc10a07`) overlaid for `/` and `/subscribe.html`:

- **axe-core 4.13** in headless Chromium, WCAG 2.0, 2.1 and 2.2 A and AA rules
  including `color-contrast` and `target-size`, on one page per template in the light
  and the dark color scheme: `/`, `/404.html` and an unknown address, two agency
  pages, an agency brief and board, `/app/` (directory, an agency, compare),
  `/subscribe.html`, the alert confirm and unsubscribe pages, the bundle download
  page, `/program/` and `/program/california/`, `/bundle/`, `/bundle/setup/`,
  `/bundle/sample/`, `/invoice/`, `/accessibility/` and a fix guide.
- **The same browser pass, scripted:** a 40-press Tab walk from the top of each page
  recording whether each focused element draws an outline and whether anything covers
  it; every focusable target under 24 by 24 CSS px; horizontal overflow at a 320 CSS px
  viewport; and clipped text after the WCAG 1.4.12 text-spacing override.
- **The repository's own gates:** `pipeline/scripts/check_contrast.py` (every text and
  non-text color pair in the light, dark and high-contrast themes), the pa11y-ci axe
  scan of 39 URLs in `.github/workflows/a11y.yml`, Lighthouse accessibility at 0.95 or
  better, and the Playwright suites in `pipeline/tests/e2e` (keyboard journeys, form
  errors, focus not obscured, 320 px reflow, reduced motion).
- **Code reading** of templates and scripts for what automation cannot judge: alt text
  and labels, combobox and menu patterns against the ARIA Authoring Practices, error
  handling, dragging, help placement, redundant entry and authentication.
- Not used yet: NVDA, JAWS, VoiceOver or TalkBack (Appendix B).

## Applicable standards/guidelines

| Standard/Guideline | Included in report |
| --- | --- |
| Web Content Accessibility Guidelines 2.0 | Level A (Yes), Level AA (Yes), Level AAA (No) |
| Web Content Accessibility Guidelines 2.1 | Level A (Yes), Level AA (Yes), Level AAA (No) |
| Web Content Accessibility Guidelines 2.2 | Level A (Yes), Level AA (Yes), Level AAA (No; see `docs/accessibility.md`) |

WCAG 2.2 includes every success criterion of 2.0 and 2.1 except 4.1.1 Parsing, so the
2.2 tables below also report conformance to 2.0 and 2.1 at the same levels. The
Revised Section 508 Standards incorporate WCAG 2.0 Level AA; the 508 chapters carried
over from the earlier edition of this report are in Appendix C.

## Terms

- **Supports:** the functionality of the product has at least one method that meets
  the criterion without known defects or meets with equivalent facilitation.
- **Partially Supports:** some functionality of the product does not meet the
  criterion.
- **Does Not Support:** the majority of product functionality does not meet the
  criterion.
- **Not Applicable:** the criterion is not relevant to the product.
- **Not Evaluated:** the product has not been evaluated against the criterion. Used
  only for Level AAA in ITI's template; not used in this report.

## WCAG 2.2 Report

### Table 1: Success Criteria, Level A

| Criteria | Conformance Level | Remarks and Explanations |
| --- | --- | --- |
| 1.1.1 Non-text Content (Level A) | Supports | Decorative SVG and route-rule art are `aria-hidden` or `role="presentation"`. The grade badge image has alt text naming the agency and grade. Score sparklines carry the series in `aria-label` with a "Show the numbers" table. The MapLibre maps are `aria-hidden`; the route and stop table on each agency page, and `/agencies/` for the national maps, carry what they show. axe: 0 `image-alt`, `svg-img-alt` or `role-img-alt` violations. Screen-reader confirmation pending. |
| 1.2.1 Audio-only and Video-only (Prerecorded) (Level A) | Not Applicable | No audio or video. |
| 1.2.2 Captions (Prerecorded) (Level A) | Not Applicable | No audio or video. |
| 1.2.3 Audio Description or Media Alternative (Prerecorded) (Level A) | Not Applicable | No audio or video. |
| 1.3.1 Info and Relationships (Level A) | Supports | Landmarks, one `h1` per page, nested headings, real tables with header cells, lists, `fieldset`/`legend` for checkbox groups, labeled fields. After the 2026-11-20 fixes: the four hints on `/bundle/setup/` are each field's accessible description (they were shown but not tied to their fields), and the alert and download pages wrap their message in `main`. axe: 0 violations. Screen-reader confirmation pending. |
| 1.3.2 Meaningful Sequence (Level A) | Supports | DOM order is reading order; no CSS reordering of meaningful content. Checked in the Tab walk and by reading templates. |
| 1.3.3 Sensory Characteristics (Level A) | Supports | Instructions name controls by their label, never by shape, color or position. |
| 1.4.1 Use of Color (Level A) | Supports | Grades are letters; severities carry words; the current nav stop carries `aria-current` and a filled marker; route colors on agency pages are also described in words; the equity map adds hatching. |
| 1.4.2 Audio Control (Level A) | Not Applicable | No audio. |
| 2.1.1 Keyboard (Level A) | Partially Supports | Every page control works from the keyboard: theme menu, nav menu, filters, the route table's highlight toggles, forms, copy buttons, and both agency pickers (Up and Down move through suggestions, Enter chooses, Escape closes; agency-search branch). Covered by `test_keyboard.py`, `test_forms.py` and the branch's `test_agency_combobox.py`. Exception: panning and zooming the MapLibre maps needs a pointer. On agency pages and `/map/` the same information is in a keyboard table on the page. On `/routes/` the national route map has no on-page equivalent; the agency list, coverage view and each agency's route table carry its information on other pages. |
| 2.1.2 No Keyboard Trap (Level A) | Supports | Tab walk on every tested page moved forward without getting stuck; menus and pickers close on Escape and on Tab. Map canvases are out of the tab order. |
| 2.1.4 Character Key Shortcuts (Level A) | Not Applicable | No single-character keyboard shortcuts. |
| 2.2.1 Timing Adjustable (Level A) | Not Applicable | No time limits on any page. Stripe Checkout's own session limit is outside this report. |
| 2.2.2 Pause, Stop, Hide (Level A) | Supports | Nothing moves, blinks or updates on its own for more than five seconds. The status blip runs twice (4 s) and stops; reveal animations last under half a second and are off under `prefers-reduced-motion`. |
| 2.3.1 Three Flashes or Below Threshold (Level A) | Supports | No flashing content. |
| 2.4.1 Bypass Blocks (Level A) | Supports | "Skip to main content" is the first focusable element on every page with repeated navigation, and lands on `#main`. Pages with a map add a skip link past it. The one-message alert and download pages have no repeated blocks. |
| 2.4.2 Page Titled (Level A) | Supports | Each page and each `/app/` route sets a descriptive `<title>`; the alert and download pages are titled with their outcome ("You are subscribed", "Link expired"). |
| 2.4.3 Focus Order (Level A) | Supports | Tab order follows reading order in the Tab walk. `/app/` moves focus to the main region on each route change; forms move focus to the first field in error. |
| 2.4.4 Link Purpose (In Context) (Level A) | Supports | Link text or `aria-label` names the destination; fix-guide links name the finding; links that open a new tab say so. axe: 0 `link-name` violations. |
| 2.5.1 Pointer Gestures (Level A) | Supports | Nothing needs a multipoint or path gesture. Pinch-zoom on a map also works by double-click or scroll, and the map content is in a table. |
| 2.5.2 Pointer Cancellation (Level A) | Supports | Controls act on click (the up event). The pickers' `mousedown` handler only keeps focus in the field; the choice happens on click. |
| 2.5.3 Label in Name (Level A) | Supports | Where a control has an `aria-label`, it begins with or contains the visible text (for example "Source code on GitHub" on a link reading "GitHub"). Checked by reading the templates; axe's experimental rule is not relied on. |
| 2.5.4 Motion Actuation (Level A) | Not Applicable | No motion-operated functions. |
| 3.1.1 Language of Page (Level A) | Supports | `<html lang="en">` on every page and `lang="es"` on `/es/`. After the 2026-11-20 fixes the alert confirm and unsubscribe pages and the bundle download page also declare `lang="en"`; before them they declared no language. |
| 3.2.1 On Focus (Level A) | Supports | Focus never changes context. |
| 3.2.2 On Input (Level A) | Supports | Typing in a picker only lists suggestions; moving through them changes nothing. On the home page (agency-search branch) a deliberate Enter, click or the Find button opens the agency page, as following a link would. Filters update results in place and announce the count. |
| 3.2.6 Consistent Help (Level A) | Supports | The help mechanism is the footer's "Get help or sponsor" link to `/support/`. It is in the footer, after the main content, on every page that has the site footer, including the home page, whose footer is laid out differently. |
| 3.3.1 Error Identification (Level A) | Supports | Forms name the problem in text, set `aria-invalid` and move focus to the field. After the 2026-11-20 fixes this includes `/bundle/setup/`, which named the missing field in its status line but did not mark or focus it. On the agency-search branch the alerts form treats an agency field with nothing chosen as an error that says how to fix it. Covered by `test_forms.py` and `test_bundle_setup_form.py`. |
| 3.3.2 Labels or Instructions (Level A) | Supports | Every field has a visible label; required fields say "(required)"; format hints sit under their fields and, after the 2026-11-20 fixes, are read with them on `/bundle/setup/` too. |
| 3.3.7 Redundant Entry (Level A) | Supports | No form asks twice for what the reader already gave. `/bundle/setup/` leaves the delivery address optional and uses the checkout email when it is blank. On the agency-search branch, "Watch this feed" opens the alerts form with that agency already chosen. |
| 4.1.1 Parsing (Level A) | Supports | Obsolete in WCAG 2.2 and treated as always satisfied. For WCAG 2.0 and 2.1: the pages are generated from templates with no duplicate IDs (axe `duplicate-id-aria`: 0). |
| 4.1.2 Name, Role, Value (Level A) | Supports | Native controls throughout. The theme control is a `button` with `aria-expanded` opening a `menu` of `menuitemradio` (axe cannot confirm its `aria-controls` target while the menu is closed and not yet in the page); the nav menu button has `aria-expanded`/`aria-controls`; route table rows are `role="button"` with `aria-pressed`. On the agency-search branch both pickers expose `role="combobox"` with `aria-expanded`, `aria-controls` and `aria-activedescendant`, over a labeled `listbox` of `option` rows with `aria-selected`; without JavaScript each is a labeled text field. axe: 0 violations. Screen-reader confirmation pending. |

### Table 2: Success Criteria, Level AA

| Criteria | Conformance Level | Remarks and Explanations |
| --- | --- | --- |
| 1.2.4 Captions (Live) (Level AA) | Not Applicable | No live audio. |
| 1.2.5 Audio Description (Prerecorded) (Level AA) | Not Applicable | No video. |
| 1.3.4 Orientation (Level AA) | Supports | No orientation lock; layouts are responsive in portrait and landscape. |
| 1.3.5 Identify Input Purpose (Level AA) | Supports | Fields asking for the reader's own details carry `autocomplete` (`email`, `name`, `organization`). |
| 1.4.3 Contrast (Minimum) (Level AA) | Supports | Lowest normal-text ratio in `check_contrast.py`: 7.07:1 in the light theme, 7.08:1 dark, 7.15:1 high contrast, against a 4.5:1 requirement (the site holds 7:1). axe `color-contrast`: 0 violations on the 25 tested pages in light and in dark. axe left 116 text nodes undecided because they sit on gradients or textures; those colors are pairs in the contrast gate. The downloadable bundle report (`/bundle/sample/`) is light only, with its lowest text pair at #3d4339 on white. |
| 1.4.4 Resize Text (Level AA) | Supports | Relative units; text resizes to 200% without loss (2026-07-13 check, `test_mobile.py`). |
| 1.4.5 Images of Text (Level AA) | Supports | Text is live text. The one image of text on a page is the embeddable grade badge previewed in an agency's "Show your grade" section, where the badge itself is what is being offered (essential), and its alt text carries the same words. |
| 1.4.10 Reflow (Level AA) | Supports | No horizontal page scrolling at 320 CSS px on 24 of the 25 tested pages (Appendix D). On the bundle report sample, which is also the file buyers download, the category table is 349 px wide at a 320 px viewport, so the page scrolls 29 px sideways; data tables are an allowed two-dimensional exception, and letting long words in its cells wrap is listed as a design change for approval. Wide tables on site pages scroll inside their own keyboard-focusable region. |
| 1.4.11 Non-text Contrast (Level AA) | Supports | Form field borders 3.59:1 to 4.44:1 light and dark (6.66:1 high contrast); focus rings 8.5:1 or more on their backgrounds; grade badge fills 7:1 with white text. |
| 1.4.12 Text Spacing (Level AA) | Supports | With line height 1.5, letter spacing 0.12em, word spacing 0.16em and paragraph spacing 2em applied, no text was lost on the tested pages. The one element reported as clipping, the grade "reel" on agency pages, hides the four grades that are not the agency's by design; the shown grade still fits its 104 px row, and the reel's `aria-label` carries it. |
| 1.4.13 Content on Hover or Focus (Level AA) | Supports | No custom hover or focus pop-ups. The only hover text is native SVG `<title>` and `<abbr title>` tooltips, which the browser controls. Picker suggestions appear on typing, not on hover or focus, and Escape closes them. |
| 2.4.5 Multiple Ways (Level AA) | Supports | Primary nav, footer, breadcrumbs, the agency directory, search, the map and program pages. The alert and download pages are steps of a process and exempt. |
| 2.4.6 Headings and Labels (Level AA) | Supports | Headings name their sections; labels name their fields. |
| 2.4.7 Focus Visible (Level AA) | Supports | Every element reached in the Tab walk (up to 40 per page, 25 pages) drew an outline or ring; none was invisible. Picker options, which keep focus in the field, draw their own 3 px inset ring (agency-search branch). |
| 2.4.11 Focus Not Obscured (Minimum) (Level AA) | Supports | The sticky header never fully covered the focused element in the Tab walk on any tested page; `test_focus_not_obscured.py` drives Shift+Tab and in-page links under it. Picker lists close when focus leaves the field. |
| 2.5.7 Dragging Movements (Level AA) | Partially Supports | Panning a MapLibre map is the only drag on the site. Agency pages fit the map to the agency's routes and the route table highlights a route without dragging; `/map/` has the filterable agency table. The national map on `/routes/` can only be explored by dragging. |
| 2.5.8 Target Size (Minimum) (Level AA) | Supports | Buttons, fields, chips, nav and footer links are 44 px or more; picker options 65 px, two lines each (agency-search branch). Text links inside sentences are exempt as inline. Stand-alone list and table links are 13 to 22 px tall with spacing that clears the 24 px circle test; checkboxes are 13 to 19 px but sit inside their clickable labels. The small state and country shapes on the `/app/` maps fall under the equivalent-control exception (the chip grid). axe `target-size`: 0 violations on the 25 tested pages. |
| 3.1.2 Language of Parts (Level AA) | Supports | English on `/es/` carries `lang="en"`; other pages are English only. |
| 3.2.3 Consistent Navigation (Level AA) | Supports | The same primary nav, in the same order, on every page with site chrome, generated from one list (`_NAV_ITEMS`, held by `test_static_nav.py`). |
| 3.2.4 Consistent Identification (Level AA) | Supports | Shared components keep the same names across pages. |
| 3.3.3 Error Suggestion (Level AA) | Supports | Error text says what to do ("Enter a complete email address", "Trim the list and send it again", a URL must start with http or https). |
| 3.3.4 Error Prevention (Legal, Financial, Data) (Level AA) | Supports | Purchases go through Stripe Checkout's review step; the invoice path is a request, not a commitment; alert signup is double opt-in and unsubscribing is one link. |
| 3.3.8 Accessible Authentication (Minimum) (Level AA) | Supports | There is no sign-in. Alert signup is confirmed from an emailed link, and bundle setup uses the order reference Stripe adds to the address; neither asks the reader to remember, transcribe or solve anything. |
| 4.1.3 Status Messages (Level AA) | Supports | `role="status"` regions announce loading, result counts, copy confirmations and form outcomes without moving focus; on the agency-search branch the pickers announce how many agencies match, and when none do. Screen-reader confirmation pending. |

### Table 3: Success Criteria, Level AAA

Not included in this report. See `docs/accessibility.md` for the AAA criteria the site
tracks.

## Appendix A: fixes on branch a11y/acr-2026-11

1. **Alert and download pages declare a language, a viewport and a main landmark**
   (3.1.1, 1.3.1, 1.4.10). The confirm and unsubscribe pages (`infra/alerts/handler.py`)
   and the bundle download page (`infra/program-bundle/common.py`) had no `lang`, no
   viewport and no landmark. Held by
   `test_confirm_and_unsubscribe_pages_declare_language_viewport_and_main` and
   `test_download_pages_declare_language_viewport_and_main`.
2. **`/bundle/setup/` reads its hints with their fields, and marks and focuses the field
   to fix** (1.3.1, 3.3.1, 3.3.2). Held by three tests in
   `pipeline/tests/e2e/test_bundle_setup_form.py`.
3. **The accessibility statement names this report's edition** ("WCAG-edition VPAT
   report", was "508-edition VPAT"). Held by
   `test_accessibility_statement_names_the_edition_the_acr_is_written_in`.

## Appendix B: screen-reader walkthrough still to do

About three hours: NVDA with Firefox on Windows, VoiceOver with Safari on macOS, and
VoiceOver on an iPhone for the two pickers and the nav menu. Log each run in
`docs/accessibility-testing.md`. On each page listen for the page title, landmarks,
one level-one heading and the skip link first.

1. **Home (`/`).** Type "yolo" in "Find a published feed". Listen for the field's name,
   "combobox", "collapsed" then "expanded", and the match count from the status line.
   Down arrow: each suggestion should read its name, place and feed ID, and "selected".
   Enter opens the agency page. Escape closes the list and says so. (Rows 2.1.1, 4.1.2,
   4.1.3.)
2. **Agency page (`/agency/unitrans/`).** Headings in order: agency name, grade, top
   fixes. The grade badge alt text reads the grade. The map is silent. In the route
   table, each row is announced as a toggle button with its pressed state. (1.1.1,
   1.3.1, 4.1.2.)
3. **Brief and board (`/agency/unitrans/brief/`, `/board/`).** Navigate by table: each
   cell is read with its column and row header. (1.3.1.)
4. **`/app/`.** Filter by a state: the count is announced without focus moving. Open an
   agency: the new page title is announced and focus is in the main region. On the
   findings table, change the severity filter and listen for the new count. (2.4.3,
   4.1.3.)
5. **Alerts (`/subscribe.html`).** Tab through: each field's label and hint are read.
   Submit with nothing filled: the error is read and focus is on the email field. In the
   agency field, Down in the empty field offers "All agencies". After a successful send,
   the status line is read. (3.3.1, 3.3.2, 4.1.3.)
6. **Confirm page.** Open a confirm link on the phone: the page reads in English, at
   phone width, with the heading first. (3.1.1, 1.4.10.)
7. **Program and bundle (`/program/california/`, `/bundle/`, `/bundle/setup/`).** On
   setup, each field's hint is read with it; submit empty and confirm the error is read
   and focus lands on the program name. (1.3.1, 3.3.1.)
8. **Theme and nav menus.** Open Theme with Enter, arrow through the four options; the
   checked one is announced. On a narrow window, the Menu button reads "collapsed" and
   "expanded". (4.1.2.)
9. **404 (`/no-such-page/`).** The title and heading say the page was not found, and the
   three links are named. (2.4.2, 2.4.4.)

## Appendix C: Section 508 chapters (carried over)

The Revised 508 Standards incorporate WCAG 2.0 Level AA, which Tables 1 and 2 cover.

| Provision | Conformance | Remarks |
| --- | --- | --- |
| 302.1 Without Vision | Partially Supports | Semantic structure, text alternatives and ARIA are in place; the screen-reader walkthrough (Appendix B) has not been recorded, and the `/routes/` map has no on-page equivalent. |
| 302.2 With Limited Vision | Supports | 7:1 text contrast, 200% resize, 320 px reflow, a theme menu with high contrast. |
| 302.3 Without Perception of Color | Supports | See 1.4.1. |
| 302.4 Without Hearing | Not Applicable | No audio. |
| 302.5 With Limited Hearing | Not Applicable | No audio. |
| 302.6 Without Speech | Not Applicable | No speech input. |
| 302.7 With Limited Manipulation | Partially Supports | Keyboard operable throughout and targets meet 2.5.8; exploring the `/routes/` map needs dragging (2.5.7). |
| 302.8 With Limited Reach and Strength | Supports | No timed or force-based interaction. |
| 302.9 With Limited Language, Cognitive, and Learning Abilities | Supports | Plain-language summaries, a glossary, consistent navigation. |
| 502 Interoperability with Assistive Technology | Supports | Standard HTML and ARIA expose name, role, value and state. |
| 504 Authoring Tools | Not Applicable | Not an authoring tool. |
| CLI and GitHub Action | Supports | Output is plain text in the job log; the optional `--html` scorecard reuses the agency-page renderer. |
| 602.2 Accessibility and Compatibility Features | Supports | This report and `docs/accessibility.md`. |
| 602.3 Electronic Support Documentation | Supports | Docs are Markdown or HTML on the same templates. |
| 603 Support Services | Supports | A barrier report path at `/accessibility/` and the accessibility issue template. |

## Appendix D: measurements (2026-11-20)

Pages, each in light and dark: `/`, `/404.html`, `/no-such-page/`, `/agency/unitrans/`,
`/agency/yolobus/`, `/agency/unitrans/brief/`, `/agency/unitrans/board/`, `/app/`,
`/app/#/agency/unitrans`, `/app/#/compare`, `/subscribe.html`, the alert confirm and
unsubscribe pages, the bundle download page, `/program/`, `/program/california/`,
`/bundle/`, `/bundle/setup/`, `/bundle/sample/`, `/invoice/`, `/accessibility/`,
`/fix/expired_calendar/`, and from the agency-search branch `/`, `/subscribe.html` and
`/agency/unitrans/`.

| Check | Result |
| --- | --- |
| axe-core 4.13, WCAG 2.0/2.1/2.2 A and AA rules | 0 violations on every page, light and dark |
| axe, undecided ("incomplete") | 116 `color-contrast` nodes over gradients and textures (covered by the contrast gate); the theme button's `aria-controls` while its menu is closed |
| Lowest text contrast, light / dark / high contrast | 7.07:1 / 7.08:1 / 7.15:1 |
| Lowest non-text contrast (field borders) | 3.59:1 light, 3.80:1 dark, 6.66:1 high contrast |
| Focus rings | 8.50:1 or more against their backgrounds |
| Reflow at 320 CSS px | No page-level sideways scroll except `/bundle/sample/` (349 px, a data table) |
| Text spacing override | No text lost; the grade reel's hidden letters are by design |
| Tab walk | No focus without a visible indicator; nothing fully covered by the sticky header |
| Open agency pickers (agency-search branch), light and dark | 0 axe violations with the list open; `role="combobox"`, `aria-expanded="true"`, a named listbox, the active option ringed 3 px; options 65 px tall; the status line reads the count ("2 matches. Choose one to show its scorecard."); no sideways scroll at 320 px |

## Revision history

- 2026-11-20: Rewritten as a WCAG 2.2 A and AA report on the VPAT 2.5 Rev WCAG edition,
  after a template-by-template axe, keyboard, reflow, text-spacing and contrast pass in
  light and dark. 3.1.1, 1.3.1 and 3.3.1 hold after this branch's fixes. 2.1.1 and
  2.5.7 are reported as Partially Supports for the `/routes/` map, which the earlier
  edition recorded as an exception without a row-level rating. The 508 chapters are
  kept in Appendix C. The agency-search branch's combobox notes are folded into rows
  2.1.1, 3.2.2, 4.1.2 and 4.1.3.
- 2026-11-17: Corrected four remarks after a keyboard, zoom and contrast sweep of the
  live site: the skip link's label (2.4.1), the page language and the language of parts
  on `/es/` (3.1.1, 3.1.2), and target sizes (302.7).
- 2026-07-13: Corrected the evaluation-method description, recorded the 200% text-resize
  check, and kept screen-reader testing explicitly pending.
- 2026-06-22: Initial 508-edition report. Companion to `docs/accessibility.md` (WCAG 2.2
  AAA detail) and `docs/section-508-plan.md` (remaining work).
