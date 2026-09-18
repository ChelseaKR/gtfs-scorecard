# ADR 0057: Bundle conversion events in GA4

**Status:** Accepted (2026-09-18)

## Context

ADR 0056 loaded Google Analytics 4 as a page-view counter. The Google Ads
campaign for the program report bundle can then only be judged on taps: GA4
saw a checkout only as a click on a link to another site, and saw nothing at
all of a completed purchase. On 2026-09-18 the owner asked for ads and search
to be judged on purchases. The GA4 property already lists `purchase` as a key
event, so what was missing was the events themselves.

## Decision

The bundle pages announce three steps toward a purchase as a
`scorecard:commerce` event on the document, and the GA4 block of
`web/src/measure.js` forwards them as GA4's recommended ecommerce events:

| Step | Where | GA4 event | Parameters |
| --- | --- | --- | --- |
| The plans a reader can buy were shown | `/bundle/`, `web/src/bundle.js`, after `plan.json` is read with payments on | `view_item` | `currency`, `value` (the entry bundle's price), `items` (every plan on sale) |
| A checkout link was followed | `/bundle/`, both the button at the top and each plan card | `begin_checkout` | `currency`, `value`, `items` (that plan) |
| Stripe sent a buyer back after paying | `/bundle/setup/`, `web/src/bundle-setup.js`, on load with a well-formed `session_id` | `purchase` | `transaction_id`, and `currency`, `value`, `items` when the plan is known |

Every item is `{item_id, price, quantity: 1}`, where `item_id` is the plan id
from `plan.json` (`bundle_25`, `bundle_100`, `refresh_mo`, `refresh_yr`).

**Only the GA4 block talks to Google.** The page scripts dispatch a DOM event
and never call `gtag`. So the event is sent only when GA4 loaded, which means
no opt-out, no Global Privacy Control and no Do Not Track. The block builds
every parameter again from fields it checks one at a time: the event name is
one of the three, a plan id matches `^[a-z0-9_]{1,40}$`, a price is a plain
number, the currency is three capital letters, and a transaction id is 32
lowercase hex characters. Anything else in the event, such as an email a
future edit put there by mistake, is dropped. `page_location` and
`page_referrer` are the same path-only values the page view carries.

**The order reference never reaches Google.** Stripe returns the buyer to
`/bundle/setup/?session_id=cs_...`. The setup page hashes that reference with
SHA-256 and sends the first 32 hex characters as `transaction_id`. The owner
can match a GA4 purchase to a Stripe session by hashing the session id. GA4
counts purchases with one `transaction_id` once, so a reload or a later visit
to the same address does not add a sale.

**What was bought.** The setup page's address names no plan. When a checkout
link is followed, the GA4 block keeps `{item, currency}` in the tab's session
storage under `scorecard-checkout`. On the purchase it reads that, sends the
plan and price, and replaces it with `{reported: <transaction id>}`, so this
tab never reports the same order twice. Opting out removes the key. A buyer
who returns in a different tab is still counted, with no value. Only the GA4
block writes the key, and only while GA4 is on.

**PostHog is unchanged.** It still receives `bundle_checkout_click` with the
plan id (ADR 0055), from the same links.

**The top of `/bundle/`.** The page now opens with the entry bundle's price and
one checkout button above the fold on a phone. The sample report link and the
link to every plan come next. The price and link come from `plan.json`
through `bundle.js`, like every other price on the page. Without scripting,
or when the plan cannot be read, the button stays a link to the plan list.

## Consequences

- The disclosure at `/about/#privacy-purchase-steps` names the three steps,
  what each carries, the hashing, and the session-storage key.
  `test_measure_ga4.py` holds the block to the checks above and runs the
  events through the Node harness, including an event loaded with an email
  and a raw order reference that must not reach `dataLayer`.
- For Google Ads, the GA4 `purchase` key event can be imported as the
  campaign's conversion. The separate server-side upload in
  `docs/google-ads-upload-setup.md` would count the same purchases a second
  time. Only one of the two should be a primary conversion action.
- A subscription's `value` is its first period's price. Renewals are not
  reported.
