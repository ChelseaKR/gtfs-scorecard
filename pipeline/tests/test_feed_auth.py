"""Credentialed feed sources (issue #371), exercised against a real local server.

The fetch tests run the real stack end to end: fetch_static, the credentialed
download path, net.py's guarded streaming and hand-followed redirects, and the
requests library, against two stdlib HTTP servers on 127.0.0.1 that refuse
anything without the right credential. The only thing replaced is
``net.validate_public_url``, because the SSRF guard (tested in test_net.py)
rejects loopback by design; the stand-in admits exactly the two fixture
origins and rejects everything else, so a request that tried to leave them
would still fail.

The load-bearing property is fail-closed: with the variable missing, a
credentialed record is unreachable with the reason "credential not
configured", no request is made, the mirror is never consulted, and no
artifact (so no grade, F or otherwise) is written. Each red assertion below is
preceded by a check that its sabotage actually landed, so a sabotage that
silently no-ops cannot read as a pass.

No credential here is real. The fixture value is assembled at runtime and is
low-entropy on purpose, so the secret scanners have nothing to flag.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import io
import json
import os
import re
import shutil
import subprocess
import threading
import tomllib
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import jsonschema
import pytest
import requests
import yaml

from scorecard_pipeline import cli, net
from scorecard_pipeline import fetch as fetchmod
from scorecard_pipeline.agencies import AgencyConfigError, parse_agencies
from scorecard_pipeline.config import AGENCIES, Agency, FetchAuth, artifacts_dir, raw_dir
from scorecard_pipeline.feed_auth import (
    NOT_CONFIGURED,
    CredentialNotConfiguredError,
    ResolvedCredential,
    describe_failure,
    published_url,
    reference_problem,
    resolve_credential,
)
from scorecard_pipeline.lint import lint_registry
from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.publish import build_artifact, validate_artifact
from scorecard_pipeline.run_summary import (
    AgencyOutcome,
    append_outcome,
    build_shard_summary,
    merge_run_summaries,
    read_outcomes,
)
from scorecard_pipeline.score import build_scorecard

REPO_ROOT = Path(__file__).resolve().parents[2]
GITLEAKS_CONFIG = REPO_ROOT / ".gitleaks.toml"
GITLEAKS_RULE = "scorecard-fetch-auth-literal-secret"

ENV = "SCORECARD_FEED_AUTH_FIXTURE"
# Joined at runtime and deliberately readable: a fixture, not a key.
CREDENTIAL = "fixture-" + "credential-not-real-0001"
BASIC_USER = "fixture-user"
DATE = dt.date(2026, 9, 17)
GENERATED_AT = dt.datetime(2026, 9, 17, 12, 0, tzinfo=dt.UTC)


def _zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("agency.txt", "agency_name,agency_url,agency_timezone\nX,https://x,UTC")
        archive.writestr("stops.txt", "stop_id,stop_name\n1,Main St")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# The fixture servers


@dataclass
class Seen:
    path: str
    headers: dict[str, str]


@dataclass
class Gate:
    """One fixture origin: its base URL and every request it received."""

    base: str
    seen: list[Seen] = field(default_factory=list)

    def url(self, path: str) -> str:
        return f"{self.base}{path}"

    def text(self) -> str:
        """Everything this origin was sent, for "the credential never
        reached here" assertions."""
        return json.dumps([(s.path, s.headers) for s in self.seen])


class _GateServer(ThreadingHTTPServer):
    gate: Gate
    other: Gate | None = None


class _Handler(BaseHTTPRequestHandler):
    server: _GateServer

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _send(self, status: int, body: bytes = b"", location: str | None = None) -> None:
        self.send_response(status)
        if location:
            self.send_header("Location", location)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        headers = {key.lower(): value for key, value in self.headers.items()}
        self.server.gate.seen.append(Seen(self.path, headers))
        parts = urlsplit(self.path)
        query = parse_qs(parts.query)
        has_header = headers.get("x-api-key") == CREDENTIAL
        basic = "Basic " + base64.b64encode(f"{BASIC_USER}:{CREDENTIAL}".encode()).decode()
        if parts.path == "/open.zip":
            self._send(200, _zip_bytes())
        elif parts.path == "/header.zip":
            self._send(200, _zip_bytes()) if has_header else self._send(401)
        elif parts.path == "/query.zip":
            ok = query.get("apikey") == [CREDENTIAL] and query.get("format") == ["gtfs"]
            self._send(200, _zip_bytes()) if ok else self._send(401)
        elif parts.path == "/basic.zip":
            ok = headers.get("authorization") == basic
            self._send(200, _zip_bytes()) if ok else self._send(401)
        elif parts.path == "/redirect-away.zip" and has_header:
            assert self.server.other is not None
            self._send(302, location=self.server.other.url("/open.zip"))
        elif parts.path == "/redirect-home.zip" and has_header:
            self._send(302, location="/header.zip")
        elif parts.path == "/missing.zip":
            self._send(404)
        else:
            self._send(401)


