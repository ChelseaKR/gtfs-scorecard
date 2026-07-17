# Read API and data contract

The scorecard publishes static JSON, and that JSON is a public read API. Other
tools, dashboards, and an agency's own website can pull a grade without scraping
the page. This document is the contract those consumers depend on. The roadmap
(docs/roadmap.md, Year 3) makes it an intentional, versioned interface; this
file is the start of that.

## Where the data lives

On the deployed site, artifacts are served under `data/artifacts/`. When the
CloudFront origin is configured (ADR 0002), the same paths sit under the CDN
domain. Every path below is relative to that base.

| Path | What it is |
| --- | --- |
| `index.json` | Every published feed record with its score/grade history. Powers the picker and trends. |
| `directory.json` | Slim covered-set directory: per-scorecard grade, portable location, size tier, plus guarded corpus-wide, country/subdivision, and legacy place summaries. Individual percentiles are not published. |
| `changes/latest.json` | Canonical feed records whose grade or score moved under the same current producer contract since their last check. Auditable dated copies are retained at `changes/<date>.json`. |
| `<agency>/latest.json` | The most recent full scorecard for one agency. |
| `<agency>/<date>.json` | The scorecard for one agency on one date (`YYYY-MM-DD`). |
| `<agency>/badge.svg` | Embeddable grade badge (see below). |
| `<agency>/badge.json` | The same grade in the Shields.io endpoint format, for custom badges. |
| `rollups/index.json` | Every published program rollup, summarized. |
| `rollups/<id>.json` | One rollup across many agencies. |
| `rollups/<id>.csv` | The same rollup's members as a spreadsheet (grade, score, expiry status, top fix) for a liaison's report. |
| `catalog.json` | Flat list of every agency with grade, feed URL, freshness, identity, and provenance, in one request. |
| `catalog.csv` | The same catalog as CSV. |
| `scoring.json` | Machine-readable methodology: category weights, grade bands, and the correctness severity deductions. |
| `/api/v1/coverage.json` | Separately named registry, organization-key, published-page, and scored-row counts. |
| `/schemas/artifact.schema.json`, `/schemas/catalog.schema.json`, `/schemas/directory.schema.json`, `/schemas/coverage.schema.json` | JSON Schemas (Draft 2020-12) for validating the per-agency artifact, catalog, directory, and coverage counts in CI. |

## License and attribution

The published scorecard data is offered under **CC-BY-4.0**. Reuse it, including
commercially, with attribution: "GTFS Scorecard (gtfsscorecard.org), scored on
top of the MobilityData gtfs-validator." The `catalog.json` and `directory.json`
documents carry `license` and `attribution` fields so the grant travels with the
data. The grade is a derived data-quality signal, not a compliance
determination.

## Coverage and sampling frame

The scorecard scores feeds discovered through the Mobility Database plus a
curated set. An agency that publishes no GTFS, or that appears in no catalog, is
not scored and simply does not appear. Absence therefore means "not covered,"
never "failing." Do not infer a national denominator from the row count; it is
the covered set, not the universe of US agencies.

`/api/v1/coverage.json` makes the service's internal denominators explicit.
`configured_feed_records` and `active_canonical_feed_records` describe the
curated registry. `distinct_organization_keys` includes feed-ID fallbacks;
`provisional_organization_keys` says how many of those fallbacks still need
curation. `published_scorecard_pages` counts entries retained in the artifact
index, while `scored_latest_rows` counts latest rows with a numeric score.
These values can differ because removing a feed from the registry does not
erase its published history. The older `/api/v1/stats.json` `agency_count`
field remains for API v1 consumers and counts every row in that endpoint's
published score dataset. `comparison_eligible_count` names the narrower
producer-, methodology-, category-, and identity-safe denominator used for
score aggregates. Use `coverage.json` for registry, organization, and rendered
page counts.

## Versioning

Every artifact carries a `schema_version` (currently `1.14`). The rule for
consumers: tolerate added fields, and treat a change in the major version as a
breaking change worth pinning against. New fields are additive within a major
version. When a field's meaning changes or a field is removed, the major
version increments and the change is noted in the rubric changelog.

A JSON Schema for the per-agency artifact (`latest.json`, `<date>.json`),
`catalog.json`, and `directory.json` is published under `/schemas/`, so a
consumer can validate against it in CI and catch a breaking change as a test
failure. The pipeline enforces the artifact schema on its own output: every
artifact is validated against `artifact.schema.json` before it is written, so a
shape change cannot reach production without a schema update. `scoring.json`
exposes the category weights, grade bands, and severity deductions, so the
grade is reproducible rather than opaque.

