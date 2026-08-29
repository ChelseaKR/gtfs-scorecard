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


## Recurrence, 2026-08-28: the observation the record asked for

The correction above ends "the next occurrence at `ovapi-netherlands` is the
observation to watch for." It has now occurred twice with the ceiling switched
on, so this section records what was observed rather than leaving the question
open.

**The `prlimit` ceiling did not convert the runner death into a catchable
validator failure.** `SCORECARD_VALIDATOR_MEMORY_MB: "10240"` went to workflow
level at 2026-08-27 01:43 UTC. The two scheduled Daily runs since,
[33096623505](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/33096623505)
(08-27) and
[33194678335](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/33194678335)
(08-28), both died in the same shard, at the same feed, with the same message.
From 33194678335's log:

```
17:39:38 INFO scorecard_pipeline.validate: running gtfs-validator on .../ovapi-netherlands/2026-08-28/gtfs.zip
17:47:16 ##[error]The runner has received a shutdown signal. This can happen when the runner service is stopped, or a manually started runner is canceled.
17:47:16 ##[error]The operation was canceled.
```

No `RuntimeError`, no truncated stderr, no `report.json` diagnostic: the same
signature as before the ceiling, roughly seven and a half minutes in rather
than the two to four minutes the original diagnosis recorded. The ceiling is
therefore a control with no observed effect on this failure, in either
direction. The one live measurement it does have,
[32508141222](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/32508141222),
recorded peak RSS within a few megabytes of the unbounded run alongside it,
which says the bound was never reached in a healthy run either.

Nothing here argues for removing it, and nothing here argues for changing the
number. The original note that a heap change "without new evidence would be
guessing" applies unchanged to the ceiling. What has changed is that the
question is answered: the ceiling is not the fix, and the trigger is still
unconfirmed.

**The blast-radius claim was wrong.** The correction above says the change
takes the outcome from "the day's publish lost" to "one agency logged and
skipped". The first half held: `collect` and `deploy` both ran on 08-27 and
08-28. The second half did not. Because the runner itself dies, the shard never
reaches its `upload-artifact` step, so every feed record that shard had already
scored is discarded along with `ovapi-netherlands`. At 32 shards over roughly
2,100 records that is on the order of 65 records per occurrence, not one, and
each keeps its previous scorecard.

**That loss was invisible on `/status/`.** `merge_run_summaries` summed every
total over the shard summaries that arrived. A shard whose runner is killed
uploads no `run-summary.json` at all, so it was absent rather than present and
empty: `shard_count` read 31, `agency_count` dropped by the lost shard's
records, the unreachable fraction stayed at zero, and the page rendered "Run
completed". That is precisely the failure `run_summary.py`'s own module
docstring says the feature exists to prevent, "if one of twelve shards failed,
the agencies it owned silently kept showing yesterday's data with no public
signal anywhere". The merge now takes the planned shard count from the workflow
(`--expected-shards`), counts the shortfall, degrades the run, and names the
reason on `/status/`; `pipeline/tests/test_run_summary.py` and
`pipeline/tests/test_workflow_safety.py` hold both halves.

**Still open, and a maintainer decision.** Two things this pass deliberately
did not do:

1. Find the trigger. It needs live experiments against the failing feed
   (`validate-one-feed.yml` with a lower `SCORECARD_LARGE_FEED_HEAP`, a lower
   `SCORECARD_VALIDATOR_MEMORY_MB`, and a disk-space reading), not a guess in a
   config file. Until then the Daily run stays red and the Watchdog stays red
   behind it.
2. Stop a killed runner from discarding the work its shard had already
   finished. The shard uploads its scored artifacts once, at the end. Moving
   that to an incremental upload, or splitting `large_feed` records onto their
   own shard, would bound the loss to the feed that actually failed. Both are
   real changes to how the daily run is structured and should be chosen, not
   slipped in.

Neither is a reason to silence the Watchdog. It is reporting a true fact.


## Recurrence, 2026-08-29: the failure reproduces on demand, and a diagnostic that said nothing

Three `validate-one-feed.yml` dispatches against `ovapi-netherlands` today, all
three dead. Two of the three retract things this record has been saying since
2026-08-21.

**"Neither diagnostic run reproduced the runner death" no longer holds.** The
Verification section above records two successful diagnostic runs on 08-21 and
concludes the trigger "is intermittent, not deterministic". Today it reproduced
on every attempt:

| Run | `SCORECARD_VALIDATOR_MEMORY_MB` | `SCORECARD_LARGE_FEED_HEAP` | Outcome |
|---|---|---|---|
| [33264844507](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/33264844507) | 6144 | 4g | exit 1 at 1.3s, peak RSS 271 MB |
| [33264970236](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/33264970236) | 10240 | 4g | step `cancelled` 4m01s into validation |
| [33265338459](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/33265338459) | 10240 | default (6g) | step `cancelled` 2m24s into validation |