def _serve() -> tuple[_GateServer, threading.Thread]:
    server = _GateServer(("127.0.0.1", 0), _Handler)
    server.gate = Gate(base=f"http://127.0.0.1:{server.server_address[1]}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


@pytest.fixture
def gates(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[Gate, Gate]]:
    """Two fixture origins, a gated publisher and an open second host.

    ``validate_public_url`` admits exactly these two origins. The mirror lookup
    returns a working URL on the open host, so a mirror fallback, if one
    happened, would succeed and be visible rather than fail quietly.
    """
    publisher, publisher_thread = _serve()
    elsewhere, elsewhere_thread = _serve()
    publisher.other = elsewhere.gate
    allowed = {publisher.gate.base, elsewhere.gate.base}

    def only_fixture_origins(url: str) -> None:
        parts = urlsplit(url)
        if f"{parts.scheme}://{parts.netloc}" not in allowed:
            raise net.UnsafeURLError(f"not a fixture origin: {url!r}")

    monkeypatch.setattr(net, "validate_public_url", only_fixture_origins)
    monkeypatch.setattr(fetchmod, "FETCH_RETRIES", 0)
    try:
        yield publisher.gate, elsewhere.gate
    finally:
        for server, thread in ((publisher, publisher_thread), (elsewhere, elsewhere_thread)):
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


@pytest.fixture
def mirror_calls(monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate]) -> list[str]:
    """Record every Mobility Database mirror lookup and answer with a mirror
    that works, so a fallback cannot hide behind a failing mirror."""
    _publisher, elsewhere = gates
    calls: list[str] = []

    def hosted_mirror_url(agency_id: str, *_args: object, **_kwargs: object) -> str:
        calls.append(agency_id)
        return elsewhere.url("/open.zip")

    monkeypatch.setattr("scorecard_pipeline.mobilitydb.hosted_mirror_url", hosted_mirror_url)
    return calls


def _agency(url: str, kind: str = "header", name: str = "X-Api-Key", **extra: Any) -> Agency:
    return Agency(
        id="gated",
        name="Gated Transit",
        static_gtfs_url=url,
        mdb_id="mdb-1",
        fetch_auth=FetchAuth(kind=kind, secret=ENV, name=name),
        **extra,
    )


def _snapshot_dir(agency_id: str = "gated") -> Path:
    return raw_dir() / agency_id / DATE.isoformat()


# ---------------------------------------------------------------------------
# Fail-closed: the property everything else depends on


def test_missing_variable_is_unreachable_with_no_request_and_no_mirror(
    monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate], mirror_calls: list[str]
) -> None:
    publisher, elsewhere = gates
    monkeypatch.delenv(ENV, raising=False)
    agency = _agency(publisher.url("/header.zip"))
    # The sabotage landed: the variable really is absent from this process.
    assert ENV not in os.environ

    with pytest.raises(CredentialNotConfiguredError) as caught:
        fetchmod.fetch_static(agency, DATE)

    assert str(caught.value).startswith(f"unreachable: {NOT_CONFIGURED}")
    assert caught.value.reason == NOT_CONFIGURED
    assert ENV in str(caught.value)  # names the variable for the operator
    assert publisher.seen == [] and elsewhere.seen == []  # no request at all
    assert mirror_calls == []  # the mirror was never even looked up
    assert not _snapshot_dir().exists() or not any(_snapshot_dir().iterdir())


def test_the_mirror_stub_is_live_so_its_silence_above_means_something(
    gates: tuple[Gate, Gate], mirror_calls: list[str]
) -> None:
    """Negative control for the test above. A keyless record whose origin
    refuses does fall back to this very mirror stub, so "mirror_calls == []"
    for the credentialed record is a real no-fallback result, not a stub that
    could never have been called."""
    publisher, elsewhere = gates
    keyless = Agency(
        id="keyless", name="Keyless", static_gtfs_url=publisher.url("/header.zip"), mdb_id="m"
    )

    result = fetchmod.fetch_static(keyless, DATE)

    assert mirror_calls == ["keyless"]
    assert result.source == "mirror"
    assert [s.path for s in elsewhere.seen] == ["/open.zip"]
    assert result.auth_kind is None


@pytest.mark.parametrize("value", ["", "   ", "\n"])
def test_an_empty_variable_is_the_same_neutral_state(
    monkeypatch: pytest.MonkeyPatch,
    gates: tuple[Gate, Gate],
    mirror_calls: list[str],
    value: str,
) -> None:
    publisher, _elsewhere = gates
    monkeypatch.setenv(ENV, value)
    assert os.environ[ENV] == value

    with pytest.raises(CredentialNotConfiguredError, match=NOT_CONFIGURED):
        fetchmod.fetch_static(_agency(publisher.url("/header.zip")), DATE)
    assert publisher.seen == [] and mirror_calls == []


def test_a_wrong_credential_fails_without_a_mirror_and_without_quoting_it(
    monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate], mirror_calls: list[str]
) -> None:
    publisher, _elsewhere = gates
    wrong = CREDENTIAL + "-wrong"
    monkeypatch.setenv(ENV, wrong)

    with pytest.raises(fetchmod.CredentialedFetchError) as caught:
        fetchmod.fetch_static(_agency(publisher.url("/header.zip")), DATE)

    # The request really was made with the (wrong) credential and refused.
    assert publisher.seen[0].headers["x-api-key"] == wrong
    assert "HTTP 401" in str(caught.value)
    assert wrong not in str(caught.value)
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert mirror_calls == []