The raw feed bytes behind a grade are archived too, deduplicated by the
`feed.sha256` every artifact already carries (content-addressed: one copy per
distinct hash, not per agency per day). The score job writes each new hash to
a local dedup store and, when a durable bucket is configured
(`RAW_ARCHIVE_BUCKET`, falling back to `ARTIFACTS_BUCKET`), to S3 as the
second, durable tier (`archive.py`). `scorecard reproduce <agency> <date>`
pulls the archived bytes for a published snapshot, re-runs the validator
version that artifact recorded, rescores it, and diffs the result against the
published grade, score, and category scores: the mechanism a disputed grade
or a validator-upgrade study cites. The archive is private to the pipeline;
public redistribution of a re-served copy is a separate, license-gated
decision (see `docs/ideation/02-large-scale-fixes.md`, FIX-02).

The flat analysis exports (`dataset.json`, `dataset.csv`,
`api/v1/agencies.parquet`) carry two version fields: `schema_version` is the
version of the flat export's own shape, and `pipeline_schema_version` is the
artifact schema (the `1.x` documented here) the export was derived from. A
citation should pin the release tag, which fixes both.

Flat export schema `1.2` adds `rubric_version`, `scoring_profile_id`,
`scoring_profile_rubric_version`, `validator_version`, and `feed_sha256`.
Together with the category columns, these fields let consumers build the same
single-producer, single-category-set, deduplicated comparison cohort as the
public summaries.

For citation, do not cite the live site: it changes daily. A monthly
`dataset-YYYY-MM` release (the `Dataset release` workflow) pins the flat
exports, the parquet file, the NTD rollup, this data dictionary, and
`CITATION.cff` to an immutable tag, so a paper's reference resolves to exactly
the bytes analysed. Releases:
<https://github.com/ChelseaKR/gtfs-scorecard/releases>.

Changelog:

- `1.14` adds `ferry_profile` to every ferry-serving feed. The ungraded block
  measures the ferry subset's terminal hierarchy, `stop_access`, published
  wheelchair fields, and bicycle and car carriage fields. It labels fare and
  configured realtime facts as whole-feed. Blank enum values remain unknown.
  Selected fields are also flattened into `api/v1/features.json`. Additive;
  grades and the scoring profile are unchanged.
- `1.13` adds a descriptive `mode_profile` to every current artifact. It
  reports route and trip counts by GTFS `route_type`, the trip-weighted primary
  mode, mixed-mode status, and ferry membership. The block is explicitly
  ungraded. The version bump rebuilds unchanged feeds once so mode filters do
  not confuse an older unknown measurement with an absent mode. Additive;
  grades and the scoring profile are unchanged.
- `1.12` adds the `translations` detail block to measured rider-experience
  completeness artifacts. The version bump makes unchanged-feed reuse rebuild
  each current artifact once, so translation availability does not remain
  unknown after deployment. Additive; grades and the scoring profile are
  unchanged.
- `1.11` adds `configured_kinds` and `kinds_configured` to Realtime category
  details. Together with `kinds_reachable`, they state the exact denominator
  behind capability-aware reachability scoring for partial GTFS-Realtime
  publishers. Additive.
- `1.10` adds `effective_expiry_date`, `service_horizon_review_years`, and
  `service_horizon_status` to freshness details; the status is also copied to
  index history, catalog rows, and the open dataset/API. An unusually distant
  service end date is a display and trust advisory, not a GTFS error, finding,
  or score deduction. Readers derive the same status for legacy rows when the
  field is absent but snapshot date and expiry evidence are present, so an
  existing artifact is safe on the first deployment.
  The downloadable dataset shape was `1.1` with the added status column.
  Additive.
- `1.9` broadens portable country fields from the initial US/Canada values to
  every assigned ISO 3166-1 alpha-2 country. Published schemas validate the
  stable alpha-2 shape; the generated global ISO vocabulary remains the
  stricter admission boundary for country and subdivision codes. Scores and
  the scoring profile are unchanged. Additive.
- `1.8` adds the required `scoring_profile` block to every per-agency
  artifact. It identifies the scoring contract independently from the API
  schema and states that its weights, deductions, thresholds, grade bands,
  and fix ranking are project choices, not worldwide authority. No existing
  score, category, grade, or top-fix field moved or changed. Additive.
- `1.7` adds portable agency location fields: ISO 3166-1 `country`, ISO 3166-2
  `subdivision_code`, and practitioner-facing `subdivision_name`. The legacy
  `state` field remains available for existing US consumers. The initial
  published values were `US` and `CA`. Additive.
- `1.7` introduced `state_percentile` on per-state rollups. Public percentile
  claims were subsequently retired. Current rollup payloads retain the field as
  `null` for compatibility and expose guarded comparison-cohort metadata
  instead. Historical 1.x documents may still contain the former integer.
- `1.6` adds a `confidence` block to every scorecard: a `level`
  (`provisional`, `medium`, or `high`) reading how much of the grade this run
  could measure, plus the measured category count, fetch source, realtime
  sampling depth, and snapshot age behind it. A legibility layer on the one
  grade, never a second grade. Additive.
