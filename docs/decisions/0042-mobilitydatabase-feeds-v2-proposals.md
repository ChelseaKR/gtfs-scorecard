# ADR 0042: Mobility Database V2 is the proposal source

**Status:** Accepted (2026-07-25)

## Context

`scorecard sync` removes mechanical work from registry intake. It reads a
catalog, omits feeds that are not suitable for an unauthenticated Schedule
check, and writes candidate YAML for a curator to review. It does not establish
feed identity, license terms, or permission to republish.

The command originally used Mobility Database's legacy `sources.csv` export.
Mobility Database now publishes `feeds_v2.csv`, whose status, authentication,
official-source, location, Schedule, and Realtime fields give intake reviewers
a clearer candidate universe. The two exports do not use the same identifier
spelling for older records: a legacy numeric id such as `123` appears as
`mdb-123` in V2.

The legacy export still carries redirect and hosted-mirror details used by
runtime recovery, moved-feed discovery, and state backfill. Changing every
catalog consumer at once would mix a proposal improvement with a
redirect-sensitive runtime migration.

## Decision

Only `scorecard sync --source mobilitydb` changes its default catalog to the
official `feeds_v2.csv` URL. An explicit `--catalog <URL-or-path>` continues to
work for a pinned snapshot or a compatible local fixture. Hosted-mirror lookup,
`scorecard discover`, and `scorecard backfill-state` temporarily retain the
legacy export.

Legacy numeric identity is compared through one normalized key. Bare numeric
`123`, prefixed `mdb-123`, and zero-padded equivalents refer to `mdb-123`.
Nonlegacy Mobility Database and Transitland identifiers retain their exact
spelling. Existing registry entries are not rewritten merely to change an id's
display form; new V2 proposals retain the source id.

`scorecard sync` remains proposal-only:

- `--out` writes reviewable candidate YAML.
- There is no `--apply` option.
- The command does not edit any registry shard.
- Proposal and sidecar outputs are rejected when they resolve to the local
  catalog input or the agency registry.
- A curator must verify source ownership, identity, status, reuse terms,
  attribution, and whether the feed belongs in the declared coverage corpus.

`--source-metadata-out <path>` writes a JSON provenance sidecar with schema
version `1.0`. It records:

- the source name and a safe location label; URL credentials, all query values,
  fragments, and local directory components are redacted. The exact downloaded
  bytes, not a potentially secret-bearing locator, are the reproducibility
  anchor;
- the UTC retrieval time;
- the SHA-256 of the exact source bytes;
- the validated V2 or compatible legacy catalog schema;
- ordered CSV columns and the SHA-256 of the exact header record, excluding its
  line ending;
- total, Schedule, Realtime, active Schedule, active keyless Schedule, and
  proposal-eligible Schedule record counts;
- the supplied country, subdivision, and provider filters; and
- the number of Mobility Database proposals remaining after those filters and
  the current registry's identity checks;
- a SHA-256 fingerprint and counts for the normalized registry ids, Mobility
  Database ids, and feed URLs used to suppress already tracked candidates;
- the package version, proposal-contract version, and SHA-256 of the installed
  Python source tree; and
- the SHA-256 and byte length of the exact rendered proposal output. An empty
  run writes an empty output file, so fresh metadata cannot sit beside a stale
  proposal.

The proposal-eligible source count is pre-filter and pre-deduplication. It
means a row is an active or status-unspecified, keyless, not-explicitly-
unofficial Schedule row with a usable proposal URL. It is a review denominator,
not an admission count.

For `--source all`, the sidecar covers only the Mobility Database CSV and
explicitly names Transitland Atlas source rows and per-source counts as
excluded. Its output hash still binds the combined rendered file, but the
sidecar cannot reconstruct the Transitland portion by itself. A
Transitland-only sync rejects `--source-metadata-out`; Transitland's source is
not the CSV snapshot described by this schema.

Every sidecar states that catalog metadata is evidence for review and does not
grant permission to reuse or republish a feed.

## Consequences

- For a Mobility Database-only run, fork operators can reproduce and verify the
  exact candidate output from the pinned source bytes, registry identity
  fingerprint, filters, and tool source digest. For `--source all`, they can
  verify the rendered file's hash but need a separately pinned Transitland
  snapshot to reconstruct it.
- Existing numeric registry pins suppress their prefixed V2 equivalents
  without a bulk registry rewrite.
- A proposal file and sidecar can be reviewed together, while the registry
  remains unchanged until a person edits the appropriate intake shard.
- Redirect-sensitive consumers keep known behavior until they receive a
  separate migration with replacement and mirror tests.
- The sidecar is a source envelope, not a complete disposition ledger. A later
  intake system can add one decision record per candidate without changing this
  boundary.

## Alternatives rejected

- **Change the global catalog default.** This would silently move mirror,
  discovery, and backfill behavior before V2 redirect coverage is proven.
- **Rewrite existing numeric ids.** Normalized comparison solves the identity
  mismatch without a large, low-value registry diff.
- **Treat catalog inclusion or a license URL as permission.** Catalog metadata
  can direct a review, but it cannot supply agency authorization or resolve all
  reuse terms.
- **Apply proposals automatically.** URL safety and duplicate checks do not
  establish canonical feed identity, rights, or appropriate coverage.
