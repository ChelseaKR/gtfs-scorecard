# Agency registry

The scorecard loads the shards listed, in order, by [`index.yaml`](index.yaml).
The manifest is authoritative: every listed file must exist, every YAML shard
under this directory must be listed, and agency ids must be unique across the
merged registry. This explicit list prevents a stray or partially generated
YAML file from silently entering production.

New agency submissions go to [`intake.yaml`](intake.yaml). Once a curator has
verified the agency's primary location, move its complete YAML block to the
matching `registry/<country>/<subdivision>.yaml` shard and add a new shard to
`index.yaml` when necessary. Move the block textually so comments and field
ordering survive. A submission and a routine feed-URL update should each touch
only the relevant small shard.

## Required fields

- `id`: stable lowercase slug containing letters, digits, `-`, or `_`.
- `name`: public agency or service name.
- `static_gtfs_url`: direct `http(s)` URL for the GTFS Schedule feed.

## Location fields

- `country`: assigned ISO 3166-1 alpha-2 code. State it on every new entry;
  omitted legacy entries default to `US` for compatibility.
- `subdivision_code` and `subdivision_name`: portable primary jurisdiction,
  normally an ISO 3166-2 code and its canonical name. Supply them together.
- `state`: deprecated US-only compatibility input retained on older records.
  Do not add it to new entries; portable location fields are canonical.

An agency that cannot yet be located honestly stays in `intake.yaml`; location
must not be guessed merely to choose a shard.

## Optional feed and curation fields

- `rt_urls`: mapping whose supported keys are `trip_updates`,
  `vehicle_positions`, and `service_alerts`; every value is an `http(s)` URL.
- `rt_note`, `license_note`, `operating_note`, `ntd_note`: curator-facing
  explanatory text shown on the relevant scorecard surfaces.
- `mdb_id`: Mobility Database source id used for exact feed rediscovery.
- `ntd_id`: four- or five-digit US National Transit Database id.
- `organization_id`: stable operator slug shared by related feeds.
- `alias_of`: id of another registry entry when this is a retained alias.
- `feed_variant`: descriptive variant label for one operator's multiple feeds.
- `feed_status`: `active`, `deprecated`, `inactive`, or `development`.
- `is_official`: `true` or `false` when catalog provenance establishes it.
- `service_type`: `fixed` (default), `seasonal`, or `demand_response`.
- `fare_free`: `true` only when fare-free operation is a verified policy.

### Reviewed reuse evidence

`reuse_evidence` is an optional, curator-approved record used by bounded
coverage gates. It is deliberately separate from `license_note`, catalog
`is_official` flags, and Mobility Database metadata. Those fields can point a
reviewer toward evidence, but they never grant permission by themselves.

```yaml
reuse_evidence:
  decision: approved
  source_kind: official_portal
  provider_source_url: https://provider.example/dataset
  terms_url: https://provider.example/terms
  scope: [gtfs_schedule]
  attribution: Provider name.
  reviewed_by: curator-handle
  reviewed_on: "2026-07-16"
  identity_reviewed: true
```

The parser accepts only an `approved` decision, `official_portal` or `provider`
source kind, HTTP(S) evidence links, the closed `gtfs_schedule` scope, a valid
review date, non-empty attribution and reviewer, and an explicit identity
review. Unknown keys or inferred evidence fail registry loading. Absence means
no approved evidence record is on file; it is not a claim that the feed is
unlicensed.

Unknown fields, malformed URLs or locations, duplicate ids, missing alias
targets, and alias cycles fail registry loading. Run the same gates as CI before
opening a pull request:

```sh
cd pipeline
uv run scorecard lint --strict
uv run pytest -q tests/test_agencies.py tests/test_submissions.py
```

The contributor walkthrough is in
[`docs/add-your-agency.md`](../docs/add-your-agency.md).