- `1.5` adds `shapes_readiness` to every US agency artifact: shapes.txt
  coverage of trips, mapped onto FTA's July 2025 shapes.txt requirement
  (Full Reporters RY2025; Reduced, Rural, and Tribal Reporters RY2026).
  Additive.
- `1.4` carries identity and provenance on every catalog and directory row
  (`mdb_id`, `validator_version`, `rubric_version`, `retrieved_at`,
  `feed_sha256`) and a `license`/`attribution` on the catalog and directory
  documents. Additive.
- `1.3` exposed the freshness fields described below (`days_until_expiry` in
  index history, `expiry_status` in the catalog and rollup members). Additive.

## Scorecard shape (`latest.json`, `<date>.json`)

```jsonc
{
  "schema_version": "1.14",
  "rubric_version": "1.2",
  "scoring_profile": {
    "id": "gtfs-scorecard-1.2",
    "rubric_version": "1.2",
    "provenance": "GTFS Scorecard's project-authored weights, deductions, thresholds, grade bands, and fix ranking, informed by the California Transit Data Guidelines and the MobilityData gtfs-validator. It is not a worldwide standard or a compliance determination."
  },
  "validator_version": "8.0.1",       // the MobilityData gtfs-validator release used
  "agency": { "id": "barrie-transit", "name": "Barrie Transit (Ontario)",
              "country": "CA", "subdivision_code": "CA-ON",
              "subdivision_name": "Ontario",
              "operating_note": "optional curator-verified status; absent if unset" },
  "generated_at": "2026-06-12T13:25:01+00:00",   // when this grade was produced (retrieved_at in the catalog)
  "snapshot_date": "2026-06-12",
  "feed": { "static_url": "...", "sha256": "...", "size_bytes": 0, "license_note": "..." },
  "mode_profile": {
    "measured": true, "graded": false,
    "primary_mode": "ferry", "primary_mode_label": "Ferry",
    "modes": [
      { "key": "ferry", "label": "Ferry", "route_count": 2,
        "trip_count": 38, "trip_share_pct": 100.0 }
    ],
    "route_count": 2, "trip_count": 38, "is_multimodal": false,
    "has_ferry": true, "ferry_only": true
  },
  "ferry_profile": {
    "measured": true, "graded": false, "scope": "ferry_routes_and_trips",
    "route_count": 2, "trip_count": 38,
    "terminal_hierarchy": {
      "boarding_location_count": 8,
      "parented_boarding_location_count": 6,
      "parented_boarding_location_pct": 75.0,
      "referenced_station_count": 3
    },
    "stop_access": {
      "eligible_terminal_count": 6, "stated_count": 4, "stated_pct": 66.7,
      "direct_count": 2, "through_station_count": 2
    },
    "accessibility": {
      "terminals": { "total_count": 8, "stated_count": 6, "stated_pct": 75.0,
                     "allowed_count": 5, "allowed_pct": 62.5,
                     "not_allowed_count": 1, "not_allowed_pct": 12.5 },
      "trips": { "total_count": 38, "stated_count": 30, "stated_pct": 78.9,
                 "allowed_count": 28, "allowed_pct": 73.7,
                 "not_allowed_count": 2, "not_allowed_pct": 5.3 },
      "measures": "published_values_not_physical_usability"
    },
    "bikes": { "...": "same yes/no/unknown coverage shape over ferry trips" },
    "cars": { "...": "same yes/no/unknown coverage shape over ferry trips" },
    "fares": { "scope": "whole_feed", "fare_free": false,
               "model": "legacy", "applied": true },
    "realtime": { "scope": "whole_feed", "configured_kinds": ["trip_updates"],
                  "kinds_configured": 1 }
  },
  "overall": { "score": 84.1, "grade": "B",
               // distance to the grade-band edges: points up to the next letter's
               // floor (null for an A) and points above this band's own floor
               "margin_to_next_band": 5.9, "margin_to_lower_band": 4.1 },
  "fetch": { "source": "origin",      // or "mirror" (MobilityData hosted copy); "unknown" for
                                      // snapshots downloaded before provenance recording
                                      // (fetch policy itself: gtfsscorecard.org/fetcher/)
             "final_url": "...",      // the URL that actually served the graded bytes
             "user_agent": "...",     // the User-Agent presented to that server
             "max_attempts": 4,       // configured attempt ceiling; omitted when unknown
             "origin_error": "..." }, // exception that forced the mirror; only on mirror fetches
  "confidence": { "level": "high",          // "provisional", "medium", or "high" — a word, never a letter or a number
                  "measured_categories": 4, "total_categories": 4,
                  "fetch_source": "origin", "rt_windows": 1, "feed_age_days": 0,
                  "notes": [ "All four score categories were measured this run.", "..." ] },
  "shapes_readiness": { "status": "ready",   // or "at_risk" / "not_ready"; US agencies only
                        "detail": "plain language", "fix": "present unless ready",
                        "total_trips": 0, "trips_with_shape": 0 },
  "categories": {
    "correctness":  { "name": "...", "status": "measured", "score": 0, "weight": 0.35,
                      "summary": "plain language", "findings": [ /* see below */ ],
                      "details": { /* category-specific */ } },
    "freshness":    { "...": "..." },
    "completeness": { "...": "..." },
    "realtime":     { "status": "not_yet_measured", "summary": "neutral note", "weight": 0.20 }
  },
  "top_fixes": [ { "rank": 1, "code": "...", "what": "...", "why": "...", "fix": "...",
                   "effort": "...", "severity": "WARNING", "count": 0 } ]
}
```

