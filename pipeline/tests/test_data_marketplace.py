"""The AWS Data Exchange listing of the history tables (ADR 0065).

Four things are held here: the monthly revision publisher against a fake Data
Exchange client, the Terraform that is off by default and least-privilege when
on, the workflow job that runs only once the owner has set the data set id,
and the two export changes the listing needed (credential-like URL values are
redacted, and the CSV data dictionary is the export's own column list).
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from scorecard_pipeline import marketplace_revision as mr
from scorecard_pipeline.history_export import (
    CHECKS_COLUMNS,
    DICTIONARY_CSV_HEADER,
    FINDINGS_COLUMNS,
    REDACTED,
    TABLES_VERSION,
    check_row,
    export_files,
    redact_url,
    render_dictionary_csv,
)

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "history-export.yml"
TERRAFORM = ROOT / "infra" / "artifacts" / "marketplace.tf"
DOC = ROOT / "docs" / "data-marketplace.md"
DICTIONARY_CSV = ROOT / "docs" / "marketplace" / "data-dictionary.csv"

DATA_SET = "ds-1"
BUCKET = "gtfs-scorecard-artifacts-ckr"
MONTH = "2026-11"


class FakeDataExchange:
    """Just enough of the Data Exchange client to run ``publish_month``."""

    def __init__(
        self,
        *,
        revisions: list[dict[str, Any]] | None = None,
        job_states: list[str] | None = None,
        imported: list[str] | None = None,
        page_size: int = 1,
    ) -> None:
        self.revisions = list(revisions or [])
        self.job_states = list(job_states or ["IN_PROGRESS", "COMPLETED"])
        self.imported = imported
        self.page_size = page_size
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.assets: list[dict[str, Any]] = []

    def _page(self, items: list[dict[str, Any]], key: str, token: str | None) -> dict[str, Any]:
        start = int(token or 0)
        page: dict[str, Any] = {key: items[start : start + self.page_size]}
        if start + self.page_size < len(items):
            page["NextToken"] = str(start + self.page_size)
        return page

    def list_data_set_revisions(self, *, DataSetId: str, NextToken: str | None = None) -> Any:
        self.calls.append(("list_data_set_revisions", {"DataSetId": DataSetId}))
        return self._page(self.revisions, "Revisions", NextToken)

    def delete_revision(self, **kwargs: Any) -> None:
        self.calls.append(("delete_revision", kwargs))

    def create_revision(self, **kwargs: Any) -> dict[str, str]:
        self.calls.append(("create_revision", kwargs))
        return {"Id": "rev-new"}

    def create_job(self, **kwargs: Any) -> dict[str, str]:
        self.calls.append(("create_job", kwargs))
        sources = kwargs["Details"]["ImportAssetsFromS3"]["AssetSources"]
        keys = self.imported if self.imported is not None else [s["Key"] for s in sources]
        self.assets = [{"Id": f"a{i}", "Name": key} for i, key in enumerate(keys)]
        return {"Id": "job-1"}

    def start_job(self, **kwargs: Any) -> None:
        self.calls.append(("start_job", kwargs))

    def get_job(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("get_job", kwargs))
        state = self.job_states.pop(0) if len(self.job_states) > 1 else self.job_states[0]
        job: dict[str, Any] = {"State": state}
        if state == "ERROR":
            job["Errors"] = [{"Code": "ACCESS_DENIED_EXCEPTION", "Message": "no read on key"}]
        return job

    def list_revision_assets(
        self, *, DataSetId: str, RevisionId: str, NextToken: str | None = None
    ) -> Any:
        self.calls.append(("list_revision_assets", {"RevisionId": RevisionId}))
        return self._page(self.assets, "Assets", NextToken)

    def update_asset(self, **kwargs: Any) -> None:
        self.calls.append(("update_asset", kwargs))

    def update_revision(self, **kwargs: Any) -> None:
        self.calls.append(("update_revision", kwargs))

    def named(self, name: str) -> list[dict[str, Any]]:
        return [kwargs for call, kwargs in self.calls if call == name]


def _publish(client: FakeDataExchange) -> mr.Outcome:
    return mr.publish_month(
        client, data_set_id=DATA_SET, bucket=BUCKET, month=MONTH, sleep=lambda _s: None
    )


# --- the revision publisher -------------------------------------------------


def test_the_five_assets_are_the_five_files_the_export_writes() -> None:
    assert sorted(mr.ASSET_NAMES) == sorted(export_files(Path(".")))
    assert [s["Key"] for s in mr.asset_sources(BUCKET, MONTH)] == [
        f"history/{MONTH}/tables/{name}" for name in mr.ASSET_NAMES
    ]


def test_a_new_month_is_imported_renamed_checked_and_finalized() -> None:
    client = FakeDataExchange()
    outcome = _publish(client)

    assert outcome == mr.Outcome("published", "rev-new")
    assert client.named("create_revision") == [
        {"DataSetId": DATA_SET, "Comment": mr.revision_comment(MONTH)}
    ]
    (job,) = client.named("create_job")
    assert job["Type"] == "IMPORT_ASSETS_FROM_S3"
    assert job["Details"]["ImportAssetsFromS3"]["RevisionId"] == "rev-new"
    assert sorted(call["Name"] for call in client.named("update_asset")) == sorted(mr.ASSET_NAMES)
    assert client.named("update_revision") == [
        {"DataSetId": DATA_SET, "RevisionId": "rev-new", "Finalized": True}
    ]
    # Finalizing is the last thing the run does.
    assert client.calls[-1][0] == "update_revision"


def test_a_published_month_is_left_alone() -> None:
    client = FakeDataExchange(
        revisions=[
            {"Id": "rev-old", "Comment": mr.revision_comment("2026-10"), "Finalized": True},
            {"Id": "rev-done", "Comment": mr.revision_comment(MONTH), "Finalized": True},
        ]
    )
    assert _publish(client) == mr.Outcome("already_published", "rev-done")
    assert not client.named("create_revision")
    assert not client.named("delete_revision")
    assert not client.named("update_revision")


def test_an_interrupted_run_is_deleted_and_rebuilt_from_the_start() -> None:
    client = FakeDataExchange(
        revisions=[{"Id": "rev-half", "Comment": mr.revision_comment(MONTH), "Finalized": False}]
    )
    assert _publish(client).status == "published"
    assert client.named("delete_revision") == [{"DataSetId": DATA_SET, "RevisionId": "rev-half"}]
    first_delete = client.calls.index(("delete_revision", client.named("delete_revision")[0]))
    first_create = [name for name, _ in client.calls].index("create_revision")
    assert first_delete < first_create


@pytest.mark.parametrize("state", ["ERROR", "CANCELLED", "TIMED_OUT"])
def test_a_failed_import_is_never_finalized(state: str) -> None:
    client = FakeDataExchange(job_states=[state])
    with pytest.raises(mr.MarketplaceRevisionError, match=state):
        _publish(client)
    assert not client.named("update_revision")


def test_a_job_that_never_finishes_is_never_finalized() -> None:
    client = FakeDataExchange(job_states=["IN_PROGRESS"])
    with pytest.raises(mr.MarketplaceRevisionError, match="did not finish"):
        mr.publish_month(
            client,
            data_set_id=DATA_SET,
            bucket=BUCKET,
            month=MONTH,
            sleep=lambda _s: None,
            max_polls=3,
        )
    assert not client.named("update_revision")


def test_a_revision_missing_a_file_is_never_finalized() -> None:
    keys = [f"history/{MONTH}/tables/{name}" for name in mr.ASSET_NAMES[:-1]]
    client = FakeDataExchange(imported=keys)
    with pytest.raises(mr.MarketplaceRevisionError, match="not the five files"):
        _publish(client)
    assert not client.named("update_revision")


def test_a_revision_with_a_stray_file_is_never_finalized() -> None:
    keys = [f"history/{MONTH}/tables/{name}" for name in mr.ASSET_NAMES]
    client = FakeDataExchange(imported=[*keys[:-1], f"history/{MONTH}/history.zip"])
    with pytest.raises(mr.MarketplaceRevisionError):
        _publish(client)
    assert not client.named("update_revision")


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "26-11", "2026-11-01", ""])
def test_a_bad_month_is_refused_before_any_call(month: str) -> None:
    client = FakeDataExchange()
    with pytest.raises(mr.MarketplaceRevisionError, match="YYYY-MM"):
        mr.publish_month(client, data_set_id=DATA_SET, bucket=BUCKET, month=month)
    assert client.calls == []


def test_the_cli_reports_success_and_failure(capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["--data-set-id", DATA_SET, "--bucket", BUCKET, "--month", MONTH]
    client = FakeDataExchange()
    client.job_states = ["COMPLETED"]
    assert mr.main(argv, client=client) == 0
    assert f"published {MONTH} as revision rev-new" in capsys.readouterr().out

    failing = FakeDataExchange(job_states=["ERROR"])
    assert mr.main(argv, client=failing) == 1
    assert "::error::import job job-1 ended ERROR: no read on key" in capsys.readouterr().err


# --- the Terraform ----------------------------------------------------------


def _terraform() -> str:
    return TERRAFORM.read_text()


def test_terraform_is_off_by_default_and_every_resource_is_gated() -> None:
    text = _terraform()
    assert re.search(
        r'variable "marketplace_enabled" \{[^}]*type\s+= bool[^}]*default\s+= false', text, re.S
    )
    blocks = re.findall(r'^(resource|data) "([a-z_]+)" "([a-z_]+)" \{\n(.*?)^\}', text, re.M | re.S)
    assert len(blocks) == 5
    for kind, typ, name, body in blocks:
        first = body.strip().splitlines()[0].strip()
        assert first == "count = local.marketplace_count" or first.startswith("count "), (
            f"{kind} {typ}.{name} is not gated by marketplace_enabled"
        )
        assert "local.marketplace_count" in body


def test_the_publishing_role_is_least_privilege() -> None:
    text = _terraform()
    actions = set(re.findall(r'"((?:dataexchange|s3|aws-marketplace|iam):[A-Za-z*]+)"', text)) - {
        "dataexchange:JobType"
    }
    assert actions == {
        "dataexchange:GetDataSet",
        "dataexchange:ListDataSetRevisions",
        "dataexchange:CreateRevision",
        "dataexchange:GetRevision",
        "dataexchange:UpdateRevision",
        "dataexchange:DeleteRevision",
        "dataexchange:ListRevisionAssets",
        "dataexchange:GetAsset",
        "dataexchange:UpdateAsset",
        "dataexchange:CreateJob",
        "dataexchange:StartJob",
        "dataexchange:GetJob",
        "dataexchange:CancelJob",
        "s3:GetObject",
        "s3:GetBucketLocation",
        "s3:PutObject",
        "s3:PutObjectAcl",
    }
    # No wildcard action, nothing from the Marketplace Catalog (products, offers).
    assert '"dataexchange:*"' not in text and "aws-marketplace:" not in text
    assert '"IMPORT_ASSETS_FROM_S3"' in text and "dataexchange:JobType" in text
    # S3 reads are the month's tables folder only; writes only into Data
    # Exchange's own buckets, and only through Data Exchange.
    assert '"${aws_s3_bucket.artifacts.arn}/history/*/tables/*"' in text
    assert '"arn:aws:s3:::*aws-data-exchange*"' in text
    assert "dataexchange.amazonaws.com" in text
    # The same main-only trust as the module's other two roles.
    assert "assume_role_policy = data.aws_iam_policy_document.deploy_assume.json" in text


# --- the workflow -----------------------------------------------------------


def _workflow() -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load(WORKFLOW.read_text())
    return loaded


def test_the_marketplace_job_runs_only_after_the_export_and_only_once_configured() -> None:
    jobs = _workflow()["jobs"]
    job = jobs["marketplace"]
    assert job["needs"] == "export"
    assert job["if"] == "${{ vars.ADX_DATA_SET_ID != '' }}"
    assert job["permissions"] == {"contents": "read", "id-token": "write"}
    assert jobs["export"]["outputs"]["month"] == "${{ steps.write.outputs.month }}"
    steps = job["steps"]
    auth = next(step for step in steps if "configure-aws-credentials" in str(step.get("uses")))
    assert auth["with"]["role-to-assume"] == "${{ secrets.MARKETPLACE_AWS_ROLE_ARN }}"
    publish = next(
        step for step in steps if step.get("name") == "Publish the month as a new revision"
    )
    assert "scorecard_pipeline.marketplace_revision" in publish["run"]


def test_the_unzipped_tables_are_written_only_when_the_listing_is_on() -> None:
    steps = _workflow()["jobs"]["export"]["steps"]
    names = [step.get("name") for step in steps]
    write = names.index("Write the month's export to the private history prefix")
    tables = names.index("Write the unzipped tables for the marketplace revision")
    assert tables == write + 1
    step = steps[tables]
    assert step["if"] == "${{ vars.ADX_DATA_SET_ID != '' }}"
    for name in mr.ASSET_NAMES:
        assert name in step["run"]
    assert "history/${month}/tables/${name}" in step["run"]


def test_no_job_uploads_a_run_artifact() -> None:
    # A run artifact of a public repository is published; the tables are sold.
    for job in _workflow()["jobs"].values():
        for step in job["steps"]:
            assert "upload-artifact" not in str(step.get("uses", ""))


# --- the export changes the listing needed ----------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "https://b.s3.amazonaws.com/f.zip?response-content-disposition=attachment"
            "&AWSAccessKeyId=ASIAXX&Signature=abc%3D&x-amz-security-token=IQo&Expires=1785944386",
            "https://b.s3.amazonaws.com/f.zip?response-content-disposition=attachment"
            f"&AWSAccessKeyId={REDACTED}&Signature={REDACTED}&x-amz-security-token={REDACTED}"
            "&Expires=1785944386",
        ),
        (
            "https://app.mecatran.com/utw/ws/gtfsfeed/static/okc?apiKey=0123",
            f"https://app.mecatran.com/utw/ws/gtfsfeed/static/okc?apiKey={REDACTED}",
        ),
        (
            "https://api.example.fr/exs/GTFS?Key=k1&OperatorCode=ABC",
            f"https://api.example.fr/exs/GTFS?Key={REDACTED}&OperatorCode=ABC",
        ),
        (
            "https://storage.googleapis.com/b/f.zip?X-Goog-Credential=c&X-Goog-Signature=s",
            f"https://storage.googleapis.com/b/f.zip?X-Goog-Credential={REDACTED}"
            f"&X-Goog-Signature={REDACTED}",
        ),
        ("https://user:pass@feeds.example/gtfs.zip", "https://feeds.example/gtfs.zip"),
        ("https://feeds.example/gtfs.zip", "https://feeds.example/gtfs.zip"),
        (
            "https://feeds.example/gtfs.zip?v=3&download",
            "https://feeds.example/gtfs.zip?v=3&download",
        ),
        (None, None),
        ("", None),
    ],
)
def test_credential_like_url_values_are_redacted_and_nothing_else(
    raw: str | None, expected: str | None
) -> None:
    assert redact_url(raw) == expected


def test_a_check_row_carries_the_redacted_urls() -> None:
    artifact = {
        "snapshot_date": "2026-10-01",
        "overall": {"score": 80.0},
        "feed": {"static_url": "https://x.example/f?apiKey=s3cret"},
        "fetch": {"final_url": "https://b.example/f.zip?X-Amz-Signature=abc&X-Amz-Credential=c"},
    }
    row = check_row("alpha", artifact, agency=None, finding_count=0)
    assert row["feed_static_url"] == f"https://x.example/f?apiKey={REDACTED}"
    assert "abc" not in row["fetch_final_url"] and "X-Amz-Credential" in row["fetch_final_url"]
    assert TABLES_VERSION == "1.1"


def test_the_csv_dictionary_is_the_export_column_list_and_is_committed() -> None:
    text = render_dictionary_csv()
    rows = list(csv.reader(io.StringIO(text)))
    assert tuple(rows[0]) == DICTIONARY_CSV_HEADER
    expected = [("checks", c.name, c.type, c.meaning) for c in CHECKS_COLUMNS] + [
        ("findings", c.name, c.type, c.meaning) for c in FINDINGS_COLUMNS
    ]
    assert [tuple(row) for row in rows[1:]] == expected
    assert len(text.encode()) < 1_000_000  # Data Exchange's limit is 1 MB.
    assert DICTIONARY_CSV.read_text() == text, (
        "docs/marketplace/data-dictionary.csv is stale; regenerate it with "
        "render_dictionary_csv() (docs/data-marketplace.md)"
    )


def test_the_doc_names_the_switches_the_code_reads() -> None:
    doc = DOC.read_text()
    for name in (
        "marketplace_enabled",
        "ADX_DATA_SET_ID",
        "MARKETPLACE_AWS_ROLE_ARN",
        "marketplace_data_set_id",
        "marketplace_publish_role_arn",
        "history/<YYYY-MM>/tables/",
    ):
        assert name in doc, name
