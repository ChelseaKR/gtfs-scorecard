"""The small agency index behind find-as-you-type agency pickers.

The home page search and the alerts signup form both suggest agencies as a
person types. Until this file existed, the signup form filled its picker from
``data/artifacts/index.json``, the full per-agency history index (84 MB
unpacked in production), and the home search read ``api/v1/ids.json``, which
also carries every feed URL. A picker needs much less: who the agency is, what
it is called, and where its page lives.

This module builds that index at render time from the same catalog records the
directory and ``ids.json`` are built from, so the picker can only offer
agencies that have a published scorecard page. One row per agency, as a
compact array in the field order the payload names, which keeps the file to a
few hundred kilobytes for the whole corpus (well under 100 KB gzipped).

Matching (case, accents, punctuation, the abbreviations agencies carry in
parentheses) happens in the browser, in ``web/src/agency-combobox.js``; this
file only publishes the rows. The index carries no score, so it never goes
stale in a way a reader could misread as a grade.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA_VERSION = 1

# Served at /data/agency-index.json (web/data/ is merged into the site's /data/
# alongside the artifacts at deploy, see .github/workflows/pages.yml).
INDEX_PATH = "data/agency-index.json"

FIELDS = ("id", "name", "slug", "place")

# The same shape the renderer accepts for an agency id: the page lives at
# /agency/<slug>/, so a row whose id could not be a path segment is dropped
# rather than published as a broken link.
_SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _place(record: Mapping[str, Any]) -> str:
    """A short location label to tell apart agencies that share a name.

    The subdivision name when the catalog knows it (``California``), else the
    country code (``CA`` for Canada), else nothing.
    """
    subdivision = str(record.get("subdivision_name") or "").strip()
    if subdivision:
        return subdivision
    return str(record.get("country") or "").strip()


def build_agency_index(
    catalog: Iterable[Mapping[str, Any]], *, generated_at: str
) -> dict[str, Any]:
    """Return the agency index payload for the given catalog records.

    Rows are ordered by id so the file is byte-stable between renders of the
    same corpus. A record with an empty name or an id that cannot be a page
    path is skipped, and a repeated id keeps its first record.
    """
    rows: dict[str, list[str]] = {}
    for record in catalog:
        agency_id = str(record.get("id") or "").strip()
        name = " ".join(str(record.get("name") or "").split())
        if not name or not _SLUG.match(agency_id) or agency_id in rows:
            continue
        rows[agency_id] = [agency_id, name, agency_id, _place(record)]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "fields": list(FIELDS),
        "agencies": [rows[key] for key in sorted(rows)],
    }
