"""Tests for the OpenTripPlanner routing-QA glue (pure)."""

from __future__ import annotations

from pathlib import Path

import pytest

from scorecard_pipeline.otp import (
    PlanResult,
    assess_routing,
    classify_graph_build,
    fetch_plan,
    parse_plan,
    plan_url,
    sample_od_pairs,
    sample_scheduled_stop_pairs,
)

# The real log from the 2026-08-10 batch: OTP 2.5.0 on a feed whose shapes.txt
# has no shape_id column.
MALFORMED_SHAPES_LOG = """\
15:07:26.904 ERROR [main]  (OTPMain.java:60) An uncaught error occurred inside OTP: \
io error: entityType=org.onebusaway.gtfs.model.ShapePoint path=shapes.txt lineNumber=2
org.onebusaway.csv_entities.exceptions.CsvEntityIOException: io error: \
entityType=org.onebusaway.gtfs.model.ShapePoint path=shapes.txt lineNumber=2
Caused by: org.onebusaway.csv_entities.exceptions.MissingRequiredFieldException: \
missing required field: shape_id
"""


def test_sample_od_pairs_spans_the_area_deterministically() -> None:
    points = [(-121.9, 38.5), (-121.5, 38.7), (-121.7, 38.6), (-121.8, 38.55)]
    pairs = sample_od_pairs(points, count=2)
    assert len(pairs) == 2
    # First pair joins the longitudinal extremes; deterministic across runs.
    assert pairs[0] == ((-121.9, 38.5), (-121.5, 38.7))
    assert sample_od_pairs(points, count=2) == pairs


def test_sample_od_pairs_needs_two_distinct_points() -> None:
    assert sample_od_pairs([(1.0, 2.0)]) == []
    assert sample_od_pairs([(1.0, 2.0), (1.0, 2.0)]) == []


def test_plan_url_uses_lat_lon_order_and_anchors_time() -> None:
    url = plan_url(
        "http://otp:8080/", (-121.7, 38.5), (-121.5, 38.7), date="2026-06-21", time="08:00"
    )
    assert "/otp/routers/default/plan?" in url
    assert "fromPlace=38.5%2C-121.7" in url  # lat,lon
    assert "toPlace=38.7%2C-121.5" in url
    assert "date=2026-06-21" in url and "time=08%3A00" in url


def test_plan_url_accepts_namespaced_stop_ids() -> None:
    url = plan_url(
        "http://otp:8080", "qa:origin", "qa:destination", date="2026-07-13", time="09:15"
    )
    assert "fromPlace=qa%3Aorigin" in url
    assert "toPlace=qa%3Adestination" in url


def test_sample_scheduled_stop_pairs_uses_active_trip_endpoints() -> None:
    trips = [
        {"trip_id": "inactive", "service_id": "weekend"},
        {"trip_id": "active", "service_id": "weekday"},
    ]
    stop_times = [
        {"trip_id": "active", "stop_id": "last", "stop_sequence": "2", "arrival_time": "09:30:00"},
        {
            "trip_id": "active",
            "stop_id": "first",
            "stop_sequence": "1",
            "departure_time": "09:00:00",
        },
        {
            "trip_id": "inactive",
            "stop_id": "ignored",
            "stop_sequence": "1",
            "departure_time": "08:00:00",
        },
    ]
    assert sample_scheduled_stop_pairs(trips, stop_times, {"weekday"}) == [
        ("qa:first", "qa:last", "09:00")
    ]


def test_parse_plan_finds_itineraries() -> None:
    result = parse_plan({"plan": {"itineraries": [{"duration": 1200}, {"duration": 1500}]}})
    assert result.routable is True
    assert result.itinerary_count == 2


def test_parse_plan_handles_no_itineraries_and_errors() -> None:
    assert parse_plan({"plan": {"itineraries": []}}).routable is False
    err = parse_plan({"error": {"id": 404, "msg": "PATH_NOT_FOUND"}})
    assert err.routable is False
    assert err.error == "PATH_NOT_FOUND"


def test_assess_routing_verdict() -> None:
    qa = assess_routing(
        [
            PlanResult(routable=True, itinerary_count=1),
            PlanResult(routable=False, itinerary_count=0, error="PATH_NOT_FOUND"),
            PlanResult(routable=True, itinerary_count=2),
        ]
    )
    assert qa.pairs_tested == 3
    assert qa.pairs_routable == 2
    assert qa.all_routable is False
    assert round(qa.routable_share, 2) == 0.67
    assert qa.failures == ["PATH_NOT_FOUND"]


def test_assess_routing_all_pass() -> None:
    qa = assess_routing([PlanResult(routable=True, itinerary_count=1)])
    assert qa.all_routable is True
    assert qa.failures == []


def test_classify_graph_build_reads_a_clean_build() -> None:
    result = classify_graph_build(0, "Graph saved to /var/opentripplanner/graph.obj")
    assert result.status == "built"
    assert result.built is True
    assert result.feed_unbuildable is False


