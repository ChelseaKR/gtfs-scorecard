"""The robots.txt check a catalog-driven registry edit runs first (ADR 0069)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from scorecard_pipeline import robots_policy as rp
from scorecard_pipeline.robots_policy import RobotsChecker, classify_robots_response, robots_url

TARGET = "https://feeds.example/agency/gtfs.zip"
RULES = "https://feeds.example/robots.txt"


def _classify(
    status: int,
    body: str = "",
    *,
    final_url: str = RULES,
    content_type: str = "text/plain",
) -> rp.RobotsVerdict:
    return classify_robots_response(
        target_url=TARGET,
        status=status,
        final_url=final_url,
        content_type=content_type,
        body=body,
    )


@pytest.mark.parametrize("status", [404, 410])
def test_a_missing_rules_file_is_no_rules(status: int) -> None:
    assert _classify(status) == rp.RobotsVerdict(True, rp.NO_ROBOTS_FILE)


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_any_other_error_at_robots_is_a_refusal(status: int) -> None:
    verdict = _classify(status)
    assert not verdict.allowed
    assert verdict.reason == f"robots_status_{status}"


def test_a_redirect_off_the_robots_path_is_not_permission() -> None:
    verdict = _classify(200, "<!doctype html>", final_url="https://feeds.example/")
    assert verdict == rp.RobotsVerdict(False, rp.ROBOTS_REDIRECTED_OFF)


def test_an_html_page_served_as_robots_is_not_a_rules_file() -> None:
    verdict = _classify(200, "<!DOCTYPE html><html></html>", content_type="text/html")
    assert verdict == rp.RobotsVerdict(False, rp.ROBOTS_NOT_A_RULES_FILE)
    # Sniffed from the body too, when the header claims plain text.
    verdict = _classify(200, "  <html><body>app shell</body></html>")
    assert verdict == rp.RobotsVerdict(False, rp.ROBOTS_NOT_A_RULES_FILE)


def test_parsed_rules_are_asked_about_our_own_user_agent() -> None:
    assert _classify(200, "User-agent: *\nDisallow:\n") == rp.RobotsVerdict(
        True, rp.ALLOWED_BY_ROBOTS
    )
    assert _classify(200, "User-agent: *\nDisallow: /agency/\n") == rp.RobotsVerdict(
        False, rp.DISALLOWED_BY_ROBOTS
    )
    # A rule aimed at another crawler does not bind this one.
    assert _classify(200, "User-agent: OtherBot\nDisallow: /\n").allowed


def test_robots_url_is_the_origin_rules_file() -> None:
    assert robots_url("https://feeds.example/a/b.zip?x=1") == RULES
    assert robots_url("http://feeds.example:8080/x") == "http://feeds.example:8080/robots.txt"
    assert robots_url("ftp://feeds.example/x") is None
    assert robots_url("not a url") is None


@dataclass
class _Response:
    status_code: int
    text: str = ""
    url: str = RULES
    headers: dict[str, str] = field(default_factory=lambda: {"content-type": "text/plain"})


class _Recorder:
    def __init__(self, response: _Response | Exception) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, url: str, **kwargs: Any) -> _Response:
        self.calls.append((url, kwargs))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_checker_reads_each_origin_once_and_identifies_itself() -> None:
    get = _Recorder(_Response(200, "User-agent: *\nDisallow: /private/\n"))
    checker = RobotsChecker(get=get)

    assert checker.check(TARGET).allowed
    assert not checker.check("https://feeds.example/private/gtfs.zip").allowed

    assert [url for url, _ in get.calls] == [RULES]
    user_agent = get.calls[0][1]["headers"]["User-Agent"]
    assert user_agent == rp.USER_AGENT
    assert "gtfs-scorecard" in user_agent
    for browser_token in ("Mozilla", "Chrome", "Safari", "Gecko"):
        assert browser_token not in user_agent


def test_a_network_failure_is_a_refusal_not_permission() -> None:
    checker = RobotsChecker(get=_Recorder(ConnectionError("refused")))
    assert checker.check(TARGET) == rp.RobotsVerdict(False, rp.ROBOTS_UNREACHABLE)


def test_a_non_http_url_is_refused_without_a_request() -> None:
    get = _Recorder(_Response(404))
    assert RobotsChecker(get=get).check("file:///etc/passwd") == rp.RobotsVerdict(
        False, rp.INVALID_URL
    )
    assert get.calls == []


def test_negative_control_the_403_rule_is_what_holds_a_403_host() -> None:
    """Sabotage the classifier's error branch and show the refusal disappears."""
    get = _Recorder(_Response(403, "Access Denied", headers={"content-type": "text/html"}))
    assert RobotsChecker(get=get).check(TARGET) == rp.RobotsVerdict(False, "robots_status_403")

    def permissive(**kwargs: Any) -> rp.RobotsVerdict:
        return rp.RobotsVerdict(True, "sabotaged")

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(rp, "classify_robots_response", permissive)
        # The sabotage landed: the module now answers from the stub.
        assert rp.classify_robots_response(
            target_url=TARGET, status=403, final_url=RULES, content_type="", body=""
        ) == rp.RobotsVerdict(True, "sabotaged")
        assert RobotsChecker(get=get).check(TARGET) == rp.RobotsVerdict(True, "sabotaged")
