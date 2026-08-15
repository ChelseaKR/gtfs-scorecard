#!/usr/bin/env python3
"""Re-read each feed's own publisher declaration into a dated snapshot.

Writes ``data/feed-publishers.json``: for every registry feed that can be read,
the ``feed_publisher_name`` and ``feed_publisher_url`` its own ``feed_info.txt``
declares, alongside the URL those bytes came from.

Why this file exists: the host serving a GTFS zip is not the same fact as the
tool that produced it. Several services host feeds built elsewhere, so reading a
producing tool off the host alone attributes a feed to a company that did not
build it. The feed's own declaration is the publisher's statement about itself,
so ``tool_profiles`` reads this snapshot rather than guessing from the host. See
``docs/decisions/0045-producer-attribution-from-the-feed.md``.

Like the Caltrans directory refresh, this reaches the network and no test or
daily build runs it. The committed snapshot is what everything else reads, so
attribution stays reproducible offline.

Polite by construction. Where a host supports HTTP range requests the script
reads only the zip's central directory and the one member it needs, about 30 kB
instead of a whole feed; hosts that do not are downloaded once, capped, and
discarded. Requests are spaced and one host is never asked for two feeds at once.

    uv run --project pipeline python pipeline/scripts/fetch_feed_publishers.py
    uv run --project pipeline python pipeline/scripts/fetch_feed_publishers.py --limit 20
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import threading
import time
import urllib.request
import zipfile
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "pipeline" / "src"))

from scorecard_pipeline.agencies import load_agencies  # noqa: E402
from scorecard_pipeline.config import AGENCIES, utc_today  # noqa: E402
from scorecard_pipeline.fetch import FEED_HEADERS  # noqa: E402

OUT = REPO_ROOT / "data" / "feed-publishers.json"
SCHEMA_VERSION = "1.0"
# The same headers the daily fetch sends, so this reads the feeds the pipeline
# reads. fetch.py explains why they are a browser's: several hosts answer a
# non-browser User-Agent with 403 and would leave those feeds without evidence.
HEADERS = dict(FEED_HEADERS)
# A feed served without a content length, or by a host that ignores Range, is
# downloaded whole. Anything past this is skipped rather than pulled down: the
# declaration is three fields, and no national feed is worth gigabytes to read.
MAX_WHOLE_DOWNLOAD_BYTES = 80 * 1024 * 1024
REQUEST_SPACING_SECONDS = 0.4
# Distinct hosts read at once. Within a host the reads stay strictly
# sequential and spaced, so this widens the sweep without leaning on anyone.
HOST_WORKERS = 12


class _HttpRangeFile(io.RawIOBase):
    """A seekable read-only file over HTTP range requests.

    ``zipfile`` seeks to the end for the central directory and then to the one
    member it is asked for, so a handful of small ranges replace the download.
    """

    def __init__(self, url: str, size: int) -> None:
        self.url = url
        self.size = size
        self.pos = 0
        self.requests = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        else:
            self.pos = self.size + offset
        return self.pos

    def tell(self) -> int:
        return self.pos

    def readinto(self, buf: Any) -> int:  # type: ignore[override]
        want = len(buf)
        if want == 0 or self.pos >= self.size:
            return 0
        end = min(self.pos + want, self.size) - 1
        req = urllib.request.Request(  # noqa: S310
            self.url, headers={**HEADERS, "Range": f"bytes={self.pos}-{end}"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            if resp.status != 206:
                raise OSError("range request not honored")
            data = resp.read()
        self.requests += 1
        buf[: len(data)] = data
        self.pos += len(data)
        return len(data)


def _feed_info_row(zf: zipfile.ZipFile) -> dict[str, str]:
    names = [n for n in zf.namelist() if n.rsplit("/", 1)[-1] == "feed_info.txt"]
    if not names:
        return {}
    text = zf.read(names[0]).decode("utf-8-sig", "replace")
    rows = list(csv.DictReader(io.StringIO(text)))
    return rows[0] if rows else {}


def _head(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers=HEADERS, method="HEAD")  # noqa: S310
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
        return int(resp.headers.get("Content-Length") or 0), resp.geturl()


def _read_declaration(url: str) -> dict[str, str]:
    """The publisher fields feed_info.txt declares, read as cheaply as the host allows."""
    try:
        size, final_url = _head(url)
    except Exception:
        size, final_url = 0, url
    if size and size <= MAX_WHOLE_DOWNLOAD_BYTES:
        try:
            handle = _HttpRangeFile(final_url, size)
            with zipfile.ZipFile(io.BufferedReader(handle, buffer_size=32 * 1024)) as zf:
                return _feed_info_row(zf)
        except Exception:  # noqa: S110 - a host that ignores Range falls through
            pass
    if size > MAX_WHOLE_DOWNLOAD_BYTES:
        raise RuntimeError(f"feed is {size} bytes; too large to read whole")
    req = urllib.request.Request(final_url, headers=HEADERS)  # noqa: S310
    with urllib.request.urlopen(req, timeout=90) as resp:  # noqa: S310
        body = resp.read(MAX_WHOLE_DOWNLOAD_BYTES + 1)
    if len(body) > MAX_WHOLE_DOWNLOAD_BYTES:
        raise RuntimeError("feed exceeds the whole-download cap")
    with zipfile.ZipFile(io.BytesIO(body)) as zf:
        return _feed_info_row(zf)


def _write(feeds: dict[str, Any]) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "retrieved_on": utc_today().isoformat(),
        "note": (
            "Each feed's own feed_info.txt publisher declaration, read once from the feed "
            "URL recorded with it. Producer attribution reads this instead of inferring a "
            "tool from the host that serves the zip. Rebuild with "
            "pipeline/scripts/fetch_feed_publishers.py."
        ),
        "feed_count": len(feeds),
        "feeds": dict(sorted(feeds.items())),
    }
    OUT.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")


def _sweep(agencies: list[Any], existing: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Read every feed's declaration, grouped by host.

    Each host is read strictly in sequence with spacing between requests, so no
    host ever sees two requests at once. Hosts are read concurrently because
    they are unrelated servers; the politeness that matters is per host.
    """
    by_host: dict[str, list[Any]] = defaultdict(list)
    for agency in agencies:
        by_host[urlparse(agency.static_gtfs_url).netloc.lower()].append(agency)

    feeds: dict[str, Any] = {}
    counters = {"read": 0, "declared": 0, "failed": 0}
    lock = threading.Lock()

    def read_host(host_agencies: list[Any]) -> None:
        for position, agency in enumerate(host_agencies):
            if position:
                time.sleep(REQUEST_SPACING_SECONDS)
            try:
                row = _read_declaration(agency.static_gtfs_url)
            except Exception as exc:  # unreachable, not a zip, too large: no evidence
                with lock:
                    counters["failed"] += 1
                    prior = existing.get(agency.id)
                    if prior and prior.get("url") == agency.static_gtfs_url:
                        feeds[agency.id] = prior
                print(
                    f"  skip {agency.id}: {type(exc).__name__}: {str(exc)[:70]}",
                    file=sys.stderr,
                    flush=True,
                )
                continue
            name = (row.get("feed_publisher_name") or "").strip()
            publisher_url = (row.get("feed_publisher_url") or "").strip()
            with lock:
                counters["read"] += 1
                if name or publisher_url:
                    counters["declared"] += 1
                feeds[agency.id] = {
                    "url": agency.static_gtfs_url,
                    "publisher_name": name,
                    "publisher_url": publisher_url,
                }

    with ThreadPoolExecutor(max_workers=HOST_WORKERS) as pool:
        futures = [pool.submit(read_host, group) for group in by_host.values()]
        for done, _ in enumerate(as_completed(futures), start=1):
            if done % 25 == 0:
                with lock:
                    _write(dict(feeds))
                print(f"  ... {done}/{len(futures)} hosts done", file=sys.stderr, flush=True)
    return feeds, counters


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="read only the first N feeds")
    parser.add_argument("--only", default="", help="comma-separated agency ids to read")
    args = parser.parse_args(argv)

    load_agencies()
    wanted = {a.strip() for a in args.only.split(",") if a.strip()}
    agencies = [a for a in AGENCIES.values() if a.static_gtfs_url]
    if wanted:
        agencies = [a for a in agencies if a.id in wanted]
    agencies.sort(key=lambda a: a.id)
    if args.limit:
        agencies = agencies[: args.limit]

    existing: dict[str, Any] = {}
    if OUT.exists():
        existing = json.loads(OUT.read_text()).get("feeds", {})

    feeds, counters = _sweep(agencies, existing)

    _write(feeds)
    print(
        f"read {counters['read']} feeds, {counters['declared']} declared a publisher, "
        f"{counters['failed']} unreadable"
    )
    print(f"wrote {OUT.relative_to(REPO_ROOT)} with {len(feeds)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
