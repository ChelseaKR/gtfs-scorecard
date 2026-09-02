"""Program report bundle: one program's branded board reports, for a cohort.

The site already ships one agency's board report as a self-contained file
(report.py, docs/board-report.md). A state program, a technical-assistance
center, a feed vendor, or a consultancy that prepares packets for *many*
agencies wants the same thing for its whole caseload, with its own name on
the cover, delivered as one archive and refreshed on a schedule. This module
is the pure core of that product (docs/program-plan.md, ADR 0049): it turns a
request into a validated ``BundleRequest``, classifies every requested agency
id against the loaded registry, renders each current one through the
existing report generator, and zips the results with a manifest that names
every id that was asked for and what happened to it.

Nothing here computes a new metric or a new grade. Each report is the same
document the free CLI produces; the bundle is packaging, branding, and
delivery for the program tier. The agency-facing report stays free and
unchanged (gtfs-scorecard-plans/07: the paid thing is additive and for
someone else).

Two rules shape the shape of this file:

- **An id is never silently dropped.** A request for 40 agencies that yields
  37 reports says so, per id, in the manifest and the delivery email: unknown
  id, retired alias, or no published scorecard. A bundle that quietly shrank
  would teach a program to distrust the tool.
- **Nothing here talks to a payment provider.** Whether a request was paid
  for is settled before it reaches this module (infra/program-bundle). The
  core can be run locally against the committed snapshot with no account and
  no key, the same way ``scorecard report`` can.
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import re
import secrets
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .agencies import ID_PATTERN
from .config import AGENCIES
from .net import UnsafeURLError, validate_public_url
from .notify import Email
from .report import DEFAULT_ACCENT, Brand, ReportError, _validate_accent, generate_report

MAX_AGENCIES = 100
MAX_PROGRAM_NAME = 120
MAX_LOGO_BYTES = 512 * 1024
CADENCES = ("one_time", "monthly")
BUNDLE_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DATA_URI_RE = re.compile(
    r"^data:(image/svg\+xml|image/png|image/jpeg);base64,([A-Za-z0-9+/=\s]+)$"
)
_LOGO_MEDIA_TYPES = ("image/svg+xml", "image/png", "image/jpeg")
# The link a bundle lives behind is a 128-bit capability; it expires with the
# object. Kept in step with the S3 lifecycle rule for program-bundles/ in
# infra/artifacts/main.tf and the DynamoDB TTL in infra/program-bundle.
DOWNLOAD_DAYS = 30

FetchLogo = Callable[[str], bytes]


class BundleError(ValueError):
    """A request problem the message explains in plain language."""


@dataclass(frozen=True)
class BundleRequest:
    """One validated request for a bundle.

    ``logo`` is either a data: URI (already embedded) or an https URL still to
    be fetched at build time, or None. The setup Lambda validates the URL's
    shape but never fetches it; the build step, which has the SSRF-guarded
    fetch layer, does.
    """

    bundle_id: str
    program_name: str
    accent: str
    logo: str | None
    agency_ids: tuple[str, ...]
    deliver_to: str
    cadence: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "program_name": self.program_name,
            "accent": self.accent,
            "logo": self.logo or "",
            "agency_ids": list(self.agency_ids),
            "deliver_to": self.deliver_to,
            "cadence": self.cadence,
        }


def new_bundle_id() -> str:
    """A fresh 128-bit hex token; the bundle's download capability."""
    return secrets.token_hex(16)