`scoring_profile.id` is the stable identifier consumers should use when they
need to compare like-for-like grades. It changes when the scoring contract
changes, while `schema_version` changes when the artifact shape changes. The
duplicated `rubric_version` makes the relationship explicit without requiring
consumers to parse the profile identifier. This block describes the one shared
profile only; it does not select or apply a jurisdiction overlay.

In a scorecard's `agency` block, an omitted `country` means the legacy `US`
default. The portable subdivision fields are optional when the primary
subdivision is not known. US artifacts may also carry `state` as a compatibility
alias; non-US artifacts do not use it. Consumers must treat `country` as an open
ISO 3166-1 alpha-2 value rather than an enum of the countries covered today. A
new country can appear within API v1 without changing the field's meaning or
type. The agency registry determines which countries currently have scorecards;
it does not determine which assigned ISO locations the data model can represent.
The write boundary validates codes against the packaged global ISO vocabulary.

A category is either `"status": "measured"` (has `score`, `summary`,
`findings`, `details`) or not measured (`"status": "not_yet_measured"` with a
neutral `summary` and no score). An agency without realtime is never a zero.

The `fetch` block states how the graded bytes were obtained. When an origin
403s or times out, the pipeline scores the MobilityData hosted mirror instead
of dropping the agency; `"source": "mirror"` makes that visible, since a mirror
copy can lag what the agency republished. The block is additive within schema
1.4 (consumers tolerate added fields, per the versioning rule above).

The `confidence` block states how much of this grade the pipeline could
measure this run, not a second grade on top of it: `level` is always a word
(`provisional`, `medium`, or `high`), never a letter or a number, so it cannot
be mistaken for a second score. `measured_categories` and `total_categories`
state the breadth measured; `fetch_source` mirrors `fetch.source` above;
`rt_windows` is `1` when realtime was sampled this run; `feed_age_days` is how
old the scored snapshot was at scoring time; `notes` are the same
plain-language sentences shown in the scorecard page's "How we measured this"
panel. Absent on artifacts published before schema 1.6. Additive within schema
1.6.

The `shapes_readiness` block (US agencies only, schema 1.5) reads the feed's
shapes.txt coverage against FTA's NTD shapes requirement: `status` is `ready`
(every trip has a shape), `at_risk` (partial coverage), or `not_ready` (no
shapes), with a plain-language `detail` and, when not ready, a concrete `fix`.
Like `ntd_ready`, it is a data-quality heads-up, never an official
determination.

## Freshness fields

The `freshness` category's `details` carry the feed's validity window, and two
fields are surfaced for consumers:

- `details.days_until_expiry` (integer, or `null` when the feed states no end
  date): days until the feed's service window closes. Negative means it already
  expired that many days ago. Also copied onto each `index.json` history point.
- `details.effective_expiry_date` (ISO date, or `null`): the exact earlier date
  used from `feed_info` and scheduled service.
- `details.service_horizon_review_years` (integer): the documented ten-year
  review threshold used for this artifact.
- `details.service_horizon_status` (string, also copied onto index history,
  catalog, and open-dataset rows): `within_review_threshold`,
  `unusually_distant`, or `unknown`. Unusually distant means the effective end
  date is strictly more than ten calendar years after the check. The exact
  boundary stays within the threshold. This advisory is outside category
  findings, Top 3 fixes, finding prevalence, and finding diffs; it changes no
  score. For legacy artifacts and rows without this field, consumers can derive
  it from the snapshot/date plus `effective_expiry_date` or
  `days_until_expiry`. Missing date evidence remains `unknown`.
- `expiry_status` (string): a stable bucket derived from `days_until_expiry`,
  published on `catalog.json` agencies and rollup members. One of:

  | Value | Meaning |
  | --- | --- |
  | `current` | 30+ days of service left |
  | `expiring_soon` | 1 to 30 days left |
  | `lapsed` | expired within the last year (likely still running) |
  | `stale` | expired over a year ago (source went quiet) |
  | `unknown` | no end date in the feed |

## Catalog (`catalog.json`)

One document listing every published feed record, for consumers that want the
whole picture in a single request rather than fetching each `latest.json`.

