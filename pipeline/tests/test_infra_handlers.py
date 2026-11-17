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
import json
import sys
import time
import types
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
        self.put_item_value: dict[str, Any] | None = None
        self.updated = False
        self.deleted = False

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:
        return {"Item": self._item} if self._item else {}

    def update_item(self, **_: Any) -> None:
        self.updated = True

    def put_item(self, Item: dict[str, Any]) -> None:
        self.put_item_value = Item

    def delete_item(self, Key: dict[str, Any]) -> None:
        self.deleted = True


class FakeUrlResponse:
    """Context-managed byte response for urllib-backed handler tests."""

    def __init__(self, payload: object) -> None:
        self.body = json.dumps(payload).encode()

    def __enter__(self) -> FakeUrlResponse:
        return self

    def __exit__(self, *_: object) -> None:
        return None

    def read(self) -> bytes:
        return self.body


# --- alerts: validate_subscribe ---


def test_validate_subscribe_normalizes_email_and_defaults_kinds() -> None:
    out = alerts.validate_subscribe({"email": "  Agency@Example.ORG ", "all": True})
    assert out["email"] == "agency@example.org"
    assert out["all"] is True
    # Previously pinned ["expiry", "regression"], which pinned the bug: a subscriber who chose
    # nothing was stored an explicit closed list that permanently opted them out of the other
    # three kinds, contradicting the "omit for every kind" contract in subscriptions.yaml.
    assert out["kinds"] == ["expiry", "lapse_risk", "regression", "export_change", "anomaly"]


def test_handler_alert_kinds_match_the_digest_builder() -> None:
    """The subscribe form must not accept a narrower set than the digest can send.

    These two lists live in separate deployables -- the Lambda cannot import the pipeline package
    -- so nothing but this test stops them drifting. They did drift, and the failure was silent in
    the worst direction: the form kept accepting subscriptions while quietly recording consent to
    only two of five alert kinds, so the subscriber saw a success page and then never received
    three of the things they had asked about.
    """
    from scorecard_pipeline.notify import ALERT_KINDS as DIGEST_KINDS

    assert set(alerts.ALERT_KINDS) == set(DIGEST_KINDS)


def test_validate_subscribe_accepts_every_kind_the_digest_can_send() -> None:
    from scorecard_pipeline.notify import ALERT_KINDS as DIGEST_KINDS

    out = alerts.validate_subscribe(
        {"email": "a@example.org", "all": True, "kinds": sorted(DIGEST_KINDS)}
    )
    assert set(out["kinds"]) == set(DIGEST_KINDS)


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
    monkeypatch.setattr(submit, "_limits_table", FakeLimitsTable)
    event = _submit_event(SUBMIT_FORM, headers={"x-submit-token": "s3cret"})
    resp = submit.handler(event, None)
    assert resp["statusCode"] == 200
    assert "pull/1" in resp["body"]


# --- submit: size cap, strict fields, daily limits ---

SUBMIT_FORM = {"name": "New Transit", "static_gtfs_url": "https://example.org/new.zip"}


class FakeConditionalCheckFailed(Exception):
    """What boto3 raises when a ConditionExpression is false."""

    def __init__(self, code: str = "ConditionalCheckFailedException") -> None:
        super().__init__(code)
        self.response = {"Error": {"Code": code}}