def test_a_reference_outside_the_namespace_is_never_read_or_sent(
    monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate], mirror_calls: list[str]
) -> None:
    """A record naming some other process secret must not get it sent to the
    host it names. The variable is set, so this fails only because of the
    namespace, not because the value is missing."""
    publisher, _elsewhere = gates
    other = "OTHER_PROCESS_" + "SECRET"
    monkeypatch.setenv(other, CREDENTIAL)
    agency = Agency(
        id="gated",
        name="Gated",
        static_gtfs_url=publisher.url("/header.zip"),
        fetch_auth=FetchAuth(kind="header", secret=other, name="X-Api-Key"),
    )

    with pytest.raises(CredentialNotConfiguredError, match="variable name"):
        fetchmod.fetch_static(agency, DATE)
    assert publisher.seen == [] and mirror_calls == []


def test_cli_run_records_the_named_reason_and_writes_no_artifact(
    monkeypatch: pytest.MonkeyPatch,
    gates: tuple[Gate, Gate],
    mirror_calls: list[str],
    tmp_path: Path,
) -> None:
    """Through the real `scorecard run` path: exit 1, an unreachable outcome
    with the reason, nothing under data/artifacts. No grade of any letter is
    published for bytes that were never fetched."""
    publisher, _elsewhere = gates
    monkeypatch.delenv(ENV, raising=False)
    AGENCIES["gated"] = _agency(publisher.url("/header.zip"))
    outcomes = tmp_path / "outcomes.ndjson"
    args = argparse.Namespace(
        all=False,
        agency="gated",
        date=DATE,
        force_fetch=True,
        rt_samples=0,
        rt_interval=0,
        skip_rt=True,
        skip_unchanged=False,
        outcome_out=str(outcomes),
    )

    assert cli._cmd_run(args, argparse.ArgumentParser()) == 1

    (line,) = [json.loads(raw) for raw in outcomes.read_text().splitlines()]
    assert line["outcome"] == "unreachable"
    assert line["reason"] == NOT_CONFIGURED
    assert not artifacts_dir().exists() or not any(artifacts_dir().rglob("*.json"))
    assert publisher.seen == [] and mirror_calls == []


def test_an_ordinary_failure_records_no_credential_reason(tmp_path: Path) -> None:
    """The reason is specific: any other unreachable outcome carries none."""
    AGENCIES["plain"] = Agency(id="plain", name="Plain", static_gtfs_url="https://x.example/g")
    outcomes = tmp_path / "outcomes.ndjson"
    args = argparse.Namespace(
        all=False,
        agency="plain",
        date=DATE,
        force_fetch=True,
        rt_samples=0,
        rt_interval=0,
        skip_rt=True,
        skip_unchanged=False,
        outcome_out=str(outcomes),
    )
    with patch.object(cli, "run_agency", side_effect=RuntimeError("boom")):
        assert cli._cmd_run(args, argparse.ArgumentParser()) == 1
    (line,) = [json.loads(raw) for raw in outcomes.read_text().splitlines()]
    assert line["outcome"] == "unreachable"
    assert "reason" not in line


def test_the_reason_reaches_the_shard_and_merged_run_summaries(tmp_path: Path) -> None:
    started = dt.datetime(2026, 9, 17, tzinfo=dt.UTC)
    outcomes = [
        AgencyOutcome("gated", "unreachable", reason=NOT_CONFIGURED),
        AgencyOutcome("down", "unreachable"),
        AgencyOutcome("fine", "scored"),
    ]
    shard = build_shard_summary("0", outcomes, started, started)
    merged = merge_run_summaries([shard], started, expected_shard_count=1)

    assert shard["unreachable_reasons"] == {"gated": NOT_CONFIGURED}
    assert merged["unreachable_reasons"] == {"gated": NOT_CONFIGURED}
    assert merged["unreachable_agencies"] == ["down", "gated"]
    # A summary with no named reason keeps its existing shape.
    plain = build_shard_summary("1", outcomes[1:], started, started)
    assert "unreachable_reasons" not in plain
    assert "unreachable_reasons" not in merge_run_summaries([plain], started)
    # And the ndjson round trip keeps it.
    log = tmp_path / "o.ndjson"
    append_outcome(log, outcomes[0])
    assert read_outcomes(log)[0].reason == NOT_CONFIGURED


# ---------------------------------------------------------------------------
# Injection, one test per kind, and what gets recorded


def _assert_nowhere_on_disk(root: Path, secret: str) -> None:
    for path in root.rglob("*"):
        if path.is_file():
            assert secret.encode() not in path.read_bytes(), path


