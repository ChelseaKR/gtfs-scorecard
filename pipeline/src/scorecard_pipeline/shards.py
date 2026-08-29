"""Split the agency list into balanced shards for parallel CI runs.

The roadmap's Year 1 compute step (docs/roadmap.md): the validator is a few
seconds per feed, so a region's worth of feeds still fits the daily cron, but
only if the work fans out instead of running in one serial loop. The CI matrix
asks this command for a plan, then each matrix job runs its slice with
`scorecard run --agency ...`.

Round-robin assignment keeps shards close to equal in size without needing to
know per-feed timing. A single rebuild job stitches the per-shard artifacts
back into one index afterwards.

Some feeds get a shard to themselves. See ``plan_shards``.
"""

from __future__ import annotations

from collections.abc import Collection


def plan_shards(
    agency_ids: list[str], count: int, isolate: Collection[str] = ()
) -> list[list[str]]:
    """Distribute agency ids across `count` shards, round-robin.

    Empty shards are dropped so the CI matrix never spawns a job with no work
    (which happens when there are fewer agencies than requested shards).

    Ids in `isolate` are held out of the round-robin and given one shard each,
    appended after it. Blast radius is the reason (issue #297): when a runner
    is killed mid-validation the shard never reaches its `upload-artifact`
    step, so every record it had already scored is discarded along with the
    feed that killed it. At 32 shards over roughly 2,100 records that cost
    about 65 records per occurrence. A feed that runs alone can only cost
    itself.

    This does not identify, and does not claim to fix, whatever kills the
    runner; the incident record is explicit that the trigger is unconfirmed.
    It bounds the loss when it happens again.

    The plan stays deterministic. Both groups are sorted before assignment and
    the isolated shards are appended in sorted order, so the same registry and
    the same `count` always produce the same plan, which is what makes a
    re-run comparable to the run it repeats.

    Note for the caller: the number of shards returned is no longer implied by
    `count`. It is `count` (or fewer, if some round-robin buckets came up
    empty) plus one per isolated id, so anything that needs the planned shard
    count must read the length of this list rather than assume `count`.
    """
    if count < 1:
        raise ValueError("shard count must be at least 1")
    present = set(agency_ids)
    isolated = sorted(present & set(isolate))
    ordinary = sorted(present - set(isolated))
    buckets: list[list[str]] = [[] for _ in range(count)]
    for i, agency_id in enumerate(ordinary):
        buckets[i % count].append(agency_id)
    return [b for b in buckets if b] + [[agency_id] for agency_id in isolated]
