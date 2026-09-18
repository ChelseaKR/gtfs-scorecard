"""Credentialed feed sources: the registry names a secret and never holds one.

Issue #371. A few publishers put a GTFS Schedule feed whose license already
permits reuse behind a registration wall: the file endpoint answers 401 until
a registered account's key is presented. docs/follow-ups.md names Austria's
Verkehrsverbünde and New York's ``datatools-511ny`` bucket. A registry record
opts in with::

    fetch_auth:
      kind: header                          # header | query | basic
      name: X-Api-Key                       # header or query-parameter name
      secret: SCORECARD_FEED_AUTH_EXAMPLE   # the NAME of an environment variable

Three properties carry the design, and each has a test that fails without it.

1. **Fail closed.** A variable that is unset, empty, or malformed raises
   CredentialNotConfiguredError before any request is made. A credentialed
   record never falls back to the Mobility Database mirror and is never
   retried without its credential. The run records the feed as unreachable
   with the reason "credential not configured" and writes no artifact, so no
   grade is published for bytes that were never fetched. A silent mirror
   fallback would publish a grade for bytes from somewhere other than the
   source the record names, the same shape as the empty-archive defects this
   repository has already withdrawn grades for.
2. **A reference, never a value.** ``secret`` must be an environment variable
   name in the ``SCORECARD_FEED_AUTH_`` namespace. Anything else is refused by
   ``scorecard lint --strict`` as a literal credential, and here at fetch time,
   where it is never read. The namespace also stops a record from naming some
   other process secret (a cloud key, the Actions token) and having the
   fetcher send it to whatever host the record names.
3. **Nothing the credential touched is published.** The artifact says
   ``auth: env-ref`` and the kind. The recorded final URL of a credentialed
   fetch drops its query string, and a failed request is reported by exception
   class and HTTP status only, because a requests error quotes the full URL
   and a ``query`` credential rides in it. Credential headers go only to the
   configured URL's own origin, never to a host a redirect points at.

Storing, rotating, or minting credentials (OAuth) is out of scope. The operator
puts the value in the environment (an Actions secret, a Lambda variable); the
registry and the published record never see it.
"""

from __future__ import annotations

import base64
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlencode, urlsplit, urlunsplit

from .config import FetchAuth

FETCH_AUTH_KINDS = ("header", "query", "basic")
FETCH_AUTH_KEYS = frozenset({"kind", "name", "secret"})

#: Every credential reference lives in this namespace. See property 2 above.
REFERENCE_ENV_PREFIX = "SCORECARD_FEED_AUTH_"
REFERENCE_ENV_PATTERN = re.compile(r"^SCORECARD_FEED_AUTH_[A-Z0-9]+(?:_[A-Z0-9]+)*$")
REFERENCE_ENV_MAX_LENGTH = 96

#: RFC 9110 token characters, the only ones a header field name may contain.
HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]{1,64}$")
#: Unreserved URL characters, so a parameter name never needs escaping.
QUERY_NAME_PATTERN = re.compile(r"^[A-Za-z0-9._~-]{1,64}$")

#: What the artifact's ``fetch.auth`` says: a credential was supplied by
#: reference. The artifact never carries more than this and the kind.
AUTH_DISCLOSURE = "env-ref"
#: The fixed public reason recorded for a credentialed record that cannot be
#: fetched. Neutral by design: it describes our configuration, not the feed.
NOT_CONFIGURED = "credential not configured"

_REFERENCE_PROBLEM = (
    "fetch_auth.secret must be the name of an environment variable matching "
    f"{REFERENCE_ENV_PREFIX}<NAME>; the value on file is not one, so it is treated as "
    "a literal credential (the value is not printed)"
)


def reference_problem(secret: object) -> str | None:
    """Why ``secret`` is not an acceptable credential reference, or None.

    The sentence never repeats the value. When the value is a literal
    credential, echoing it into a lint report or a CI log would publish it a
    second time.
    """
    if (
        isinstance(secret, str)
        and len(secret) <= REFERENCE_ENV_MAX_LENGTH
        and REFERENCE_ENV_PATTERN.fullmatch(secret)
    ):
        return None
    return _REFERENCE_PROBLEM


