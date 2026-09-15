# Paid search (Google Ads) readiness for the program report bundle

Prepared 2026-09-14. Everything below is code- and content-side preparation
for a Google Search campaign selling the program report bundle
(`/bundle/`, [`docs/program-plan.md`](program-plan.md)). No ad account,
Merchant Center account, or other external account was created; no money was
spent anywhere; nothing was submitted to Google. Prices below are read from
`web/bundle/plan.json`, the only source of truth for them
(`bundle_25` $149, `bundle_100` $349, `refresh_mo` $49/mo, `refresh_yr`
$490/yr); if that file changes, re-check every price quoted here before
reusing this document.

**2026-09-15 update:** a real conversion action now exists
(`customers/2688527650/conversionActions/7769927171`) and §3's "later,
separately" upload job (originally step 10 below) is built --
`infra/program-bundle/ads_conversion_upload_handler.py`. §3 and step 10
below are historical (they describe the state as of 2026-09-14, before the
conversion action existed); read
[`docs/google-ads-upload-setup.md`](google-ads-upload-setup.md) for the
current design and the owner steps that remain.

## 0. Why paid search, in one paragraph

Organic traffic to this site is almost entirely lookup intent: someone who
wants one agency's raw feed, a `stops.txt`, or a definition of GTFS. That
traffic already exists and converts to the free tools it wants, not to a
$149 program bundle -- a program manager preparing board packets for many
agencies is a different, much smaller, much higher-intent search population,
and a brand-new page has no organic authority to rank against a decade of
established GTFS reference content for those broad terms anyway. Paid search
is the right tool specifically because the buyer population is small and the
per-click cost of reaching them is likely to be low (see the budget table in
§4) -- it does not depend on ranking against gtfs.org or MobilityData's own
docs, it depends on bidding on a few dozen people a month who type something
closer to "GTFS compliance audit" than "GTFS stops.txt download."

## 1. Keyword research

Method: no Ads account was created (Keyword Planner needs one), so this uses
Google Trends (free, account-less, checked for relative interest and
"related queries" on the terms below) plus domain knowledge of the transit
data-quality space reflected in this repo's own content (the rubric in
`docs/rubric.md`, the MobilityData validator taxonomy, the free
`/procurement/` page's own framing of "GTFS vendor contract language").
Absolute search volume was not measurable without an Ads account; every term
below is inherently low-volume (this is a request-for-proposal-shaped niche,
not a consumer one), which is exactly the shape paid search handles well and
organic SEO does not.

### Tier 1 -- exact buyer intent (high priority)

These name the product's actual job (a data-quality report an oversight
body can act on) or the actual buyer role (a program managing many
agencies), not just the underlying technology.

| Keyword | Why it matches the buyer |
| --- | --- |
| gtfs data quality audit | Names the deliverable directly |
| gtfs compliance report | Names the deliverable directly |
| gtfs compliance audit tool | "Tool" signals someone evaluating a product, not reading a spec |
| gtfs validator report | Report framing, not "how do I run the validator" |
| transit feed compliance report | Program/oversight framing ("compliance") |
| gtfs quality scorecard for transit agencies | Matches the product's own category name |
| gtfs data quality board report | Matches the product literally |
| transit data quality reporting tool | "Reporting tool" is a buyer's phrase, not a developer's |

### Tier 2 -- adjacent buyer intent (medium priority)

Signals a program, technical-assistance, or vendor role, or a validator
question asked by someone thinking about more than one feed -- worth
bidding on, but a broader or less certain match to "wants a branded board
report for many agencies" than Tier 1.

| Keyword | Note |
| --- | --- |
| mobilitydata validator errors explained | The task brief's own example; likely a mix of a single agency's engineer and a TA-center reviewer, so priced and bid lower than Tier 1 |
| gtfs validator notices explained | Same shape as above |
| transit data quality score | Close to the product's own "grade" framing |
| gtfs feed quality dashboard | Multi-feed framing |
| state dot gtfs oversight tool | Names the program persona directly |
| gtfs quality monitoring for multiple agencies | Explicit "multiple agencies" |
| rural transit gtfs technical assistance | Matches the Cal-ITP-style TA-center persona this site already targets |
| gtfs feed health monitoring | Ongoing-oversight framing, close to the refresh subscription |
| transit data quality kpi | Board/reporting framing |

