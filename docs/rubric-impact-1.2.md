# Rubric 1.2 impact: partial GTFS-Realtime feeds

Rubric 1.2 corrects how the Realtime category treats an agency that publishes
only some GTFS-Realtime feed kinds. A feed kind absent from the agency registry
is now neutral instead of being treated as an outage. TripUpdates coverage is
scored only when TripUpdates is configured, and vehicle-position plausibility
is scored only when VehiclePositions is configured.

This is a projected impact report, not a rescore. It was produced on 2026-07-13
from the public `latest.json` artifacts and the feed kinds in `agencies.yaml`.
The registry contained 32 partial realtime configurations. Thirty-one had a
published, measured Realtime category; Denton County Transportation Authority
had no public latest artifact and was excluded.

## Result

- Median Realtime category change: **+16.7 points**.
- Median overall-score change: **+3.3 points**.
- Projected letter-band changes: **15 of 31 artifacts**.
- Projected downward letter-band changes: **0**.

| Before | After | Artifacts |
|---|---|---:|
| B | B | 2 |
| C | A | 1 |
| C | B | 3 |
| C | C | 3 |
| D | B | 4 |
| D | C | 2 |
| D | D | 2 |
| F | C | 2 |
| F | D | 3 |
| F | F | 9 |

The projected band movers were:

| Agency id | Band | Realtime | Overall | Configured kinds |
|---|---|---:|---:|---|
| `basmy-kangar` | F → D | 47.2 → 98.2 | 52.6 → 62.8 | VehiclePositions |
| `humboldt-transit-authority` | C → A | 13.9 → 100.0 | 78.2 → 95.5 | ServiceAlerts |
| `madera-county-transit` | C → B | 33.3 → 100.0 | 73.8 → 87.1 | ServiceAlerts |
| `metrolink` | D → B | 13.9 → 100.0 | 67.1 → 84.3 | ServiceAlerts |
| `thousand-oaks-transit` | C → B | 33.3 → 100.0 | 72.6 → 85.9 | ServiceAlerts |
| `bay-area-rapid-transit-bart` | F → D | 84.2 → 94.0 | 59.1 → 61.1 | ServiceAlerts, TripUpdates |
| `benton-area-transportation` | D → B | 13.9 → 100.0 | 70.0 → 87.2 | ServiceAlerts |
| `washington-park-shuttle` | F → C | 33.3 → 100.0 | 57.5 → 70.8 | ServiceAlerts |
| `charleston-area-regional-transportation-authority-carta` | F → C | 13.9 → 100.0 | 58.9 → 76.1 | ServiceAlerts |
| `metropolitan-transit-authority-mta` | D → B | 13.9 → 100.0 | 64.0 → 81.2 | ServiceAlerts |
| `metropolitan-transit-authority-mta-510` | D → C | 33.3 → 100.0 | 61.2 → 74.5 | ServiceAlerts |
| `metropolitan-transit-authority-mta-516` | D → B | 13.9 → 100.0 | 64.2 → 81.4 | ServiceAlerts |
| `nassau-inter-county-express-nice-bus` | F → D | 13.9 → 100.0 | 46.1 → 63.4 | ServiceAlerts |
| `rochester-genesee-regional-transportation-authority-rgrta` | D → C | 47.6 → 98.9 | 60.9 → 71.2 | VehiclePositions |
| `el-paso-transportation-authority` | C → B | 83.3 → 100.0 | 77.7 → 81.1 | TripUpdates, VehiclePositions |

## Replay method and limits

The evaluated set was selected mechanically: registry entries with one or two
nonempty `rt_urls` keys and a published Realtime category marked `measured`.
For each artifact, the replay:

1. Counted a configured kind as reachable when its existing
   `scorecard_rt_<kind>_unreachable` finding was absent.
2. Reused `worst_lag_seconds` with the published 60-second full-credit and
   600-second zero-credit interpolation, but only when TripUpdates or
   VehiclePositions was configured.
3. Included `coverage_pct` only for a configured TripUpdates feed and
   `vehicles_on_route_pct` only for a configured VehiclePositions feed.
4. Renormalized the measurable Realtime weights (25 reachability, 25 freshness,
   35 trip coverage, 15 position plausibility), replaced that category score,
   and recomputed the overall score with the published category weights and
   grade bands.

The public details are rounded, and this replay did not fetch new protobufs or
re-run route-shape analysis. The values above therefore estimate the
methodology discontinuity on a fixed published corpus. Published details also
cannot distinguish an endpoint whose every sample failed from one with a mix
of successful and failed samples. The live scorer drops TripUpdates coverage
when no sample succeeded, avoiding a second deduction for the same outage; the
replay retained the published coverage value. The first rubric 1.2 sampling
run remains the authoritative new score and may differ as live data changes.
