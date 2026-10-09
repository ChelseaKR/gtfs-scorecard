# The history tables

**On sale since October 2026.** This page is the contract for the scorecard
history tables, the paid data tier decided in [ADR 0063](decisions/0063-history-tables-paid-tier.md).
The export, the delivery, the pages, and the pointers to them are built, the
Stripe price and Payment Link exist, the Terraform is applied, the first
export has run, and `paymentsAvailable` is on in `web/data/history/plan.json`
(the runbook below records the order). Turning the tier off again is the
reverse of the runbook's last step: plan off, re-sync, and drop `Product`
from `site-seo.json`. The free site is unchanged apart from the pages that
describe this tier.

## Price

The same posture as the bundle (`docs/program-plan.md`): the amount is a
hypothesis and the checkout is the experiment. It lives in
`web/data/history/plan.json` and nowhere else; the page and its structured
data are generated from that file, and `test_paid_tier_visibility.py` fails
the build on the amount typed anywhere else.

| Knob | Price | What it covers |
| --- | --- | --- |
| `history_once` | $99 once | The newest monthly build of both tables, the dictionary, the provenance file, and the license, as one zip, licensed to one organization, with a 30-day download link |

Why this number: no priced product sells a national feed-quality history, so
there is no direct comparable. Transitland's $200 a month is the nearest
priced transit-data subscription and bundles much more; $99 sits under the
card-without-procurement line for a consultant or a researcher, above a token
amount so a sale is a signal, and below the bundle's entry plan so the two do
not compete for the same buyer. A monthly refresh plan waits for the first
sale. The day-90 rule applies on this tier's own clock: no sale after 90 days
with the page over about 50 unique visitors halves the one-time price once,
and nothing else changes.

## Where the tier is pointed to from

