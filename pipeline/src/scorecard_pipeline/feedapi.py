"""Ingest from the Mobility Feed API (api.mobilitydatabase.org).

The catalog CSV (mobilitydb.py) lists feeds. The newer Feed API goes further: for
each feed it records the latest dataset MobilityData fetched, its content hash,
and a validation report run with a named gtfs-validator version. When their hash
and validator version match what we would compute, their report is our report,
so we can skip the most expensive step in a score, the Java validator run, and
reuse MobilityData's result instead. That is the cost lever this module adds on
top of the sha-keyed validator cache.

Reuse is guarded, never assumed. The bytes must match (same sha256) and the
validator version must match, or we re-validate locally. A mismatch on either is
a silent fall-through to the normal path, so a feed is never scored against a
report for different bytes. The API needs a bearer token (an access token minted
from a refresh token); without one, this module does nothing and the pipeline
runs the validator as before.

Pure parsing and the reuse decision are unit-tested against fixture JSON; the
network calls are thin and token-gated.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .identity import normalized_mdb_id
from .net import safe_get
from .validate import ValidationReport, parse_report_data

log = logging.getLogger(__name__)

API_BASE = "https://api.mobilitydatabase.org/v1"


@dataclass(frozen=True)
class ApiValidation:
    """A dataset's validation summary as the Feed API reports it."""

    validator_version: str
    total_error: int
    total_warning: int
    total_info: int
    url_json: str = ""  # link to the full report.json (the validator's own schema)
    url_html: str = ""


@dataclass(frozen=True)
class ApiDataset:
    """The latest dataset the Mobility Feed API holds for a feed."""

    dataset_id: str
    feed_id: str
    hosted_url: str  # MobilityData's hosted copy of the zip (GCS)
    downloaded_at: str
    sha256: str  # the dataset's content hash, for matching against our fetch
    validation: ApiValidation | None = None


@dataclass(frozen=True)
class ApiFeed:
    """A feed record from the Feed API, narrowed to fields we use."""

    feed_id: str
    provider: str
    producer_url: str  # the agency's own GTFS download URL
    data_type: str
    status: str = ""
    country: str = ""
    subdivision: str = ""


def feed_id_for(mdb_id: str) -> str:
    """The Feed API id for a catalog mdb id. The API ids are ``mdb-<n>``; a value
    already prefixed (or a non-numeric id) is passed through unchanged."""
    return normalized_mdb_id(mdb_id.strip())


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def parse_validation(data: dict[str, Any] | None) -> ApiValidation | None:
    """Parse a dataset's ``validation_report`` block, or None when absent."""
    if not data:
        return None
    return ApiValidation(
        validator_version=str(data.get("validator_version", "unknown")),
        total_error=_int(data.get("total_error")),
        total_warning=_int(data.get("total_warning")),
        total_info=_int(data.get("total_info")),
        url_json=str(data.get("url_json", "") or ""),
        url_html=str(data.get("url_html", "") or ""),
    )


def parse_dataset(data: dict[str, Any]) -> ApiDataset:
    """Parse a Feed API dataset object (the ``/datasets/.../latest`` shape)."""
    hash_value = data.get("hash") or data.get("sha256") or ""
    return ApiDataset(
        dataset_id=str(data.get("id", "")),
        feed_id=str(data.get("feed_id", "")),
        hosted_url=str(data.get("hosted_url", "") or ""),
        downloaded_at=str(data.get("downloaded_at", "") or ""),
        sha256=str(hash_value),
        validation=parse_validation(data.get("validation_report")),
    )


def parse_feeds(data: list[dict[str, Any]]) -> list[ApiFeed]:
    """Parse a Feed API feed list (the ``/feeds`` shape)."""
    feeds: list[ApiFeed] = []
    for row in data:
        source = row.get("source_info") or {}
        location = (row.get("locations") or [{}])[0]
        feeds.append(
            ApiFeed(
                feed_id=str(row.get("id", "")),
                provider=str(row.get("provider", "") or ""),
                producer_url=str(source.get("producer_url", "") or ""),
                data_type=str(row.get("data_type", "") or ""),
                status=str(row.get("status", "") or ""),
                country=str(location.get("country_code", "") or ""),
                subdivision=str(location.get("subdivision_name", "") or ""),
            )
        )
    return feeds


