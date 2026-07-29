---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: route color and text color don't contrast

Code: `route_color_contrast` (MobilityData validator)

## What this means

`routes.txt` lets you set `route_color` (the route's background colour) and
`route_text_color` (the colour of the route name drawn on it). The two are too
close in brightness, so the label is hard to read against its background.

## Why it matters

Apps and maps draw the route number or name in `route_text_color` on a swatch of
`route_color`. Low contrast makes that label hard to read for everyone and
unreadable for low-vision riders, which undoes the point of branding the route
at all. This is an accessibility fix as much as a cosmetic one.

## How to fix it

- **Set `route_text_color` to whichever of black (`000000`) or white
  (`FFFFFF`) contrasts more with the route colour.** Dark route colours take
  white text; light ones take black.
- Aim for a contrast ratio of at least 4.5:1 (the WCAG AA threshold). Any online
  contrast checker will tell you whether a colour pair passes.
- If a route has no strong brand colour, leaving both fields blank is fine; apps
  fall back to readable defaults.

## How long it usually takes

A few minutes: pick black or white text per route colour. A bulk edit in most
scheduling tools.