The home page (one sentence on the "Use the public data" card, beside the
`/data/` link it already carried), `/tools/` (an entry marked "Paid", as the
bundle's is), `/data/` (the open-data page, in its own section), `/support/`
(a second paid card beside the bundle's), `/bundle/` (one line for the reader
who needs tables rather than board reports; the history page carries one line
back to the bundle the same way), the shared footer only through `/support/`,
`web/llms.txt` and `README.md` (which describe two paid things and name no
price, per ADR 0054), and the sitemap. `/api/`, the directory a reader guesses
at when they want the data as files, is a redirect alias to the open-data
page's endpoint list rather than a 404. None of these surfaces types the
amount; it lives only in the plan file, and `test_history_plan_contract.py`
sweeps each of them for it. The shared nav and footer are unchanged, and
agency pages, call briefs, and board one-pagers name nothing about it, as ADR
0058 requires of every paid surface.

## What the tables are

Two Parquet tables built by `scorecard history-export` from the dated
artifacts under `data/artifacts`, joined on `agency_id` and `snapshot_date`:

- `checks.parquet`: one row per feed record per dated check, with the grade,
  the overall and category scores, the expiry fields, the methodology and
  feed-byte identity, the fetch provenance, and the registry's license record
  for the feed.
- `findings.parquet`: one row per finding per check, with the notice code,
  severity, instance count, points, its rank among the top fixes, and the
  reach numbers from the consequence block where the artifact has one.

Beside them: `DATA-DICTIONARY.md` (every column, its type, and what a null
means), `PROVENANCE.json` (what was read, the snapshot date range, the
artifact schema versions seen, the row counts, the SHA-256 of each table, and
how many feed records were left out by request), and `LICENSE.md` (the text
below). The five files pack into one zip with fixed timestamps.

Run it from `pipeline/` with the `query` extra installed:

    uv run scorecard history-export --out ../history --zip ../history.zip

`--out` must be a new or empty directory. `--artifacts` reads a different
artifact root, `--exclusions` a different ledger, and `--generated-on` dates
the provenance file; by default it carries the newest snapshot date in the
corpus, so the output is a function of the input alone.

## How the tables are delivered

Phase 2 of ADR 0063. No per-order build, no new always-on resource, and no
buyer data in any workflow run.

1. **One shared object a month.** `.github/workflows/history-export.yml` runs
   on day 4 UTC (after the free dataset release's own window), hydrates every
   dated artifact from the private bucket, runs `scorecard history-export`,
   checks the zip holds exactly the five files above, and writes
   `history/<YYYY-MM>/history.zip` (and the month's `PROVENANCE.json` beside
   it) to the private artifacts bucket. It can be dispatched by hand, with an
   optional `month` input for a make-good; a re-run overwrites the same key.
   The prefix is outside the CloudFront allow-list and listed in the bucket
   policy's explicit deny, and a lifecycle rule retires an object after 400
   days. The workflow assumes its own role (`infra/artifacts/github_oidc.tf`,
   `history_export`): list and read `data/artifacts/`, list and write
   `history/`, nothing else, and only from runs on `main`.
2. **The checkout.** The Stripe Payment Link for the `history_once` price
   sends the buyer to `/data/history/setup/?session_id={CHECKOUT_SESSION_ID}`.
   That page has no form: `web/src/history-setup.js` posts the session id to
   the program-bundle API's existing `POST /setup`.
3. **The setup branch.** `infra/program-bundle/setup_handler.py` recognizes
   the `history_once` plan from the session's one line item, the same way it
   recognizes the four bundle plans, and takes the history branch: refuse with
   the checkout unused while `HISTORY_ENABLED` is not `"1"`, while the store
   cannot be read, or while no monthly object exists yet; otherwise claim the
   session, write a capability row that names the newest
   `history/<YYYY-MM>/history.zip`, email the link from `SES_FROM`, and answer
   with the link. A reload of the setup page answers the same link again. A
   mail failure is reported on the page as exactly that; the link still works.
4. **The download.** The existing `GET /download/{id}` route presigns the one
   key the row names, for fifteen minutes per click, for 30 days. A row that
   names any key other than its own derived bundle key or a
   `history/<YYYY-MM>/history.zip` is refused, so the route can never presign
   an arbitrary object. The daily reconciler heads the named key, so a history
   link sold against an object that disappears is reported like an undelivered
   bundle, with its own repair sentence.

What the Lambda may do, and no more: read `history/*`, list the bucket under
the `history/` prefix, and send mail from the one SES identity named in
`ses_identity_arn`. The SES permission exists only when that identity is set.

### Turning the tier on (owner runbook)

Every step is an owner action; none is taken by automation or by an agent.

1. In Stripe (live mode), create one product, "GTFS Scorecard history tables",
   with one one-time price of $99 USD, nickname `history_once`, and one Payment
   Link for it: quantity 1, payment methods card and Link, after completion
   redirect to `https://gtfsscorecard.org/data/history/setup/?session_id={CHECKOUT_SESSION_ID}`,
   terms-of-service consent required, and the submit message
   "License and delivery terms: https://gtfsscorecard.org/data/history/#license".
2. Apply `infra/artifacts` for the lifecycle rule, the deny statement and the
   `history_export` role, and set the repository secret `HISTORY_AWS_ROLE_ARN`
   to the `history_export_role_arn` output.
3. Run `history-export.yml` once by hand and confirm
   `history/<this month>/history.zip` exists in the bucket.
4. In `infra/program-bundle`'s `terraform.tfvars`, set `history_price_id` to
   the price id, `ses_from` to the verified sender, `ses_identity_arn` to its
   identity ARN, and `history_sales_enabled = "1"`; rebuild the Lambda package
   and apply.
5. Rehearse once in test mode (a test price, a test Payment Link, a test
   checkout) and confirm the link, the email, and the download; then set
   `paymentsAvailable: true` and the live `checkout_url` in
   `web/data/history/plan.json`, run `make sync-bundle-offers`, add
   `"Product"` to the `/data/history/` entry of `required_json_ld_types` in
   `site-seo.json` (the offers block is the page's Product node, and the
   deploy gate requires it only once the plan is on), and merge.

## What stays free

Everything that is free today. Every dated artifact
(`/data/artifacts/<id>/<date>.json`), `index.json` and its compact history,
`catalog.*`, `dataset.*`, every `api/v1/` file including `agencies.parquet`,
the monthly `dataset-YYYY-MM` release, `/query/`, and the `history-export`
command itself, which is Apache-2.0 like the rest of the pipeline. A buyer who
would rather build the tables from the free files can. What is sold is the
built artifact and its refresh, not the facts and not the code.

Grades, methodology, weights, and which agencies are listed are not for sale,
and the tables' numbers are the ones on the public site.

## How the tables treat absence

- A category the check did not measure is null, never zero. An agency with no
  realtime feed has a null `realtime`.
- A row with `recompute_kind = freshness` is an intraday sweep: only the
  calendar dates were re-read that day, and the other category scores are the
  previous full score's, carried forward. `feed_fetched_date` says when the
  scored bytes were actually downloaded.
- Grades are comparable only within one `scoring_profile_id`,
  `validator_version`, `rubric_version`, `reader_archive_profile`, and set of
  measured categories. [docs/comparison-policy.md](comparison-policy.md)
  applies unchanged.
- License fields are null when the registry has no structured block for the
  record. Null never means permissive. An empty `license_notice` means no
  share-alike license is recorded, not that the license is known.

## Publisher terms, credit lines, and opting out

Each `checks` row carries what the registry records about the feed's terms:
`license_id`, `license_status`, `attribution_required`,
`redistribution_allowed`, and `share_alike` from the structured block (each
term as recorded: `true`, `false`, or `unknown`), `license_terms_url`,
`publisher_credit` (the credit line the publisher asks for), the prose
`license_note`, and `license_notice`, the same share-alike reuse notice the
scorecard page and the flat exports carry ([feeds.md](feeds.md#share-alike-admitted-with-a-notice)).

A publisher who does not want its feed's measurements in the tables that are
sold is listed in `history-export-exclusions.yaml` at the repository root. The
export drops every row for that id from both tables and records only the
count in `PROVENANCE.json`, so a sold file never names the publishers who
asked not to be in it. The ledger is honored the way the
[listing policy](listing-policy.md) honors a removal request: quickly, without
argument, and without touching the free site. A missing or malformed ledger
stops the export rather than shipping rows nobody checked.

## Columns

Every column name below is held to the export's own column list by
`pipeline/tests/test_history_export.py`, in both directions.

### checks

`agency_id`, `agency_name`, `country`, `subdivision_code`, `subdivision_name`,
`mdb_id`, `ntd_id`, `snapshot_date`, `generated_at`, `recompute_kind`,
`feed_fetched_date`, `artifact_schema_version`, `rubric_version`,
`scoring_profile_id`, `scoring_profile_rubric_version`, `validator_version`,
`reader_archive_profile`, `grade`, `score`, `correctness`, `freshness`,
`completeness`, `realtime`, `categories_measured`, `confidence_level`,
`days_until_expiry`, `effective_expiry_date`, `expiry_status`,
`service_horizon_status`, `feed_sha256`, `feed_size_bytes`, `feed_static_url`,
`fetch_source`, `fetch_final_url`, `source_provenance`, `stop_count`,
`primary_mode`, `finding_count`, `top_fix_code`, `license_id`,
`license_status`, `attribution_required`, `redistribution_allowed`,
`share_alike`, `license_terms_url`, `publisher_credit`, `license_note`,
`license_notice`.

### findings

`agency_id`, `snapshot_date`, `category`, `finding_index`, `code`, `severity`,
`count`, `points`, `owner`, `top_fix_rank`, `reach_basis`, `reach_affected`,
`reach_total`, `reach_share`, `reach_reason`.

Types and meanings are in the generated `DATA-DICTIONARY.md`, which
`render_dictionary()` writes from the same column list.

## The license the tables are sold under

The text between the two markers is `LICENSE_TEXT` in
`pipeline/src/scorecard_pipeline/history_export.py`, held equal by a test. It
ships in the zip as `LICENSE.md`.

<!-- history-license:begin -->
# License for the GTFS Scorecard history tables

These tables are a packaged work prepared by GTFS Scorecard (gtfsscorecard.org).
They are licensed to the purchasing organization, not to the public.

1. One organization. The purchaser may use the tables inside its own
   organization, for any internal purpose, including work it is paid for.
2. No redistribution of the package. The purchaser may not publish, sell,
   sublicense, or share the tables, in whole or in substantial part, outside
   its organization. Figures, charts, and findings derived from the tables may
   be published freely.
3. The facts stay free. Every number in these tables is derived from a dated
   scorecard artifact that gtfsscorecard.org publishes free of charge under
   CC BY 4.0, and the export command that built them is open source. Nothing in
   this license restricts the use of those free sources.
4. Share-alike rows. A row whose license_notice names a share-alike license is
   licensed to the purchaser under that license, not under clauses 1 and 2, and
   may be redistributed on that license's terms.
5. Publisher terms travel with the rows. Each feed's own publisher terms,
   recorded in license_id, license_terms_url, publisher_credit, and
   license_note, continue to apply to what the row says about that feed.
6. Attribution. A published figure drawn from the tables credits "GTFS Scorecard
   (gtfsscorecard.org), scored on top of the MobilityData gtfs-validator" and
   any publisher_credit the row carries.
7. No warranty. The grade is a data-quality signal, not a compliance
   determination, and the tables are provided as they are.
<!-- history-license:end -->

Why a different license from the free data's: the tables are a new work. The
CC BY 4.0 grant on every free file is not revoked, and clause 3 says so. The
free data page's sentence that CC BY covers "this scorecard's reports and
derived dataset" describes the free dataset; the packaged tables are separate.
