"""Publish one month's history tables as an AWS Data Exchange revision (ADR 0065).

The history tables (ADR 0063) are built once a month by ``history-export.yml``.
When the owner lists them on AWS Data Exchange, every month's build becomes one
new revision of one owned data set: the five files the zip carries, imported
from ``history/<YYYY-MM>/tables/`` in the private artifacts bucket, renamed to
their plain file names, and finalized. A finalized revision of a data set that
is in a published product reaches every active subscriber at once; that is the
whole delivery, and nothing here knows who the subscribers are.

What this module holds to:

- **One revision per month, never two.** A finalized revision whose comment
  names the month means the month is already published; the run says so and
  changes nothing, because a published revision cannot be edited, only
  revoked, and revoking is the owner's call. An unfinalized revision for the
  month is what an interrupted run leaves behind; it is deleted and built
  again from the start, so a half-imported revision is never finalized.
- **Finalize only what was checked.** The revision is finalized only after the
  import job completed and the revision holds exactly the five expected files.
- **Nothing is created outside the one data set.** The data set id is given;
  the role the workflow assumes (``infra/artifacts/marketplace.tf``) can act on
  that data set's revisions, its assets and import jobs, and nothing else.

Run from ``pipeline/`` in the workflow, with boto3 pulled in for the run:

    uv run --with boto3 python -m scorecard_pipeline.marketplace_revision \\
        --data-set-id <id> --bucket <bucket> --month 2026-11
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Final

from .history_export import (
    CHECKS_TABLE,
    DICTIONARY_FILENAME,
    FINDINGS_TABLE,
    LICENSE_FILENAME,
    PROVENANCE_FILENAME,
)

log = logging.getLogger(__name__)

#: The five files of one month's build, by the name a subscriber sees.
ASSET_NAMES: Final = (
    f"{CHECKS_TABLE}.parquet",
    f"{FINDINGS_TABLE}.parquet",
    DICTIONARY_FILENAME,
    PROVENANCE_FILENAME,
    LICENSE_FILENAME,
)
_MONTH: Final = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_DONE_STATES: Final = frozenset({"COMPLETED", "ERROR", "CANCELLED", "TIMED_OUT"})


class MarketplaceRevisionError(RuntimeError):
    """The month could not be published, and says why."""


@dataclass(frozen=True)
class Outcome:
    """What a run did: ``published`` or ``already_published``."""

    status: str
    revision_id: str


def revision_comment(month: str) -> str:
    """The comment that names a month's revision. It is how a re-run finds it."""
    return f"GTFS Scorecard history tables, build of {month}"


def tables_prefix(month: str) -> str:
    """Where the export job writes the unzipped tables for ``month``."""
    return f"history/{month}/tables/"


def asset_sources(bucket: str, month: str) -> list[dict[str, str]]:
    """The S3 objects one month's revision imports, in a fixed order."""
    prefix = tables_prefix(month)
    return [{"Bucket": bucket, "Key": f"{prefix}{name}"} for name in ASSET_NAMES]


def check_month(month: str) -> str:
    """``month`` if it is YYYY-MM, else refuse."""
    if not _MONTH.match(month):
        raise MarketplaceRevisionError(f"month must be YYYY-MM, not {month!r}")
    return month


def _pages(
    call: Callable[..., dict[str, Any]], key: str, **kwargs: Any
) -> Iterator[dict[str, Any]]:
    """Every item of a NextToken-paged Data Exchange list call."""
    token: str | None = None
    while True:
        page = call(**kwargs, **({"NextToken": token} if token else {}))
        yield from page.get(key) or []
        token = page.get("NextToken")
        if not token:
            return


