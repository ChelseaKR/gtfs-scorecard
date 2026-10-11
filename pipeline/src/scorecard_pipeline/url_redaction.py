"""Remove credentials from URLs before they are published.

A scorecard records two URLs per feed: the configured feed URL
(``feed.static_url``) and the URL that actually served the bytes
(``fetch.final_url``). Both are published in the per-agency artifacts, and the
configured URL also reaches the catalog, the directory, the API, the scorecard
pages and their JSON-LD ``isBasedOn``. Either can carry a credential:

- A redirect to a presigned object in someone else's bucket (S3, R2, GCS,
  Azure Blob, GitHub release assets) carries the temporary credential and
  signature it was signed with (``AWSAccessKeyId``, ``Signature``,
  ``x-amz-security-token``, ``X-Amz-Credential``, ``sig``, ``jwt``).
- Some publishers put an API key in the download URL itself (``apiKey``,
  ``key``), and some redirects add one.

This module is the one rule for every published URL (ADR 0066). A matching
query parameter keeps its name and its value becomes ``REDACTED``, so a reader
can still see that the URL needed one; every other part of the URL is kept
exactly, and a user-info part (``user:password@``), a credential by
definition, is dropped. A URL with nothing to redact is returned unchanged,
byte for byte. Nothing here changes what the pipeline fetches: it is applied
where a URL is published, never where one is requested.

The credentialed-fetch path keeps its stricter rule
(``feed_auth.published_url`` drops the whole query), because there the query is
known to carry our own credential.

The module is standard library only so the deployment's artifact assembly
(``scripts/assemble_public_artifacts.sh``) can run it as a script without the
pipeline's environment::

    python3 url_redaction.py ROOT [--write]

which counts (or, with ``--write``, rewrites) every credential-like URL value
in the JSON files under ROOT. It prints counts and file names, never a value.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Final
from urllib.parse import unquote_plus, urlsplit, urlunsplit

#: What a credential-like query value is replaced with.
REDACTED: Final = "REDACTED"

#: Query parameter names whose value is a credential, a signature, or part of
#: a presigned request, compared case-insensitively. An explicit list, not a
#: pattern, so a reviewer can read exactly what is removed; every entry has a
#: test (tests/test_url_redaction.py).
CREDENTIAL_QUERY_PARAMS: Final[frozenset[str]] = frozenset(
    {
        # AWS Signature Version 2 presigned URLs (and the security token a
        # temporary credential adds to either version).
        "awsaccesskeyid",
        "signature",
        "expires",
        "x-amz-security-token",
        # Other object stores' access-key-id parameters (Aliyun OSS, generic).
        "accesskeyid",
        "ossaccesskeyid",
        # Google Cloud Storage V2 signed URLs.
        "googleaccessid",
        # Azure Blob shared access signatures and GitHub release-asset links.
        "sig",
        "jwt",
        # API keys and tokens put in the URL by a publisher or a redirect.
        "key",
        "apikey",
        "api_key",
        "api-key",
        "x-api-key",
        "token",
        "access_token",
        "access-token",
        "accesstoken",
        "auth",
        "auth_token",
        "authorization",
        "subscription-key",
        "ocp-apim-subscription-key",
        "client_secret",
        "secret",
        "password",
    }
)

#: Name prefixes whose every parameter is part of a presigned request: AWS
#: Signature Version 4 (``X-Amz-Algorithm``, ``X-Amz-Credential``,
#: ``X-Amz-Signature``, ...) and Google Cloud Storage V4 (``X-Goog-...``).
CREDENTIAL_QUERY_PREFIXES: Final[tuple[str, ...]] = ("x-amz-", "x-goog-")

_URL_START: Final = re.compile(r"^https?://", re.IGNORECASE)
#: A JSON string token. Scanning a valid JSON document from its start with
#: this pattern visits every string exactly once, because outside a string a
#: JSON text has no quote characters.
_JSON_STRING: Final = re.compile(r'"(?:[^"\\]|\\.)*"', re.DOTALL)


def is_credential_param(name: str) -> bool:
    """Whether a query parameter name (raw or percent-encoded) is credential-like."""
    lowered = unquote_plus(name).strip().lower()
    return lowered in CREDENTIAL_QUERY_PARAMS or lowered.startswith(CREDENTIAL_QUERY_PREFIXES)


def _redact_query(query: str) -> str:
    pairs = []
    for pair in query.split("&"):
        name, sep, _value = pair.partition("=")
        if sep and is_credential_param(name):
            pairs.append(f"{name}={REDACTED}")
        else:
            pairs.append(pair)
    return "&".join(pairs)


def redact_url_text(url: str) -> str:
    """``url`` with credential-like query values replaced and user-info dropped.

    Returns ``url`` itself, unchanged, when there is nothing to redact, so a
    clean URL stays byte-identical. A string that does not parse as a URL is
    returned unchanged too: it is not a URL this rule can speak for.
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    netloc = parts.netloc.rpartition("@")[2]
    query = _redact_query(parts.query) if parts.query else parts.query
    if netloc == parts.netloc and query == parts.query:
        return url
    return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))


