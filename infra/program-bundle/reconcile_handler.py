"""Scheduled reconciler for paid orders nobody is watching (docs/program-plan.md).

EventBridge invokes this daily. It walks the bundles table once and asks the
only question the rest of this system cannot ask itself: *is there money here
that bought nothing?*

Three shapes, and each is a real path a paid order can take to silence:

``undelivered``
    A capability row whose archive is not in S3 after ``STALE_HOURS``. The
    setup route writes that row before it dispatches report-bundle.yml, so
    this covers both a dispatch that never started and a fulfilment run that
    started and died. It is the broadest of the three and the one that
    catches failures this module has not thought of.

``never_started``
    A ``session#`` claim still holding ``dispatched: False``. The buyer paid,
    the handler claimed the checkout, and GitHub never accepted the dispatch.
    The claim is deliberately left unfinished so the buyer can retry and
    resume the same bundle (setup_handler); this is what notices when they
    never come back. A claim written before that flag existed says nothing
    either way and is not reported on a guess -- see ``_never_started``.

``abandoned_checkout``
    A ``checkout#`` row the webhook wrote with no matching ``session#`` row.
    The buyer paid and closed the tab before filling in the setup form.
    Nothing is broken and nobody is coming: they need an email from a person.

Findings are reported by opening one GitHub issue and keeping it up to date.
Nobody watches a dashboard here, and the operator's own mail domain has no MX
record, so an emailed alert would have been delivered nowhere; the issue
tracker is a channel that is demonstrably read.

**The issue carries counts and nothing else.** This repository is public, so
its issues are world-readable, and every identifying field this module holds
is either a credential or personal data: a bundle id IS the download
capability, and `deliver_to`, `program_name` and the agency list all describe
a paying customer. ``issue_body`` is therefore given the counts alone and
never sees a finding, so it cannot leak one by oversight or by a later edit.
The detail stays in CloudWatch, which is private to the account.

Two refusals, because a reconciler that cannot fail is worse than none:

* A row with no readable timestamp is reported, not skipped. "I could not
  tell how old this is" must not read as "this is fine".
* An S3 answer that is neither "here" nor "404" is reported as ``unreadable``
  and makes the run raise. A reconciler that treats an outage as an all-clear
  is exactly the absence-rendered-as-a-value bug it exists to catch.

Dry run: ``DRY_RUN=1`` in the environment, or ``{"dry_run": true}`` as the
invoke payload, scans and logs and sends nothing.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from typing import Any

from common import (
    DOWNLOAD_DAYS,
    UpstreamError,
    github_request,
    now_iso,
    payments_enabled,
    table,
)

# How long an order may sit before it counts as undelivered. A bundle of a
# hundred agencies renders well inside report-bundle.yml's own 30-minute
# bound, so six hours is several failed-and-retried builds, not a tight race.
STALE_HOURS = 6
# The capability row's TTL. A row past this is about to be deleted by
# DynamoDB and the evidence with it, so the digest says so out loud.
EXPIRY_DAYS = DOWNLOAD_DAYS

_SESSION_PREFIX = "session#"
_CHECKOUT_PREFIX = "checkout#"
_ARTIFACT_PRESENT = "present"
_ARTIFACT_MISSING = "missing"
_ARTIFACT_UNREADABLE = "unreadable"


def _age_hours(stamp: str, *, now: dt.datetime) -> float | None:
    """Hours since an ISO-8601 timestamp, or None when it cannot be read.

    None is a finding, never a pass: every caller below treats an unreadable
    timestamp as old enough to report.
    """
    if not stamp:
        return None
    try:
        parsed = dt.datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return (now - parsed).total_seconds() / 3600


def _is_stale(stamp: str, *, now: dt.datetime, stale_hours: float) -> bool:
    age = _age_hours(stamp, now=now)
    return age is None or age >= stale_hours


def artifact_state(s3: Any, bucket: str, bundle_id: str) -> str:
    """Whether this bundle's archive is in the bucket.

    Distinguishes "S3 says no such key" from "S3 did not answer". The second
    is not evidence of an undelivered order and is not evidence of a
    delivered one either, so it gets its own value and the caller refuses.
    """
    try:
        s3.head_object(Bucket=bucket, Key=f"program-bundles/{bundle_id}/bundle.zip")
    except Exception as err:  # botocore's ClientError, read by code not by type
        response = getattr(err, "response", None)
        code = ""
        if isinstance(response, dict):
            code = str((response.get("Error") or {}).get("Code") or "")
            code = code or str((response.get("ResponseMetadata") or {}).get("HTTPStatusCode") or "")
        return (
            _ARTIFACT_MISSING if code in ("404", "NoSuchKey", "NotFound") else _ARTIFACT_UNREADABLE
        )
    return _ARTIFACT_PRESENT


def _scan_all(bundles: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {}
    while True:
        page = bundles.scan(**kwargs)
        rows.extend(page.get("Items") or [])
        start = page.get("LastEvaluatedKey")
        if not start:
            return rows
        kwargs = {"ExclusiveStartKey": start}


def _never_started(row: dict[str, Any]) -> bool:
    """True only when the claim positively says no build was ever started.

    The setup handler records that fact as ``dispatched: False``, flipped to
    True once GitHub accepts the workflow_dispatch.

    A claim carrying neither answer is one written before the field existed,
    and it is not reported here. Absence of the flag is not evidence that the
    dispatch failed, and treating it as evidence would email the operator
    about every order placed before the flag shipped. Those orders are not
    lost to this job: if one really has no archive, the capability row finds
    it under ``undelivered``, which asks a question about S3 rather than
    about a field that was never written.
    """
    return row.get("dispatched") is False


def _session_finding(
    row: dict[str, Any],
    key: str,
    created: dict[str, str],
    *,
    now: dt.datetime,
    stale_hours: float,
) -> dict[str, Any] | None:
    """A claim that never became a build."""
    if not _never_started(row):
        return None
    bundle_id = str(row.get("consumed_by") or "")
    # The claim itself carries no timestamp, so its age is the age of the
    # capability row it named -- written in the same invocation, moments
    # before the dispatch that failed. Without that, a claim caught mid-flight
    # by the daily scan would be reported as an abandoned order.
    claimed = str(row.get("claimed_at") or "") or created.get(bundle_id, "")
    if not _is_stale(claimed, now=now, stale_hours=stale_hours):
        return None
    return {
        "kind": "never_started",
        "key": key,
        "bundle_id": bundle_id,
        "plan": str(row.get("plan") or ""),
        "age_hours": _age_hours(claimed, now=now),
        "action": "The checkout was claimed and report-bundle.yml never started. "
        "Dispatch it by hand with this bundle id, or tell the buyer to submit the "
        "setup form again -- the claim is still open and a retry resumes this same "
        "order.",
    }


def _checkout_finding(
    row: dict[str, Any], key: str, keys: set[str], *, now: dt.datetime, stale_hours: float
) -> dict[str, Any] | None:
    """A payment that never reached the setup form."""
    if f"{_SESSION_PREFIX}{key[len(_CHECKOUT_PREFIX) :]}" in keys:
        return None
    seen = str(row.get("seen_at") or "")
    if not _is_stale(seen, now=now, stale_hours=stale_hours):
        return None
    return {
        "kind": "abandoned_checkout",
        "key": key,
        "email": str(row.get("email") or ""),
        "plan": str(row.get("plan") or ""),
        "age_hours": _age_hours(seen, now=now),
        "action": "Paid, then left before the setup form. Nothing is broken and "
        "nothing will happen on its own: send them the setup link with their "
        "session id.",
    }


def _capability_finding(
    row: dict[str, Any],
    key: str,
    s3: Any,
    bucket: str,
    *,
    now: dt.datetime,
    stale_hours: float,
) -> dict[str, Any] | None:
    """An order with no archive behind its download link."""
    created = str(row.get("created_at") or "")
    if not _is_stale(created, now=now, stale_hours=stale_hours):
        return None
    state = artifact_state(s3, bucket, key)
    if state == _ARTIFACT_PRESENT:
        return None
    age = _age_hours(created, now=now)
    if state == _ARTIFACT_MISSING:
        action = (
            f"No archive at program-bundles/{key}/bundle.zip. Re-dispatch "
            "report-bundle.yml with this bundle id; the download link the buyer "
            "holds already points at that key."
        )
        if age is not None and age >= (EXPIRY_DAYS - 1) * 24:
            action += f" This row is within a day of its {EXPIRY_DAYS}-day TTL."
    else:
        action = (
            "S3 would not say whether this archive exists, so this run cannot "
            "vouch for this order either way. Check the bucket."
        )
    return {
        "kind": "undelivered" if state == _ARTIFACT_MISSING else "unreadable",
        "key": key,
        "deliver_to": str(row.get("deliver_to") or ""),
        "program_name": str(row.get("program_name") or ""),
        "source": str(row.get("source") or ""),
        "age_hours": age,
        "action": action,
    }


def reconcile(
    *,
    bundles: Any,
    s3: Any,
    bucket: str,
    now: dt.datetime | None = None,
    stale_hours: float = STALE_HOURS,
) -> dict[str, Any]:
    """Walk the table and return every order that bought nothing.

    Returns ``{"scanned": int, "findings": [...]}``; each finding carries the
    kind, the key, the age in hours (None when unreadable) and a sentence
    saying what to do about it.
    """
    current = now or dt.datetime.now(dt.UTC)
    rows = _scan_all(bundles)
    keys = {str(row.get("bundle_id") or "") for row in rows}
    # A `session#` claim carries no timestamp of its own, so it borrows the
    # one on the capability row it named.
    created = {
        str(row.get("bundle_id") or ""): str(row.get("created_at") or "")
        for row in rows
        if "#" not in str(row.get("bundle_id") or "")
    }
    findings: list[dict[str, Any]] = []

    for row in rows:
        key = str(row.get("bundle_id") or "")
        if key.startswith(_SESSION_PREFIX):
            found = _session_finding(row, key, created, now=current, stale_hours=stale_hours)
        elif key.startswith(_CHECKOUT_PREFIX):
            found = _checkout_finding(row, key, keys, now=current, stale_hours=stale_hours)
        else:
            # Anything else is a capability row: one download link, one order.
            found = _capability_finding(row, key, s3, bucket, now=current, stale_hours=stale_hours)
        if found is not None:
            findings.append(found)

    return {"scanned": len(rows), "findings": findings}


# The issue is found again by this label, and confirmed by the marker in its
# body. The label is the cheap server-side filter; the marker is what proves
# the issue we found is the one this Lambda wrote, and not one somebody else
# happened to label.
ISSUE_LABEL = "program-bundle-reconciler"
ISSUE_MARKER = "<!-- gtfs-scorecard:program-bundle-reconciler -->"
LOG_GROUP = "/aws/lambda/gtfs-scorecard-program-bundle-reconcile"
# Every kind the walk above can produce, so a kind that drops to zero is
# printed as zero rather than vanishing from the report.
KINDS = ("undelivered", "never_started", "abandoned_checkout", "unreadable")


def counts_by_kind(findings: list[dict[str, Any]]) -> dict[str, int]:
    """How many of each kind. The only thing that reaches a public issue."""
    return {kind: sum(1 for f in findings if f.get("kind") == kind) for kind in KINDS}


def issue_title(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    return f"{total} program order{'' if total == 1 else 's'} need attention"


def issue_body(counts: dict[str, int]) -> str:
    """The whole public report.

    Takes counts, not findings. That is deliberate and is the only reason
    this function is safe to point at a public repository: there is no
    identifying value in scope for it to print, so no future edit can reach
    one. Everything a responder needs beyond these numbers is in CloudWatch,
    which is private.
    """
    lines = [ISSUE_MARKER, ""]
    lines += [f"{kind:<20}{counts.get(kind, 0)}" for kind in KINDS]
    lines += [
        "",
        f"Details: CloudWatch {LOG_GROUP}",
        "",
        "Counts only. This repository is public, and every identifying field "
        "behind these numbers is a download capability or a customer's own "
        "details, so none of it is printed here.",
    ]
    return "\n".join(lines) + "\n"


def _standing_issue() -> dict[str, Any] | None:
    """The open issue this Lambda maintains, or None.

    Filtered server-side by label, then confirmed by the marker: a label
    somebody else applied to their own issue must not make this Lambda
    overwrite it.
    """
    found = github_request("GET", f"/issues?state=open&labels={ISSUE_LABEL}&per_page=20")
    if not isinstance(found, list):
        return None
    for issue in found:
        if isinstance(issue, dict) and ISSUE_MARKER in str(issue.get("body") or ""):
            return issue
    return None


def report_findings(findings: list[dict[str, Any]]) -> str:
    """Open or update the standing issue. Returns what it did.

    Idempotent by content, not by date: a daily schedule over a standing
    problem must not open a new issue every morning, and must not edit the
    same issue every morning either, because an issue that churns daily stops
    being read. So the body is compared and written only when it differs.

    Nothing is ever closed. A human decides when a finding is handled; a job
    that closes its own report can close one somebody was still working on.
    """
    counts = counts_by_kind(findings)
    body = issue_body(counts)
    title = issue_title(counts)
    issue = _standing_issue()
    if issue is None:
        github_request("POST", "/issues", {"title": title, "body": body, "labels": [ISSUE_LABEL]})
        return "opened"
    number = int(issue["number"])
    if str(issue.get("body") or "") == body and str(issue.get("title") or "") == title:
        return "unchanged"
    github_request("PATCH", f"/issues/{number}", {"title": title, "body": body})
    return "updated"


def handler(event: dict[str, Any], context: Any = None) -> dict[str, Any]:
    """EventBridge entrypoint. The scheduled event carries nothing the
    handler reads; a hand invoke may pass ``{"dry_run": true}``."""
    dry_run = os.environ.get("DRY_RUN", "0") == "1" or (
        isinstance(event, dict) and event.get("dry_run") is True
    )
    if not payments_enabled():
        print(json.dumps({"reconcile": "skipped: PAYMENTS_ENABLED is not 1", "at": now_iso()}))
        return {"ok": True, "payments_enabled": False, "dry_run": dry_run}

    import boto3

    region = os.environ.get("AWS_REGION", "us-west-2")
    bucket = os.environ["ARTIFACTS_BUCKET"]
    result = reconcile(
        bundles=table("BUNDLES_TABLE"),
        s3=boto3.client("s3", region_name=region),
        bucket=bucket,
    )
    findings = result["findings"]
    print(json.dumps({"reconcile": result, "dry_run": dry_run, "at": now_iso()}))

    reported = "dry_run" if dry_run else "nothing to report"
    if findings and not dry_run:
        # Raised, not swallowed. If the report cannot be filed then this run
        # found paid orders and told nobody, which is the failure this whole
        # module exists to prevent; a green invocation would be a lie.
        #
        # The token was verified on 2026-09-12 to carry `Issues: Read and
        # write` on this repository, so a 403 here means it was narrowed or
        # rotated since. The message names that rather than making somebody
        # re-derive it. A 422 is more likely the missing label.
        try:
            reported = report_findings(findings)
        except UpstreamError as err:
            raise RuntimeError(
                f"{len(findings)} program orders need attention and the report could not "
                f"be filed ({err}). A 403 means the dispatch token no longer carries the "
                "fine-grained repository permission 'Issues: Read and write' on this repo; "
                f"a 422 usually means the '{ISSUE_LABEL}' label does not exist yet."
            ) from err

    # An S3 read that did not answer leaves this run unable to vouch for those
    # orders. Raising is what puts that in front of somebody; returning a
    # count nobody reads is the failure mode this module is about. It happens
    # after the report so the orders it COULD read are still filed.
    unreadable = [f for f in findings if f["kind"] == "unreadable"]
    if unreadable:
        raise RuntimeError(
            f"{len(unreadable)} bundle archives could not be read from s3://{bucket}; "
            "this run cannot say whether those orders were delivered."
        )
    return {
        "ok": True,
        "payments_enabled": True,
        "scanned": result["scanned"],
        "findings": len(findings),
        "reported": reported,
        "dry_run": dry_run,
    }
