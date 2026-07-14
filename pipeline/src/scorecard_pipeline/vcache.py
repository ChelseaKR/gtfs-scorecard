"""Validator-result cache keyed by feed content hash.

The MobilityData Java validator is the most expensive step in a score, and the
daily run re-validates every feed even though most feeds are byte-identical to
the day before. This caches the normalized validator report in the private
pipeline cache, keyed by the feed's sha256, validator version, and validator
country.
A re-score whose bytes, version, and country all match the cache reuses the
report and skips the Java run entirely; anything else re-validates and refreshes
the cache.

The local cache lives at data/cache/validator/<id>.json, outside the published
data/artifacts tree and covered by the repository's data/cache ignore rule. One
file per agency is overwritten when the feed changes, so the cache stays
bounded and cannot become a public scorecard artifact.

Optional S3 tier. Production CI keeps the durable cache under the private
``cache/validator/`` prefix when ``VALIDATOR_CACHE_BUCKET`` (or
``ARTIFACTS_BUCKET``) is set: the ignored local file stays the fast first tier,
S3 is the durable second tier, and an S3 hit writes through locally. The S3
path is best-effort by design: boto3 is imported lazily and every S3 error is
swallowed, so a missing dependency, missing credentials, or a transient
failure never fails a score; it just falls back to running the validator. With
no bucket set (local development and forks), the cache remains local and
private to that checkout.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from .config import cache_dir
from .location import normalize_country_code
from .validate import NoticeGroup, ValidationReport

log = logging.getLogger(__name__)


def _report_to_json(report: ValidationReport) -> dict[str, Any]:
    return {
        "validator_version": report.validator_version,
        "notices": [
            {
                "code": g.code,
                "severity": g.severity,
                "total": g.total,
                "sample_notices": g.sample_notices,
            }
            for g in report.notices
        ],
    }


def _report_from_json(data: dict[str, Any]) -> ValidationReport:
    notices = [
        NoticeGroup(
            code=str(n.get("code", "unknown")),
            severity=str(n.get("severity", "INFO")),
            total=int(n.get("total", 0)),
            sample_notices=list(n.get("sample_notices", [])),
        )
        for n in data.get("notices", [])
    ]
    return ValidationReport(
        validator_version=str(data.get("validator_version", "unknown")), notices=notices
    )


def cache_path(agency_id: str) -> Path:
    """Private local path for one agency's normalized validator result."""
    return cache_dir() / "validator" / f"{agency_id}.json"


def _cache_country(country_code: str) -> str:
    country = normalize_country_code(country_code)
    if not country:
        raise ValueError(
            "validator cache country must be an assigned ISO 3166-1 alpha-2 code, "
            f"got {country_code!r}"
        )
    return country


def _matching_report(
    data: Any,
    sha256: str,
    validator_version: str,
    country_code: str = "US",
) -> ValidationReport | None:
    """The stored report when feed bytes, version, and country all match.

    A mismatch on any input is a miss, so the caller re-validates. Cache files
    written before country-aware validation omitted ``country_code``; those are
    known U.S. runs and remain reusable only for U.S. requests.
    """
    if not isinstance(data, dict):
        return None
    stored_country = normalize_country_code(str(data.get("country_code") or "US"))
    if (
        data.get("sha256") != sha256
        or data.get("validator_version") != validator_version
        or stored_country != _cache_country(country_code)
    ):
        return None
    report = data.get("report")
    if not isinstance(report, dict):
        return None
    return _report_from_json(report)


def _write_local(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


# --- Optional S3 tier -------------------------------------------------------


def _cache_bucket() -> str | None:
    """Bucket for the durable cache tier, or None to stay file-only.

    ``VALIDATOR_CACHE_BUCKET`` lets the cache live in a different bucket than the
    public artifacts; absent that, it reuses ``ARTIFACTS_BUCKET`` under a private
    prefix so one variable turns both on together."""
    return os.environ.get("VALIDATOR_CACHE_BUCKET") or os.environ.get("ARTIFACTS_BUCKET") or None


def _s3_key(agency_id: str) -> str:
    # A prefix outside data/artifacts/ keeps the cache off the public CDN mirror
    # and away from the index/rollup walkers.
    return f"cache/validator/{agency_id}.json"


def _s3_client() -> Any:  # pragma: no cover - thin boto3 wrapper, faked in tests
    # Lazy: boto3 is an optional dependency, present only when caching to S3.
    import boto3  # type: ignore[import-not-found]

    return boto3.client("s3", region_name=os.environ.get("AWS_REGION") or "us-west-2")


def _s3_load(bucket: str, agency_id: str) -> dict[str, Any] | None:
    try:
        obj = _s3_client().get_object(Bucket=bucket, Key=_s3_key(agency_id))
        data = json.loads(obj["Body"].read())
        return data if isinstance(data, dict) else None
    except Exception as exc:
        log.debug("validator cache S3 read miss for %s: %s", agency_id, exc)
        return None


def _s3_store(bucket: str, agency_id: str, payload: dict[str, Any]) -> None:
    try:
        _s3_client().put_object(
            Bucket=bucket,
            Key=_s3_key(agency_id),
            Body=(json.dumps(payload, sort_keys=True) + "\n").encode(),
            ContentType="application/json",
        )
    except Exception as exc:
        log.warning("validator cache S3 write failed for %s: %s", agency_id, exc)


# --- Public API -------------------------------------------------------------


def load_cached(
    agency_id: str,
    sha256: str,
    validator_version: str,
    country_code: str = "US",
) -> ValidationReport | None:
    """The cached report when bytes, version, and country match, else None.

    Checks the local file first (fast, no network), then the S3 tier if a bucket
    is configured. An S3 hit is written through to the ignored local file so the
    rest of this run can reuse it without placing it in published artifacts."""
    country = _cache_country(country_code)
    path = cache_path(agency_id)
    try:
        local = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        local = None
    hit = _matching_report(local, sha256, validator_version, country)
    if hit is not None:
        return hit

    bucket = _cache_bucket()
    if bucket:
        remote = _s3_load(bucket, agency_id)
        hit = _matching_report(remote, sha256, validator_version, country)
        if hit is not None and isinstance(remote, dict):
            _write_local(path, remote)
            return hit
    return None


def store_cached(
    agency_id: str,
    sha256: str,
    validator_version: str,
    report: ValidationReport,
    country_code: str = "US",
) -> Path:
    """Write a country-bound report locally and, if configured, to S3."""
    payload = {
        "sha256": sha256,
        "validator_version": validator_version,
        "country_code": _cache_country(country_code),
        "report": _report_to_json(report),
    }
    path = cache_path(agency_id)
    _write_local(path, payload)

    bucket = _cache_bucket()
    if bucket:
        _s3_store(bucket, agency_id, payload)
    return path
