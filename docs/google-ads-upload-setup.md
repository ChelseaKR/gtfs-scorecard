# Google Ads conversion upload: owner setup

Extends [`docs/paid-search-readiness.md`](paid-search-readiness.md) §3
(the conversion-tracking seam) and its owner step 10 (the upload job that
step deliberately deferred). That job now exists:
`infra/program-bundle/ads_conversion_upload_handler.py`, a Lambda
EventBridge invokes daily. This page is the ordered list of things an owner
does outside this repository to turn it on, plus where each resulting
value goes.

**Status:** written and tested, not applied and not running. The
conversion action created for this
(`customers/2688527650/conversionActions/7769927171`, "Enhanced
conversions for leads", Purchases, primary, data-driven attribution,
90-day click-through window) is wired into `var.google_ads_conversion_action`
in `infra/program-bundle/main.tf`. The upload Lambda's own schedule stays
`DISABLED` until `var.google_ads_upload_ready` is set `true`, and Terraform
refuses that (a plan-time precondition, `terraform_data.google_ads_upload_guard`)
until the four required credential variables below are non-blank.

## What runs where

- `conversion_tracking.py` (unchanged in shape, extended in sink): builds
  the event and, when a conversion action is configured, writes it to
  CloudWatch (as before) and to a new small DynamoDB table,
  `gtfs-scorecard-program-ad-conversions`, keyed by the Stripe checkout
  session id with `status: "pending"`.
