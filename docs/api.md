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
| `index.json` | Every agency with its score/grade history. Powers the picker and trends. |
| `directory.json` | Slim national directory: per-agency grade, state, size tier, percentiles, plus a national and per-state summary. |
| `changes/latest.json` | Agencies whose grade or score moved since their last check (a daily transition feed). Immutable dated copy at `changes/<date>.json`. |
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
| `/schemas/artifact.schema.json`, `/schemas/catalog.schema.json`, `/schemas/directory.schema.json` | JSON Schemas (Draft 2020-12) for validating the per-agency artifact, the catalog, and the directory in CI. |

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

## Versioning

Every artifact carries a `schema_version` (currently `1.5`). The rule for
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

The flat analysis exports (`dataset.json`, `dataset.csv`,
`api/v1/agencies.parquet`) carry two version fields: `schema_version` is the
version of the flat export's own shape, and `pipeline_schema_version` is the
artifact schema (the `1.x` documented here) the export was derived from. A
citation should pin the release tag, which fixes both.

For citation, do not cite the live site: it changes daily. A monthly
`dataset-YYYY-MM` release (the `Dataset release` workflow) pins the flat
exports, the parquet file, the NTD rollup, this data dictionary, and
`CITATION.cff` to an immutable tag, so a paper's reference resolves to exactly
the bytes analysed. Releases:
<https://github.com/ChelseaKR/gtfs-scorecard/releases>.

Changelog:

- `1.5` adds a `confidence` block to every scorecard: a `level`
  (`provisional`, `medium`, or `high`) reading how much of the grade this run
  could measure, plus the measured category count, fetch source, realtime
  sampling depth, and snapshot age behind it. A legibility layer on the one
  grade, never a second grade. Additive.
- `1.4` carries identity and provenance on every catalog and directory row
  (`mdb_id`, `validator_version`, `rubric_version`, `retrieved_at`,
  `feed_sha256`) and a `license`/`attribution` on the catalog and directory
  documents. Additive.
- `1.3` exposed the freshness fields described below (`days_until_expiry` in
  index history, `expiry_status` in the catalog and rollup members). Additive.

## Scorecard shape (`latest.json`, `<date>.json`)

