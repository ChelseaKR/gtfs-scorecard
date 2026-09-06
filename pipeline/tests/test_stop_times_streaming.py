"""stop_times.txt must not be materialized by the scoring path.

The Dutch national aggregate's `score` shard died for three weeks on a
stop_times.txt of 1,011,976,627 bytes -- 62 MB *under* the whole-table reader's
1 GiB cap. Read whole, those 17,099,889 rows cost about 750 bytes each as
Python dicts: roughly 13 GB on a 15.6 GiB runner. The cap could not see that,
because bytes on disk do not predict bytes in memory, and a bigger feed was
actually safer: every earlier export was *over* the cap, so the read was
skipped and the shard lived.

These tests hold the property that replaced the cap on that path: what the two
whole-table consumers of stop_times.txt take from it is a handful of sets keyed
by trip and by stop, so their cost is set by the number of distinct trips and
stops and not by the number of rows.
"""

from __future__ import annotations

import logging
import tracemalloc
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from scorecard_pipeline import gtfs
from scorecard_pipeline.ferry_profile import ferry_profile_from_zip
from scorecard_pipeline.routability import assess_routability

_FERRY_ROUTES = "route_id,route_type\nf,4\n"
_FERRY_TRIPS = "route_id,service_id,trip_id\nf,s,t1\nf,s,t2\n"
_STOPS = "stop_id,stop_name,location_type\nA,Alpha,0\nB,Beta,0\n"
_BUS_ROUTES = "route_id,route_type\nb,3\n"


def _stop_times(rows: int, *, trips: int = 1000, stops: int = 500) -> str:
    """A stop_times.txt of ``rows`` rows over a fixed number of trips and stops.

    The distinct-id counts are deliberately held constant so that growing the
    row count grows the table and nothing a streaming reader has to remember.
    """
    lines = ["trip_id,stop_id,stop_sequence"]
    lines += [f"t{i % trips},s{i % stops},{i}" for i in range(rows)]
    return "\n".join(lines) + "\n"


def _peak_bytes(work: Callable[[], object]) -> int:
    """Peak Python allocation while ``work`` runs, in bytes."""
    tracemalloc.start()
    try:
        work()
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def test_routability_memory_does_not_grow_with_stop_times_rows(tmp_path: Path) -> None:
    # Quadrupling the rows while holding the trips and stops fixed must not
    # meaningfully move the memory ceiling. Reading the table whole did move it
    # by the same factor of four, which is the failure this pins down.
    small, large = 50_000, 200_000
    peaks = []
    for count, rows in (("small", small), ("large", large)):
        path = tmp_path / f"{count}.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("trips.txt", "route_id,service_id,trip_id\nr,s,t0\n")
            zf.writestr("stops.txt", "stop_id,stop_name,location_type\ns0,Zero,0\n")
            zf.writestr("stop_times.txt", _stop_times(rows))
        peaks.append(_peak_bytes(lambda p=path: assess_routability(str(p))))  # type: ignore[misc]

    small_peak, large_peak = peaks
    # Four times the rows, at most 1.5x the memory. Materializing the table put
    # this ratio at roughly 4.0.
    assert large_peak < small_peak * 1.5, (
        f"{large} rows peaked at {large_peak} bytes against {small_peak} for {small}"
    )
    # And an absolute ceiling, so a future change cannot satisfy the ratio by
    # making both ends expensive. The 200,000-row table is ~2.6 MB on disk and
    # would be ~67 MB as dicts.
    assert large_peak < 8 * 1024 * 1024, f"{large} rows peaked at {large_peak} bytes"


def _cap_between(zip_path: Path, streamed: str, others: tuple[str, ...]) -> int:
    """A whole-table cap that only ``streamed`` is over.

    Returned rather than assumed, and the caller asserts the whole-table reader
    really does refuse the table at it: a size guard that quietly did not apply
    would leave these tests passing for the wrong reason.
    """
    with zipfile.ZipFile(zip_path) as zf:
        biggest_other = max(zf.getinfo(name).file_size for name in others)
        streamed_size = zf.getinfo(streamed).file_size
    assert biggest_other < streamed_size, "fixture does not separate the tables by size"
    return streamed_size - 1


