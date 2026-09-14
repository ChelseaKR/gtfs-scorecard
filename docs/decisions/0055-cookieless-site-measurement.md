# ADR 0055: Cookieless site measurement, disclosed on the page it measures

**Status:** Accepted (2026-09-13)

## Context

Until this decision the site recorded nothing about a visit. `docs/listing-policy.md`
said so, `README.md` and `docs/deploy.md` repeated it, ADR 0031 declined
real-user monitoring on the same ground, and `check_site_seo.py` failed the
build on any analytics loader. That was a portfolio-wide rule, and it was
withdrawn for this site on 2026-09-13.

What changed is that there is now a question the site cannot answer about
itself. Search Console shows 34,000 impressions and 128 clicks over three months,
almost all on `/agency/*` pages against raw-feed-lookup intent. The program
report bundle (ADR 0049) went on sale at `/bundle/` on 2026-09-12 with Stripe
Payment Links, and nothing on the site can say whether a visitor reaches that
page or follows a checkout link from it. The checkout itself happens on Stripe;
the click is the last thing the site can see. The day-90 rule in
`docs/program-plan.md` turns on a visitor count the Pages traffic view cannot
give per page.

The site is a civic tool whose readers include state staff and agencies. The
bar for measuring them is that a reader can find out exactly what is recorded,
that it is as little as the question needs, and that saying no is honoured
without a banner.

## Decision

One first-party script, `web/src/measure.js`, is the whole of what the site
collects about a visit. It sends two kinds of event to PostHog Cloud US:

- `$pageview`, once per page load, with the page path (never the query string
  or fragment), a page family (`home`, `agency`, `program`, `bundle`, `support`,
  `fix`, `directory`, `other`), and the referring domain (never the full
  referrer).
- `bundle_checkout_click`, with the plan id from `web/bundle/plan.json`, when a
  Payment Link on `/bundle/` is followed. `web/src/bundle.js` marks those links
  with `data-measure` and `data-measure-plan`; the script reports nothing else a
  reader clicks.

It is cookieless by construction. There is no SDK, so there is no autocapture
and no session recording. The visit id is a random UUIDv7 kept in
`sessionStorage`, which the browser discards when the tab closes; it is sent as
both `distinct_id` and `$session_id`, and every event carries
`$process_person_profile: false`, so PostHog keeps no person profile. Global
Privacy Control or Do Not Track returns before anything is sent. The script
never reads a form, an input, or the page text, and the post-checkout form,
including the buyer's email field, carries `ph-no-capture` so that a PostHog
SDK could not autocapture it either, should one ever be added.

The key reaches the site at deploy time only. `scorecard render-measure` writes
the `POSTHOG_KEY` secret into the one marked line of the script in the assembled
`_site/`, in `pages.yml`, after `web/` is copied and before the structural gate
runs. The committed copy has no key and sends nothing, which is also what a
deploy with no secret ships. A malformed key fails the deploy with the reason.
`refresh.yml` and `scorecard.yml` pass the secret through their `workflow_call`,
so a data-refresh deploy carries the same key a code push does.

The disclosure is on the site, at `/about/#privacy`, linked from the shared
footer on every page. It states what is sent, where (PostHog Cloud US, PostHog
Inc., United States), the retention (one year on the plan the project uses),
that the project discards the client IP at ingestion, and how to opt out. It
describes the script and nothing more. `docs/listing-policy.md`, `README.md`,
`docs/deploy.md`, `docs/release-checklist.md`, `docs/audits/dpia-lite.md`, and
ADR 0031 are amended to match.

## Why these shapes

**A shim rather than `posthog-js`.** The SDK is about 50 KB gzipped and brings
autocapture, session recording, and feature flags, none of which the question
needs and two of which the disclosure would then have to rule out by
configuration. Sixty lines of `fetch` cover a page view and a click, keep the
Lighthouse budgets where they are, and make the disclosure a description of a
file a reader can open. This is the same choice `family-greenhouse` made, which
keeps the two products on one vendor and one pattern.

**A per-tab id rather than PostHog's server-side cookieless mode.** That mode
hashes IP, user agent, and domain with a daily salt on the server, which is
also cookieless, but it needs the SDK and a project setting this repository
cannot verify from the outside. A random id in `sessionStorage` is verifiable
from the script alone, and it answers the question: whether a visit reached
`/bundle/` and clicked is a within-visit path. What it gives up is joining two
visits by the same person, which the disclosure can then say plainly.

**Path only, domain only.** `/bundle/setup/` receives the Stripe Checkout
Session id in its query string. That id is an order reference, and an event
carrying it would publish a bundle identifier to a third party, which the
bundle handlers are built to never do. Dropping the query string and the
fragment from the URL, and the path from the referrer, removes the class of
leak rather than one instance of it.

**The gate is the disclosure's guarantee.** `check_site_seo.py` now holds the
site-measurement contract in place of the no-tracking one: exactly one
`/src/measure.js` on every page, none on a redirect stub, no vendor analytics
loader (the PostHog SDK asset hosts are on that list) and no mention of the
measurement host anywhere but the declared script, and no `https://` host inside
the declared script but the declared one. `tests/test_measure.py` holds the
script's own promises: no `localStorage`, no `document.cookie`, no `FormData`,
no `location.search`, no `location.href`, no `document.referrer` outside the
domain helper, `$process_person_profile: false`, and both opt-out signals. It
also holds the `ph-no-capture` marker on the setup form and its email input,
the key line's substitution, and that the self-contained board report a buyer
receives never carries the script.

## Consequences

- A code push or a data refresh with no `POSTHOG_KEY` secret ships exactly the
  committed script, which returns on its first line of logic.
- The two numbers the deploy prints beside each other in `seo-report.json`,
  `measured_pages` and `html_files`, differ by exactly the redirect stubs when
  the contract holds.
- Adding a third event means editing `measure.js`, the `/about/#privacy` text,
  and `test_measure.py` in one change; the gate does not know the event
  vocabulary, and that is deliberate, because the disclosure is prose a person
  keeps.
- Owner steps, in order, each of which only she can do: create the PostHog
  project on US Cloud; turn on "Discard client IP data" in its settings; confirm
  the plan's retention matches the one-year sentence on `/about/` (a paid plan
  keeps events seven years, and the sentence would change); then
  `gh secret set POSTHOG_KEY --repo ChelseaKR/gtfs-scorecard` with the value
  supplied in her own terminal. The next scheduled publish ships it.
- If the rule is ever reversed again, the reversal is: delete the secret,
  remove the script tag from `_page` and the hand-authored pages (`make
  sync-measure` after deleting the tag from `with_measure_tag`), and restore the
  no-tracking text. The gate then fails until `site-seo.json` drops the
  `measurement_*` keys, which is the right order: the disclosure changes last.
