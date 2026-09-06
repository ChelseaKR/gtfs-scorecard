# Program report bundle: what it is, what it costs, how it turns on

The program tier's first product, built 2026-09-01 and **not launched**. The
decision behind it is [ADR 0049](decisions/0049-a-checkout-is-the-named-user.md);
the money rules it lives under are the sustainability plan's
(`gtfs-scorecard-plans/07-monetization-sustainability.md`, summarized in the
next section). This page is the runbook: the pieces, the prices, the day-90
stop rule, and the exact sequence that opens the tier.

## What it is

A state program, a technical-assistance center, a feed vendor, or a
consultancy that prepares packets for many agencies buys one archive: every
agency's board report, with the program's name, logo, and accent on each
cover, plus a manifest that names every id that was asked for and what
happened to it. One-time, or refreshed monthly.

Each file is the same self-contained report the site already ships for one
agency (`board-report.md`, `/agency/<id>/board/`). The bundle computes no new
metric and no new grade. It is packaging, branding, and delivery.

| Piece | Where | Status |
| --- | --- | --- |
| Core: validate a request, classify ids against the registry, render each current one through `report.generate_report`, zip with a manifest | `pipeline/src/scorecard_pipeline/bundle.py`; `scorecard bundle`, `scorecard bundle-email` | Built, tested |
| Fulfilment: on-demand render, upload behind a capability key, email the link | `.github/workflows/report-bundle.yml` | Built; delivery steps gated on Actions variables |
| Purchase plumbing: post-checkout form (confirms the session is paid, dispatches), download route (presigns per click), Stripe webhook, weekly refresh | `infra/program-bundle/` | Written, **not applied**; `payments_enabled = "0"` |
| Storage: `program-bundles/<id>/bundle.zip` expires after 30 days | `infra/artifacts/main.tf` lifecycle rule | Written; needs a re-apply of `infra/artifacts` |
| Pages: plans read from `web/bundle/plan.json`; setup form posts to the API | `web/bundle/`, `web/src/bundle.js`, `web/src/bundle-setup.js` | Built; unlinked, `noindex`, out of the sitemap; `paymentsAvailable: false` |
| Stripe objects: two products, four prices, four Payment Links | `scripts/stripe-setup.sh` | Script only; nothing created |

## The rules it lives under

From `gtfs-scorecard-plans/07`, restated because they bound what can ever be
sold here:

- **Agency-facing stays free.** The single report, the board one-pager, the
  CLI, the data, the API, the badges, the alerts, and one-off scoring are
  unchanged. Nothing is subtracted from the free tier to create the bundle.
- **The paid thing is additive and for someone else.** The buyer manages
  many agencies. It is never the way an agency sees its own grade.
- **No shaming surface.** One report per agency, no league table, and it
  will not gain one for a buyer.
- **Independence is the product.** Purchase buys no influence over grades,
  methodology, or listing. The page and every email say so.
- **Instant scoring stays free.** ADR 0029 is untouched.

## Prices: hypotheses, and the checkout is the experiment

These are knobs, not research. The verified anchor is that a *single*
agency's on-time-performance module from a commercial vendor is quoted at
about three thousand dollars a year, and that the work product an agency
hands a board or a grant reviewer is the layer buyers pay for
(`income-plan-2026-07/15-EXPANSION-STUDY4` F4, `09-NEW-PROJECT-IDEATION` N1).
A program with twenty agencies gets twenty board packets for a twentieth of
that. Set them in `scripts/stripe-setup.sh` and the Stripe dashboard; the
site never carries a price of its own.

| Knob | Price | What it covers |
| --- | --- | --- |
| `bundle_25` | $149 once | One archive, up to 25 agencies |
| `bundle_100` | $349 once | One archive, up to 100 agencies |
| `refresh_mo` | $49 a month | A fresh archive every month, up to 100 agencies, cancel any time |
| `refresh_yr` | $490 a year | The same, billed yearly |

Commitments on the page, which the operator has to be able to keep:

- The download link arrives normally within the hour and **always within two
  business days**; if not, the purchase is refunded. (The build is a
  workflow run; "two business days" is the margin for a broken run and a
  make-good by hand.)
- The link is valid for **30 days**. A monthly plan sends a new archive and a
  new link each month.
- The manifest names every requested id and its outcome: included, not a
  tracked id, a retired record, or no published scorecard yet.

## The day-90 gate

Read this ninety days after the page is linked. It is the stop rule ADR 0049
promises, so a tier that sells nothing is revisited rather than left up as
if it were working.

