# Program report bundle: what it is, what it costs, how it turns on

The program tier's first product, built 2026-09-01 and **launched 2026-09-12**. The
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
| Purchase plumbing: post-checkout form (confirms the session is paid, dispatches), download route (presigns per click), Stripe webhook, weekly refresh, daily reconciler | `infra/program-bundle/` | **Applied and live** 2026-09-12; `payments_enabled = "1"`, `stripe_price_ids_are_live = true`. The daily reconciler is deployed but its schedule is `DISABLED` until its reporting channel lands. |
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

The "up to" is enforced, not advisory. The setup route reads the Checkout
Session's line item, refuses any price that is not one of these four, and
holds the agency list to that price's cap: a `bundle_25` buyer who lists 26
ids is told so and can resend the same checkout with 25. Without that check
a paid checkout for anything else on the same Stripe account would pass the
form, which is also why the account this runs on matters.

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

Steps 1 to 6 also run as one command: `scripts/bundle-testmode.sh`. It walks
the test-mode rehearsal as a sequence of phases, each idempotent and each
resumable with `--from`, checks every assertion below rather than trusting an
exit code, and stops at the `web/src/config.js` commit because that is a change
to a public site. It reads its three credentials from the environment, prints
at most four characters of any of them, and refuses a live key. `--dry-run`
runs every read-only check and creates nothing. The steps below stay the
description of what has to be true; the script is how it is done and checked.

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
   deployed, and the module refuses anything that is not an `rk_` key.
   The setup route reads the session *and* its line items
   (`GET /v1/checkout/sessions/{id}/line_items`), because what was bought
   decides whether a build happens at all; line items are a sub-resource of
   the session, so Checkout Sessions: Read is the permission for both. Check
   it rather than trust it: the endpoint answers 403 with a body naming the
   missing permission, and a key that cannot read line items refuses every
   purchase.
3. **Apply the module.** From the repository root:
   `scripts/build-lambda-package.sh infra/program-bundle`, which vendors the
   pipeline as Linux wheels and refuses a package holding a binary built for
   anything else. A plain `pip install ../../pipeline -t build` on a Mac
   produces a package that unpacks, deploys, and then dies on the first
   request with `ModuleNotFoundError: No module named 'rpds.rpds'`. Then
   `terraform init && terraform apply` with `github_token` (a fine-grained
   PAT with **actions: write** on this repo and nothing else),
   `artifacts_bucket`, `stripe_secret_key`, and the price ids. Leave
   `payments_enabled = "0"` for this apply. Note the two outputs. The
   `terraform init` is what wires up the S3 backend in `backend.tf`: this
   module's state holds the PAT, the restricted key, and the webhook secret
   as Lambda environment variables, so it is never allowed to land in a local
   `terraform.tfstate` on one laptop.
   Apply the `expire-program-bundles` lifecycle rule in `infra/artifacts`
   **as a targeted apply of that one resource**:
   `terraform -chdir=infra/artifacts apply -target=aws_s3_bucket_lifecycle_configuration.artifacts`.
   Do not apply the whole module from this runbook. On 2026-09-10 an untargeted
   plan also carried a `www` redirect bucket, a Route 53 record, and a CDN
   function update, merged work that had never been applied, and a payment
   walkthrough is the wrong place to ship it. The module's `terraform.tfvars`
   must also set `create_oidc_provider = false`, because this AWS account
   already holds the GitHub OIDC provider; left at its default of `true`, the
   plan adds a second one and rewrites both deploy roles' trust policies.
   `scripts/bundle-testmode.sh` does both, and refuses a plan that reaches past
   the lifecycle resource.
4. **Webhook.** In Stripe (test mode) add one webhook endpoint at the
   `webhook_url` output with the events `checkout.session.completed`,
   `customer.subscription.created`, `customer.subscription.updated`,
   `customer.subscription.deleted`. Its signing secret is
   `stripe_webhook_secret`; apply again with it set.
5. **Actions variables.** Set `BUNDLE_API_BASE` to the `api_base` output.
   `ARTIFACTS_BUCKET` and `SES_FROM` already exist as repository *variables*
   for the daily run, and `AWS_ROLE_ARN` as a repository *secret*
   (`report-bundle.yml` reads it as `secrets.AWS_ROLE_ARN`); the workflow
   reuses all three. Confirm the OIDC role can `PutObject` under
   `program-bundles/` in the artifacts bucket.
6. **End-to-end, test mode.** Apply once more with `payments_enabled = "1"`
   (the preconditions now pass), then set `window.SCORECARD_BUNDLE_URL` in
   `web/src/config.js` to `api_base`. That value only exists once the module
   is applied, so it cannot ride the launch branch: it is its own small commit
   to `main`, merged and deployed by `pages.yml` before the purchase below.
   The form stays invisible while it lands, because `/bundle/setup/` is
   unlinked and `noindex`. Then buy a `bundle_25` with a
   Stripe test card through the Payment Link. Walk the loop: Payment Link →
   `/bundle/setup/` → form → workflow run → email → download link → archive
   with the right cover and a manifest that names every id. Then cancel a
   test subscription from the Stripe customer portal and confirm the row
   reads `canceled`. Run `report-bundle.yml` by hand once with a deliberately
   bad id to see it listed in the manifest, not dropped. Dispatch it with
   `--ref main`: the OIDC role trusts `refs/heads/main` and nothing
   else (`infra/artifacts/github_oidc.tf`), so a run dispatched on any other
   ref cannot assume the role and fails at the upload.
   Buy a `bundle_25` and try 26 agency ids as well: the plan's cap is
   enforced by the setup route from the price that was actually paid for, so
   that purchase is refused in the form with the reason, not quietly trimmed
   and not quietly upgraded.