### Tier 3 -- broad / informational (low priority; source for negatives)

Real, measured lookup-intent shapes (the organic traffic this site already
gets, converting near zero to a purchase). Bid these only if ever testing an
awareness campaign with its own budget and expectations; do not let them
share a campaign or budget with Tier 1/2.

| Keyword |
| --- |
| gtfs stops.txt download |
| gtfs feed download |
| what is gtfs |
| gtfs validator free |
| gtfs.zip example |
| mobilitydata gtfs validator github |
| gtfs schedule format |
| transit agency gtfs feed url |

### Negative keywords (apply at the campaign level, not just per ad group)

Exclude the lookup-intent shape explicitly, plus adjacent terms that read as
informational or as a different product entirely:

`stops.txt`, `download`, `free`, `open source`, `github`, `example`,
`tutorial`, `how to create gtfs`, `gtfs generator`, `gtfs builder`, `format`,
`specification`, `schema`, `what is`, `trip planner`, `route planner`,
`app` (a rider-facing transit app, not this product), `job`, `jobs`,
`career` (this space also gets transit-hiring-adjacent noise).

One category deliberately left out of both the bid list and the negative
list: procurement/RFP-language queries ("gtfs rfp language", "gtfs vendor
contract requirements"). This site already ranks the free `/procurement/`
page for that shape of search, and that page is the right destination for
it -- a program figuring out what to put in a vendor contract is not yet a
program buying board reports about agencies it already oversees. Bidding on
it would compete with a page that already serves the visitor for free and
would likely convert closer to Tier 3 than Tier 1.

## 2. Ad copy

Four Responsive Search Ad variants below, one per suggested ad group,
mapped to the keyword tiers above. Every character count is measured
against Google's limits (headlines <= 30 characters, descriptions <= 90);
counts are shown so they can be pasted in verbatim. Every claim is grounded
in what `/bundle/` and `plan.json` actually say: the guarantee text is the
page's own ("within the hour, always within two business days ... If it is
later than that, the purchase is refunded"), the independence line is the
page's own ("Grades ... are never for sale"), and every price matches
`plan.json` exactly. None of the variants uses "audit" as a verb the
product performs on demand -- the bundle packages already-published,
already-computed scores; it does not re-score a feed at purchase time, so
copy says "report" and "board report," not "we'll audit your agencies."

### A -- Compliance / audit ad group (Tier 1: audit, compliance report)

| Headlines (<=30) | len |
| --- | --- |
| GTFS Data Quality Reports | 25 |
| Board Reports, One Archive | 26 |
| From $149 per Archive | 21 |
| 2-Day Delivery or Refunded | 26 |

| Descriptions (<=90) | len |
| --- | --- |
| One board-ready GTFS quality report per agency you support, in one branded archive. | 83 |
| Grades are never for sale. Same public rubric as the free site. Delivered in 2 days. | 84 |
| Built for state programs, TA centers, vendors, and consultancies. Refreshed monthly. | 84 |

### B -- Program / TA-center ad group (Tier 1/2: state programs, oversight)

| Headlines (<=30) | len |
| --- | --- |
| Board Reports, Every Agency | 27 |
| For State Transit Programs | 26 |
| One Archive, Your Branding | 26 |
| $149 for Up to 25 Agencies | 26 |

| Descriptions (<=90) | len |
| --- | --- |
| Package every supported agency's GTFS quality report into one branded archive. | 78 |
| Delivered within 2 business days, guaranteed, or the purchase is refunded. | 74 |
| Grades, methodology, and listings are never for sale. Same numbers as the public site. | 86 |

### C -- Validator / report ad group (Tier 1/2: validator report, notices)

| Headlines (<=30) | len |
| --- | --- |
| GTFS Validator Board Reports | 28 |
| Reports for Every Agency | 24 |
| One Branded Archive, $149+ | 26 |
| Monthly Refresh Available | 25 |

| Descriptions (<=90) | len |
| --- | --- |
| Turn MobilityData validator results into board-ready GTFS quality reports. | 74 |
| One report per agency, one archive, your program's name and logo on the cover. | 78 |

### D -- Vendor / consultancy ad group (Tier 1/2: feed vendor, consultancy)

| Headlines (<=30) | len |
| --- | --- |
| GTFS Reports for Clients | 24 |
| One Archive, Every Agency | 25 |
| Branded Board Reports | 21 |
| Refunded If Late, Guaranteed | 28 |

| Descriptions (<=90) | len |
| --- | --- |
| Prepare board-ready GTFS data quality reports for every agency you support. | 75 |
| One-time from $149, or a refreshed monthly archive from $49. No influence on grades. | 84 |

Every variant has 4 headlines and 2-3 descriptions, above Google's stated
minimum of 3 headlines / 2 descriptions for a Responsive Search Ad.

### Landing page per ad group

Recommendation: point all four ad groups at `/bundle/` itself, not a new
purpose-built page, for launch. Reasoning:

- `/bundle/` already states the price, the guarantee, and the independence
  promise above or just below the fold (see §5's review) -- the three things
  a cold click needs before paying $149 sight-unseen.
- A stripped, nav-free landing page would need its own route, its own entry
  in `site-seo.json`'s `noindex_path_patterns` (so it does not compete with
  `/bundle/` for the same organic queries), its own pass through the
  accessibility gate (`test_the_a11y_gate_covers_every_page_that_renders_a_purchase_surface`),
  its own localization-readiness accounting, and its own price-sync wiring
  to `plan.json` -- this repo gates all of those, on purpose, and a
  duplicate purchase surface is real ongoing maintenance, not a one-time
  page. That is not "small" by this lane's own rule to keep code changes
  small.
- If, after real ad spend, `/bundle/`'s conversion rate looks nav-distraction-limited specifically (high click-through, low time-on-page, exits through
  the primary nav rather than the plan cards), building a stripped variant
  becomes a scoped, measured follow-up instead of a guess made before any
  click has happened.

