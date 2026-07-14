"""Tests for --skip-unchanged in `scorecard run`.

These tests cover three scenarios for the liveness pre-check:
  - Feed is UNCHANGED  → _cmd_run exits 2 (skip, don't stage)
  - Feed is CHANGED    → _cmd_run proceeds with scoring (exit 0)
  - No prior record    → treated the same as CHANGED (first run always scores)

All tests mock _liveness_unchanged (for _cmd_run tests) or check_feed at its
source module (for _liveness_unchanged unit tests) so they don't touch the
network or the Java validator.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from scorecard_pipeline import RUBRIC_VERSION, SCHEMA_VERSION, SCORING_PROFILE_ID
from scorecard_pipeline.cli import (
    RunOutcome,
    _artifact_contract_current,
    _cmd_run,
    _liveness_unchanged,
)
from scorecard_pipeline.config import AGENCIES, Agency
from scorecard_pipeline.liveness import (
    CHANGED,
    UNCHANGED,
    UNREACHABLE,
    LivenessRecord,
    load_state,
)
from scorecard_pipeline.validate import VALIDATOR_VERSION

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

_TEST_URL = "https://feeds.example.org/gtfs.zip"
_TEST_ID = "testagency"


@pytest.fixture()
def one_agency() -> Iterator[str]:
    """Register a single synthetic agency and clean up afterward."""
    agency = Agency(id=_TEST_ID, name="Test Transit", static_gtfs_url=_TEST_URL)
    original = dict(AGENCIES)
    AGENCIES.clear()
    AGENCIES[_TEST_ID] = agency
    yield _TEST_ID
    AGENCIES.clear()
    AGENCIES.update(original)


def _run_args(**overrides: object) -> argparse.Namespace:
    defaults: dict[str, object] = {
        "all": False,
        "agency": _TEST_ID,
        "date": datetime.date(2026, 6, 27),
        "force_fetch": False,
        "rt_samples": 3,
        "rt_interval": 30,
        "skip_rt": True,
        "skip_unchanged": True,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _write_current_artifact(root: Path, **overrides: object) -> Path:
    artifact: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "rubric_version": RUBRIC_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "scoring_profile": {
            "id": SCORING_PROFILE_ID,
            "rubric_version": RUBRIC_VERSION,
        },
    }
    artifact.update(overrides)
    path = root / "data" / "artifacts" / _TEST_ID / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(artifact))
    return path


# ---------------------------------------------------------------------------
# _cmd_run exit-code tests (mock _liveness_unchanged and run_agency)
# ---------------------------------------------------------------------------


def test_skip_unchanged_exits_2_when_feed_unchanged(one_agency: str) -> None:
    """When the feed is UNCHANGED, --skip-unchanged must exit with code 2."""
    parser = argparse.ArgumentParser()
    with (
        patch("scorecard_pipeline.cli._liveness_unchanged", return_value=True),
        patch("scorecard_pipeline.cli.run_agency") as mock_score,
    ):
        result = _cmd_run(_run_args(), parser)

    assert result == 2
    mock_score.assert_not_called()


def test_skip_unchanged_proceeds_when_feed_changed(one_agency: str) -> None:
    """When the feed is CHANGED, scoring must proceed and return exit 0."""
    parser = argparse.ArgumentParser()
    with (
        patch("scorecard_pipeline.cli._liveness_unchanged", return_value=False),
        patch(
            "scorecard_pipeline.cli.run_agency",
            return_value=RunOutcome(path="/tmp/artifact.json", mirrored=False, cache_hit=False),
        ),
    ):
        result = _cmd_run(_run_args(), parser)

    assert result == 0


def test_force_fetch_bypasses_liveness_skip(one_agency: str) -> None:
    parser = argparse.ArgumentParser()
    with (
        patch("scorecard_pipeline.cli._liveness_unchanged") as liveness,
        patch(
            "scorecard_pipeline.cli.run_agency",
            return_value=RunOutcome(path="/tmp/artifact.json", mirrored=False, cache_hit=False),
        ) as score,
    ):
        result = _cmd_run(_run_args(force_fetch=True), parser)

    assert result == 0
    liveness.assert_not_called()
    score.assert_called_once_with(
        _TEST_ID,
        datetime.date(2026, 6, 27),
        force_fetch=True,
        rt_samples=3,
        rt_interval=30,
        skip_rt=True,
    )


def test_skip_unchanged_proceeds_when_no_prior_record(one_agency: str) -> None:
    """No prior liveness record (first run) is treated as CHANGED: always score."""
    # _liveness_unchanged returning False covers this: check_feed with no prior
    # record classifies as CHANGED, so _liveness_unchanged returns False.
    parser = argparse.ArgumentParser()
    with (
        patch("scorecard_pipeline.cli._liveness_unchanged", return_value=False),
        patch(
            "scorecard_pipeline.cli.run_agency",
            return_value=RunOutcome(path="/tmp/artifact.json", mirrored=False, cache_hit=False),
        ),
    ):
        result = _cmd_run(_run_args(), parser)

    assert result == 0


def test_skip_unchanged_proceeds_when_feed_unreachable(one_agency: str) -> None:
    """An UNREACHABLE feed is not skipped; the normal score attempt surfaces the error."""
    # _liveness_unchanged returns False for UNREACHABLE (same as CHANGED).
    parser = argparse.ArgumentParser()
    with (
        patch("scorecard_pipeline.cli._liveness_unchanged", return_value=False),
        patch("scorecard_pipeline.cli.run_agency", side_effect=RuntimeError("network error")),
    ):
        result = _cmd_run(_run_args(), parser)

    assert result == 1  # pipeline failure, not a skip


# ---------------------------------------------------------------------------
# _liveness_unchanged unit tests (mock check_feed at its source module)
#
# check_feed is imported inside _liveness_unchanged with `from .liveness import
# check_feed`, so the correct patch target is scorecard_pipeline.liveness.check_feed.
# ---------------------------------------------------------------------------


def test_liveness_unchanged_returns_true_for_unchanged(one_agency: str, tmp_path: Path) -> None:
    """When check_feed classifies the feed as UNCHANGED, _liveness_unchanged returns True."""
    _write_current_artifact(tmp_path / "repo")
    sha = hashlib.sha256(b"same body").hexdigest()

    def _fake_check(url: str, record: object, **kwargs: object) -> tuple[LivenessRecord, str]:
        return (LivenessRecord(url=url, sha256=sha, status=304), UNCHANGED)

    with patch("scorecard_pipeline.liveness.check_feed", _fake_check):
        result = _liveness_unchanged(_TEST_ID)

    assert result is True


def test_liveness_unchanged_returns_false_for_changed(one_agency: str, tmp_path: Path) -> None:
    """When check_feed classifies the feed as CHANGED, _liveness_unchanged returns False."""
    _write_current_artifact(tmp_path / "repo")
    new_sha = hashlib.sha256(b"new content").hexdigest()

    def _fake_check(url: str, record: object, **kwargs: object) -> tuple[LivenessRecord, str]:
        return (LivenessRecord(url=url, sha256=new_sha, status=200), CHANGED)

    with patch("scorecard_pipeline.liveness.check_feed", _fake_check):
        result = _liveness_unchanged(_TEST_ID)

    assert result is False


def test_liveness_unchanged_returns_false_for_unreachable(one_agency: str, tmp_path: Path) -> None:
    """When check_feed returns UNREACHABLE, _liveness_unchanged returns False."""
    _write_current_artifact(tmp_path / "repo")

    def _fake_check(url: str, record: object, **kwargs: object) -> tuple[LivenessRecord, str]:
        return (LivenessRecord(url=url, consecutive_failures=1), UNREACHABLE)

    with patch("scorecard_pipeline.liveness.check_feed", _fake_check):
        result = _liveness_unchanged(_TEST_ID)

    assert result is False


# ---------------------------------------------------------------------------
# --outcome-out (FIX-11): _cmd_run appends one ndjson outcome line per agency,
# for run-summary.py to turn into the shard's run-summary.json.
# ---------------------------------------------------------------------------


def test_outcome_out_records_reused_on_skip(one_agency: str, tmp_path: Path) -> None:
    outcomes_path = tmp_path / "outcomes.ndjson"
    parser = argparse.ArgumentParser()
    with (
        patch("scorecard_pipeline.cli._liveness_unchanged", return_value=True),
        patch("scorecard_pipeline.cli.run_agency") as mock_score,
    ):
        result = _cmd_run(_run_args(outcome_out=str(outcomes_path)), parser)

    assert result == 2
    mock_score.assert_not_called()
    lines = [json.loads(line) for line in outcomes_path.read_text().splitlines()]
    assert lines == [
        {
            "agency_id": _TEST_ID,
            "outcome": "reused",
            "mirrored": False,
            "cache_hit": False,
            "wall_seconds": lines[0]["wall_seconds"],
        }
    ]


def test_outcome_out_records_scored_with_mirror_and_cache_flags(
    one_agency: str, tmp_path: Path
) -> None:
    from scorecard_pipeline.cli import RunOutcome

    outcomes_path = tmp_path / "outcomes.ndjson"
    parser = argparse.ArgumentParser()
    with (
        patch("scorecard_pipeline.cli._liveness_unchanged", return_value=False),
        patch(
            "scorecard_pipeline.cli.run_agency",
            return_value=RunOutcome(path="/tmp/a.json", mirrored=True, cache_hit=True),
        ),
    ):
        result = _cmd_run(_run_args(outcome_out=str(outcomes_path)), parser)

    assert result == 0
    (line,) = [json.loads(line) for line in outcomes_path.read_text().splitlines()]
    assert line["outcome"] == "scored"
    assert line["mirrored"] is True
    assert line["cache_hit"] is True


def test_outcome_out_records_unreachable_on_failure(one_agency: str, tmp_path: Path) -> None:
    outcomes_path = tmp_path / "outcomes.ndjson"
    parser = argparse.ArgumentParser()
    with (
        patch("scorecard_pipeline.cli._liveness_unchanged", return_value=False),
        patch("scorecard_pipeline.cli.run_agency", side_effect=RuntimeError("network error")),
    ):
        result = _cmd_run(_run_args(outcome_out=str(outcomes_path)), parser)

    assert result == 1
    (line,) = [json.loads(line) for line in outcomes_path.read_text().splitlines()]
    assert line["outcome"] == "unreachable"


def test_no_outcome_out_writes_nothing(one_agency: str, tmp_path: Path) -> None:
    """Without --outcome-out (the default), no outcome log is written."""
    parser = argparse.ArgumentParser()
    with (
        patch("scorecard_pipeline.cli._liveness_unchanged", return_value=True),
        patch("scorecard_pipeline.cli.run_agency"),
    ):
        _cmd_run(_run_args(), parser)
    assert not (tmp_path / "outcomes.ndjson").exists()


def test_liveness_unchanged_persists_state(one_agency: str, tmp_path: Path) -> None:
    """The liveness record is written to data/liveness.json even on a skip."""
    _write_current_artifact(tmp_path / "repo")
    sha = hashlib.sha256(b"content").hexdigest()

    def _fake_check(url: str, record: object, **kwargs: object) -> tuple[LivenessRecord, str]:
        return (
            LivenessRecord(url=url, sha256=sha, status=304, checked_at="2026-06-27T13:00:00+00:00"),
            UNCHANGED,
        )

    with patch("scorecard_pipeline.liveness.check_feed", _fake_check):
        _liveness_unchanged(_TEST_ID)

    # isolated_repo_root sets SCORECARD_ROOT to tmp_path/repo.
    state_path = tmp_path / "repo" / "data" / "liveness.json"
    state = load_state(state_path)
    assert _TEST_ID in state
    assert state[_TEST_ID].checked_at == "2026-06-27T13:00:00+00:00"


@pytest.mark.parametrize(
    "overrides",
    [
        {"schema_version": "0.9"},
        {"rubric_version": "0.9"},
        {"validator_version": "0.9.0"},
        {"scoring_profile": "not-an-object"},
        {"scoring_profile": {"id": "old-profile", "rubric_version": RUBRIC_VERSION}},
        {"scoring_profile": {"id": SCORING_PROFILE_ID, "rubric_version": "0.9"}},
    ],
)
def test_artifact_contract_rejects_stale_producer_inputs(
    one_agency: str, tmp_path: Path, overrides: dict[str, object]
) -> None:
    _write_current_artifact(tmp_path / "repo", **overrides)
    assert _artifact_contract_current(_TEST_ID) is False


def test_artifact_contract_accepts_current_producer_inputs(one_agency: str, tmp_path: Path) -> None:
    _write_current_artifact(tmp_path / "repo")
    assert _artifact_contract_current(_TEST_ID) is True


@pytest.mark.parametrize("contents", [None, "{", "[]"])
def test_artifact_contract_rejects_missing_or_malformed_latest(
    one_agency: str, tmp_path: Path, contents: str | None
) -> None:
    path = tmp_path / "repo" / "data" / "artifacts" / _TEST_ID / "latest.json"
    if contents is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)
    assert _artifact_contract_current(_TEST_ID) is False


def test_liveness_skips_network_when_artifact_contract_is_stale(
    one_agency: str, tmp_path: Path
) -> None:
    _write_current_artifact(tmp_path / "repo", rubric_version="0.9")
    with patch("scorecard_pipeline.liveness.check_feed") as check_feed:
        assert _liveness_unchanged(_TEST_ID) is False
    check_feed.assert_not_called()
