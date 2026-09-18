"""Cheap feed change and liveness detection.

A full score downloads and validates a feed; that is the expensive step and the
reason scoring only runs daily. But knowing whether a feed *changed* or *broke*
is much cheaper: a conditional GET (If-None-Match / If-Modified-Since) returns
304 with no body when the feed is unchanged, and only transfers the body on the
rare day the feed actually changes. A host returning 403/404/timeout is an
availability problem worth flagging on its own.

This module is the detector. It keeps a small per-feed record (validator
headers, body hash, last status) so a later run can tell unchanged from changed,
and recovered from still-broken. It deliberately does no validation and writes no
scorecard artifacts: its output is a signal — "these feeds changed, re-score
them; these are unreachable, alert on them" — that a cheaper-than-daily job can
act on between full scores.

The HTTP call is injected (`opener`) so the classification is unit-tested without
a network, and the live check runs only where outbound access is allowed (CI).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from http.client import HTTPException
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from .instance import BASE_URL

USER_AGENT = f"gtfs-scorecard liveness (+{BASE_URL})"

# Classifications returned per feed.
UNCHANGED = "unchanged"
CHANGED = "changed"
UNREACHABLE = "unreachable"


@dataclass
class LivenessRecord:
    """The last thing we saw at a feed URL, enough to detect the next change."""

    url: str
    etag: str | None = None
    last_modified: str | None = None
    sha256: str | None = None
    content_length: int | None = None
    status: int | None = None
    checked_at: str | None = None
    # When the body last actually changed, and how many checks in a row failed
    # (so an alert can wait for a sustained outage rather than one flaky request).
    changed_at: str | None = None
    consecutive_failures: int = 0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, d: dict[str, Any]) -> LivenessRecord:
        return cls(
            url=str(d.get("url", "")),
            etag=d.get("etag"),
            last_modified=d.get("last_modified"),
            sha256=d.get("sha256"),
            content_length=d.get("content_length"),
            status=d.get("status"),
            checked_at=d.get("checked_at"),
            changed_at=d.get("changed_at"),
            consecutive_failures=int(d.get("consecutive_failures") or 0),
        )


class _Response(Protocol):
    status: int

    def read(self) -> bytes: ...
    def __enter__(self) -> _Response: ...
    def __exit__(self, *exc: object) -> None: ...
    @property
    def headers(self) -> Any: ...


Opener = Callable[[Request, float], _Response]


def _default_opener(req: Request, timeout: float) -> _Response:
    return urlopen(req, timeout=timeout)  # type: ignore[no-any-return]  # noqa: S310


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def conditional_headers(prev: LivenessRecord | None) -> dict[str, str]:
    """Validators that ask the server "only send the body if it changed"."""
    headers = {"User-Agent": USER_AGENT}
    if prev and prev.etag:
        headers["If-None-Match"] = prev.etag
    if prev and prev.last_modified:
        headers["If-Modified-Since"] = prev.last_modified
    return headers


def evaluate_ok(
    url: str,
    prev: LivenessRecord | None,
    *,
    etag: str | None,
    last_modified: str | None,
    body: bytes,
    now: str | None = None,
) -> tuple[LivenessRecord, str]:
    """Classify a 200 response by hashing the body against the last seen hash.

    The body hash is authoritative: some hosts ignore conditional headers and
    always return 200, so a matching hash still means unchanged."""
    now = now or _now()
    sha = hashlib.sha256(body).hexdigest()
    changed = prev is None or prev.sha256 != sha
    record = LivenessRecord(
        url=url,
        etag=etag,
        last_modified=last_modified,
        sha256=sha,
        content_length=len(body),
        status=200,
        checked_at=now,
        changed_at=now if changed else (prev.changed_at if prev else now),
        consecutive_failures=0,
    )
    return record, (CHANGED if changed else UNCHANGED)


def check_feed(
    url: str,
    prev: LivenessRecord | None,
    *,
    opener: Opener = _default_opener,
    timeout: float = 30.0,
    now: str | None = None,
) -> tuple[LivenessRecord, str]:
    """Conditionally fetch a feed and classify it unchanged / changed / unreachable.

    Carries the last good validators and hash forward on an unreachable result so
    a transient outage does not erase what we knew about the feed."""
    now = now or _now()
    req = Request(url, headers=conditional_headers(prev))  # noqa: S310
    try:
        resp = opener(req, timeout)
    except HTTPError as exc:
        if exc.code == 304:
            return _carry_forward(url, prev, status=304, now=now, ok=True), UNCHANGED
        return _carry_forward(url, prev, status=exc.code, now=now, ok=False), UNREACHABLE
    except (URLError, TimeoutError, OSError):
        return _carry_forward(url, prev, status=None, now=now, ok=False), UNREACHABLE

    try:
        with resp:
            body = resp.read()
            headers = resp.headers
    except (URLError, TimeoutError, OSError, HTTPException):
        # A reset or truncated read mid-download (one agency's server dropping the
        # connection) must not crash the whole sweep: treat it like any other
        # unreachable result and carry the last good record forward.
        return _carry_forward(url, prev, status=None, now=now, ok=False), UNREACHABLE
    return evaluate_ok(
        url,
        prev,
        etag=headers.get("ETag"),
        last_modified=headers.get("Last-Modified"),
        body=body,
        now=now,
    )


def _carry_forward(
    url: str, prev: LivenessRecord | None, *, status: int | None, now: str, ok: bool
) -> LivenessRecord:
    base = prev or LivenessRecord(url=url)
    return LivenessRecord(
        url=url,
        etag=base.etag,
        last_modified=base.last_modified,
        sha256=base.sha256,
        content_length=base.content_length,
        status=status,
        checked_at=now,
        changed_at=base.changed_at,
        consecutive_failures=0 if ok else base.consecutive_failures + 1,
    )


def host_of(url: str) -> str:
    """The host name a request to ``url`` goes to: the unit politeness counts in.

    Lower-cased by urllib. A URL with no parseable host keys on itself, so it
    never shares a slot with another feed and is never grouped by accident.
    """
    try:
        host = urlsplit(url).hostname
    except ValueError:
        host = None
    return host or url


def check_feeds(
    targets: Sequence[tuple[str, str, LivenessRecord | None]],
    *,
    workers: int = 1,
    timeout: float = 30.0,
) -> dict[str, tuple[LivenessRecord, str]]:
    """Check many feeds, side by side across hosts and one at a time within one.

    ``targets`` is ``(agency_id, url, previous record)``. The feeds are grouped
    by host name and each group is walked in order by a single worker, so a
    host never has two requests from this sweep in flight at once: the load
    the serial sweep put on it, arriving no faster. What changes is that
    different hosts are checked at the same time. Measured 2026-09-18, the
    serial sweep took 44-45 minutes a cycle for about 1,500 due feeds across
    some 500 hosts, most of it spent waiting on one server at a time.

    The longest groups start first, since the largest host (505 feeds on
    2026-09-18) is the floor under the whole sweep's duration. ``workers=1``
    is a plain serial sweep.
    """
    if workers < 1:
        raise ValueError(f"workers must be at least 1, got {workers}")
    by_host: dict[str, list[tuple[str, str, LivenessRecord | None]]] = {}
    for target in targets:
        by_host.setdefault(host_of(target[1]), []).append(target)
    lanes = sorted(by_host.values(), key=len, reverse=True)

    def walk(
        lane: list[tuple[str, str, LivenessRecord | None]],
    ) -> list[tuple[str, tuple[LivenessRecord, str]]]:
        # Looked up at call time, so a test that replaces the module's
        # check_feed replaces it here too.
        return [(aid, check_feed(url, prev, timeout=timeout)) for aid, url, prev in lane]

    results: dict[str, tuple[LivenessRecord, str]] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="liveness") as pool:
        for lane_results in pool.map(walk, lanes):
            results.update(lane_results)
    return results


def requeue(
    state: dict[str, LivenessRecord],
    baseline: dict[str, LivenessRecord],
    agency_ids: Iterable[str],
) -> None:
    """Put back the pre-check record of feeds a cycle detected but never re-scored.

    The intraday refresh records what it saw at every checked URL before it
    re-scores the changed ones. A feed its rescore deferred to the time budget
    would otherwise carry this cycle's new hash forward, and its next check
    would read it as unchanged: the change would wait for the next daily run
    while the refresh's own warning said it would be picked up. Restoring the
    record it had before this cycle (or dropping it, when there was none)
    makes the next check classify the feed exactly as this one did.
    """
    for agency_id in agency_ids:
        previous = baseline.get(agency_id)
        if previous is None:
            state.pop(agency_id, None)
        else:
            state[agency_id] = previous


def recovered(prev: LivenessRecord | None, classification: str) -> bool:
    """True when a feed that had been failing is reachable again."""
    return bool(prev and prev.consecutive_failures > 0 and classification != UNREACHABLE)


def load_state(path: Path) -> dict[str, LivenessRecord]:
    try:
        raw = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return {}
    return {aid: LivenessRecord.from_json(rec) for aid, rec in raw.get("feeds", {}).items()}


def save_state(path: Path, state: dict[str, LivenessRecord]) -> None:
    payload = {
        "schema_version": "1.0",
        "feeds": {aid: rec.to_json() for aid, rec in sorted(state.items())},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)
