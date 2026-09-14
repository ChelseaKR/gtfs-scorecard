"""The page a paying buyer lands on, driven in a browser.

/bundle/setup/ is the second half of a purchase. Stripe's Payment Links
redirect to it with ``?session_id=cs_...`` after checkout, and it is the only
route by which an order reaches the fulfilment workflow: the webhook records
that a checkout happened, but nothing builds until this form is submitted.

It had never been run in a browser. The four Payment Links are live, the API
is deployed, and no one has bought anything in live mode, so every statement
about what this page does with a session reference was read off the source
rather than observed. These
tests observe it: the real page, the real ``web/src/bundle-setup.js``, a real
form submission, and the request it makes intercepted at the browser.

**Nothing leaves the machine.** ``web/src/config.js`` points
``SCORECARD_BUNDLE_URL`` at the deployed API Gateway, and that Lambda reads
the Checkout Session out of Stripe. So config.js is served with the endpoint
rewritten to this test server's own origin, and conftest's
``_block_external_requests`` aborts anything that would leave 127.0.0.1
regardless. No Stripe object is addressed, let alone created.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("playwright.sync_api", reason="the e2e dependency group is not installed")

from playwright.sync_api import Page, Route, expect

pytestmark = pytest.mark.e2e

# This file is pipeline/tests/e2e/test_bundle_setup_form.py, so parents[3] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_JS = REPO_ROOT / "web" / "src" / "config.js"

# The path the rewritten endpoint lives under. It is served by nothing: every
# request to it is fulfilled by a route in the test, so an un-intercepted one
# fails loudly as a 404 rather than quietly reaching a real service.
FAKE_API = "/__bundle_api_under_test"
SESSION_ID = "cs_test_a1B2c3D4e5F6g7H8"

# The keys infra/program-bundle/setup_handler.setup() reads off the form body.
# `session_id` is the checkout reference; the rest are the program's details.
EXPECTED_BODY_KEYS = {
    "session_id",
    "program_name",
    "accent",
    "logo",
    "agency_ids",
    "deliver_to",
}


def _point_the_page_at_the_test_server(page: Page, base_url: str) -> None:
    """Serve the real config.js with the bundle endpoint rewritten.

    Appended rather than replaced: config.js sets several globals the rest of
    the page reads, and a stub carrying only this one would be testing a
    different page.
    """
    body = CONFIG_JS.read_text(encoding="utf-8")
    body += f'\nwindow.SCORECARD_BUNDLE_URL = "{base_url}{FAKE_API}";\n'

    def _fulfill(route: Route) -> None:
        route.fulfill(status=200, content_type="text/javascript", body=body)

    page.route("**/src/config.js", _fulfill)


def _capture_setup(page: Page, *, status: int, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Answer the setup POST with a fixed response, recording each request."""
    seen: list[dict[str, Any]] = []

    def _fulfill(route: Route) -> None:
        request = route.request
        seen.append(
            {
                "method": request.method,
                "url": request.url,
                "content_type": request.headers.get("content-type", ""),
                "body": json.loads(request.post_data or "{}"),
            }
        )
        route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))

    page.route(f"**{FAKE_API}/setup", _fulfill)
    return seen


def _open_setup(page: Page, base_url: str, query: str = f"?session_id={SESSION_ID}") -> None:
    _point_the_page_at_the_test_server(page, base_url)
    page.goto(f"{base_url}/bundle/setup/{query}")


def _fill(page: Page, *, agency_ids: str = "unitrans, yolobus") -> None:
    page.fill("#program_name", "Example State Transit Program")
    page.fill("#accent", "#2c5f70")
    page.fill("#agency_ids", agency_ids)
    page.fill("#deliver_to", "liaison@example.org")


def test_the_form_posts_the_checkout_reference_and_the_program_details(
    page: Page, base_url: str
) -> None:
    """The request the Lambda has never received, observed once before a buyer
    makes it.

    Every field here is one ``setup()`` reads by name. A renamed input, a
    dropped key, or a reference read from the wrong place is not a visible
    failure on this page: the POST goes out, the Lambda answers 400, and the
    buyer is shown a validation message about a form they filled in correctly.
    """
    _open_setup(page, base_url)
    seen = _capture_setup(
        page,
        status=200,
        payload={
            "ok": True,
            "bundle_id": "a" * 32,
            "deliver_by": "2026-09-16",
            "promise": "It will arrive by Tuesday 16 September.",
        },
    )
    _fill(page)
    page.get_by_role("button", name="Build my reports").click()

    expect(page.locator("#form-status")).to_have_class("form-status form-status-ok")
    assert len(seen) == 1, f"the form made {len(seen)} requests"
    request = seen[0]
    assert request["method"] == "POST"
    assert request["url"].endswith(f"{FAKE_API}/setup")
    assert request["content_type"].startswith("application/json")
    assert set(request["body"]) == EXPECTED_BODY_KEYS, (
        f"the form posts {sorted(request['body'])}; setup() reads {sorted(EXPECTED_BODY_KEYS)}"
    )
    # The reference comes from the address Stripe redirected to, not the form.
    assert request["body"]["session_id"] == SESSION_ID
    assert request["body"]["program_name"] == "Example State Transit Program"
    assert request["body"]["agency_ids"] == "unitrans, yolobus"
    assert request["body"]["deliver_to"] == "liaison@example.org"
    assert request["body"]["logo"] == "", "an empty optional field is sent as empty, not omitted"


