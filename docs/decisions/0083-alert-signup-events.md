# ADR 0083: Alert signup events, and no counting of automated browsers

**Status:** Accepted (2026-11-20)

## Context

A traffic review on 2026-11-20 found two gaps in what GA4 can say about this
site.

- The only key events in the GA4 property are `purchase` and
  `begin_checkout`. Nothing a reader can do short of paying is counted, so "0
  key events" can only ever mean "no sale". A confirmed feed-health alert
  signup is the step that matters most for the readers the site has: it is
  the lead list for the bundle and the history tables.
- About 96% of GA4 sessions in the 28 days to 2026-11-20 came from one
  headless-Chrome fleet (Singapore and China, fixed window sizes, 0 seconds).
  Our own automation was already kept out (localhost, `?measure=off`, curl),
  but any browser that is driven by automation software and says so was
  still counted.

The confirmation itself happens on the alerts API (`infra/alerts/handler.py`),
not on the static site: the emailed link opens a page served by the Lambda,
and pressing "Confirm my alerts" POSTs back to it. That page carries the
reader's address and the token in its own address.

## Decision

**A first confirmation ends on the site.** When the POST to `/confirm` marks
a row verified, the API answers `303 See Other` to
`<site origin>/subscribe.html#confirmed` instead of its own "You are
subscribed" page. The site origin is the form's allowed origin
(`ALLOW_ORIGIN`), checked to be a bare `https://` origin. The address carries
a fixed marker and nothing from the link. The redirect keeps the API page's
`Cache-Control: no-store` and `Referrer-Policy: no-referrer`, so the link is
neither cached nor sent to the site as a referrer, and its body is the old
page for a client that does not follow redirects. The same link pressed again
gets the API's plain page, so it is not counted twice.

The alerts page shows a note with the same words the API page used ("You are
subscribed. Your address is confirmed. ..."). CSS `:target` shows it, so it
appears without scripting. `web/src/subscribe.js` keeps it shown, takes the
marker out of the address so a reload neither shows it again nor counts it
again, and moves focus to it.

Why the site and not the API page:

- The opt-out is kept in the site's local storage, which the API's origin
  cannot read. A GA4 tag on the API page would count readers who opted out.
- Every other rule GA4 follows here (consent defaults, GPC, Do Not Track,
  path-only addresses, the localhost and automation checks) lives in one
  place, `web/src/measure.js`. A second copy on the API would drift.
- The API page's address holds the email and the token. Keeping Google off
  that page means neither can leak through a default page_location.
- A server-side Measurement Protocol hit would need an API secret created in
  the GA4 admin, would not know a reader's opt-out, and would not join the
  reader's visit.

**Two steps, forwarded by name only.** The alerts page dispatches a
`scorecard:lead` event on the document, as the bundle pages do with
`scorecard:commerce` (ADR 0057). The GA4 block forwards it as a GA4 event
whose name is one of two, with `page_location` and `page_referrer` built the
same path-only way as the page view, and nothing else from the event:

| Step | When | GA4 event |
| --- | --- | --- |
| The form was accepted | the API answered `status: "pending"` (a new or still-pending address; an address already subscribed is not counted) | `alert_signup_requested` |
| The reader confirmed from the email | the page opened as `/subscribe.html#confirmed` | `alert_signup_confirmed` |

`alert_signup_confirmed` is the one to mark as a key event in the GA4 admin
(Admin, Data display, Events, then the star next to the event once it has
been seen, or Key events, New key event, with that exact name). The requested
step is there to show how many requests never get confirmed.

PostHog is unchanged; it sees the alerts page view by path, as before.

**Automated browsers are not counted.** Both blocks of `measure.js` return
before anything loads when `navigator.webdriver` is `true`. Playwright,
Puppeteer, Selenium and headless Chrome set it by default. A stealth bot
that hides it is still counted, so reports should keep leading with engaged
sessions.

## Consequences

- The confirmation needs `infra/alerts` re-applied (`docs/deploy.md`, section
  2) to take effect. Until then the site side is inert: no page links to
  `#confirmed`.
- The disclosure at `/about/#privacy-alert-steps` names both steps and what
  they never carry. `pipeline/tests/test_measure_ga4.py` runs both events,
  one loaded with an address and a token, through the Node harness;
  `pipeline/tests/test_alerts_signup_hardening.py` holds the redirect and the
  note.
- A reader who opens the email on another device is counted on that device,
  not joined to the visit that filled in the form.
