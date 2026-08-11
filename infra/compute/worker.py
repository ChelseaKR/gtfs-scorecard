"""Worker: score one agency per SQS message and mirror its artifacts.

Year 2 of docs/roadmap.md. Each message names one agency; the worker runs the
existing pipeline for it and uploads just that agency's artifacts to the
artifacts bucket. The worker is a thin wrapper because the pipeline is already
a filesystem CLI (ADR 0001): moving from the Actions matrix to a queue is a
packaging change, not a rewrite.

The per-agency index/rollup rebuild is deliberately not done here (workers run
concurrently and must not race a shared index). A separate collect step rebuilds
the index after the queue drains, exactly as the sharded CI workflow does.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

import boto3

from scorecard_pipeline.agencies import load_agencies
from scorecard_pipeline.config import AGENCIES, artifacts_dir, utc_today

BUCKET = os.environ["ARTIFACTS_BUCKET"]
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def _score(agency_id: str) -> None:
    load_agencies()
    # The agency_id arrives from the SQS message; validate it before it reaches a
    # subprocess argument, and require it to be a registered agency.
    if not ID_PATTERN.match(agency_id) or agency_id not in AGENCIES:
        raise ValueError(f"unknown or invalid agency id: {agency_id!r}")
    # Use the CLI so the worker and the local/CI path run identical code.
    subprocess.run(
        # UTC, not the container's zone: this becomes the artifact's
        # snapshot_date, which the Actions matrix stamps in UTC.
        ["scorecard", "run", "--agency", agency_id, "--date", utc_today().isoformat()],
        check=True,
    )


def _upload(agency_id: str) -> None:
    s3 = boto3.client("s3")
    agency_dir = artifacts_dir() / agency_id
    for path in agency_dir.glob("*"):
        if path.is_file():
            key = f"data/artifacts/{agency_id}/{path.name}"
            content_type = "image/svg+xml" if path.suffix == ".svg" else "application/json"
            s3.upload_file(
                str(path), BUCKET, key, ExtraArgs={"ContentType": content_type}
            )


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    processed = []
    for record in event.get("Records", []):
        agency_id = json.loads(record["body"])["agency_id"]
        _score(agency_id)
        _upload(agency_id)
        processed.append(agency_id)
    return {"processed": processed}
