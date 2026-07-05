# 0013 — Rebuild the visual identity on roadway signage

Status: accepted
Date: 2026-07-04

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
  use Overpass Mono, keeping the family in one voice. The identity is all
  sans, deliberately: signage has no serifs.
- **Color.** Grounds move from butter cream to an enamel sign-blank near-white
  with a green cast (`#f2f3ee` / `#e5e8df` / card `#fbfcf8`). The accent
  sharpens from amber to warning-sign yellow (`#fdc70a`). The pine chrome
  (`#102a20`) stays and is recast as what it already was: guide-sign green.
  The A-F grade ramp is unchanged; it already follows US sign-color semantics
  (guidance green, services blue-teal, warning, construction orange,
  regulatory red).
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

- One canonical Google Fonts URL is embedded in every page head (including
  ~4,600 prerendered agency pages) and in `site_shell.py`; regenerating the
  site keeps them in sync. Golden test fixtures were updated to match.
- `web/og.svg` uses a Helvetica-first stack so local rasterization
  (`rsvg-convert`) matches the signage voice without installing Overpass.
- The old palette's warmth now has to come from the deep greens, the yellow
  signal, and the plain-language voice rather than from cream paper. That is
  a deliberate trade: guidance, not judgment, is the register the signage
  language carries.
