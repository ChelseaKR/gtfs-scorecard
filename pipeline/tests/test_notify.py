"""Tests for per-subscriber feed-health email digests."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from scorecard_pipeline.alerts import AlertItem, Digest, build_digest
from scorecard_pipeline.config import artifacts_dir
from scorecard_pipeline.notify import (
    ALERT_KINDS,
    EMAIL_RE,
    SubscriptionError,
    build_emails,
    build_portfolio_emails,
    build_webhook_notifications,
    parse_subscribers,
    personal_digest,
    send_webhooks,
    subscriber_from_item,
    verification_email,
)
from scorecard_pipeline.portfolio_digest import PortfolioDigest


def test_email_regex_rejects_url_significant_characters() -> None:
    assert EMAIL_RE.match("agency@example.org")
    assert EMAIL_RE.match("first.last+tag@sub.example.co")
    # Characters that could smuggle query/URL syntax into a confirm link.
    for bad in ("a&b@x.io", "a?b@x.io", "a#b@x.io", "a/b@x.io", "a b@x.io", "a%40b@x.io"):
        assert not EMAIL_RE.match(bad), bad


def _item(agency_id: str, name: str, kind: str = "expiry") -> AlertItem:
    return AlertItem(
        agency_id=agency_id,
        agency_name=name,
        kind=kind,
        headline="Service data has expired",
        detail="The schedule stopped covering service.",
        fix="Re-export with a longer calendar.",
    )


def _digest() -> Digest:
    return Digest(
        as_of=dt.date(2026, 6, 16),
        items=[_item("unitrans", "Unitrans"), _item("merced", "Merced")],
    )


def test_parse_valid_and_all() -> None:
    subs = parse_subscribers(
        {
            "subscribers": [
                {"email": "a@example.org", "agencies": ["unitrans"]},
                {"email": "b@example.org", "all": True},
            ]
        }
    )
    assert subs[0].agency_ids == frozenset({"unitrans"})
    assert subs[1].agency_ids is None
    assert subs[1].follows("anything")


@pytest.mark.parametrize(
    "raw",
    [
        {"subscribers": [{"email": "not-an-email", "agencies": ["x"]}]},
        {"subscribers": [{"email": "a@example.org"}]},  # no agencies, no all
        {
            "subscribers": [
                {"email": "a@example.org", "agencies": ["x"]},
                {"email": "a@example.org", "all": True},
            ]
        },
        {"nope": []},
    ],
)
def test_parse_rejects_bad_input(raw: dict[str, object]) -> None:
    with pytest.raises(SubscriptionError):
        parse_subscribers(raw)


def test_personal_digest_filters_to_followed() -> None:
    sub = parse_subscribers({"subscribers": [{"email": "a@example.org", "agencies": ["merced"]}]})[
        0
    ]
    personal = personal_digest(sub, _digest())
    assert [i.agency_id for i in personal.items] == ["merced"]


def test_build_emails_skips_all_clear_and_renders() -> None:
    subs = parse_subscribers(
        {
            "subscribers": [
                {"email": "follows@example.org", "agencies": ["merced"], "verified": True},
                {"email": "healthy@example.org", "agencies": ["someone-else"], "verified": True},
            ]
        }
    )
    emails = build_emails(subs, _digest())
    # Only the subscriber with a matching item gets mail; the all-clear is silence.
    assert len(emails) == 1
    assert emails[0].to == "follows@example.org"
    assert "1 feed needs attention" in emails[0].subject
    assert "Merced" in emails[0].body


def test_unsubscribe_footer_added_when_base_set() -> None:
    import dataclasses

    parsed = parse_subscribers(
        {
            "subscribers": [
                {"email": "follows@example.org", "agencies": ["merced"], "verified": True}
            ]
        }
    )
    subs = [dataclasses.replace(parsed[0], unsub_token="abc")]
    emails = build_emails(subs, _digest(), unsubscribe_base="https://api.example.org/")
    # The address is URL-encoded in the link so it can't smuggle query syntax.
    assert "/unsubscribe?email=follows%40example.org&token=abc" in emails[0].body
    # No base -> no footer
    plain = build_emails(subs, _digest())
    assert "unsubscribe" not in plain[0].body.lower()


def test_unverified_subscriber_is_never_emailed() -> None:
    # Same as above but unverified (the default): the consent gate keeps it silent.
    subs = parse_subscribers(
        {"subscribers": [{"email": "follows@example.org", "agencies": ["merced"]}]}
    )
    assert subs[0].verified is False
    assert build_emails(subs, _digest()) == []


def test_kinds_opt_in_filters_alert_kinds() -> None:
    digest = Digest(
        as_of=dt.date(2026, 6, 16),
        items=[
            _item("unitrans", "Unitrans", kind="expiry"),
            _item("unitrans", "Unitrans", kind="regression"),
        ],
    )
    sub = parse_subscribers(
        {"subscribers": [{"email": "a@example.org", "agencies": ["unitrans"], "kinds": ["expiry"]}]}
    )[0]
    assert sub.kinds == frozenset({"expiry"})
    personal = personal_digest(sub, digest)
    assert [i.kind for i in personal.items] == ["expiry"]


def test_parse_rejects_unknown_kind() -> None:
    with pytest.raises(SubscriptionError):
        parse_subscribers(
            {"subscribers": [{"email": "a@example.org", "all": True, "kinds": ["bogus"]}]}
        )


def test_subscriber_from_dynamo_item() -> None:
    # boto3 resource form: native sets and bools.
    all_sub = subscriber_from_item({"email": "liaison@x.org", "all": True, "verified": True})
    assert all_sub.agency_ids is None and all_sub.verified is True

    one = subscriber_from_item(
        {
            "email": "a@x.org",
            "agencies": {"unitrans"},
            "kinds": {"expiry"},
            "verified": True,
            "unsub_token": "utok",
        }
    )
    assert one.agency_ids == frozenset({"unitrans"})
    assert one.kinds == frozenset({"expiry"})
    assert one.unsub_token == "utok"

    # missing verified defaults to false (the consent gate's safe default)
    pending = subscriber_from_item({"email": "b@x.org", "agencies": {"yolobus"}})
    assert pending.verified is False


def test_parse_accepts_https_webhook_url() -> None:
    sub = parse_subscribers(
        {
            "subscribers": [
                {
                    "email": "a@example.org",
                    "all": True,
                    "webhook_url": "https://hooks.example.org/services/T00/B00/xyz",
                }
            ]
        }
    )[0]
    assert sub.webhook_url == "https://hooks.example.org/services/T00/B00/xyz"


def test_parse_defaults_webhook_url_to_empty() -> None:
    sub = parse_subscribers({"subscribers": [{"email": "a@example.org", "all": True}]})[0]
    assert sub.webhook_url == ""


def test_parse_rejects_non_https_webhook_url() -> None:
    with pytest.raises(SubscriptionError):
        parse_subscribers(
            {
                "subscribers": [
                    {
                        "email": "a@example.org",
                        "all": True,
                        "webhook_url": "http://hooks.example.org/x",
                    }
                ]
            }
        )


def test_subscriber_from_dynamo_item_reads_webhook_url() -> None:
    sub = subscriber_from_item(
        {"email": "a@x.org", "all": True, "webhook_url": "https://hooks.example.org/x"}
    )
    assert sub.webhook_url == "https://hooks.example.org/x"

    # A non-https value in the store is dropped, not trusted or raised.
    bad = subscriber_from_item(
        {"email": "b@x.org", "all": True, "webhook_url": "javascript:alert(1)"}
    )
    assert bad.webhook_url == ""


def test_build_webhook_notifications_skips_all_clear_and_renders() -> None:
    subs = parse_subscribers(
        {
            "subscribers": [
                {
                    "email": "follows@example.org",
                    "agencies": ["merced"],
                    "verified": True,
                    "webhook_url": "https://hooks.example.org/a",
                },
                {
                    "email": "healthy@example.org",
                    "agencies": ["someone-else"],
                    "verified": True,
                    "webhook_url": "https://hooks.example.org/b",
                },
            ]
        }
    )
    notes = build_webhook_notifications(subs, _digest())
    assert len(notes) == 1
    assert notes[0].url == "https://hooks.example.org/a"
    assert "Merced" in notes[0].payload["text"]


def test_build_webhook_notifications_skips_unverified_and_no_webhook() -> None:
    subs = parse_subscribers(
        {
            "subscribers": [
                # verified, but no webhook_url set.
                {"email": "a@example.org", "agencies": ["merced"], "verified": True},
                # a webhook_url set, but unverified.
                {
                    "email": "b@example.org",
                    "agencies": ["merced"],
                    "webhook_url": "https://hooks.example.org/a",
                },
            ]
        }
    )
    assert build_webhook_notifications(subs, _digest()) == []


def test_send_webhooks_skips_a_non_public_url_without_posting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import requests

    from scorecard_pipeline.notify import WebhookNotification

    posted: list[str] = []
    monkeypatch.setattr(requests, "post", lambda url, **_kw: posted.append(url))
    # A private-IP-literal URL needs no DNS lookup and is rejected by the same
    # SSRF guard every feed fetch uses (net.validate_public_url).
    notes = [WebhookNotification(url="https://10.0.0.5/hook", payload={"text": "x"})]
    assert send_webhooks(notes) == 0
    assert posted == []  # never attempted


def test_send_webhooks_posts_to_a_public_url_and_counts_it(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    from scorecard_pipeline.notify import WebhookNotification

    calls: list[tuple[str, dict[str, object]]] = []

    def fake_post(url: str, json: dict[str, object], **_kw: object) -> None:
        calls.append((url, json))

    monkeypatch.setattr(requests, "post", fake_post)
    # 93.184.216.34 (example.com) is publicly routable; no DNS needed in the test.
    notes = [WebhookNotification(url="https://93.184.216.34/hook", payload={"text": "hi"})]
    assert send_webhooks(notes) == 1
    assert calls == [("https://93.184.216.34/hook", {"text": "hi"})]


def test_send_webhooks_skips_a_failed_post_without_stopping_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import requests

    from scorecard_pipeline.notify import WebhookNotification

    def fake_post(url: str, **_kw: object) -> None:
        if url.endswith("/broken"):
            raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(requests, "post", fake_post)
    notes = [
        WebhookNotification(url="https://93.184.216.34/broken", payload={"text": "a"}),
        WebhookNotification(url="https://93.184.216.34/ok", payload={"text": "b"}),
    ]
    assert send_webhooks(notes) == 1


def test_verification_email_contains_tokenized_confirm_link() -> None:
    email = verification_email("manager@agency.gov", "tok123")
    assert email.to == "manager@agency.gov"
    assert "/confirm?token=tok123" in email.body
    assert "ignore this email" in email.body


# ---------------------------------------------------------------------------
# Anomaly-digest integration tests
# These tests drive build_digest (in alerts.py) with fixture histories and
# verify that score-cliff anomalies surface in the digest while transient
# dips (one-day glitches that bounced back) are suppressed.
# ---------------------------------------------------------------------------


def _write_index(entries: dict) -> None:  # type: ignore[type-arg]
    """Write a minimal index.json to the isolated artifacts directory."""
    path = artifacts_dir() / "index.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"schema_version": "1.1", "agencies": entries}))


def test_score_cliff_appears_in_digest() -> None:
    """A 20+ point drop in one step (that is not a transient dip) becomes an
    anomaly AlertItem with kind='anomaly' in the built digest."""
    _write_index(
        {
            "cliffside": {
                "name": "Cliffside Transit",
                "history": [
                    {"date": "2026-06-10", "score": 85.0, "grade": "B", "days_until_expiry": 120},
                    # 25-point drop — above the SCORE_CLIFF_POINTS threshold
                    {"date": "2026-06-11", "score": 60.0, "grade": "D", "days_until_expiry": 119},
                    # stays down, so not a transient dip
                    {"date": "2026-06-12", "score": 59.0, "grade": "D", "days_until_expiry": 118},
                ],
            }
        }
    )
    digest = build_digest(today=dt.date(2026, 6, 12))
    anomaly_items = [i for i in digest.items if i.kind == "anomaly"]
    assert anomaly_items, "expected at least one anomaly item in the digest"
    assert anomaly_items[0].agency_id == "cliffside"
    assert "2026-06-11" in anomaly_items[0].headline


def test_transient_dip_does_not_appear_in_digest() -> None:
    """A one-day score dip that fully recovered the next day is noise. It
    should not produce any anomaly item in the digest."""
    _write_index(
        {
            "bouncy": {
                "name": "Bouncy Transit",
                "history": [
                    {"date": "2026-06-10", "score": 85.0, "grade": "B", "days_until_expiry": 120},
                    # drops hard for one day — this is the transient dip
                    {"date": "2026-06-11", "score": 40.0, "grade": "F", "days_until_expiry": 119},
                    # recovers fully the next day
                    {"date": "2026-06-12", "score": 84.0, "grade": "B", "days_until_expiry": 118},
                ],
            }
        }
    )
    digest = build_digest(today=dt.date(2026, 6, 12))
    anomaly_items = [i for i in digest.items if i.kind == "anomaly"]
    assert anomaly_items == [], (
        "transient dip that recovered should not produce an anomaly digest item"
    )


def test_anomaly_kind_is_subscriber_optable() -> None:
    """'anomaly' is in ALERT_KINDS so subscribers can opt into (or out of)
    anomaly alerts explicitly, just like 'expiry' and 'regression'."""
    assert "anomaly" in ALERT_KINDS


def test_subscriber_kinds_filter_anomaly_items() -> None:
    """A subscriber with kinds=['expiry'] does not receive anomaly items even
    when they follow the agency."""
    digest = Digest(
        as_of=dt.date(2026, 6, 16),
        items=[
            AlertItem(
                agency_id="unitrans",
                agency_name="Unitrans",
                kind="anomaly",
                headline="Score changed sharply on 2026-06-15",
                detail="The score fell 25 points in one step.",
                fix="Check for feed changes.",
                scorecard_url="https://gtfsscorecard.org/agency/unitrans/",
            ),
            _item("unitrans", "Unitrans", kind="expiry"),
        ],
    )
    sub = parse_subscribers(
        {"subscribers": [{"email": "a@example.org", "agencies": ["unitrans"], "kinds": ["expiry"]}]}
    )[0]
    personal = personal_digest(sub, digest)
    assert [i.kind for i in personal.items] == ["expiry"]


# ---------------------------------------------------------------------------
# Portfolio (cohort rollup) digest opt-in — the consent-model extension.
# ---------------------------------------------------------------------------


def _portfolio_digest(rollup_id: str = "all", member_count: int = 3) -> PortfolioDigest:
    # A steady (all-clear) weekly digest is still sent on the schedule.
    return PortfolioDigest(
        rollup_id=rollup_id,
        rollup_name="All tracked agencies",
        as_of=dt.date(2026, 6, 19),
        first_run=False,
        member_count=member_count,
        movements=[],
        snapshot={},
    )


def test_parse_rollups_field() -> None:
    sub = parse_subscribers(
        {"subscribers": [{"email": "a@example.org", "all": True, "rollups": ["all", "ca"]}]}
    )[0]
    assert sub.rollup_ids == frozenset({"all", "ca"})
    assert sub.follows_rollup("ca")
    assert not sub.follows_rollup("nv")


def test_rollups_field_defaults_to_none() -> None:
    sub = parse_subscribers({"subscribers": [{"email": "b@example.org", "all": True}]})[0]
    assert sub.rollup_ids is None
    assert not sub.follows_rollup("all")


def test_parse_rejects_empty_rollups() -> None:
    with pytest.raises(SubscriptionError):
        parse_subscribers({"subscribers": [{"email": "a@example.org", "all": True, "rollups": []}]})


def test_subscriber_from_item_parses_rollups() -> None:
    sub = subscriber_from_item(
        {"email": "liaison@x.org", "all": True, "rollups": {"all"}, "verified": True}
    )
    assert sub.rollup_ids == frozenset({"all"})


def test_build_portfolio_emails_for_opted_in_verified() -> None:
    subs = parse_subscribers(
        {
            "subscribers": [
                {"email": "liaison@example.org", "all": True, "rollups": ["all"], "verified": True}
            ]
        }
    )
    emails = build_portfolio_emails(subs, {"all": _portfolio_digest()})
    assert len(emails) == 1
    assert emails[0].to == "liaison@example.org"
    assert "portfolio digest" in emails[0].subject
    # A steady week still sends the reassuring all-clear (unlike the alert path).
    assert "held steady" in emails[0].body


def test_build_portfolio_emails_skips_unverified() -> None:
    # Same subscriber but unverified (the default): the consent gate keeps it silent.
    subs = parse_subscribers(
        {"subscribers": [{"email": "liaison@example.org", "all": True, "rollups": ["all"]}]}
    )
    assert subs[0].verified is False
    assert build_portfolio_emails(subs, {"all": _portfolio_digest()}) == []


def test_build_portfolio_emails_skips_when_not_opted_in() -> None:
    # Verified, follows every agency for alerts, but did not opt into any rollup.
    subs = parse_subscribers(
        {"subscribers": [{"email": "a@example.org", "all": True, "verified": True}]}
    )
    assert build_portfolio_emails(subs, {"all": _portfolio_digest()}) == []


def test_build_portfolio_emails_only_sends_subscribed_rollups() -> None:
    subs = parse_subscribers(
        {
            "subscribers": [
                {"email": "a@example.org", "all": True, "rollups": ["ca"], "verified": True}
            ]
        }
    )
    # The only digest built this week is for a rollup the subscriber did not opt into.
    assert build_portfolio_emails(subs, {"all": _portfolio_digest()}) == []