def test_header_kind_fetches_and_records_the_kind_not_the_value(
    monkeypatch: pytest.MonkeyPatch,
    gates: tuple[Gate, Gate],
    mirror_calls: list[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    publisher, _elsewhere = gates
    monkeypatch.setenv(ENV, CREDENTIAL)
    caplog.set_level("DEBUG")

    result = fetchmod.fetch_static(_agency(publisher.url("/header.zip")), DATE)

    assert publisher.seen[0].headers["x-api-key"] == CREDENTIAL
    assert result.source == "origin" and result.auth_kind == "header"
    assert result.final_url == publisher.url("/header.zip")
    sidecar = json.loads((_snapshot_dir() / fetchmod.PROVENANCE_FILENAME).read_text())
    assert sidecar["auth"] == "env-ref" and sidecar["auth_kind"] == "header"
    assert ENV not in json.dumps(sidecar)  # not even the variable's name
    _assert_nowhere_on_disk(raw_dir(), CREDENTIAL)
    assert CREDENTIAL not in caplog.text
    assert CREDENTIAL not in repr(result)
    assert mirror_calls == []


def test_query_kind_appends_the_parameter_and_publishes_no_query(
    monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate]
) -> None:
    publisher, _elsewhere = gates
    monkeypatch.setenv(ENV, CREDENTIAL)
    agency = _agency(publisher.url("/query.zip?format=gtfs"), kind="query", name="apikey")

    result = fetchmod.fetch_static(agency, DATE)

    # The configured parameter survived and the credential was added to it.
    assert parse_qs(urlsplit(publisher.seen[0].path).query) == {
        "format": ["gtfs"],
        "apikey": [CREDENTIAL],
    }
    assert result.auth_kind == "query"
    assert result.final_url == publisher.url("/query.zip")  # no query string at all
    assert result.url == agency.static_gtfs_url  # the URL on file, credential-free
    _assert_nowhere_on_disk(raw_dir(), CREDENTIAL)


def test_basic_kind_sends_an_authorization_header(
    monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate]
) -> None:
    publisher, _elsewhere = gates
    monkeypatch.setenv(ENV, f"{BASIC_USER}:{CREDENTIAL}")

    result = fetchmod.fetch_static(_agency(publisher.url("/basic.zip"), "basic", ""), DATE)

    assert publisher.seen[0].headers["authorization"].startswith("Basic ")
    assert result.auth_kind == "basic"


def test_basic_kind_without_a_colon_is_not_configured(
    monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate]
) -> None:
    publisher, _elsewhere = gates
    monkeypatch.setenv(ENV, CREDENTIAL)  # no user:password separator

    with pytest.raises(CredentialNotConfiguredError, match="user:password"):
        fetchmod.fetch_static(_agency(publisher.url("/basic.zip"), "basic", ""), DATE)
    assert publisher.seen == []


def test_a_redirect_to_another_origin_does_not_carry_the_credential(
    monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate]
) -> None:
    publisher, elsewhere = gates
    monkeypatch.setenv(ENV, CREDENTIAL)

    result = fetchmod.fetch_static(_agency(publisher.url("/redirect-away.zip")), DATE)

    # The sabotage landed: the publisher got the credential and redirected,
    # and the second origin really was fetched from.
    assert publisher.seen[0].headers["x-api-key"] == CREDENTIAL
    assert [s.path for s in elsewhere.seen] == ["/open.zip"]
    # And that second origin never saw the credential.
    assert "x-api-key" not in elsewhere.seen[0].headers
    assert CREDENTIAL not in elsewhere.text()
    assert result.final_url == elsewhere.url("/open.zip")


def test_a_redirect_within_the_origin_keeps_the_credential(
    monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate]
) -> None:
    """Control for the test above: scoping is by origin, not "first hop only".
    A publisher redirecting within its own host still gets the header."""
    publisher, _elsewhere = gates
    monkeypatch.setenv(ENV, CREDENTIAL)

    fetchmod.fetch_static(_agency(publisher.url("/redirect-home.zip")), DATE)

    assert [s.path for s in publisher.seen] == ["/redirect-home.zip", "/header.zip"]
    assert all(s.headers.get("x-api-key") == CREDENTIAL for s in publisher.seen)


def test_a_failed_query_fetch_does_not_quote_its_url(
    monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate]
) -> None:
    publisher, _elsewhere = gates
    monkeypatch.setenv(ENV, CREDENTIAL)
    keyed = f"{publisher.url('/missing.zip')}?apikey={CREDENTIAL}"
    # The sabotage has something to remove: the raw requests error for this
    # exact URL does quote the credential.
    with pytest.raises(requests.exceptions.HTTPError) as raw:
        net.safe_get(keyed, timeout=5)
    assert CREDENTIAL in str(raw.value)

    with pytest.raises(fetchmod.CredentialedFetchError) as caught:
        fetchmod.fetch_static(
            _agency(publisher.url("/missing.zip"), kind="query", name="apikey"), DATE
        )

    assert "HTTPError (HTTP 404)" in str(caught.value)
    assert CREDENTIAL not in str(caught.value)


def test_a_large_credentialed_feed_streams_with_the_credential(
    monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate]
) -> None:
    """The bounded-memory streaming path (large_feed) gets the same injection."""
    publisher, _elsewhere = gates
    monkeypatch.setenv(ENV, CREDENTIAL)

    result = fetchmod.fetch_static(
        _agency(publisher.url("/header.zip"), large_feed=True), DATE, force=True
    )

    assert publisher.seen[0].headers["x-api-key"] == CREDENTIAL
    assert result.auth_kind == "header"


