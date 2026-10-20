"""The robots.txt rules every feed request follows (ADR 0070)."""

from __future__ import annotations

from typing import Any

import pytest

from scorecard_pipeline import robots_policy as rp
from scorecard_pipeline.robots_policy import (
    RobotsChecker,
    RobotsRefusedError,
    RobotsResponse,
    allowlisted_403,
    classify_robots_response,
    robots_url,
)

TARGET = "https://feeds.example/agency/gtfs.zip"
RULES = "https://feeds.example/robots.txt"


def _classify(
    status: int,
    body: str = "",
    *,
    target: str = TARGET,
    final_url: str | None = None,
    content_type: str = "text/plain",
) -> rp.RobotsVerdict:
    return classify_robots_response(
        target_url=target,
        status=status,
        final_url=final_url or robots_url(target) or RULES,
        content_type=content_type,
        body=body,
    )


def test_user_agent_identifies_the_project_and_is_never_a_browser() -> None:
    assert rp.USER_AGENT.startswith("gtfs-scorecard/")
    assert "(+https://" in rp.USER_AGENT
    for browser_token in ("Mozilla", "Chrome", "Safari", "Gecko", "AppleWebKit"):
        assert browser_token not in rp.USER_AGENT


@pytest.mark.parametrize("status", [404, 410])
def test_a_missing_rules_file_is_no_rules(status: int) -> None:
    assert _classify(status) == rp.RobotsVerdict(True, rp.NO_ROBOTS_FILE)


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_an_error_at_robots_is_off_limits_off_the_allowlist(status: int) -> None:
    verdict = _classify(status)
    assert (verdict.allowed, verdict.reason) == (False, f"robots_status_{status}")
    assert verdict.not_fetched_reason == rp.NOT_FETCHED_OFF_LIMITS


@pytest.mark.parametrize(
    "url",
    [
        "https://s3.amazonaws.com/bucket/feed.zip",
        "https://mdotmta-gtfs.s3.amazonaws.com/feed.zip",
        "https://ctb-gtfs.s3.eu-south-2.amazonaws.com/feed.zip",
        "https://s3.eu-west-1.amazonaws.com/bucket/feed.zip",
        "https://storage.googleapis.com/bucket/feed.zip",
        "https://tvv.fra1.digitaloceanspaces.com/feed.zip",
        "https://api.gtfs-data.jp/v2/organizations/x/feeds/y/files/feed.zip",
        "https://gtfs.remix.com/agency.zip",
    ],
)
def test_a_403_on_an_object_store_or_api_host_is_no_file(url: str) -> None:
    assert _classify(403, target=url) == rp.RobotsVerdict(True, rp.MISSING_OBJECT_403)


def test_negative_control_the_allowlist_is_what_admits_a_403() -> None:
    """The same 403 on an unlisted host stays off-limits."""
    url = "https://www.city.example/feed.zip"
    assert allowlisted_403("www.city.example") is None
    assert not _classify(403, target=url).allowed
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            rp,
            "MISSING_OBJECT_403_HOSTS",
            (*rp.MISSING_OBJECT_403_HOSTS, rp.AllowlistedHost("www.city.example", "test")),
        )
        assert allowlisted_403("www.city.example") is not None  # the sabotage landed
        assert _classify(403, target=url).allowed


def test_the_allowlist_admits_only_403_not_other_errors_or_lookalikes() -> None:
    s3 = "https://bucket.s3.amazonaws.com/feed.zip"
    assert not _classify(500, target=s3).allowed
    assert not _classify(401, target=s3).allowed
    assert allowlisted_403("amazonaws.com.evil.example") is None
    assert allowlisted_403("evil-s3.amazonaws.com.example") is None


def test_every_allowlist_entry_states_its_reason() -> None:
    patterns = [entry.pattern for entry in rp.MISSING_OBJECT_403_HOSTS]
    assert len(patterns) == len(set(patterns))
    for entry in rp.MISSING_OBJECT_403_HOSTS:
        assert entry.pattern == entry.pattern.lower()
        assert len(entry.reason) > 20


def test_explicit_disallow_is_obeyed_and_named() -> None:
    verdict = _classify(200, "User-agent: *\nDisallow: /agency/\n")
    assert verdict == rp.RobotsVerdict(False, rp.DISALLOWED_BY_ROBOTS)
    assert verdict.not_fetched_reason == "not fetched: robots disallows"
    assert _classify(200, "User-agent: *\nDisallow: /other/\n").allowed
    assert _classify(200, "User-agent: OtherBot\nDisallow: /\n").allowed
    assert not _classify(200, "User-agent: gtfs-scorecard\nDisallow: /\n").allowed


def test_a_redirect_off_robots_or_an_html_page_is_off_limits() -> None:
    assert _classify(200, "<!doctype html>", final_url="https://feeds.example/") == (
        rp.RobotsVerdict(False, rp.ROBOTS_REDIRECTED_OFF)
    )
    assert _classify(200, "<html><body>app</body></html>") == rp.RobotsVerdict(
        False, rp.ROBOTS_NOT_A_RULES_FILE
    )
    # A redirect that lands on another robots.txt is still a rules file.
    assert _classify(
        200, "User-agent: *\nDisallow:\n", final_url="https://www.feeds.example/robots.txt"
    ).allowed


class _Recorder:
    def __init__(self, response: RobotsResponse | Exception) -> None:
        self.response = response
        self.calls: list[str] = []

    def __call__(self, url: str) -> RobotsResponse:
        self.calls.append(url)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_checker_reads_each_origin_once() -> None:
    get = _Recorder(RobotsResponse(200, RULES, "", "User-agent: *\nDisallow: /private/\n"))
    checker = RobotsChecker(get=get)
    assert checker.check(TARGET).allowed
    assert not checker.check("https://feeds.example/private/x.zip").allowed
    assert get.calls == [RULES]


def test_a_read_failure_is_a_refusal_and_require_raises_with_the_reason() -> None:
    checker = RobotsChecker(get=_Recorder(ConnectionError("refused")))
    assert checker.check(TARGET) == rp.RobotsVerdict(False, rp.ROBOTS_UNREACHABLE)
    with pytest.raises(RobotsRefusedError) as raised:
        checker.require(TARGET)
    assert raised.value.reason == rp.NOT_FETCHED_OFF_LIMITS
    assert raised.value.detail == rp.ROBOTS_UNREACHABLE


def test_require_names_an_explicit_disallow() -> None:
    checker = RobotsChecker(
        get=_Recorder(RobotsResponse(200, RULES, "", "User-agent: *\nDisallow: /\n"))
    )
    with pytest.raises(RobotsRefusedError) as raised:
        checker.require(TARGET)
    assert raised.value.reason == "not fetched: robots disallows"


def test_default_getter_keeps_the_status_of_an_error_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import requests

    from scorecard_pipeline import net

    def fake_safe_get(url: str, **kwargs: Any) -> bytes:
        response = requests.Response()
        response.status_code = 403
        response.url = url
        response.headers["content-type"] = "application/xml"
        raise requests.exceptions.HTTPError(response=response)

    monkeypatch.setattr(net, "safe_get", fake_safe_get)
    got = rp._default_get("https://bucket.s3.amazonaws.com/robots.txt")
    assert (got.status, got.content_type) == (403, "application/xml")
