"""Alerts signup hardening: scanner-safe links, one-click unsubscribe headers,
the alerts Lambda's memory, the no-JavaScript form and the form's API errors.

Mail scanners (Safe Links, Proofpoint, Mimecast) open every link in an email
before the person does. While confirm and unsubscribe acted on a plain GET, a
scanner confirmed addresses on its own (the person then saw "Link not valid")
and could unsubscribe a reader from a digest they never meant to leave. These
tests hold the fix: a GET only shows a page with one button, the button POSTs,
and an already-confirmed link says so instead of calling itself invalid.
"""

from __future__ import annotations

import base64
import email
import email.policy
import importlib.util
import re
import sys
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


alerts = _load("infra/alerts/handler.py", "alerts_handler_hardening")


class RecordingTable:
    """A DynamoDB Table stand-in that keeps the row and records each write."""

    def __init__(self, item: dict[str, Any] | None = None) -> None:
        self.item = item
        self.updates: list[dict[str, Any]] = []
        self.deleted = False

    def get_item(self, Key: dict[str, Any]) -> dict[str, Any]:
        return {"Item": dict(self.item)} if self.item else {}

    def update_item(self, **kwargs: Any) -> None:
        self.updates.append(kwargs)

    def delete_item(self, Key: dict[str, Any]) -> None:
        self.deleted = True


