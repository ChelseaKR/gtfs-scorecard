# 0030 — Rebuild the visual identity on roadway signage

> Renumbered from 0013 on 2026-07-05 (remediation QW-8): that number collided
> with `0013-static-public-api.md`, which every in-repo "ADR 0013" reference
> (code comments, `docs/api.md`, `docs/expansion.md`) actually means. This
> document had no external references to its old filename, so it was a plain
> rename with no link updates needed elsewhere.

Status: accepted
Date: 2026-07-04
Updated: 2026-07-19

## Context

The site's first skin was a "civic report card": warm cream paper, a
high-contrast serif display face (Fraunces), and one amber accent. It was
carefully built (AAA-verified palette, three themes, print styles), but that
exact combination has become the most common default look of AI-generated and
template web design. For a tool whose reviewers include design- and
accessibility-literate program staff, reading as a template undercuts the
craft that is actually in it.

What was distinctive in the old skin was never the stationery layer. It was
the transit vernacular: the wayfinding nav whose sections are stops on a route
line, the split-flap grade reel, the departure-board hero, the route-line
rules. Those elements are grounded in the subject; the cream-and-serif wrapper
around them was not.

## Decision

Re-derive the identity from the visual language the subject already owns:
United States roadway and transit signage.

- **Type.** Display type is Overpass, the open digitization of the FHWA's
  Highway Gothic, the letterforms on road signs riders already follow. Running
  text stays Public Sans, the U.S. government's own open typeface (USWDS),
  which is what state program staff work in daily. Data and wayfinding labels
  use Atkinson Hyperlegible Mono. Its distinct letters and numerals make compact
  operational labels easier to scan while preserving the timetable voice. The
  identity is all sans, deliberately: signage has no serifs.
- **Color.** Grounds move from butter cream to an enamel sign-blank near-white
  with a green cast (`#f2f3ee` / `#e5e8df` / card `#fbfcf8`). The accent
  sharpens from amber to warning-sign yellow (`#fdc70a`). The pine chrome
  (`#102a20`) stays and is recast as what it already was: guide-sign green.
  The A-F grade ramp is unchanged; it already follows US sign-color semantics
  (guidance green, services blue-teal, warning, construction orange,
  regulatory red). Surfaces use solid fills; the identity does not use
  decorative color gradients or simulated lighting.
- **Components.** Grade letters sit in a roundel with a white keyline just
  inside the disc edge, the way a route number sits on a bus-stop flag; the
  rubber-stamp rotation is gone. Inner pages' footer becomes the same pine
  signage band as the header, so every page is bookended by the chrome.
  Layout, copy, and interaction patterns are unchanged.

Every changed color pair was verified against WCAG AAA (7:1 normal text,
4.5:1 large) in all three themes before the swap; the pairs live in
`pipeline/scripts/check_contrast.py`. The work also fixed two latent misses:

- The high-contrast theme's amber (`#b25c00`) did not clear 7:1 as kicker
  text on the black status board; it is now `#ffd34d`.
- The shared stylesheet's OS-dark block targeted bare `:root`, so choosing
  the Light theme while the OS preferred dark still rendered inner pages
  dark. It is now scoped to `:root:not([data-theme])`, matching the landing
  page's inline tokens.

## Consequences

- The three interface fonts are served locally as Latin WOFF2 subsets with
  system fallbacks and `font-display: optional`. The site does not depend on a
  third-party request for its visual identity.
- `web/og.svg` keeps local fallback stacks so rasterization (`rsvg-convert`)
  matches the signage voice without requiring the interface fonts to be installed.
- The old palette's warmth now has to come from the deep greens, the yellow
  signal, and the plain-language voice rather than from cream paper. That is
  a deliberate trade: guidance, not judgment, is the register the signage
  language carries.

## Follow-up: 2026-07-19 landing-page information architecture

The first signage pass changed the type, color, and shared chrome while leaving
the landing-page layout intact. The result still used a familiar marketing
composition: a two-column hero, a proof band, repeated card grids, and a final
call-to-action block. Those patterns made the page feel less specific to feed
quality than the inner reports, even though the visual tokens were now
subject-specific.

The landing page now treats the site as a public feed bulletin:

- The opening pairs a publication line and last-run link with a semantic
  coverage ledger. Counts keep curated feed records separate from published
  scorecards.
- The central route is the feed-inspection workflow itself. It follows a public
  feed through canonical validation, plain-language translation, and a dated
  result. The route metaphor therefore explains function rather than decorating
  the page.
- The shipped service is presented as a five-row scope ledger for agency work,
  program work, rider-facing feature research, the pre-publish feed bench, and
  machine-readable data use. The rows remain visible rather than hiding the
  product range behind interactive disclosure.
- A dedicated operating-notes ledger states the worldwide quality core,
  coverage limits, regional-module boundary, neutral realtime treatment, and
  the distinction between feed quality, compliance, and service quality.

The bulletin uses square editorial rules, a wider working canvas, flat signal
fills, and keylines instead of floating panels. This is a landing-specific
composition, not a new shared component family. The locally mirrored palette,
type families, theme behavior, solid-fill rule, and accessibility requirements
from the original decision remain in force. Inner pages and the agency report
route are unchanged.

## Follow-up: 2026-07-19 interactive service desk

Visual differentiation alone did not restore the scorecard's product value at
the top of the landing page. The bulletin now treats a real scorecard as its
working instrument:

- The first record is the latest published Unitrans artifact, not a fictional
  best-case grade. Yolobus is a second home-pilot state, with no comparison or
  ranking language.
- A reader can switch records, inspect all four category results, choose any
  prioritized fix in the snapshot, and follow that fix through source file,
  measurement check, finding code, and dated evidence.
- Agency-name search is opt-in. It loads only the smaller public ID file after
  input, then fetches the selected agency's individual artifact. The large
  score directory is not part of initial rendering.
- The chosen feed, fix, and category persist in the URL. Updates retain focus,
  use concise status announcements, and keep the last good record visible while
  another artifact loads.
- On phones, source order is question, real scorecard, directory tools, coverage
  evidence. This restores the scorecard to the first screen without hiding the
  five-row service scope or operating boundaries below.

The interface uses no rolling score animation or automatic rotation. State
changes use the existing flat fills, rules, labels, and departure-board grade
tile. Reduced-motion mode therefore loses no content or feedback.
