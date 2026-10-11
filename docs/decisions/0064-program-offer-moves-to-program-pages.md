# ADR 0064: Program offer moves to program pages

**Status:** Accepted (2026-10-11). Amends the placement in
[ADR 0058](0058-program-panel-on-agency-scorecards.md).

## Context

ADR 0058 put one panel, "For programs that support several agencies", on
every agency scorecard on 2026-09-18, with the cheapest bundle's price and a
counted link to `/bundle/`. Its own stop rule said the panel could go if
agency-page sessions reached `/bundle/` and never bought.

A read-only investigation on 2026-10-11 measured the 23 days since (GA4
property 554864268, Search Console, and Stripe list calls):

- Sessions that landed on an agency page: 2,945. Engaged: 26. Sessions among
  them that later viewed `/bundle/`: 0. `begin_checkout`: 0.
- None of the 344 queries Search Console disclosed for the site carried
  commercial intent. Most were lookups for an agency's raw feed file in the
  summer and, since September, an operator's name.
- `/program/all/` drew 255 impressions at an average position of 7.9 since
  2026-09-12, and the fix guides at `/fix/<rule>/` 122 at 15.6. These are the
  pages whose readers do the work a program or vendor is paid for.

The panel's stop rule has a stronger answer than the one it anticipated: the
visitors it addressed did not reach the bundle page at all.

## Decision

The program panel moves off agency scorecards and onto the program rollup
pages, `/program/<id>/`, which includes `/program/all/`.

- **Agency pages.** The scorecard names nothing paid above the shared footer,
  the same as the call brief and the board one-pager. `_render_agency` no
  longer takes an offer, so no caller can put the panel back by passing one.
  The report route loses its "For programs" stop.
- **Rollup pages.** The "Board reports for this group" section, already
  after the member list, becomes the panel when `web/bundle/plan.json` sells
  something: the existing paragraph, then the cheapest one-time plan's label,
  amount, and delivery promise, one link to `/bundle/` marked
  `data-measure="bundle_panel_click"`, and the sample report. "Prices are on
  that page" gives way to the price itself. With no sellable plan it is the
  plain pointer, word for word what the app's rollup view shows.
- **Measurement.** Nothing new is recorded. `bundle_panel_click` (ADR 0055)
  now fires from the rollup panel, and the `/about/` privacy statement names
  the new place. The ADR 0057 events fire on `/bundle/` and
  `/bundle/setup/` as before, wherever the visitor came from.
- **Unchanged.** Stripe links, prices, `plan.json`, `/bundle/`, and
  `/data/history/` are untouched. The rollup panel is hidden in print, like
  the footer.

## Consequences

- An agency's own page no longer names a price. ADR 0058's softening of
  "agency-facing stays free" is reversed for the scorecard.
- `test_paid_tier_visibility.py` sweeps every agency golden for a `/bundle/`
  link above the footer and pins one panel per rollup page, after the member
  list, with the counted link, the sample, and the independence sentence.
  `test_program_offer_panel.py` pins the rollup panel's content and its
  negative controls.
- Measuring it: sessions that view a `/program/` page and later `/bundle/`,
  or reach `begin_checkout`. The day-90 table in `docs/program-plan.md` still
  decides the tier (bundle: 2026-12-11). This is a placement change, not a
  revenue forecast.