- `ads_conversion_upload_handler.py` (new): EventBridge invokes it daily.
  It reads every `status: "pending"` row, uploads each as a Google Ads
  click conversion via the `google-ads` Python client library's
  `ConversionUploadService`, and writes each row's own outcome back
  (`"uploaded"` or `"failed"` with Google Ads' error message attached).
  See that module's docstring for the full design, including why a table
  and not the CloudWatch Logs Insights query §3 originally sketched.

Read both modules' docstrings before changing either; this page is the
owner-facing half, not a second copy of the design.

## Owner steps, in order

### 1. Confirm the Google Cloud project and enable the API

Use (or create) one Google Cloud project for this. In that project's
**APIs & Services** console, enable the **Google Ads API**.

### 2. Brand verification, then apply for Basic access

**This whole section changed on 2026-09-09** and the facts below were
checked against Google's current documentation on 2026-09-15, not assumed
from older material — Google sunset the developer token as the
API's access-control mechanism that day: access levels (Test / Basic /
Standard) now attach to the **Google Cloud project** behind your OAuth
credentials, not to a developer-token string issued from a manager
account's old API Center. ([Developer token —
Google for Developers](https://developers.google.com/google-ads/api/docs/api-policy/developer-token),
[Access levels and permissible use —
Google for Developers](https://developers.google.com/google-ads/api/docs/api-policy/access-levels))

This product's use case — a handful of purchase conversions a week,
uploaded against your own Google Ads account, no agency or multi-client
use — needs **Basic access**, not Standard:

| Level | Allows | Daily operation ceiling |
| --- | --- | --- |
| Test | Test accounts only | 15,000 |
| **Basic** (this use case) | Test **and production** accounts | 15,000 |
| Standard | Test and production accounts | Unlimited |

**The genuinely good news, worth stating plainly because it contradicts
older advice you may have seen about a multi-week developer-token wait:**
per Google's current docs, Basic access applications are now automated
and reviewed within minutes of brand verification and submission — not
the weeks-long manual review that used to gate it. The real prerequisite
work is brand verification itself, which is something you complete, not
something you wait on Google for:

- In your Cloud project's OAuth consent screen configuration, set **User
  type** to **External** and **Publishing status** to **In production**.
- Your app's homepage must be hosted on a domain you own and verify
  (Search Console verification of `gtfsscorecard.org` already exists for
  this repo per `docs/decisions/0055-cookieless-site-measurement.md`'s
  neighbors — reuse that verified domain rather than standing up a new
  one), and it must accurately describe what the integration does.
- Add a privacy policy link on that homepage, and make sure it is the
  **exact same URL** you enter in the OAuth consent screen's privacy
  policy field — a mismatch is a documented rejection reason.

Once brand verification is complete, apply for Basic access from the
Google Ads API Overview page inside the Cloud project (Google Ads API
Center in the console). Expect an answer within minutes, per Google's
current docs — if it instead sits pending, that itself is a signal
something above was incomplete, not that this is normal.

### 3. Create the OAuth 2.0 client

In the same Cloud project: **APIs & Services → Credentials → Create
Credentials → OAuth client ID → Application type: Desktop app**. Name it
something identifiable (e.g. "gtfs-scorecard ads upload"). Download the
client secret JSON. A Desktop app client needs no redirect URI configured
in the console — the local script below handles that itself.

- `google_ads_client_id` = the client's id
- `google_ads_client_secret` = the client's secret

### 4. Generate a refresh token (one-time, interactive, local)

```sh
pip install google-ads   # pulls in google-auth-oauthlib
python3 scripts/generate-google-ads-refresh-token.py \
    --client-secrets /path/to/client_secret_....json
```

This opens a browser tab, asks you to sign in with the Google account that
administers the Ads account, and prints a refresh token to your terminal.
Run this on your own machine, never in CI. The scope requested is exactly
`https://www.googleapis.com/auth/adwords`.

- `google_ads_refresh_token` = the printed token

### 5. The developer token (optional, but still worth generating)

Because of the 2026-09-09 change above, a developer token no longer
determines your access level, and Google's docs now describe developer
tokens sent in API calls as **optional and currently ignored** — Google
has said it will stop accepting them in a future major API version it has
not yet named. `google_ads_developer_token` reflects this: it is read and
passed to the `google-ads` client library (which still accepts the field),
but it is *not* one of the four variables
`terraform_data.google_ads_upload_guard` requires before
`google_ads_upload_ready` can be `true` — leaving it blank does not block
turning this on.

Generating one anyway costs a couple of minutes and keeps this forward-compatible
with whatever Google's "future major API version" turns out to require. If
your Cloud project's Google Ads API Center still offers to generate one,
do so and set:

- `google_ads_developer_token` = the generated token

If it does not (the console surface for this may have moved or been
retired as part of the same migration — check current UI rather than
assuming it matches this description, since this was the single fastest-
moving fact in this whole page), leave the variable blank and move on.

### 6. The login customer id

Already set: `google_ads_login_customer_id` defaults to `"2688527650"` in
`main.tf` — the same account id embedded in
`google_ads_conversion_action`. Ten digits, no dashes; only change it if
uploads should run against a different account than the one that owns the
conversion action.

### 7. Put the values in Terraform

Same place `stripe_secret_key`, `stripe_webhook_secret`, and `github_token`
already live for this module (whichever tfvars file or secret store this
account's operator uses for `infra/program-bundle` — **not** this
repository, and not a value typed into a shell that gets logged):

```hcl
google_ads_client_id         = "..."
google_ads_client_secret     = "..."
google_ads_refresh_token     = "..."
google_ads_developer_token   = "..."   # optional, see step 5
# google_ads_login_customer_id and google_ads_conversion_action already
# have the right defaults in main.tf; only override if either changes.
```

Then rebuild the Lambda package (it now includes the `google-ads` client
library — `scripts/build-lambda-package.sh` installs it only for this
module) and apply:

```sh
scripts/build-lambda-package.sh infra/program-bundle
cd infra/program-bundle && terraform init && terraform apply
```

`google_ads_upload_ready` is still `false` at this point — applying here
creates the `ad-conversions` table and the Lambda, but the daily schedule
stays `DISABLED`. That is deliberate; do not set it `true` in the same
apply as the credentials, so you can check the dry run first.

### 8. Dry run, then a first real run, then flip the schedule on

```sh
aws lambda invoke --function-name gtfs-scorecard-program-bundle-ads-upload \
    --payload '{"dry_run": true}' /dev/stdout
```

With no purchases yet, this logs `scanned: 0` and returns cleanly — nothing
to check yet, but it proves the Lambda deploys and imports the `google-ads`
package correctly before waiting on a real sale.

Once at least one real purchase has gone through (`conversion_tracking`
will have written a `status: "pending"` row keyed by that checkout's
session id), invoke without `dry_run` and confirm that row moves to
`status: "uploaded"` in the `gtfs-scorecard-program-ad-conversions` table,
not `"failed"`. Only then set `google_ads_upload_ready = true` and re-apply
to turn the daily schedule on.

### 9. What "working" looks like afterward, and the accuracy caveat already on record

Per `docs/paid-search-readiness.md` §7 step 8: expect a lower match rate
than a typical Enhanced Conversions setup, because this site captures no
`gclid` (its measurement drops the query string, and GA4 runs with ad storage
denied, per ADR 0056) — Google matches on the hashed email alone
against its signed-in-user graph. That trade-off was accepted when the
conversion action was designed and is not a bug to chase here.

## If something goes wrong

- **A row stays `"failed"`**: read its `detail` field in the
  `ad-conversions` table (or the Lambda's CloudWatch log, which prints the
  same counts). The upload job never retries a failed row automatically —
  see `ads_conversion_upload_handler.py`'s docstring for why — so a
  transient error needs a person to look and decide.
- **The Lambda invocation itself raises `RuntimeError` naming rows that
  "need attention"**: that is intentional (the same "a green run that
  found a problem and told nobody is the bug" posture as the daily
  reconciler). CloudWatch alarms on the failed invocation; check the named
  rows.
- **`ConfigurationError` naming a blank env var**: one of the four required
  `google_ads_*` variables did not make it into the deployed Lambda
  environment. Re-check step 7 and re-apply.