## 3. Conversion tracking: the seam

Code: `infra/program-bundle/conversion_tracking.py` (new),
`infra/program-bundle/webhook_handler.py` (wired in),
`infra/program-bundle/main.tf` (new Terraform variable
`google_ads_conversion_action`, default `""`). Tests:
`pipeline/tests/test_program_bundle_handlers.py` (8 new tests, including two
negative controls -- see §6).

**What it does today: nothing.** `GOOGLE_ADS_CONVERSION_ACTION` is unset in
every deploy, so `conversion_tracking.build_conversion_event` always
returns `None` and the webhook's behavior is byte-for-byte what it was
before this change. That is the point: the seam had to exist without
inventing a fake account or ID to test it against.

**Where it hooks in.** The Stripe webhook's `checkout.session.completed`
handler already writes one row to the `bundles` table the moment a purchase
is confirmed (`webhook_handler.apply_event`) -- that is the earliest
server-side moment "a sale happened" is knowable, well before the buyer
fills out the setup form or the archive is built. Right after that row is
written, and only when the checkout was confirmed as this product's (never
for a Stripe-outage `"unverified"` note -- see §6), `note_conversion` builds
a payload and hands it to `emit`.

**What shape it builds.** Google Ads' "Enhanced conversions for leads":
a SHA-256 hash of the buyer's (trimmed, lowercased) email, a conversion
value and currency read straight off the Stripe event (`amount_total`,
`currency` -- no second Stripe API call), a timestamp, and the plan. This
is deliberately not a client-side pixel or tag: `web/src/measure.js`
already keeps this site cookieless
([`docs/decisions/0055-cookieless-site-measurement.md`](decisions/0055-cookieless-site-measurement.md)),
and Enhanced Conversions for Leads is the one Google Ads conversion path
that needs no cookie, no script, and no `gclid` capture on the frontend --
it matches server-side on the hashed identifier against Google's own
signed-in-user graph. The email hashed is the same one the webhook already
stores in the `bundles` table; nothing new is collected, only reused after a
sale is already known.