The third is the one that matters. `10240` with the default heap is exactly
what `scorecard.yml` and `refresh.yml` run, and it is exactly the pairing that
[32508141222](https://github.com/ChelseaKR/gtfs-scorecard/actions/runs/32508141222)
validated successfully on 08-21 in 3m30.4s at 6,715,340 KB peak RSS. The same
configuration, against the same feed id, now dies. In all three the job
finished `failure` with the validating step `cancelled`, the 55-minute job
timeout nowhere near reached; `validate-one-feed.yml` has no `concurrency`
block and no later run superseded any of them, which is the same signature the
scheduled runs have carried since 08-17. It remains an inference from the
absence of a cancelling actor rather than a positive signal from the platform.

**So the memory parameters are not the variable.** Two of them have now been
moved with no effect on the outcome, and the pairing that worked eight days ago
does not work today. What differs between 08-21 and 08-29 is the feed's own
bytes, refetched every run, or the runner image underneath. That is consistent
with the original 08-21 diagnosis, which refuted "the feed outgrew the runner"
because the same feed passed and failed under identical settings. Nothing here
identifies the trigger. It narrows where it is not.

**The first run was a bad experiment, and it exposed a real defect.** `6144`
with a `4g` heap is not a smaller version of the production setting.
`SCORECARD_VALIDATOR_MEMORY_MB` becomes `prlimit --as`, which caps virtual
address space, not resident memory, and a JVM reserves far more address space
than its `-Xmx`. That run died in 1.3 seconds at 271 MB peak RSS: the VM never
started, so the feed was never read. The run says nothing about the feed.

What it did say, in full, was this:

```
INFO scorecard_pipeline.validate: running gtfs-validator on .../ovapi-netherlands/2026-08-29/gtfs.zip
ERROR scorecard_pipeline.cli: ovapi-netherlands: gtfs-validator produced no report (exit 1):
```

Nothing after the colon. `run_validator` quoted the subprocess's stderr into
its `RuntimeError` and discarded stdout, and a JVM splits its startup failures
across both streams: a malformed flag ("Invalid maximum heap size: -Xmx", the
bug [#299](https://github.com/ChelseaKR/gtfs-scorecard/pull/299) fixed) goes to
stderr, while a heap it cannot reserve ("Error occurred during initialization
of VM / Could not reserve enough space for ... object heap") goes to stdout.
Verified directly against a JVM, not inferred. The failure mode an
`SCORECARD_VALIDATOR_MEMORY_MB` set too close to `-Xmx` provokes was therefore
the exact one the error path could not report, and the cause had to be
reconstructed from `/usr/bin/time`'s peak-RSS line instead. An error path that
announces a failure without the information to diagnose it is the same class of
defect as a gate that cannot fail.

**What changed now**

1. `run_validator`'s failure quotes both streams, each labelled, each capped at
   8,000 characters head-and-tail with the omitted count stated, and names the
   exit code, the feed, the heap flag, the address-space ceiling and the exact
   command to reproduce by hand. An empty stream reads `(empty)` rather than as
   a blank gap, so "the validator said nothing" is distinguishable from "we
   dropped it".
2. The address-space-versus-RSS distinction is documented on the
   `validate-one-feed.yml` dispatch inputs, where an operator actually types
   the number, rather than only in `scorecard.yml`'s env comment and
   `validate.py`'s docstring. Today's first run is cited there as the worked
   example.
3. `scorecard shards` gives every `large_feed` a shard of its own, the option
   this record's "Still open" list named. A killed runner never reaches
   `upload-artifact`, so it discards everything its shard had already scored;
   at 32 shards over ~2,000 records that has been costing about 65 records per
   occurrence. Ten records carry `large_feed: true`, so the plan goes from 32
   shards to 42 and a death at `ovapi-netherlands` costs one record.
4. That change had a trap in it worth recording. `collect` measured both its
   shard-shortfall warning and `run-summary merge --expected-shards` against
   `SHARD_COUNT`, the *requested* round-robin count. Isolation makes the plan
   longer than `SHARD_COUNT`, so those comparisons would have read 42 bundles
   present against 32 expected, come out false in every branch, and stopped
   detecting shortfalls entirely — reintroducing the silent shard loss
   [#322](https://github.com/ChelseaKR/gtfs-scorecard/pull/322) removed, hours
   after it landed. Both now read a `shard_count` output the `plan` job
   publishes, and `collect` refuses to publish if that denominator is missing
   rather than comparing against an empty string.
5. The claim in `scorecard.yml`'s env comment that the ceiling "changes the
   blast radius from the whole day's publish to one agency logged and skipped"
   is corrected in place to match the 08-28 retraction above, which had left
   the workflow comment still asserting it.

**Still open, and narrowed.** The trigger is still unconfirmed and nothing here
claims otherwise. It is cheaper to chase than it was this morning: it now
reproduces on demand at production settings in a read-only workflow that never
deploys, and the next failure will say what the validator said instead of
printing a bare exit code. The heap and the ceiling have each been moved once
with no effect, so the next experiments worth running are the ones that vary
something else — the runner image, the feed's own bytes against a pinned
earlier copy, or the validator version.