def test_a_reused_snapshot_still_discloses_the_kind(
    monkeypatch: pytest.MonkeyPatch, gates: tuple[Gate, Gate]
) -> None:
    """The bytes on disk were fetched with a credential; a rerun that reuses
    them must say so even after the variable is gone."""
    publisher, _elsewhere = gates
    monkeypatch.setenv(ENV, CREDENTIAL)
    agency = _agency(publisher.url("/header.zip"))
    fetchmod.fetch_static(agency, DATE)
    monkeypatch.delenv(ENV)

    reused = fetchmod.fetch_static(agency, DATE)

    assert reused.reused is True
    assert reused.auth_kind == "header"
    assert len(publisher.seen) == 1  # the reuse made no request


def test_a_hand_edited_sidecar_cannot_put_arbitrary_text_in_the_artifact() -> None:
    assert fetchmod._recorded_auth_kind({"auth": "env-ref", "auth_kind": "header"}) == "header"
    assert fetchmod._recorded_auth_kind({"auth": "env-ref", "auth_kind": "<b>x</b>"}) is None
    assert fetchmod._recorded_auth_kind({"auth": "inline", "auth_kind": "header"}) is None
    assert fetchmod._recorded_auth_kind({}) is None


# ---------------------------------------------------------------------------
# The artifact


def _fetch_result(auth_kind: str | None) -> fetchmod.FetchResult:
    return fetchmod.FetchResult(
        agency_id="gated",
        path=Path("/tmp/gtfs.zip"),
        url="https://gated.example/feed.zip",
        fetched_date=DATE,
        sha256="a" * 64,
        size_bytes=10,
        reused=False,
        source="origin",
        final_url="https://gated.example/feed.zip",
        max_attempts=4,
        auth_kind=auth_kind,
    )


def _artifact(auth_kind: str | None) -> dict[str, Any]:
    card = build_scorecard([CategoryResult(name="correctness", score=90.0, summary="s")])
    agency = Agency(id="gated", name="Gated", static_gtfs_url="https://gated.example/feed.zip")
    return build_artifact(agency, _fetch_result(auth_kind), card, GENERATED_AT)


def test_the_artifact_discloses_env_ref_and_the_kind_and_validates() -> None:
    artifact = _artifact("query")

    assert artifact["fetch"]["auth"] == "env-ref"
    assert artifact["fetch"]["auth_kind"] == "query"
    note = artifact["confidence"]["notes"][-1]
    assert "requires registration" in note and "a URL parameter" in note
    assert "not published" in note
    validate_artifact(artifact)


def test_the_page_provenance_line_says_a_credential_was_used() -> None:
    from scorecard_pipeline.render_site import _confidence_section

    gated = _confidence_section(_artifact("basic"))
    keyless = _confidence_section(_artifact(None))

    assert "score categories from the feed URL on file" in gated
    assert ", using a registered credential." in gated
    assert "registered credential" not in keyless
    assert "requires registration" in gated  # the confidence note, rendered


def test_a_keyless_artifact_is_unchanged() -> None:
    artifact = _artifact(None)

    assert "auth" not in artifact["fetch"] and "auth_kind" not in artifact["fetch"]
    assert not any("registration" in note for note in artifact["confidence"]["notes"])


@pytest.mark.parametrize(
    "mutate",
    [
        lambda f: f.pop("auth_kind"),
        lambda f: f.pop("auth"),
        lambda f: f.update(auth="the-key-itself"),
        lambda f: f.update(auth_kind="cookie"),
    ],
    ids=["auth-without-kind", "kind-without-auth", "auth-not-env-ref", "unknown-kind"],
)
def test_the_schema_holds_the_disclosure_to_its_two_fixed_shapes(mutate: Any) -> None:
    artifact = _artifact("header")
    validate_artifact(artifact)  # control: the unmutated artifact is valid
    mutate(artifact["fetch"])
    with pytest.raises(jsonschema.ValidationError):
        validate_artifact(artifact)


# ---------------------------------------------------------------------------
# Pure pieces


def test_resolved_credential_repr_shows_only_the_kind() -> None:
    credential = resolve_credential(
        FetchAuth(kind="header", secret=ENV, name="X-Api-Key"), {ENV: CREDENTIAL}
    )
    assert CREDENTIAL not in repr(credential)
    assert repr(credential) == "ResolvedCredential(kind='header')"


def test_a_line_break_in_the_value_is_refused() -> None:
    auth = FetchAuth(kind="header", secret=ENV, name="X-Api-Key")
    with pytest.raises(CredentialNotConfiguredError, match="line break"):
        resolve_credential(auth, {ENV: "a\r\nInjected: header"})


def test_surrounding_whitespace_in_the_value_is_trimmed() -> None:
    auth = FetchAuth(kind="header", secret=ENV, name="X-Api-Key")
    assert resolve_credential(auth, {ENV: f"  {CREDENTIAL}\n"}).headers == {"X-Api-Key": CREDENTIAL}


def test_an_unsupported_kind_or_bad_name_is_not_configured() -> None:
    with pytest.raises(CredentialNotConfiguredError, match="not supported"):
        resolve_credential(FetchAuth(kind="oauth", secret=ENV), {ENV: CREDENTIAL})
    with pytest.raises(CredentialNotConfiguredError, match="header name"):
        resolve_credential(FetchAuth(kind="header", secret=ENV, name="Bad Name"), {ENV: "v"})


