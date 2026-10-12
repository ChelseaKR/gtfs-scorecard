# The history tables on a data marketplace

**Built, not listed.** This page is the contract for listing the
[history tables](history-tables.md) on AWS Data Exchange, decided in
[ADR 0065](decisions/0065-history-tables-on-aws-data-exchange.md). The code is
on `main` and every part of it is off: nothing is created in AWS, and the
monthly workflow runs exactly as before, until the owner registers as a seller
and turns it on with the steps below. Snowflake Marketplace was compared and
is not built; the ADR says why.

The listing is a second storefront for the same product, not a new product.
The files, the license terms, and the price per monthly build are the ones the
Stripe checkout sells on `/data/history/`.

## What a subscriber gets

One owned data set of S3 files, "GTFS Scorecard history tables". Every monthly
build is one revision of it, holding the five files the zip holds, unzipped so
a subscriber can query the Parquet where it lands:

- `checks.parquet` and `findings.parquet`, the two tables
- `DATA-DICTIONARY.md`, `PROVENANCE.json`, and `LICENSE.md`

Each revision is the whole history up to that month, not an increment, so the
newest revision is all a subscriber needs. The CSV data dictionary the listing
shows is `docs/marketplace/data-dictionary.csv`, written by
`render_dictionary_csv()` from the same column list as the zip's dictionary;
`test_data_marketplace.py` fails the build when the committed file is stale.
Regenerate it from `pipeline/` with:

    uv run python -c "from scorecard_pipeline.history_export import render_dictionary_csv as c; open('../docs/marketplace/data-dictionary.csv', 'w').write(c())"

The public sample (two CSV files, every row for three feed records whose
publishers license their data CC BY 4.0) is cut with
`pipeline/scripts/build_marketplace_sample.py` from any export directory.

## How a month reaches subscribers

1. `history-export.yml` builds the month as it always has and writes the zip
   for the Stripe tier. When the repository variable `ADX_DATA_SET_ID` is set,
   it also writes the five files to `history/<YYYY-MM>/tables/` in the same
   private bucket (same encryption, same 400-day lifecycle rule).
2. The workflow's `marketplace` job, which runs only when `ADX_DATA_SET_ID` is
   set, assumes its own role and runs
   `python -m scorecard_pipeline.marketplace_revision`. That creates one
   revision whose comment names the month, imports the five files with one
   import job, checks that the revision holds exactly those five, renames them
   to their plain file names, and finalizes it. A finalized revision in a
   published product reaches every subscriber at once.
3. A re-run for a month that is already published says so and changes
   nothing: a published revision cannot be edited, only revoked in the
   console. An unfinalized revision an interrupted run left behind is deleted
   and rebuilt from the start, so a half-imported month is never finalized.

The role (`infra/artifacts/marketplace.tf`, created only when
`marketplace_enabled = true`) may create, check, rename, finalize, and delete
an unfinalized revision of that one data set, run import-from-S3 jobs, read
`history/*/tables/*`, and write into Data Exchange's own service buckets
through Data Exchange. It cannot read the Stripe zip, the dated artifacts, or
stored orders, and it has no AWS Marketplace Catalog permission, so it cannot
create or change a product, an offer, or a price. It trusts runs on `main`
only.

## Turning it on (owner runbook)

Every step is an owner action; no automation and no agent takes any of them.
The exact field values are in the hand-off kept outside this repository; the
order is:

1. Register the AWS account that owns the artifacts bucket as an AWS
   Marketplace seller, with tax and banking information, and file the AWS Data
   Exchange provider qualification case. The account cannot be changed later.
2. In `infra/artifacts/terraform.tfvars`, set `marketplace_enabled = true` and
   apply with targets on the three marketplace resources only: the data set,
   the role, and its policy. Set the repository secret `MARKETPLACE_AWS_ROLE_ARN` to the
   `marketplace_publish_role_arn` output and the repository variable
   `ADX_DATA_SET_ID` to the `marketplace_data_set_id` output.
3. Dispatch `history-export.yml` on `main` once. It writes the tables folder
   and finalizes the first revision.
4. In the AWS Marketplace Management Portal, create the data product with the
   data set, the CSV dictionary, the sample, the listing copy, the custom data
   subscription agreement (the text of `LICENSE.md`), and the public offer.
   Test it at limited visibility, then request public visibility.

To turn it off: unset `ADX_DATA_SET_ID` (the workflow is back to the Stripe
build alone), restrict the product's visibility in the portal, and set
`marketplace_enabled = false` only after the product no longer needs the data
set.

## Price

The public offer charges the same amount per monthly build as the
`history_once` price in `web/data/history/plan.json`, for a one-month
subscription with auto-renewal off. That is the same thing the Stripe link
sells: the newest build on the day of purchase, plus any build published in
the month that follows. A buyer cannot get the same files cheaper on either
storefront. When the day-90 rule changes the plan file's price, the offer
changes the same day. A longer or renewing subscription is a refresh plan,
and a refresh plan waits for the first sale on either storefront.

## What the listing must not say

AWS Data Exchange's publishing guidelines forbid using a listing to promote a
product that is not on AWS Marketplace, so the listing copy does not link the
Stripe checkout or `/data/history/`. It may link the free site and the
documentation. It names the free sources plainly: every number in the tables
is already free, one file at a time, under CC BY 4.0.

## Fields a marketplace reviewer should know about

- `feed_static_url` and `fetch_final_url` are references to the publisher's
  own download, never feed bytes. From tables version 1.1 a credential-like
  query value in either (an API key, a token, or a presigned URL's
  signature and temporary credentials) reads `REDACTED`, and a user-info part
  is dropped. Measured on the committed snapshot before 1.1, about a fifth of
  its feed records had such a value in one of the two URLs, almost all an
  expired presigned redirect, and 7 had a publisher's API key in the
  configured URL.
- The license columns are mostly null today: the registry's structured
  license block is not yet filled for any record, so `license_id` and
  `license_notice` are null and the prose `license_note` carries what is known
  (in the registry, 967 notes say no license is stated in the Mobility
  Database; in the committed snapshot, 84 feed records name the Open Database
  License or another share-alike license). Clause 4 of the license covers share-alike
  rows by the license the row names, and the data subscription agreement
  carries the same clause.
- `owner` in `findings` is a role ("Likely your export tool"), never a person.
  No column names a person.
