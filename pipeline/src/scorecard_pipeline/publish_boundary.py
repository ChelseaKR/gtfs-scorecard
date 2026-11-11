"""Slim the public JSON copies at the deployment boundary.

GitHub Pages caps a published site at 1 GB, and the site as published on
2026-11-10 was 1.95 GB (`_agent-tools/growth/gtfs-under-1gb-2026-11-10.md`).
The pipeline's store writes every JSON document pretty-printed (``indent=2``,
sorted keys), and ``index.json`` carries every history point an agency ever had
with every provenance field on each point. None of that is needed by anything
that reads the published copy. This module rewrites only the copy the site
publishes: S3, the committed history, the release bundle, and the history
export are not touched, and ``latest.json`` keeps every field.

Three rules, each measured on the real artifact before it was written:

1. Every JSON file is rewritten compact (no indentation, ``,`` and ``:``
   separators). Key order and ASCII escaping are preserved, so the file parses
   to the same object. About a third of the bytes, 176 MB on the site.
2. ``index.json`` history points drop ``feed_sha256`` and
   ``service_horizon_status``. Nothing on the site reads them from the index:
   the web app, ``subscribe.js``, and the MCP server read ``date``, ``grade``,
   ``grade_qualifier``, ``score``, ``categories``, ``days_until_expiry``, and
   the producer-contract fields; the app reads ``service_horizon_status`` from
   ``latest.json`` details. 35 MB.
3. Each agency's ``index.json`` history keeps its newest
   :data:`PUBLISHED_HISTORY_POINTS` points, the same ceiling the MCP server
   already returns (``mcp_server.MAX_HISTORY_POINTS``). Without a cap the
   index grows about 1 MB a day, one point per agency per check. The agency
   page's trend shows at most that many checks; the dated archive and the
   history export keep the rest.

The module is standard library only, like ``url_redaction.py``, so the
deployment's artifact assembly (``scripts/assemble_public_artifacts.sh``) can
run it as a script without the pipeline's environment::

    python3 -I publish_boundary.py ROOT [--write]

which reports (or, with ``--write``, applies) the rewrite for every JSON file
under ROOT. It prints counts and never a value.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: Newest history points published per agency. Equal to the MCP server's
#: ``MAX_HISTORY_POINTS`` (asserted in tests): a history the site cannot show
#: in one tool call is not a richer history, it is a bigger file.
PUBLISHED_HISTORY_POINTS: Final = 120

#: Fields removed from every published ``index.json`` history point. Both stay
#: on ``latest.json`` and every dated snapshot, where their readers look.
UNPUBLISHED_INDEX_POINT_FIELDS: Final = ("feed_sha256", "service_horizon_status")

_COMPACT: Final = (",", ":")


@dataclass(frozen=True)
class SlimResult:
    """What one pass over a tree did, or would do."""

    files: int
    bytes_before: int
    bytes_after: int
    points_dropped: int
    fields_dropped: int
    #: ``.json`` files left exactly as they were because they did not parse
    #: (or could not be read as UTF-8). The assembly publishes what it was
    #: given; whether such a file belongs on the site is another gate's call.
    skipped: int = 0

    @property
    def bytes_saved(self) -> int:
        return self.bytes_before - self.bytes_after


def compact_json_text(text: str) -> str:
    """``text`` re-serialized with no whitespace; same object, same key order.

    A file whose non-ASCII characters were escaped stays ASCII; a file that
    carries raw UTF-8 keeps it. Either way the parsed object is unchanged.
    """
    return json.dumps(json.loads(text), separators=_COMPACT, ensure_ascii=text.isascii())


def _point_date(point: Any) -> str:
    return str(point.get("date") or "") if isinstance(point, dict) else ""


def slim_index(index: Any, *, max_points: int = PUBLISHED_HISTORY_POINTS) -> tuple[int, int]:
    """Cap each agency's history at its newest points and drop the unread fields.

    Mutates ``index`` in place and returns ``(points dropped, fields dropped)``.
    The publish step writes history oldest to newest; the sort keeps that true
    for the published copy even if a point were out of place. A document that
    is not an agency index (no ``agencies`` object) is left exactly as it is.
    """
    agencies = index.get("agencies") if isinstance(index, dict) else None
    if not isinstance(agencies, dict):
        return 0, 0
    points_dropped = fields_dropped = 0
    for entry in agencies.values():
        if not isinstance(entry, dict):
            continue
        history = entry.get("history")
        if not isinstance(history, list):
            continue
        history.sort(key=_point_date)
        if len(history) > max_points:
            points_dropped += len(history) - max_points
            del history[:-max_points]
        for point in history:
            if not isinstance(point, dict):
                continue
            for field in UNPUBLISHED_INDEX_POINT_FIELDS:
                if field in point:
                    del point[field]
                    fields_dropped += 1
    return points_dropped, fields_dropped


def slim_json_text(text: str, *, agency_index: bool) -> tuple[str, int, int]:
    """The published form of one JSON document and the index counts it dropped."""
    document = json.loads(text)
    points = fields = 0
    if agency_index:
        points, fields = slim_index(document)
    return json.dumps(document, separators=_COMPACT, ensure_ascii=text.isascii()), points, fields


def _json_files(root: Path) -> Iterable[Path]:
    return sorted(path for path in root.rglob("*.json") if path.is_file())


def slim_tree(root: Path, *, write: bool) -> SlimResult:
    """Rewrite (or only measure) every JSON file under ``root``.

    Only ``root/index.json`` is the agency index; ``rollups/index.json`` and
    every other file are compacted and otherwise left as they are.
    """
    files = before = after = points = fields = skipped = 0
    agency_index = root / "index.json"
    for path in _json_files(root):
        try:
            text = path.read_text(encoding="utf-8")
            slim, dropped_points, dropped_fields = slim_json_text(
                text, agency_index=path == agency_index
            )
        except (OSError, UnicodeDecodeError, ValueError):
            skipped += 1
            continue
        files += 1
        before += len(text.encode("utf-8"))
        after += len(slim.encode("utf-8"))
        points += dropped_points
        fields += dropped_fields
        if write and slim != text:
            path.write_text(slim, encoding="utf-8")
    return SlimResult(files, before, after, points, fields, skipped)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("root", type=Path, help="directory of published JSON files")
    parser.add_argument(
        "--write", action="store_true", help="rewrite the files (default: measure only)"
    )
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print(f"not a directory: {args.root}", file=sys.stderr)
        return 2
    result = slim_tree(args.root, write=args.write)
    verb = "rewrote" if args.write else "would rewrite"
    print(
        f"publish boundary: {verb} {result.files} JSON file(s), "
        f"{result.bytes_before:,} -> {result.bytes_after:,} bytes "
        f"({result.bytes_saved:,} saved); index history: {result.points_dropped} "
        f"point(s) beyond the newest {PUBLISHED_HISTORY_POINTS} and "
        f"{result.fields_dropped} unread field value(s) dropped; "
        f"{result.skipped} file(s) not JSON, left as they were"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the assembly script
    sys.exit(main())