def _text(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    return value.strip() if isinstance(value, str) else ""


def _agency_ids(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        parts = raw.replace("\n", ",").split(",")
    elif isinstance(raw, list | tuple):
        parts = [str(item) for item in raw]
    else:
        raise BundleError("agency_ids must be a comma-separated string or a list")
    seen: list[str] = []
    for part in parts:
        agency_id = part.strip().lower()
        if not agency_id:
            continue
        if not ID_PATTERN.match(agency_id):
            raise BundleError(
                f"agency id {agency_id!r} is not a scorecard id "
                "(lowercase letters, digits, - and _)"
            )
        if agency_id not in seen:
            seen.append(agency_id)
    if not seen:
        raise BundleError("agency_ids must name at least one agency")
    if len(seen) > MAX_AGENCIES:
        raise BundleError(
            f"a bundle covers at most {MAX_AGENCIES} agencies; {len(seen)} were given"
        )
    return tuple(seen)


def _logo(raw: str) -> str | None:
    if not raw:
        return None
    if raw.startswith("data:"):
        match = _DATA_URI_RE.match(raw)
        if match is None:
            raise BundleError("logo must be an SVG, PNG, or JPEG data: URI, or an https URL")
        try:
            decoded = base64.b64decode(match.group(2), validate=False)
        except ValueError as err:
            raise BundleError("logo data: URI is not valid base64") from err
        if len(decoded) > MAX_LOGO_BYTES:
            raise BundleError(f"logo must be {MAX_LOGO_BYTES // 1024} KiB or smaller")
        return raw
    if not raw.startswith("https://"):
        raise BundleError("logo must be an https URL or an SVG, PNG, or JPEG data: URI")
    try:
        validate_public_url(raw)
    except UnsafeURLError as err:
        raise BundleError(f"logo URL refused: {err}") from err
    return raw


def parse_request(raw: Mapping[str, object]) -> BundleRequest:
    """Validate a raw request (form body, workflow inputs, or a stored row).

    Raises BundleError with one plain sentence on the first problem, so the
    setup form can show it and a workflow log can be read without the code.
    """
    bundle_id = _text(raw, "bundle_id").lower()
    if not BUNDLE_ID_RE.match(bundle_id):
        raise BundleError("bundle_id must be 32 lowercase hex characters")
    program_name = _text(raw, "program_name")
    if not program_name:
        raise BundleError("program_name is required; it goes on every report cover")
    if len(program_name) > MAX_PROGRAM_NAME:
        raise BundleError(f"program_name must be {MAX_PROGRAM_NAME} characters or fewer")
    try:
        accent = _validate_accent(_text(raw, "accent") or DEFAULT_ACCENT)
    except ReportError as err:
        raise BundleError(str(err)) from err
    deliver_to = _text(raw, "deliver_to")
    if not _EMAIL_RE.match(deliver_to):
        raise BundleError("deliver_to must be an email address; the download link goes there")
    cadence = _text(raw, "cadence") or "one_time"
    if cadence not in CADENCES:
        raise BundleError(f"cadence must be one of {', '.join(CADENCES)}")
    return BundleRequest(
        bundle_id=bundle_id,
        program_name=program_name,
        accent=accent,
        logo=_logo(_text(raw, "logo")),
        agency_ids=_agency_ids(raw.get("agency_ids")),
        deliver_to=deliver_to,
        cadence=cadence,
    )


# ---------------------------------------------------------------------------
# Classification: which requested ids can become a report, and why not.
# ---------------------------------------------------------------------------

STATUS_CURRENT = "current"
STATUS_UNKNOWN = "unknown_id"
STATUS_RETIRED = "retired"
STATUS_NOT_PUBLISHED = "not_published"
STATUS_INCLUDED = "included"

_STATUS_DETAIL = {
    STATUS_UNKNOWN: "not a tracked scorecard id; check the id on gtfsscorecard.org/agencies/",
    STATUS_RETIRED: "a retired record; its successor publishes the current grade",
    STATUS_NOT_PUBLISHED: "tracked, but no scorecard is published for it yet",
}


def classify(agency_ids: tuple[str, ...]) -> dict[str, str]:
    """Map each id to current / unknown_id / retired against the loaded registry.

    An empty process-global registry is the library/test compatibility mode
    (config.current_agency_ids): every id is treated as current and the
    artifact tree decides.
    """
    if not AGENCIES:
        return dict.fromkeys(agency_ids, STATUS_CURRENT)
    out: dict[str, str] = {}
    for agency_id in agency_ids:
        agency = AGENCIES.get(agency_id)
        if agency is None:
            out[agency_id] = STATUS_UNKNOWN
        elif agency.is_canonical_feed:
            out[agency_id] = STATUS_CURRENT
        else:
            out[agency_id] = STATUS_RETIRED
    return out


def plan(request: BundleRequest) -> dict[str, Any]:
    """The build plan a workflow reads before hydrating artifacts: which ids
    to fetch, and which were refused up front and why."""
    statuses = classify(request.agency_ids)
    return {
        "bundle_id": request.bundle_id,
        "current": [a for a, s in statuses.items() if s == STATUS_CURRENT],
        "refused": [
            {"id": a, "status": s, "detail": _STATUS_DETAIL[s]}
            for a, s in statuses.items()
            if s != STATUS_CURRENT
        ],
    }


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def _sniff_media_type(raw: bytes) -> str:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8"):
        return "image/jpeg"
    head = raw[:2048].lstrip().lower()
    if head.startswith(b"<") and b"<svg" in head:
        return "image/svg+xml"
    raise BundleError("logo URL did not return an SVG, PNG, or JPEG image")


def _default_fetch(url: str) -> bytes:
    from .net import safe_get

    return safe_get(url, timeout=(10, 30), max_bytes=MAX_LOGO_BYTES)


def resolve_logo(logo: str | None, fetch: FetchLogo | None = None) -> str | None:
    """Turn the request's logo into a data: URI, fetching an https URL through
    the SSRF-guarded fetch layer. A data: URI passes through unchanged."""
    if logo is None or logo.startswith("data:"):
        return logo
    fetcher = fetch or _default_fetch
    try:
        raw = fetcher(logo)
    except Exception as err:  # any fetch failure is one plain sentence to the buyer
        raise BundleError(f"logo could not be fetched from {logo}: {err}") from err
    if len(raw) > MAX_LOGO_BYTES:
        raise BundleError(f"logo must be {MAX_LOGO_BYTES // 1024} KiB or smaller")
    media_type = _sniff_media_type(raw)
    return f"data:{media_type};base64,{base64.b64encode(raw).decode('ascii')}"


def _readme(request: BundleRequest, manifest: dict[str, Any]) -> str:
    lines = [
        f"GTFS Scorecard board reports prepared for {request.program_name}",
        f"Generated {manifest['generated_at']} (UTC). Bundle {request.bundle_id}.",
        "",
        "reports/<agency-id>-board-report.html: one self-contained file per agency.",
        "Open any of them in a browser and print to PDF; nothing needs a network.",
        "manifest.json: every agency id that was requested, and what happened to it.",
        "",
        f"{manifest['included']} of {manifest['requested']} requested agencies are included.",
    ]
    skipped = [a for a in manifest["agencies"] if a["status"] != STATUS_INCLUDED]
    if skipped:
        lines.append("Not included:")
        lines.extend(f"  {a['id']}: {a['detail']}" for a in skipped)
    lines += [
        "",
        "Every number comes from the agency's published scorecard at",
        "https://gtfsscorecard.org/agency/<id>/. The generator computes nothing new,",
        "and the free report for one agency is the same document. Sponsorship or",
        "purchase buys no influence over grades, methodology, or listing.",
        "",
    ]
    return "\n".join(lines)


def build_bundle(
    request: BundleRequest,
    out_zip: Path,
    *,
    now: dt.datetime | None = None,
    fetch_logo: FetchLogo | None = None,
    workdir: Path | None = None,
) -> dict[str, Any]:
    """Render every current agency's branded report and zip them with a manifest.

    Returns the manifest (also written inside the archive). Raises BundleError
    only for a request-level problem (an unusable logo); a single agency with
    no published scorecard is recorded in the manifest, never raised.
    """
    generated_at = (now or dt.datetime.now(dt.UTC)).replace(microsecond=0)
    brand = Brand(
        name=request.program_name,
        logo_data_uri=resolve_logo(request.logo, fetch_logo),
        accent=request.accent,
    )
    statuses = classify(request.agency_ids)
    work = workdir or out_zip.parent / f".{request.bundle_id}.work"
    reports_dir = work / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for agency_id in request.agency_ids:
        status = statuses[agency_id]
        if status != STATUS_CURRENT:
            rows.append({"id": agency_id, "status": status, "detail": _STATUS_DETAIL[status]})
            continue
        target = reports_dir / f"{agency_id}-board-report.html"
        try:
            generate_report(agency_id, brand=brand, out=target, now=generated_at)
        except ReportError:
            rows.append(
                {
                    "id": agency_id,
                    "status": STATUS_NOT_PUBLISHED,
                    "detail": _STATUS_DETAIL[STATUS_NOT_PUBLISHED],
                }
            )
            continue
        rows.append(
            {
                "id": agency_id,
                "status": STATUS_INCLUDED,
                "detail": "",
                "file": f"reports/{target.name}",
            }
        )

    manifest: dict[str, Any] = {
        "schema_version": "1",
        "bundle_id": request.bundle_id,
        "program_name": request.program_name,
        "cadence": request.cadence,
        "generated_at": generated_at.isoformat(),
        "requested": len(rows),
        "included": sum(1 for r in rows if r["status"] == STATUS_INCLUDED),
        "agencies": rows,
    }

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("README.txt", _readme(request, manifest))
        archive.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        for row in rows:
            if row["status"] == STATUS_INCLUDED:
                archive.write(reports_dir / Path(str(row["file"])).name, row["file"])
    return manifest


# ---------------------------------------------------------------------------
# Delivery
# ---------------------------------------------------------------------------


def delivery_email(
    request: BundleRequest,
    manifest: Mapping[str, Any],
    download_url: str,
    expires_on: str,
) -> Email:
    """The plain-text email that carries the download link.

    Says what was included and, per id, what was not. The link is a
    capability that expires; the date is stated so nobody discovers that by
    clicking a dead link.
    """
    included = int(manifest["included"])
    requested = int(manifest["requested"])
    lines = [
        f"Your GTFS Scorecard board reports for {request.program_name} are ready.",
        "",
        f"Download (valid until {expires_on}):",
        f"  {download_url}",
        "",
        f"{included} of {requested} requested agencies are included, one self-contained",
        "HTML file each. Open any of them in a browser and print to PDF.",
    ]
    skipped = [a for a in manifest["agencies"] if a["status"] != STATUS_INCLUDED]
    if skipped:
        lines += ["", "Not included:"]
        lines += [f"  {a['id']}: {a['detail']}" for a in skipped]
    if request.cadence == "monthly":
        lines += [
            "",
            "This bundle refreshes monthly. Each refresh arrives at this address with a",
            "new link; manage or cancel the subscription from the receipt Stripe sent you.",
        ]
    lines += [
        "",
        "Every number comes from the agency's published scorecard. The generator",
        "computes nothing new, and the free report for one agency is the same",
        "document. Purchase buys no influence over grades, methodology, or listing.",
        "",
        "Questions or a wrong id: reply to this email.",
        "",
    ]
    return Email(
        to=request.deliver_to,
        subject=f"Board reports for {request.program_name}: {included} of {requested} ready",
        body="\n".join(lines),
    )


def expires_on(generated_at: dt.datetime, days: int = DOWNLOAD_DAYS) -> str:
    """The calendar date the download link stops working, in UTC."""
    return (generated_at + dt.timedelta(days=days)).date().isoformat()
