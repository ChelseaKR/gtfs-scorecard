"""Unit tests for the serverless handler logic (infra/alerts, infra/submit,
infra/instant-score).

These handlers are standalone Lambda modules outside the scorecard_pipeline
package, but their validation, token, and rate-limit logic is the most
security-sensitive code in the repo and was previously untested. They keep boto3
lazy, so the pure logic loads and runs without AWS; the few table-touching paths
are exercised with a fake table.
"""

from __future__ import annotations

import importlib.util
import time
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]


def _load(rel_path: str, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, REPO / rel_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


alerts = _load("infra/alerts/handler.py", "alerts_handler")
submit = _load("infra/submit/handler.py", "submit_handler")
instant_score = _load("infra/instant-score/handler.py", "instant_score_handler")


class FakeTable:
    """Minimal stand-in for a DynamoDB Table."""

    def __init__(self, item: dict[str, Any] | None = None) -> None:
        self._item = item
        self.updated = False
        self.deleted = False

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:  # noqa: N803 - boto3 kwarg name
        return {"Item": self._item} if self._item else {}

    def update_item(self, **_: Any) -> None:
        self.updated = True

    def delete_item(self, Key: dict[str, Any]) -> None:  # noqa: N803 - boto3 kwarg name
        self.deleted = True


# --- alerts: validate_subscribe ---


def test_validate_subscribe_normalizes_email_and_defaults_kinds() -> None:
    out = alerts.validate_subscribe({"email": "  Agency@Example.ORG ", "all": True})
    assert out["email"] == "agency@example.org"
    assert out["all"] is True
    assert out["kinds"] == ["expiry", "regression"]


def test_validate_subscribe_rejects_url_significant_email() -> None:
    for bad in ("a&b@x.io", "a?b@x.io", "a b@x.io", "nope"):
        with pytest.raises(alerts.BadRequest):
            alerts.validate_subscribe({"email": bad, "all": True})


def test_validate_subscribe_validates_agency_slugs_and_count() -> None:
    with pytest.raises(alerts.BadRequest):
        alerts.validate_subscribe({"email": "a@b.io", "agencies": ["Bad Slug!"]})
    with pytest.raises(alerts.BadRequest):
        alerts.validate_subscribe({"email": "a@b.io"})  # neither all nor agencies
    out = alerts.validate_subscribe({"email": "a@b.io", "agencies": ["unitrans", "yolobus"]})
    assert out["agencies"] == ["unitrans", "yolobus"]


def test_validate_subscribe_rejects_unknown_kind() -> None:
    with pytest.raises(alerts.BadRequest):
        alerts.validate_subscribe({"email": "a@b.io", "all": True, "kinds": ["nope"]})


# --- alerts: cooldown and secret gate ---


def test_email_on_cooldown() -> None:
    now = int(time.time())
    assert alerts._email_on_cooldown(None) is False
    assert alerts._email_on_cooldown({"verified": True, "requested_ts": now}) is False
    assert alerts._email_on_cooldown({"requested_ts": now}) is True
    assert alerts._email_on_cooldown({"requested_ts": now - 10_000}) is False


def test_secret_ok_open_when_unset_and_constant_time_when_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SUBSCRIBE_SHARED_SECRET", raising=False)
    assert alerts._secret_ok({}) is True
    monkeypatch.setenv("SUBSCRIBE_SHARED_SECRET", "s3cret")
    assert alerts._secret_ok({"headers": {"X-Subscribe-Token": "s3cret"}}) is True
    assert alerts._secret_ok({"headers": {"X-Subscribe-Token": "wrong"}}) is False
    assert alerts._secret_ok({}) is False


# --- alerts: confirm / unsubscribe token logic ---


def test_confirm_rejects_wrong_token_and_does_not_verify(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable({"email": "a@b.io", "token": "good"})
    monkeypatch.setattr(alerts, "_table", lambda: table)
    resp = alerts._confirm({"rawQueryString": "email=a@b.io&token=wrong"})
    assert resp["statusCode"] == 400
    assert table.updated is False


def test_confirm_accepts_matching_token(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable({"email": "a@b.io", "token": "good"})
    monkeypatch.setattr(alerts, "_table", lambda: table)
    resp = alerts._confirm({"rawQueryString": "email=a@b.io&token=good"})
    assert resp["statusCode"] == 200
    assert table.updated is True


def test_unsubscribe_missing_row_is_idempotent_success(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable(None)
    monkeypatch.setattr(alerts, "_table", lambda: table)
    resp = alerts._unsubscribe({"rawQueryString": "email=a@b.io&token=x"})
    assert resp["statusCode"] == 200
    assert table.deleted is False


# --- submit: secret gate ---


def test_submit_options_preflight() -> None:
    resp = submit.handler({"requestContext": {"http": {"method": "OPTIONS"}}}, None)
    assert resp["statusCode"] == 204


def test_submit_rejects_wrong_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUBMIT_SHARED_SECRET", "s3cret")
    event = {
        "requestContext": {"http": {"method": "POST"}},
        "headers": {"x-submit-token": "wrong"},
        "body": "{}",
    }
    resp = submit.handler(event, None)
    assert resp["statusCode"] == 401


def test_submit_accepts_correct_secret_and_routes_to_pr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUBMIT_SHARED_SECRET", "s3cret")
    monkeypatch.setattr(submit, "_open_pull_request", lambda form: "https://github.com/x/pull/1")
    event = {
        "requestContext": {"http": {"method": "POST"}},
        "headers": {"x-submit-token": "s3cret"},
        "body": "{}",
    }
    resp = submit.handler(event, None)
    assert resp["statusCode"] == 200
    assert "pull/1" in resp["body"]


# --- instant-score: validate_score_request ---


def test_validate_score_request_normalizes_url_and_name() -> None:
    out = instant_score.validate_score_request(
        {"url": "  https://example.org/gtfs.zip  ", "name": "  Demo  "}
    )
    assert out == {"url": "https://example.org/gtfs.zip", "name": "Demo"}


def test_validate_score_request_rejects_missing_or_bad_url() -> None:
    for bad in ({}, {"url": ""}, {"url": "not-a-url"}, {"url": 123}):
        with pytest.raises(instant_score.BadRequest):
            instant_score.validate_score_request(bad)


def test_validate_score_request_rejects_non_string_name() -> None:
    with pytest.raises(instant_score.BadRequest):
        instant_score.validate_score_request({"url": "https://example.org/gtfs.zip", "name": 7})


def test_validate_score_request_truncates_long_name() -> None:
    out = instant_score.validate_score_request(
        {"url": "https://example.org/gtfs.zip", "name": "x" * 500}
    )
    assert len(out["name"]) == instant_score.MAX_NAME_LEN


def test_validate_score_request_no_name_key_when_absent() -> None:
    out = instant_score.validate_score_request({"url": "https://example.org/gtfs.zip"})
    assert "name" not in out


# --- instant-score: routing ---


def test_instant_score_options_preflight() -> None:
    resp = instant_score.handler({"requestContext": {"http": {"method": "OPTIONS"}}}, None)
    assert resp["statusCode"] == 204


def test_instant_score_unknown_method_is_404() -> None:
    resp = instant_score.handler({"requestContext": {"http": {"method": "DELETE"}}}, None)
    assert resp["statusCode"] == 404


def test_instant_score_async_self_invoke_runs_the_job(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(
        instant_score,
        "_run_scoring_job",
        lambda job_id, url, name: calls.append((job_id, url, name)),
    )
    result = instant_score.handler(
        {"job_id": "abc123", "url": "https://x.test/g.zip", "name": "X"}, None
    )
    assert result is None
    assert calls == [("abc123", "https://x.test/g.zip", "X")]


# --- instant-score: POST /score ---


def test_instant_score_post_invalid_json_is_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(instant_score, "_ip_rate_limited", lambda event: False)
    resp = instant_score.handler(
        {"requestContext": {"http": {"method": "POST"}}, "body": "not json"}, None
    )
    assert resp["statusCode"] == 400


def test_instant_score_post_bad_request_is_400(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(instant_score, "_ip_rate_limited", lambda event: False)
    resp = instant_score.handler(
        {"requestContext": {"http": {"method": "POST"}}, "body": "{}"}, None
    )
    assert resp["statusCode"] == 400


def test_instant_score_post_starts_a_job(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(instant_score, "_ip_rate_limited", lambda event: False)
    started = []
    monkeypatch.setattr(
        instant_score,
        "_start_scoring",
        lambda job_id, url, name: started.append((job_id, url, name)),
    )
    body = '{"url": "https://x.test/g.zip", "name": "X Transit"}'
    resp = instant_score.handler(
        {"requestContext": {"http": {"method": "POST"}}, "body": body}, None
    )
    assert resp["statusCode"] == 202
    assert len(started) == 1
    job_id, url, name = started[0]
    assert instant_score._JOB_ID_RE.match(job_id)
    assert url == "https://x.test/g.zip"
    assert name == "X Transit"
    assert job_id in resp["body"]


def test_instant_score_post_actually_rate_limited_returns_429(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(instant_score, "_ip_rate_limited", lambda event: True)
    resp = instant_score.handler(
        {"requestContext": {"http": {"method": "POST"}}, "body": "{}"}, None
    )
    assert resp["statusCode"] == 429


# --- instant-score: GET /score/{id} ---


def test_instant_score_get_rejects_invalid_job_id() -> None:
    event = {"requestContext": {"http": {"method": "GET", "path": "/score/short"}}}
    resp = instant_score.handler(event, None)
    assert resp["statusCode"] == 400


def test_instant_score_get_unknown_job_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable(None)
    monkeypatch.setattr(instant_score, "_jobs_table", lambda: table)
    event = {"requestContext": {"http": {"method": "GET", "path": "/score/abc12345"}}}
    resp = instant_score.handler(event, None)
    assert resp["statusCode"] == 404


def test_instant_score_get_done_job_includes_grade_and_result_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = FakeTable(
        {
            "status": "done",
            "result_url": "https://gtfsscorecard.org/scratch/abc12345/latest.json",
            "grade": "B",
        }
    )
    monkeypatch.setattr(instant_score, "_jobs_table", lambda: table)
    event = {"requestContext": {"http": {"method": "GET", "path": "/score/abc12345"}}}
    resp = instant_score.handler(event, None)
    assert resp["statusCode"] == 200
    assert "abc12345/latest.json" in resp["body"]
    assert '"grade": "B"' in resp["body"]


def test_instant_score_get_error_job_includes_message(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable({"status": "error", "message": "Could not score this feed."})
    monkeypatch.setattr(instant_score, "_jobs_table", lambda: table)
    event = {"requestContext": {"http": {"method": "GET", "path": "/score/abc12345"}}}
    resp = instant_score.handler(event, None)
    assert resp["statusCode"] == 200
    assert "Could not score this feed." in resp["body"]


def test_instant_score_get_pending_job_has_no_extra_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    table = FakeTable({"status": "pending"})
    monkeypatch.setattr(instant_score, "_jobs_table", lambda: table)
    event = {"requestContext": {"http": {"method": "GET", "path": "/score/abc12345"}}}
    resp = instant_score.handler(event, None)
    assert resp["statusCode"] == 200
    assert "grade" not in resp["body"]


# --- instant-score: _run_scoring_job never raises ---


def test_run_scoring_job_records_error_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(instant_score, "_prepare_runtime", lambda: None)
    table = FakeTable()

    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("network is down")

    monkeypatch.setattr("scorecard_pipeline.cli.run_adhoc", boom)
    monkeypatch.setattr(instant_score, "_jobs_table", lambda: table)
    instant_score._run_scoring_job("abc12345", "https://x.test/g.zip", "X")
    assert table.updated is True


def test_run_scoring_job_records_done_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(instant_score, "_prepare_runtime", lambda: None)
    table = FakeTable()
    artifact = {"overall": {"grade": "A"}}
    monkeypatch.setattr("scorecard_pipeline.cli.run_adhoc", lambda *a, **k: artifact)
    monkeypatch.setattr(instant_score, "_jobs_table", lambda: table)
    monkeypatch.setattr(
        instant_score,
        "_publish_result",
        lambda job_id, art: "https://gtfsscorecard.org/scratch/abc12345/latest.json",
    )
    instant_score._run_scoring_job("abc12345", "https://x.test/g.zip", "X")
    assert table.updated is True