**What it does NOT do, on purpose.** It does not call the Google Ads API.
A real upload needs OAuth (a developer token, an OAuth client, a refresh
token, a login customer ID) -- credentials this repo does not have and
should not hold speculatively. `emit` writes one structured JSON line to
the webhook Lambda's own CloudWatch log group
(`{"conversion_event": {...}}`). That is a deliberate, inspectable stopping
point: once real events are flowing to CloudWatch, building the small
scheduled job that reads them and calls the Google Ads API's conversion
upload (via the `google-ads` Python client library) is a much better-
informed follow-up than writing that call blind today.

**Turning it on is the one-line change the brief asked for**: set
`google_ads_conversion_action` (Terraform variable, `main.tf`) to the real
conversion action resource name once one exists, and re-apply. See owner
step 8 below for exactly where that ID comes from and what accuracy
trade-off to expect from having no `gclid`.

## 4. Budget and economics -- a number to react to, not a forecast

**These are estimates from general knowledge of B2B/niche-software Search
CPCs, not measured data** -- no Ads account exists to pull real numbers
from, and none was created to get them.

The clean way to frame this: because spend = clicks x CPC and revenue =
clicks x conversion rate x average order value, **the break-even conversion
rate is just CPC / average order value**, independent of how many clicks
are bought. Two average-order-value scenarios: $149 (a buyer takes only the
cheapest one-time bundle) and $249 (a blend that includes some $349
bundles and refresh subscriptions).

| Assumed CPC (estimate) | Break-even conversion rate at $149 AOV | Break-even conversion rate at $249 AOV |
| --- | --- | --- |
| $3 (low: hyper-niche exact terms, no real competing bidder) | 2.0% | 1.2% |
| $5 | 3.4% | 2.0% |
| $8 | 5.4% | 3.2% |
| $12 (moderate: overlaps generic "compliance software" B2B terms) | 8.1% | 4.8% |
| $20 (high: worst case if broader B2B software advertisers outbid on shared terms) | 13.4% | 8.0% |

