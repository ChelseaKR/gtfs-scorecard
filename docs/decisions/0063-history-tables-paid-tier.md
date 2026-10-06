# ADR 0063: The history tables are the paid data tier

**Status:** Accepted (2026-10-05). The export is built; the tier is not yet on
sale. Delivery, the Terraform, the Lambda branch, the page, and the Stripe
prices follow in later phases, each behind the same mechanical gate the bundle
uses.

**Status log, phase 2 (2026-10-06).** Delivery is built and closed:
`history-export.yml` writes one zip a month to `history/<YYYY-MM>/` under its
own least-privilege role; the setup route answers a paid `history_once`
checkout with a 30-day capability for the newest object and emails the link;
`/data/history/` and `/data/history/setup/` are published with the plan file
saying payments are off. Nothing sells until the owner creates the Stripe
price and Payment Link, sets `history_price_id`, `history_sales_enabled`,
`ses_from` and `ses_identity_arn`, re-applies `infra/program-bundle`, runs the
export once, and turns `paymentsAvailable` on in the plan file; the steps are
in `docs/history-tables.md`.

**Status log, phase 3 (2026-10-06).** The pointers and the pricing copy:
`/data/` points a reader who needs the corpus over time at `/data/history/`,
`/support/` carries a second paid card, `llms.txt` and the README describe
two paid things and name no price, the history page carries the buyer's
questions and a matching FAQ node, and the price knob and the day-90 rule
are recorded in `docs/history-tables.md`. Everything is built; the owner's
runbook is the only thing between the tier and a sale.

## Context

The free read API is static files with no key and no limit (ADR 0013), the
published data is CC BY 4.0 (`docs/api.md`), and every dated artifact stays
reachable at its own address. What nobody publishes is the corpus as a table
over time: `index.json` keeps a compact trend per feed record (Yolobus carries
34 points there against 108 dated files in the artifact store), and no file
anywhere lists findings as rows. Rebuilding that history from the free site
means fetching hundreds of thousands of small files and writing the row-shaping
yourself.

A 2026-10-05 design pass (`_agent-tools/remediate-2026-10-01/gtfs-paid-api/DESIGN.md`
in the portfolio, not in this repository) compared three things that could be
sold: the history as tables, a cohort data pack for programs, and a keyed
on-demand scoring API. It recommended the tables, because they are the one
thing in this dataset that is not already free, they cost nothing to serve, and
the bundle's Stripe path (ADR 0049) can deliver them without a new always-on
resource. The owner approved that recommendation. Two earlier decisions still
say otherwise and are overridden here rather than left standing:

- `gtfs-scorecard-plans/07-monetization-sustainability.md` lists "Public
  JSON/CSV API, dataset releases, badges: Always free." That line stays true
  for everything that exists today. The tables are a new artifact.
- ADR 0049 says everything beyond the bundle "keeps the conversation door only
  until this smaller tier has a buyer," and `docs/program-plan.md`'s day-90
  gate falls on 2026-12-11. This decision opens a second checkout door early,
  on the owner's call.

A raw feed archive was examined separately on 2026-09-13 and is not an option:
most United States publishers state no license, several forbid sale, and the
roadmaps cut it four times. The tables carry measurements, not feed bytes.

## Decision

`scorecard history-export` builds two Parquet tables from the dated artifacts
under `data/artifacts`: `checks`, one row per feed record per dated check, and
`findings`, one row per finding per check. Beside them it writes a data
dictionary, a provenance file, and the license the tables are sold under.
`docs/history-tables.md` is the contract.

What the export holds to:

- **The free data stays free, and the export only reads it.** No dated
  artifact, index, flat export, or page changes. The rows are derived from
  files the site already serves, and the export command is Apache-2.0 like the
  rest of the pipeline, so a buyer who would rather build the tables
  themselves can. The price buys the built artifact and its monthly refresh.
- **Deterministic and bounded.** For a fixed artifact tree the bytes of every
  file are the same on every run: rows are emitted in one order, each table is
  written with an explicit schema, the zip carries fixed timestamps, and the
  provenance file dates itself from the newest snapshot rather than the clock.
  Artifacts are read one at a time and streamed to disk before DuckDB writes
  the Parquet, so the process holds one artifact, the registry, and counters.
- **Absence stays absent.** A category the check did not measure is null, not
  zero. A sweep row says `recompute_kind = freshness` so a consumer can tell a
  carried-forward score from a fresh one. A record with no license block has
  null license fields, never a permissive reading, and an empty
  `license_notice` means only that no share-alike license is recorded.
- **Publisher terms travel with the rows.** Each row carries the registry's
  structured license block (class, the three recorded terms, the terms link),
  the credit line the publisher asks for, the prose `license_note`, and the
  share-alike reuse notice from `license_notice.py` when the block affirms one.
  The license text says those terms continue to apply to what the row says
  about that feed, and that a share-alike row is licensed on its own license's
  terms, not the package's.
- **A publisher can opt out.** `history-export-exclusions.yaml` at the
  repository root lists the feed records whose publishers asked to be left out
  of the paid tables. The export drops every row for a listed id from both
  tables and records only the count in the provenance file, so a sold file
  never names the publishers who asked not to be in it. A missing or malformed
  ledger stops the export. Requests are honored the way `docs/listing-policy.md`
  honors a removal request.
- **Independence is unchanged.** Grades, methodology, weights, and which
  agencies are listed are not for sale, and the tables' numbers are the ones
  on the public site.

The packaged tables are licensed to the purchasing organization for internal
use, without redistribution of the package, and with every fact in them
remaining free at its public address under CC BY 4.0. The full text is in
`docs/history-tables.md` and ships in the zip as `LICENSE.md`. It is a
different license from the free data's because it is a different work; the
CC BY grant on the free files is not revoked, and nothing in the paid license
restricts the free sources.

## Consequences

- Phase 1 (this ADR) changes no page, no Lambda, no Terraform, and no Stripe
  object. `scorecard history-export` can be run by anyone with the committed
  snapshot; `make verify` holds the tables to their dictionary, the dictionary
  to the doc, the doc's license text to the module's, the exclusion rule, the
  license-notice rule, and determinism.
- Phase 2 adds a monthly workflow that writes one shared zip to a private S3
  prefix outside the CloudFront allow-list, a branch in `infra/program-bundle`'s
  setup route that mints a capability for the newest zip and emails the
  existing download link, and the landing and setup pages. The Stripe prices
  and Payment Link are owner steps. Phase 3 is the pricing copy, the open-data
  page, and the release notes.
- The monthly dataset release (`dataset-release.yml`) is the free anchor a paid
  monthly refresh sits beside. It has not cut a release since August; its fix
  (#506) comes before the tier opens.
- The 2026-09-13 licensing audit's layperson reading stands: the tables add no
  disclosure the free CC BY export does not already make, and what they add is
  money changing hands, which is the one word some United States publishers'
  terms turn on. The notices, the credit lines, and the opt-out ledger are the
  answer; a legal review sits beside the still-outstanding tax review in
  `docs/program-plan.md`.
- The day-90 rule still applies to this tier on its own clock: a page over
  about 50 unique visitors and no sale after 90 days halves the one-time price
  once; nothing else changes.
