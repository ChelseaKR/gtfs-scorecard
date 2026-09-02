"""Minimal readers for the handful of GTFS files the rubric needs directly.

Mostly freshness-related files (feed_info, calendar, calendar_dates), plus a
few fields NTD readiness reads directly (agency_id, shapes/trips). Everything
rule-shaped stays in the canonical validator.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass


def _parse_gtfs_date(value: str) -> dt.date | None:
    value = value.strip()
    if len(value) != 8 or not value.isdigit():
        return None
    try:
        return dt.date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError:
        return None


# Cap a single uncompressed table to guard against zip bombs in untrusted feeds
# and to bound the memory a table costs when read whole into Python. Most GTFS
# tables are comfortably under this, but a national aggregate's stop_times.txt
# can exceed it (the Swiss national timetable's is 2.4 GiB). Readers that hit
# the cap raise TableTooLargeError so a caller can skip that one table rather
# than fail the whole score.
MAX_MEMBER_BYTES = 1024 * 1024 * 1024


class TableTooLargeError(ValueError):
    """A single GTFS table exceeds the reader's per-table memory cap.

    Subclasses ValueError so existing ``except ValueError`` callers keep
    catching it; a caller that specifically wants to skip an oversized table
    (rather than fail) can catch this narrower type.
    """


def _read_table(zf: zipfile.ZipFile, name: str) -> list[dict[str, str]]:
    try:
        info = zf.getinfo(name)
    except KeyError:
        return []
    if info.file_size > MAX_MEMBER_BYTES:
        raise TableTooLargeError(
            f"{name} is {info.file_size} bytes uncompressed, over the safety cap"
        )
    text = zf.read(name).decode("utf-8-sig", errors="replace")
    return list(csv.DictReader(io.StringIO(text)))


def read_tables(gtfs_zip_path: str, names: list[str]) -> dict[str, list[dict[str, str]]]:
    """Read several GTFS tables at once; missing files come back empty."""
    with zipfile.ZipFile(gtfs_zip_path) as zf:
        return {name: _read_table(zf, name) for name in names}


def iter_table_rows(
    gtfs_zip_path: str,
    name: str,
    *,
    max_member_bytes: int = MAX_MEMBER_BYTES,
) -> Iterator[dict[str, str]]:
    """Yield one GTFS table without materializing its decoded CSV.

    ``max_member_bytes`` lets a caller set a lower, task-specific analysis
    budget than the general whole-table reader. The size check happens before
    decompression, and a missing table yields no rows.
    """
    with zipfile.ZipFile(gtfs_zip_path) as zf:
        try:
            info = zf.getinfo(name)
        except KeyError:
            return
        if info.file_size > max_member_bytes:
            raise TableTooLargeError(
                f"{name} is {info.file_size} bytes uncompressed, over the "
                f"{max_member_bytes}-byte analysis cap"
            )
        with (
            zf.open(info) as raw,
            io.TextIOWrapper(
                raw,
                encoding="utf-8-sig",
                errors="replace",
                newline="",
            ) as text,
        ):
            yield from csv.DictReader(text)


def read_agency_ids(gtfs_zip_path: str) -> list[str]:
    """The distinct, non-blank agency_id values declared in agency.txt.

    Used by the RY2026 NTD presence and optional NTD-ID equality checks. The
    base GTFS Schedule specification permits agency_id to be omitted from a
    single-agency feed, but an NTD GTFS submission must provide a stable value
    for every represented reporter and crosswalk it on P-50. An empty list
    therefore means "no agency_id set"; the parser returns it normally and the
    NTD assessment supplies the finding. Order is preserved and duplicates are
    dropped so the values can be shown back to the agency."""
    with zipfile.ZipFile(gtfs_zip_path) as zf:
        rows = _read_table(zf, "agency.txt")
    seen: set[str] = set()
    ids: list[str] = []
    for row in rows:
        value = (row.get("agency_id") or "").strip()
        if value and value not in seen:
            seen.add(value)
            ids.append(value)
    return ids


@dataclass(frozen=True)
class ShapesCoverage:
    """How much of a feed's service is drawn from shapes.txt.

    Used by the shapes readiness check (ntd.assess_shapes_readiness). total_trips
    is the row count of trips.txt; trips_with_shape counts only rows whose
    shape_id is non-blank and actually present in shapes.txt (a dangling
    reference does not count as coverage)."""

    total_trips: int
    trips_with_shape: int


def read_shapes_coverage(gtfs_zip_path: str) -> ShapesCoverage:
    """Read trips.txt and shapes.txt and report shape coverage across trips."""
    tables = read_tables(gtfs_zip_path, ["shapes.txt", "trips.txt"])
    shape_ids = {
        row["shape_id"].strip() for row in tables["shapes.txt"] if row.get("shape_id", "").strip()
    }
    trips = tables["trips.txt"]
    with_shape = sum(1 for t in trips if (t.get("shape_id") or "").strip() in shape_ids)
    return ShapesCoverage(total_trips=len(trips), trips_with_shape=with_shape)


@dataclass(frozen=True)
class FeedDates:
    """Dates that drive the freshness category."""

    has_feed_info: bool
    feed_publisher_name: str | None
    feed_version: str | None
    feed_start_date: dt.date | None
    feed_end_date: dt.date | None
    # Last date any service runs, from calendar.txt end_date and
    # calendar_dates.txt added service (exception_type=1).
    last_service_date: dt.date | None
    # True when the calendars themselves encode distinct service periods
    # (e.g. academic terms separated by a break) AND the effective expiry
    # lands exactly on the end of one of those periods. Lets freshness frame
    # an undeclared seasonal feed's lapse as a planned transition. Detection
    # is conservative: a single continuous span never sets it.
    seasonal_boundary: bool = False
    # Whether the archive contained any table that can carry a service date at
    # all (feed_info.txt, calendar.txt, calendar_dates.txt). False means there
    # was nothing to read, which is different from having read the calendars and
    # found no end date -- that is a real finding about a real feed, and it still
    # scores. Defaults True so a hand-built FeedDates keeps scoring as before;
    # only read_feed_dates, which knows what the archive held, can set it False.
    has_date_tables: bool = True

    def effective_expiry(self) -> dt.date | None:
        """The date riders lose trip planning: the earlier of feed_info's
        stated end and the last scheduled service date."""
        candidates = [d for d in (self.feed_end_date, self.last_service_date) if d is not None]
        return min(candidates) if candidates else None


# A break of at least this many service-free days between calendar spans is
# read as a deliberate service-period boundary (a school break, an off-season)
# rather than sloppy calendar authoring. Two weeks clears ordinary long
# weekends and holiday closures encoded as short gaps.
SEASONAL_GAP_DAYS = 14


def _merge_spans(spans: list[tuple[dt.date, dt.date]]) -> list[tuple[dt.date, dt.date]]:
    """Merge overlapping or adjacent (consecutive-day) date spans."""
    merged: list[tuple[dt.date, dt.date]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + dt.timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _detect_seasonal_boundary(
    spans: list[tuple[dt.date, dt.date]], effective_expiry: dt.date | None
) -> bool:
    """True when the calendars encode distinct service periods and the feed's
    effective expiry is exactly the end of one of them.

    Conservative on purpose (a false positive would soften a genuinely lapsing
    feed): requires at least two merged spans separated by an internal gap of
    SEASONAL_GAP_DAYS or more service-free days, and an expiry that coincides
    with a span end. A single continuous span never triggers it."""
    if effective_expiry is None or len(spans) < 2:
        return False
    has_seasonal_gap = any(
        (spans[i + 1][0] - spans[i][1]).days - 1 >= SEASONAL_GAP_DAYS for i in range(len(spans) - 1)
    )
    return has_seasonal_gap and any(end == effective_expiry for _, end in spans)


def read_feed_dates(gtfs_zip_path: str) -> FeedDates:
    """Extract freshness-relevant dates from a static GTFS zip."""
    date_tables = ("feed_info.txt", "calendar.txt", "calendar_dates.txt")
    with zipfile.ZipFile(gtfs_zip_path) as zf:
        # Presence of the file, not of any row in it: an empty calendar.txt is a
        # feed that says it has no service, which is a measurable claim. An
        # archive carrying none of these tables said nothing at all.
        present = set(zf.namelist())
        has_date_tables = any(name in present for name in date_tables)
        feed_info_rows = _read_table(zf, "feed_info.txt")
        calendar_rows = _read_table(zf, "calendar.txt")
        calendar_date_rows = _read_table(zf, "calendar_dates.txt")

    info = feed_info_rows[0] if feed_info_rows else {}

    weekdays = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    service_dates: list[dt.date] = []
    # Active service spans, for seasonal-boundary detection. calendar_dates
    # added service counts as a one-day span. If any active calendar row lacks
    # a well-formed [start, end] the span picture is untrustworthy, so
    # detection is disabled rather than risk inventing a phantom gap.
    spans: list[tuple[dt.date, dt.date]] = []
    spans_reliable = True
    for row in calendar_rows:
        # A calendar with no active weekday runs on no day; its end_date is dead
        # service and must not push out the apparent expiry (which would mask a
        # stale feed). calendar_dates additions below are explicit and still count.
        if not any(row.get(day, "").strip() == "1" for day in weekdays):
            continue
        start = _parse_gtfs_date(row.get("start_date", ""))
        end = _parse_gtfs_date(row.get("end_date", ""))
        if end:
            service_dates.append(end)
        if start and end and start <= end:
            spans.append((start, end))
        else:
            spans_reliable = False
    for row in calendar_date_rows:
        if row.get("exception_type", "").strip() == "1":
            d = _parse_gtfs_date(row.get("date", ""))
            if d:
                service_dates.append(d)
                spans.append((d, d))

    feed_end_date = _parse_gtfs_date(info.get("feed_end_date", ""))
    last_service_date = max(service_dates) if service_dates else None
    expiry_candidates = [d for d in (feed_end_date, last_service_date) if d is not None]
    effective_expiry = min(expiry_candidates) if expiry_candidates else None

    return FeedDates(
        has_feed_info=bool(feed_info_rows),
        feed_publisher_name=info.get("feed_publisher_name") or None,
        feed_version=info.get("feed_version") or None,
        feed_start_date=_parse_gtfs_date(info.get("feed_start_date", "")),
        feed_end_date=feed_end_date,
        last_service_date=last_service_date,
        seasonal_boundary=(
            spans_reliable and _detect_seasonal_boundary(_merge_spans(spans), effective_expiry)
        ),
        has_date_tables=has_date_tables,
    )
