"""The one URL redaction rule for published URLs (ADR 0066).

Every value below is a made-up placeholder. No real key, token or signature
appears in this file.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.config import Agency
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.publish import build_artifact
from scorecard_pipeline.score import build_scorecard
from scorecard_pipeline.tool_profiles import _load_snapshot
from scorecard_pipeline.url_redaction import (
    CREDENTIAL_QUERY_PARAMS,
    CREDENTIAL_QUERY_PREFIXES,
    REDACTED,
    is_credential_param,
    main,
    redact_artifact,
    redact_json_text,
    redact_tree,
    redact_url,
    redact_url_text,
    redact_urls_in,
)

ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "pipeline" / "src" / "scorecard_pipeline" / "url_redaction.py"
FAKE = "PLACEHOLDER-NOT-A-SECRET"

#: One test per listed name: the spelling a publisher or an object store uses
#: in the wild, which differs in case from the lowercase list entry.
LISTED_SPELLINGS: dict[str, str] = {
    "awsaccesskeyid": "AWSAccessKeyId",
    "signature": "Signature",
    "expires": "Expires",
    "x-amz-security-token": "x-amz-security-token",
    "accesskeyid": "AccessKeyId",
    "ossaccesskeyid": "OSSAccessKeyId",
    "googleaccessid": "GoogleAccessId",
    "sig": "sig",
    "jwt": "jwt",
    "key": "Key",
    "apikey": "apiKey",
    "api_key": "api_key",
    "api-key": "API-Key",
    "x-api-key": "X-API-KEY",
    "token": "token",
    "access_token": "access_token",
    "access-token": "Access-Token",
    "accesstoken": "accessToken",
    "auth": "auth",
    "auth_token": "auth_token",
    "authorization": "Authorization",
    "subscription-key": "subscription-key",
    "ocp-apim-subscription-key": "Ocp-Apim-Subscription-Key",
    "client_secret": "client_secret",
    "secret": "secret",
    "password": "password",
}

#: One test per prefix family, with each parameter a presigned request uses.
PREFIXED_SPELLINGS = (
    "X-Amz-Algorithm",
    "X-Amz-Credential",
    "X-Amz-Date",
    "X-Amz-Expires",
    "X-Amz-SignedHeaders",
    "X-Amz-Signature",
    "X-Amz-Security-Token",
    "X-Amz-Content-Sha256",
    "X-Goog-Algorithm",
    "X-Goog-Credential",
    "X-Goog-Signature",
)


def test_every_listed_name_has_a_test_spelling() -> None:
    assert set(LISTED_SPELLINGS) == set(CREDENTIAL_QUERY_PARAMS)
    covered = {
        prefix
        for prefix in CREDENTIAL_QUERY_PREFIXES
        if any(spelling.lower().startswith(prefix) for spelling in PREFIXED_SPELLINGS)
    }
    assert covered == set(CREDENTIAL_QUERY_PREFIXES)


@pytest.mark.parametrize("spelling", sorted(LISTED_SPELLINGS.values()))
def test_each_listed_parameter_is_redacted_case_insensitively(spelling: str) -> None:
    url = f"https://feeds.example.org/gtfs.zip?format=zip&{spelling}={FAKE}&v=2"
    redacted = redact_url_text(url)
    assert redacted == f"https://feeds.example.org/gtfs.zip?format=zip&{spelling}={REDACTED}&v=2"
    assert FAKE not in redacted
    assert is_credential_param(spelling)
    assert is_credential_param(spelling.upper())
    assert is_credential_param(spelling.lower())


@pytest.mark.parametrize("spelling", PREFIXED_SPELLINGS)
def test_each_presigned_prefix_parameter_is_redacted(spelling: str) -> None:
    url = f"https://bucket.s3.amazonaws.com/feed.zip?{spelling}={FAKE}"
    assert redact_url_text(url) == f"https://bucket.s3.amazonaws.com/feed.zip?{spelling}={REDACTED}"
    assert is_credential_param(spelling.lower())


def test_a_whole_sigv2_presigned_redirect_keeps_only_its_harmless_parameters() -> None:
    url = (
        "https://repo-bucket.s3.amazonaws.com/feed.zip?"
        "response-content-disposition=attachment%3B%20filename%3Dfeed.zip"
        f"&AWSAccessKeyId={FAKE}&Signature={FAKE}%3D&x-amz-security-token={FAKE}"
        f"&Expires=1790000000&rid=abc"
    )
    assert redact_url_text(url) == (
        "https://repo-bucket.s3.amazonaws.com/feed.zip?"
        "response-content-disposition=attachment%3B%20filename%3Dfeed.zip"
        f"&AWSAccessKeyId={REDACTED}&Signature={REDACTED}&x-amz-security-token={REDACTED}"
        f"&Expires={REDACTED}&rid=abc"
    )


def test_a_percent_encoded_parameter_name_is_still_matched() -> None:
    url = f"https://example.org/f.zip?api%5Fkey={FAKE}"
    assert redact_url_text(url) == f"https://example.org/f.zip?api%5Fkey={REDACTED}"


@pytest.mark.parametrize(
    "name",
    [
        "response-content-disposition",
        "rid",
        "alt",
        "OperatorCode",
        "operatorIds",
        "se",
        "sp",
        "skoid",
        "format",
        "keyword",
        "monkey",
        "tokens_left",
    ],
)
def test_other_parameters_are_left_alone(name: str) -> None:
    url = f"https://example.org/f.zip?{name}=visible"
    assert redact_url_text(url) is url
    assert not is_credential_param(name)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/gtfs.zip",
        "https://example.org/gtfs.zip?",
        "https://example.org/gtfs.zip#frag",
        "https://example.org/gtfs.zip?flag&key",
        "HTTPS://Example.org:8443/a%20b/gtfs.zip?x=1&y=2",
    ],
)
def test_a_url_with_nothing_to_redact_is_returned_unchanged(url: str) -> None:
    assert redact_url_text(url) is url


def test_user_info_is_dropped() -> None:
    url = f"https://user:{FAKE}@example.org:8080/gtfs.zip?x=1"
    assert redact_url_text(url) == "https://example.org:8080/gtfs.zip?x=1"


def test_the_fragment_is_kept() -> None:
    url = f"https://example.org/f.zip?token={FAKE}#part"
    assert redact_url_text(url) == f"https://example.org/f.zip?token={REDACTED}#part"


def test_redact_url_treats_absence_as_absence() -> None:
    assert redact_url(None) is None
    assert redact_url("") is None
    assert redact_url("   ") is None
    assert redact_url(17) is None
    assert redact_url(f"https://example.org/?key={FAKE}") == f"https://example.org/?key={REDACTED}"


def test_redact_urls_in_walks_every_url_field_and_leaves_keys_alone() -> None:
    document: dict[str, Any] = {
        "feed": {"static_url": f"https://a.example/f.zip?apiKey={FAKE}"},
        "fetch": {"final_url": f"https://b.example/f.zip?sig={FAKE}"},
        "rt": [f"http://c.example/rt?token={FAKE}", "not a url ?key=x"],
        f"https://key.example/?key={FAKE}": 1,
        "score": 88.0,
    }
    redacted, changed = redact_urls_in(document)
    assert changed == 3
    assert redacted["feed"]["static_url"] == f"https://a.example/f.zip?apiKey={REDACTED}"
    assert redacted["fetch"]["final_url"] == f"https://b.example/f.zip?sig={REDACTED}"
    assert redacted["rt"] == [f"http://c.example/rt?token={REDACTED}", "not a url ?key=x"]
    assert redacted["score"] == 88.0
    # The input is not mutated.
    assert FAKE in document["feed"]["static_url"]


def test_redact_artifact_mutates_in_place_and_keeps_key_order() -> None:
    artifact = {"a": 1, "fetch": {"final_url": f"https://x.example/?Signature={FAKE}"}, "z": 2}
    assert redact_artifact(artifact) == 1
    assert list(artifact) == ["a", "fetch", "z"]
    assert FAKE not in json.dumps(artifact)
    assert redact_artifact(artifact) == 0


def test_redact_json_text_rewrites_only_the_changed_strings() -> None:
    document: dict[str, Any] = {
        "feed": {"static_url": f"https://a.example/f.zip?apiKey={FAKE}", "name": "Café"},
        "fetch": {"final_url": "https://b.example/f.zip?x=1"},
        "note": 'a "quoted" https://c.example/?key=inside-prose',
    }
    text = json.dumps(document, indent=2, sort_keys=True) + "\n"
    redacted, changed = redact_json_text(text)
    assert changed == 1
    expected = dict(document)
    expected["feed"] = dict(
        document["feed"], static_url=f"https://a.example/f.zip?apiKey={REDACTED}"
    )
    assert redacted == json.dumps(expected, indent=2, sort_keys=True) + "\n"
    clean = json.dumps({"u": "https://a.example/f.zip"}, indent=2)
    assert redact_json_text(clean) == (clean, 0)


def test_redact_tree_counts_without_writing_and_rewrites_with_write(tmp_path: Path) -> None:
    dirty = tmp_path / "agency" / "latest.json"
    dirty.parent.mkdir()
    dirty.write_text(json.dumps({"fetch": {"final_url": f"https://x.example/?jwt={FAKE}"}}))
    clean = tmp_path / "agency" / "badge.json"
    clean.write_text('{"label": "GTFS"}')
    before = dirty.read_bytes()
    assert redact_tree(tmp_path, write=False) == (1, 1)
    assert dirty.read_bytes() == before
    assert redact_tree(tmp_path, write=True) == (1, 1)
    assert FAKE not in dirty.read_text()
    assert clean.read_text() == '{"label": "GTFS"}'
    assert redact_tree(tmp_path, write=True) == (0, 0)


def test_cli_prints_counts_and_never_a_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "latest.json"
    target.write_text(json.dumps({"u": f"https://x.example/?apiKey={FAKE}"}))
    assert main([str(tmp_path)]) == 0
    out = capsys.readouterr()
    assert "would redact 1 URL value(s) in 1 file(s)" in out.out
    assert FAKE not in out.out + out.err
    assert main([str(tmp_path), "--write"]) == 0
    assert FAKE not in target.read_text()
    assert main([str(tmp_path / "missing")]) == 2


def test_the_module_runs_as_a_standalone_script(tmp_path: Path) -> None:
    """The assembly script runs it with ``python3 -I`` and no pipeline env."""
    target = tmp_path / "x.json"
    target.write_text(json.dumps({"u": f"https://x.example/?token={FAKE}"}))
    result = subprocess.run(  # noqa: S603 - fixed interpreter and test-owned paths
        [sys.executable, "-I", str(MODULE), str(tmp_path), "--write"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "redacted 1 URL value(s)" in result.stdout
    assert FAKE not in result.stdout + result.stderr + target.read_text()


def test_public_artifact_assembly_redacts_every_copied_json(tmp_path: Path) -> None:
    source = tmp_path / "artifacts"
    agency = source / "demo"
    agency.mkdir(parents=True)
    (source / "index.json").write_text(json.dumps({"agencies": {"demo": {}}}))
    artifact = {
        "feed": {"static_url": f"https://pub.example/gtfs?apiKey={FAKE}"},
        "fetch": {"final_url": f"https://b.s3.amazonaws.com/f.zip?AWSAccessKeyId={FAKE}"},
    }
    for name in ("latest.json", "2026-07-14.json"):
        (agency / name).write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    (source / "directory.json").write_text(
        json.dumps({"agencies": [{"feed_url": f"https://pub.example/gtfs?apiKey={FAKE}"}]})
    )
    destination = tmp_path / "site"
    bash = shutil.which("bash")
    assert bash is not None
    result = subprocess.run(  # noqa: S603 - fixed executable and test-owned paths
        [
            bash,
            str(ROOT / "pipeline" / "scripts" / "assemble_public_artifacts.sh"),
            str(source),
            str(destination),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert FAKE not in result.stdout + result.stderr
    for path in destination.rglob("*.json"):
        assert FAKE not in path.read_text(), path
    assert REDACTED in (destination / "demo" / "latest.json").read_text()
    # The source store is not modified: the boundary redacts the copy.
    assert FAKE in (agency / "latest.json").read_text()


def test_publish_records_redacted_urls_and_leaves_the_fetch_alone() -> None:
    keyed = f"https://pub.example/gtfs.zip?apiKey={FAKE}"
    presigned = f"https://b.s3.amazonaws.com/f.zip?X-Amz-Credential={FAKE}&X-Amz-Signature={FAKE}"
    agency = Agency(id="demo", name="Demo", static_gtfs_url=keyed, license_note="test")
    fetch = FetchResult(
        agency_id="demo",
        path=Path("/tmp/gtfs.zip"),
        url=keyed,
        fetched_date=dt.date(2026, 10, 11),
        sha256="a" * 64,
        size_bytes=1024,
        reused=False,
        source="origin",
        final_url=presigned,
    )
    card = build_scorecard([CategoryResult(name="correctness", score=88.0, summary="s")])
    artifact = build_artifact(agency, fetch, card, dt.datetime(2026, 10, 11, tzinfo=dt.UTC))
    assert artifact["feed"]["static_url"] == f"https://pub.example/gtfs.zip?apiKey={REDACTED}"
    assert artifact["fetch"]["final_url"] == (
        f"https://b.s3.amazonaws.com/f.zip?X-Amz-Credential={REDACTED}&X-Amz-Signature={REDACTED}"
    )
    assert FAKE not in json.dumps(artifact)
    # What the pipeline fetches is untouched: the registry URL and the fetch
    # record still hold the configured URL.
    assert agency.static_gtfs_url == keyed
    assert fetch.url == keyed


def test_tool_profile_declarations_answer_to_the_redacted_url(tmp_path: Path) -> None:
    keyed = f"https://pub.example/gtfs.zip?apiKey={FAKE}"
    snapshot = tmp_path / "publishers.json"
    snapshot.write_text(
        json.dumps(
            {"feeds": {"demo": {"url": keyed, "publisher_name": "Pub", "publisher_url": ""}}}
        )
    )
    index = _load_snapshot(snapshot)
    assert index[keyed] == ("Pub", "")
    assert index[redact_url_text(keyed)] == ("Pub", "")