def test_classify_graph_build_names_the_unparseable_table() -> None:
    result = classify_graph_build(255, MALFORMED_SHAPES_LOG)
    assert result.status == "feed-unbuildable"
    assert result.feed_unbuildable is True
    assert "shapes.txt" in result.detail
    assert "shape_id" in result.detail
    assert "line 2" in result.detail
    assert "\n" not in result.detail


def test_classify_graph_build_ignores_dockers_routine_pull_notice() -> None:
    """Docker's "Unable to find image ... locally" is normal, not a failure.

    It prints whenever the image is not already cached, so it is present in
    every clean-runner build. Matching it as an infrastructure marker classified
    a genuinely unparseable feed as a harness error and failed the run, which is
    what happened to rlv-riom on 2026-08-11 after the first fix shipped.
    """
    log = (
        "Unable to find image 'opentripplanner/opentripplanner@sha256:472509f' locally\n"
        + MALFORMED_SHAPES_LOG
    )
    result = classify_graph_build(255, log)
    assert result.status == "feed-unbuildable"
    assert result.feed_unbuildable
    assert "shapes.txt" in result.detail


def test_classify_graph_build_still_catches_a_genuinely_failed_pull() -> None:
    """The routine notice precedes a real pull failure; the failure still wins."""
    log = (
        "Unable to find image 'opentripplanner/opentripplanner@sha256:472509f' locally\n"
        "docker: Error response from daemon: pull access denied for opentripplanner.\n"
    )
    result = classify_graph_build(125, log)
    assert result.status == "harness-error"


def test_classify_graph_build_treats_a_bad_zip_as_the_feed() -> None:
    result = classify_graph_build(
        255, "java.util.zip.ZipException: zip END header not found\n\tat java.base/..."
    )
    assert result.feed_unbuildable is True


def test_classify_graph_build_keeps_infrastructure_failures_loud() -> None:
    pull = classify_graph_build(125, "docker: Error response from daemon: manifest unknown.")
    assert pull.status == "harness-error"
    # An unrecognized crash is the harness's until proven otherwise.
    silent = classify_graph_build(137, "the container went away")
    assert silent.status == "harness-error"
    assert "137" in silent.detail


def test_classify_graph_build_blames_memory_not_the_feed() -> None:
    # The stack sits in the GTFS reader, but the runner ran out of heap.
    result = classify_graph_build(
        1,
        "java.lang.OutOfMemoryError: Java heap space\n"
        "\tat org.onebusaway.gtfs.serialization.GtfsReader.read",
    )
    assert result.status == "harness-error"
    assert "outofmemoryerror" in result.detail


def test_otp_build_check_cli_keeps_an_unparseable_feed_green(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline import cli

    log_path = tmp_path / "build.log"
    log_path.write_text(MALFORMED_SHAPES_LOG)
    code = cli.main(["otp-build-check", "--log", str(log_path), "--exit-code", "255"])
    out = capsys.readouterr().out
    assert code == 0  # the workflow keeps going and records the feed
    assert "outcome=feed-unbuildable" in out
    assert "shapes.txt" in out
    # One line per key, so the CI step can append it straight to $GITHUB_OUTPUT.
    assert len([line for line in out.splitlines() if line]) == 2


def test_otp_build_check_cli_fails_on_a_broken_run(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline import cli

    log_path = tmp_path / "build.log"
    log_path.write_text("docker: Error response from daemon: manifest unknown.")
    assert cli.main(["otp-build-check", "--log", str(log_path), "--exit-code", "125"]) == 1
    assert "outcome=harness-error" in capsys.readouterr().out


def test_otp_build_check_cli_fails_when_no_log_was_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline import cli

    missing = str(tmp_path / "missing.log")
    assert cli.main(["otp-build-check", "--log", missing, "--exit-code", "1"]) == 1
    assert "outcome=harness-error" in capsys.readouterr().out


def test_fetch_plan_allows_only_explicit_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        content = b'{"plan":{"itineraries":[{}]}}'
        is_redirect = False
        is_permanent_redirect = False

        def raise_for_status(self) -> None:
            pass

        def close(self) -> None:
            pass

    monkeypatch.setattr("requests.get", lambda *_args, **_kwargs: Response())
    result = fetch_plan(
        "http://127.0.0.1:8080",
        (-121.7, 38.5),
        (-121.5, 38.7),
        date="2026-07-13",
        time="08:00",
        allow_loopback=True,
    )
    assert result.routable is True


def test_fetch_plan_loopback_opt_in_rejects_public_host() -> None:
    with pytest.raises(ValueError, match="requires a localhost"):
        fetch_plan(
            "https://example.com",
            (-121.7, 38.5),
            (-121.5, 38.7),
            date="2026-07-13",
            time="08:00",
            allow_loopback=True,
        )