def redact_url(value: object) -> str | None:
    """A published URL field: the redacted text, or None when there is none.

    The same contract as ``history_export``'s column helper: None, a non-string
    and a blank string are all "not recorded".
    """
    if not isinstance(value, str) or not value.strip():
        return None
    return redact_url_text(value)


def redact_urls_in(document: Any) -> tuple[Any, int]:
    """A copy of a JSON-shaped value with every http(s) URL string redacted.

    Walks dicts and lists; keys are left alone. Returns the new value and how
    many strings changed. Every URL-valued field is covered, not a named
    list, so a URL field added later is redacted without anyone remembering to.
    """
    if isinstance(document, str):
        if _URL_START.match(document):
            redacted = redact_url_text(document)
            return redacted, int(redacted != document)
        return document, 0
    if isinstance(document, dict):
        changed = 0
        out: dict[Any, Any] = {}
        for key, item in document.items():
            out[key], count = redact_urls_in(item)
            changed += count
        return out, changed
    if isinstance(document, list):
        changed = 0
        items = []
        for item in document:
            new, count = redact_urls_in(item)
            items.append(new)
            changed += count
        return items, changed
    return document, 0


def redact_artifact(artifact: dict[str, Any]) -> int:
    """Redact every URL in a loaded artifact in place; return how many changed.

    For a renderer that has just read an artifact written before publish-time
    redaction existed: the in-memory record is what every page, export and
    API row is built from, so redacting it here is enough for all of them.
    """
    redacted, changed = redact_urls_in(artifact)
    if changed:
        artifact.clear()
        artifact.update(redacted)
    return changed


def redact_json_text(text: str) -> tuple[str, int]:
    """Redact URL strings in a JSON document's text without re-serializing it.

    Only the changed string tokens are rewritten, so every other byte (key
    order, indentation, escaping) is preserved and a file with nothing to
    redact is returned unchanged.
    """
    changed = 0

    def _replace(match: re.Match[str]) -> str:
        nonlocal changed
        token = match.group(0)
        if "http" not in token[:8].lower():
            return token
        try:
            value = json.loads(token)
        except ValueError:
            return token
        if not isinstance(value, str) or not _URL_START.match(value):
            return token
        redacted = redact_url_text(value)
        if redacted == value:
            return token
        changed += 1
        return json.dumps(redacted, ensure_ascii=token.isascii())

    return _JSON_STRING.sub(_replace, text), changed


def _json_files(root: Path) -> Iterable[Path]:
    if root.is_file():
        yield root
        return
    yield from sorted(path for path in root.rglob("*.json") if path.is_file())


def redact_tree(root: Path, *, write: bool) -> tuple[int, int]:
    """Count (and with ``write``, rewrite) credential-like URLs under ``root``.

    Returns (files with a redaction, URL strings redacted). Files are read and
    written as UTF-8; a file that is not UTF-8 is skipped, since no artifact
    this project writes is anything else.
    """
    files = 0
    strings = 0
    for path in _json_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if "?" not in text and "@" not in text:
            continue
        redacted, changed = redact_json_text(text)
        if not changed:
            continue
        files += 1
        strings += changed
        if write:
            path.write_text(redacted, encoding="utf-8")
    return files, strings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Redact credential-like query values in the JSON files under a directory."
    )
    parser.add_argument("root", type=Path, help="a JSON file or a directory to scan")
    parser.add_argument(
        "--write", action="store_true", help="rewrite the files (default: count only)"
    )
    args = parser.parse_args(argv)
    if not args.root.exists():
        print(f"url_redaction: {args.root} does not exist", file=sys.stderr)
        return 2
    files, strings = redact_tree(args.root, write=args.write)
    verb = "redacted" if args.write else "would redact"
    print(f"url_redaction: {verb} {strings} URL value(s) in {files} file(s) under {args.root}")
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the assembly script
    raise SystemExit(main())
