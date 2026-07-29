"""Regression checks for workflows that publish or commit generated data."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_commit_retry_loops_fail_when_no_push_succeeds() -> None:
    for name in ("equity.yml", "canada-equity.yml", "rt-monitor.yml", "rt-archive.yml"):
        workflow = _workflow(name)
        assert "pushed=false" in workflow, name
        assert "pushed=true" in workflow, name
        assert 'if [ "$pushed" != true ]' in workflow, name
        assert "exit 1" in workflow, name


def test_pages_publishes_only_registry_bounded_artifact_directories() -> None:
    workflow = _workflow("pages.yml")
    assembler = (ROOT / "pipeline" / "scripts" / "assemble_public_artifacts.sh").read_text()

    assert "assemble_public_artifacts.sh" in workflow
    assert "jq -r '.agencies | keys[]' \"$index_path\"" in assembler
    assert "cp -r data/artifacts _site/data/artifacts" not in workflow
    assert 'cp -r "data/artifacts/run"' not in workflow


def test_browser_workflows_gate_generated_size_after_assembly() -> None:
    for name in ("a11y.yml", "pages.yml"):
        workflow = _workflow(name)
        assert workflow.index("assemble_public_artifacts.sh") < workflow.index(
            "check_site_budgets.py"
        ), name
        assert "--site-root ../_site" in workflow, name
        assert "--config ../site-budgets.json" in workflow, name
    pages = _workflow("pages.yml")
    assert 'if [ "$budget_status" -eq 1 ] && [ "$PERF_GATE" = "advisory" ]' in pages
    assert 'exit "$budget_status"' in pages


def test_browser_workflows_cover_representative_routes_and_retain_reports() -> None:
    upload_artifact = "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f"
    for name in ("a11y.yml", "pages.yml"):
        workflow = _workflow(name)
        assert "lighthouserc.json" in workflow, name
        assert "lighthouserc.routes.json" in workflow, name
        assert "lhci-reports/" in workflow, name
        assert "if: ${{ always() }}" in workflow, name
        assert upload_artifact in workflow, name


def test_pages_verifies_the_deployed_crawl_surface() -> None:
    workflow = _workflow("pages.yml")

    assert "production-smoke:" in workflow
    assert "needs: [lighthouse, deploy]" in workflow
    assert re.search(
        r"^\s+BASE_URL: https://gtfsscorecard[.]org$",
        workflow,
        flags=re.MULTILINE,
    )
    assert "/robots.txt" in workflow
    assert "/sitemap.xml" in workflow
    assert "/agency/unitrans/" in workflow
    assert "/agency/yolobus/" in workflow
    assert "_site/deployment.json" in workflow
    assert "needs.lighthouse.outputs.deployed_sha" in workflow
    assert ".commit == $commit" in workflow