def test_apply_to_url_keeps_the_configured_query_byte_for_byte() -> None:
    credential = ResolvedCredential(kind="query", query=("key", "a b&c"))
    assert credential.apply_to_url("https://h/f.zip?x=%20y") == "https://h/f.zip?x=%20y&key=a+b%26c"
    assert credential.apply_to_url("https://h/f.zip") == "https://h/f.zip?key=a+b%26c"
    assert ResolvedCredential(kind="header").apply_to_url("https://h/f?q=1") == "https://h/f?q=1"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://h.example/f.zip?apikey=abc#frag", "https://h.example/f.zip"),
        ("https://user:pw@h.example:8443/f.zip", "https://h.example:8443/f.zip"),
        ("https://[2001:db8::1]/f.zip?sig=x", "https://[2001:db8::1]/f.zip"),
    ],
)
def test_published_url_keeps_only_scheme_host_port_and_path(url: str, expected: str) -> None:
    assert published_url(url) == expected


def test_describe_failure_never_includes_the_message() -> None:
    response = requests.models.Response()
    response.status_code = 403
    exc = requests.exceptions.HTTPError("403 for url: https://h/?apikey=abc", response=response)
    assert describe_failure(exc) == "HTTPError (HTTP 403)"
    assert describe_failure(requests.exceptions.ConnectTimeout("https://h/?k=v")) == (
        "ConnectTimeout"
    )


@pytest.mark.parametrize(
    "secret",
    [
        CREDENTIAL,
        "AWS_SECRET_ACCESS_KEY",
        "scorecard_feed_auth_lowercase",
        "SCORECARD_FEED_AUTH_",
        "SCORECARD_FEED_AUTH_" + "A" * 90,
        "",
    ],
)
def test_reference_problem_refuses_anything_but_a_namespaced_name(secret: str) -> None:
    problem = reference_problem(secret)
    assert problem is not None
    # One fixed sentence whatever the input, so it cannot echo the value.
    assert problem == reference_problem("anything else at all")
    assert CREDENTIAL not in problem


def test_reference_problem_accepts_a_namespaced_name() -> None:
    assert reference_problem("SCORECARD_FEED_AUTH_AT_VOR") is None
    assert reference_problem("SCORECARD_FEED_AUTH_511NY") is None


# ---------------------------------------------------------------------------
# The registry loader


def _entry(**fetch_auth: Any) -> dict[str, Any]:
    return {
        "agencies": [
            {
                "id": "gated",
                "name": "Gated",
                "static_gtfs_url": "https://gated.example/feed.zip",
                "fetch_auth": fetch_auth,
            }
        ]
    }


def test_loader_parses_each_kind() -> None:
    (header,) = parse_agencies(_entry(kind="header", name="X-Api-Key", secret=ENV))
    (query,) = parse_agencies(_entry(kind="query", name="apikey", secret=ENV))
    (basic,) = parse_agencies(_entry(kind="basic", secret=ENV))

    assert header.fetch_auth == FetchAuth(kind="header", secret=ENV, name="X-Api-Key")
    assert query.fetch_auth == FetchAuth(kind="query", secret=ENV, name="apikey")
    assert basic.fetch_auth == FetchAuth(kind="basic", secret=ENV, name="")


def test_a_record_without_fetch_auth_is_keyless() -> None:
    raw = _entry()
    del raw["agencies"][0]["fetch_auth"]
    (agency,) = parse_agencies(raw)
    assert agency.fetch_auth is None


@pytest.mark.parametrize(
    ("block", "message"),
    [
        ({"kind": "cookie", "secret": ENV}, "kind must be one of"),
        ({"kind": "header", "secret": ENV}, "HTTP header name"),
        ({"kind": "query", "name": "a b", "secret": ENV}, "query-parameter name"),
        ({"kind": "basic", "name": "Authorization", "secret": ENV}, "not used with kind basic"),
        ({"kind": "header", "name": "X-Api-Key"}, "must name the environment variable"),
        ({"kind": "header", "name": "X-Api-Key", "secret": ENV, "token": "x"}, "unknown"),
    ],
)
def test_loader_refuses_a_malformed_block(block: dict[str, Any], message: str) -> None:
    with pytest.raises(AgencyConfigError, match=message):
        parse_agencies(_entry(**block))


def test_loader_refuses_a_non_mapping_block() -> None:
    raw = _entry()
    raw["agencies"][0]["fetch_auth"] = ENV
    with pytest.raises(AgencyConfigError, match="must be a mapping"):
        parse_agencies(raw)


def test_loader_refuses_a_credential_over_plain_http() -> None:
    raw = _entry(kind="header", name="X-Api-Key", secret=ENV)
    raw["agencies"][0]["static_gtfs_url"] = "http://gated.example/feed.zip"
    with pytest.raises(AgencyConfigError, match="requires an https"):
        parse_agencies(raw)


def test_loader_errors_never_quote_the_secret_field() -> None:
    """Shape errors are raised with a literal in ``secret``; none may echo it."""
    for block in (
        {"kind": "cookie", "secret": CREDENTIAL},
        {"kind": "header", "secret": CREDENTIAL},
        {"kind": "basic", "name": "x", "secret": CREDENTIAL},
    ):
        with pytest.raises(AgencyConfigError) as caught:
            parse_agencies(_entry(**block))
        assert CREDENTIAL not in str(caught.value)


