"""`scorecard bundle-email --send`, the manual delivery command.

It printed "sent to <buyer>" and exited 0 whatever SES did: send_via_ses
reports a refusal in its return value instead of raising, and the command
ignored it. The workflow path (bundle_order.py email) already fails on a
refusal. Here a refusal exits 1 and says how many emails were not sent, and
neither outcome prints the buyer's address: the repository is public, and a
run log of this command would be a publication.
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from scorecard_pipeline import cli

BUYER = "liaison@example.org"
SENDER = "bundles@sender.example"


@pytest.fixture(autouse=True)
def registry(isolated_repo_root: Path) -> None:
    """main() loads the registry before any command runs."""
    isolated_repo_root.mkdir(parents=True, exist_ok=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: sampletown\n"
        "    name: Sampletown Transit\n"
        "    static_gtfs_url: https://transit.example/gtfs.zip\n"
    )


class _SesRefusal(Exception):
    """SES's MessageRejected, whose message quotes the recipient."""

    def __init__(self, recipient: str) -> None:
        super().__init__(f"Email address is not verified: {recipient}")
        self.response = {"Error": {"Code": "MessageRejected", "Message": recipient}}


def _fake_boto3(monkeypatch: pytest.MonkeyPatch, *, refuse: bool) -> list[str]:
    """Install a boto3 whose SES client accepts or refuses; return who was sent to."""
    delivered: list[str] = []

    class _Ses:
        def send_email(self, **kwargs: object) -> None:
            to = kwargs["Destination"]["ToAddresses"][0]  # type: ignore[index]
            if refuse:
                raise _SesRefusal(to)
            delivered.append(to)

    fake = types.ModuleType("boto3")
    fake.client = lambda *_a, **_kw: _Ses()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake)
    return delivered


def _args(tmp_path: Path) -> list[str]:
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "bundle_id": "0123456789abcdef0123456789abcdef",
                "program_name": "Example State Transit Program",
                "accent": "#2C5F70",
                "logo": "",
                "agency_ids": "sampletown",
                "deliver_to": BUYER,
                "cadence": "one_time",
            }
        )
    )
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "requested": 1,
                "included": 1,
                "agencies": [{"id": "sampletown", "status": "included", "detail": ""}],
            }
        )
    )
    return [
        "bundle-email",
        "--request",
        str(request),
        "--manifest",
        str(manifest),
        "--download-url",
        "https://x.example/download/abc",
        "--expires-on",
        "2026-12-01",
        "--send",
        "--from",
        SENDER,
    ]


def test_a_refused_send_exits_1_and_says_how_many_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    delivered = _fake_boto3(monkeypatch, refuse=True)

    code = cli.main(_args(tmp_path))

    out, err = capsys.readouterr()
    assert code == 1, err
    assert delivered == []
    assert "sent" not in out.replace("not sent", ""), "it still claimed the email was sent"
    assert "1 of 1 delivery email(s) not sent" in err
    assert BUYER not in out + err


def test_an_accepted_send_exits_0_without_naming_the_buyer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    delivered = _fake_boto3(monkeypatch, refuse=False)

    code = cli.main(_args(tmp_path))

    out, err = capsys.readouterr()
    assert code == 0, err
    assert delivered == [BUYER]
    assert out.strip() == "sent 1 delivery email"
    assert BUYER not in out + err


def test_rendering_without_send_still_writes_the_address_to_the_chosen_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Control: --out is the operator's own file and keeps its To: line; only
    stdout stops carrying the address. No send is attempted without --send."""
    delivered = _fake_boto3(monkeypatch, refuse=False)
    out_file = tmp_path / "email.txt"
    args = [a for a in _args(tmp_path) if a not in ("--send", "--from", SENDER)]

    code = cli.main([*args, "--out", str(out_file)])

    out, err = capsys.readouterr()
    assert code == 0, err
    assert delivered == []
    assert out.strip() == str(out_file)
    assert out_file.read_text().startswith(f"To: {BUYER}\n")
