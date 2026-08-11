"""Weekly OTP routing-QA batch: which feeds to test, and the batch verdict.

otp.py answers "do sampled trips route" for one feed against one OpenTripPlanner
instance. The weekly batch (ADR 0014, expansion plan item "trip-plannability at
sample scale") asks that question for a handful of feeds without a hosted OTP:
CI builds a throwaway containerized OTP per feed. This module is the pure half
of that batch — pick which feeds are worth the container spin-up, and aggregate
the per-feed verdicts — mirroring how otp.py keeps the live HTTP call thin.

The selection takes the same published index the rankings and the open dataset
read from (dataset.build_quality_dataset), so "best" and "worst" here mean
exactly what the national pulse page means by them. Best feeds catch a router
regression that scores miss (a top-graded feed that cannot plan a trip is the
sharpest possible signal); worst feeds show whether the grade actually predicts
a rider's experience. Everything here is pure over dicts and dataclasses, and
unit-tested; the CLI and workflow own all IO.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .dataset import build_quality_dataset
from .otp import RoutingQA


@dataclass(frozen=True)
class BatchFeed:
    """One feed chosen for the batch: enough to fetch it and label the job."""

    feed_id: str
    feed_url: str
    score: float
    cohort: str  # "best" or "worst"


def select_best_worst(
    index: dict[str, Any], feed_urls: Mapping[str, str], *, count: int = 2
) -> list[BatchFeed]:
    """Pick the `count` best and `count` worst scored feeds from the index.

    Ranks by the same latest-check score the published rankings use, breaking
    ties by agency id so the selection is deterministic between runs. Feeds
    without a score yet, without a known fetch URL, or without a current service
    window are skipped: the batch can only route service that OTP can build for
    today. When fewer than 2*count feeds qualify, the best cohort fills first
    and the worst takes the remainder, so a feed is never queued twice. Best
    feeds come first (highest score first), then worst (lowest score first).
    """
    rows = build_quality_dataset(index)["rows"]
    ranked = sorted(
        (
            (float(row["score"]), str(row["id"]))
            for row in rows
            if row.get("score") is not None
            and row["id"] in feed_urls
            and row.get("days_until_expiry") is not None
            and float(row["days_until_expiry"]) > 0
        ),
        key=lambda item: (-item[0], item[1]),
    )
    best = ranked[:count]
    worst = ranked[count:][-count:]
    chosen = [BatchFeed(fid, feed_urls[fid], score, "best") for score, fid in best]
    chosen += [BatchFeed(fid, feed_urls[fid], score, "worst") for score, fid in reversed(worst)]
    return chosen


def matrix_entries(feeds: Sequence[BatchFeed]) -> list[dict[str, str]]:
    """Render the selection as the JSON-able matrix a CI fan-out consumes.

    One object per feed with only strings, matching how scorecard.yml feeds
    `fromJSON` into `strategy.matrix`. The cohort rides along so the per-feed
    job name says why the feed was picked.
    """
    return [
        {"feed_id": feed.feed_id, "feed_url": feed.feed_url, "cohort": feed.cohort}
        for feed in feeds
    ]


@dataclass(frozen=True)
class BatchVerdict:
    """The verdict over the whole batch: did every sampled feed route?"""

    feeds_tested: int
    feeds_routable: int
    failures: list[str]
    not_testable: list[str] = field(default_factory=list)

    @property
    def all_routable(self) -> bool:
        return self.feeds_tested > 0 and self.feeds_routable == self.feeds_tested

    @property
    def routable_share(self) -> float:
        return self.feeds_routable / self.feeds_tested if self.feeds_tested else 0.0


def assess_batch(
    results: Sequence[tuple[str, RoutingQA]],
    *,
    not_testable: Sequence[tuple[str, str]] = (),
) -> BatchVerdict:
    """Aggregate per-feed routing verdicts into one batch verdict.

    A feed passes only when all of its sampled pairs routed (the same gate the
    single-feed CLI exits on). Failures carry the feed id with each pair-level
    message, so the weekly digest can say which feed broke and how; a feed that
    tested no pairs at all is a failure too, not a silent pass.

    `not_testable` holds feeds OTP could not build a graph from, as
    (feed_id, reason). They are recorded, not counted: no router behavior was
    observed, so calling them unroutable would say something the batch never
    measured, and the feed's own parsing problem already reaches the agency
    through its scorecard.
    """
    routable = sum(1 for _, qa in results if qa.all_routable)
    failures = [
        f"{feed_id}: {message}"
        for feed_id, qa in results
        if not qa.all_routable
        for message in (qa.failures or ["no origin/destination pairs tested"])
    ]
    return BatchVerdict(
        feeds_tested=len(results),
        feeds_routable=routable,
        failures=failures,
        not_testable=[f"{feed_id}: {reason}" for feed_id, reason in not_testable],
    )
