# Complexity ratchet (CODE-QUALITY-STANDARD CQ-05)

**Opened:** 2026-07-05, as part of QW-5 (widen ruff `select` to the canonical
set, including `C90` with `max-complexity = 10`).

## Why this file exists

Turning on `C90` (mccabe complexity) against the real codebase surfaces 16
functions already over the standard's `max-complexity = 10` floor. Refactoring
all 16 to comply is genuine multi-function engineering work (some are 2-3x
the floor), not a same-day fix, so it cannot block landing the rest of QW-5
(the `E`/`W`/`F`/`I`/`UP`/`B`/`SIM`/`S`/`RUF` selection, which is now fully
enabled and clean). Per the remediation ground rules, the honest path is:
enable the gate for real, **not silence it**, and track the pre-existing
debt explicitly here with a dated, visible `# noqa: C901` at each site
pointing back to this file — rather than leaving `C90` out of `select`
(which would let the audit's FAIL stand unchanged) or leaving CI red.

**Rule:** no new `# noqa: C901` may be added without a row below. Existing
rows are debt, not precedent — do not point to this file to justify a new one
without discussion.

## Tracked exceptions

| Function | File:line | Complexity | Note |
|---|---|---|---|
| `parse_agencies` | `src/scorecard_pipeline/agencies.py:41` | 16 | Config-parsing fan-out over many optional YAML fields; candidate: split per-field validators. |
| `render_digest` | `src/scorecard_pipeline/alerts.py:269` | 12 | Digest section assembly; candidate: extract one function per digest section. |
| `_cmd_liveness` | `src/scorecard_pipeline/cli.py:1360` | 12 | CLI subcommand with several independent check branches; candidate: table-driven checks. |
| `completeness` | `src/scorecard_pipeline/completeness.py:51` | 11 | Rider-experience field scoring; candidate: extract per-field scorers. |
| `propose_agencies` | `src/scorecard_pipeline/mobilitydb.py:183` | 12 | Mobility Database matching heuristics; candidate: extract match-scoring helper. |
| `parse_subscribers` | `src/scorecard_pipeline/notify.py:86` | 15 | Subscriber YAML parsing/validation; candidate: split per-field validators (same shape as `parse_agencies`). |
| `leaderboard` | `src/scorecard_pipeline/publicapi.py:53` | 11 | Ranking/filter assembly; candidate: extract filter-predicate builder. |
| `_board_hero` | `src/scorecard_pipeline/render_site.py:583` | 11 | Template string assembly with several conditional blocks. |
| `_render_brief` | `src/scorecard_pipeline/render_site.py:1654` | 14 | Template string assembly. |
| `_render_agency_index` | `src/scorecard_pipeline/render_site.py:2926` | 12 | Template string assembly. |
| `_md_to_html` | `src/scorecard_pipeline/render_site.py:3350` | 15 | Hand-rolled Markdown-subset renderer; candidate: dispatch table per block type. |
| `render_site` | `src/scorecard_pipeline/render_site.py:6014` | 37 | Top-level orchestrator calling every page renderer in sequence; the biggest single item here — candidate: split into `render_site` (thin driver) + a registry of `(route, render_fn)` pairs. |
| `parse_ridership_csv` | `src/scorecard_pipeline/ridership.py:56` | 14 | CSV column-mapping heuristics; candidate: extract per-column parsers. |
| `_route_type_family` | `src/scorecard_pipeline/route_geometry.py:102` | 14 | GTFS route-type classification; candidate: replace if/elif ladder with a lookup table. |
| `realtime` | `src/scorecard_pipeline/rt.py:309` | 21 | Realtime category scoring; candidate: extract per-subscore helpers (mirrors `completeness`). |
| `compute_drift` | `src/scorecard_pipeline/rt_drift.py:83` | 13 | Schedule-vs-RT drift computation; candidate: extract per-window drift helper. |

## Plan

Ratchet down opportunistically: when touching any function above for a
feature/bugfix, refactor it under the threshold and delete its row rather
than editing around it. `render_site` (37) and `rt.py::realtime` (21) are the
highest-value targets given how far over the floor they are. Re-run
`ruff check --statistics` after each removal to confirm the count only goes
down. Track as a P1/CQ-05 follow-up in the real issue tracker (a GitHub issue
was not opened by this remediation pass — write-effect issue creation was
out of scope for an automated pass; a human should open one referencing this
file).