```jsonc
{
  "schema_version": "1.5",
  "rubric_version": "1.1",
  "validator_version": "8.0.1",       // the MobilityData gtfs-validator release used
  "agency": { "id": "yolobus", "name": "Yolobus (...)",
              "operating_note": "optional curator-verified status; absent if unset" },
  "generated_at": "2026-06-12T13:25:01+00:00",   // when this grade was produced (retrieved_at in the catalog)
  "snapshot_date": "2026-06-12",
  "feed": { "static_url": "...", "sha256": "...", "size_bytes": 0, "license_note": "..." },
  "overall": { "score": 84.1, "grade": "B",
               // distance to the grade-band edges: points up to the next letter's
               // floor (null for an A) and points above this band's own floor
               "margin_to_next_band": 5.9, "margin_to_lower_band": 4.1 },
  "fetch": { "source": "origin",      // or "mirror" (MobilityData hosted copy); "unknown" for
                                      // snapshots downloaded before provenance recording
             "final_url": "...",      // the URL that actually served the graded bytes
             "user_agent": "...",     // the User-Agent presented to that server
             "max_attempts": 4,       // configured attempt ceiling; omitted when unknown
             "origin_error": "..." }, // exception that forced the mirror; only on mirror fetches
  "confidence": { "level": "high",          // "provisional", "medium", or "high" — a word, never a letter or a number
                  "measured_categories": 4, "total_categories": 4,
                  "fetch_source": "origin", "rt_windows": 1, "feed_age_days": 0,
                  "notes": [ "All four score categories were measured this run.", "..." ] },
  "overall": { "score": 84.1, "grade": "B" },
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
panel. Absent on artifacts published before schema 1.5. Additive within schema
1.5.

## Freshness fields

The `freshness` category's `details` carry the feed's validity window, and two
fields are surfaced for consumers:

- `details.days_until_expiry` (integer, or `null` when the feed states no end
  date): days until the feed's service window closes. Negative means it already
  expired that many days ago. Also copied onto each `index.json` history point.
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

One document listing every agency, for consumers that want the whole picture in
a single request rather than fetching each `latest.json`.

```jsonc
{
  "source": "https://gtfsscorecard.org",
  "schema_version": "1.5",
  "rubric_version": "1.1",
  "license": "CC-BY-4.0",
  "attribution": "GTFS Scorecard (gtfsscorecard.org), scored on top of the MobilityData gtfs-validator",
  "agencies": [
    { "id": "yolobus", "name": "Yolobus (...)", "state": "California", "grade": "B", "score": 84.1,
      "size_tier": "small", "national_percentile": 72, "peer_percentile": 80,
      "snapshot_date": "2026-06-12", "days_until_expiry": 120, "expiry_status": "current",
      "ntd_ready": "ready", "google_gate": "pass", "stops": 312,
      "mdb_id": "1234", "validator_version": "8.0.1", "rubric_version": "1.1",
      "retrieved_at": "2026-06-12T13:25:01+00:00", "feed_sha256": "...",
      "feed_url": "...", "top_fix": "...", "scorecard_url": "https://..." }
  ]
}
```

`catalog.csv` carries the key columns (including `mdb_id` and
`validator_version`). Use `mdb_id` to join a row to the Mobility Database rather
than matching on the scorecard's own slug or on the feed URL.

Three readiness fields ride on every catalog and directory row and are worth
consuming directly rather than re-deriving:

- `ntd_ready` (string): readiness for the FTA NTD GTFS requirement, rolled up
  from the published/valid/current pillars. One of `ready` (all three pillars
  hold), `at_risk` (a recoverable gap: validator errors, or service running
  out soon), `not_ready` (unreachable, lapsed, or no readable end date). A
  data-quality heads-up, never an official determination; the agency's own
  D-10 certification is the official one.
- `google_gate` (string): whether the feed clears the Google/Apple Maps
  four-week service-coverage bar. One of `pass` (four or more weeks of service
  ahead), `at_risk` (under four weeks), `fail` (expired).
- `stops` (integer or null): boardable stop count read from the feed's
  stops.txt, a rough size signal alongside `size_tier`.
- `country` (string): ISO 3166-1 alpha-2 code, `US` or `CA`. Canadian
  agencies carry no US state; group them by this field instead of treating
  an empty state as unlocated.

## Directory (`directory.json`)

The national document the web app's overview reads: one record per agency with
the same fields as a catalog row (identity, grade, freshness, readiness,
provenance, size tier, and percentiles) plus a `summary` block with the
national grade distribution, expiring and expired counts, median score, a
per-state rollup, and size-tier counts. It carries the same `license` and
`attribution` as the catalog. Prefer it over `index.json` when you want the
current national picture without the full per-agency history.

## Versioned cross-agency API (`api/v1/`)

The paths above are per-agency or whole-catalog. The `api/v1/` endpoints add the
cross-agency views a state program or app developer asks for, as small flat JSON
files under a versioned path. `v1` is a stability contract: fields may be added,
but existing fields keep their meaning and type, and a breaking change lands at
`api/v2`. Built from the same index, so the numbers match the pages (ADR 0013).

| Path | What it is |
| --- | --- |
| `api/v1/index.json` | The API's self-description: version, endpoint list, license, attribution. |
| `api/v1/agencies.json` | Every agency's latest check in one list (id, name, date, grade, score, the four category scores, days to expiry). `realtime` is null when not published. |
| `api/v1/leaderboard.json` | `top` and `bottom` by score, and `most_improved` / `most_declined` by the change since each agency's previous check. |
| `api/v1/by-state.json` | Per-state agency count, median score, and grade distribution. Agencies without a known state group under `Unlocated`. |
| `api/v1/stats.json` | National count, average and median score, grade distribution, and the share of feeds not expired. |
| `api/v1/equity.json` | Per-state ACS need tiers (poverty, zero-vehicle, disability) joined to agency grades, with the high-need states that carry many low-grade feeds. Refreshed weekly from Census ACS. |
| `api/v1/ids.json` | Identity crosswalk: every agency's scorecard slug joined to its Mobility Database id, NTD id, and feed URL, so grades join to either registry (or FTA data) without fuzzy matching. |
| `api/v1/ridership-impact.json` | National quality weighted by NTD annual rider-trips (ADR 0021): trips covered, trips by grade, and the share of trips on expired feeds, with the matched coverage stated. Present when the daily run's NTD fetch succeeded. |

Per-agency detail stays the published artifact (`<agency>/latest.json`); the API
does not duplicate it. The human standings render on
[the national pulse](https://gtfsscorecard.org/pulse/).

### Bulk table and SQL (`api/v1/agencies.parquet`)

For arbitrary filters and joins, the same national table is published as Parquet
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
arbitrary SQL over the national dataset, both from object storage with no query
server (ADR 0013). A managed database follows only if interactive multi-tenant
queries genuinely appear. The decision and trigger are in
`docs/decisions/0013-static-public-api.md`.

## Change feed (`changes/latest.json`)

For consumers that ingest transitions rather than diffing the whole catalog each
day. Lists every agency whose grade or score moved between its two most recent
checks, regressions first, then largest move. `changes/<date>.json` is an
immutable dated copy.

```jsonc
{
  "schema_version": "1.5",
  "license": "CC-BY-4.0",
  "generated_at": "2026-06-20T13:25:01+00:00",
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
  "schema_version": "1.5",
  "rollup": { "id": "california", "name": "California agencies" },
  "agency_count": 2,
  "average_score": 78.2,
  "grade_distribution": { "B": 1, "C": 1 },
  "needs_attention": 1,
  "expired": { "lapsed": 1, "stale": 0, "total": 1 },
  "members": [ { "id": "...", "name": "...", "score": 0, "grade": "C",
                 "snapshot_date": "...", "needs_attention": true,
                 "days_until_expiry": -30, "expiry_status": "lapsed", "top_fix": "..." } ],
  "common_fixes": [ { "code": "...", "fix": "...", "agencies": 2 } ]
}
```

Members are sorted worst-score-first. `expired` counts the members whose feed
has run out, split into recently lapsed and long stale. `common_fixes` lists
fixes shared by more than one member, so a program can see the one change that
lifts several feeds.

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
uvx --from gtfs-scorecard scorecard try "$FEED_URL" \
  --min-grade B --min-days-to-expiry 30
```

The command prints the grade, category bars, and top fixes, and exits non-zero
when a threshold is not met. `--min-grade` and `--min-days-to-expiry` are
optional; with neither, it just reports.

## HTTP contract

- Served over HTTPS as `application/json` with `Access-Control-Allow-Origin: *`,
  so the artifacts are fetchable directly from a browser or an edge function.
- Dated artifacts (`<agency>/<date>.json`) are immutable once written and are
  retained, so a consumer can pin a specific date as a stable reference.
  `latest.json`, `catalog.json`, and `directory.json` are rewritten daily.
- Each row's `retrieved_at` (and a scorecard's `generated_at`) is the authority
  on freshness; read it rather than re-fetching on a loop.

## Etiquette

The data refreshes once a day. There is no value in polling it more often than
that, and the CDN caches for a few minutes regardless. Consumers should read
`generated_at`/`retrieved_at` rather than re-fetching on a tight loop.
