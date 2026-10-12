# ADR 0068: Repair the trend's history, and rescore earlier records from stored data

**Status:** Accepted (2026-10-12)

## Context

On 2026-10-12 the public "Is transit data getting better?" trend
(`/pulse/#trend`, `api/v1/trend.json`) had two points, 2026-10-11 and
2026-10-12, although the dated store held daily records for every feed since
June.

Two separate things were behind it.

1. **index.json had lost its history.** `publish._update_index` rebuilt an
   agency's history from the dated files in the local checkout. A CI checkout
   holds only the committed cutover snapshot plus whatever a workflow hydrated
   (the intraday refresh hydrates today and yesterday). Every intraday
   re-score and every freshness sweep goes through `publish()`, so each one
   dropped every row whose record lived only in S3. `rebuild_index` already
   kept those rows; the incremental path did not. Measured on the S3 index of
   2026-10-12 04:34 UTC: each feed kept 2026-06-11 to 2026-07-10 and
   2026-08-06 to 2026-08-07 (the cutover files in git) plus the last two days.
   With the rows in between gone, the newest older row (for most feeds the
   2026-08-07 rubric 1.3 row) ended each feed's current-contract suffix, so
   the trend began at 2026-10-11.
2. **Each rubric release restarts the trend by design** (ADR 0020, ADR 0051,
   `comparisons.current_producer_contract_suffix`). Rubric 1.4 took effect on
   2026-10-02, so even a complete index gives a native series of 11 days.

## Decision

- `publish._update_index` and `rebuild_index` share
  `merge_index_history`: a prior index row survives when its date has no
  local dated file. A local readable record still wins for its date, and an
  unreadable local file is still dropped.
- `scorecard backfill-index-history --mirror DIR` restores missing rows from a
  local copy of the dated records. It never replaces a row, never adds one
  after a feed's index tail, and accepts a file only when its path date,
  `snapshot_date`, and agency id agree. Each row is exactly what
  `_history_entry` writes on publish.
- `scorecard rescore-history --mirror DIR` (`rescore_history.py`) rescores
  earlier-rubric records under the current rubric from what each record
  stores. Correctness and freshness are recomputed with the current code from
  the stored notice groups and feed dates. Rider-experience completeness is
  carried only where rubric 1.3 and 1.4 cannot move it (stops and trips
  present, no missing-headsign finding) or taken from a native 1.4 record of
  the same feed bytes. Realtime is carried from rubric 1.2 or later. Every
  other record is counted by reason and contributes no number. The output is a
  separate derived file, `data/artifacts/rescored-history.json`; dated records
  are never rewritten.
- The trend publishes the rescored series beside the native one
  (`trend.json` `rescored`, additive). It is merged into the chart only when
  rescoring every native 1.4 record reproduces it exactly. Otherwise it is
  shown apart and labeled. It follows a fixed panel (the feeds with a
  comparable score on the window's first date), because inside the window the
  cohort grows by up to a fifth and new feeds would otherwise move the average
  without any feed changing.
- `trend-history-repair.yml` (dispatch-only, dry run by default, holds the
  `artifacts-publish` lock) runs both commands against the store and uploads
  the two derived files.

## Measured result (local run over the store, 2026-10-12)

- Backfill: 173,581 rows restored across 2,474 feed records.
- Native series: 11 points, 2026-10-02 to 2026-10-12.
- Rescore: 150,629 records rescored, 25,158 not. The largest gap is 22,184
  records from 393 feeds that lacked some `trip_headsign`; rubric 1.3 and 1.4
  can change their completeness, and only the feed bytes can say by how much.
- Control: of 26,787 native 1.4 records, 25,695 reproduce exactly. Every
  category score matches; the overall differs by 0.1 on the rest, because
  stored category scores are rounded to one decimal. The national average of
  the rescored native records equals the published average to one decimal on
  all 11 native dates. Because the record-level check is not exact, the
  rescored series is shown apart.

## Consequences

- The intraday refresh no longer erodes the index. The repair itself needs one
  operator run of `trend-history-repair.yml` with `write: true`.
- The 80% coverage rule (ADR 0020) still limits the rescored series to dates
  when the comparable cohort was near full size.
- Not done here: scoring the 22,184 missing-headsign records from the archived
  feed bytes. A 12-version sample reproduced 12 of 12 native completeness
  scores from the archive, so the method works; the full pass is 4,655
  archived versions (51.6 GB), and 1,935 versions were never archived.