def test_the_page_states_the_promise_the_server_computed(page: Page, base_url: str) -> None:
    """The delivery date carries a refund, so it is computed once, in the
    Lambda, and shown here verbatim.

    A browser working the two business days out again would be a second
    implementation of a refund liability, and the two would disagree the first
    time a public holiday fell between them.
    """
    _open_setup(page, base_url)
    _capture_setup(
        page,
        status=200,
        payload={
            "ok": True,
            "bundle_id": "b" * 32,
            "deliver_by": "2026-09-16",
            "promise": "It will arrive by Tuesday 16 September.",
        },
    )
    _fill(page)
    page.get_by_role("button", name="Build my reports").click()

    status = page.locator("#form-status")
    expect(status).to_contain_text("It will arrive by Tuesday 16 September.")
    expect(status).to_contain_text("30 days")
    # And the form stays closed: the order is placed, and a second submission
    # of the same checkout is refused by the server anyway.
    expect(page.get_by_role("button", name="Build my reports")).to_be_disabled()


def test_a_list_over_the_plans_cap_is_answered_with_the_servers_own_number(
    page: Page, base_url: str
) -> None:
    """The page's own ceiling is the widest cap across every plan, because it
    cannot know which price was paid. The server knows, and refuses *before*
    it consumes the checkout so the buyer can trim and send the same one again.

    That recovery only works if this page shows the server's sentence and
    re-enables the form. Shown a generic failure, or left disabled, a
    bundle_25 buyer who listed forty agencies has paid and has no way forward.
    """
    _open_setup(page, base_url)
    seen = _capture_setup(
        page,
        status=400,
        payload={"ok": False, "error": "your plan covers at most 25 agencies; 40 were given"},
    )
    _fill(page, agency_ids=", ".join(f"agency{n}" for n in range(40)))
    page.get_by_role("button", name="Build my reports").click()

    assert len(seen) == 1
    status = page.locator("#form-status")
    expect(status).to_have_text("your plan covers at most 25 agencies; 40 were given")
    expect(status).to_have_class("form-status form-status-err")
    expect(page.get_by_role("button", name="Build my reports")).to_be_enabled()
    expect(page.locator("#agency_ids")).to_be_enabled()


def test_a_list_over_the_widest_cap_never_reaches_the_server(page: Page, base_url: str) -> None:
    """The client ceiling is a courtesy, not the rule, and it must not fire
    below the widest plan: a bundle_100 buyer listing a hundred agencies is
    within their plan and must get through."""
    _open_setup(page, base_url)
    seen = _capture_setup(page, status=200, payload={"ok": True, "bundle_id": "c" * 32})

    # One over: refused here, and the form stays open so it can be trimmed.
    _fill(page, agency_ids=", ".join(f"agency{n}" for n in range(101)))
    page.get_by_role("button", name="Build my reports").click()
    expect(page.locator("#form-status")).to_contain_text("100 agencies")
    assert seen == [], "a list over every plan's cap was posted anyway"

    # Exactly the widest cap: sent. A guard that fired here would refuse a
    # bundle_100 buyer their whole plan, on the page, with no way past it.
    _fill(page, agency_ids=", ".join(f"agency{n}" for n in range(100)))
    page.get_by_role("button", name="Build my reports").click()
    expect(page.locator("#form-status")).to_have_class("form-status form-status-ok")
    assert len(seen) == 1, "a hundred agencies is inside the widest plan and must be sent"


def test_a_service_that_cannot_be_reached_never_tells_a_buyer_they_were_not_charged(
    page: Page, base_url: str
) -> None:
    """The one sentence this page must never show somebody holding a receipt.

    Stripe has taken the money by the time this page loads. "Nothing has been
    charged" is false to that reader and is the sentence most likely to stop
    them chasing an order that did go through.
    """
    _open_setup(page, base_url)

    def _fail(route: Route) -> None:
        route.abort()

    page.route(f"**{FAKE_API}/setup", _fail)
    _fill(page)
    page.get_by_role("button", name="Build my reports").click()

    status = page.locator("#form-status")
    expect(status).to_contain_text("Your payment is safe")
    assert "Nothing has been charged" not in (status.text_content() or "")
    expect(page.get_by_role("button", name="Build my reports")).to_be_enabled()


def test_an_address_with_no_checkout_reference_does_not_offer_to_build_anything(
    page: Page, base_url: str
) -> None:
    """Reached without the reference Stripe adds, the form is closed and says
    how to get help, and still does not claim nothing was paid: somebody who
    lost the redirect page is exactly the reader who did pay."""
    _open_setup(page, base_url, query="")

    expect(page.get_by_role("button", name="Build my reports")).to_be_disabled()
    text = page.locator("#form-status").text_content() or ""
    assert "order reference" in text
    assert "Do not pay again." in text
    assert "Nothing has been charged" not in text
