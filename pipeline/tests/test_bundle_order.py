"""The fulfillment workflow's side of a stored order (bundle_order.py).

report-bundle.yml is dispatched with an opaque reference and collects the
order from the private bucket. Everything it then does with the order goes
through these commands, so that no buyer value is ever on a command line, in
an env block, or printed unmasked in a public run log. The values here are
synthetic.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import bundle_order, cli
from scorecard_pipeline.bundle import MAX_AGENCIES, BundleError, archive_key

BUNDLE_ID = "0123456789abcdef0123456789abcdef"
FROZEN = dt.datetime(2026, 9, 1, 12, 0, tzinfo=dt.UTC)


def _order(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "bundle_id": BUNDLE_ID,
        "program_name": "Example State Transit Program",
        "accent": "#2C5F70",
        "logo": "https://logo.example/mark.svg",
        "agency_ids": ["sampletown", "yolobus"],
        "deliver_to": "liaison@example.org",
        "cadence": "one_time",
        "promised_by": "Wednesday 16 September",
        "max_agencies": 25,
    }
    base.update(overrides)
    return base


def _write(tmp_path: Path, order: Any, name: str = "request.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(order))
    return path


def _manifest(tmp_path: Path) -> Path:
    manifest = {
        "requested": 2,
        "included": 1,
        "agencies": [
            {"id": "sampletown", "status": "included", "detail": ""},
            {"id": "yolobus", "status": "unknown_id", "detail": "not a tracked scorecard id"},
        ],
    }
    return _write(tmp_path, manifest, "manifest.json")


@pytest.fixture(autouse=True)
def _public_logo(monkeypatch: pytest.MonkeyPatch) -> None:
    # parse_request resolves an https logo host; no network in the suite.
    monkeypatch.setattr("scorecard_pipeline.bundle.validate_public_url", lambda url: None)


def test_mask_covers_every_value_that_names_the_buyer_or_grants_access() -> None:
    lines = bundle_order.mask_lines(_order())
    masked = {line.removeprefix("::add-mask::") for line in lines}
    assert all(line.startswith("::add-mask::") for line in lines)
    assert masked == {
        BUNDLE_ID,
        "liaison@example.org",
        "Example State Transit Program",
        "https://logo.example/mark.svg",
        "sampletown",
        "yolobus",
    }
    # Longest first, so a value that contains another is masked whole.
    lengths = [len(value) for value in masked]
    assert [len(line.removeprefix("::add-mask::")) for line in lines] == sorted(
        lengths, reverse=True
    )


def test_mask_reads_the_raw_object_so_an_invalid_order_is_masked_too() -> None:
    """Masks come from the object as stored, before validation, so the value
    a validation error is about to quote is already covered. A string list,
    a comma string and stray whitespace are all read the same way."""
    raw = _order(deliver_to=" not-an-address ", agency_ids="Bad Id!, sampletown\nyolobus")
    masked = {line.removeprefix("::add-mask::") for line in bundle_order.mask_lines(raw)}
    assert {"not-an-address", "Bad Id!", "sampletown", "yolobus"} <= masked


def test_mask_skips_what_it_must_not_or_cannot_mask() -> None:
    """A data: URI is image bytes and never printed; a value with a line break
    would end the workflow command early and register a partial mask; the
    style and scheduling fields say nothing about who bought what."""
    raw = _order(logo="data:image/png;base64,AAAA", program_name="two\nlines")
    masked = {line.removeprefix("::add-mask::") for line in bundle_order.mask_lines(raw)}
    assert not any(value.startswith("data:") for value in masked)
    assert "two\nlines" not in masked
    for field in ("accent", "cadence", "promised_by"):
        assert str(raw[field]) not in masked
    assert all("\n" not in line and "\r" not in line for line in bundle_order.mask_lines(raw))


def test_the_mask_command_prints_masks_before_the_error_that_could_quote_one(
    tmp_path: Path,
) -> None:
    """Run as the workflow runs it, stdout and stderr into one stream. The
    runner registers a mask when it reads the line; a mask that arrived after
    the error quoting the value would not cover it."""
    # No logo: the child process would resolve its host, and the monkeypatch
    # above does not reach it.
    path = _write(tmp_path, _order(agency_ids="Bad Id!", logo=""))
    done = subprocess.run(  # noqa: S603 - this interpreter and a module in this package
        [sys.executable, "-m", "scorecard_pipeline.bundle_order", "mask", str(path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    assert done.returncode == 2
    out = done.stdout
    assert "::add-mask::Bad Id!" in out
    assert out.index("::add-mask::Bad Id!") < out.index("order error:")


def test_the_mask_command_succeeds_quietly_on_a_valid_order(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert bundle_order.main(["mask", str(_write(tmp_path, _order()))]) == 0
    out = capsys.readouterr().out
    assert all(line.startswith("::add-mask::") for line in out.splitlines() if line)


@pytest.mark.parametrize(
    ("stored", "cap"),
    [
        (25, 25),
        (100, 100),
        (1000, MAX_AGENCIES),
        (None, MAX_AGENCIES),
        (0, MAX_AGENCIES),
        (True, MAX_AGENCIES),
        ("25", MAX_AGENCIES),
    ],
)
def test_the_cap_is_what_was_sold_and_never_more_than_the_widest_plan(
    stored: Any, cap: int
) -> None:
    assert bundle_order.order_cap(_order(max_agencies=stored)) == cap


def test_the_cap_is_enforced_again_when_the_order_is_loaded(tmp_path: Path) -> None:
    over = _order(max_agencies=1)
    with pytest.raises(BundleError, match="at most 1 agencies"):
        bundle_order.load_order(_write(tmp_path, over))


def test_the_render_is_held_to_the_cap_on_the_command_line(tmp_path: Path) -> None:
    """`scorecard bundle --max-agencies` is how the workflow passes the cap on:
    a hand-edited stored order cannot ship more than was bought."""
    path = _write(tmp_path, _order(agency_ids=["sampletown", "yolobus"]))

    def plan_with_cap(cap: int | None) -> int:
        args = argparse.Namespace(
            request=path, plan=tmp_path / "p.json", out=None, manifest=None, max_agencies=cap
        )
        return cli._cmd_bundle(args, argparse.ArgumentParser())

    assert plan_with_cap(1) == 2
    assert plan_with_cap(2) == 0
    assert plan_with_cap(None) == 0, "no cap given is the product ceiling, as before"


def test_archive_key_and_cap_commands_print_only_what_the_next_step_needs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _write(tmp_path, _order())
    assert bundle_order.main(["archive-key", str(path)]) == 0
    assert capsys.readouterr().out.strip() == archive_key(BUNDLE_ID)
    assert bundle_order.main(["cap", str(path)]) == 0
    assert capsys.readouterr().out.strip() == "25"


def test_the_delivery_email_carries_the_link_the_promise_and_the_address(
    tmp_path: Path,
) -> None:
    sent: list[tuple[str, str, str, str]] = []
    bundle_order.send_delivery_email(
        _write(tmp_path, _order()),
        _manifest(tmp_path),
        api_base="https://api.example/bundle/",
        source="reports@example.org",
        send=lambda *mail: sent.append(mail),
        now=FROZEN,
    )
    [(source, to, subject, body)] = sent
    assert source == "reports@example.org"
    assert to == "liaison@example.org"
    assert "1 of 2 ready" in subject
    assert f"https://api.example/bundle/download/{BUNDLE_ID}" in body
    assert "promised by Wednesday 16 September" in body
    assert "valid until 2026-10-01" in body


def test_a_refresh_order_states_no_promise(tmp_path: Path) -> None:
    sent: list[tuple[str, str, str, str]] = []
    bundle_order.send_delivery_email(
        _write(tmp_path, _order(promised_by="", cadence="monthly")),
        _manifest(tmp_path),
        api_base="https://api.example",
        source="reports@example.org",
        send=lambda *mail: sent.append(mail),
        now=FROZEN,
    )
    assert "promised by" not in sent[0][3]


def test_the_email_refuses_a_route_it_cannot_honor(tmp_path: Path) -> None:
    request, manifest = _write(tmp_path, _order()), _manifest(tmp_path)
    sent: list[Any] = []
    with pytest.raises(BundleError, match="https"):
        bundle_order.send_delivery_email(
            request,
            manifest,
            api_base="http://api.example",
            source="r@example.org",
            send=lambda *mail: sent.append(mail),
        )
    with pytest.raises(BundleError, match="SES_FROM"):
        bundle_order.send_delivery_email(
            request,
            manifest,
            api_base="https://api.example",
            source="",
            send=lambda *mail: sent.append(mail),
        )
    assert sent == []


def test_the_email_command_reads_its_route_from_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Nothing about the send is an argument: the step names two files and
    the environment names the route. What it prints is that a link was sent,
    never to whom or which link."""
    monkeypatch.setenv("BUNDLE_API_BASE", "https://api.example")
    monkeypatch.setenv("SES_FROM", "reports@example.org")
    sent: list[tuple[str, str, str, str]] = []
    code = bundle_order.main(
        ["email", str(_write(tmp_path, _order())), str(_manifest(tmp_path))],
        send=lambda *mail: sent.append(mail),
    )
    assert code == 0 and len(sent) == 1
    printed = capsys.readouterr()
    assert printed.out.strip() == "the download link was sent"
    for value in ("liaison@example.org", BUNDLE_ID, "/download/"):
        assert value not in printed.out + printed.err


def test_an_unreadable_order_fails_without_quoting_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "request.json"
    broken.write_text("liaison@example.org is not json")
    assert bundle_order.main(["mask", str(broken)]) == 2
    assert bundle_order.main(["cap", str(_write(tmp_path, ["a", "list"], "list.json"))]) == 2
    err = capsys.readouterr().err
    assert "order error" in err and "liaison@example.org" not in err


def test_a_malformed_command_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    assert bundle_order.main([]) == 2
    assert bundle_order.main(["mask"]) == 2
    assert bundle_order.main(["email", "only-one-file"]) == 2
    assert "usage:" in capsys.readouterr().err
