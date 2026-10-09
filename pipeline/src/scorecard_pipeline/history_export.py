"""The scorecard history tables (ADR 0063): every dated check, as two tables.

The free site publishes every dated artifact one file at a time, and
``index.json`` keeps a compact trend per feed record. Nothing publishes the
corpus's check-level and finding-level history as a table. This module builds
that: ``checks`` (one row per feed record per dated check) and ``findings``
(one row per finding per check), as Parquet, with a data dictionary, a
provenance file, and the license terms the tables are sold under. It is the
build step behind the paid history tier; the pricing, delivery, and the page
belong to later phases, and nothing here changes what the free site serves.

Three rules shape the code:

- **The free data stays free, and this reads it only.** Every row is derived
  from a dated artifact the site already serves. The export never writes into
  ``data/artifacts`` and never changes what ``render_site`` publishes.
- **Deterministic for a fixed input.** Rows are emitted in one order (feed
  record id, snapshot date, category, finding position), every table is written
  with an explicit schema, the zip carries fixed timestamps, and the provenance
  file dates itself from the corpus rather than the clock unless a date is
  given. Running the export twice over the same artifacts gives the same bytes.
- **Bounded memory.** Artifacts are read one at a time and streamed to
  newline-delimited JSON on disk; DuckDB reads those files to write the Parquet.
  The Python process holds one artifact, the registry, and the counters.

A publisher who asks to be left out of the paid tables is recorded in
``history-export-exclusions.yaml`` at the repository root, the same way
``corrections.yaml`` records a withdrawn grade. Every row for a listed id is
dropped from both tables, and the provenance file carries only the count, so a
sold file never names the publishers who asked not to be in it. A malformed or
missing ledger stops the export rather than shipping rows nobody checked.

Each row also carries what the registry records about the feed's license: the
structured ``license`` block's class and terms, the credit line the publisher
asks for, the record's prose ``license_note``, and the share-alike reuse notice
from ``license_notice.py`` when the block affirms one. Absence stays absent: a
record with no block has null license fields, and an empty ``license_notice``
means only that no share-alike license is recorded.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import tempfile
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

from . import DATA_ATTRIBUTION, SCHEMA_VERSION
from .comparisons import reader_archive_profile
from .config import AGENCIES, Agency, artifacts_dir, repo_root
from .identity import resolve_published_agency_name
from .license_notice import notice_for_agency
from .metrics import expiry_status, resolve_service_horizon_status
from .publish import registered_agency_dirs
from .score import published_overall

#: The shape of the export, independent of the artifact schema it reads.
TABLES_VERSION: Final = "1.0"
PRODUCT_NAME: Final = "GTFS Scorecard history tables"
SOURCE_URL: Final = "https://gtfsscorecard.org"
EXCLUSIONS_FILENAME: Final = "history-export-exclusions.yaml"

CHECKS_TABLE: Final = "checks"
FINDINGS_TABLE: Final = "findings"
DICTIONARY_FILENAME: Final = "DATA-DICTIONARY.md"
PROVENANCE_FILENAME: Final = "PROVENANCE.json"
LICENSE_FILENAME: Final = "LICENSE.md"

_CATEGORY_KEYS: Final = ("correctness", "freshness", "completeness", "realtime")
_DATED_GLOB: Final = "[0-9]" * 4 + "-[0-9][0-9]-[0-9][0-9].json"
_AGENCY_ID: Final = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_ISO_DATE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}$")
#: Every file in the zip carries this timestamp, so the archive's bytes depend
#: on its contents alone.
_ZIP_TIME: Final = (1980, 1, 1, 0, 0, 0)


class HistoryExportError(ValueError):
    """The export cannot proceed as asked, and says why."""


@dataclass(frozen=True)
class Column:
    """One column of a table: its name, its DuckDB type, and what it means."""

    name: str
    type: str
    meaning: str


#: ``checks``: one row per feed record per dated check.
CHECKS_COLUMNS: Final[tuple[Column, ...]] = (
    Column("agency_id", "VARCHAR", "The feed record's id, the last part of its scorecard address."),
    Column("agency_name", "VARCHAR", "The name the scorecard publishes for the record."),
    Column(
        "country", "VARCHAR", "ISO 3166-1 alpha-2 country; US for records that predate the field."
    ),
    Column(
        "subdivision_code",
        "VARCHAR",
        "ISO 3166-2 state, province, or territory; null when unknown.",
    ),
    Column("subdivision_name", "VARCHAR", "The subdivision's display name; null when unknown."),
    Column(
        "mdb_id", "VARCHAR", "Mobility Database id from the registry; null when none is pinned."
    ),
    Column(
        "ntd_id",
        "VARCHAR",
        "FTA National Transit Database reporter id from the registry; null when none.",
    ),
    Column("snapshot_date", "DATE", "The date of this check (the dated artifact's name)."),
    Column("generated_at", "VARCHAR", "When the artifact was written, ISO 8601 with offset."),
    Column(
        "recompute_kind",
        "VARCHAR",
        "freshness when this row is an intraday sweep that re-read only the calendar dates "
        "and carried the other categories forward; null for a full score.",
    ),
    Column(
        "feed_fetched_date",
        "DATE",
        "The date the scored bytes were downloaded; earlier than snapshot_date on a sweep row.",
    ),
    Column(
        "artifact_schema_version",
        "VARCHAR",
        "The per-agency artifact schema the row was read from.",
    ),
    Column("rubric_version", "VARCHAR", "Rubric version the check was scored under."),
    Column("scoring_profile_id", "VARCHAR", "Scoring profile id; compare grades only within one."),
    Column("scoring_profile_rubric_version", "VARCHAR", "The profile's own rubric version."),
    Column("validator_version", "VARCHAR", "MobilityData gtfs-validator release used."),
    Column(
        "reader_archive_profile",
        "VARCHAR",
        "How the archive was read: raw-v1 or flat-single-root-v1.",
    ),
    Column("grade", "VARCHAR", "Letter grade derived from score, as the public trend derives it."),
    Column("score", "DOUBLE", "Overall score, 0 to 100."),
    Column("correctness", "DOUBLE", "Correctness category score; null when not measured."),
    Column("freshness", "DOUBLE", "Freshness category score; null when not measured."),
    Column(
        "completeness", "DOUBLE", "Rider-experience completeness score; null when not measured."
    ),
    Column(
        "realtime",
        "DOUBLE",
        "Realtime category score; null when the agency publishes no realtime feed.",
    ),
    Column(
        "categories_measured", "INTEGER", "How many of the four categories this check measured."
    ),
    Column(
        "confidence_level",
        "VARCHAR",
        "provisional, medium, or high; null before artifact schema 1.6.",
    ),
    Column(
        "days_until_expiry",
        "INTEGER",
        "Days of service left at the check; negative once expired; null when unknown.",
    ),
    Column(
        "effective_expiry_date",
        "DATE",
        "The earlier of feed_info end and the last service date; null when unknown.",
    ),
    Column(
        "expiry_status",
        "VARCHAR",
        "current, expiring_soon, lapsed, stale, or unknown, from days_until_expiry.",
    ),
    Column(
        "service_horizon_status",
        "VARCHAR",
        "within_review_threshold, unusually_distant, or unknown.",
    ),
    Column("feed_sha256", "VARCHAR", "SHA-256 of the scored feed bytes."),
    Column("feed_size_bytes", "BIGINT", "Size of the scored archive; null when not recorded."),
    Column("feed_static_url", "VARCHAR", "The configured feed URL at the time of the check."),
    Column(
        "fetch_source", "VARCHAR", "origin, mirror, or unknown: where the scored bytes came from."
    ),
    Column(
        "fetch_final_url",
        "VARCHAR",
        "The URL that actually served the bytes; null when not recorded.",
    ),
    Column(
        "source_provenance",
        "VARCHAR",
        "official, third_party, archive, or unverified; null before schema 1.18.",
    ),
    Column("stop_count", "INTEGER", "Boardable stops read from stops.txt; null when not recorded."),
    Column(
        "primary_mode",
        "VARCHAR",
        "Trip-weighted primary GTFS mode; null before the mode profile existed.",
    ),
    Column("finding_count", "INTEGER", "Rows in the findings table for this check."),
    Column(
        "top_fix_code", "VARCHAR", "The notice code ranked first among the fixes; null when none."
    ),
    Column(
        "license_id",
        "VARCHAR",
        "License class from the registry's structured block; null when no block is on file.",
    ),
    Column(
        "license_status", "VARCHAR", "unreviewed, needs_review, or reviewed; null when no block."
    ),
    Column(
        "attribution_required",
        "VARCHAR",
        "true, false, or unknown as the block records it; null when no block.",
    ),
    Column(
        "redistribution_allowed",
        "VARCHAR",
        "true, false, or unknown as the block records it; null when no block.",
    ),
    Column(
        "share_alike",
        "VARCHAR",
        "true, false, or unknown as the block records it; null when no block.",
    ),
    Column("license_terms_url", "VARCHAR", "The publisher's terms, when the block links them."),
    Column(
        "publisher_credit",
        "VARCHAR",
        "The credit line the publisher asks for, when the block records one.",
    ),
    Column(
        "license_note", "VARCHAR", "The registry's prose note on the feed's terms; never a grant."
    ),
    Column(
        "license_notice",
        "VARCHAR",
        "The share-alike reuse notice when the block affirms one; null means no share-alike "
        "license is recorded, not that the license is known or permissive.",
    ),
)

#: ``findings``: one row per finding per check.
FINDINGS_COLUMNS: Final[tuple[Column, ...]] = (
    Column("agency_id", "VARCHAR", "Joins to checks.agency_id."),
    Column("snapshot_date", "DATE", "Joins to checks.snapshot_date."),
    Column("category", "VARCHAR", "correctness, freshness, completeness, or realtime."),
    Column("finding_index", "INTEGER", "Position within the category's finding list, from 0."),
    Column("code", "VARCHAR", "The notice code: a validator notice or a scorecard_ finding."),
    Column("severity", "VARCHAR", "ERROR, WARNING, or INFO as the artifact recorded it."),
    Column("count", "BIGINT", "Instances the finding counted; null when it has no count."),
    Column("points", "DOUBLE", "Points the finding cost in its category; null when not recorded."),
    Column(
        "owner",
        "VARCHAR",
        "Who the fix most likely belongs to, as the scorecard words it; null when absent.",
    ),
    Column(
        "top_fix_rank",
        "INTEGER",
        "1, 2, or 3 when the finding is one of the check's top fixes; null otherwise.",
    ),
    Column(
        "reach_basis",
        "VARCHAR",
        "What reach is counted against (stops, trips, routes, none); null before schema 1.19.",
    ),
    Column("reach_affected", "BIGINT", "Instances affected; null when no share is countable."),
    Column(
        "reach_total",
        "BIGINT",
        "The published total the finding is counted against; null when none.",
    ),
    Column("reach_share", "DOUBLE", "affected / total, 0 to 1; null when no share is countable."),
    Column(
        "reach_reason",
        "VARCHAR",
        "Why no share is given (feed_level, sampled_window, ...); null when one is.",
    ),
)

#: The terms the packaged tables are sold under. ``docs/history-tables.md``
#: carries the same words, and a test holds the two together.
LICENSE_TEXT: Final = """# License for the GTFS Scorecard history tables