def name_problem(kind: str, name: str) -> str | None:
    """Why ``name`` does not fit ``kind``, or None.

    ``header`` and ``query`` need the header or parameter name the publisher
    documents. ``basic`` always uses ``Authorization``, so a name there is a
    mistake worth refusing rather than silently ignoring.
    """
    if kind == "basic":
        return "fetch_auth.name is not used with kind basic; remove it" if name else None
    if kind == "header" and not HEADER_NAME_PATTERN.fullmatch(name):
        return "fetch_auth.name must be an HTTP header name, such as X-Api-Key"
    if kind == "query" and not QUERY_NAME_PATTERN.fullmatch(name):
        return "fetch_auth.name must be a query-parameter name, such as apikey"
    return None


class CredentialNotConfiguredError(RuntimeError):
    """A credentialed record cannot be fetched: the neutral unreachable state.

    Raised before any request. ``reason`` is the fixed phrase the run summary
    records; ``detail`` names the variable, never its value, for the operator.
    """

    reason = NOT_CONFIGURED

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"unreachable: {NOT_CONFIGURED} ({detail})")


@dataclass(frozen=True)
class ResolvedCredential:
    """A credential ready to inject. Its repr shows the kind and nothing else."""

    kind: str
    headers: dict[str, str] = field(default_factory=dict, repr=False)
    query: tuple[str, str] | None = field(default=None, repr=False)

    def apply_to_url(self, url: str) -> str:
        """``url`` with a ``query`` credential appended; unchanged otherwise.

        The configured query string is kept byte for byte and the credential
        parameter is appended after it, so the publisher sees exactly the URL
        on file plus one parameter.
        """
        if self.query is None:
            return url
        parts = urlsplit(url)
        extra = urlencode([self.query])
        query = f"{parts.query}&{extra}" if parts.query else extra
        return urlunsplit(parts._replace(query=query))


def resolve_credential(
    auth: FetchAuth, environ: Mapping[str, str] | None = None
) -> ResolvedCredential:
    """Read the referenced variable and build what the request needs.

    Every failure raises CredentialNotConfiguredError, and it does so before
    the caller has made any request. There is no partial credential and no
    keyless attempt.
    """
    env = os.environ if environ is None else environ
    if reference_problem(auth.secret) is not None:
        raise CredentialNotConfiguredError(
            f"fetch_auth.secret is not a {REFERENCE_ENV_PREFIX} variable name"
        )
    if auth.kind not in FETCH_AUTH_KINDS:
        raise CredentialNotConfiguredError(f"fetch_auth.kind {auth.kind!r} is not supported")
    problem = name_problem(auth.kind, auth.name)
    if problem is not None:
        raise CredentialNotConfiguredError(problem)
    value = env.get(auth.secret, "").strip()
    if not value:
        raise CredentialNotConfiguredError(f"{auth.secret} is not set")
    if any(ch in value for ch in "\r\n\x00"):
        raise CredentialNotConfiguredError(f"{auth.secret} contains a line break")
    if auth.kind == "header":
        return ResolvedCredential(kind="header", headers={auth.name: value})
    if auth.kind == "query":
        return ResolvedCredential(kind="query", query=(auth.name, value))
    if ":" not in value:
        raise CredentialNotConfiguredError(f"{auth.secret} must hold user:password for basic")
    token = base64.b64encode(value.encode("utf-8")).decode("ascii")
    return ResolvedCredential(kind="basic", headers={"Authorization": f"Basic {token}"})


def published_url(url: str) -> str:
    """The form of a credentialed fetch's URL that is safe to publish.

    Scheme, host, port, and path only. The query can carry the credential
    itself (``query`` kind) or a signature a publisher minted for our account
    after a redirect, and the user-info part is a credential by definition.
    """
    parts = urlsplit(url)
    host = parts.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def describe_failure(exc: BaseException) -> str:
    """Exception class and HTTP status, and nothing that quotes a URL."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    name = type(exc).__name__
    return f"{name} (HTTP {status})" if isinstance(status, int) else name
