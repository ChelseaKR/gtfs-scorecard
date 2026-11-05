"""Tests for the consumer-facing freshness/uptime commitment (pure, EXP-10)."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from scorecard_pipeline.metrics import STALE_FEED_DAYS, UNREACHABLE_STREAK_CHECKS
from scorecard_pipeline.status_commitment import (
    DAILY_FULL_SCORE_CRON,
    build_status_commitment,
    cadence_commitment,
    degradation_policy,
    refresh_success_record,
)

NOW = dt.datetime(2026, 7, 8, 12, 0, tzinfo=dt.UTC)

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github" / "workflows"


def _workflow_crons(name: str) -> list[str]:
    """Every `- cron: "..."` line in a workflow, read as text.

    Deliberately a regex over the raw file rather than a YAML parse: the point
    is to compare the literal string a reader sees in the workflow against the
    literal string this module publishes, with no normalization in between.
    """
    text = (WORKFLOWS / name).read_text()
    return re.findall(r"^\s*-\s*cron:\s*[\"'](.+?)[\"']\s*$", text, flags=re.MULTILINE)


def _feed(checked_at: str, *, failures: int = 0) -> dict[str, object]:
    return {"checked_at": checked_at, "consecutive_failures": failures}


def test_cadence_commitment_has_all_three_tiers_with_a_cadence() -> None:
    tiers = cadence_commitment()
    names = {t["tier"] for t in tiers}
    assert names == {"priority", "standard", "full_validation"}
    for t in tiers:
        assert t["cadence"]
        assert t["applies_to"]
        assert t["schedule_cron"]


def test_published_crons_match_the_workflows_they_name() -> None:
    """The guardrail the module docstring has always claimed.

    `schedule_cron` is published verbatim on /status/ and in api/v1/status.json,
    so a cron edited in the workflow and nowhere else would publish a false
    statement about how often the pipeline runs. Nothing else in the suite
    catches that, because every other assertion here is about the shape of the
    document rather than its content.

    Since 2026-10-31 the Intraday refresh runs only by hand, so it declares no
    cron and no tier may name one from it: every tier runs on the Daily.
    """
    assert _workflow_crons("refresh.yml") == []
    assert _workflow_crons("scorecard.yml") == [DAILY_FULL_SCORE_CRON]
    assert {t["schedule_cron"] for t in cadence_commitment()} == {DAILY_FULL_SCORE_CRON}


def _daily_job(name: str) -> str:
    """One top-level job of scorecard.yml, from its key to the next job's key."""
    text = (WORKFLOWS / "scorecard.yml").read_text()
    start = text.index(f"\n  {name}:\n") + 1
    following = re.search(r"^  [a-z][a-z0-9_-]*:$", text[start + 1 :], re.MULTILINE)
    return text[start : start + 1 + following.start()] if following else text[start:]


def test_the_daily_run_checks_every_feed_and_publishes_the_liveness_state() -> None:
    """What makes "one direct liveness check each day" true.

    The liveness tiers name the Daily's cron, so the Daily has to do the check:
    over every feed (no `--only` due subset), persisted (`--apply`), and written
    back to the object the deploy and the next day's check read. Without the
    publish the check would run and its result would be thrown away, and
    /status/ would keep reporting the last state the Intraday refresh saved.
    """
    job = _daily_job("liveness")
    commands = [line.split("#", 1)[0] for line in job.splitlines()]
    check = [line for line in commands if "scorecard liveness" in line]
    assert len(check) == 1
    assert "--apply" in check[0]
    assert "--only" not in check[0]
    publish = job[job.index("- name: Publish the liveness state") :]
    upload = re.sub(r"\s*\\\n\s*", " ", publish)
    assert 'aws s3 cp data/liveness.json "s3://${ARTIFACTS_BUCKET}/data/liveness.json"' in upload
    # The deploy after collect reads data/liveness.json from S3, so collect
    # waits for this job, and still runs when it fails.
    collect = _daily_job("collect")
    assert "needs: [plan, score, liveness]" in collect
    assert "if: ${{ !cancelled() }}" in collect


def test_degradation_policy_uses_the_real_code_thresholds() -> None:
    policy = degradation_policy()
    assert policy["unreachable_after_consecutive_checks"] == UNREACHABLE_STREAK_CHECKS
    assert policy["stale_after_days_past_expiry"] == STALE_FEED_DAYS
    assert len(policy["statements"]) >= 3


def test_refresh_success_record_empty_feeds_degrades_cleanly() -> None:
    record = refresh_success_record({}, NOW)
    assert record["feeds_tracked"] == 0
    assert record["currently_clean_pct"] is None
    assert record["success_rate_pct"] is None


def test_refresh_success_record_classifies_healthy_degraded_unreachable() -> None:
    feeds = {
        "healthy-a": _feed("2026-07-08T11:00:00+00:00", failures=0),
        "healthy-b": _feed("2026-07-08T10:00:00+00:00", failures=0),
        "degraded": _feed("2026-07-08T09:00:00+00:00", failures=3),
        "dead": _feed("2026-07-01T00:00:00+00:00", failures=UNREACHABLE_STREAK_CHECKS),
    }
    record = refresh_success_record(feeds, NOW)
    assert record["feeds_tracked"] == 4
    assert record["healthy"] == 2
    assert record["degraded"] == 1
    assert record["unreachable"] == 1
    assert record["currently_clean_pct"] == 50.0
    assert record["success_rate_pct"] == 50.0
    assert "not a historical request-success rate" in record["measurement_note"]
    # The dead feed hasn't checked in a week; max staleness reflects that.
    assert record["hours_since_last_check"]["max"] > 24


def test_refresh_success_record_tolerates_malformed_timestamps() -> None:
    feeds = {"bad": {"checked_at": "not-a-date", "consecutive_failures": 0}}
    record = refresh_success_record(feeds, NOW)
    assert record["feeds_tracked"] == 1
    assert record["hours_since_last_check"]["max"] is None


def test_build_status_commitment_assembles_every_section() -> None:
    feeds = {"a": _feed("2026-07-08T11:30:00+00:00")}
    doc = build_status_commitment(feeds, NOW, "https://gtfsscorecard.org")
    assert doc["license"]
    assert doc["attribution"]
    assert doc["human_readable"] == "https://gtfsscorecard.org/status/"
    assert doc["commitment"]["tiers"]
    assert doc["refresh_success_record"]["feeds_tracked"] == 1
    assert doc["degradation_policy"]["statements"]


def test_both_liveness_tiers_promise_one_check_a_day_and_nothing_more() -> None:
    """Every feed is checked once a day by the Daily, whatever its tier. A
    cadence sentence that named hours or a spread across a period would be
    describing the Intraday refresh, which no longer runs on a schedule."""
    tiers = {t["tier"]: t for t in cadence_commitment()}
    for name in ("priority", "standard"):
        cadence = tiers[name]["cadence"]
        assert cadence == "one direct liveness check each day"
        assert "hour" not in cadence
        assert "spread" not in cadence
