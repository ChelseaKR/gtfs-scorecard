# ADR 0056: Google Analytics 4 beside PostHog, loaded from the same script

**Status:** Accepted (2026-09-17)

## Context

ADR 0055 put one first-party measurement script on every page, sending page
views and bundle checkout clicks to PostHog Cloud US. On 2026-09-17 the owner
decided that every public site in the portfolio carries Google Analytics 4 as
well, with each privacy page updated to match. The GA4 property for
gtfsscorecard.org is provisioned: measurement id `G-45H8Q9H93F`, property
554864268, with event data retention set to 14 months and Google signals
turned off in the property.

GA4 brings what PostHog's shim deliberately left out: Google's own script,
first-party cookies, and Google as a second recipient. The bar ADR 0055 set
still holds. A reader can find out exactly what is recorded, it is as little
as the question needs, and saying no is honoured without a banner.

## Decision

GA4 is a second, separate block at the end of `web/src/measure.js`. The
PostHog block above it changes only to honour the footer opt-out described
below. The two blocks share no variables, only the opt-out mark on the page,
so either can be turned off without touching the other.

**Where the id lives.** A GA4 measurement id is public by design, so it is
committed rather than held in the repository's secrets. It is
`measurement_ga4_id` in `site-seo.json`. The deploy's
existing `scorecard render-measure` step writes it into the one marked line of
the script (`var GA4_ID = ""; // measure:ga4-id`) in the assembled `_site/`,
the same way it writes the PostHog key. The committed script never carries
the id, so a local server and the accessibility build load nothing from
Google. An empty value turns GA4 off on the next deploy. A value that is not
shaped like `G-` plus capital letters and digits fails the deploy, and fails
the structural gate's config check, with the reason.

**What the block does before it loads anything.** It returns, with nothing
written to the page and no request made, when:

- no id was written;
- `navigator.globalPrivacyControl` is `true`, or Do Not Track is `"1"`;
- the page is served from `localhost` or a loopback address, so local work and
  the Lighthouse runs in `pages.yml` are never counted.

**What it sets up.** Consent Mode v2 defaults come first. `ad_storage`,
`ad_user_data` and `ad_personalization` are denied everywhere.
`analytics_storage` is denied for the EEA (the 27 EU members, Iceland,
Liechtenstein and Norway), the United Kingdom and Switzerland through gtag's
`region` parameter, and granted elsewhere. The site has no consent banner, so
in those regions the denial is permanent: no `_ga` cookie is ever set there,
and gtag sends only cookieless pings. The config sets
`allow_google_signals: false` and `allow_ad_personalization_signals: false`.

**What the page address is.** The config sets `page_location` to the origin
and path, and `page_referrer` to the referring site's origin. `/bundle/setup/`
receives the Stripe Checkout Session id in its query string, and the page a
buyer opens after it would carry that address as its referrer. ADR 0055 keeps
that reference away from PostHog for the same reason.

**What the gate allows.** `check_site_seo.py` declares the GA4 loader origin as
`measurement_ga4_host`. The declared script may name it beside the PostHog
host. No page, inline script or other JavaScript file may name any Google
Analytics host (`googletagmanager.com`, `google-analytics.com`,
`analytics.google.com`), so GA4 can reach a page only through the declared
script. The existing rules still hold: exactly one `/src/measure.js` on every
page and none on a redirect stub. That is how GA4 reaches every page family
the site emits, agency, board and brief views, program pages, `/bundle/`,
`/query/`, `/status/` and the rest, without an edit to any renderer.

**The footer opt-out.** Every page footer carries an "Opt out of analytics"
link (owner decision, 2026-09-17, for all four public sites). Without
scripts it is a link to `/about/#privacy-opt-out`. The first block of
`measure.js`, which runs before PostHog and GA4 and whether or not either is
configured, turns it into a toggle:

- The choice is stored on the device in `localStorage` under
  `scorecard-analytics` (`"off"` or absent). A stored `"off"` marks the page
  `data-measure-stopped` before either tool block runs, and both return on
  that mark.
- Opting out mid-page stores the choice, marks the page, stops PostHog's later
  events on that page, sets Google's `ga-disable-<id>` flag, and expires the
  `_ga` and `_ga_<container>` cookies on the host and each parent domain.
- The control then reads "Opt back in to analytics". Opting back in clears
  the stored choice; the page stays stopped, and both tools start again from
  the next page.
- The wording and the status message a screen reader hears come from data
  attributes in the footer markup (`ANALYTICS_OPT_OUT_HTML` and its Spanish
  twin in `site_shell.py`), so the script carries no copy.

`check_site_seo.py` fails any page that loads the measurement script without a
`[data-analytics-toggle]` control, so the opt-out reaches every page type the
measurement does. The cookieless pings GA4 sends in the EEA, the UK and
Switzerland under denied consent were accepted as they are by the same owner
decision.

**The disclosure.** `/about/#privacy` gains a Google Analytics part. It says
what GA4 records, names the `_ga` cookies and their two-year lifetime, says
what changes in the EEA, the UK and Switzerland, says the ad features are off,
names Google LLC and the 14-month retention of event-level data, and says how
to opt out, with the footer link first.

## Why these shapes

**One script, not a second tag.** A separate `ga4.js` would put a second
script tag on every page, one more request on every page even when GA4 is
off, and a second copy of the rules the gate already holds for the first. A
block inside the declared script costs no request when GA4 is off and reaches
exactly the pages the measurement contract already covers.

**A committed id, not a secret or a variable.** The id is in every page's
source once it ships. Committing it means a pull request turns GA4 on or off,
reviewed like any other change, and it needs no step only the owner can run.

**No CSP change.** The site sets no Content-Security-Policy: GitHub Pages
serves no custom headers, and no page carries a CSP meta tag. If one is ever
added, it needs `www.googletagmanager.com` in `script-src` and
`*.google-analytics.com` and `*.analytics.google.com` in `connect-src` and
`img-src`.

## Consequences

- GA4 sets first-party cookies outside the EEA, the UK and Switzerland. The
  PostHog block still sets none, and the privacy text now says which tool does
  what.
- Campaign tags in a link (`utm_*`) are not in the page address GA4 receives,
  because the query string is dropped, so traffic sources come from the
  referring origin. With ad storage denied, no ad click cookie (`_gcl_*`) is
  written either, which keeps the Google Ads upload's "no `gclid`" premise
  (`docs/paid-search-readiness.md`) true.
- The Lighthouse runs in `pages.yml` never load GA4, so they do not measure its
  cost. The weekly production Lighthouse run in `watchdog.yml` does.
- The property's enhanced measurement settings are part of what the disclosure
  describes. It says GA4 records page views, scrolls, clicks on links to other
  sites, and file downloads. "Page changes based on browser history events",
  "Site search" and "Form interactions" must stay off in the web data stream.
  The first would send a full address after `history.replaceState`, bypassing
  the path-only `page_location`. The other two record things the disclosure
  does not list.
- Turning GA4 off is one edit: set `measurement_ga4_id` to `""`. Removing it
  entirely is that edit, then deleting the block from `measure.js`, the
  `measurement_ga4_*` keys from `site-seo.json` and the gate, and the Google
  Analytics part of `/about/#privacy`, in one change.
