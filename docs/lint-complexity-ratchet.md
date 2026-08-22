# Complexity ratchet (CODE-QUALITY-STANDARD CQ-05)

**Opened:** 2026-07-05, as part of QW-5 (widen ruff `select` to the canonical
set, including `C90` with `max-complexity = 10`).

## Why this file exists

Turning on `C90` (mccabe complexity) against the real codebase surfaced
functions already over the standard's `max-complexity = 10` floor. Refactoring
them all to comply is genuine multi-function engineering work (some are 3-5x
the floor), not a same-day fix, so it cannot block landing the rest of QW-5
(the `E`/`W`/`F`/`I`/`UP`/`B`/`SIM`/`S`/`RUF` selection, which is now fully
enabled and clean). Per the remediation ground rules, the honest path is:
enable the gate for real, **not silence it**, and track the pre-existing
debt explicitly here with a dated, visible `# noqa: C901` at each site
pointing back to this file — rather than leaving `C90` out of `select`
(which would let the audit's FAIL stand unchanged) or leaving CI red.

**Last synced:** 2026-08-22, when `realtime` came off the table. Every row
below was regenerated from
`uv run ruff check --select C901 --ignore-noqa --output-format concise src`,
so the file:line and the number are what ruff prints today, not what it printed
when the row was written. Four rows had drifted since the 2026-08-15 sync:
`completeness` had gone from 13 to 15, and `render_site`,
`propose_agencies_with_dispositions` and `_cmd_liveness` had all moved line.
Re-run that command and rewrite this table whenever a row changes — including
when removing one, since the removal shifts lines in the same file.

The 2026-08-15 sync (issue #249) is what established the practice, after the
table had drifted a long way: two entries had been refactored under the floor
and were still listed, one had been renamed, one had moved module, four live
suppressions had no row at all, and 13 of the 15 recorded complexity numbers
were wrong.

**Rule:** no new `# noqa: C901` may be added without a row below. Existing
rows are debt, not precedent — do not point to this file to justify a new one
without discussion.

## Tracked exceptions

| Function | File:line | Complexity | Note |
|---|---|---|---|
| `render_site` | `src/scorecard_pipeline/render_site.py:9996` | 54 | Top-level orchestrator calling every page renderer in sequence; the biggest single item here — candidate: split into `render_site` (thin driver) plus a registry of `(route, render_fn)` pairs. |
| `parse_agencies` | `src/scorecard_pipeline/agencies.py:171` | 36 | Config-parsing fan-out over many optional YAML fields; candidate: split per-field validators. |
| `propose_agencies_with_dispositions` | `src/scorecard_pipeline/mobilitydb.py:666` | 32 | Mobility Database matching heuristics; candidate: extract match-scoring helper. Was tracked as `propose_agencies`, which is now a thin wrapper at `mobilitydb.py:909` with no suppression. |
| `render_digest` | `src/scorecard_pipeline/alerts.py:421` | 17 | Digest section assembly; candidate: extract one function per digest section. |
| `_render_brief` | `src/scorecard_pipeline/render_site.py:3029` | 16 | Template string assembly. |
| `completeness` | `src/scorecard_pipeline/completeness.py:209` | 15 | Rider-experience field scoring; candidate: extract per-field scorers. |
| `parse_subscribers` | `src/scorecard_pipeline/notify.py:87` | 15 | Subscriber YAML parsing and validation; candidate: split per-field validators (same shape as `parse_agencies`). |
| `build_digest` | `src/scorecard_pipeline/alerts.py:343` | 14 | Alert digest construction. Was suppressed with a bare `# noqa: C901` and no row; both fixed here. |
| `parse_ridership_csv` | `src/scorecard_pipeline/ridership.py:58` | 14 | CSV column-mapping heuristics; candidate: extract per-column parsers. |
| `_cmd_liveness` | `src/scorecard_pipeline/cli.py:2582` | 13 | CLI subcommand with several independent check branches; candidate: table-driven checks. |
| `_render_agency` | `src/scorecard_pipeline/render_site.py:2611` | 13 | Template string assembly. Its suppression pointed at this file and had no row; added here. |
| `route_type_family` | `src/scorecard_pipeline/modes.py:48` | 13 | GTFS route-type classification. Moved here from `route_geometry.py`, which now keeps a two-line wrapper with no suppression. Its `# noqa` carries its own rationale ("explicit spec range mapping") rather than pointing at this file; that is a deliberate permanent exemption, listed so the count reconciles. |
| `_board_hero` | `src/scorecard_pipeline/render_site.py:1114` | 12 | Template string assembly with several conditional blocks. |
| `compute_drift` | `src/scorecard_pipeline/rt_drift.py:96` | 12 | Schedule-vs-RT drift computation; candidate: extract per-window drift helper. |
| `run_agency` | `src/scorecard_pipeline/cli.py:170` | 12 | Per-agency run driver. Was suppressed with a bare `# noqa: C901` and no row; both fixed here. |

Fifteen sites, sorted by how far over the floor they sit. Three rows that used
to be here are gone because the functions are now under the floor:
`_md_to_html` (`render_site.py:5182`), `_render_agency_index`
(`render_site.py:4445`), and `realtime` (`rt.py`, was 29, issue #250). None of
them carries a suppression any more.

## Plan

Ratchet down opportunistically: when touching any function above for a
feature/bugfix, refactor it under the threshold and delete its row rather
than editing around it. `render_site` (54), `parse_agencies` (36) and
`propose_agencies_with_dispositions` (32) are the highest-value targets given
how far over the floor they sit. Re-run
`ruff check --statistics` after each removal to confirm the count only goes
down. Tracked in the issue tracker: #250 covered `realtime` and is resolved by
the row's removal above; #249 covered the drift the 2026-08-15 sync resolved.

`realtime` is the worked example for the rest of this table. It came down from
29 to 3 by extracting one helper per scored component (`_reachability`,
`_freshness`, `_alerts`, `_trip_coverage`, `_plausibility_component`,
`_drift_component`) plus `_assessed_kinds` and `_realtime_summary`, leaving
`realtime` itself as a thin driver that calls each one and assembles the
result. No helper is over the floor; the largest is `_freshness` at 9. The
scoring is unchanged, which was checked by running the old and new
implementations over 27,232 generated input combinations and diffing the score,
summary, findings, and the `details` dict in key order: byte-for-byte identical.