```jsonc
{
  "source": "https://gtfsscorecard.org",
  "schema_version": "1.14",
  "rubric_version": "1.2",
  "license": "CC-BY-4.0",
  "attribution": "GTFS Scorecard (gtfsscorecard.org), scored on top of the MobilityData gtfs-validator",
  "agencies": [
    { "id": "yolobus", "name": "Yolobus (...)", "country": "US",
      "subdivision_code": "US-CA", "subdivision_name": "California",
      "state": "California", "grade": "B", "score": 84.1,
      "correctness": 90, "freshness": 85, "completeness": 72,
      "realtime": 88, "size_tier": "small",
      "national_percentile": null, "peer_percentile": null,
      "snapshot_date": "2026-06-12", "days_until_expiry": 120,
      "service_horizon_status": "within_review_threshold", "expiry_status": "current",
      "ntd_ready": "ready", "google_gate": "pass", "stops": 312,
      "mdb_id": "1234", "validator_version": "8.0.1", "rubric_version": "1.2",
      "scoring_profile_id": "gtfs-scorecard-1.2",
      "scoring_profile_rubric_version": "1.2",
      "retrieved_at": "2026-06-12T13:25:01+00:00", "feed_sha256": "...",
      "feed_url": "...", "top_fix": "...", "scorecard_url": "https://..." }
  ]
}
```

`catalog.csv` carries the key columns (including `mdb_id`, `country`,
`subdivision_code`, `subdivision_name`, and
`validator_version`). Use `mdb_id` to join a row to the Mobility Database rather
than matching on the scorecard's own slug or on the feed URL.

Three readiness fields ride on every catalog and directory row and are worth
consuming directly rather than re-deriving:

- `ntd_ready` (string): readiness for the FTA NTD GTFS requirement, rolled up
  from the published/valid/current/agency_id pillars. One of `ready` (all four
  pillars hold), `at_risk` (a recoverable gap: validator errors, service running
  out soon, or identity not checked), `not_ready` (unreachable, lapsed, no
  readable end date, or no nonblank agency_id). A
  data-quality heads-up, never an official determination; the agency's own
  D-10 certification is the official one.
- `google_gate` (string): whether the feed clears the Google/Apple Maps
  four-week service-coverage bar. One of `pass` (four or more weeks of service
  ahead), `at_risk` (under four weeks), `fail` (expired).
- `stops` (integer or null): boardable stop count read from the feed's
  stops.txt, a rough size signal alongside `size_tier`.
- `country` (string): ISO 3166-1 alpha-2 country code. It defaults to `US` for
  registry entries that predate the international location fields. The schema
  validates the portable alpha-2 shape, not a closed list of countries; clients
  should preserve unfamiliar valid codes.
- `subdivision_code` (string or null): ISO 3166-2 code for the agency's state,
  province, or territory, such as `US-CA` or `CA-ON`.
- `subdivision_name` (string or null): practitioner-facing subdivision name,
  such as `California` or `Ontario`. Use it for display; use
  `subdivision_code` for joins and grouping.
- `state` (string or null): legacy US display field retained for compatibility.
  Existing US consumers may keep reading it. New consumers should use
  `subdivision_code` and `subdivision_name`; do not treat a null `state` on a
  non-US agency as unlocated.

## Directory (`directory.json`)

The covered-set document the web app's overview reads: one record per published feed with
the same fields as a catalog row (identity, grade, freshness, readiness,
provenance, and size tier) plus a `summary` block with expiring and expired
counts, size-tier counts, and guarded score aggregates. The `comparison` object
states the required rubric, scoring profile, validator, measured category set,
and exclusions; unresolved duplicate feed identities do not influence medians
or grade distributions. `feed_records` counts every published row,
`scored_feed_records` counts the subset with a numeric score, and
`comparison_eligible_count` states the still-narrower score-aggregate
denominator. The legacy
`national_percentile` and `peer_percentile` keys remain present as `null`; no
individual percentile is published. It carries the same `license` and
`attribution` as the catalog. Prefer it over `index.json` when you want the
current coverage picture without the full per-feed history.

## Versioned cross-agency API (`api/v1/`)

The paths above are per-agency or whole-catalog. The `api/v1/` endpoints add the
cross-agency views a state program or app developer asks for, as small flat JSON
files under a versioned path. `v1` is a stability contract: fields may be added,
but existing fields keep their meaning and type, and a breaking change lands at
`api/v2`. Built from the same index, so the numbers match the pages (ADR 0013).