class FakeLimitsTable:
    """The rate-limit table's conditional counter, in memory."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expires: dict[str, int] = {}

    def update_item(
        self,
        *,
        Key: dict[str, str],
        UpdateExpression: str,
        ConditionExpression: str,
        ExpressionAttributeNames: dict[str, str],
        ExpressionAttributeValues: dict[str, int],
    ) -> None:
        assert UpdateExpression.startswith("ADD #c :one")
        assert ConditionExpression == "attribute_not_exists(#c) OR #c < :cap"
        key = Key["key"]
        if self.counts.get(key, 0) >= ExpressionAttributeValues[":cap"]:
            raise FakeConditionalCheckFailed
        self.counts[key] = self.counts.get(key, 0) + ExpressionAttributeValues[":one"]
        self.expires.setdefault(key, ExpressionAttributeValues[":exp"])


def _submit_event(
    form: object,
    *,
    ip: str | None = "203.0.113.7",
    headers: dict[str, str] | None = None,
    body: str | None = None,
) -> dict[str, Any]:
    http: dict[str, Any] = {"method": "POST"}
    if ip is not None:
        http["sourceIp"] = ip
    return {
        "requestContext": {"http": http},
        "headers": headers or {},
        "body": json.dumps(form) if body is None else body,
    }


@pytest.fixture
def submit_env(monkeypatch: pytest.MonkeyPatch) -> tuple[FakeLimitsTable, list[dict[str, str]]]:
    """A limits table and a recorder in place of the GitHub conversation."""
    table = FakeLimitsTable()
    opened: list[dict[str, str]] = []

    def open_pull_request(form: dict[str, str]) -> str:
        opened.append(form)
        return f"https://github.com/owner/repo/pull/{len(opened)}"

    monkeypatch.delenv("SUBMIT_SHARED_SECRET", raising=False)
    monkeypatch.delenv("SUBMIT_CLIENT_DAILY_CAP", raising=False)
    monkeypatch.delenv("SUBMIT_GLOBAL_DAILY_CAP", raising=False)
    monkeypatch.setattr(submit, "_limits_table", lambda: table)
    monkeypatch.setattr(submit, "_open_pull_request", open_pull_request)
    return table, opened


def test_submit_passes_only_validated_fields_to_the_pull_request(
    submit_env: tuple[FakeLimitsTable, list[dict[str, str]]],
) -> None:
    _table, opened = submit_env
    form = SUBMIT_FORM | {"name": "  New Transit ", "rt_note": ""}
    resp = submit.handler(_submit_event(form), None)
    assert resp["statusCode"] == 200
    assert opened == [SUBMIT_FORM]


def test_submit_refuses_an_oversized_body_before_anything_else(
    submit_env: tuple[FakeLimitsTable, list[dict[str, str]]],
) -> None:
    table, opened = submit_env
    padded = json.dumps(SUBMIT_FORM | {"license_note": "a" * submit.MAX_BODY_BYTES})
    resp = submit.handler(_submit_event(None, body=padded), None)
    assert resp["statusCode"] == 413
    # Multi-byte text is measured in bytes, not characters.
    wide = json.dumps({"name": "東" * (submit.MAX_BODY_BYTES // 3 + 1)}, ensure_ascii=False)
    assert len(wide) < submit.MAX_BODY_BYTES
    assert submit.handler(_submit_event(None, body=wide), None)["statusCode"] == 413
    assert opened == []
    assert table.counts == {}


def test_submit_reads_a_base64_body_under_the_same_cap(
    submit_env: tuple[FakeLimitsTable, list[dict[str, str]]],
) -> None:
    _table, opened = submit_env
    encode = submit.base64.b64encode
    event = _submit_event(None, body=encode(json.dumps(SUBMIT_FORM).encode()).decode())
    event["isBase64Encoded"] = True
    assert submit.handler(event, None)["statusCode"] == 200
    assert opened == [SUBMIT_FORM]

    big = _submit_event(None, body=encode(b"a" * (submit.MAX_BODY_BYTES + 1)).decode())
    big["isBase64Encoded"] = True
    assert submit.handler(big, None)["statusCode"] == 413
    broken = _submit_event(None, body="not base64!!")
    broken["isBase64Encoded"] = True
    assert submit.handler(broken, None)["statusCode"] == 400
    assert len(opened) == 1


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        "null",
        "7",
        '"name"',
        "[" * 5000,
        '{"name": "New Transit", "static_gtfs_url": "https://example.org/new.zip", "extra": "x"}',
        '{"name": ["New Transit"], "static_gtfs_url": "https://example.org/new.zip"}',
        '{"name": "New Transit", "static_gtfs_url": "ftp://example.org/new.zip"}',
        '{"name": "New <b>Transit</b>", "static_gtfs_url": "https://example.org/new.zip"}',
        '{"name": "New Transit"}',
        "{}",
    ],
)
def test_submit_refuses_a_malformed_submission_without_counting_it(
    submit_env: tuple[FakeLimitsTable, list[dict[str, str]]], body: str
) -> None:
    table, opened = submit_env
    resp = submit.handler(_submit_event(None, body=body), None)
    assert resp["statusCode"] == 400
    assert json.loads(resp["body"])["ok"] is False
    assert opened == []
    assert table.counts == {}


def test_submit_caps_one_client_per_day(
    submit_env: tuple[FakeLimitsTable, list[dict[str, str]]],
) -> None:
    _table, opened = submit_env
    statuses = [
        submit.handler(_submit_event(SUBMIT_FORM, ip="203.0.113.7"), None)["statusCode"]
        for _ in range(submit.DEFAULT_CLIENT_DAILY_CAP + 2)
    ]
    assert statuses == [200] * submit.DEFAULT_CLIENT_DAILY_CAP + [429, 429]
    assert len(opened) == submit.DEFAULT_CLIENT_DAILY_CAP
    # Another client still has its own allowance.
    assert submit.handler(_submit_event(SUBMIT_FORM, ip="198.51.100.9"), None)["statusCode"] == 200


def test_submit_caps_all_clients_together_per_day(
    submit_env: tuple[FakeLimitsTable, list[dict[str, str]]], monkeypatch: pytest.MonkeyPatch
) -> None:
    table, opened = submit_env
    monkeypatch.setenv("SUBMIT_GLOBAL_DAILY_CAP", "4")
    statuses = [
        submit.handler(_submit_event(SUBMIT_FORM, ip=f"203.0.113.{n}"), None)["statusCode"]
        for n in range(1, 8)
    ]
    assert statuses == [200, 200, 200, 200, 429, 429, 429]
    assert len(opened) == 4
    (global_key,) = [key for key in table.counts if key.startswith("submit#all#")]
    assert table.counts[global_key] == 4


def test_a_client_over_its_own_cap_does_not_use_up_the_global_one(
    submit_env: tuple[FakeLimitsTable, list[dict[str, str]]],
) -> None:
    table, _opened = submit_env
    for _ in range(submit.DEFAULT_CLIENT_DAILY_CAP + 10):
        submit.handler(_submit_event(SUBMIT_FORM, ip="203.0.113.7"), None)
    (global_key,) = [key for key in table.counts if key.startswith("submit#all#")]
    assert table.counts[global_key] == submit.DEFAULT_CLIENT_DAILY_CAP


def test_requests_with_no_source_address_share_one_allowance(
    submit_env: tuple[FakeLimitsTable, list[dict[str, str]]],
) -> None:
    statuses = [
        submit.handler(_submit_event(SUBMIT_FORM, ip=None), None)["statusCode"]
        for _ in range(submit.DEFAULT_CLIENT_DAILY_CAP + 1)
    ]
    assert statuses == [200] * submit.DEFAULT_CLIENT_DAILY_CAP + [429]


def test_submit_limit_keys_hold_no_address_and_expire(
    submit_env: tuple[FakeLimitsTable, list[dict[str, str]]],
) -> None:
    table, _opened = submit_env
    before = int(time.time())
    submit.handler(_submit_event(SUBMIT_FORM, ip="203.0.113.7"), None)
    assert len(table.counts) == 2
    for key, expires_at in table.expires.items():
        assert key.startswith(("submit#client#", "submit#all#"))
        assert "203.0.113.7" not in key
        assert before < expires_at <= before + 2 * 86400
    day_one = submit._client_key(_submit_event(SUBMIT_FORM), "2026-11-17")
    day_two = submit._client_key(_submit_event(SUBMIT_FORM), "2026-11-18")
    assert day_one.rsplit("#", 1)[1] != day_two.rsplit("#", 1)[1]


def test_submit_is_refused_when_the_limits_cannot_be_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[dict[str, str]] = []

    def open_pull_request(form: dict[str, str]) -> str:
        opened.append(form)
        return "https://github.com/owner/repo/pull/1"

    monkeypatch.delenv("SUBMIT_SHARED_SECRET", raising=False)
    monkeypatch.setattr(submit, "_open_pull_request", open_pull_request)

    # No table configured at all.
    monkeypatch.delenv("RATELIMIT_TABLE", raising=False)
    resp = submit.handler(_submit_event(SUBMIT_FORM), None)
    assert resp["statusCode"] == 503
    assert "paused" in json.loads(resp["body"])["error"]

    # A table that answers with an error other than "cap reached".
    class Throttled:
        def update_item(self, **_kwargs: Any) -> None:
            raise FakeConditionalCheckFailed("ProvisionedThroughputExceededException")

    monkeypatch.setattr(submit, "_limits_table", Throttled)
    assert submit.handler(_submit_event(SUBMIT_FORM), None)["statusCode"] == 503

    class Unreachable:
        def update_item(self, **_kwargs: Any) -> None:
            raise OSError("network unreachable")

    monkeypatch.setattr(submit, "_limits_table", Unreachable)
    assert submit.handler(_submit_event(SUBMIT_FORM), None)["statusCode"] == 503
    assert opened == []


@pytest.mark.parametrize("value", ["", "0", "-3", "many", "2.5"])
def test_a_cap_that_is_not_a_positive_whole_number_falls_back_to_the_default(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("SUBMIT_CLIENT_DAILY_CAP", value)
    assert submit._cap("SUBMIT_CLIENT_DAILY_CAP", 3) == 3


def test_submit_module_grants_only_the_counter_update_and_sets_the_limits() -> None:
    terraform = (REPO / "infra/submit/main.tf").read_text(encoding="utf-8")
    assert 'Action   = ["dynamodb:UpdateItem"]' in terraform
    assert "Resource = data.aws_dynamodb_table.ratelimit.arn" in terraform
    for name in ("RATELIMIT_TABLE", "SUBMIT_CLIENT_DAILY_CAP", "SUBMIT_GLOBAL_DAILY_CAP"):
        assert name in terraform
    assert terraform.count("dynamodb:") == 1


def test_submit_tracked_ids_reads_only_valid_published_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {
        "agencies": [
            {"id": "unitrans"},
            {"id": ""},
            {"id": 7},
            "not-an-entry",
            {"id": "yolobus"},
        ]
    }
    monkeypatch.setattr(
        submit.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeUrlResponse(payload)
    )

    assert submit._tracked_ids() == {"unitrans", "yolobus"}


def test_submit_tracked_ids_fails_closed_to_intake_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise OSError("offline")

    monkeypatch.setattr(submit.urllib.request, "urlopen", unavailable)

    assert submit._tracked_ids() == set()


def test_submit_pull_request_updates_only_the_intake_shard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "test-token")
    monkeypatch.setenv("GITHUB_REPO", "owner/repo")
    intake = (
        "agencies:\n"
        "  - id: existing\n"
        "    name: Existing\n"
        "    static_gtfs_url: https://example.org/existing.zip\n"
    )
    calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def fake_gh(
        method: str,
        path: str,
        token: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert token == "test-token"
        calls.append((method, path, payload))
        if method == "GET" and "/contents/" in path:
            return {
                "content": submit.base64.b64encode(intake.encode()).decode(),
                "sha": "intake-sha",
            }
        if method == "GET":
            return {"object": {"sha": "head-sha"}}
        if path.endswith("/pulls"):
            return {"html_url": "https://github.com/owner/repo/pull/1"}
        return {}

    monkeypatch.setattr(submit, "_gh", fake_gh)
    monkeypatch.setattr(submit, "_tracked_ids", lambda: {"curated-elsewhere"})

    url = submit._open_pull_request(
        {"name": "New Transit", "static_gtfs_url": "https://example.org/new.zip"}
    )

    assert url.endswith("/pull/1")
    content_calls = [call for call in calls if "/contents/" in call[1]]
    assert [call[:2] for call in content_calls] == [
        ("GET", "/repos/owner/repo/contents/registry/intake.yaml?ref=main"),
        ("PUT", "/repos/owner/repo/contents/registry/intake.yaml"),
    ]
    # Every request path is built from configuration alone. What was submitted
    # travels only inside JSON bodies, and the one name derived from it (the
    # branch) is a slug.
    assert [call[:2] for call in calls] == [
        ("GET", "/repos/owner/repo/contents/registry/intake.yaml?ref=main"),
        ("GET", "/repos/owner/repo/git/ref/heads/main"),
        ("POST", "/repos/owner/repo/git/refs"),
        ("PUT", "/repos/owner/repo/contents/registry/intake.yaml"),
        ("POST", "/repos/owner/repo/pulls"),
    ]
    payloads = {path: payload for _method, path, payload in calls if payload}
    assert payloads["/repos/owner/repo/git/refs"]["ref"] == "refs/heads/submit-new-transit"
    assert payloads["/repos/owner/repo/pulls"]["head"] == "submit-new-transit"
    assert payloads["/repos/owner/repo/pulls"]["base"] == "main"


# --- instant-score: validate_score_request ---


def test_validate_score_request_normalizes_url_and_name() -> None:
    out = instant_score.validate_score_request(
        {"url": "  https://example.org/gtfs.zip  ", "name": "  Demo  "}
    )
    assert out == {
        "url": "https://example.org/gtfs.zip",
        "name": "Demo",
        "country": "US",
    }


def test_validate_score_request_normalizes_an_assigned_country() -> None:
    out = instant_score.validate_score_request(
        {"url": "https://example.org/gtfs.zip", "country": " ca "}
    )
    assert out["country"] == "CA"


def test_validate_score_request_rejects_unassigned_country_codes() -> None:
    for country in ("ZZ", "UK", "USA", 7):
        with pytest.raises(instant_score.BadRequest, match="country"):
            instant_score.validate_score_request(
                {"url": "https://example.org/gtfs.zip", "country": country}
            )


def test_instant_score_country_codes_match_the_packaged_iso_vocabulary() -> None:
    source = json.loads((REPO / "pipeline/src/scorecard_pipeline/data/iso3166.json").read_text())
    assert frozenset(source["countries"]) == instant_score._ASSIGNED_COUNTRY_CODES


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
        lambda job_id, url, name, country: calls.append((job_id, url, name, country)),
    )
    result = instant_score.handler(
        {
            "job_id": "abc123",
            "url": "https://x.test/g.zip",
            "name": "X",
            "country": "CA",
        },
        None,
    )
    assert result is None
    assert calls == [("abc123", "https://x.test/g.zip", "X", "CA")]


def test_instant_score_async_legacy_event_defaults_to_us(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    monkeypatch.setattr(
        instant_score,
        "_run_scoring_job",
        lambda job_id, url, name, country: calls.append(country),
    )
    instant_score.handler({"job_id": "abc123", "url": "https://x.test/g.zip", "name": "X"}, None)
    assert calls == ["US"]


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
        lambda job_id, url, name, country: started.append((job_id, url, name, country)),
    )
    body = '{"url": "https://x.test/g.zip", "name": "X Transit", "country": "nz"}'
    resp = instant_score.handler(
        {"requestContext": {"http": {"method": "POST"}}, "body": body}, None
    )
    assert resp["statusCode"] == 202
    assert len(started) == 1
    job_id, url, name, country = started[0]
    assert instant_score._JOB_ID_RE.match(job_id)
    assert url == "https://x.test/g.zip"
    assert name == "X Transit"
    assert country == "NZ"
    assert job_id in resp["body"]


def test_start_scoring_carries_country_into_the_async_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = FakeTable()
    invoked: dict[str, Any] = {}

    class FakeLambdaClient:
        def invoke(self, **kwargs: Any) -> None:
            invoked.update(kwargs)

    fake_boto3 = types.ModuleType("boto3")
    fake_boto3.__dict__["client"] = lambda *args, **kwargs: FakeLambdaClient()
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)
    monkeypatch.setattr(instant_score, "_jobs_table", lambda: table)
    monkeypatch.setenv("FUNCTION_NAME", "instant-score")

    instant_score._start_scoring("abc12345", "https://x.test/g.zip", "X Transit", "CA")

    assert table.put_item_value is not None
    assert table.put_item_value["country"] == "CA"
    assert json.loads(invoked["Payload"])["country"] == "CA"


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
    calls = []

    def score(url: str, name: str, date: object, *, country: str) -> dict[str, Any]:
        calls.append((url, name, date, country))
        return artifact

    monkeypatch.setattr("scorecard_pipeline.cli.run_adhoc", score)
    monkeypatch.setattr(instant_score, "_jobs_table", lambda: table)
    monkeypatch.setattr(
        instant_score,
        "_publish_result",
        lambda job_id, art: "https://gtfsscorecard.org/scratch/abc12345/latest.json",
    )
    instant_score._run_scoring_job("abc12345", "https://x.test/g.zip", "X", "NZ")
    assert table.updated is True
    assert calls[0][3] == "NZ"