7. **The live decision.** *Recorded 2026-09-12.* Live mode was opened on this
   date on Stripe account `acct_1UEJ7fAJdYOJsO05` (verified activated:
   `charges_enabled`, `payouts_enabled`, `details_submitted`, no outstanding
   requirements). Four live prices and four Payment Links were created, a
   restricted key scoped to Checkout Sessions: Read was deployed, a live
   webhook endpoint was registered, and `infra/program-bundle` was applied
   with `payments_enabled = "1"` and `stripe_price_ids_are_live = true`.
   `/bundle/` was published the same day (PR #393, merge `865a6d6e173`).

   **What the date turned on, and what it did not.** The 2026-10-01 date this
   branch was named for existed to protect a TechCA Emerging Technologies
   Forum submission that used gtfsscorecard.org as its supporting URL. That
   submission is not being filed (a work conflict, decided 2026-09-12), so the
   "no paywall" non-goal it protected was withdrawn rather than overridden.
   Agency-facing scoring staying free is a separate commitment and is
   untouched.

   **The three reviews this decision is supposed to rest on are NOT yet
   recorded**, and this paragraph does not pretend otherwise:

   | Review | State |
   |---|---|
   | Tax treatment of the revenue | outstanding |
   | Refund policy, written down | outstanding |
   | The two-business-day delivery commitment, reviewed against what the pipeline actually guarantees | outstanding |

   The third is the one with teeth. `/bundle/` tells a buyer delivery is
   "always within two business days. If it is later than that, the purchase is
   refunded." As of this date nothing computes that deadline, nothing detects a
   breach, and refunds are entirely manual: the deployed restricted key cannot
   issue one by design. The daily reconciler (deployed, `DISABLED`) is what
   would surface an undelivered order; until its reporting channel lands, a
   failed delivery is found by a buyer complaining. Treat the commitment as a
   promise currently kept by hand.

   For reference, the original instruction for this step was: record the date
   and the reviews it rests on (tax, refund policy, the two-business-day
   commitment). Then, in
   live mode: `scripts/stripe-setup.sh` again with a *live* key, a live
   restricted key, a live webhook, and an apply with `stripe_price_ids_are_live
   = true`. The precondition refuses a live key paired with unconfirmed
   prices.
8. **Turn the page on.** Edit `web/bundle/plan.json`: `paymentsAvailable:
   true` *and* the `products` block from step 7, in the same branch and
   before the merge. `paymentsAvailable: true` with the null placeholder
   still in `products` publishes a page that announces checkout is open and
   then prices every plan "Not yet available" (`web/src/bundle.js`).
   Link `/bundle/` from `/support/` and from the board one-pager's footer.
   That `/support/` link needs a new card: the "For programs and
   consultancies" one this step used to name was removed in #332, along with
   the dead consulting link it held.
   Remove `/bundle/` from `site-seo.json`'s `noindex_path_patterns`, drop the
   `robots` meta from that page, and add it to the hand-maintained `urls`
   list at the top of `render_site.py`'s site render, which is what the
   sitemap is built from; the SEO gate compares the three and fails if they
   disagree. `/bundle/setup/` stays `noindex` and out of the sitemap: it is a
   post-checkout form that says nothing to a reader who arrives without a
   session, and an indexed one would collect search traffic it can only turn
   away. Not before early October: the TechCA
   review window (`gtfs-scorecard-plans/10-next-60-days-2026-08.md`) freezes
   the public surface until then.
9. **Ninety days later**, the gate table above.

## When an order does not get built

Payment and fulfilment are separate systems, so there is a gap between them
where a paid order can go quiet. Three ways it happens, and what answers each.

**The dispatch fails.** GitHub is down, the token has lost `actions: write`,
the workflow file was renamed. The claim records whether a build was ever
started separately from whether the payment is spoken for, so an order in this
state is still open: the buyer is told to submit the form again, and the retry
finishes the same bundle id rather than opening a second order. One payment
can still only ever produce one bundle.

**The build fails.** `report-bundle.yml` writes an annotation and a run
summary naming the bundle id, and mails the same facts to `SES_FROM`.
Re-dispatching with the same inputs is the repair: the archive and the
download link are both keyed on the bundle id, so the re-run fills the object
the buyer's existing link already points at. `watchdog.yml` reads that
workflow's most recent conclusion every six hours as the backstop, and counts
`cancelled` as a failure because that is what a job killed by its own
`timeout-minutes` records.

**Nobody comes back.** The buyer pays and closes the tab before the setup
form, or hits a failed dispatch and never retries. The daily reconciler
(`infra/program-bundle/reconcile_handler.py`) walks the bundles table and
reports any capability row older than six hours with no
`program-bundles/<id>/bundle.zip`, any claim that never dispatched, and any
`checkout#` row with no matching `session#` row. It refuses rather than
reports clean when it cannot read a row's timestamp or the bucket will not
answer.

It reports by keeping one GitHub issue up to date, not by email. The
operator's own domain has no MX record, so an emailed alert would have been
delivered nowhere, and a notification that cannot arrive is the same defect
as no notification. This repository is public, so that issue carries the
counts and a CloudWatch pointer and nothing else: a bundle id is a download
capability, and the delivery address, the program name and the agency list
all describe a paying customer. The detail stays in CloudWatch, which is
private to the account. The schedule stays disabled until
`reconciler_reporting_ready` is set, because a reconciler with nowhere to
report finds things and tells nobody. The dispatch token already carries the
`Issues: Read and write` permission the design needs; what that switch records
is that somebody checked, and that the label the report is filed under
exists.

## Closing it again

Set `payments_enabled = "0"` and apply: the `/setup` route disappears, the
weekly refresh and daily reconcile rules are disabled, and the download route
keeps serving links already issued until they expire. Set `paymentsAvailable: false` in
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
