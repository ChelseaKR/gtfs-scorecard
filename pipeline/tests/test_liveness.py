"""Tests for cheap feed change/liveness detection (injected opener, no network)."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request

import pytest

from scorecard_pipeline import cli
from scorecard_pipeline import liveness as liveness_module
from scorecard_pipeline.liveness import (
    CHANGED,
    UNCHANGED,
    UNREACHABLE,
    LivenessRecord,
    check_feed,
    check_feeds,
    conditional_headers,
    host_of,
    load_state,
    recovered,
    requeue,
    save_state,
)

URL = "https://feeds.example.org/gtfs.zip"


class _FakeResp:
    def __init__(self, body: bytes, headers: dict[str, str]) -> None:
        self.status = 200
        self._body = body
        self.headers = headers

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResp:
        return self

    def __exit__(self, *exc: object) -> None:
        return None


def _opener_returning(
    body: bytes, headers: dict[str, str] | None = None
) -> Callable[[Request, float], _FakeResp]:
    def opener(req: Request, timeout: float) -> _FakeResp:
        return _FakeResp(body, headers or {})

    return opener


def _opener_raising(exc: Exception) -> Callable[[Request, float], _FakeResp]:
    def opener(req: Request, timeout: float) -> _FakeResp:
        raise exc

    return opener


def _opener_read_raises(exc: Exception) -> Callable[[Request, float], _FakeResp]:
    """Opener that connects fine but whose body read fails mid-download."""

    class _BrokenResp(_FakeResp):
        def read(self) -> bytes:
            raise exc

    def opener(req: Request, timeout: float) -> _FakeResp:
        return _BrokenResp(b"", {})

    return opener


def _rec(body: bytes, **kw: object) -> LivenessRecord:
    return LivenessRecord(url=URL, sha256=hashlib.sha256(body).hexdigest(), **kw)  # type: ignore[arg-type]


def test_conditional_headers_use_stored_validators() -> None:
    prev = LivenessRecord(url=URL, etag='"abc"', last_modified="Wed, 21 Oct 2026 07:28:00 GMT")
    h = conditional_headers(prev)
    assert h["If-None-Match"] == '"abc"'
    assert h["If-Modified-Since"] == "Wed, 21 Oct 2026 07:28:00 GMT"
    assert "User-Agent" in h
    # No prior record: only the user agent, no conditional validators.
    assert set(conditional_headers(None)) == {"User-Agent"}


def test_304_is_unchanged_and_clears_failures() -> None:
    prev = _rec(b"old", consecutive_failures=2)
    err = HTTPError(URL, 304, "Not Modified", {}, None)  # type: ignore[arg-type]
    rec, cls = check_feed(URL, prev, opener=_opener_raising(err), now="2026-06-20T00:00:00+00:00")
    assert cls == UNCHANGED
    assert rec.sha256 == prev.sha256  # carried forward
    assert rec.status == 304
    assert rec.consecutive_failures == 0


def test_200_with_new_body_is_changed() -> None:
    prev = _rec(b"old")
    opener = _opener_returning(b"new feed bytes", {"ETag": '"v2"'})
    rec, cls = check_feed(URL, prev, opener=opener, now="2026-06-20T00:00:00+00:00")
    assert cls == CHANGED
    assert rec.sha256 == hashlib.sha256(b"new feed bytes").hexdigest()
    assert rec.etag == '"v2"'
    assert rec.changed_at == "2026-06-20T00:00:00+00:00"


def test_200_with_same_body_is_unchanged_even_without_304() -> None:
    # A host that ignores conditional headers and re-sends the same bytes is still
    # unchanged; the body hash is authoritative.
    body = b"identical feed"
    prev = _rec(body, changed_at="2026-06-01T00:00:00+00:00")
    rec, cls = check_feed(
        URL, prev, opener=_opener_returning(body), now="2026-06-20T00:00:00+00:00"
    )
    assert cls == UNCHANGED
    assert rec.changed_at == "2026-06-01T00:00:00+00:00"  # unchanged keeps the old change time


def test_first_check_with_no_prior_record_is_changed() -> None:
    rec, cls = check_feed(URL, None, opener=_opener_returning(b"first"))
    assert cls == CHANGED
    assert rec.sha256 == hashlib.sha256(b"first").hexdigest()


def test_http_error_is_unreachable_and_counts_failures() -> None:
    prev = _rec(b"old", consecutive_failures=1)
    err = HTTPError(URL, 403, "Forbidden", {}, None)  # type: ignore[arg-type]
    rec, cls = check_feed(URL, prev, opener=_opener_raising(err))
    assert cls == UNREACHABLE
    assert rec.status == 403
    assert rec.consecutive_failures == 2
    assert rec.sha256 == prev.sha256  # last known hash preserved


def test_url_error_is_unreachable() -> None:
    rec, cls = check_feed(URL, None, opener=_opener_raising(URLError("dns")))
    assert cls == UNREACHABLE
    assert rec.consecutive_failures == 1
    assert rec.status is None


def test_connection_reset_during_read_is_unreachable() -> None:
    # The connection opens but the server drops it mid-download (the real failure
    # the daily sweep hit). It must classify unreachable, not crash the sweep.
    prev = _rec(b"old", consecutive_failures=0)
    rec, cls = check_feed(
        URL,
        prev,
        opener=_opener_read_raises(ConnectionResetError(104, "reset by peer")),
        now="2026-06-20T00:00:00+00:00",
    )
    assert cls == UNREACHABLE
    assert rec.consecutive_failures == 1
    assert rec.sha256 == prev.sha256  # last known hash preserved


def test_recovered_flags_a_previously_failing_feed() -> None:
    failing = _rec(b"x", consecutive_failures=3)
    assert recovered(failing, UNCHANGED) is True
    assert recovered(failing, UNREACHABLE) is False
    assert recovered(None, CHANGED) is False
    assert recovered(_rec(b"x", consecutive_failures=0), CHANGED) is False


def test_state_round_trips_through_disk(tmp_path) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / "liveness.json"
    state = {
        "demo": _rec(b"a", etag='"e"', status=200, checked_at="2026-06-20T00:00:00+00:00"),
        "other": LivenessRecord(url="https://x/y.zip", status=403, consecutive_failures=4),
    }
    save_state(path, state)
    back = load_state(path)
    assert back["demo"].sha256 == state["demo"].sha256
    assert back["demo"].etag == '"e"'
    assert back["other"].consecutive_failures == 4
    # Missing file degrades to empty, not an error.
    assert load_state(tmp_path / "nope.json") == {}


# ---------------------------------------------------------------------------
# The sweep: side by side across hosts, one at a time within one


def test_host_of_is_the_lower_cased_host_name() -> None:
    assert host_of("https://API.GTFS-Data.jp/v2/feed.zip") == "api.gtfs-data.jp"
    assert host_of("http://user@host.example:8080/f.zip") == "host.example"


def test_a_url_without_a_host_keys_on_itself() -> None:
    """Never grouped with another feed by accident, so never serialized with one either."""
    assert host_of("file:///tmp/feed.zip") == "file:///tmp/feed.zip"
    assert host_of("http://[::1/broken") == "http://[::1/broken"


class _InstrumentedCheck:
    """A check_feed stand-in that records how many requests each host had in flight."""

    def __init__(self, seconds: float = 0.02) -> None:
        self.seconds = seconds
        self.lock = threading.Lock()
        self.live: Counter[str] = Counter()
        self.peak_per_host: Counter[str] = Counter()
        self.peak_overall = 0

    def __call__(
        self, url: str, prev: LivenessRecord | None, *, timeout: float
    ) -> tuple[LivenessRecord, str]:
        host = host_of(url)
        with self.lock:
            self.live[host] += 1
            self.peak_per_host[host] = max(self.peak_per_host[host], self.live[host])
            self.peak_overall = max(self.peak_overall, sum(self.live.values()))
        time.sleep(self.seconds)
        with self.lock:
            self.live[host] -= 1
        return LivenessRecord(url=url, sha256=url, status=200), CHANGED


def _targets(hosts: int, per_host: int) -> list[tuple[str, str, LivenessRecord | None]]:
    return [
        (f"h{h}-f{f}", f"https://host-{h}.example/feed-{f}.zip", None)
        for h in range(hosts)
        for f in range(per_host)
    ]


def test_no_host_ever_has_two_checks_in_flight(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _InstrumentedCheck()
    monkeypatch.setattr(liveness_module, "check_feed", fake)

    results = check_feeds(_targets(hosts=6, per_host=4), workers=16, timeout=5.0)

    assert len(results) == 24
    assert max(fake.peak_per_host.values()) == 1
    # Different hosts really were checked at the same time.
    assert fake.peak_overall > 1


def test_the_parallel_sweep_classifies_exactly_as_the_serial_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bodies = {f"https://host-{n % 3}.example/{n}.zip": f"body-{n}".encode() for n in range(9)}
    prev = {
        url: LivenessRecord(url=url, sha256=hashlib.sha256(b"body-0").hexdigest()) for url in bodies
    }
    targets = [(f"feed-{n}", url, prev[url]) for n, url in enumerate(bodies)]

    def opener(req: Request, timeout: float) -> _FakeResp:
        return _FakeResp(bodies[req.full_url], {})

    def via_fake(
        url: str, prev: LivenessRecord | None, *, timeout: float
    ) -> tuple[LivenessRecord, str]:
        return check_feed(url, prev, opener=opener, timeout=timeout, now="2026-09-18T00:00Z")

    monkeypatch.setattr(liveness_module, "check_feed", via_fake)

    def classify(workers: int) -> dict[str, tuple[LivenessRecord, str]]:
        return check_feeds(targets, workers=workers)

    serial = classify(1)
    assert classify(8) == serial
    assert serial["feed-0"][1] == UNCHANGED
    assert {cls for _, cls in serial.values()} == {UNCHANGED, CHANGED}


def test_the_busiest_host_starts_first(monkeypatch: pytest.MonkeyPatch) -> None:
    order: list[str] = []

    def record(
        url: str, prev: LivenessRecord | None, *, timeout: float
    ) -> tuple[LivenessRecord, str]:
        order.append(host_of(url))
        return LivenessRecord(url=url), UNCHANGED

    monkeypatch.setattr(liveness_module, "check_feed", record)
    targets = [
        ("a", "https://quiet.example/a.zip", None),
        ("b", "https://busy.example/b.zip", None),
        ("c", "https://busy.example/c.zip", None),
    ]
    check_feeds(targets, workers=1)

    assert order == ["busy.example", "busy.example", "quiet.example"]


def test_sweep_workers_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        check_feeds([], workers=0)


def test_requeue_puts_back_the_record_from_before_the_sweep() -> None:
    before = {"seen": _rec(b"old", changed_at="2026-09-01T00:00:00+00:00")}
    state = {
        "seen": _rec(b"new", changed_at="2026-09-18T00:00:00+00:00"),
        "first": _rec(b"first"),
        "scored": _rec(b"scored"),
    }
    requeue(state, before, ["seen", "first"])

    # The exact old record, so the next check reads the change and dates it truly.
    assert state["seen"] == before["seen"]
    # No record before this sweep: none after, so the next check sees a new feed.
    assert "first" not in state
    # A feed that was re-scored keeps what this sweep recorded.
    assert state["scored"].sha256 == hashlib.sha256(b"scored").hexdigest()


def test_the_sweep_command_checks_side_by_side_and_writes_a_baseline(
    isolated_repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_repo_root.mkdir(parents=True)
    (isolated_repo_root / "agencies.yaml").write_text(
        "agencies:\n"
        + "".join(
            f"  - id: feed-{n}\n    name: Feed {n}\n"
            f"    static_gtfs_url: https://host-{n % 2}.example/{n}.zip\n"
            for n in range(4)
        )
    )
    before = {"feed-0": LivenessRecord(url="https://host-0.example/0.zip", sha256="old")}
    save_state(isolated_repo_root / "data" / "liveness.json", before)
    fake = _InstrumentedCheck(seconds=0.01)
    monkeypatch.setattr(liveness_module, "check_feed", fake)
    baseline = tmp_path / "before.json"
    changed = tmp_path / "changed.txt"

    assert (
        cli.main(
            [
                "liveness",
                "--apply",
                "--workers",
                "4",
                "--baseline-out",
                str(baseline),
                "--changed-out",
                str(changed),
            ]
        )
        == 0
    )

    assert max(fake.peak_per_host.values()) == 1
    assert load_state(baseline) == before
    assert changed.read_text().splitlines() == [f"feed-{n}" for n in range(4)]
    after = load_state(isolated_repo_root / "data" / "liveness.json")
    assert after["feed-0"].sha256 == "https://host-0.example/0.zip"