| Path | What it is |
| --- | --- |
| `api/v1/index.json` | The API's self-description: version, endpoint list, license, attribution. |
| `api/v1/agencies.json` | Every published feed record's latest check in one list (id, name, date, grade, score, rubric and scoring-profile fields, validator version, feed hash, category scores, days to expiry, and service-horizon review status). `realtime` is null when not measured. |
| `api/v1/leaderboard.json` | Compatibility path for named changes. `top` and `bottom` are always empty; `most_improved` and `most_declined` compare a canonical feed only with its own prior check under the same rubric, scoring profile, validator, and measured category set. |
| `api/v1/by-state.json` | Legacy U.S.-state rollups. `count` covers every U.S. published row in the state; `comparison_eligible_count`, median score, and grade distribution use the guarded comparison cohort. U.S. feeds without a known state group under `Unlocated`. |
| `api/v1/by-location.json` | Portable country rollups with nested ISO 3166-2 subdivisions. Each `count` covers every published row in that location; `comparison_eligible_count`, median score, and grade distribution use the guarded comparison cohort. Null codes collect rows whose curated location is unknown. |
| `api/v1/stats.json` | Covered-row count and current-feed share over every published row, plus average score, median score, and grade distribution over the guarded cohort. `comparison_eligible_count` and the `comparison` block state that narrower denominator and its exclusions. |
| `api/v1/equity.json` | United States-only state ACS need tiers (poverty, zero-vehicle, disability) joined to agency grades. Refreshed weekly from U.S. Census ACS. |
| `api/v1/ids.json` | Identity crosswalk: every agency's scorecard slug joined to its Mobility Database id, NTD id, and feed URL, so grades join to either registry (or FTA data) without fuzzy matching. |
| `api/v1/ridership-impact.json` | United States-only quality context weighted by NTD annual rider-trips (ADR 0021). Weighting uses the guarded comparison cohort and only unique, unambiguous NTD reporter matches. `matched_ntd_reporters`, `total_feed_records`, and the duplicate-reporter exclusion fields disclose coverage; legacy `matched_agencies` and `total_agencies` keys remain as aliases. Present when the daily NTD fetch succeeded. |
| `api/v1/scoring.json` | The same machine-readable methodology as `scoring.json` at the artifact base (weights, grade bands, deductions), served under the versioned path. |
| `api/v1/accessibility.json` | Covered-set accessibility-data completeness: how many feeds populate wheelchair fields, overall and by portable country/subdivision. Backs the coverage section at `/adoption/#access`. |
| `api/v1/adoption.json` | Which optional GTFS capabilities (Flex, Fares v2, pathways, cEMV, and rider-facing translations) feeds publish, overall and by portable country/subdivision. Backs `/adoption/`. |
| `api/v1/features.json` | Every current feed record with filterable service modes, capability flags, translation languages, stop- and trip-level wheelchair-field completeness, ferry-subset capability measurements, portable location, identity, scorecard URL, and comparison eligibility. Unknown measurements are `null`, never `false`. Backs the consumer filters and CSV export in `/app/`. |
| `api/v1/global-coverage.json` | Auditable readiness gate for a bounded European GTFS Schedule beta. It lists the reviewed feed-record cohort, source and terms evidence, current-versus-threshold criteria, country balance, freshness and measurement exceptions, and explicit limits. `not_ready` is a valid result, not an API failure. |
| `api/v1/realtime.json` | Realtime reliability over sampled windows, overall and by portable country/subdivision. Backs `/realtime/`. |
| `api/v1/problems.json` | The most common validator findings across the covered corpus, with prevalence counts. Its input contains findings without agency identity, so this endpoint has no geographic rows. Backs `/problems/`. |
| `api/v1/trend.json` | The covered-set quality time series. Backs the trend section at `/pulse/#trend`. |
| `api/v1/status.json` | Intended cadence plus liveness outcomes restricted to the current published artifact index. Its `scope` block discloses included and excluded liveness records. |
| `api/v1/run-status.json` | Latest completed-run evidence. Aggregate counts retain that run's historical attempted set; named unreachable records are restricted to the current published catalog, with older records counted but not named. |
| `api/v1/canada-equity.json` | Canada served-area equity overlay (StatCan CIMD, ADR 0027), refreshed monthly. Appears once the monthly job has run. |

`features.json` keeps the feature-measurement denominator separate from the
score-comparison denominator. `capability_measured_count` and
`accessibility_measured_count` cover every current feed record with those
measurements. `translation_measured_count` counts rows rescored with the
translation detector; older rows keep `has_translations`, `translation_count`,
`translation_languages`, and `translated_tables` null. `mode_measured_count`
counts rows with the ungraded `route_type` profile; older rows keep
`primary_mode`, `modes`, `has_ferry`, and `ferry_only` null.
`ferry_profile_measured_count` counts ferry-serving rows carrying the ungraded
ferry profile. Its flat fields include ferry route, trip, and terminal counts;
`stop_access`, wheelchair, bicycle, and car completeness percentages; explicit
allowed percentages; the feed-level fare model; and configured realtime kinds.
Schedule fields use ferry routes and trips only. Fare and realtime fields
describe the whole feed, matching the scope labels in the artifact.
`comparison_eligible_count` only describes whether scores share
the current producer contract; it does not control feature filtering. Combine
feature flags with AND logic. A wheelchair completeness threshold is inclusive,
except the `any` option in the web app, which means greater than zero. A null
value does not match a filter. Published accessibility metadata describes the
GTFS feed, not verified physical accessibility. Translation metadata describes
usable rows and language tags in `translations.txt`; it does not assess
linguistic accuracy or complete coverage of every customer-facing value.
Translation-language filters match an exact BCP 47 tag case-insensitively, so
`fr` does not imply a match for `fr-CA`.