A self-serve product with an instant Stripe checkout and no sales call
typically converts a well-targeted, high-intent B2B visitor in the low
single digits to high single digits (2-8%) by general industry benchmarks
-- so break-even looks plausible at the low-to-moderate end of that CPC
range and looks like it needs an unusually good page at the high end. That
is a reason to start with tight, cheap, Tier-1 exact/phrase-match terms
(§1) and Manual CPC or "Maximize Clicks" bidding (not "Maximize
Conversions," which has no conversion history yet to learn from) rather
than an assumption that any CPC clears easily.

Rough click volume at a few weekly budgets, same CPC range:

| Weekly budget | Clicks/week at $5 CPC | Clicks/week at $12 CPC |
| --- | --- | --- |
| $35 ($5/day) | ~7 | ~3 |
| $70 ($10/day) | ~14 | ~6 |
| $140 ($20/day) | ~28 | ~12 |
| $350 ($50/day) | ~70 | ~29 |

**The volume caveat matters more than the rate math.** At 3-30 clicks a
week, one sale swings the observed conversion rate by several points either
way; a zero-sale week at this volume is not evidence the campaign failed,
and a one-sale week is not evidence it is working. Plan to look at 4-8
weeks of pooled clicks before judging conversion rate, not week to week.

Recommended starting point, given the above: $10/day ($70/week), Manual CPC
or Maximize Clicks with a cap around $8-10, Tier 1 keywords in Phrase match
plus a handful of the tightest Tier 1 terms in Exact match, all of Tier 3 as
account-level negatives. That is cheap enough that even zero sales for
several weeks is a bounded, known cost, and it produces enough clicks (~10-
15/week) to start reading a real number instead of noise sooner than a
smaller budget would.

## 5. Landing page (`/bundle/`) -- cold-traffic review

Read as if arriving from a search ad with zero prior context. What already
works well for a cold, skeptical visitor:

- **Price is stated immediately and without scripting.** The "Plans and
  prices" section is unmissable, and even a no-JS visitor sees all four
  amounts (the `<noscript>` fallback list).
- **The guarantee is concrete and dated, not vague.** "Normally within the
  hour, always within two business days. If it is later than that, the
  purchase is refunded. That is a commitment, not an estimate" answers "what
  if this doesn't work" before a visitor has to ask.
- **The buyer persona is named in the first sentence** ("A state program, a
  technical-assistance center, a feed vendor, or a consultancy...") -- a
  cold visitor can self-qualify in one sentence.
- **The independence promise is real and specific** ("No influence over the
  scores... the bundle's numbers are the same ones on the public site"),
  which matters more for paid traffic than organic: someone who clicked a
  paid ad is primed to wonder whether the product is pay-to-play.

What a cold visitor lacked, and the one fix made (small, see below): the
page never said what GTFS Scorecard itself *is* before assuming the reader
already knows. Everything past the first sentence assumes the reader
already understands "board report," "grade," and why GTFS data quality
matters -- true for someone who arrived from the homepage or an agency
page, not necessarily true for someone who typed "gtfs compliance audit"
into Google and has never seen this site. **Fix applied**: one sentence was
added to the top of the page's lede (`web/bundle/index.html`) stating
plainly what the free scorecard measures, before the persona sentence:
"GTFS Scorecard grades a transit agency's
published GTFS feed for data quality and rider-information gaps, free, for
any agency, at gtfsscorecard.org." This was verified small: it adds one
sentence outside every generated/gated region of the page (the offers and
noscript-plan blocks `make sync-bundle-offers` owns), carries no price
digit (the price-ownership test scans this file), and the full targeted
test suite for this page (`test_paid_tier_visibility.py`,
`test_bundle_offers_markup.py`, `test_bundle_plan_contract.py`,
`test_delivery_deadline.py`, `test_l10n_readiness.py`) plus the full
`make verify` gate passed after the change.

Flagged but **not** fixed, because each is either not small or is a
judgment call better made after real traffic exists:

- **Payment trust ("GTFS Scorecard never sees your card") sits in step 1 of
  "How it works," well below the pricing section.** A cold visitor deciding
  whether to trust a $149 charge to an unfamiliar brand might want that
  nearer the price. Left alone because moving it changes the page's
  existing structure (and its accessibility heading order) for a benefit
  that is a guess until there is click data.
- **No visible social proof or "how many reports have shipped" trust
  signal.** True today: there are zero sales, so there is nothing honest to
  show yet. Revisit once the first few sales land.
- **A purpose-built, nav-free landing page** -- covered in §2's per-ad-group
  recommendation: plausible upside, not small, deferred to a measured
  follow-up rather than built speculatively.

## 6. Tests and negative controls

`pipeline/tests/test_program_bundle_handlers.py` adds:

- `test_webhook_fires_no_conversion_event_while_unconfigured` -- the
  negative control for the whole seam: with `GOOGLE_ADS_CONVERSION_ACTION`
  unset (every deploy today), a real confirmed checkout still gets noted in
  the `bundles` table, but the conversion sink is never called. Without
  this test, a spy on the sink would pass trivially whether or not the seam
  ran at all.
- `test_webhook_fires_a_conversion_event_once_a_conversion_action_is_configured`
  -- the positive case: setting the one env var produces exactly one
  emitted event, with the right hashed email, value, currency, and plan,
  and confirms the raw email string never appears in the emitted payload.
- `test_webhook_fires_no_conversion_event_for_an_unverified_checkout` --
  configured, but Stripe is down and the checkout could not be confirmed as
  this product's; the event must not fire even though the action is set,
  because firing on a guess would misreport a sale to Google Ads rather
  than just miss one.
- `test_conversion_event_is_none_with_no_email_even_when_configured` and
  `test_conversion_event_is_none_while_unconfigured` -- unit tests on the
  pure builder function directly.
- `test_hash_identifier_normalizes_before_hashing` -- confirms the
  trim/lowercase-before-hash normalization Google Ads' enhanced conversions
  require.

`make verify` (ruff, mypy, the full pytest suite with 92% branch-coverage
gate, contrast, readability, versions, doc-stats, supersession-review, and
the bare-marker sweep) passed clean after every change in this lane.

## 7. Owner steps, in order

Everything through step 5 needs no engineering; steps 6-8 need the code
already merged from this lane.

1. **Create the Google Ads account** at ads.google.com. When it asks to
   build a campaign automatically ("Smart" mode), decline and switch to
   Expert Mode -- the default wizard tends to spend on broad match and the
   Display Network with little control, which is the opposite of what a
   near-zero-conversion-history niche product needs at launch.
2. **Create one Search campaign** (not Smart): Network = Search only
   (uncheck Display Network and Search Partners to start), Locations = the
   country/countries where the target programs are (US, given the buyer
   persona), Language = English, budget and bidding per §4's recommended
   starting point ($10/day, Manual CPC or Maximize Clicks, ~$8-10 max CPC).
3. **Create four ad groups**, one per §2 variant (Compliance/audit,
   Program/TA-center, Validator/report, Vendor/consultancy).
4. **Add keywords**: Tier 1 (§1) in Phrase match per its themed ad group;
   the tightest few Tier 1 terms additionally in Exact match. Tier 2 in
   Phrase match, split across the closest-matching ad group.
5. **Add negative keywords** at the campaign level: every Tier 3 term (§1)
   plus the explicit negative list, so lookup-intent clicks (the traffic
   already measured to convert near zero) cannot spend the budget.
6. **Import the ad copy** (§2): either paste each variant's headlines and
   descriptions directly into its ad group's "Responsive search ad" editor
   in the Ads UI, or, for a bulk import, use Google Ads Editor (a free
   desktop app) with a CSV built from §2's tables. Set each ad group's
   final URL to `https://gtfsscorecard.org/bundle/`.
7. **Add extensions**: sitelinks to `/bundle/#plans-h`; a price extension
   naming the four plans and prices in `plan.json`; callout extensions
   ("Open source," "No influence on grades," "2-day delivery guarantee");
   a structured snippet for "Plans: One-time, Monthly, Yearly."
8. **Create the conversion action, then flip the one-line switch**: in
   Ads, Tools & Settings -> Conversions -> New conversion action -> Website
   (or Import, if following Google's current "Enhanced conversions for
   leads" setup flow for that release of the UI) -> enable Enhanced
   Conversions for Leads for it. Copy its resource name
   (`customers/<id>/conversionActions/<id>`, shown in the action's
   settings). **Expect a lower match rate than a typical Enhanced
   Conversions setup**: this site captures no `gclid` at click time (by
   the 2026-09-13 cookieless-measurement decision), so Google is matching
   on the hashed email alone against its signed-in-user graph, not against
   a specific ad click -- a known, accepted trade-off, not a bug to chase.
   Then: set `google_ads_conversion_action` to that resource name (in
   whichever tfvars or secret store already holds `stripe_secret_key` and
   the rest of `infra/program-bundle`'s configuration), rebuild the Lambda
   package (`scripts/build-lambda-package.sh infra/program-bundle` --
   needed regardless, since `conversion_tracking.py` is a new file the
   package must include), and re-apply `infra/program-bundle` the same way
   the rest of it was applied.
9. **Launch**, and expect noise for the first several weeks per §4's
   volume caveat -- judge by 4-8 weeks of pooled clicks, not week to week.
10. **Later, separately** (not blocking launch): build the small scheduled
    job that reads the CloudWatch-logged conversion events and calls the
    Google Ads API's conversion upload via the `google-ads` client library,
    once step 8 has produced real logged events to build it against.
