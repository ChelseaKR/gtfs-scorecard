# ADR 0058: One program panel on each agency scorecard

**Status:** Accepted (2026-09-18)

## Context

The program report bundle (ADR 0049) went on sale on 2026-09-12 and had no
purchase by 2026-09-18. The owner chose to put the effort into the path from
the free pages to the bundle instead of into ads.

Where do visitors land? Measured, not assumed:

- **Search Console, 2026-06-16 to 2026-09-11** (the owner's export): 34,297
  impressions and 128 clicks at an average position of 6.7. Agency scorecard
  pages carried 33,222 of those impressions (97%) and 113 of the clicks
  (88%), spread over 974 pages. The home page had 286 impressions and 8
  clicks. Among the queries Search Console discloses, about half are lookups
  for a raw feed file or a stop's coordinates ("<agency> gtfs stops.txt", a
  feed's zip URL). About a quarter look for an agency's feed. Two percent ask
  about validation.
- **GA4** (property 554864268) has collected since 2026-09-18 only. Its first
  day holds 47 sessions. 41 of them landed on `/bundle/`, most from the paid
  campaign, and none came from organic search yet. It cannot rank landing
  pages until it has a few weeks of data.

So the visitors are mostly feed consumers, with some agency staff. The buyer
the bundle is for, someone who supports several agencies, is a small share of
them. That reader already arrives on agency pages: the scorecard's "Send the
agency a note" block is written for them. Until now, the only way from an
agency page to the bundle was the shared footer, or a one-line pointer to the
free state rollup that names the bundle below its member list.

The rule this changes: `test_paid_tier_visibility.py` asserted that nothing
above an agency page's footer named the paid tier. ADR 0049 itself holds
"agency-facing stays free": nothing about the bundle may gate or degrade an
agency's own experience. The test's rule was a stricter placement choice made
at launch, and the owner's decision on 2026-09-18 revisits it.

## Decision

Each agency scorecard page (`/agency/<id>/`) carries one panel, "For programs
that support several agencies". `render_site._program_offer_section` renders it.

- **Where.** After the standards section and the free rollup pointer, before
  the badge and citation blocks. It sits below the grade, the fixes, the
  scores, and the evidence, and never in the hero. The page's section route
  lists it as "For programs", so it can be found without being in the way.
  It is hidden in print, like the footer.
- **What it says.** The scorecard and this agency's board one-pager are free
  and stay free. It says who the bundle is for and what it adds: this
  agency's board report in one archive with the others a program supports,
  with the program's name, logo, and accent on each cover. It then lists
  what that report holds for this agency, from this page's artifact: the
  grade, score, and check date, the category scores, the top fixes when there
  are any, and the score history when there are two or more checks. Each of
  those is a section `report.py` renders for this agency, under the same
  conditions.
- **Price.** The cheapest one-time plan, its label and amount, and the
  delivery promise, all read from `web/bundle/plan.json` through
  `bundle_offer_nodes`. The /bundle/ page's generated offers make the same
  refusals, so a plan with payments off quotes nothing. No amount is typed
  in source; the existing sweep in `test_paid_tier_visibility.py` still
  covers `pipeline/src`.
- **Links.** One primary action to `/bundle/`, a text link to the real sample
  at `/bundle/sample/`, the free one-pager, and the methodology section at
  `/how-to-read/#methodology-h`. The rubric stamp in the page's disclaimer
  now links the same methodology section.
- **Credibility.** The panel repeats the independence sentence ADR 0049 uses,
  the check date, the rubric and validator versions, and the feed-source line
  from the hero.
- **When it does not render.** Any of these switches it off: no sellable plan,
  a grade that is not a letter on the published scale, a score that is not a
  finite number, a missing check date, or a record that is not the current
  canonical feed. A page with missing data offers nothing. It never shows a
  panel with a gap where a number should be. The CLI's standalone scorecard
  passes no plan and renders as before.
- **What stays as it was.** The call brief, the board one-pager,
  `report.py`'s self-contained document, and the interactive app view name
  nothing paid. No popup, no countdown, no scarcity, and no new script or
  third-party request.

## Consequences

- An agency's own page now names a price. The panel addresses programs, says
  first that the agency's report is free, and sits below the grade, the fixes,
  and the evidence. That softens the change without removing it.
  `test_paid_tier_visibility.py` now allows exactly one panel on the
  scorecard page, only after the standards section, and still fails on a
  second offer or a `/bundle/` link anywhere else above the footer.
- The accessibility gate now also opens `/agency/yolobus/` and
  `/agency/barrie-transit/`, because every page that states the offer must
  be scanned (`test_the_a11y_gate_opens_every_page_that_names_the_paid_tier_in_its_content`).
- Measuring it needs no new tracking. GA4 records `page_location` for every
  view in a session. Sessions whose landing page is `/agency/...` and that
  later view `/bundle/` or reach `begin_checkout` or `purchase` (ADR 0057, PR #467)
  are the panel's effect. The privacy page's list of what is recorded is
  unchanged, because nothing new is recorded.
- Stop rule: `docs/program-plan.md`'s day-90 table still decides the tier. If
  a few weeks of GA4 data show agency-page sessions reaching `/bundle/` but
  never buying, the panel can go at no cost to anything else.
