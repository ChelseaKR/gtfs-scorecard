"""Guard the public agency-claim intake contract."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_claim_form_collects_public_evidence_without_requiring_email() -> None:
    form = yaml.safe_load((ROOT / ".github/ISSUE_TEMPLATE/claim-agency.yml").read_text())
    fields = {item.get("id"): item for item in form["body"] if item.get("id")}

    assert form["labels"] == ["agency-claim"]
    assert fields["agency-id"]["validations"]["required"] is True
    assert fields["requested-change"]["validations"]["required"] is True
    assert "public-proof" in fields
    assert "proof-method" in fields
    assert not any("email" in field_id for field_id in fields)


def test_claim_workflow_never_auto_changes_the_registry() -> None:
    workflow = (ROOT / ".github/workflows/claim.yml").read_text()
    assert "evidence review checklist" in workflow
    assert "actions/checkout" not in workflow
    assert "pull request" in workflow
    assert "issues.createComment" in workflow
