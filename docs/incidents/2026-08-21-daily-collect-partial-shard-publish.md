# Daily scorecard silently skipped four consecutive publishes

**Status:** Reopened 2026-08-26, see "Recurrence" at the end
**Issue:** [#297](https://github.com/ChelseaKR/gtfs-scorecard/issues/297)
**Severity:** SEV3 (public data went stale for up to a day at a time; the live
site never served an error, and Intraday refresh kept most of the corpus
current throughout)

## Summary

`scorecard.yml`'s `collect` job depended on `score` with no `if:` guard, which
defaults to `if: success()`. One score shard was repeatedly killed by the
Actions runner itself (not a normal job failure) while validating
`ovapi-netherlands`, a large national feed. Every time that happened, `collect`
and `deploy` were skipped outright — even though the other 31 shards had
scored cleanly — and the day's Daily publish never happened. This recurred on
the `00/06/12/18` UTC cadence-tier cycle for four consecutive scheduled days,
2026-08-17 through 2026-08-20.

`Watchdog`'s own alert was independently wrong during this window: it checked
`scorecard.yml`'s (Daily-only) run history and reported "the published data is
going stale," but `Intraday refresh` (a separate, 3-hourly workflow) kept
deploying successfully the entire time, so the live site's data was in fact
current.

## Timeline (UTC, from Actions run history)

| Date | Event |
|---|---|
| 2026-08-17 | Daily scorecard run lost to a `setup-uv` 429 rate-limit on one shard; `collect`/`deploy` skipped (same `needs: score` gap, different trigger) |
| 2026-08-18 – 2026-08-20 | Daily scorecard run killed validating `ovapi-netherlands` on the `00/06/12/18` UTC cadence-tier cycle, three days running; `collect`/`deploy` skipped each time |
| 2026-08-21 13:36 | First diagnostic pass (a separate session) roots the pattern to the `collect` job's missing `if:` guard; confirms `ovapi-netherlands` both passed and failed under identical settings on other cycles, refuting a simple "feed too big" theory |
| 2026-08-21 16:44 | [#298](https://github.com/ChelseaKR/gtfs-scorecard/pull/298) merged: `collect: if: !cancelled()` plus a zero-shard publish floor, `timeout-minutes` on `score`/`collect`/`refresh`, an opt-in `prlimit`-based memory ceiling for the validator subprocess, a real Watchdog freshness check, and the SEO-retention masking fix |
| 2026-08-21 16:45 – 17:38 | Follow-up fixes: [#299](https://github.com/ChelseaKR/gtfs-scorecard/pull/299) (an env-var edge case caught live-dispatching the diagnostic below), [#300](https://github.com/ChelseaKR/gtfs-scorecard/pull/300) ([#286](https://github.com/ChelseaKR/gtfs-scorecard/issues/286), unrelated but landed the same session), [#301](https://github.com/ChelseaKR/gtfs-scorecard/pull/301)–[#304](https://github.com/ChelseaKR/gtfs-scorecard/pull/304) (CI/security follow-ups, unrelated to this incident) |
| 2026-08-21 17:21 – 17:30 | Two live dispatches of the new `validate-one-feed.yml` diagnostic against `ovapi-netherlands`'s actual current feed, unbounded and memory-bounded — see Verification |
| 2026-08-21 17:48 | Real production `Daily scorecard` dispatched post-fix — see Verification |

## Root cause

`.github/workflows/scorecard.yml`:

```yaml
collect:
  needs: score
  runs-on: ubuntu-latest
```

`needs:` alone defaults the job's condition to `success()`. `score` runs as a
32-shard matrix with `fail-fast: false`, so one shard dying does not stop the
others — but it does make the *aggregate* `needs: score` condition false,
skipping `collect` (and, transitively, `deploy`) even though 31 of 32 shards
had valid, publishable output sitting in uploaded artifacts.

The killed shard's own logs showed no Java `OutOfMemoryError`, no Python
traceback, and no `report.json` — just "received a shutdown signal" / "lost
communication with the server" 2–4 minutes into validating
`ovapi-netherlands` (a `large_feed: true` national aggregate,
`stop_times.txt` 1.13 GB uncompressed). That is the Actions runner dying, not
the validator failing. The prior diagnostic pass found the *same* feed
validate successfully on other cycles under identical settings
(`-Xmx6g`, same runner image), which rules out a simple "the feed grew past
what the runner can hold" explanation — the trigger is content- or
timing-dependent, not deterministic, and remains only partially understood.

`Watchdog`'s freshness check compounded the misdiagnosis: it read
`scorecard.yml`'s own run history rather than the live site's actual deployed
data, so it reported staleness that was true of *Daily* but false of the site
as a whole — Intraday refresh (a separate 3-hourly workflow, unaffected by
this bug) kept publishing the whole time.

## What changed

Full detail in [#298](https://github.com/ChelseaKR/gtfs-scorecard/pull/298)
and [#299](https://github.com/ChelseaKR/gtfs-scorecard/pull/299); summarized
here:

1. **`collect: if: !cancelled()`** instead of the implicit `if: success()`, so
   one dead shard can no longer block the whole publish. A new "Verify shard
   artifacts before publishing" step counts shard bundles via the Actions API
   first and refuses to publish (fails loudly) only if **zero** shards
   uploaded anything.
2. **`timeout-minutes`** on `score` (55m, above the ~32m slowest observed
   shard), `collect` (60m, above the ~41m observed), and `refresh.yml`'s
   `refresh` job (240m, above the ~137m observed peak) — none had a bound
   short of the platform's 360-minute default.
3. **An opt-in per-process memory ceiling** (`SCORECARD_VALIDATOR_MEMORY_MB`,
   applied via `prlimit --as=` around the validator subprocess) so an
   overrun fails the allocating syscall — the JVM exits, the existing
   per-agency `RuntimeError` handling treats it as an ordinary failure —
   instead of the *runner* dying. Off by default (real Actions-runner memory
   isn't local dev memory); verified live below rather than assumed to work.
4. **Watchdog now checks the live site's actual `deployment.json`**
   (resolved through its `source_run_id` to that run's completion time)
   instead of `scorecard.yml`'s run history, so it reflects whichever
   publisher — Daily or Intraday — most recently deployed. Its separate
   "most recent Daily run did not fail" check gained `if: always()`; it had
   no way to run in practice before, because the freshness check's old 26h
   threshold had always already tripped by the time Watchdog's own
   6-hourly schedule got a turn.
5. **`pages.yml`/`a11y.yml`'s SEO-retention step** changed from
   `if-no-files-found: error` to `warn`, so a genuinely unrelated earlier
   failure in the same job stops masquerading as a SEO-report failure.
6. A caught-live follow-up ([#299](https://github.com/ChelseaKR/gtfs-scorecard/pull/299)):
   `large_feed_heap()` read `SCORECARD_LARGE_FEED_HEAP` with
   `os.environ.get(key, default)`, which only falls back to `default` when
   the key is *absent* — a workflow input left at its documented-empty
   default sets the env var present-but-empty, producing a bare `-Xmx` and a
   JVM that refuses to start. Production was never affected (that env var is
   never set there), but the new diagnostic workflow below hit it on its
   first real dispatch.

## Before / after (scheduled runs, from Actions run history)

| Workflow | Before (2026-08-07 through the 2026-08-21 diagnosis) | After |
|---|---|---|
| Daily scorecard | 14 attempted / 8 succeeded / 6 failed (4 of the 6 the `collect` gate specifically; 4 consecutive missed publishes 08-17→08-20) | Fix merged 16:44 UTC 2026-08-21; a fresh production dispatch is running post-fix — see Verification for the live run to check |
| Intraday refresh | 117 / 100 / 17 (17 unrelated one-offs: a production-smoke exit 1, a Lighthouse "Materialize" exit 2 + SEO-retention masking ×4, an SEO-contract exit 1) | Unaffected by the root cause throughout; the SEO-masking class of the 17 is fixed by item 5 above |
| Watchdog | 61 / 34 / 27, all 27 at the same step, reporting staleness that was false the entire time | Step 3 now measures real deployed freshness; step 4 can now actually run |
| Realtime monitor | 115 / 108 / 7 | Not in scope; unaffected throughout |

## Verification

Not claimed from a local dry run. Real dispatches, checked after landing:

- **`validate-one-feed.yml` run [32507466874](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/32507466874)** — `ovapi-netherlands`, unbounded (default settings, matching current production). `success`; validator exit status 0; wall clock 3m24.6s; peak RSS 6,718,072 KB (~6.4 GB) on a 15 GiB / 4-vCPU runner. Well past the 2–4 minute window where the runner previously died, on the actual current feed.
- **`validate-one-feed.yml` run [32508141222](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/32508141222)** — same feed, `SCORECARD_VALIDATOR_MEMORY_MB=10240` (the new `prlimit` ceiling exercised for the first time). `success`; exit status 0; wall clock 3m30.4s; peak RSS 6,715,340 KB — consistent with the unbounded run, confirming the wrapping mechanism doesn't interfere with a normal successful validation.
- **Daily scorecard run [32510124085](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/32510124085)** — dispatched 2026-08-21 17:48 UTC, the first full production run since the fix. Check this URL for the live/final result; if `ovapi-netherlands`'s shard fails again on this run, the `collect`/`deploy` gate fix (item 1) is what determines whether the other 31 shards still publish.

Neither diagnostic run reproduced the runner death — consistent with the prior
finding that the trigger is intermittent, not deterministic. The fix does not
depend on reproducing it: it makes the *consequence* (one shard's failure
blocking 31 others' publish) impossible regardless of cause, and gives the
validator subprocess a real, catchable failure mode instead of taking the
runner down with it, if and when it recurs.

## What's still open

- **The exact trigger for the runner death remains unconfirmed.** The
  `prlimit` ceiling (item 3) is a backstop, not a fix for a root cause that
  is still only partially understood. If `ovapi-netherlands` (or another
  `large_feed`) kills a runner again, `SCORECARD_VALIDATOR_MEMORY_MB` should
  be set for a future `validate-one-feed.yml` dispatch against the failing
  feed to see whether the bound converts a runner death into an ordinary,
  loud validator failure.
- **Whether a lower `SCORECARD_LARGE_FEED_HEAP` would help** is deliberately
  not assumed here — the original diagnosis explicitly refuted "the feed
  outgrew the runner" as the sole explanation, so changing the heap number
  without new evidence would be guessing, not fixing.

## Recurrence, 2026-08-26

This incident was closed as Resolved. It was not resolved, and the record
above overstates what the fix accomplished. Both halves are corrected here
rather than edited above, so the original claim and its correction both stay
readable.

**The gate fix was applied to half of what the diagnosis named.** The root
cause section says the condition skipped "`collect` (and, transitively,
`deploy`)". Remediation item 1 added `if: !cancelled()` to `collect` only.
`deploy` kept its implicit `if: success()`, which GitHub evaluates over a
job's whole ancestry rather than over its `needs:` list, so a dead `score`
shard went on skipping `deploy` exactly as before.

Observed on the three most recent daily runs at the time of writing
([32975621570](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/32975621570),
[32854480196](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/32854480196),
[32642725318](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/32642725318)):
`collect: success`, `deploy: skipped`.

This was invisible because `Intraday refresh` deploys every three hours and
kept the live site current, which is the same masking effect the original
investigation had to see through in the opposite direction. It would have
become a visible outage the moment that workflow was paused.

**The daily has been red for eight of the last nine scheduled runs**
(2026-08-18 through 08-26, with a single success on 08-21), failing on the
same shard at `ovapi-netherlands` with the same "The runner has received a
shutdown signal". The "What's still open" note above says that if this
recurred, `SCORECARD_VALIDATOR_MEMORY_MB` should be exercised against the
failing feed. It recurred five more times and the ceiling was never switched
on for a scheduled run, because item 3 shipped it opt-in and no scheduled
workflow set it.

**What changed now**

1. `deploy` gates on `needs.collect.result == 'success'` instead of the
   implicit ancestry-wide `success()`, finishing item 1.
2. `SCORECARD_VALIDATOR_MEMORY_MB: "10240"` is set at workflow level in
   `scorecard.yml` and `refresh.yml`, so both scheduled tiers run the
   validator under the ceiling that
   [32508141222](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/32508141222)
   verified live against that feed's real data.
3. Two regression tests in `pipeline/tests/test_workflow_safety.py`, both
   confirmed to fail against the configuration this repository carried before
   this change. An opt-in safeguard that no workflow opts into, and a gate fix
   applied to one job out of two, are both the kind of defect a merge-blocking
   assertion catches and a prose remediation list does not.

**Still open, unchanged.** The trigger for the runner death remains
unconfirmed. Nothing here claims to fix it. What changes is the blast radius:
one agency logged and skipped, rather than the day's publish lost. Whether the
ceiling actually converts a runner death into a catchable validator failure is
now testable in production for the first time, and the next occurrence at
`ovapi-netherlands` is the observation to watch for.