| Signal at day 90 | Do |
| --- | --- |
| 0 purchases, `/bundle/` under about 50 unique visitors | Leave the page up (it costs nothing), keep Sponsors, **do not build the workspace**. Revisit next NTD reporting season. |
| 0 purchases, `/bundle/` over about 50 unique visitors | A price or copy problem, not a demand problem. Halve the one-time price once; change nothing else for another 90 days. |
| 1 or more purchases | Build the program workspace (hosted saved cohorts, team sharing, SLA'd support; 07's "supporter workspace" row) for that buyer. Ask permission to name their program on `/support/`. |

Unique visitors come from the Pages traffic view, the only analytics this
site has; the page is `noindex` and unlinked until launch, so the count
starts at launch.

## Runbook: from "written" to "on"

Nothing before step 7 can charge anyone. Steps 1 to 6 are all in test mode.

1. **Stripe, test mode.** With a *test* secret key exported:
   `scripts/stripe-setup.sh`. It creates the two products, four prices, and
   four Payment Links (success URL
   `https://gtfsscorecard.org/bundle/setup/?session_id={CHECKOUT_SESSION_ID}`)
   and prints the `stripe_price_ids` block for `terraform.tfvars` and the
   `products` block for `plan.json`. Keep the output; the script is not
   idempotent.
2. **A restricted key for the Lambda.** In the Stripe dashboard create a
   *restricted* key with read access to Checkout Sessions only. That is
   `stripe_secret_key`. The full secret key is never given to anything
   deployed.
3. **Apply the module.** From `infra/program-bundle/`:
   `pip install ../../pipeline -t build && cp *.py build/`, then
   `terraform init && terraform apply` with `github_token` (a fine-grained
   PAT with **actions: write** on this repo and nothing else),
   `artifacts_bucket`, `stripe_secret_key`, and the price ids. Leave
   `payments_enabled = "0"` for this apply. Note the two outputs.
   Re-apply `infra/artifacts` so the `expire-program-bundles` lifecycle rule
   exists.
4. **Webhook.** In Stripe (test mode) add one webhook endpoint at the
   `webhook_url` output with the events `checkout.session.completed`,
   `customer.subscription.created`, `customer.subscription.updated`,
   `customer.subscription.deleted`. Its signing secret is
   `stripe_webhook_secret`; apply again with it set.
5. **Actions variables.** Set `BUNDLE_API_BASE` to the `api_base` output.
   `ARTIFACTS_BUCKET`, `AWS_ROLE_ARN`, and `SES_FROM` already exist for the
   daily run; the workflow reuses them. Confirm the OIDC role can `PutObject`
   under `program-bundles/` in the artifacts bucket.
6. **End-to-end, test mode.** Apply once more with `payments_enabled = "1"`
   (the preconditions now pass), set `window.SCORECARD_BUNDLE_URL` in
   `web/src/config.js` to `api_base`, deploy, and buy a `bundle_25` with a
   Stripe test card through the Payment Link. Walk the loop: Payment Link →
   `/bundle/setup/` → form → workflow run → email → download link → archive
   with the right cover and a manifest that names every id. Then cancel a
   test subscription from the Stripe customer portal and confirm the row
   reads `canceled`. Run `report-bundle.yml` by hand once with a deliberately
   bad id to see it listed in the manifest, not dropped.
7. **The live decision.** Record it here with the date and the reviews it
   rests on (tax, refund policy, the two-business-day commitment). Then, in
   live mode: `scripts/stripe-setup.sh` again with a *live* key, a live
   restricted key, a live webhook, and an apply with `stripe_price_ids_are_live
   = true`. The precondition refuses a live key paired with unconfirmed
   prices.
8. **Turn the page on.** Edit `web/bundle/plan.json`: `paymentsAvailable:
   true` and the `products` block from step 7. Link `/bundle/` from
   `/support/` ("For programs and consultancies", the card that used to hold
   the consulting link) and from the board one-pager's footer. Remove
   `/bundle/` and `/bundle/setup/` from `site-seo.json`'s
   `noindex_path_patterns` and drop the `robots` meta from both pages so the
   sitemap and the SEO gate agree. Not before early October: the TechCA
   review window (`gtfs-scorecard-plans/10-next-60-days-2026-08.md`) freezes
   the public surface until then.
9. **Ninety days later**, the gate table above.

## Closing it again

Set `payments_enabled = "0"` and apply: the `/setup` route disappears, the
weekly refresh rule is disabled, and the download route keeps serving links
already issued until they expire. Set `paymentsAvailable: false` in
`plan.json`: the page shows "Not yet available" and no checkout link. Both
halves are independent and fail closed, the same two-gate shape
family-greenhouse uses.

## What is deliberately not here

- No per-check charge on instant scoring, no agency pricing, no white-label
  state instance without a contract, no realtime archive (07).
- No account, no password, no customer portal of our own. The capability
  link is the credential and Stripe's receipt is the account.
- No waitlist. A checkout is the waitlist.
- No promise of coverage: an id the scorecard does not track is listed in the
  manifest with the reason, and the page says so before purchase.
