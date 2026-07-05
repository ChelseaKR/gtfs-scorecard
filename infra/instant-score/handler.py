"""Serverless handler for instant on-demand scoring: score any GTFS URL now.

A container-image Lambda behind API Gateway (this account blocks public
Function URLs; see infra/alerts/main.tf). Three routes:

  POST /score        {url, name?}  -> validate, rate-limit, kick off scoring
                      asynchronously, return {job_id, status: "pending"}.
  GET  /score/{id}    -> the job's current status: pending, done (with a
                      shareable result URL), or error.
  (async, self-invoked, no HTTP route) -> run the actual scoring: fetch the
                      feed, run the validator, build the artifact, write it to
                      the artifacts bucket under scratch/<job_id>/, and record
                      the outcome.

Why async: API Gateway hard-caps a proxied Lambda integration at 30 seconds,
but scoring a real feed (fetch + the Java validator + the scoring pipeline)
can run well past that for a larger agency. POST returns in well under a
second; the actual work happens in a second invocation of this same function,
started with InvocationType="Event" (fire-and-forget), which can run for the
function's full configured timeout. The client polls GET /score/{id}.

The scoring itself reuses scorecard_pipeline.cli.run_adhoc unchanged: this
handler is a thin wrapper, the same principle infra/compute/worker.py uses for
the daily fan-out ("a packaging change, not a rewrite").

Environment:
  JOBS_TABLE           DynamoDB table for job status (this module's own table)
  RATELIMIT_TABLE      DynamoDB table for per-IP rate limiting (shared with
                       infra/alerts; a distinct key prefix gives this endpoint
                       its own quota rather than sharing alerts' budget)
  ARTIFACTS_BUCKET     S3 bucket scored results are written to, under scratch/
  RESULT_BASE_URL      Public base URL results are served from (the artifacts
                       CDN), used to build the shareable result_url
  ALLOW_ORIGIN         CORS origin of the web form (never "*")
  FUNCTION_NAME        This Lambda's own name, for the self-invoke
  AWS_REGION           provided by Lambda
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import Any

# Restricted to what a real published GTFS URL looks like; deep safety
# validation (SSRF, private hosts) happens inside fetch_static via
# net.validate_public_url when the feed is actually fetched, not here.
_URL_RE = re.compile(r"^https?://.+", re.IGNORECASE)
_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,32}$")
MAX_NAME_LEN = 200

# A stricter quota than the alerts endpoint: scoring runs a JVM over a
# downloaded feed and costs real compute per request, unlike sending an email.
IP_LIMIT = 5
IP_WINDOW = 3600  # seconds

# How long a job record (and its scratch result) is kept before it expires,
# matching the "shareable URL that expires in 30 days unless claimed" idea
# from the growth-plans funnel design (06-beyond-static-unlocks.md Tier 1).
JOB_TTL_SECONDS = 30 * 24 * 3600

STATUS_PENDING = "pending"
STATUS_DONE = "done"
STATUS_ERROR = "error"


class BadRequest(ValueError):
    """Input the form should never send; surfaced as a 400."""


def validate_score_request(body: dict[str, Any]) -> dict[str, str]:
    """Normalize and validate a POST /score payload. Pure; raises BadRequest."""
    url = body.get("url")
    if not isinstance(url, str) or not _URL_RE.match(url.strip()):
        raise BadRequest("a valid http(s) GTFS Schedule URL is required")
    name = body.get("name")
    if name is not None and not isinstance(name, str):
        raise BadRequest("name must be a string if present")
    out = {"url": url.strip()}
    if name:
        out["name"] = name.strip()[:MAX_NAME_LEN]
    return out


def _cors_headers() -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": os.environ.get("ALLOW_ORIGIN", "https://gtfsscorecard.org"),
        "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _json(status: int, body: dict[str, Any]) -> dict[str, Any]:
    return {"statusCode": status, "headers": _cors_headers(), "body": json.dumps(body)}


def _jobs_table() -> Any:
    import boto3  # noqa: PLC0415 - lazy; provided by the Lambda runtime

    region = os.environ.get("AWS_REGION", "us-west-2")
    return boto3.resource("dynamodb", region_name=region).Table(os.environ["JOBS_TABLE"])


def _ip_rate_limited(event: dict[str, Any]) -> bool:
    """Fixed-window per-IP counter in the shared rate-limit table (TTL
    auto-expires each window), prefixed so this endpoint has its own quota
    separate from the alerts endpoint's budget."""
    ip = event.get("requestContext", {}).get("http", {}).get("sourceIp")
    if not ip:
        return False
    import boto3  # noqa: PLC0415 - lazy; provided by the Lambda runtime

    region = os.environ.get("AWS_REGION", "us-west-2")
    table = boto3.resource("dynamodb", region_name=region).Table(os.environ["RATELIMIT_TABLE"])
    now = int(time.time())
    bucket = now // IP_WINDOW
    resp = table.update_item(
        Key={"key": f"score#{ip}#{bucket}"},
        UpdateExpression="ADD #c :one SET expires_at = if_not_exists(expires_at, :exp)",
        ExpressionAttributeNames={"#c": "count"},
        ExpressionAttributeValues={":one": 1, ":exp": (bucket + 1) * IP_WINDOW + 60},
        ReturnValues="ALL_NEW",
    )
    return int(resp["Attributes"]["count"]) > IP_LIMIT


