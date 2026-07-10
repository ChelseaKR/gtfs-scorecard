# ADR 0031: Separate organizations, feeds, endpoints, and aliases

**Status:** Accepted  
**Date:** 2026-07-09

## Context

The original registry used one `Agency` record per GTFS Schedule URL. At
national scale, that is not the same as one transit agency. One operator may
publish separate bus, rail, or flex feeds; several operators may share a
regional feed; and the Mobility Database can retain an old endpoint beside its
replacement. Treating every record as a distinct agency distorts public counts,
state rollups, structured data, and search pages.

The source catalog also provides `status` and `is_official`, but the importer
previously discarded both fields.

## Decision

The registry keeps its backwards-compatible `Agency` record while adding five
identity fields:

- `organization_id`: stable operator or public-brand key shared by related feeds.
- `feed_variant`: plain-language purpose such as bus, rail, or flex.
- `feed_status`: `active`, `development`, `deprecated`, or `inactive`.
- `is_official`: the catalog's provenance flag when known.
- `alias_of`: the canonical feed record for a retired or duplicate endpoint.

An empty `organization_id` means the record's own id. An empty `alias_of` means
the record is canonical. Aliases remain in the registry so old artifacts and
citations keep resolving, but they do not count as canonical active feeds.

The Mobility Database proposer now excludes explicitly unofficial and
non-active rows, deduplicates source ids and scheme-only URL variants, and
retains status/provenance in proposed YAML.

`scorecard identity` publishes the coverage ledger used while the existing
registry is backfilled. It reports configured records, active records,
canonical feeds, distinct organizations, aliases, official-source coverage,
and unresolved duplicate groups. It does not merge records automatically.

## Consequences

- Public surfaces can use explicit denominators instead of calling every URL an
  agency.
- A curator must decide ambiguous organization and shared-feed relationships.
- Existing YAML remains valid because all new fields have conservative defaults.
- Duplicate groups remain visible until a later cleanup PR adds reviewed
  `organization_id` and `alias_of` values.

## Verification

Run:

```sh
cd pipeline
uv run scorecard identity
uv run scorecard lint
```

Last verified: 2026-07-09 · Recheck cadence: whenever the Mobility Database
catalog schema or registry identity fields change.