def _wait_for_job(
    client: Any,
    job_id: str,
    *,
    sleep: Callable[[float], None],
    poll_seconds: float,
    max_polls: int,
) -> None:
    """Return once the import job completed; raise on any other ending."""
    for _ in range(max_polls):
        job = client.get_job(JobId=job_id)
        state = str(job.get("State"))
        if state == "COMPLETED":
            return
        if state in _DONE_STATES:
            errors = "; ".join(
                str(error.get("Message") or error.get("Code") or error)
                for error in job.get("Errors") or []
            )
            raise MarketplaceRevisionError(
                f"import job {job_id} ended {state}" + (f": {errors}" if errors else "")
            )
        sleep(poll_seconds)
    raise MarketplaceRevisionError(
        f"import job {job_id} did not finish after {max_polls} polls; "
        "the revision was left unfinalized and the next run rebuilds it"
    )


def publish_month(
    client: Any,
    *,
    data_set_id: str,
    bucket: str,
    month: str,
    sleep: Callable[[float], None] = time.sleep,
    poll_seconds: float = 10.0,
    max_polls: int = 180,
) -> Outcome:
    """Create, fill, check, and finalize the revision for ``month``."""
    check_month(month)
    comment = revision_comment(month)
    existing = [
        revision
        for revision in _pages(client.list_data_set_revisions, "Revisions", DataSetId=data_set_id)
        if revision.get("Comment") == comment
    ]
    finalized = [revision for revision in existing if revision.get("Finalized")]
    if finalized:
        revision_id = str(finalized[0]["Id"])
        log.warning(
            "%s is already published as revision %s; a published revision cannot be "
            "replaced, only revoked by the owner in the console",
            month,
            revision_id,
        )
        return Outcome("already_published", revision_id)
    for stale in existing:
        log.info("deleting the unfinalized revision %s an earlier run left", stale["Id"])
        client.delete_revision(DataSetId=data_set_id, RevisionId=stale["Id"])

    revision_id = str(client.create_revision(DataSetId=data_set_id, Comment=comment)["Id"])
    job_id = str(
        client.create_job(
            Type="IMPORT_ASSETS_FROM_S3",
            Details={
                "ImportAssetsFromS3": {
                    "AssetSources": asset_sources(bucket, month),
                    "DataSetId": data_set_id,
                    "RevisionId": revision_id,
                }
            },
        )["Id"]
    )
    client.start_job(JobId=job_id)
    _wait_for_job(client, job_id, sleep=sleep, poll_seconds=poll_seconds, max_polls=max_polls)

    prefix = tables_prefix(month)
    assets = list(
        _pages(client.list_revision_assets, "Assets", DataSetId=data_set_id, RevisionId=revision_id)
    )
    by_name = {str(asset.get("Name")).removeprefix(prefix): asset for asset in assets}
    if len(assets) != len(ASSET_NAMES) or set(by_name) != set(ASSET_NAMES):
        raise MarketplaceRevisionError(
            f"revision {revision_id} holds {sorted(by_name)}, not the five files "
            f"{list(ASSET_NAMES)}; it was left unfinalized"
        )
    for name, asset in by_name.items():
        if asset.get("Name") != name:
            client.update_asset(
                AssetId=asset["Id"], DataSetId=data_set_id, RevisionId=revision_id, Name=name
            )
    client.update_revision(DataSetId=data_set_id, RevisionId=revision_id, Finalized=True)
    return Outcome("published", revision_id)


def _client(region: str) -> Any:  # pragma: no cover - needs boto3 and AWS credentials
    import boto3  # type: ignore[import-not-found,import-untyped,unused-ignore]

    return boto3.client("dataexchange", region_name=region)


def main(argv: Sequence[str] | None = None, *, client: Any = None) -> int:
    """Command-line entry point for the workflow step."""
    parser = argparse.ArgumentParser(
        prog="python -m scorecard_pipeline.marketplace_revision",
        description="Publish one month's history tables as an AWS Data Exchange revision.",
    )
    parser.add_argument("--data-set-id", required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--region", default="us-west-2")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        outcome = publish_month(
            client if client is not None else _client(args.region),
            data_set_id=args.data_set_id,
            bucket=args.bucket,
            month=args.month,
        )
    except MarketplaceRevisionError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"{outcome.status} {args.month} as revision {outcome.revision_id}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