def reuse_reason(dataset: ApiDataset, sha256: str, validator_version: str) -> str | None:
    """Why MobilityData's report cannot be reused, or None when it can.

    Returns a short reason string for the mismatch (different bytes, a different
    validator version, or no usable report link), so the caller can log why it
    fell back to a local run. None means every guard passed and the report at
    ``dataset.validation.url_json`` is safe to reuse for these bytes.
    """
    if dataset.validation is None:
        return "no validation report"
    if not dataset.validation.url_json:
        return "no report link"
    if not dataset.sha256 or dataset.sha256.lower() != sha256.lower():
        return "feed bytes differ from MobilityData's dataset"
    if dataset.validation.validator_version != validator_version:
        return (
            f"validator version differs ({dataset.validation.validator_version} "
            f"vs {validator_version})"
        )
    return None


# --- network (token-gated) ----------------------------------------------------


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def fetch_latest_dataset(feed_id: str, token: str) -> ApiDataset:
    """Fetch the latest dataset record for a feed from the Feed API."""
    import json

    url = f"{API_BASE}/gtfs_feeds/{feed_id}/datasets/latest"
    body = safe_get(url, headers=_auth_headers(token), timeout=60)
    return parse_dataset(json.loads(body.decode("utf-8")))


def fetch_report_json(url: str, token: str | None = None) -> dict[str, Any]:
    """Fetch a validator report.json by its URL (the dataset's ``url_json``).

    The report links are typically public GCS objects, so a token is optional;
    it is sent when present in case the link is gated.
    """
    import json

    headers = _auth_headers(token) if token else None
    body = safe_get(url, headers=headers, timeout=120, max_bytes=64 * 1024 * 1024)
    data = json.loads(body.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError("report.json was not a JSON object")
    return data


def report_from_api(
    dataset: ApiDataset,
    sha256: str,
    validator_version: str,
    *,
    fetch_report: Callable[[str], dict[str, Any]],
) -> ValidationReport | None:
    """MobilityData's report for a dataset, as our normalized model, when reuse is
    safe. ``fetch_report`` is injected so the guard logic is testable without the
    network; production passes a closure over :func:`fetch_report_json`. Returns
    None (and logs the reason) on any mismatch or fetch error, so the caller
    falls back to a local validator run.
    """
    reason = reuse_reason(dataset, sha256, validator_version)
    if reason is not None:
        log.info("feedapi: not reusing MobilityData report (%s)", reason)
        return None
    if dataset.validation is None:  # reuse_reason guarantees this; explicit so -O never skips it
        raise AssertionError("dataset.validation is None despite reuse_reason() passing")
    try:
        data = fetch_report(dataset.validation.url_json)
    except Exception as exc:
        log.warning("feedapi: report fetch failed, validating locally (%s)", exc)
        return None
    return parse_report_data(data)


def try_cached_report(
    mdb_id: str, sha256: str, validator_version: str, token: str
) -> ValidationReport | None:
    """Best-effort: MobilityData's report for an agency's feed, or None.

    The whole path is wrapped so any network or parsing failure falls through to
    the normal validator run. Used by the pipeline when an agency pins an mdb id
    and a Feed API token is configured.
    """
    feed_id = feed_id_for(mdb_id)
    if not feed_id or not token:
        return None
    try:
        dataset = fetch_latest_dataset(feed_id, token)
    except Exception as exc:
        log.warning("feedapi: dataset lookup failed for %s (%s)", feed_id, exc)
        return None
    return report_from_api(
        dataset,
        sha256,
        validator_version,
        fetch_report=lambda url: fetch_report_json(url, token),
    )
