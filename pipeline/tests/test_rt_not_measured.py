"""A realtime sample we could not take must not be published as an outage.

``fetch_sample`` caught every exception into ``ok=False``. That value is not a
neutral flag: it becomes an ERROR finding on the agency page, a real deduction
from the realtime score, and a "down" reading in the longitudinal uptime record
that ``/realtime/`` publishes. So a refusal by our own SSRF guard, or any
unexpected exception inside our own fetcher, was published as "your feed is
down" over an agency's name.

The distinction restored here is the one PR #355 restored for validator
reports: a failure that is evidence about the agency stays a failure, and a
failure that is only evidence about us becomes not-measured, drops out of the
score, and renormalizes.
"""

from __future__ import annotations

import pytest
import requests
from google.protobuf.message import DecodeError
from google.transit import gtfs_realtime_pb2

from scorecard_pipeline import rt
from scorecard_pipeline.net import UnresolvableHostError, UnsafeURLError
from scorecard_pipeline.rt import RtSample, RtWindow, fetch_sample, realtime
from scorecard_pipeline.rt_health import observe, summarize

NOW = 1_770_000_000

URL = "https://feed.example.gov/tu.pb"


def _sample(kind: str, *, ok: bool = True, measured: bool = True, lag: int = 5) -> RtSample:
    return RtSample(
        kind=kind,
        fetched_at=NOW,
        ok=ok,
        measured=measured,
        header_timestamp=NOW - lag if ok else None,
        error=None if ok else "boom",
    )


def _raise(exc: BaseException):  # type: ignore[no-untyped-def]
    def _fn(*_a: object, **_k: object) -> bytes:
        raise exc

    return _fn


# --------------------------------------------------------------- the boundary


@pytest.mark.parametrize(
    ("label", "exc"),
    [
        ("our SSRF guard refused a private address", UnsafeURLError("resolves to 10.0.0.1")),
        ("our size cap refused the response", UnsafeURLError("response exceeded the cap")),
        ("our own code raised something unexpected", AttributeError("fetcher bug")),
    ],
)
def test_a_failure_of_ours_is_not_measured_rather_than_an_outage(
    monkeypatch: pytest.MonkeyPatch, label: str, exc: BaseException
) -> None:
    monkeypatch.setattr(rt, "safe_get", _raise(exc))
    s = fetch_sample("trip_updates", URL)
    assert s.ok is False, label
    assert s.measured is False, label


@pytest.mark.parametrize(
    ("label", "exc"),
    [
        ("the host refused the connection", requests.exceptions.ConnectionError("refused")),
        ("the host timed out", requests.exceptions.ReadTimeout("timed out")),
        ("the host has no DNS answer", UnresolvableHostError("cannot resolve host")),
    ],
)
def test_an_endpoint_failure_is_still_a_measured_outage(
    monkeypatch: pytest.MonkeyPatch, label: str, exc: BaseException
) -> None:
    monkeypatch.setattr(rt, "safe_get", _raise(exc))
    s = fetch_sample("trip_updates", URL)
    assert s.ok is False, label
    assert s.measured is True, label


def test_a_body_that_is_not_a_protobuf_is_still_a_measured_outage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The endpoint answered; what it served is not GTFS-Realtime. That is theirs.

    Real bytes, decoded by the real parser: an HTML error page served with a 200,
    the commonest way a realtime endpoint lies about being up.
    """
    page = b"<!doctype html><html><body>404 Not Found</body></html>"
    with pytest.raises(DecodeError):
        gtfs_realtime_pb2.FeedMessage().ParseFromString(page)
    monkeypatch.setattr(rt, "safe_get", lambda *_a, **_k: page)
    s = fetch_sample("trip_updates", URL)
    assert s.ok is False
    assert s.measured is True


def test_a_good_sample_is_measured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rt, "safe_get", lambda *_a, **_k: b"")
    s = fetch_sample("service_alerts", URL)
    assert s.ok is True
    assert s.measured is True


# --------------------------------------------------------------- the window


def test_an_unmeasured_sample_makes_the_kind_neither_up_nor_down() -> None:
    window = RtWindow(samples=[_sample("trip_updates", ok=False, measured=False)])
    assert window.kind_ok("trip_updates") is False
    assert window.kind_measured("trip_updates") is False


def test_a_measured_sample_beside_an_unmeasured_one_still_decides_the_kind() -> None:
    window = RtWindow(
        samples=[
            _sample("trip_updates", ok=False, measured=False),
            _sample("trip_updates"),
        ]
    )
    assert window.kind_measured("trip_updates") is True
    assert window.kind_ok("trip_updates") is True


# --------------------------------------------------------------- the score


def test_an_unfetchable_kind_drops_out_instead_of_deducting() -> None:
    """One of two feeds unmeasurable: the other one carries reachability alone."""
    window = RtWindow(
        samples=[
            _sample("trip_updates"),
            _sample("vehicle_positions", ok=False, measured=False),
        ]
    )
    result = realtime(window, None, configured_kinds={"trip_updates", "vehicle_positions"})
    assert result is not None
    codes = {f.code for f in result.findings}
    assert "scorecard_rt_vehicle_positions_unreachable" not in codes
    assert not any(f.severity == "ERROR" for f in result.findings)
    assert result.details["kinds_reachable"] == 1
    assert result.details["kinds_not_measured"] == ["vehicle_positions"]
    # Reachability and freshness both full over the one feed we could check.
    assert result.score == pytest.approx(100.0)


def test_the_page_says_which_feed_could_not_be_checked() -> None:
    window = RtWindow(
        samples=[
            _sample("trip_updates"),
            _sample("vehicle_positions", ok=False, measured=False),
        ]
    )
    result = realtime(window, None, configured_kinds={"trip_updates", "vehicle_positions"})
    assert result is not None
    notes = [f for f in result.findings if f.code == "scorecard_rt_vehicle_positions_not_checked"]
    assert len(notes) == 1
    assert notes[0].severity == "INFO"
    assert notes[0].deduction == 0.0
    assert "1 of 1" in result.summary


def test_a_window_we_could_not_measure_at_all_publishes_no_realtime_score() -> None:
    """Not a zero, not a hundred: the category is absent and renders not measured."""
    window = RtWindow(
        samples=[
            _sample("trip_updates", ok=False, measured=False),
            _sample("vehicle_positions", ok=False, measured=False),
        ]
    )
    assert realtime(window, None, configured_kinds={"trip_updates", "vehicle_positions"}) is None


def test_a_genuinely_unreachable_feed_still_scores_zero_reachability() -> None:
    """The narrowness test: a real outage must keep costing what it cost."""
    window = RtWindow(samples=[_sample("trip_updates", ok=False)])
    result = realtime(window, None, configured_kinds={"trip_updates"})
    assert result is not None
    codes = {f.code for f in result.findings}
    assert "scorecard_rt_trip_updates_unreachable" in codes
    assert result.score == pytest.approx(0.0)


# --------------------------------------------------------------- uptime record


def test_an_unmeasurable_run_records_no_observation() -> None:
    window = RtWindow(
        samples=[
            _sample("trip_updates", ok=False, measured=False),
            _sample("vehicle_positions", ok=False, measured=False),
        ]
    )
    assert observe(window, kinds_total=2, scheduled=None) is None


def test_a_real_outage_still_records_a_down_observation() -> None:
    window = RtWindow(samples=[_sample("trip_updates", ok=False)])
    obs = observe(window, kinds_total=1, scheduled=None)
    assert obs is not None
    assert obs.up is False
    assert summarize([obs]).uptime_pct == 0.0
