# ADR 0054: The paid tier is described in llms.txt, and robots.txt stays open

**Status:** Accepted (2026-09-12)

## Context

`web/llms.txt` is the file published for machine readers. It listed the rubric,
the data API, and ten key pages, and it named the program report bundle
(ADR 0049) nowhere. An assistant asked "how do I get GTFS board reports for
every agency in my state" could read the whole file and answer that no such
thing exists, while `/bundle/` sat one link away in the site footer. The same
gap ran through `README.md`, which is what a person or a crawler lands on at
the repository.

Two facts shaped how that gap could be closed.

Prices live in `web/bundle/plan.json` and nowhere else, and
`pipeline/tests/test_paid_tier_visibility.py` enforces it across `web/**/*.html`,
`web/src/*.js`, and the pipeline package. That sweep does not reach `llms.txt`
or `README.md`, which is a gap in the sweep rather than permission: a price in
either file is a price that keeps being quoted after the plan changes, and
neither file is rendered from `plan.json`.

`web/robots.txt` is generated. `render_site.py` writes the same three lines on
every render, and `pipeline/tests/goldens/robots.txt` carries a copy. Three
paths are marked noindex in `site-seo.json`: `/bundle/setup/`, and every
agency's `/board/` and `/brief/` page. They carry `<meta name="robots"
content="noindex,follow">` today.

## Decision

`llms.txt` gains a "What is free, and what is paid" section that states the
boundary in plain terms, names the audience for the bundle, and links
`/bundle/` and `/support/`. It quotes no price and no plan size, and says why:
the bundle page reads those from live plan data, and a copy here would outlive
the plan. The same section, shortened, goes into `README.md` above "Support and
sponsorship". Both repeat the independence sentence the footer, `/support/`,
and `/bundle/` already use.

The key-pages list also picks up the pages a practitioner question routes to
and that were missing: `/tools/`, `/fix/`, `/check/`, `/compare/`, `/query/`,
`/procurement/`, `/crosswalk/`, `/how-to-read/`, `/program/all/`, `/status/`,
and the OpenAPI description. The `/leaderboard/` and `/trends/` entries now
point at `/pulse/`, which is where both redirect; the old entries sent a
machine reader to a meta-refresh stub. `/api/` is not listed because it is a
404: the read API is documented at `docs/api.md` and described by
`/api/v1/openapi.yaml`.

`robots.txt` is unchanged, deliberately.

- No `Disallow` is added for the noindex paths. A disallowed URL is never
  fetched, so the crawler never sees the `noindex` on it, and a page that is
  already indexed can stay indexed with nothing to read. `noindex,follow` is
  the working instruction for all three; adding a `Disallow` would disable it.
- Nothing else is blocked either. The site is public static output and the
  sitemap line already points at the one sitemap `check_site_seo.py` expects.
- If a robots directive is ever wanted, it belongs in `render_site.py`, not in
  the committed file. Editing `web/robots.txt` by hand survives until the next
  `scorecard render-site` and no longer.

## Consequences

A model answering a procurement-shaped question can find the paid tier and can
tell which side of the free/paid line a question falls on, without any price
being restated outside `plan.json`.

`check_doc_stats.py` sweeps `web/llms.txt` for corpus figures, so the new
section carries none; the counts stay in the one gated sentence at the top and
on `/status/`.

The noindex paths remain crawlable and unindexable, which is the combination
that actually keeps them out of results. If a future page needs to be kept out
of a crawl rather than out of an index, that is a different decision and needs
its own reasoning about what the crawler can still see.