def _event(method: str, path: str, query: str = "", body: str | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {
        "requestContext": {"http": {"method": method, "path": path}, "domainName": "api.example"},
        "rawQueryString": query,
    }
    if body is not None:
        event["body"] = base64.b64encode(body.encode()).decode()
        event["isBase64Encoded"] = True
    return event


def _use(monkeypatch: pytest.MonkeyPatch, table: RecordingTable) -> None:
    monkeypatch.setattr(alerts, "_table", lambda: table)


PENDING = {"email": "person@agency.gov", "verified": False, "token": "good", "unsub_token": "u1"}


# --- B: confirm -------------------------------------------------------------------


def test_opening_a_confirm_link_shows_a_button_and_confirms_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = RecordingTable(dict(PENDING))
    _use(monkeypatch, table)
    resp = alerts.handler(_event("GET", "/confirm", "email=person%40agency.gov&token=good"), None)
    assert resp["statusCode"] == 200
    page = resp["body"]
    assert table.updates == [], "a GET (what a mail scanner sends) must not confirm"
    assert "<h1>Confirm your feed-health alerts</h1>" in page
    assert "Press the button to start alerts for person@agency.gov." in page
    # The form posts back to the same address (no action attribute), so the
    # token in the link travels with the press and nowhere else.
    assert re.search(
        r"<form method=post>\s*<button type=submit[^>]*>Confirm my alerts</button>", page
    )
    assert "action=" not in page


def test_pressing_the_confirm_button_confirms_and_keeps_the_link_recognizable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = RecordingTable(dict(PENDING))
    _use(monkeypatch, table)
    resp = alerts.handler(_event("POST", "/confirm", "email=person%40agency.gov&token=good"), None)
    assert resp["statusCode"] == 200
    assert "<h1>You are subscribed</h1>" in resp["body"]
    (update,) = table.updates
    assert update["ExpressionAttributeValues"][":t"] is True
    # The used token is kept as confirmed_token, so opening the same link
    # again can say "you are subscribed" without the link becoming a way to
    # ask whether any address is subscribed.
    assert "confirmed_token" in update["UpdateExpression"]
    assert "good" in update["ExpressionAttributeValues"].values()


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_an_already_confirmed_link_says_you_are_subscribed(
    monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    table = RecordingTable(
        {"email": "person@agency.gov", "verified": True, "confirmed_token": "good"}
    )
    _use(monkeypatch, table)
    resp = alerts.handler(_event(method, "/confirm", "email=person%40agency.gov&token=good"), None)
    assert resp["statusCode"] == 200
    assert "<h1>You are subscribed</h1>" in resp["body"]
    assert "Link not valid" not in resp["body"]
    assert table.updates == []


@pytest.mark.parametrize("method", ["GET", "POST"])
def test_a_wrong_token_never_reveals_whether_an_address_is_subscribed(
    monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    table = RecordingTable(
        {"email": "person@agency.gov", "verified": True, "confirmed_token": "good"}
    )
    _use(monkeypatch, table)
    resp = alerts.handler(_event(method, "/confirm", "email=person%40agency.gov&token=guess"), None)
    assert resp["statusCode"] == 400
    assert "<h1>Link not valid</h1>" in resp["body"]
    assert "person@agency.gov" not in resp["body"]
    assert table.updates == []


# --- B: unsubscribe ---------------------------------------------------------------


def test_opening_an_unsubscribe_link_shows_a_button_and_removes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    table = RecordingTable({**PENDING, "verified": True})
    _use(monkeypatch, table)
    resp = alerts.handler(_event("GET", "/unsubscribe", "email=person%40agency.gov&token=u1"), None)
    assert resp["statusCode"] == 200
    page = resp["body"]
    assert table.deleted is False, "a GET (what a mail scanner sends) must not unsubscribe"
    assert "<h1>Stop feed-health alerts</h1>" in page
    assert "Press the button to stop all feed-health alerts to person@agency.gov." in page
    assert re.search(r"<form method=post>\s*<button type=submit[^>]*>Unsubscribe</button>", page)


def test_the_rfc_8058_one_click_post_unsubscribes(monkeypatch: pytest.MonkeyPatch) -> None:
    table = RecordingTable({**PENDING, "verified": True})
    _use(monkeypatch, table)
    resp = alerts.handler(
        _event(
            "POST",
            "/unsubscribe",
            "email=person%40agency.gov&token=u1",
            body="List-Unsubscribe=One-Click",
        ),
        None,
    )
    assert resp["statusCode"] == 200
    assert "<h1>Unsubscribed</h1>" in resp["body"]
    assert table.deleted is True


def test_a_wrong_unsubscribe_token_shows_no_button(monkeypatch: pytest.MonkeyPatch) -> None:
    table = RecordingTable({**PENDING, "verified": True})
    _use(monkeypatch, table)
    for method in ("GET", "POST"):
        resp = alerts.handler(
            _event(method, "/unsubscribe", "email=person%40agency.gov&token=nope"), None
        )
        assert resp["statusCode"] == 400
        assert "<form" not in resp["body"]
    assert table.deleted is False


def test_pages_that_carry_a_token_are_not_cached_or_referred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use(monkeypatch, RecordingTable(dict(PENDING)))
    resp = alerts.handler(_event("GET", "/confirm", "email=person%40agency.gov&token=good"), None)
    headers = resp["headers"]
    assert headers["Content-Type"].startswith("text/html")
    assert headers["Cache-Control"] == "no-store"
    assert headers["Referrer-Policy"] == "no-referrer"


def test_the_address_on_the_page_is_escaped(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stored addresses are restricted to plain characters, but the page must
    # not depend on that.
    odd = "a<b>@agency.gov"
    _use(monkeypatch, RecordingTable({**PENDING, "email": odd}))
    resp = alerts.handler(_event("GET", "/confirm", "email=a%3Cb%3E%40agency.gov&token=good"), None)
    assert "a&lt;b&gt;@agency.gov" in resp["body"]
    assert "a<b>" not in resp["body"]


# --- B: one-click unsubscribe headers on digests -------------------------------------


def test_digest_emails_carry_the_unsubscribe_address() -> None:
    from scorecard_pipeline.notify import Subscriber, _unsubscribe_link

    sub = Subscriber(
        email="person@agency.gov", agency_ids=None, verified=True, unsub_token="tok en"
    )
    link = _unsubscribe_link(sub, "https://api.example/")
    assert link == "https://api.example/unsubscribe?email=person%40agency.gov&token=tok%20en"
    assert _unsubscribe_link(sub, None) == ""
    assert _unsubscribe_link(Subscriber(email="x@y.io", agency_ids=None), "https://a") == ""


def test_send_via_ses_adds_rfc_8058_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    from scorecard_pipeline.notify import Email, send_via_ses

    raw: list[dict[str, Any]] = []
    plain: list[dict[str, Any]] = []

    class _Ses:
        def send_raw_email(self, **kwargs: Any) -> None:
            raw.append(kwargs)

        def send_email(self, **kwargs: Any) -> None:
            plain.append(kwargs)

    fake = types.ModuleType("boto3")
    fake.client = lambda *_a, **_kw: _Ses()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake)

    long_link = (
        "https://5oemr66b9a.execute-api.us-west-2.amazonaws.com/unsubscribe?email=person%40agency.gov&token="
        + "t" * 32
    )
    report = send_via_ses(
        [
            Email(
                to="person@agency.gov",
                subject="GTFS Scorecard: 1 feed needs attention",
                body="Hello\n",
                unsubscribe_url=long_link,
            ),
            Email(to="other@agency.gov", subject="s", body="b"),
        ],
        "alerts@gtfsscorecard.org",
    )
    assert (report.sent, report.failed) == (2, 0)
    assert len(plain) == 1, "an email with no unsubscribe link is sent as before"
    (call,) = raw
    assert call["Source"] == "alerts@gtfsscorecard.org"
    assert call["Destinations"] == ["person@agency.gov"]
    data: bytes = call["RawMessage"]["Data"]
    # The header must reach the mailbox provider unfolded and unencoded.
    assert f"List-Unsubscribe: <{long_link}>\r\n".encode() in data
    assert b"List-Unsubscribe-Post: List-Unsubscribe=One-Click\r\n" in data
    message = email.message_from_bytes(data, policy=email.policy.default)
    assert message["To"] == "person@agency.gov"
    assert message["From"] == "alerts@gtfsscorecard.org"
    assert message["Subject"] == "GTFS Scorecard: 1 feed needs attention"
    assert message.get_content().replace("\r\n", "\n") == "Hello\n"


# --- C: the alerts Lambda's memory ----------------------------------------------------


def test_the_alerts_lambda_has_512_mb() -> None:
    tf = (REPO / "infra" / "alerts" / "main.tf").read_text()
    block = tf.split('resource "aws_lambda_function" "alerts"', 1)[1].split("\n}\n", 1)[0]
    assert re.search(r"^\s*memory_size\s*=\s*512\s*$", block, re.M)


# --- D: the form without JavaScript --------------------------------------------------


def test_the_alerts_form_never_puts_the_address_in_a_url() -> None:
    page = (REPO / "web" / "subscribe.html").read_text()
    form = re.search(r"<form id=\"subscribe-form\"[^>]*>", page)
    assert form and 'method="post"' in form.group(0)
    assert "<noscript>" in page
    assert "Sending this form needs JavaScript. With it turned off, nothing is sent." in page


# --- E: the API's error codes ---------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        ({"email": "nope", "all": True}, "email"),
        ({"email": "a@b.io"}, "agency"),
        ({"email": "a@b.io", "agencies": ["Bad Slug!"]}, "agency"),
        ({"email": "a@b.io", "agencies": [f"a{n}" for n in range(60)]}, "agency"),
        ({"email": "a@b.io", "all": True, "kinds": ["nope"]}, "kinds"),
        ({"email": "a@b.io", "all": True, "kinds": []}, "kinds"),
    ],
)
def test_each_refusal_names_the_field_it_is_about(payload: dict[str, Any], code: str) -> None:
    with pytest.raises(alerts.BadRequest) as caught:
        alerts.validate_subscribe(payload)
    assert caught.value.code == code


def test_the_subscribe_route_returns_the_code_with_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(alerts, "_ip_rate_limited", lambda event: False)
    event = _event("POST", "/subscribe")
    event["body"] = '{"email": "a@b.io"}'
    resp = alerts.handler(event, None)
    assert resp["statusCode"] == 400
    assert '"code": "agency"' in resp["body"]


def test_a_repeat_within_the_cooldown_is_coded_for_the_form(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import time

    monkeypatch.setattr(alerts, "_ip_rate_limited", lambda event: False)
    _use(monkeypatch, RecordingTable({**PENDING, "requested_ts": int(time.time())}))
    event = _event("POST", "/subscribe")
    event["body"] = '{"email": "person@agency.gov", "all": true}'
    resp = alerts.handler(event, None)
    assert resp["statusCode"] == 429
    assert '"code": "cooldown"' in resp["body"]
