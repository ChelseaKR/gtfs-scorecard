# ADR 0065: The history tables get a second storefront on AWS Data Exchange

**Status:** Accepted (2026-10-11). Built and off. Nothing is listed until the
owner registers as a seller and runs the steps in `docs/data-marketplace.md`.

## Context

The history tables (ADR 0063) sell through one Stripe Payment Link on
`/data/history/`. On 2026-10-11 the owner asked for the tables to be listed on
data marketplaces as a passive channel, inside the standing rules: no active
buyer outreach, no consulting, storefronts that sell without a conversation.

The traffic the site has today does not argue for or against this. A
read-only investigation the same day found about two search visitors a day, no
query with commercial intent in four months, and zero sessions from an agency
page to either paid page. A marketplace brings its own browsing buyers, which
is the only reason to try one; whether any of them want GTFS quality history
is unmeasured. This is an experiment with a low running cost, not a forecast.

Two marketplaces were compared, from their official documentation read on
2026-10-11:

- **AWS Data Exchange.** Individuals who are US citizens or residents may be
  providers. Registration is an AWS Marketplace seller account with a W-9 and
  a US bank account, plus a provider qualification case. AWS keeps 3% of a
  public offer (the listing fee for Data Exchange since 2024-01-05) and pays
  out monthly after it collects. A product is a data set of S3 files with
  monthly revisions, which is exactly how the tables are already built.
  Publishing a revision is an API call, so the monthly build can feed it
  without anyone touching the console. Running cost is S3-class storage of a
  few hundred megabytes a year, cents a month.
- **Snowflake Marketplace.** A provider needs a full (not trial) Snowflake
  account, a provider profile approved by Snowflake, Stripe Express for
  payouts, and a case with Snowflake before the first paid listing. A paid
  public listing must offer a free trial. Snowflake's fee is not published;
  it is shown in the account after onboarding. Delivery is a secure share of
  tables loaded into the provider's account, and reaching consumers in other
  regions runs cross-region auto-fulfillment, billed to the provider as
  compute, storage, and egress per region. The data is small, so the dollars
  are small, but it is a second always-on account and a load step this
  project does not have.

## Decision

List on AWS Data Exchange first. Snowflake is not built.

- **One data set, one revision a month.** `history-export.yml` writes the
  month's five files unzipped under `history/<YYYY-MM>/tables/` and a new
  `marketplace` job imports them into a new revision and finalizes it, only
  after the import completed and the revision holds exactly those five files.
  Both run only when the repository variable `ADX_DATA_SET_ID` is set.
- **Off until the owner turns it on.** `infra/artifacts/marketplace.tf`
  creates the data set and the publishing role only with
  `marketplace_enabled = true`. Registration, the product, the offer, and the
  data subscription agreement are console steps for the owner.
- **Least privilege.** The publishing role works on that one data set's
  revisions and assets and on import-from-S3 jobs, reads only
  `history/*/tables/*`, and has no AWS Marketplace Catalog permission, so it
  cannot create or change a product, an offer, or a price.
- **Same product, same price per build.** The offer is a one-month
  subscription at the `history_once` amount with auto-renewal off, which is
  what the Stripe link sells. The data subscription agreement carries the
  text of `LICENSE.md`. A buyer cannot get the same files cheaper on either
  storefront, and the day-90 rule moves both prices together.
- **The listing does not point at the Stripe checkout.** Data Exchange's
  publishing guidelines forbid promoting products that are not on AWS
  Marketplace. It may link the free site and the documentation.
- **Credential-like URL values are redacted in the tables.** A marketplace is
  a wider audience than one buyer, and the committed snapshot showed 418 feed
  records whose fetch URL carried an expired presigned signature and temporary
  credentials, and 7 with a publisher's API key in the configured URL. From
  tables version 1.1 those values read `REDACTED` in both storefronts'
  files. The free site's published URLs are redacted separately, by ADR
  0066's shared rule; this export keeps its own `redact_url`.

## Consequences

- Nothing changes until the owner acts; with the variable unset the monthly
  workflow is the same run as before, apart from an extra skipped job.
- Each listing adds an owner chore: refunds on Data Exchange are approved
  through an AWS form, and a subscriber's support request arrives through the
  support contact on the listing (the repository's issue tracker).
- A month that is already published cannot be replaced. A make-good re-run
  updates the Stripe zip and leaves the published revision as it is; the
  owner can revoke a bad revision in the console.
- Snowflake stays a documented option. It becomes worth building if a buyer
  asks for a share rather than files, or if Data Exchange sells and the
  same buyers are known to live in Snowflake.
- The day-90 rule now reads two storefronts. A sale on either counts.
