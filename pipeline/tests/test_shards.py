"""Tests for the CI fan-out shard planner."""

from __future__ import annotations

import pytest

from scorecard_pipeline.shards import plan_shards


def test_round_robin_balances_shards() -> None:
    shards = plan_shards(["a", "b", "c", "d", "e"], 2)
    assert shards == [["a", "c", "e"], ["b", "d"]]


def test_every_agency_appears_exactly_once() -> None:
    ids = [f"a{i}" for i in range(23)]
    shards = plan_shards(ids, 4)
    flat = [x for shard in shards for x in shard]
    assert sorted(flat) == sorted(ids)


def test_empty_shards_are_dropped() -> None:
    shards = plan_shards(["a", "b"], 5)
    assert shards == [["a"], ["b"]]


def test_zero_shards_rejected() -> None:
    with pytest.raises(ValueError):
        plan_shards(["a"], 0)


def test_isolated_ids_each_get_a_shard_to_themselves() -> None:
    """issue #297: a killed runner discards everything its shard had scored.

    A feed that runs alone can only cost itself, so the ~65 records that went
    down with `ovapi-netherlands` on every occurrence stay in shards of their
    own that never touched it.
    """
    shards = plan_shards(["a", "b", "c", "big1", "big2"], 2, isolate={"big1", "big2"})
    assert shards == [["a", "c"], ["b"], ["big1"], ["big2"]]


def test_an_isolated_id_is_held_out_of_the_round_robin() -> None:
    """Isolation is a partition, not a copy: sharing would score it twice."""
    shards = plan_shards(["a", "b", "big"], 2, isolate={"big"})
    round_robin = shards[:-1]
    assert not any("big" in shard for shard in round_robin)
    flat = [x for shard in shards for x in shard]
    assert sorted(flat) == ["a", "b", "big"]
    assert flat.count("big") == 1


def test_every_agency_appears_exactly_once_with_isolation() -> None:
    ids = [f"a{i}" for i in range(23)]
    shards = plan_shards(ids, 4, isolate={"a3", "a17"})
    flat = [x for shard in shards for x in shard]
    assert sorted(flat) == sorted(ids)


def test_shard_count_is_not_implied_by_count_once_anything_is_isolated() -> None:
    """The planned shard count is what the CI denominator must read.

    `collect` counts uploaded shard bundles against a planned total. If that
    total keeps reading the requested `count` while the plan returns more, the
    shortfall check compares a bigger number against a smaller one, every
    comparison comes out false, and a lost shard goes unreported again.
    """
    ids = [f"a{i}" for i in range(20)]
    plan = plan_shards(ids, 4, isolate={"a1", "a2", "a3"})
    assert len(plan) == 4 + 3
    assert len(plan) != 4


def test_isolating_an_id_that_is_not_present_changes_nothing() -> None:
    assert plan_shards(["a", "b"], 2, isolate={"absent"}) == plan_shards(["a", "b"], 2)


def test_the_plan_is_deterministic_regardless_of_input_order() -> None:
    """A re-run has to be comparable to the run it repeats."""
    ids = [f"a{i}" for i in range(15)]
    isolate = {"a4", "a11"}
    first = plan_shards(ids, 3, isolate=isolate)
    assert first == plan_shards(list(reversed(ids)), 3, isolate=isolate)
    assert first == plan_shards(ids + ids, 3, isolate=isolate)


def test_isolation_defaults_to_off_so_the_old_plan_is_unchanged() -> None:
    assert plan_shards(["a", "b", "c", "d", "e"], 2) == [["a", "c", "e"], ["b", "d"]]
