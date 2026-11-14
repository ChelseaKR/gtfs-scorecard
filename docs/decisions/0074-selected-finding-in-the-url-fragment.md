# ADR 0074: The selected finding rides in the URL fragment

**Status:** Accepted (2026-11-05). Approved by the maintainer.

## Context

The finding handoff (agency page, call brief, board view, fix guide) keeps one
selected finding across surfaces. Its links carried the finding in the query
string: `/agency/<id>/?finding=<code>#finding-handoff`. Every agency page
linked to its own brief, board and history this way, and every state and
country rollup linked each member with an "Open next finding" link of the same
form.

Search Console showed the cost on 2026-11-05. For 5 of 5 sampled `?finding=`
URLs, Google chose the query URL as canonical and ignored the page's own
`<link rel="canonical">`. The clean agency pages were "Discovered" or "Crawled,
not indexed", while the query URLs carried the impressions (Mobivie 79 at
position 5). ADR 0067 removed these links from `/program/all/` only, so the
signal kept arriving from everywhere else.

## Decision

- Generated links put the finding in the fragment:
  `/agency/<id>/#finding=<code>`. The fix guide link adds `&agency=<id>`, and
  the history link adds `&at=trend-h`, the element to scroll to. One helper,
  `_finding_url` in `render_site.py`, builds every such link, and the landing
  page's `findingHref` in `web/src/landing-scorecard.js` follows the same form.
  The copied handoff text names the same fragment URL.
- The page script reads the fragment first and falls back to the query string,
  so old `?finding=` links (bookmarks, emails, other sites) keep selecting and
  highlighting the finding. It scrolls to the handoff, or to `at`, once the page
  has loaded, and reselects on `hashchange`, so picking another finding on the
  same page no longer reloads it.
- The canonical stays the clean URL. A fragment is never a separate URL to a
  crawler, so every link counts toward the canonical page.
- Feed-health email links (`alerts.py`) keep the query form. They are not
  crawled, and the page still reads them.

## Consequences

- Expected: the clean agency pages take the indexed slot and the query URLs
  drop out as duplicates over the following recrawls. This can only be measured
  in Search Console after deploy.
- Without JavaScript, a fragment link opens the right page at the top instead
  of at the handoff, and the first finding is shown. The old form needed the
  query string for the same selection, so this is a small loss for a few
  readers.
- `pipeline/tests/test_finding_fragment.py` fails if any generated link or
  golden page carries `?finding=`, and a negative control restores the old form
  to prove the check can fail.
- The structural SEO contract (`pipeline/scripts/check_site_seo.py`) reads a
  `#finding=` fragment as page state, not as an element id. It checks the
  element the script scrolls to instead: `at` when the link names one, and
  `finding-handoff` otherwise. Before that, every finding link on the site was
  reported as a missing fragment.
