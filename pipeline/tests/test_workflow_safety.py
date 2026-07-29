"""Regression checks for workflows that publish or commit generated data."""

from __future__ import annotations

import json
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
        assembly = workflow.index("assemble_public_artifacts.sh")
        seo = workflow.index("check_site_seo.py")
        budgets = workflow.index("check_site_budgets.py")
        assert assembly < seo < budgets, name
        assert "--site-root ../_site" in workflow, name
        assert "--config ../site-budgets.json" in workflow, name
    pages = _workflow("pages.yml")
    assert 'if [ "$budget_status" -eq 1 ] && [ "$PERF_GATE" = "advisory" ]' in pages
    assert 'exit "$budget_status"' in pages


def test_browser_workflows_block_on_structural_seo_independent_of_perf_gate() -> None:
    upload_artifact = "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f"
    for name, artifact_name in (
        ("a11y.yml", "seo-report-a11y"),
        ("pages.yml", "seo-report-pages"),
    ):
        workflow = _workflow(name)
        seo_start = workflow.index("- name: Enforce the structural SEO contract")
        report_start = workflow.index("- name: Retain the structural SEO report")
        budgets_start = workflow.index("- name: Enforce generated page-size budgets")
        seo_step = workflow[seo_start:report_start]
        report_step = workflow[report_start:budgets_start]

        assert (
            "uv run python scripts/check_site_seo.py\n"
            "          --site-root ../_site\n"
            "          --config ../site-seo.json\n"
            "          --report ../seo-report.json"
        ) in seo_step, name
        assert "PERF_GATE" not in seo_step, name
        assert "set +e" not in seo_step, name
        assert "if:" not in seo_step, name

        assert "if: ${{ always() }}" in report_step, name
        assert upload_artifact in report_step, name
        assert f"name: {artifact_name}-${{{{ github.run_id }}}}" in report_step, name
        assert "${{ github.run_attempt }}" in report_step, name
        assert "path: seo-report.json" in report_step, name
        assert "if-no-files-found: error" in report_step, name
        assert "retention-days: 14" in report_step, name


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


def test_watchdog_schedules_isolated_uptime_and_production_lighthouse_jobs() -> None:
    workflow = _workflow("watchdog.yml")
    production_start = workflow.index("  production-lighthouse:")
    watch = workflow[workflow.index("  watch:") : production_start]
    production = workflow[production_start:]

    assert '- cron: "23 */6 * * *"' in workflow
    assert '- cron: "41 7 * * 0"' in workflow
    assert (
        "if: ${{ github.event_name == 'workflow_dispatch' || "
        "github.event.schedule == '23 */6 * * *' }}"
    ) in watch
    assert "41 7 * * 0" not in watch
    assert (
        "if: ${{ github.event_name == 'workflow_dispatch' || "
        "github.event.schedule == '41 7 * * 0' }}"
    ) in production
    assert "23 */6 * * *" not in production
    assert "permissions: {}" in workflow[: workflow.index("jobs:")]
    assert "actions: read" in watch
    assert "contents: read" not in watch
    assert "contents: read" in production
    assert "actions: read" not in production
    assert "timeout-minutes: 25" in production
    assert "timeout-minutes: 20" in production


def test_production_lighthouse_contract_and_report_retention() -> None:
    workflow = _workflow("watchdog.yml")
    production = workflow[workflow.index("  production-lighthouse:") :]
    config = json.loads((ROOT / "lighthouserc.production.json").read_text())
    collect = config["ci"]["collect"]
    assertions = config["ci"]["assert"]["assertions"]

    assert collect["url"] == [
        "https://gtfsscorecard.org/",
        "https://gtfsscorecard.org/agencies/",
        "https://gtfsscorecard.org/agency/unitrans/",
        "https://gtfsscorecard.org/fix/expired_calendar/",
    ]
    assert collect["numberOfRuns"] == 3
    assert assertions["categories:seo"][1]["minScore"] == 1
    assert assertions["categories:accessibility"][1]["minScore"] == 0.95
    assert assertions["categories:performance"][1]["minScore"] == 0.8
    assert assertions["largest-contentful-paint"][1]["maxNumericValue"] == 4250
    assert assertions["cumulative-layout-shift"][1]["maxNumericValue"] == 0.1
    assert assertions["total-blocking-time"][1]["maxNumericValue"] == 500
    for level, options in assertions.values():
        assert level == "error"
        assert options["aggregationMethod"] == "median-run"
    assert config["ci"]["upload"] == {
        "target": "filesystem",
        "outputDir": "lhci-reports/production",
    }

    assert "actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd" in production
    assert "--config=lighthouserc.production.json" in production
    assert "--failOnUploadFailure" in production
    assert "2>&1 | tee lhci-production.log" in production
    assert "test -s lhci-reports/production/manifest.json" in production
    assert "set -o pipefail" in production
    assert "if: ${{ always() }}" in production
    assert "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f" in production
    assert (
        "name: production-lighthouse-${{ github.run_id }}-${{ github.run_attempt }}" in production
    )
    assert "lhci-reports/production/" in production
    assert "lhci-production.log" in production
    assert "if-no-files-found: error" in production
    assert "retention-days: 90" in production
