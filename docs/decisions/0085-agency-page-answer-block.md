# ADR 0085: The agency page opens with an answer block

**Status:** Accepted (2026-11-21). The maintainer chose option A for every
decision in the 2026-11 information-architecture proposal and approved its
copy table as drafted, including the privacy sentence below.

## Context

Real readers land on one agency scorecard from search, read one more, and
leave. The page opened with six equal buttons, a duplicate "All agencies"
backlink and a block of provenance notes. The feed URL that most of these
readers came for, and the free alert the site wants them to take (ADR 0084),
both sat inside that clutter. On a 390 px phone neither the grade letter nor
the feed URL of a failed-feed page was above the fold.

## Decision

The head of `/agency/<id>/` is, in order:

1. ADR 0084's failed-address sentence, when the last check got an HTTP 4xx.
2. A breadcrumb, Home › Agencies › <state or country> › <agency>. The place
   level is the state or country page `_portfolio_route` already resolves,
   and appears only when that page was rendered. The duplicate backlink goes.
3. The answer block: the existing grade card (kicker, name, one-line
   provenance, mirror caveat, grade, partial qualifier, trend, chips, and,
   approved on 2026-11-21 with this block, one sentence under the grade: "The
   grade is not a count of validator errors. It also weighs freshness and
   rider information." with a "How the grade works" link to the methodology
   on `/how-to-read/#methodology-h`) and a
   "Feed file" card with the feed URL, a Copy URL button and the Mobility
   Database version history. On a failed address the card says "Failed at
   last check (HTTP <code>)" and links the newest saved copy under ADR
   0084's rule. No public source URL, no card (the old "Source feed" rule).
4. "Watch this feed" as the page's one primary button, with ADR 0084's
   words unchanged.
5. The other actions as text links under "More for this agency": Correct
   this listing, Board one-pager, Call brief, Compare, and the clearance log
   when there is one. "Send fixes" is dropped from the row; its section
   follows the fixes as before.

Below the head: Top things to fix, then "About this feed", which now opens
with one sentence for riders ("Looking for times or routes? ..."). The
liveness, run and confidence notes and the disclaimer move into a "How we
measured this" section after the evidence, with their text unchanged. The
route box is titled "On this page" and lists that section.

Copy URL is shown only when the browser offers the clipboard, so a reader
without scripts never meets a control that does nothing. Presses of Watch
this feed and Copy URL are counted by the existing cookieless mechanism
(ADR 0055) as `agency_watch_click` and `agency_copy_url_click`, and
`/about/#privacy` says so in one added sentence. GA4 does not receive them.

Nothing paid appears above the footer (ADR 0064). Titles, descriptions,
canonicals and JSON-LD do not change. `AGENCY_TEMPLATE_REVISED` moves to
2026-11-21 (ADR 0067), so every agency page's sitemap lastmod moves once.

## Consequences

- Every agency page changes, in order only. No sentence is removed; the
  "Source feed:" label reads "Feed URL:".
- Stop rule: if indexed agency pages fall by more than 10%, or Search
  Console clicks excluding the "jgp nis" family fall by more than 25%, over
  the four weeks after deploy against the four weeks before, restore the old
  section order and keep the breadcrumb.
- `pipeline/tests/test_agency_answer_block.py` holds the order, the place
  crumb, the single primary action, the moved notes and the counted names.