These tables are a packaged work prepared by GTFS Scorecard (gtfsscorecard.org).
They are licensed to the purchasing organization, not to the public.

1. One organization. The purchaser may use the tables inside its own
   organization, for any internal purpose, including work it is paid for.
2. No redistribution of the package. The purchaser may not publish, sell,
   sublicense, or share the tables, in whole or in substantial part, outside
   its organization. Figures, charts, and findings derived from the tables may
   be published freely.
3. The facts stay free. Every number in these tables is derived from a dated
   scorecard artifact that gtfsscorecard.org publishes free of charge under
   CC BY 4.0, and the export command that built them is open source. Nothing in
   this license restricts the use of those free sources.
4. Share-alike rows. A row whose license_notice names a share-alike license is
   licensed to the purchaser under that license, not under clauses 1 and 2, and
   may be redistributed on that license's terms.
5. Publisher terms travel with the rows. Each feed's own publisher terms,
   recorded in license_id, license_terms_url, publisher_credit, and
   license_note, continue to apply to what the row says about that feed.
6. Attribution. A published figure drawn from the tables credits "GTFS Scorecard
   (gtfsscorecard.org), scored on top of the MobilityData gtfs-validator" and
   any publisher_credit the row carries.
7. No warranty. The grade is a data-quality signal, not a compliance
   determination, and the tables are provided as they are.