`global-coverage.json` counts active canonical feed records whose structured
registry evidence was reviewed and approved for GTFS Schedule reuse. It does
not infer permission from free-form notes, catalog flags, or proposed metadata.
The European scope is the EU27 plus the United Kingdom, Switzerland, Norway,
Iceland, and Liechtenstein. The gate requires 250 reviewed records across 12
countries, no country above 40%, at least 95% of scorecards retrieved within
seven days, and complete translation-measurement, portable-location, identity,
and feature-denominator checks. Percentages over an empty cohort are `null` and
unmet. This is not a claim about all European transit, distinct agencies,
NeTEx, or service-calendar freshness. Provider terms remain attached to each
record; the endpoint's CC BY notice applies to the derived gate output.

In `api/v1/status.json`, `currently_clean_pct` is the current share of feed
records with no consecutive failed direct check. The legacy
`success_rate_pct` field remains as an equal-valued compatibility alias; it is
not a historical request-success rate. Direct liveness never uses a mirror,
while the daily scoring run may use the Mobility Database mirror.

Per-agency detail stays the published artifact (`<agency>/latest.json`); the API
does not duplicate it. Human-readable named changes and the corpus trend render
on [the coverage overview](https://gtfsscorecard.org/pulse/). Absolute score
rankings and individual percentiles are not published.

The `comparison` block on aggregate endpoints pins the required rubric,
scoring-profile id, validator version, and measured category set. Overall scores
that use three categories are not mixed with scores that also measure Realtime.
The block also reports exclusion counts and the selected category-set cohort, so
consumers can audit why `comparison_eligible_count` is smaller than `count` or
`agency_count`.

### Portable geography on aggregate endpoints

`accessibility.json`, `adoption.json`, and `realtime.json` each add a
`countries` array. Every country row carries `country_code`, `country_name`,
that endpoint's metric fields, and a nested `subdivisions` array. Subdivision
rows carry `subdivision_code` (null when unknown), `subdivision_name`, and the
same metric fields. An unknown subdivision is retained as `Unlocated`; it is
never inferred from an agency name.

Their existing `states` arrays remain U.S.-only compatibility views with the
same row shapes and metric meanings. New consumers should use `countries`.
Historical source records that omit `country` remain U.S. records by the v1
contract. The additive country rows do not change overall counts, scores,
bands, samples, or grades.

`problems.json` is intentionally the exception. Its aggregation input contains
only finding lists after agency identity has been removed, so a geographic
split would require guessing or changing the upstream contract. It remains a
covered-corpus prevalence view until identity-carrying inputs are available.

### Bulk table and SQL (`api/v1/agencies.parquet`)

For arbitrary filters and joins, the same covered-set table is published as Parquet
at `api/v1/agencies.parquet`. A DuckDB or Athena user queries it directly with no
server:

```sql
SELECT grade, count(*) FROM 'https://gtfsscorecard.org/api/v1/agencies.parquet'
GROUP BY grade ORDER BY grade;
```

The pipeline ships the same engine: `scorecard query "<sql>"` runs DuckDB over
the dataset locally (the table is named `agencies`), and `scorecard query
--export agencies.parquet` writes the file. Install the query extra first:
`pip install 'scorecard-pipeline[query]'`.

### Scaling

The static JSON serves the bounded cross-agency reads; the Parquet table serves
arbitrary SQL over the covered dataset, both from object storage with no query
server (ADR 0013). A managed database follows only if interactive multi-tenant
queries genuinely appear. The decision and trigger are in
`docs/decisions/0013-static-public-api.md`.

## Change feed (`changes/latest.json`)

For consumers that ingest transitions rather than diffing the whole catalog each
day. Lists active canonical feed records whose grade or score moved between two
checks under the same rubric, scoring profile, validator, and measured category
set. Records with unresolved duplicate identities are omitted. Regressions come
first, then the largest move.
`changes/<date>.json` is an immutable dated copy only when it carries the full
comparison contract. Pre-contract snapshots were withdrawn because their named
moves could not be audited against rubric, scoring-profile, validator, measured-
category, and canonical-identity boundaries.

```jsonc
{
  "schema_version": "1.14",
  "license": "CC-BY-4.0",
  "generated_at": "2026-06-20T13:25:01+00:00",
  "feed_record_count": 1128,
  "comparison_eligible_count": 1000,
  "comparison": {
    "eligible_count": 1000,
    "required_rubric_version": "1.2",
    "required_scoring_profile_id": "gtfs-scorecard-1.2",
    "required_validator_version": "8.0.1",
    "required_measured_categories": ["correctness", "freshness", "completeness"]
  },
  "count": 2,
  "changes": [
    { "id": "...", "name": "...", "from_grade": "B", "to_grade": "D",
      "from_score": 85.0, "to_score": 62.0, "score_delta": -23.0,
      "regressed": true, "since": "2026-06-18", "date": "2026-06-19" }
  ]
}
```

## Rollup shape (`rollups/<id>.json`)

```jsonc
{
  "schema_version": "1.14",
  "rollup": { "id": "california", "name": "California agencies" },
  "agency_count": 2,
  "average_score": 78.2,
  "grade_distribution": { "B": 1, "C": 1 },
  "comparison": { "eligible_count": 2, "excluded_count": 0,
                  "required_rubric_version": "1.2",
                  "required_scoring_profile_id": "gtfs-scorecard-1.2",
                  "required_validator_version": "8.0.1",
                  "required_measured_categories":
                    ["correctness", "freshness", "completeness"] },
  "state_percentile": null,
  "needs_attention": 1,
  "expired": { "lapsed": 1, "stale": 0, "total": 1 },
  "members": [ { "id": "...", "name": "...", "score": 0, "grade": "C",
                 "snapshot_date": "...", "needs_attention": true,
                 "days_until_expiry": -30, "expiry_status": "lapsed", "top_fix": "..." } ],
  "common_fixes": [ { "code": "...", "fix": "...", "agencies": 2 } ]
}
```

Members needing attention come first, ordered by rider impact when known and
then by name; other members are alphabetical. `average_score` and
`grade_distribution` use only the canonical, non-duplicate cohort under the
single rubric, scoring profile, validator, and measured-category set described
by `comparison`. `state_percentile` is retained as null for v1 compatibility.
`expired` counts the members whose feed
has run out, split into recently lapsed and long stale. `common_fixes` lists
fixes shared by more than one comparison-eligible member, so excluded legacy or
duplicate records cannot inflate a program-wide fix count.
`annual_trips` is `null` for every member when multiple feed records claim the
same NTD reporter id, so a reporter's rider count is never assigned twice or
used to break the worklist order ambiguously.

## Badge

`<agency>/badge.svg` is a self-contained SVG grade badge. Embed it as an image
that links back to the scorecard, using the canonical domain so it stays stable
for whoever embeds it:

```markdown
[![GTFS quality](https://gtfsscorecard.org/data/artifacts/yolobus/badge.svg)](https://gtfsscorecard.org/agency/yolobus/)
```

The badge regenerates each day with the rest of the artifacts, so it always
shows the current grade. Its accessible name is "GTFS quality: <grade> <score>".
When the feed has expired or is expiring, the badge appends a status segment
("feed expired" or "expires soon") and its accessible name gains the status in
parentheses, so a stale feed reads at a glance, not only by its letter.

`<agency>/badge.json` carries the same grade in the
[Shields.io endpoint format](https://shields.io/badges/endpoint-badge)
(`{ "schemaVersion": 1, "label": "GTFS quality", "message": "B 84.1", "color": "green" }`),
so a consumer can render a custom-styled badge:

```
https://img.shields.io/endpoint?url=https://gtfsscorecard.org/data/artifacts/yolobus/badge.json
```

## Gate a feed in CI

A feed-deployment repository can score a candidate feed before publishing and
fail the build on a low grade or an imminent expiry, using the same scoring the
site uses (no on-demand public endpoint; it runs in your own CI):

```bash
uvx --from gtfs-scorecard scorecard try "$FEED_URL" --country CA \
  --min-grade B --min-days-to-expiry 30
```

`--country` accepts an assigned ISO 3166-1 alpha-2 code and defaults to `US` so
existing commands retain their behavior. It is passed to the MobilityData
validator and written into the ad-hoc artifact. The command prints the grade,
category bars, and top fixes, and exits non-zero
when a threshold is not met. `--min-grade` and `--min-days-to-expiry` are
optional; with neither, it just reports.

## HTTP contract

- Served over HTTPS as `application/json` with `Access-Control-Allow-Origin: *`,
  so the artifacts are fetchable directly from a browser or an edge function.
- Dated artifacts (`<agency>/<date>.json`) are immutable once written and are
  retained, so a consumer can pin a specific date as a stable reference.
  `latest.json`, `catalog.json`, and `directory.json` are rewritten when a
  scoring run completes; `/api/v1/status.json` and `/api/v1/run-status.json`
  disclose the observed freshness and latest completed run.
- Each row's `retrieved_at` (and a scorecard's `generated_at`) is the authority
  on freshness; read it rather than re-fetching on a loop.

## Etiquette

The data is scheduled to refresh once a day. There is no value in polling it
more often than that, and the CDN caches for a few minutes regardless.
Consumers should read `generated_at`/`retrieved_at` and the status endpoints
rather than assuming the schedule completed or re-fetching on a tight loop.