def _start_scoring(job_id: str, url: str, name: str) -> None:
    """Fire off the actual scoring work asynchronously and record the job as
    pending. Returns immediately; the async invocation below does the work."""
    import boto3  # noqa: PLC0415 - lazy; provided by the Lambda runtime

    now = int(time.time())
    _jobs_table().put_item(
        Item={
            "job_id": job_id,
            "status": STATUS_PENDING,
            "url": url,
            "created_at": now,
            "expires_at": now + JOB_TTL_SECONDS,
        }
    )
    lambda_client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION", "us-west-2"))
    lambda_client.invoke(
        FunctionName=os.environ["FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps({"job_id": job_id, "url": url, "name": name}),
    )


def _handle_post(event: dict[str, Any]) -> dict[str, Any]:
    if _ip_rate_limited(event):
        return _json(429, {"error": "Too many requests. Try again in a bit."})
    try:
        payload = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _json(400, {"error": "invalid JSON"})
    try:
        req = validate_score_request(payload)
    except BadRequest as exc:
        return _json(400, {"error": str(exc)})

    job_id = secrets.token_urlsafe(9)
    _start_scoring(job_id, req["url"], req.get("name", ""))
    return _json(202, {"job_id": job_id, "status": STATUS_PENDING})


def _handle_get(event: dict[str, Any]) -> dict[str, Any]:
    path = event.get("requestContext", {}).get("http", {}).get("path", "")
    job_id = path.rsplit("/", 1)[-1]
    if not _JOB_ID_RE.match(job_id):
        return _json(400, {"error": "invalid job id"})
    row = _jobs_table().get_item(Key={"job_id": job_id}).get("Item")
    if not row:
        return _json(404, {"error": "unknown or expired job"})
    out: dict[str, Any] = {"job_id": job_id, "status": row["status"]}
    if row["status"] == STATUS_DONE:
        out["result_url"] = row.get("result_url", "")
        out["grade"] = row.get("grade", "")
    elif row["status"] == STATUS_ERROR:
        out["message"] = row.get("message", "Scoring failed.")
    return _json(200, out)


def _prepare_runtime() -> None:
    """Point the pipeline's writable paths at /tmp (the only writable
    filesystem in a Lambda execution environment) and seed the validator jar
    cache from the image so a cold start never depends on a network call to
    GitHub Releases to fetch it."""
    os.environ["SCORECARD_ROOT"] = "/tmp/scorecard"
    from scorecard_pipeline.config import cache_dir  # noqa: PLC0415 - after env is set
    from scorecard_pipeline.validate import VALIDATOR_VERSION

    baked = Path(os.environ.get("BAKED_VALIDATOR_JAR", "/opt/validator/gtfs-validator-cli.jar"))
    cache_dir().mkdir(parents=True, exist_ok=True)
    target = cache_dir() / f"gtfs-validator-{VALIDATOR_VERSION}-cli.jar"
    if baked.exists() and not target.exists():
        shutil.copyfile(baked, target)


def _run_scoring_job(job_id: str, url: str, name: str) -> None:
    """The async half: score the feed, publish the result, record the outcome.
    Never raises; every failure path writes an error job record so a poller
    always gets a terminal status rather than hanging forever."""
    _prepare_runtime()
    from scorecard_pipeline.cli import run_adhoc

    try:
        artifact = run_adhoc(url, name or None, dt.date.today())
    except Exception as exc:  # noqa: BLE001 - any failure becomes a job error, never a crash
        # Safe, generic message: the exception text can include a raw path or
        # subprocess output that should not reach an untrusted requester.
        _jobs_table().update_item(
            Key={"job_id": job_id},
            UpdateExpression="SET #s = :s, message = :m",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={
                ":s": STATUS_ERROR,
                ":m": f"Could not score this feed ({type(exc).__name__}). "
                "Check that the URL is a public GTFS Schedule zip.",
            },
        )
        return

    result_url = _publish_result(job_id, artifact)
    _jobs_table().update_item(
        Key={"job_id": job_id},
        UpdateExpression="SET #s = :s, result_url = :u, grade = :g",
        ExpressionAttributeNames={"#s": "status"},
        ExpressionAttributeValues={
            ":s": STATUS_DONE,
            ":u": result_url,
            ":g": artifact.get("overall", {}).get("grade", ""),
        },
    )


def _publish_result(job_id: str, artifact: dict[str, Any]) -> str:
    """Write the scored artifact to the artifacts bucket under scratch/<job_id>/
    and return its public URL — the shareable result link the funnel design
    calls for, served through the same CDN as every tracked agency's data."""
    import boto3  # noqa: PLC0415 - lazy; provided by the Lambda runtime

    key = f"scratch/{job_id}/latest.json"
    boto3.client("s3").put_object(
        Bucket=os.environ["ARTIFACTS_BUCKET"],
        Key=key,
        Body=json.dumps(artifact).encode("utf-8"),
        ContentType="application/json",
    )
    base = os.environ.get("RESULT_BASE_URL", "https://gtfsscorecard.org").rstrip("/")
    return f"{base}/{key}"


def handler(event: dict[str, Any], context: object) -> dict[str, Any] | None:
    """Entrypoint. Three shapes reach here: an API Gateway v2 HTTP event (POST
    or GET), an OPTIONS preflight, or this function's own async self-invoke
    payload (no requestContext, just {job_id, url, name})."""
    if "requestContext" not in event:
        # Async self-invoke: do the actual scoring. No HTTP response is sent
        # or expected (InvocationType="Event" discards the return value).
        _run_scoring_job(event["job_id"], event["url"], event.get("name", ""))
        return None

    ctx = event.get("requestContext", {}).get("http", {})
    method = ctx.get("method", "GET").upper()
    if method == "OPTIONS":
        return {"statusCode": 204, "headers": _cors_headers(), "body": ""}
    if method == "POST":
        return _handle_post(event)
    if method == "GET":
        return _handle_get(event)
    return _json(404, {"error": "not found"})
