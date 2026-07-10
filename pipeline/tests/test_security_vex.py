"""Keep the time-bounded container CVE exceptions honest and synchronized."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import yaml

from scorecard_pipeline.validate import VALIDATOR_VERSION

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_validator_vex_matches_trivy_exceptions_and_pin() -> None:
    root = REPOSITORY_ROOT
    vex = json.loads((root / "vex.json").read_text())
    ignored = yaml.safe_load((root / ".trivyignore.yaml").read_text())["vulnerabilities"]

    vex_ids = {item["id"] for item in vex["vulnerabilities"]}
    ignored_ids = {item["id"] for item in ignored}
    assert ignored_ids == vex_ids
    assert vex["metadata"]["component"]["version"] == VALIDATOR_VERSION
    assert all(item["analysis"]["state"] == "not_affected" for item in vex["vulnerabilities"])

    today = dt.date.today()
    expiries = {dt.date.fromisoformat(str(item["expired_at"])) for item in ignored}
    assert min(expiries) > today
    assert max(expiries) <= today + dt.timedelta(days=90)


def test_container_scan_consumes_the_reviewed_ignore_file() -> None:
    workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "container-scan.yml").read_text()
    assert "trivyignores: .trivyignore.yaml" in workflow