def test_routability_measures_a_stop_times_over_the_whole_table_cap(
    make_gtfs_zip: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The cap that killed the shard is a whole-table cap. Streaming does not
    # consult it, so a stop_times.txt on the far side of it is measured, not
    # skipped -- there is no byte at which the check silently stops running.
    stop_times = "trip_id,stop_id,stop_sequence\n"
    stop_times += "".join(f"t1,{'AB'[i % 2]},{i + 1}\n" for i in range(30))
    stop_times += "t2,A,1\n"
    path = make_gtfs_zip(
        {
            "trips.txt": "route_id,service_id,trip_id\nr,s,t1\nr,s,t2\n",
            "stops.txt": _STOPS,
            "stop_times.txt": stop_times,
        }
    )
    cap = _cap_between(path, "stop_times.txt", ("trips.txt", "stops.txt"))
    monkeypatch.setattr(gtfs, "MAX_MEMBER_BYTES", cap)
    with zipfile.ZipFile(path) as zf, pytest.raises(gtfs.TableTooLargeError):
        gtfs._read_table(zf, "stop_times.txt")

    profile = assess_routability(str(path))

    assert profile.trips_total == 2
    assert profile.single_stop_trips == 1  # t2 has one stop; t1 has thirty
    assert profile.orphan_stops == 0


def test_ferry_profile_measures_a_stop_times_over_the_whole_table_cap(
    make_gtfs_zip: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stop_times = "trip_id,stop_id,stop_sequence\n"
    stop_times += "".join(f"t{1 + i % 2},{'AB'[i % 2]},{i + 1}\n" for i in range(30))
    path = make_gtfs_zip(
        {
            "routes.txt": _FERRY_ROUTES,
            "trips.txt": _FERRY_TRIPS,
            "stops.txt": _STOPS,
            "stop_times.txt": stop_times,
        }
    )
    cap = _cap_between(path, "stop_times.txt", ("routes.txt", "trips.txt", "stops.txt"))
    monkeypatch.setattr(gtfs, "MAX_MEMBER_BYTES", cap)
    with zipfile.ZipFile(path) as zf, pytest.raises(gtfs.TableTooLargeError):
        gtfs._read_table(zf, "stop_times.txt")

    profile = ferry_profile_from_zip(str(path))

    assert profile is not None
    assert profile["terminal_hierarchy"]["boarding_location_count"] == 2


def test_ferry_profile_never_opens_stop_times_without_a_ferry_route(
    make_gtfs_zip: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # stop_times.txt is the largest table in a feed and most feeds have no
    # ferry. The reader is handed over lazily so those feeds never pay for it.
    read = False

    def spy(path: str, name: str, **kwargs: object) -> Iterator[dict[str, str]]:
        nonlocal read
        read = True
        yield {"trip_id": "t1", "stop_id": "A"}

    monkeypatch.setattr("scorecard_pipeline.ferry_profile.iter_table_rows", spy)
    path = make_gtfs_zip(
        {
            "routes.txt": _BUS_ROUTES,
            "trips.txt": "route_id,service_id,trip_id\nb,s,t1\n",
            "stops.txt": _STOPS,
            "stop_times.txt": "trip_id,stop_id,stop_sequence\nt1,A,1\nt1,B,2\n",
        }
    )

    assert ferry_profile_from_zip(str(path)) is None
    assert read is False


def test_a_big_table_logs_its_size_when_streamed(
    make_gtfs_zip: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    # The diagnostic the outage needed: which table, how big, and what was done
    # with it, in the ordinary run's own log.
    text = "trip_id,stop_id,stop_sequence\nt1,A,1\nt1,B,2\n"
    path = make_gtfs_zip(
        {
            "trips.txt": "route_id,service_id,trip_id\nr,s,t1\n",
            "stops.txt": _STOPS,
            "stop_times.txt": text,
        }
    )
    monkeypatch.setattr(gtfs, "LOG_MEMBER_BYTES", 1)

    with caplog.at_level(logging.INFO, logger="scorecard_pipeline.gtfs"):
        assess_routability(str(path))

    streamed = [r for r in caplog.records if "streaming" in r.getMessage()]
    assert [r.getMessage() for r in streamed] == [
        f"stop_times.txt: {len(text)} bytes uncompressed, streaming"
    ]


def test_a_skipped_table_logs_its_size(
    make_gtfs_zip: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    trips = "route_id,service_id,trip_id\nr,s,t1\n"
    path = make_gtfs_zip({"trips.txt": trips, "stops.txt": _STOPS, "stop_times.txt": "trip_id\n"})
    monkeypatch.setattr(gtfs, "MAX_MEMBER_BYTES", 1)

    with (
        caplog.at_level(logging.WARNING, logger="scorecard_pipeline.gtfs"),
        pytest.raises(gtfs.TableTooLargeError),
    ):
        assess_routability(str(path))

    assert any(
        f"trips.txt: {len(trips)} bytes uncompressed, not read" in r.getMessage()
        for r in caplog.records
    )