"""


@dataclass(frozen=True)
class Exclusion:
    """One publisher's request to be left out of the paid tables."""

    agency_id: str
    requested_on: str
    reason: str


@dataclass(frozen=True)
class Exclusions:
    """The exclusion ledger, parsed and checked."""

    entries: tuple[Exclusion, ...] = ()

    @property
    def ids(self) -> frozenset[str]:
        return frozenset(entry.agency_id for entry in self.entries)


def exclusions_path(root: Path | None = None) -> Path:
    """Where the opt-out ledger lives: one reviewed file at the repository root."""
    return (root or repo_root()) / EXCLUSIONS_FILENAME


def _entry_text(raw: Mapping[str, Any], key: str, label: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise HistoryExportError(f"{label}: {key} must be a non-empty string")
    return value.strip()


def parse_exclusions(raw: object, *, source: str = EXCLUSIONS_FILENAME) -> Exclusions:
    """Check the ledger's shape; refuse anything a reader would have to guess at."""
    if not isinstance(raw, Mapping) or set(raw) != {"excluded"}:
        raise HistoryExportError(f"{source}: expected one top-level key, excluded")
    items = raw["excluded"]
    if items is None:
        items = []
    if not isinstance(items, list):
        raise HistoryExportError(f"{source}: excluded must be a list")
    entries: list[Exclusion] = []
    seen: set[str] = set()
    for position, item in enumerate(items):
        label = f"{source}: excluded[{position}]"
        if not isinstance(item, Mapping) or set(item) != {"agency_id", "requested_on", "reason"}:
            raise HistoryExportError(f"{label}: needs exactly agency_id, requested_on, reason")
        agency_id = _entry_text(item, "agency_id", label)
        if not _AGENCY_ID.fullmatch(agency_id):
            raise HistoryExportError(f"{label}: agency_id {agency_id!r} is not a record id")
        if agency_id in seen:
            raise HistoryExportError(f"{label}: {agency_id} is listed twice")
        requested_on = _entry_text(item, "requested_on", label)
        if not _ISO_DATE.fullmatch(requested_on):
            raise HistoryExportError(f"{label}: requested_on must be an ISO date (YYYY-MM-DD)")
        try:
            dt.date.fromisoformat(requested_on)
        except ValueError as exc:
            raise HistoryExportError(f"{label}: requested_on is not a real date") from exc
        seen.add(agency_id)
        entries.append(Exclusion(agency_id, requested_on, _entry_text(item, "reason", label)))
    return Exclusions(tuple(entries))


def read_exclusions(path: Path) -> Exclusions:
    """Read the ledger. A missing file is an error: an export that cannot see
    the requests must not assume there are none."""
    if not path.is_file():
        raise HistoryExportError(f"{path}: the exclusion ledger is missing")
    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise HistoryExportError(f"{path}: not valid YAML: {exc}") from exc
    return parse_exclusions(raw, source=path.name)


def _tri(value: object) -> str | None:
    """A license term as recorded: 'true', 'false', or 'unknown'."""
    if value is True:
        return "true"
    if value is False:
        return "false"
    if value == "unknown":
        return "unknown"
    return None


def _license_fields(agency: Agency | None) -> dict[str, Any]:
    """The license columns for one record. No block means null everywhere
    except the prose note, never a permissive reading."""
    fields: dict[str, Any] = {
        "license_id": None,
        "license_status": None,
        "attribution_required": None,
        "redistribution_allowed": None,
        "share_alike": None,
        "license_terms_url": None,
        "publisher_credit": None,
        "license_note": (agency.license_note or None) if agency is not None else None,
        "license_notice": None,
    }
    block = agency.license_block if agency is not None else None
    if block is not None:
        fields.update(
            license_id=block.id,
            license_status=block.status,
            attribution_required=_tri(block.attribution_required),
            redistribution_allowed=_tri(block.redistribution_allowed),
            share_alike=_tri(block.share_alike),
            license_terms_url=block.terms_url or None,
            publisher_credit=block.attribution or None,
        )
    notice = notice_for_agency(agency)
    if notice is not None:
        fields["license_notice"] = notice.export_text()
    return fields


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _text_or_none(value: object) -> str | None:
    if isinstance(value, str) and value:
        return value
    return None


def _date_or_none(value: object) -> str | None:
    text = _text_or_none(value)
    if text is None or not _ISO_DATE.fullmatch(text):
        return None
    try:
        dt.date.fromisoformat(text)
    except ValueError:
        return None
    return text


def _reach_fields(finding: Mapping[str, Any]) -> dict[str, Any]:
    reach = (finding.get("consequence") or {}).get("reach") or {}
    return {
        "reach_basis": _text_or_none(reach.get("basis")),
        "reach_affected": _int_or_none(reach.get("affected")),
        "reach_total": _int_or_none(reach.get("total")),
        "reach_share": _float_or_none(reach.get("share")),
        "reach_reason": _text_or_none(reach.get("reason")),
    }


def finding_rows(agency_id: str, artifact: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The findings rows for one dated artifact, in category then list order."""
    snapshot_date = str(artifact["snapshot_date"])
    ranks: dict[str, int] = {}
    for fix in artifact.get("top_fixes") or []:
        code = _text_or_none(fix.get("code"))
        rank = _int_or_none(fix.get("rank"))
        if code is not None and rank is not None and code not in ranks:
            ranks[code] = rank
    rows: list[dict[str, Any]] = []
    categories = artifact.get("categories") or {}
    for category in _CATEGORY_KEYS:
        block = categories.get(category) or {}
        for position, finding in enumerate(block.get("findings") or []):
            code = _text_or_none(finding.get("code"))
            if code is None:
                continue
            rows.append(
                {
                    "agency_id": agency_id,
                    "snapshot_date": snapshot_date,
                    "category": category,
                    "finding_index": position,
                    "code": code,
                    "severity": _text_or_none(finding.get("severity")),
                    "count": _int_or_none(finding.get("count")),
                    "points": _float_or_none(finding.get("points")),
                    "owner": _text_or_none(finding.get("owner")),
                    "top_fix_rank": ranks.get(code),
                    **_reach_fields(finding),
                }
            )
    return rows


def check_row(
    agency_id: str,
    artifact: Mapping[str, Any],
    *,
    agency: Agency | None,
    finding_count: int,
) -> dict[str, Any]:
    """The checks row for one dated artifact."""
    agency_block = artifact.get("agency") or {}
    categories = artifact.get("categories") or {}
    measured = {
        key: _float_or_none(block.get("score"))
        for key in _CATEGORY_KEYS
        if isinstance(block := categories.get(key), Mapping) and block.get("status") == "measured"
    }
    freshness_details = (categories.get("freshness") or {}).get("details") or {}
    days = _int_or_none(freshness_details.get("days_until_expiry"))
    overall = published_overall(float(artifact["overall"]["score"]))
    profile = artifact.get("scoring_profile") or {}
    feed = artifact.get("feed") or {}
    fetch = artifact.get("fetch") or {}
    recompute = artifact.get("recompute") or {}
    snapshot_date = str(artifact["snapshot_date"])
    top_fixes = artifact.get("top_fixes") or []
    top_fix_code = _text_or_none(top_fixes[0].get("code")) if top_fixes else None
    mode_profile = artifact.get("mode_profile") or {}
    row: dict[str, Any] = {
        "agency_id": agency_id,
        "agency_name": resolve_published_agency_name(
            agency_id,
            registry_name=agency.name if agency is not None else "",
            artifact_name=str(agency_block.get("name") or ""),
        ),
        "country": str(agency_block.get("country") or "US"),
        "subdivision_code": _text_or_none(agency_block.get("subdivision_code")),
        "subdivision_name": _text_or_none(agency_block.get("subdivision_name")),
        "mdb_id": (agency.mdb_id or None) if agency is not None else None,
        "ntd_id": (agency.ntd_id or None) if agency is not None else None,
        "snapshot_date": snapshot_date,
        "generated_at": _text_or_none(artifact.get("generated_at")),
        "recompute_kind": _text_or_none(recompute.get("kind")),
        "feed_fetched_date": _date_or_none(recompute.get("feed_fetched_date")) or snapshot_date,
        "artifact_schema_version": _text_or_none(artifact.get("schema_version")),
        "rubric_version": _text_or_none(artifact.get("rubric_version")),
        "scoring_profile_id": _text_or_none(profile.get("id")),
        "scoring_profile_rubric_version": _text_or_none(profile.get("rubric_version")),
        "validator_version": _text_or_none(artifact.get("validator_version")),
        "reader_archive_profile": reader_archive_profile(dict(artifact)),
        "grade": overall["grade"],
        "score": overall["score"],
        "correctness": measured.get("correctness"),
        "freshness": measured.get("freshness"),
        "completeness": measured.get("completeness"),
        "realtime": measured.get("realtime"),
        "categories_measured": len(measured),
        "confidence_level": _text_or_none((artifact.get("confidence") or {}).get("level")),
        "days_until_expiry": days,
        "effective_expiry_date": _date_or_none(freshness_details.get("effective_expiry_date")),
        "expiry_status": expiry_status(days),
        "service_horizon_status": resolve_service_horizon_status(freshness_details, snapshot_date),
        "feed_sha256": _text_or_none(feed.get("sha256")),
        "feed_size_bytes": _int_or_none(feed.get("size_bytes")),
        "feed_static_url": _text_or_none(feed.get("static_url")),
        "fetch_source": _text_or_none(fetch.get("source")) or "unknown",
        "fetch_final_url": _text_or_none(fetch.get("final_url")),
        "source_provenance": _text_or_none(feed.get("source_provenance")),
        "stop_count": _int_or_none((artifact.get("geo") or {}).get("stop_count")),
        "primary_mode": _text_or_none(mode_profile.get("primary_mode")),
        "finding_count": finding_count,
        "top_fix_code": top_fix_code,
        **_license_fields(agency),
    }
    return row


def _read_dated(path: Path) -> dict[str, Any] | None:
    """One dated artifact, or None when it is not a scorecard this export can
    read. The reason is left to the caller's counters; a corrupt file must not
    abort a corpus-wide build, and must not become a row either."""
    try:
        artifact = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(artifact, dict):
        return None
    if str(artifact.get("snapshot_date") or "") != path.stem:
        return None
    overall = artifact.get("overall")
    if not isinstance(overall, Mapping) or _float_or_none(overall.get("score")) is None:
        return None
    return artifact


@dataclass
class Counters:
    """What the build read, kept out of the rows."""

    feed_records: int = 0
    artifacts_read: int = 0
    artifacts_unreadable: int = 0
    checks: int = 0
    findings: int = 0
    excluded_records: int = 0
    excluded_artifacts: int = 0
    first_snapshot: str | None = None
    last_snapshot: str | None = None
    artifact_schema_versions: dict[str, int] = field(default_factory=dict)

    def saw(self, artifact: Mapping[str, Any]) -> None:
        date = str(artifact["snapshot_date"])
        self.first_snapshot = (
            date if self.first_snapshot is None else min(self.first_snapshot, date)
        )
        self.last_snapshot = date if self.last_snapshot is None else max(self.last_snapshot, date)
        version = str(artifact.get("schema_version") or "unknown")
        self.artifact_schema_versions[version] = self.artifact_schema_versions.get(version, 0) + 1


def iter_rows(
    root: Path,
    *,
    agencies: Mapping[str, Agency],
    exclusions: Exclusions,
    counters: Counters,
) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Yield (checks row, findings rows) per dated artifact, in table order.

    Walks the registered agency directories under ``root`` (the same bound the
    public site applies), each one's dated files in date order. A record on the
    exclusion ledger yields nothing and is counted.
    """
    for agency_dir in sorted(registered_agency_dirs(root), key=lambda p: p.name):
        agency_id = agency_dir.name
        dated = sorted(agency_dir.glob(_DATED_GLOB))
        if not dated:
            continue
        if agency_id in exclusions.ids:
            counters.excluded_records += 1
            counters.excluded_artifacts += len(dated)
            continue
        counters.feed_records += 1
        agency = agencies.get(agency_id)
        for path in dated:
            artifact = _read_dated(path)
            if artifact is None:
                counters.artifacts_unreadable += 1
                continue
            counters.artifacts_read += 1
            counters.saw(artifact)
            findings = finding_rows(agency_id, artifact)
            row = check_row(agency_id, artifact, agency=agency, finding_count=len(findings))
            counters.checks += 1
            counters.findings += len(findings)
            yield row, findings


def rows_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    """SHA-256 over the rows as canonical JSON lines, for determinism checks
    that do not need the Parquet writer."""
    digest = hashlib.sha256()
    for row in rows:
        digest.update(json.dumps(row, sort_keys=True, separators=(",", ":")).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def render_dictionary() -> str:
    """The data dictionary that ships beside the tables."""
    lines = [
        f"# {PRODUCT_NAME}: data dictionary",
        "",
        f"Tables version {TABLES_VERSION}, built from per-agency artifacts of schema "
        f"{SCHEMA_VERSION} and earlier. Two tables, joined on agency_id and snapshot_date.",
        "",
        "A null means the artifact did not record the value. It never means zero, and it",
        "never means a license is permissive. A row with recompute_kind = freshness is an",
        "intraday sweep: only the calendar dates were re-read that day, and the other",
        "category scores are the previous full score's, carried forward.",
        "",
        "Grades are comparable only within one scoring_profile_id, validator_version,",
        "rubric_version, reader_archive_profile, and set of measured categories. The free",
        "site's comparison rules (docs/comparison-policy.md) apply here unchanged.",
        "",
    ]
    for table, columns in ((CHECKS_TABLE, CHECKS_COLUMNS), (FINDINGS_TABLE, FINDINGS_COLUMNS)):
        lines.append(f"## {table}.parquet")
        lines.append("")
        lines.append("| Column | Type | Meaning |")
        lines.append("| --- | --- | --- |")
        for column in columns:
            lines.append(f"| `{column.name}` | {column.type} | {column.meaning} |")
        lines.append("")
    lines.append(f"Attribution: {DATA_ATTRIBUTION}.")
    lines.append("")
    return "\n".join(lines)


def _duckdb() -> Any:
    try:
        import duckdb
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via the CLI
        raise HistoryExportError(
            "The history export needs DuckDB. Install it with: pip install 'gtfs-scorecard[query]'"
        ) from exc
    return duckdb


def _write_parquet(
    duckdb: Any, ndjson: Path, columns: tuple[Column, ...], out: Path, order_by: str
) -> None:
    """One table from its newline-delimited rows, with an explicit schema so the
    types never depend on which values happened to be present."""
    schema = ", ".join(f"'{column.name}': '{column.type}'" for column in columns)
    names = ", ".join(column.name for column in columns)
    con = duckdb.connect()
    try:
        # The column names and types are module constants, not user input, and
        # the two paths are named parameters: with positional ones DuckDB bound
        # the COPY target before the source, and read_json tried to open the
        # Parquet it was about to write.
        con.execute(
            f"COPY (SELECT {names} FROM read_json($src, format='newline_delimited', "  # noqa: S608
            f"columns={{{schema}}}) ORDER BY {order_by}) TO $dst (FORMAT PARQUET)",
            {"src": str(ndjson), "dst": str(out)},
        )
    finally:
        con.close()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _provenance(counters: Counters, out_dir: Path, generated_on: str) -> dict[str, Any]:
    return {
        "product": PRODUCT_NAME,
        "tables_version": TABLES_VERSION,
        "generated_on": generated_on,
        "source": SOURCE_URL,
        "attribution": DATA_ATTRIBUTION,
        "license": LICENSE_FILENAME,
        "pipeline_schema_version": SCHEMA_VERSION,
        "snapshot_dates": {"first": counters.first_snapshot, "last": counters.last_snapshot},
        "feed_records": counters.feed_records,
        "artifacts_read": counters.artifacts_read,
        "artifacts_unreadable": counters.artifacts_unreadable,
        "artifact_schema_versions": dict(sorted(counters.artifact_schema_versions.items())),
        "excluded_by_request": {
            "feed_records": counters.excluded_records,
            "artifacts": counters.excluded_artifacts,
        },
        "tables": {
            CHECKS_TABLE: {
                "rows": counters.checks,
                "sha256": _sha256(out_dir / f"{CHECKS_TABLE}.parquet"),
            },
            FINDINGS_TABLE: {
                "rows": counters.findings,
                "sha256": _sha256(out_dir / f"{FINDINGS_TABLE}.parquet"),
            },
        },
    }


def export_files(out_dir: Path) -> tuple[str, ...]:
    """Every file an export writes, in archive order."""
    return (
        f"{CHECKS_TABLE}.parquet",
        f"{FINDINGS_TABLE}.parquet",
        DICTIONARY_FILENAME,
        LICENSE_FILENAME,
        PROVENANCE_FILENAME,
    )


def write_zip(out_dir: Path, zip_path: Path) -> Path:
    """Pack the export with fixed timestamps and a fixed order, so the archive's
    bytes follow from its contents."""
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in export_files(out_dir):
            info = zipfile.ZipInfo(name, date_time=_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, (out_dir / name).read_bytes(), compresslevel=9)
    return zip_path


def export_history(
    out_dir: Path,
    *,
    root: Path | None = None,
    agencies: Mapping[str, Agency] | None = None,
    exclusions: Exclusions | None = None,
    generated_on: str | None = None,
    zip_path: Path | None = None,
) -> Counters:
    """Build the tables, the dictionary, the license, and the provenance file
    into ``out_dir`` (which must be new or empty), and optionally a zip.

    ``generated_on`` defaults to the newest snapshot date in the corpus, so the
    provenance file is a function of the input rather than of the clock.
    """
    duckdb = _duckdb()
    artifact_root = root or artifacts_dir()
    registry = agencies if agencies is not None else AGENCIES
    ledger = exclusions if exclusions is not None else read_exclusions(exclusions_path())
    if generated_on is not None and _date_or_none(generated_on) is None:
        raise HistoryExportError("generated_on must be an ISO date (YYYY-MM-DD)")
    out_dir.mkdir(parents=True, exist_ok=True)
    if any(out_dir.iterdir()):
        raise HistoryExportError(f"{out_dir}: must be a new or empty directory")
    counters = Counters()
    with tempfile.TemporaryDirectory(prefix="history-export-") as tmp:
        checks_ndjson = Path(tmp) / "checks.ndjson"
        findings_ndjson = Path(tmp) / "findings.ndjson"
        with checks_ndjson.open("w") as checks_out, findings_ndjson.open("w") as findings_out:
            for row, findings in iter_rows(
                artifact_root, agencies=registry, exclusions=ledger, counters=counters
            ):
                checks_out.write(json.dumps(row, sort_keys=True) + "\n")
                for finding in findings:
                    findings_out.write(json.dumps(finding, sort_keys=True) + "\n")
        _write_parquet(
            duckdb,
            checks_ndjson,
            CHECKS_COLUMNS,
            out_dir / f"{CHECKS_TABLE}.parquet",
            "agency_id, snapshot_date",
        )
        _write_parquet(
            duckdb,
            findings_ndjson,
            FINDINGS_COLUMNS,
            out_dir / f"{FINDINGS_TABLE}.parquet",
            "agency_id, snapshot_date, category, finding_index",
        )
    (out_dir / DICTIONARY_FILENAME).write_text(render_dictionary())
    (out_dir / LICENSE_FILENAME).write_text(LICENSE_TEXT)
    stamp = generated_on or counters.last_snapshot or "unknown"
    provenance = _provenance(counters, out_dir, stamp)
    (out_dir / PROVENANCE_FILENAME).write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    )
    if zip_path is not None:
        write_zip(out_dir, zip_path)
    return counters
