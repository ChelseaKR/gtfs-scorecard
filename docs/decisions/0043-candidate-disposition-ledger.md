# ADR 0043: Catalog proposal receipts carry a complete candidate ledger

**Status:** Accepted (2026-07-25)

## Context

`scorecard sync --source-metadata-out` already binds a proposal run to the
exact Mobility Database bytes, filters, registry identity inputs, proposal
bytes, and tool source tree. Its counts explain the source envelope, but they
did not explain what happened to each Schedule row between the source
denominator and the review queue.

A proposal count alone cannot distinguish an inactive feed, an access-gated
feed, a filter mismatch, a duplicate endpoint, an already tracked identity, or
an unresolved identity conflict. Reconstructing those decisions after the run
would duplicate the proposer and could disagree with it.

## Decision

Source-metadata schema 1.2 carries a nested `candidate_ledger` with schema
version 1.0. The proposer and ledger use one decision engine. The existing
`propose_agencies()` API remains as a compatibility wrapper.

The ledger contains exactly one record for every recognized GTFS Schedule row
in the bound Mobility Database snapshot, including rows without a usable
direct-download URL. Each record has:

- its logical source-record number, source id, normalized source id, and
  provider label;
- whether it met mechanical proposal eligibility and the supplied filters;
- one disposition: `proposed_for_review`, `already_tracked`,
  `collapsed_duplicate`, `excluded`, `filtered_out`, or
  `blocked_conflict`;
- closed reason codes and review flags;
- a proposal id or selected duplicate record when applicable; and
- public registry ids when an existing identity suppressed the candidate.

The receipt reconciles the ledger against the source counts and Mobility
Database-only proposal count before writing. It also hashes the exact
Mobility Database proposal fragment. `--source all` labels cross-source
deduplication as not represented because its Transitland source snapshot is
not bound by this receipt.

The CLI validates the finished receipt against its public schema before either
output is written. The schema closes the decision, reason, review-flag, and
count vocabularies; rejects zero-valued observed counters; couples source scope
fields; and prevents a disposition from carrying contradictory proposal,
selection, registry-match, eligibility, or filter state. A Mobility
Database-only receipt run reuses the disposition engine's proposals rather
than evaluating the same source twice.

Catalog rows are grouped deterministically. If one normalized catalog id maps
to multiple normalized endpoints, every affected row is blocked as an identity
conflict. The proposer does not choose one endpoint by source order.

Ledger records omit raw Schedule and Realtime URLs, query values,
authentication details, contact fields, notes, and per-endpoint hashes. The
whole-source SHA-256 is the evidence anchor. The selected proposal fragment
continues to carry the keyless endpoint a curator must review.

`proposed_for_review` is not an admission or rights decision. This is
catalog-processing provenance, not a remediation closure receipt; it records
no participant action or causal claim. A curator still verifies ownership,
canonical identity, status, reuse terms, attribution, and fit with the declared
coverage corpus before editing a registry shard.

The public JSON contract is
[`web/schemas/sync-source-metadata-1.2.schema.json`](../../web/schemas/sync-source-metadata-1.2.schema.json).
The original 1.1 contract remains frozen at its existing unversioned path and
has a versioned reference beside it.

## Consequences

- Every Schedule source row has a machine-readable mechanical outcome.
- Candidate-processing coverage can be measured without presenting proposals
  as approved feeds.
- Duplicate and registry suppression decisions name their evidence without
  exposing endpoint secrets.
- Proposal rendering becomes independent of CSV row order for endpoint groups
  and fails closed on a catalog id that names multiple endpoints.
- This is not yet the human rights and identity disposition ledger. Human
  review decisions remain outside the sync receipt until a reviewed intake
  workflow defines that contract.

## Alternatives rejected

- **Infer outcomes from source and proposal counts.** Counts cannot explain an
  individual omission and cannot expose an identity conflict safely.
- **Write a second ledger file.** The existing source receipt already binds the
  inputs and outputs needed to interpret these decisions. Splitting the
  evidence would create an avoidable join and stale-file risk.
- **Put decisions in registry YAML.** Proposal outcomes are intake evidence,
  not properties of an admitted feed record.
- **Include raw URLs or URL hashes.** The source snapshot and proposal fragment
  already preserve the necessary evidence. Repeating secret-bearing locators
  or guessable hashes adds disclosure risk without resolving rights.
