# Feature roadmap

A near-term, feature-level plan: the concrete things to build next and the order
to build them in. This sits between the two longer-horizon documents and should
be read with them:

- [`product-roadmap.md`](product-roadmap.md) is the multiyear view of user value.
- [`roadmap.md`](roadmap.md) is the multiyear infrastructure and scaling plan.
- This file is what to ship over the next few iterations. When an item ships, it
  moves out of this file and into the "where the product is today" paragraph in
  `product-roadmap.md`.

## Status: the 2026-06 list shipped in full

Every item from the previous version of this file (the expired-feed loop,
predictive freshness, and registry themes) has shipped and moved to
`product-roadmap.md` per the rule above. For the record, where each landed:

| Item | Where it landed |
| --- | --- |
| Resilient feed fetching | `net.py` (browser UA, backoff on 403/429), `fetch.py` Mobility Database mirror fallback, neutral "unreachable" state in `metrics.py` |
| Recurring stale-feed report per program | `rollups.py` `expired` block, rendered on every `/program/<id>/` page |
| `discover` on a schedule, replacements as PRs | `.github/workflows/discover.yml` (weekly) |
| "Still operating?" signal | `operating_note` in `agencies.yaml`, rendered on scorecard and directory |
| Liaison-ready outreach copy | outreach note block in `render_site.py` |
| Expiry forecasting and lead-time alerts | tiered 60/30/14/7-day digest in `alerts.py` |
| Expiry status in the API and badges | `expiry_status` in `docs/api.md`, status segment in `badge.py` |
| Findings cleared between runs | Causal-neutral "no longer reported" diff in `render_site.py` |
| Pin Mobility Database ids | `mdb_id` in `agencies.yaml`, exact-match discover |
| Realtime freshness | lapsed-header framing in `rt.py` |
| Vendor view of stale feeds | `vendors.py`, expiry aggregated by serving host |

The competitive sequence from [ADR 0005](decisions/0005-competitive-positioning.md)
also played out: fetching was hardened, coverage grew to about 1,128 published
scorecard pages and the location model became worldwide-capable, the crosswalk became an
on-site page, and the vendor view exists as an operator surface.

## What comes next

The next ship-list is drawn from two places rather than restated here:

- [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md), the cross-referenced index of
  research-derived items, tracks which of its R- and E-items remain open.
- [`ideation/04-impact-and-sequencing.md`](ideation/04-impact-and-sequencing.md)
  sequences the 2026-07 structural-fix and expansion candidates (FIX-01…13,
  EXP-01…17), with its "do-first" quadrant as the standing recommendation.

Items in those files are candidates for evaluation, not commitments. When one is
picked up and shipped, record it in `product-roadmap.md`'s "today" paragraph as
before.

## How to use this list

Pick the top unstarted item from the do-first quadrant in
`ideation/04-impact-and-sequencing.md` unless a pilot agency or liaison asks
for something specific. Keep each feature shippable on its own: a finished pull
request that renders, passes `make verify`, and updates the relevant doc.

Last verified: 2026-07-12 · Recheck cadence: when an item ships or monthly,
whichever is first.
