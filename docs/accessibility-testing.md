# Manual accessibility test script

The axe gate (`.github/workflows/a11y.yml`) and the contrast gate
(`pipeline/scripts/check_contrast.py`) catch the ~30–57% of WCAG issues a machine
can find. This script is the other half: the human pass that the
[accessibility standard](standards/ACCESSIBILITY-STANDARD.md) requires as a
**review-gate**, and the evidence behind the functional-performance rows of the
[VPAT](vpat.md) (works without vision, with low vision, with limited manipulation).

It is written so a non-specialist can run it. You do not need to know the success
criteria; follow the tasks and note anything that gets in your way.

## When to run it

- **Every quarter** (a full pass), and
- **before merging any change** to the primary navigation, the theme switcher, the
  forms (`submit`, `subscribe`), the scorecard layout, the directory filters, or the
  map.

Record each run in the [log](#results-log) at the bottom. A dated, committed run is
what turns a "we tested it" claim into a real conformance artifact.

## Setup (pick at least one screen reader + keyboard + zoom each pass)

| Tool | How |
| --- | --- |
| **NVDA + Firefox** (Windows) | Free from nvaccess.org. Browse mode on. |
| **VoiceOver + Safari** (macOS) | Cmd+F5 to toggle. Use the rotor (VO+U) for headings/landmarks/links. |
| **Keyboard only** | Unplug the mouse. Tab / Shift+Tab / Enter / Space / arrows / Escape. |
| **Zoom + reflow** | Browser zoom to 200% and 400%; also try the page at a 1280-CSS-px-wide window. |
| **Forced colors** | Windows High Contrast, or DevTools → Rendering → emulate `forced-colors: active`. |
| **Reduced motion** | OS "reduce motion", or DevTools → Rendering → emulate `prefers-reduced-motion: reduce`. |

## Core tasks (the user journeys)

Run each task with a screen reader **and** keyboard-only. The page is fine if you can
complete the task without sighted, mouse-driven help.

1. **Find an agency and read its grade.** From `/` open the app, search or filter to
   an agency, open it. Confirm the screen reader announces the agency name, the
   overall grade, and the "top fixes" — in a sensible order.
2. **Read the NTD readiness block** on an agency page. The four checks
   (published / valid / current / agency_id) and the plain-language note should each be reachable
   and announced.
3. **Read a printable brief** (`/agency/<id>/brief/`). Headings and tables make sense
   when navigated by structure.
4. **Submit an agency** (`/submit.html`). Tab through every field; labels are
   announced. Submit empty — the error is announced and focus lands on the field to
   fix. Fix it and confirm the status message is announced.
5. **Subscribe to alerts** (`/subscribe.html`). Same field/label/error checks.
6. **Use the national map** (`/map/`). Confirm the map is announced as an image with a
   label that points to the agencies list, and that the list (`/agencies/`) carries the
   same information without the map.
7. **Switch the colour theme.** Open the Theme menu from the keyboard, move with arrow
   keys, choose High contrast and Dark; the choice persists and is announced.
8. **Navigate.** Use the skip link, then the primary nav. The current page's "stop" is
   announced as current. On a narrow window the menu button opens/closes the stops and
   Escape closes it.

## Cross-cutting checks (per surface)

**Screen reader**
- [ ] Landmarks present (banner / nav / main / contentinfo); one `<h1>`; headings nest without skipping levels.
- [ ] Every link's purpose is clear from its text or label; external/new-tab links say so.
- [ ] Form fields have announced labels; required is announced; errors are announced and describe the fix.
- [ ] Live regions announce status (loading, result counts, form status) without stealing focus.
- [ ] Images/badges have text alternatives; decorative graphics are silent.
- [ ] The active nav item is announced as current.

**Keyboard only**
- [ ] Everything operable by mouse is operable by keyboard; tab order matches reading order.
- [ ] Focus is always visible and never lost; no keyboard trap; Escape closes menus/panels and returns focus.
- [ ] The skip link works and lands on `#main`.

**Zoom & reflow (200% / 400%)**
- [ ] No content or function is lost; no horizontal scrolling of the page; nothing overlaps or clips.

**Forced colors / high contrast**
- [ ] All text and controls remain visible; focus indicators remain visible; meaning carried by colour also has text/shape.

**Reduced motion**
- [ ] The grade reel, bar fills, and reveal animations are suppressed or instant.

**Target size**
- [ ] Interactive targets are at least 44×44 CSS px (the choropleth state paths are the one documented exception — the chip grid is the ≥44px equivalent).

## Filing what you find

Use the in-product path: the **Report an accessibility barrier** button on
`/accessibility/`, which opens the
[accessibility issue template](../.github/ISSUE_TEMPLATE/accessibility.md). Note the
task, the tool, and what happened.

## Results log

One row per pass. Keep it append-only; this is the conformance artifact.

| Date | Tester | AT + browser | Tasks run | Result | Issues filed |
| --- | --- | --- | --- | --- | --- |
| _2026-06-22_ | _(template)_ | _NVDA+Firefox / VO+Safari_ | _1–8 + cross-cutting_ | _pass / pass-with-issues_ | _#nnn, …_ |
| 2026-07-10 | Automated CI remediation | Chromium + axe, keyboard, 320px reflow, forced colors, reduced motion | Automated equivalents for 1–8 + cross-cutting | Pass; this is not a screen-reader attestation | None |

The next quarterly pass must still be performed by a person using VoiceOver or
NVDA. Automated browser coverage is evidence for reflow and operation, but it
does not replace the review-gated assistive-technology walkthrough.