# ---------------------------------------------------------------------------
# lint --strict


def _gated_record(secret: str, url: str = "https://gated.example/feed.zip") -> str:
    return (
        "  - id: gated\n"
        "    name: Gated Transit\n"
        f"    static_gtfs_url: {url}\n"
        "    mdb_id: mdb-1\n"
        "    fetch_auth:\n"
        "      kind: header\n"
        "      name: X-Api-Key\n"
        f"      secret: {secret}\n"
    )


def test_lint_strict_refuses_a_literal_token_and_never_prints_it(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    isolated_repo_root.mkdir(parents=True)
    registry = isolated_repo_root / "agencies.yaml"
    registry.write_text("agencies:\n" + _gated_record(CREDENTIAL))
    # The sabotage landed twice: in the file, and in the parsed record lint sees.
    assert CREDENTIAL in registry.read_text()
    (loaded,) = parse_agencies(yaml.safe_load(registry.read_text()))
    assert loaded.fetch_auth is not None and loaded.fetch_auth.secret == CREDENTIAL

    assert cli.main(["lint", "--strict"]) == 1

    captured = capsys.readouterr()
    assert "literal_credential\tgated\t" in captured.out
    assert "FAILED" in captured.err and "literal_credential" in captured.err
    assert CREDENTIAL not in captured.out + captured.err


def test_lint_strict_passes_the_same_record_with_a_reference(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Negative control: only the secret value differs from the test above, so
    that failure was this rule and not some other hygiene kind."""
    isolated_repo_root.mkdir(parents=True)
    (isolated_repo_root / "agencies.yaml").write_text("agencies:\n" + _gated_record(ENV))

    assert cli.main(["lint", "--strict"]) == 0
    assert "literal_credential" not in capsys.readouterr().out


def test_lint_flags_a_namespace_escape_and_a_duplicated_query_parameter() -> None:
    escape = Agency(
        id="escape",
        name="Escape",
        static_gtfs_url="https://e.example/f.zip",
        mdb_id="m1",
        fetch_auth=FetchAuth(kind="header", secret="GITHUB_TOKEN", name="X-Api-Key"),
    )
    doubled = Agency(
        id="doubled",
        name="Doubled",
        static_gtfs_url=f"https://d.example/f.zip?apikey={CREDENTIAL}",
        mdb_id="m2",
        fetch_auth=FetchAuth(kind="query", secret=ENV, name="apikey"),
    )
    issues = [i for i in lint_registry([escape, doubled]) if i.kind == "literal_credential"]

    assert {i.agency_id for i in issues} == {"escape", "doubled"}
    assert all(CREDENTIAL not in i.detail and "GITHUB_TOKEN" not in i.detail for i in issues)


def test_lint_flags_user_info_in_any_feed_url_without_printing_it() -> None:
    password = "pw-" + "not-real"
    agency = Agency(
        id="userinfo",
        name="Userinfo",
        static_gtfs_url=f"http://someone:{password}@u.example/f.zip",
        rt_urls={"trip_updates": f"https://someone:{password}@u.example/tu"},
        mdb_id="m",
    )
    issues = lint_registry([agency])

    literal = [i for i in issues if i.kind == "literal_credential"]
    assert {i.detail.split(" ")[0] for i in literal} == {"static_gtfs_url", "rt_urls.trip_updates"}
    # non_https_url is still reported, but its detail no longer echoes the URL.
    assert [i.detail for i in issues if i.kind == "non_https_url"] == [""]
    assert all(password not in i.detail for i in issues)


def test_publisher_published_url_keys_stay_advisory() -> None:
    """Open feeds that print their key on the publisher's page (the registry
    carries a few dozen) are not literal_credential: that rule is for keys
    issued to an account, which is what fetch_auth keeps out of the record."""
    agency = Agency(
        id="open",
        name="Open",
        static_gtfs_url="https://o.example/gtfs?apiKey=opendata-published-key",
        mdb_id="m",
    )
    assert not [i for i in lint_registry([agency]) if i.kind == "literal_credential"]


# ---------------------------------------------------------------------------
# Liveness never probes a credentialed URL without its credential


def test_liveness_sweep_skips_credentialed_records(
    isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_repo_root.mkdir(parents=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        + _gated_record(ENV)
        + "  - id: open\n    name: Open\n    static_gtfs_url: https://o.example/f.zip\n"
    )
    checked: list[str] = []

    def fake_check(url: str, prev: object, **_: object) -> tuple[object, str]:
        from scorecard_pipeline.liveness import UNCHANGED, LivenessRecord

        checked.append(url)
        return LivenessRecord(url=url, status=304), UNCHANGED

    monkeypatch.setattr("scorecard_pipeline.liveness.check_feed", fake_check)

    assert cli.main(["liveness"]) == 0
    assert checked == ["https://o.example/f.zip"]


def test_skip_unchanged_always_scores_a_credentialed_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    AGENCIES["gated"] = _agency("https://gated.example/feed.zip")
    monkeypatch.setattr(cli, "_artifact_contract_current", lambda _id: True)

    def must_not_run(*_a: object, **_k: object) -> None:
        raise AssertionError("the keyless liveness probe ran against a credentialed URL")

    monkeypatch.setattr("scorecard_pipeline.liveness.check_feed", must_not_run)

    assert cli._liveness_unchanged("gated") is False


# ---------------------------------------------------------------------------
# gitleaks: the rule exists, is not shadowed, and fires


def _gitleaks_config() -> dict[str, Any]:
    return tomllib.loads(GITLEAKS_CONFIG.read_text())


def test_gitleaks_rule_is_scoped_to_the_registry_and_allows_only_references() -> None:
    (rule,) = [r for r in _gitleaks_config()["rules"] if r["id"] == GITLEAKS_RULE]
    pattern = re.compile(rule["regex"])
    (allow,) = rule["allowlists"]

    assert re.search(rule["path"], "registry/at/vor.yaml")
    assert not re.search(rule["path"], "pipeline/src/scorecard_pipeline/fetch.py")
    literal = pattern.search(f"      secret: {CREDENTIAL}")
    reference = pattern.search(f"      secret: {ENV}")
    flow = pattern.search(f"  fetch_auth: {{kind: header, secret: '{CREDENTIAL}'}}")
    assert literal and reference and flow
    group = rule["secretGroup"]
    assert literal.group(group) == CREDENTIAL and flow.group(group) == CREDENTIAL
    assert not any(re.search(a, literal.group(group)) for a in allow["regexes"])
    assert any(re.search(a, reference.group(group)) for a in allow["regexes"])


def test_no_global_path_allowlist_shadows_the_registry() -> None:
    """The failure this rule was built around: gitleaks skips a globally
    path-allowlisted file entirely, for every rule, so a registry path in any
    global allowlist makes the rule above report nothing, ever."""
    config = _gitleaks_config()
    tables = list(config.get("allowlists", [])) + (
        [config["allowlist"]] if "allowlist" in config else []
    )
    for table in tables:
        for path_pattern in table.get("paths", []):
            assert not re.search(path_pattern, "registry/at/vor.yaml"), path_pattern
            assert not re.search(path_pattern, "registry/intake.yaml"), path_pattern


def test_the_registry_url_line_allowlist_does_not_cover_a_secret_line() -> None:
    config = _gitleaks_config()
    line_patterns = [
        pattern
        for table in config["allowlists"]
        if table.get("regexTarget") == "line"
        for pattern in table.get("regexes", [])
    ]
    assert line_patterns
    url_line = "    static_gtfs_url: https://h.example/f.zip?apiKey=published"
    assert any(re.search(p, url_line) for p in line_patterns)
    for line in (
        f"      secret: {CREDENTIAL}",
        f'    "    static_gtfs_url: https://h/?k={CREDENTIAL}"',
    ):
        assert not any(re.search(p, line) for p in line_patterns), line


GITLEAKS = shutil.which("gitleaks")
needs_gitleaks = pytest.mark.skipif(
    GITLEAKS is None, reason="gitleaks is not installed; the structural tests above still run"
)


def _gitleaks_scan(root: Path, config: Path) -> subprocess.CompletedProcess[str]:
    assert GITLEAKS is not None
    return subprocess.run(  # noqa: S603 - fixed argv, a scratch directory
        [
            GITLEAKS,
            "dir",
            "--no-banner",
            "--redact",
            "--config",
            str(config),
            "--report-format",
            "json",
            "--report-path",
            str(root / "report.json"),
            ".",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def _plant(root: Path, secret: str) -> Path:
    shard = root / "registry" / "at" / "vor.yaml"
    shard.parent.mkdir(parents=True)
    shard.write_text("agencies:\n" + _gated_record(secret))
    return shard


@needs_gitleaks
def test_gitleaks_fails_on_a_planted_literal_and_passes_a_reference(tmp_path: Path) -> None:
    literal_root, reference_root = tmp_path / "literal", tmp_path / "reference"
    config = tmp_path / "gitleaks.toml"
    shutil.copy(GITLEAKS_CONFIG, config)
    planted = _plant(literal_root, CREDENTIAL)
    _plant(reference_root, ENV)
    assert CREDENTIAL in planted.read_text()  # the sabotage landed

    red = _gitleaks_scan(literal_root, config)
    green = _gitleaks_scan(reference_root, config)

    assert red.returncode == 1, red.stderr
    findings = json.loads((literal_root / "report.json").read_text())
    assert [(f["RuleID"], f["File"]) for f in findings] == [(GITLEAKS_RULE, "registry/at/vor.yaml")]
    assert green.returncode == 0, green.stderr


@needs_gitleaks
def test_gitleaks_goes_blind_if_the_old_path_allowlist_returns(tmp_path: Path) -> None:
    """Why test_no_global_path_allowlist_shadows_the_registry exists: put the
    old whole-file registry allowlist back and the planted literal passes."""
    config = tmp_path / "gitleaks.toml"
    shadowed = GITLEAKS_CONFIG.read_text() + (
        '\n[[allowlists]]\ndescription = "the pre-#371 shape"\n'
        "paths = ['''^registry/.*\\.ya?ml$''']\n"
    )
    config.write_text(shadowed)
    root = tmp_path / "scan"
    planted = _plant(root, CREDENTIAL)
    assert "^registry/" in config.read_text() and CREDENTIAL in planted.read_text()

    assert _gitleaks_scan(root, config).returncode == 0
