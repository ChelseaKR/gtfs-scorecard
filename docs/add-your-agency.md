# Add your agency in 10 minutes

The scorecard tracks any agency listed in [`agencies.yaml`](../agencies.yaml)
at the repository root. Adding yours is one YAML block and a pull request;
no code changes.

## Preview first, no commitment

Want to see your grade before adding anything? Score any GTFS Schedule zip
on the spot, without registering or publishing it:

```sh
cd pipeline
uv run scorecard try https://example.org/gtfs/google_transit.zip \
  --country CA --name "My Agency"
```

Pass the feed's assigned ISO 3166-1 alpha-2 country so country-sensitive
validator rules use the right jurisdiction; `--country` defaults to `US` for
compatibility. The command prints the overall grade, the score in each category, and the top things
to fix. Add `--html scorecard.html` to also write a standalone page you can
open in a browser. Nothing is uploaded; the download stays in your local
cache.

## What you need

- A direct link to your GTFS Schedule zip. If you don't know it, search
  your agency on the [Mobility Database](https://mobilitydatabase.org) or
  [transit.land](https://www.transit.land), or ask whoever runs your
  scheduling software export.
- Optional: your GTFS-Realtime endpoint URLs (trip updates, vehicle
  positions, service alerts), if they are published without an API key.

## Steps

1. Fork this repository and open `agencies.yaml`.
2. Copy an existing block and fill in your values:

   ```yaml
   - id: my-agency            # lowercase slug, used in URLs and file paths
     name: My Agency Transit  # shown on the scorecard
     country: CA              # assigned ISO 3166-1 alpha-2 code
     subdivision_code: CA-ON  # ISO 3166-2 province, territory, or state code
     subdivision_name: Ontario
     static_gtfs_url: https://example.org/gtfs/google_transit.zip
     license_note: CC-BY 4.0  # or where the license question stands
     rt_urls:                 # omit this whole section if not applicable
       trip_updates: https://example.org/rt/TripUpdates.pb
       vehicle_positions: https://example.org/rt/VehiclePositions.pb
       service_alerts: https://example.org/rt/ServiceAlerts.pb
   ```

   State `country` on every new entry. Its legacy default is `US` only so older
   registry records keep working. Use the full assigned ISO 3166-2 code, such as
   `CA-ON`, and the canonical subdivision name. All 249 assigned countries and
   their ISO subdivisions are accepted without a country-specific code change;
   malformed, unassigned, cross-country, and unknown codes are rejected. If a
   subdivision name is ambiguous, the code is required. The first production
   feed in a country follows the coverage checks in
   [ADR 0026](decisions/0026-internationalization.md#global-iso-vocabulary-and-coverage-checklist).
   New integrations should use the portable fields for location and grouping.
   The published `state` field remains available for existing US consumers.

   If your agency has realtime tracking but the feed needs an API key,
   omit `rt_urls` and add an `rt_note` saying so; the scorecard shows the
   note neutrally instead of a score.

   If your service is seasonal or demand-response (deliberate calendar gaps),
   add `service_type: seasonal` or `service_type: demand_response`, so a
   between-seasons lapse is scored fairly rather than as a silently expired
   feed. The default is `fixed` (year-round service).

   If your agency is fare-free by policy, add `fare_free: true`. Your feed
   carries no fare files by design, so the scorecard credits that part of the
   score instead of docking it and shows a neutral note. Leave it off (the
   default) if you charge a fare.

3. Check your work locally if you like (needs Python 3.11+,
   [uv](https://docs.astral.sh/uv/), and Java 17+):

   ```sh
   cd pipeline
   uv sync
   uv run scorecard run --agency my-agency
   ```

   A bad URL or typo'd field fails immediately with a plain message. The
   command prints the path of your scorecard JSON; to see the page, serve
   the repo root (`python3 -m http.server`) and open
   `http://localhost:8000/web/#/agency/my-agency`.

4. Open a pull request with the one-file change. After merge, the daily
   pipeline scores your feed each morning and your agency appears on the
   live site.

## Notes

- Scoring methodology, with citations, is in [rubric.md](rubric.md).
  Findings are framed as fixes; nothing here is a compliance report.
- The pipeline fetches your static feed once per day and, if you list
  realtime URLs, samples them a few times per run at least 30 seconds
  apart. Tell us if your endpoints need gentler treatment.
- Realtime scoring needs keyless endpoints today. If your vendor requires
  a key, open an issue; per-agency keys are on the roadmap.
