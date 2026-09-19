"""Regression checks for workflows that publish or commit generated data."""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def test_every_watchdog_check_fails_when_it_cannot_read_the_answer() -> None:
    """A watchdog that cannot reach the API must say so, not report health.

    Each of these checks asks `gh run list` for the most recent completed run
    and branches on its `conclusion`. That call ends in `|| echo '[]'`, so any
    failure -- a network blip, an expired token, a secondary rate limit --
    yields an EMPTY conclusion rather than an error. An empty string matches
    none of the failure branches, so without an explicit guard the step exits
    0 and the watchdog reports the pipeline healthy on the strength of a reply
    it never received. That is the precise shape of a check that cannot fail.

    Measured 2026-09-13: the Daily scorecard check was missing this guard
    while the realtime and bundle checks beside it already had it. The test is
    written over every such step rather than the three that exist today, so a
    fourth check cannot be added without it.
    """
    workflow = _workflow("watchdog.yml")
    steps = [block for block in workflow.split("      - name: ") if "gh run list" in block]
    assert steps, "watchdog.yml no longer has a step that reads a run conclusion"
    unguarded = [
        block.splitlines()[0]
        for block in steps
        if "conclusion=$(" in block and 'if [ -z "$conclusion" ]' not in block
    ]
    assert not unguarded, (
        "these watchdog checks read a run conclusion but pass when it is empty, "
        "so an unreachable API reads as a healthy pipeline: " + ", ".join(unguarded)
    )


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
        materialize = workflow.index("materialize_current_artifacts.py")
        render = workflow.index("scorecard render-site")
        assembly = workflow.index("assemble_public_artifacts.sh")
        seo = workflow.index("check_site_seo.py")
        budgets = workflow.index("check_site_budgets.py")
        assert materialize < render < assembly < seo < budgets, name
        assert "--site-root ../_site" in workflow, name
        assert "--config ../site-budgets.json" in workflow, name
    pages = _workflow("pages.yml")
    assert 'if [ "$budget_status" -eq 1 ] && [ "$PERF_GATE" = "advisory" ]' in pages
    assert 'exit "$budget_status"' in pages


def test_pages_materializes_current_dated_citations_without_full_archive_sync() -> None:
    workflow = _workflow("pages.yml")

    assert workflow.index("Sync published artifacts from S3") < workflow.index(
        "materialize_current_artifacts.py"
    )
    assert '--include "*/${today}.json"' in workflow
    assert '--include "*/${yesterday}.json"' in workflow
    assert "materialize_current_artifacts.py" in workflow
    assert "--artifacts-root ../data/artifacts" in workflow
    assert '--include "*/????-??-??.json"' not in workflow


def test_pages_rebuilds_current_rollups_before_render_and_public_assembly() -> None:
    for name in ("a11y.yml", "pages.yml"):
        workflow = _workflow(name)

        materialize = workflow.index("materialize_current_artifacts.py")
        rollups = workflow.index("uv run scorecard rollups")
        render = workflow.index("uv run scorecard render-site")
        assembly = workflow.index("assemble_public_artifacts.sh")

        assert materialize < rollups < render < assembly, name


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
        # issue #297: `error` here meant a failure in an earlier step (e.g.
        # "Materialize validated current dated records") — which skips the
        # SEO check and leaves no report to retain — got masked by a second,
        # more prominent "No files were found" failure from this always-run
        # step, burying the real cause. `warn` lets a genuinely missing
        # report pass through quietly instead.
        assert "if-no-files-found: warn" in report_step, name
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
    assert "_site/release-manifest.json" in workflow
    assert "needs.lighthouse.outputs.deployed_sha" in workflow
    assert "deployment_id" in workflow
    assert "source_run_id" in workflow
    assert "source_run_attempt" in workflow
    assert "release_manifest_sha256" in workflow
    assert ".schema_version == 3" in workflow
    assert ".commit == $commit" in workflow
    assert "ref: ${{ github.sha }}" in workflow

    # Pages is fronted by Fastly, which does not vary its cache key on the
    # query string. The `?deploy=${DEPLOYMENT_ID}` buster this check used to
    # carry bought nothing, and it disguised the real hazard: a request that
    # arrives before the origin has flipped caches the *previous* deployment's
    # bytes at the edge for a full max-age, and short retries then re-read that
    # same copy forever. Fetch the plain URL, and make a miss outlast the edge
    # TTL it is blocked on rather than hammering it.
    smoke = workflow[workflow.index("  production-smoke:") :]
    assert '"${BASE_URL}/deployment.json" -o' in smoke
    assert "served_max_age" in smoke
    # Bounded, so a genuinely broken deploy still fails closed instead of
    # waiting forever, and the job cannot outlive its own budget.
    assert "SMOKE_BUDGET_SECONDS" in smoke
    assert "timeout-minutes: 20" in smoke


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


def test_daily_publish_compares_content_not_timestamps() -> None:
    """`aws s3 sync` re-uploads the whole tree from a fresh checkout, and
    `--size-only` would silently drop a same-length re-score. The daily publish
    therefore goes through `scorecard publish-artifacts`, which compares each
    local file's MD5 against the object's ETag."""
    workflow = _workflow("scorecard.yml")

    assert "scorecard publish-artifacts" in workflow
    assert "--root data/artifacts" in workflow
    assert "--prefix data/artifacts" in workflow
    assert "--retirement-manifest data/artifacts/.retired-current-artifacts.json" in workflow
    # The mtime-driven upload of the whole public tree is gone.
    assert 'aws s3 sync data/artifacts "s3://' not in workflow
    # The same private files stay out of the published tree.
    for private in (
        "*/validator-cache.json",
        "*/structure.json",
        "*/fixlog.json",
        "*/corrected.zip",
    ):
        assert f'--exclude "{private}"' in workflow
    assert '--cache-control "max-age=300"' in workflow
    # The upload must still precede the lifecycle tagging of today's artifacts.
    assert workflow.index("scorecard publish-artifacts") < workflow.index(
        "Tag today's dated artifacts for lifecycle expiration"
    )


def test_daily_index_is_the_last_aggregate_discovery_pointer() -> None:
    workflow = _workflow("scorecard.yml")
    publish = workflow.index("scorecard publish-artifacts")
    legacy_cleanup = workflow.index("Remove legacy public-path pipeline state")
    changes_cleanup = workflow.index("Named-change history is a bounded public claim surface")
    index_upload = workflow.index(
        'aws s3 cp data/artifacts/index.json "${artifact_uri}/index.json"'
    )
    private_state = workflow.index("Advance private comparison memory")

    # index.json is the aggregate discovery pointer, not another member of the
    # concurrent tree upload. Every object write and bounded cleanup must finish
    # before it advances, while direct mutable latest.json consumers remain
    # non-atomic and private comparison memory advances afterward.
    publisher_block = workflow[publish:legacy_cleanup]
    assert '--exclude "index.json"' in publisher_block
    assert publish < legacy_cleanup < changes_cleanup < index_upload < private_state


def test_lifecycle_tagging_retries_transient_s3_failures() -> None:
    for name in ("scorecard.yml", "targeted-score.yml"):
        workflow = _workflow(name)
        assert "tag_dated_artifact()" in workflow
        assert "for attempt in 1 2 3 4" in workflow
        assert "--output text >/dev/null" in workflow
        assert "::error title=lifecycle tagging failed::" in workflow


def test_intraday_publish_compares_content_not_timestamps() -> None:
    """The intraday refresh stages each refreshed feed's whole directory, so the
    mtime-driven `aws s3 sync` re-PUT that feed's entire dated history every
    cycle from a fresh checkout. Rewriting an object also drops its tags, which
    is what stopped the tag-filtered expire-dated-artifacts lifecycle rule from
    ever matching. The refresh publishes through the same content-comparing
    publisher as the daily run."""
    workflow = _workflow("refresh.yml")

    assert "scorecard publish-artifacts" in workflow
    assert '--root "$public_stage"' in workflow
    assert "--prefix data/artifacts" in workflow
    assert "--retirement-manifest data/artifacts/.retired-current-artifacts.json" in workflow
    # The mtime-driven upload of the staged public tree is gone.
    assert 'aws s3 sync "$public_stage"' not in workflow
    # The same private files stay out of the published tree.
    for private in (
        "*/validator-cache.json",
        "*/structure.json",
        "*/fixlog.json",
        "*/corrected.zip",
    ):
        assert f'--exclude "{private}"' in workflow
    assert '--cache-control "max-age=300"' in workflow
    # Publication still happens after the staging tree is built and after the
    # credentials renewal that precedes the first public write.
    assert workflow.index("Renew AWS credentials before publishing") < workflow.index(
        "scorecard publish-artifacts"
    )


def test_no_workflow_publishes_with_a_size_only_comparison() -> None:
    """`--size-only` cannot see a change that keeps the same byte length."""
    for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            code = line.split("#", 1)[0]
            assert "--size-only" not in code, f"{path.name}: {line.strip()}"


def test_dataset_release_packages_only_a_validated_canonical_deployment() -> None:
    workflow = _workflow("dataset-release.yml")
    daily = _workflow("scorecard.yml")
    refresh = _workflow("refresh.yml")

    # Checked-in web exports are a bounded development snapshot and must never
    # be the source of a citable release.
    assert "web/catalog.json web/catalog.csv" not in workflow
    assert 'cp "$f" bundle/' not in workflow
    assert 'base="https://gtfsscorecard.org"' in workflow
    assert "/data/artifacts/index.json?release=${request_id}-index" in workflow
    assert "group: artifacts-publish" in workflow
    assert 'cron: "47 17 1 * *"' in workflow
    assert "workflow_run:" not in workflow
    assert "actions: read" in workflow
    assert "actions/workflows/scorecard.yml/runs?event=schedule" in workflow
    assert "status=success&branch=main" in workflow
    assert '.event == "schedule"' in workflow
    assert '.conclusion == "success"' in workflow
    assert 'startswith($cut_date + "T")' in workflow
    assert "No successful same-day scheduled Daily scorecard run exists" in workflow
    assert "source_mode=scheduled-daily" in workflow
    assert "source_mode=manual-latest" in workflow
    assert "not scheduled day-1 Daily provenance" in workflow
    assert "ref: ${{ steps.source.outputs.head_sha }}" in workflow
    assert "fetch-depth: 0" in workflow
    assert workflow.count("secrets.SCHEDULED_WRITER_SSH_KEY") == 1
    assert 'git tag -s "$RELEASE_TAG" "$SOURCE_HEAD_SHA"' in workflow
    assert 'git verify-tag -- "$RELEASE_TAG"' in workflow
    assert 'test "$(git cat-file -t "refs/tags/${RELEASE_TAG}")" = tag' in workflow
    assert '.object.type == "tag" and .object.sha == $object' in workflow
    assert 'and .object.type == "commit"' in workflow
    assert "and .object.sha == $target" in workflow

    # The 15:23 intraday deploy normally occurs before the 17:47 monthly cut.
    # Scheduled releases therefore consume the selected Daily run's exact Pages
    # artifact instead of expecting that run to remain the mutable live deploy.
    release_cron = re.search(r'cron: "(\d+) (\d+) 1 \* \*"', workflow)
    refresh_cron = re.search(r'cron: "(\d+) \*/(\d+) \* \* \*"', refresh)
    assert release_cron is not None and refresh_cron is not None
    release_minute = int(release_cron.group(2)) * 60 + int(release_cron.group(1))
    refresh_minute = int(refresh_cron.group(1))
    refresh_step = int(refresh_cron.group(2))
    prior_refreshes = [
        hour * 60 + refresh_minute
        for hour in range(0, 24, refresh_step)
        if hour * 60 + refresh_minute < release_minute
    ]
    assert max(prior_refreshes) == 15 * 60 + 23
    scheduled_source = workflow[
        workflow.index('if [ "$SOURCE_MODE" = scheduled-daily ]') : workflow.index(
            "else\n            # Manual cuts retain latest-production semantics"
        )
    ]
    assert 'gh run download "$SOURCE_RUN_ID"' in scheduled_source
    assert "--name github-pages" in scheduled_source
    assert 'tar -xf "${archives[0]}" -C "$site"' in scheduled_source
    assert "gtfsscorecard.org" not in scheduled_source

    # A successful Daily workflow includes the reusable Pages deployment and
    # its production smoke, so selecting only a completed/successful Daily run
    # establishes both sides of the scheduled publication boundary.
    deploy = daily.index("  deploy:")
    assert daily.index("  collect:") < deploy
    assert "needs: collect" in daily[deploy:]
    assert "uses: ./.github/workflows/pages.yml" in daily[deploy:]

    manual = workflow.index("# Manual cuts retain latest-production semantics")
    before = workflow.index("deployment-before.json", manual)
    manifest = workflow.index("release-manifest.json?release=", manual)
    catalog = workflow.index(
        "for f in catalog.json catalog.csv dataset.json dataset.csv ntd.json", manual
    )
    parquet = workflow.index("api/v1/agencies.parquet?release=${request_id}-parquet", manual)
    index = workflow.index("data/artifacts/index.json?release=${request_id}-index", manual)
    latest = workflow.index("data/artifacts/${id}/latest.json?release=", manual)
    after = workflow.index("deployment-after.json", manual)
    compare = workflow.index('cmp "$source/deployment-before.json"', manual)
    validator = workflow.index("python -m scorecard_pipeline.dataset_release")
    promotion = workflow.index("scorecard_pipeline.dataset_release_promotion")

    assert before < manifest < catalog < parquet < index < latest < after < compare < validator
    assert validator < promotion
    assert ".schema_version == 3 and .commit == $commit" in workflow
    assert ".source_run_id == $source_run_id" in workflow
    assert ".source_run_attempt == $source_run_attempt" in workflow
    assert 'SOURCE_MODE" = scheduled-daily' in workflow
    assert "release_manifest_sha256 == $manifest_sha" in workflow
    assert "(.files | keys | sort)" in workflow
    assert "sha256sum --check" in workflow
    assert "Cache-Control: no-cache, no-store" in workflow
    assert '--artifacts-root "$site/data/artifacts"' in workflow
    assert '--web-root "$site"' in workflow
    assert "--bundle-root ../bundle" in workflow
    assert "open('bundle/catalog.json')" in workflow
    assert "jq -er '.agencies | keys[]'" in workflow
    assert 'find "$site/data/artifacts" -mindepth 2 -maxdepth 2 -type f' in workflow
    assert "jq -e --arg id \"$id\" '.agency.id == $id'" in workflow
    assert '--source-mode "$SOURCE_MODE"' in workflow
    assert "--stage-only" in workflow
    assert "actions/upload-artifact@b7c566a772e6b6bfb58ed0dc250532a479d7789f" in workflow
    assert "dataset-release-promotion-${{ steps.bundle.outputs.tag }}" in workflow
    assert "pipeline/scripts/promote_dataset_release.sh ${tag} ${GITHUB_RUN_ID}" in workflow
    assert "gh release create" not in workflow


def test_dataset_release_mutates_tags_only_after_trusted_main_validation() -> None:
    workflow = _workflow("dataset-release.yml")

    initial_checkout = workflow.index("ref: ${{ github.sha }}")
    source_resolution = workflow.index("- name: Resolve the release source")
    source_checkout = workflow.index("ref: ${{ steps.source.outputs.head_sha }}")
    assert initial_checkout < source_resolution < source_checkout
    assert 'if [ "$GITHUB_REF" != "refs/heads/main" ]' in workflow
    assert '"+refs/heads/main:refs/remotes/origin/main"' in workflow
    assert "origin_main=$(git rev-parse refs/remotes/origin/main)" in workflow
    assert 'if [ "$head_sha" != "$origin_main" ]' in workflow
    assert 'git merge-base --is-ancestor "$head_sha" "$origin_main"' in workflow

    hydration = workflow.index('gh run download "$SOURCE_RUN_ID"')
    deployment = workflow.index('manifest_sha=$(sha256sum "$source/release-manifest.json"')
    manifest = workflow.index("sha256sum --check -)")
    current_latest = workflow.index('cmp "$source/expected-latest-ids" "$source/actual-latest-ids"')
    canonical = workflow.index("python -m scorecard_pipeline.dataset_release")
    provenance = workflow.index("> bundle/PROVENANCE.json")
    checksums = workflow.index("> SHA256SUMS)")
    notes = workflow.index("- name: Write release notes")
    resolve_tag = workflow.index("- name: Resolve the protected dataset tag")
    create_tag = workflow.index("- name: Create the missing SSH-signed annotated dataset tag")
    push_tag = workflow.index('git push origin "refs/tags/${RELEASE_TAG}')
    verify_tag = workflow.index("- name: Verify the trusted hosted dataset tag")
    stage_draft = workflow.index("- name: Stage and verify the release draft")

    assert (
        hydration
        < deployment
        < manifest
        < current_latest
        < canonical
        < provenance
        < checksums
        < notes
        < resolve_tag
        < create_tag
        < push_tag
        < verify_tag
        < stage_draft
    )
    assert 'tag="dataset-${SOURCE_MONTH}"' in workflow
    assert "RELEASE_TAG: ${{ steps.bundle.outputs.tag }}" in workflow
    assert 'tag="${{ steps.bundle.outputs.tag }}"' in workflow


def test_dataset_release_promotion_is_draft_first_and_fail_closed() -> None:
    promotion = (ROOT / "pipeline/src/scorecard_pipeline/dataset_release_promotion.py").read_text(
        encoding="utf-8"
    )

    create = promotion.index('"draft": True')
    draft_verify = promotion.index("verified_draft = _refresh_until_exact")
    immutable = promotion.index("client.immutable_releases_enabled()")
    publish = promotion.index("client.publish(_release_id(verified_draft))")
    public_verify = promotion.index("_refresh_until_exact(client, desired, local, draft=False)")
    assert create < draft_verify < immutable < publish < public_verify
    assert 'release.get("draft") is False' in promotion
    assert 'return "already-published"' in promotion
    assert "release contains unexpected asset" in promotion
    assert "downloaded release bytes differ" in promotion
    assert 'expected["immutable"] = True' in promotion
    assert 'f"{self.api}/immutable-releases"' in promotion


def test_dataset_release_publication_uses_one_successful_run_bound_package() -> None:
    script = (ROOT / "pipeline/scripts/promote_dataset_release.sh").read_text(encoding="utf-8")

    assert "git status --porcelain --untracked-files=all" in script
    assert '"$(git rev-parse HEAD)" != "$(git rev-parse origin/main)"' in script
    assert 'gh run view "$workflow_run_id"' in script
    assert '.name == "Dataset release" and .conclusion == "success"' in script
    assert 'artifact="dataset-release-promotion-${tag}-${workflow_run_id}-' in script
    assert 'gh run download "$workflow_run_id"' in script
    assert 'git verify-tag -- "$tag"' in script
    assert "scorecard_pipeline.dataset_release_promotion" in script
    assert "--stage-only" not in script
    assert script.index('gh run download "$workflow_run_id"') < script.index(
        "scorecard_pipeline.dataset_release_promotion"
    )


def test_publish_survives_a_dead_score_shard() -> None:
    """One dead shard must not skip the day's publish (issue #297).

    `collect` was fixed in #298; `deploy` was not, and a job's implicit
    `if: success()` is evaluated over its whole ancestry rather than over
    `needs:` alone. So a failed `score` shard went on skipping `deploy` even
    when `collect` succeeded, which the incident's own root cause had already
    described ("skipping collect (and, transitively, deploy)"). Observed live
    on runs 32975621570, 32854480196 and 32642725318: collect success, deploy
    skipped, for six days, masked by Intraday refresh publishing separately.
    """
    workflow = _workflow("scorecard.yml")

    collect = workflow.index("\n  collect:")
    deploy = workflow.index("\n  deploy:")
    assert collect < deploy

    collect_block = workflow[collect:deploy]
    deploy_block = workflow[deploy:]

    assert "if: ${{ !cancelled() }}" in collect_block, (
        "collect must run regardless of individual shard outcomes"
    )
    assert "needs.collect.result == 'success'" in deploy_block, (
        "deploy must gate on collect's own result, not on the implicit "
        "success() that transitively includes the score matrix"
    )


def test_a_transient_s3_error_cannot_abort_a_score_shard() -> None:
    """One socket error must not cost a whole shard its daily refresh.

    The score step runs under `set -euo pipefail`. Of the four S3 calls in its
    per-agency loop, two carried `|| true` and two did not, so either unguarded
    call aborted the shard mid-loop and every agency after it went unscored.
    Observed live in run 33968878878 (2026-09-05): the second of that shard's
    agencies hit "Connection broken: ConnectionResetError(104, 'Connection
    reset by peer')" on the artifact prefetch, the step exited 1, and roughly
    65 records kept the previous day's scorecard. The loop's own design note
    says the opposite -- "one agency's feed being unreachable must not abort
    the shard".

    Continuing past an exhausted retry is safe for both calls, which is why
    they may warn rather than fail: the prefetch is a cache warm-up
    (`_liveness_unchanged` consults `_artifact_contract_current` first, so a
    miss re-scores the feed instead of publishing a stale number), and a
    structure fingerprint that never reaches staging leaves collect with the
    previous copy rather than a wrong one.
    """
    workflow = _workflow("scorecard.yml")

    score = workflow.index("\n  score:")
    collect = workflow.index("\n  collect:")
    score_block = workflow[score:collect]

    assert "s3_retry() {" in score_block, (
        "the per-agency loop must route retryable S3 calls through a helper"
    )
    assert "for attempt in 1 2 3" in score_block
    assert "::warning title=s3 retry exhausted::" in score_block, (
        "an exhausted retry must be announced, not swallowed"
    )

    # Every S3 call in the loop must either go through the retry helper or
    # already tolerate failure. A bare `aws ...` at the start of a line is
    # unguarded; one prefixed with `if` sits inside the helper's own condition.
    for line in score_block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("aws s3"):
            continue
        assert (
            stripped.endswith("|| true")
            or "|| true"
            in score_block[score_block.index(stripped) : score_block.index(stripped) + 400]
        ), f"unguarded S3 call can abort the shard under set -e: {stripped!r}"

    # Both previously-unguarded call sites now retry and tolerate exhaustion.
    assert score_block.count('s3_retry "${id}:') == 2, (
        "both the artifact prefetch and the structure-fingerprint upload must "
        "retry; they were the two calls that could kill the shard"
    )


def test_scheduled_workflows_bound_the_validator_subprocess() -> None:
    """The memory ceiling is opt-in, so a workflow that forgets it is unprotected.

    Without it a runaway validator takes the Actions runner down with it
    ("The runner has received a shutdown signal") instead of failing as an
    ordinary per-agency RuntimeError. Both scheduled workflows run the Java
    validator: the daily one over every feed, the intraday one over whichever
    feeds changed, which can include a large feed.
    """
    for name in ("scorecard.yml", "refresh.yml"):
        workflow = _workflow(name)
        assert 'SCORECARD_VALIDATOR_MEMORY_MB: "10240"' in workflow, name
        jobs_at = workflow.index("\njobs:")
        assert workflow.index("SCORECARD_VALIDATOR_MEMORY_MB") < jobs_at, (
            f"{name}: the ceiling must be workflow-level env so every job inherits it"
        )


def test_daily_merge_tells_the_run_summary_how_many_shards_were_planned() -> None:
    """A shard whose runner is killed uploads no run-summary.json, so the merge
    step's glob simply returns one fewer file. Nothing downstream can recover
    the planned count, so the workflow has to hand it over. Without it the
    merged artifact totals over the survivors and /status/ reports a day that
    lost a thirty-second of the corpus as "Run completed"."""
    workflow = _workflow("scorecard.yml")
    merge_at = workflow.index("scorecard run-summary merge")
    merge_block = workflow[merge_at : merge_at + 400]

    assert "--expected-shards" in merge_block, (
        "the merge step must pass the planned shard count; it cannot be inferred "
        "from the summaries that arrived"
    )
    assert '--expected-shards "$PLANNED_SHARDS"' in merge_block, (
        "the planned count is what `plan` actually emitted, not the requested "
        "SHARD_COUNT. Since `scorecard shards` gives every large_feed a shard of "
        "its own (issue #297), the plan is longer than SHARD_COUNT, and measuring "
        "against SHARD_COUNT would compare more bundles present than expected and "
        "silently stop detecting any shortfall at all"
    )
    assert "degraded_reasons" in workflow, (
        "the CI log must name why the run was degraded, not just that it was"
    )


def test_the_shard_denominator_comes_from_the_plan_not_the_requested_count() -> None:
    """Both consumers of the planned shard count must read the same source.

    `scorecard shards` returns SHARD_COUNT round-robin shards plus one shard
    per `large_feed` (issue #297), so the plan is longer than SHARD_COUNT and
    the two numbers are no longer interchangeable. If the shortfall check kept
    reading SHARD_COUNT it would see 42 bundles against 32 expected, every
    comparison would come out false, and a lost shard would go unreported —
    the exact defect #322 removed, reintroduced by the fix for a different one.
    """
    workflow = _workflow("scorecard.yml")

    assert "shard_count: ${{ steps.plan.outputs.count }}" in workflow, (
        "the plan job must publish the count it actually produced"
    )
    assert "needs: [plan, score]" in workflow, (
        "collect must depend on plan to read its shard_count output"
    )
    verify_at = workflow.index("Verify shard artifacts before publishing")
    verify_block = workflow[verify_at : workflow.index("Gather shard run-health summaries")]
    assert 'expected="${PLANNED_SHARDS:-}"' in verify_block, (
        "the shortfall check measures against the planned count, not SHARD_COUNT"
    )
    assert 'expected="$SHARD_COUNT"' not in workflow, (
        "no consumer of the denominator may fall back to the requested count"
    )


def test_a_missing_shard_denominator_refuses_to_publish() -> None:
    """A shortfall check with no denominator reads exactly like a passing one.

    `collect` runs under `if: !cancelled()`, so it still runs when `plan`
    failed, and an empty shard_count would make every numeric comparison below
    it vacuous rather than loud.
    """
    workflow = _workflow("scorecard.yml")
    verify_at = workflow.index("Verify shard artifacts before publishing")
    verify_block = workflow[verify_at : workflow.index("Gather shard run-health summaries")]
    assert '[ "${expected:-0}" -gt 0 ]' in verify_block, (
        "the denominator must be validated before it is trusted"
    )
    assert "refusing to publish without a denominator" in verify_block, (
        "and the refusal must say why"
    )


def test_daily_publish_names_any_shard_shortfall_not_only_a_collapse() -> None:
    """31 of 32 is neither zero nor below half. The step that verifies shard
    artifacts printed nothing at all in that case, which is the shape the daily
    run has actually been failing in since 2026-08-17."""
    workflow = _workflow("scorecard.yml")
    verify_at = workflow.index("Verify shard artifacts before publishing")
    verify_block = workflow[verify_at : workflow.index("Gather shard run-health summaries")]

    assert '"$got" -eq 0' in verify_block, "a total collapse must still be an error"
    assert '"$got" -lt "$expected"' in verify_block, (
        "any shortfall must be reported, not only a shortfall below half"
    )


def test_lighthouse_logs_capture_the_stream_the_assertions_are_written_to() -> None:
    """`@lhci/cli` writes every assertion line to stderr (assert.js writes
    `<label> for <url> assertion` with `process.stderr.write`); only progress
    lines go to stdout. A `| tee` with no `2>&1` therefore captures a log that
    can never contain the word "warning", which is what `pages.yml`'s advisory
    performance annotation greps for. That annotation is the entire signal FIX-14
    leaves in place on the roughly nine intraday deploys a day that pass
    `perf_gate: advisory`, and it had never once been emitted.

    `watchdog.yml` already redirects, and `test_watchdog_production_lighthouse...`
    pins it there. Pin it for the other two callers so the log a gate reads and
    the log a human downloads both contain the thing they are for."""
    for name, commands in (
        ("pages.yml", ("tee lhci-core.log", "tee lhci-representative.log")),
        (
            "a11y.yml",
            ("tee lhci-core.log", "tee lhci-representative.log", "tee pa11y-output.log"),
        ),
        ("watchdog.yml", ("tee lhci-production.log",)),
    ):
        workflow = _workflow(name)
        for command in commands:
            assert f"2>&1 | {command}" in workflow, (
                f"{name}: `{command}` must capture stderr, or the retained log and any "
                "grep over it see only progress output"
            )
            assert f" | {command}" not in workflow.replace(f"2>&1 | {command}", ""), (
                f"{name}: an unredirected `{command}` remains"
            )


def test_the_advisory_performance_annotation_greps_a_log_that_can_hold_it() -> None:
    """The grep and the redirect have to stay together: either change alone
    silently turns the annotation back into an unreachable branch."""
    pages = _workflow("pages.yml")
    grep_at = pages.index('grep -Eq "warning for"')
    grep_block = pages[grep_at - 400 : grep_at + 200]

    assert "2>&1 | tee lhci-core.log" in grep_block
    assert "2>&1 | tee lhci-representative.log" in grep_block


def _rescore_step() -> str:
    workflow = _workflow("refresh.yml")
    step_at = workflow.index("- name: Re-score only the feeds that changed")
    return workflow[step_at : workflow.index("- name: Rebuild index and rollups", step_at)]


def test_the_intraday_refresh_has_a_floor_under_its_rescore_loop() -> None:
    """`refresh.yml` deploys roughly nine times a day and turned every
    per-feed failure into an `echo`. Nothing counted them, so a cycle in which
    every changed feed failed to re-score still ran reindex, rollups,
    render-site, the S3 publish and the Pages deploy, and reported success.
    `scorecard.yml` has had a floor since #298; this tier had none at all
    (`grep -n '::error\\|exit 1' refresh.yml` returned nothing).

    The loop now lives in `scorecard rescore`, whose floor is tested by what
    it returns (test_rescore.py). What is left to hold here is the wiring: the
    step runs it, and nothing between its exit code and the job swallows it.
    """
    step = _rescore_step()

    assert "uv run scorecard rescore" in step
    assert "set -euo pipefail" in step
    assert "|| true" not in step and "|| echo" not in step, (
        "the rescore's exit 1 is the floor; a fallback here would put the echo back"
    )


def test_the_intraday_rescore_loop_tells_unchanged_apart_from_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`scorecard run` reserves exit 2 for "the feed had not changed after
    all". `scorecard.yml` has always separated it; the shell loop treated every
    non-zero exit identically, which would make the floor fire on a cycle
    where nothing needed doing the moment --skip-unchanged is added here. The
    rescore's constant is held to what `scorecard run` actually returns."""
    import argparse

    from scorecard_pipeline import cli
    from scorecard_pipeline.config import Agency
    from scorecard_pipeline.rescore import UNCHANGED_EXIT

    agency = Agency(id="unitrans", name="Unitrans", static_gtfs_url="https://u.example/g.zip")
    monkeypatch.setattr(cli, "AGENCIES", {agency.id: agency})
    monkeypatch.setattr(cli, "_liveness_unchanged", lambda _agency_id: True)
    args = argparse.Namespace(
        all=False,
        agency=agency.id,
        date=None,
        force_fetch=False,
        rt_samples=1,
        rt_interval=0,
        skip_rt=True,
        skip_unchanged=True,
        outcome_out=None,
    )

    assert cli._cmd_run(args, argparse.ArgumentParser()) == UNCHANGED_EXIT


def test_the_intraday_rescore_loop_has_a_wall_clock_deadline() -> None:
    """The rescore loop had no bound of its own, so a large due batch could
    run the whole job out to its own `timeout-minutes` with the loop still
    mid-agency. A job killed by its own timeout never reaches the reindex and
    rollups step or the S3 publish step after it, so every feed already
    re-scored that cycle was discarded along with the ones still queued.

    Measured 2026-09-14: four of that day's eight scheduled runs (06:56,
    09:37, 12:41, 18:34 UTC; run ids 34815554761, 34828962272, 34844837213,
    34881574728) were canceled at their 175-minute bound while still inside
    this loop, each having already re-scored 100+ agencies before losing all
    of them -- and 34844837213's overrun then held the shared
    `artifacts-publish` concurrency slot long enough that the same day's Daily
    scorecard `collect` job queued behind it and was evicted (canceled, 0
    steps) when the next scheduled refresh arrived. The loop now stops taking
    on new agencies once a deadline measured from the job's own start has
    passed, leaving slack for the steps after it. How it defers is tested in
    test_rescore.py; this holds the budget it is handed.
    """
    workflow = _workflow("refresh.yml")
    job_timeout = _job_timeout(workflow, "refresh")

    assert "job_started_epoch" in workflow, (
        "the loop's deadline must be read from when the job actually started, "
        "not from when this step started -- earlier steps already spend part "
        "of the same timeout-minutes budget"
    )
    record_at = workflow.index("Record job start time")
    step_at = workflow.index("Re-score only the feeds that changed")
    assert record_at < step_at, "the job start time must be recorded before the loop reads it"

    step = _rescore_step()

    assert '--started-epoch "$job_started_epoch"' in step
    assert '--budget-seconds "$REFRESH_RESCORE_DEADLINE_SECONDS"' in step
    deadline_match = re.search(r'REFRESH_RESCORE_DEADLINE_SECONDS: "(\d+)"', step)
    assert deadline_match, "the deadline must be a fixed, readable number of seconds"
    deadline_seconds = int(deadline_match.group(1))
    assert 0 < deadline_seconds < job_timeout * 60

    # Slack for the reindex/rollups step and the S3 publish after this loop:
    # measured 2026-09-14, both plus the AWS credential renewal between them
    # took 2-4 minutes on every recorded run, so 10 minutes of headroom below
    # the job's own bound is not a tight budget.
    assert job_timeout * 60 - deadline_seconds >= 10 * 60, (
        "the deadline leaves too little of the job's timeout-minutes for the "
        "steps that publish whatever this loop managed to score"
    )


def test_a_deferred_feed_is_put_back_for_its_next_check() -> None:
    """The deferral warning used to say deferred feeds "stay due next cycle".
    They stayed due, but the liveness sweep had already recorded their new
    hash, so the next check read them as unchanged and nothing re-scored them
    until the daily run. The sweep now saves the state it started from and the
    rescore puts a deferred feed's record back from it."""
    workflow = _workflow("refresh.yml")
    sweep_at = workflow.index("- name: Detect changed and unreachable feeds")
    sweep = workflow[sweep_at : workflow.index("\n      - name:", sweep_at + 1)]
    step = _rescore_step()

    assert '--baseline-out "$RUNNER_TEMP/liveness.before.json"' in sweep
    assert '--liveness-baseline "$RUNNER_TEMP/liveness.before.json"' in step
    # And the state it rewrites is the one the publish step uploads.
    publish = workflow[workflow.index("- name: Publish refreshed artifacts to S3") :]
    assert "aws s3 cp data/liveness.json" in publish


def test_the_rescore_and_sweep_run_several_at_once_but_politely() -> None:
    """Both steps overlap waiting, not load on any one host: the sweep keeps
    one request per host in flight and the rescore one feed per host, and the
    rescore's children take turns at the heavy part through the lock file."""
    workflow = _workflow("refresh.yml")
    sweep_at = workflow.index("- name: Detect changed and unreachable feeds")
    sweep = workflow[sweep_at : workflow.index("\n      - name:", sweep_at + 1)]
    step = _rescore_step()

    assert re.search(r"--workers (\d+)", sweep)
    assert '--workers "$REFRESH_RESCORE_WORKERS"' in step
    workers = re.search(r'REFRESH_RESCORE_WORKERS: "(\d+)"', step)
    assert workers and 1 <= int(workers.group(1)) <= 8
    assert '--heavy-lock "$RUNNER_TEMP/' in step


def test_the_shard_step_runs_under_pipefail() -> None:
    """The whole of a shard's work happens inside
    `echo "$MATRIX_SHARD" | jq -r '.[]' | while read -r id`. Actions runs
    `run:` blocks under `bash -e {0}`: -e but not -o pipefail. jq is not the
    last element of that pipeline, so its exit status was thrown away. A
    malformed matrix slice made the loop read nothing, iterate zero times and
    exit 0, and `if-no-files-found: ignore` on the upload meant a shard that
    scored no agency at all looked exactly like a shard with nothing to do.
    Verified locally: the same pipeline exits 0 under `set -e` and 5 under
    `set -euo pipefail` when jq is handed input it cannot parse."""
    workflow = _workflow("scorecard.yml")
    step_at = workflow.index("Score this shard's agencies")
    step = workflow[step_at : workflow.index("actions/upload-artifact", step_at)]

    pipeline_at = step.index('echo "$MATRIX_SHARD" | jq -r')
    assert "set -euo pipefail" in step
    assert step.index("set -euo pipefail") < pipeline_at, (
        "the options have to be set before the pipeline they protect"
    )


def test_the_tiles_size_ceiling_stops_the_commit_it_exists_to_stop() -> None:
    """ADR 0023 commits the PMTiles archive into `web/tiles/` "as long as it
    stays at or under 25 MB" and says to move it to S3 + CloudFront above that.
    The step checking it printed a `::warning` and returned 0, and the commit
    step below it runs with `inputs.commit` defaulting to true, so the archive
    was pushed to main either way. The branch had also never been taken: the
    committed archive is around 670 KB against a 26,214,400-byte ceiling, so
    nothing had ever exercised it."""
    workflow = _workflow("tiles.yml")
    gate_at = workflow.index("26214400")
    gate = workflow[gate_at : workflow.index("Upload archive as a workflow artifact")]

    assert "::error" in gate, "over the ceiling has to be an error, not a warning"
    assert "exit 1" in gate, "and it has to fail, so the commit step is skipped"

    commit_at = workflow.index("- name: Commit the rebuilt archive")
    assert gate_at < commit_at, "the ceiling must be checked before the commit, not after"

    upload = workflow[workflow.index("Upload archive as a workflow artifact") : commit_at]
    assert "if: ${{ always() }}" in upload, (
        "an archive that trips the ceiling still has to be downloadable; it is "
        "the file ADR 0023 says to move to S3"
    )


# The realtime monitor's runtime, read off its own run history on 2026-09-08
# rather than estimated: 116.8 minutes was the shortest recorded successful
# run (2026-08-30) and 162.9 the longest (2026-09-05). The figure grows with
# the registry because the sampling burst walks every configured realtime
# endpoint, so it is an observation with a date on it, not a derived count --
# nothing recomputes it, so it cannot jam a merge queue the way a
# hand-maintained counter gated on equality does.
REALTIME_MONITOR_OBSERVED_RUNTIME_CEILING_MINUTES = 163


def test_the_realtime_monitor_bound_sits_between_its_runtime_and_its_cadence() -> None:
    """`timeout-minutes: 45` killed eleven consecutive scheduled runs.

    The bound landed with the portfolio-wide job-timeout pass and was never
    measured against this job. Every recorded successful run of this workflow
    has taken longer than 45 minutes -- the shortest was 117 -- so from that
    commit onward every scheduled run was stopped part-way through "Sample
    realtime feeds", "Commit observations" was skipped, and nothing was
    recorded. `data/rt-health`'s newest commit is 2026-09-05 and the eleven
    runs after it are 11 of 11 `cancelled`, which is how GitHub records a job
    hitting its own bound and is the conclusion every sweep reads as "no
    signal rather than a failure".

    Both directions are asserted, because both mistakes are available:

    * **Below the runtime** is the defect above: the job never finishes.
    * **At or above the cadence** is the opposite one. The concurrency group
      is serial (`cancel-in-progress: false`), so a run allowed to outlive its
      own 180-minute cron makes the next run queue behind it, and a third
      arrival evicts the queued one -- the same silent drop, reached from the
      other side. A run that has already lost the schedule should be stopped,
      not given more room.

    The concurrency shape is asserted here too, because it is the premise that
    makes the cadence a ceiling. If it ever stops being serial, this test's
    reasoning is wrong and should be re-read rather than quietly still passing.
    """
    workflow = _workflow("rt-monitor.yml")

    every_n_hours = re.search(r'- cron: "\d+ \*/(\d+) \* \* \*"', workflow)
    assert every_n_hours, "rt-monitor.yml no longer declares an every-N-hours cron"
    cadence_minutes = int(every_n_hours.group(1)) * 60

    monitor = workflow[workflow.index("  monitor:") :]
    bound = re.search(r"^    timeout-minutes: (\d+)$", monitor, re.MULTILINE)
    assert bound, "the monitor job declares no timeout-minutes"
    timeout_minutes = int(bound.group(1))

    assert timeout_minutes > REALTIME_MONITOR_OBSERVED_RUNTIME_CEILING_MINUTES, (
        f"timeout-minutes: {timeout_minutes} is at or below the longest recorded run "
        f"({REALTIME_MONITOR_OBSERVED_RUNTIME_CEILING_MINUTES} min). A bound under the "
        "job's real runtime does not catch a hang, it guarantees one: every run is "
        "killed part-way and GitHub records it as `cancelled`, not as a failure."
    )
    assert timeout_minutes < cadence_minutes, (
        f"timeout-minutes: {timeout_minutes} is at or above the {cadence_minutes}-minute "
        "cron interval. With a serial concurrency group a run that outlives its cadence "
        "queues the next one and the one after that evicts it. Shard the burst or "
        "lengthen the cron instead of raising this."
    )

    assert "group: rt-monitor" in workflow
    assert "cancel-in-progress: false" in workflow


# Issue #390, measured 2026-09-13 from each job's own started_at/completed_at over
# its scheduled run history. They are committed as the evidence each bound is
# reasoned against, like REALTIME_MONITOR_OBSERVED_RUNTIME_CEILING_MINUTES. They do
# not need to be kept current to catch drift: the watchdog step reads live
# durations every six hours. They only need restating when a bound moves.
#: 170.1 minutes, the longest of 100 scheduled refresh runs (2026-09-01..13).
INTRADAY_REFRESH_OBSERVED_RUNTIME_CEILING_MINUTES = 171
#: 114.2 minutes, the shortest gap between consecutive scheduled refresh fires.
INTRADAY_REFRESH_TIGHTEST_OBSERVED_GAP_MINUTES = 114
#: 56.7 minutes, the longest of 59 successful scheduled collect jobs (2026-07-04..09-13).
DAILY_COLLECT_OBSERVED_RUNTIME_CEILING_MINUTES = 57


def _job_block(workflow: str, job: str) -> str:
    """One top-level job's text, from its key to the next job's key."""
    start = workflow.index(f"\n  {job}:\n") + 1
    following = re.search(r"^  [a-z][a-z0-9_-]*:$", workflow[start + 1 :], re.MULTILINE)
    return workflow[start : start + 1 + following.start()] if following else workflow[start:]


def _job_timeout(workflow: str, job: str) -> int:
    bound = re.search(r"^    timeout-minutes: (\d+)$", _job_block(workflow, job), re.MULTILINE)
    assert bound, f"the {job} job declares no timeout-minutes"
    return int(bound.group(1))


def test_the_intraday_refresh_bound_sits_between_its_runtime_and_its_cadence() -> None:
    """`timeout-minutes: 240` sat above the job's own 180-minute cron.

    It was argued from "~70 to ~137 minutes", a figure the job outgrew: the longest
    of 100 scheduled runs measured on 2026-09-13 took 170.1. A bound above the
    cadence cannot mean "this run has lost its schedule", because the serial
    `artifacts-publish` group has already queued the next cycle, and a third
    arrival evicts the queued run rather than the wedged one. Same two directions
    as the realtime monitor's test, for the same reason.

    No 90% headroom is asserted here, unlike collect. 171 of 175 is 97.7%, and no
    bound under the 180-minute cadence gets under 90% of a 170-minute run. The
    watchdog will fail on a run that long, which is the signal that the job needs
    to be faster or the cron longer.
    """
    workflow = _workflow("refresh.yml")
    every_n_hours = re.search(r'- cron: "\d+ \*/(\d+) \* \* \*"', workflow)
    assert every_n_hours, "refresh.yml no longer declares an every-N-hours cron"
    cadence_minutes = int(every_n_hours.group(1)) * 60
    timeout_minutes = _job_timeout(workflow, "refresh")

    assert timeout_minutes > INTRADAY_REFRESH_OBSERVED_RUNTIME_CEILING_MINUTES, (
        f"timeout-minutes: {timeout_minutes} is at or below the longest recorded refresh "
        f"({INTRADAY_REFRESH_OBSERVED_RUNTIME_CEILING_MINUTES} min), so a legitimately heavy "
        "cycle is killed and recorded as `cancelled`."
    )
    assert timeout_minutes < cadence_minutes, (
        f"timeout-minutes: {timeout_minutes} is at or above the {cadence_minutes}-minute "
        "cron. A refresh allowed to outlive its cadence queues the next one in the serial "
        "publish group. Make the job faster or the cron longer instead of raising this."
    )
    refresh = _job_block(workflow, "refresh")
    assert "group: artifacts-publish" in refresh
    assert "cancel-in-progress: false" in refresh


def test_the_daily_collect_bound_clears_its_runtime_and_cannot_hold_back_two_refreshes() -> None:
    """`timeout-minutes: 60` against a job whose slowest measured run took 56.7.

    A killed collect drops the whole day's publish. The daily cadence is not the
    ceiling; the shared publish slot is. Refresh fires into the same serial group
    as little as 114 minutes apart, so a collect bound under that gap means one
    collect can make at most one refresh wait, never a second that would evict it.
    """
    scorecard = _workflow("scorecard.yml")
    timeout_minutes = _job_timeout(scorecard, "collect")

    assert timeout_minutes > DAILY_COLLECT_OBSERVED_RUNTIME_CEILING_MINUTES, (
        f"timeout-minutes: {timeout_minutes} is at or below the slowest recorded collect "
        f"({DAILY_COLLECT_OBSERVED_RUNTIME_CEILING_MINUTES} min)."
    )
    # The watchdog fails a run at 90% of its bound. A bound whose own measured
    # slowest run already sits there would be red on arrival, and it is the state
    # #390 found: 56.7 of 60. Refresh cannot meet the same margin, because its
    # cadence squeezes it (171 of 175), and its test says so instead of asserting it.
    assert timeout_minutes * 9 > DAILY_COLLECT_OBSERVED_RUNTIME_CEILING_MINUTES * 10, (
        f"the slowest recorded collect ({DAILY_COLLECT_OBSERVED_RUNTIME_CEILING_MINUTES} min) "
        f"is 90% or more of timeout-minutes: {timeout_minutes}, so the watchdog's bound "
        "check is already failing and the next heavier day is a timeout kill."
    )
    assert timeout_minutes < INTRADAY_REFRESH_TIGHTEST_OBSERVED_GAP_MINUTES, (
        f"timeout-minutes: {timeout_minutes} is at or above the tightest observed gap "
        f"between refresh fires ({INTRADAY_REFRESH_TIGHTEST_OBSERVED_GAP_MINUTES} min). A "
        "collect that long can hold the publish slot across two refresh arrivals, and "
        "the second evicts the first."
    )
    # The premise that makes the refresh gap a ceiling at all.
    for text in (_job_block(scorecard, "collect"), _job_block(_workflow("refresh.yml"), "refresh")):
        assert "group: artifacts-publish" in text
        assert "cancel-in-progress: false" in text


def test_the_watchdog_measures_publish_jobs_against_the_bounds_they_declare() -> None:
    """A duration check with a stale copy of the bound measures nothing.

    The watchdog carries the bounds as data because it has no checkout. So each copy
    is held to the workflow it describes, the step reads a job killed at its bound as
    a failure, and a reading that measured no job fails instead of passing.
    """
    watchdog = _workflow("watchdog.yml")
    name = "- name: No scheduled publish job is running up against its own bound"
    at = watchdog.index(name)
    step = watchdog[at : watchdog.index("\n      - name:", at + len(name))]

    declared = {
        (workflow, job): (int(bound), int(runs))
        for workflow, job, bound, runs in re.findall(
            r"^ +([a-z0-9-]+\.yml)\|([a-z0-9_-]+)\|(\d+)\|(\d+)$", step, re.MULTILINE
        )
    }
    assert set(declared) == {
        ("refresh.yml", "refresh"),
        ("scorecard.yml", "collect"),
        ("scorecard.yml", "score"),
    }
    for (workflow, job), (bound, _runs) in declared.items():
        assert bound == _job_timeout(_workflow(workflow), job), (
            f"the watchdog measures {workflow} {job} against {bound} minutes, which is not "
            "the bound that workflow declares"
        )

    # Refresh runs every three hours and the watchdog every six, so reading fewer
    # than two runs would skip every other refresh.
    refresh_cron = re.search(r'- cron: "\d+ \*/(\d+) ', _workflow("refresh.yml"))
    watch_cron = re.search(r'- cron: "\d+ \*/(\d+) \* \* \*" # every', watchdog)
    assert refresh_cron, "refresh.yml no longer declares an every-N-hours cron"
    assert watch_cron, "watchdog.yml no longer declares its every-N-hours cron"
    refresh_hours, watch_hours = int(refresh_cron.group(1)), int(watch_cron.group(1))
    assert declared[("refresh.yml", "refresh")][1] * refresh_hours >= watch_hours

    assert "if: ${{ always() }}" in step
    assert "set -euo pipefail" in step
    assert '[ "$conclusion" = "cancelled" ]' in step, "a job killed at its bound must fail"
    assert "$((minutes * 10)) -ge $((bound * 9))" in step
    assert '[ "$measured" -eq 0 ]' in step, "measuring no job must be an error, not a pass"
    assert 'if [ -z "$ids" ]; then' in step


#: 53 minutes of a 55-minute bound, the slowest Daily score shard on 2026-09-09; 52 on
#: 2026-09-14. The shard held one feed (autolinee-toscane) that took 20.6 minutes
#: alone, and it now has a shard of its own. Restated here as the evidence the
#: watchdog's `score` row exists for, like the constants above.
DAILY_SCORE_SHARD_WORST_OBSERVED_MINUTES = 53


def _watchdog_jq_program(job: str) -> str:
    """The jq program the bound check hands `gh api`, with $job filled in."""
    watchdog = _workflow("watchdog.yml")
    name = "- name: No scheduled publish job is running up against its own bound"
    at = watchdog.index(name)
    step = watchdog[at : watchdog.index("\n      - name:", at + len(name))]
    quoted = re.search(r'--jq "(.*)" \\\n', step)
    assert quoted, "the bound check no longer passes a --jq program to gh api"
    return quoted.group(1).replace('\\"', '"').replace("$job", job)


def _run_jq(program: str, document: dict[str, Any]) -> list[str]:
    import json
    import shutil
    import subprocess

    jq = shutil.which("jq")
    assert jq, "jq is required; the workflow itself runs it on every hosted runner"
    done = subprocess.run(  # noqa: S603 - a fixed jq binary and a program from this repository
        [jq, "-r", program], input=json.dumps(document), capture_output=True, text=True, check=True
    )
    return done.stdout.splitlines()


def _job(name: str, start: str, end: str, conclusion: str = "success") -> dict[str, Any]:
    return {
        "name": name,
        "started_at": f"2026-09-14T{start}Z",
        "completed_at": f"2026-09-14T{end}Z",
        "conclusion": conclusion,
        "steps": [{}, {}, {}],
    }


def test_the_watchdog_reads_the_slowest_matrix_leg_and_not_its_neighbors() -> None:
    """The Daily's shards are named `score (<ids>)`, so an exact-name match never
    saw them. The filter must take the longest leg, ignore jobs that merely start
    with the same letters, and still match a job named exactly."""
    jobs = {
        "jobs": [
            _job("plan", "13:31:28", "13:31:55"),
            _job("score (a, b, c)", "13:31:58", "13:56:33"),
            _job("score (slow-one, x)", "13:31:58", "14:24:49"),
            _job("score (ovapi-netherlands)", "13:33:19", "13:38:29"),
            _job("scoreboard", "13:00:00", "20:00:00"),
            _job("collect", "14:24:50", "15:31:07", "cancelled"),
            _job("score (unfinished)", "13:31:58", "13:31:58"),
        ]
    }
    program = _watchdog_jq_program("score")
    rows = [line.split("\t") for line in _run_jq(program, jobs)]
    assert rows == [["2026-09-14T13:31:58Z", "2026-09-14T14:24:49Z", "success", "3"]]

    exact = [line.split("\t") for line in _run_jq(_watchdog_jq_program("collect"), jobs)]
    assert exact == [["2026-09-14T14:24:50Z", "2026-09-14T15:31:07Z", "cancelled", "3"]]

    # Nothing to measure yields no row, which the step reports as an error.
    assert _run_jq(program, {"jobs": [_job("plan", "13:31:28", "13:31:55")]}) == []


def test_the_score_bound_would_have_flagged_the_shard_that_ran_at_53_of_55() -> None:
    """The watchdog fails a job at 90% of its bound. Restating the bound's own
    arithmetic here keeps the `score` row honest: the 2026-09-09 shard was already
    past it, and the fix (a shard for the one slow feed) is what brings the
    slowest shard back under."""
    bound = _job_timeout(_workflow("scorecard.yml"), "score")
    assert bound * 9 <= DAILY_SCORE_SHARD_WORST_OBSERVED_MINUTES * 10, (
        "the recorded worst shard is under 90% of the bound; update the evidence "
        "or the bound together"
    )


def test_the_watchdog_reads_a_job_timeout_as_a_failure_not_as_silence() -> None:
    """A job killed by its own `timeout-minutes` concludes `cancelled`.

    Not `timed_out`. Measured 2026-09-08 against Realtime monitor run
    34162993774: the job started at 21:24:06 and completed at 22:09:20 --
    forty-five minutes to the second, against `timeout-minutes: 45` -- and
    both the job and the run concluded `cancelled`. So a watchdog that reads
    only `failure` and `timed_out` is blind to a workflow dying on its own
    bound, and every sweep in this campaign treats `cancelled` as no signal at
    all. That is why eleven dead runs went unremarked for three days.
    """
    workflow = _workflow("watchdog.yml")
    watch = workflow[workflow.index("  watch:") : workflow.index("  production-lighthouse:")]

    for check in ("Daily scorecard", "Realtime monitor", "Program report bundle"):
        step_at = watch.index(f"most recent completed {check} run")
        # To the end of this step, not a fixed number of characters. A window
        # measured in bytes stops covering the step the moment a comment is
        # added above the branch it looks for, and then reports that branch
        # missing when it is merely further down -- which is what happened when
        # the unreadable-answer guard was added to the Daily check.
        next_step = watch.find("\n      - name: ", step_at)
        step = watch[step_at:] if next_step == -1 else watch[step_at:next_step]
        assert '"$conclusion" = "cancelled"' in step, (
            f"the {check} check cannot see a job killed by its own timeout"
        )
        assert '"$conclusion" = "failure"' in step, check
        assert '"$conclusion" = "timed_out"' in step, check

    # A check that could not get an answer is not a check that passed. The
    # realtime step refuses an empty conclusion rather than falling through it.
    realtime_at = watch.index("The most recent realtime monitor run did not fail")
    realtime = watch[realtime_at : watch.index("The most recent program report bundle run")]
    assert "--workflow rt-monitor.yml" in realtime
    assert '[ -z "$conclusion" ]' in realtime, (
        "an unreadable run list must be an error, not an implied pass"
    )
    assert "set -euo pipefail" in realtime


# ---------------------------------------------------------------------------
# report-bundle.yml: nothing about the buyer reaches a public run log
# ---------------------------------------------------------------------------

# This repository is public, so everything GitHub renders about a run is a
# publication: the run log (each step's script, its env block, and every line
# it prints), annotations, the step summary, step and job names, the
# concurrency group, and any run artifact. GitHub prints a step's env block in
# the log, including values that came from workflow_dispatch inputs. That is
# how two hand test runs on 2026-09-11 published a buyer's address, program
# name and download capability, back when those were inputs.
#
# So the rule is structural rather than "be careful what you echo". The
# workflow takes one input, an opaque random order reference. The order is
# read from the private bucket inside Python, which registers an ::add-mask::
# for every buyer value before any later step can print one. And nothing on a
# command line, in an env block, or in an echo names a buyer field.
# `pii_log_findings` is the lint that holds that, and the negative controls
# below prove it catches each way back in.

#: Field names that identify a buyer or grant access. None may be a
#: workflow_dispatch input of any workflow in this repository.
BUYER_FIELDS = (
    "bundle_id",
    "deliver_to",
    "program_name",
    "logo",
    "promised_by",
    "download_url",
    "email",
    "buyer_email",
    "customer_email",
    "organization",
    "order_id",
    "session_id",
    "checkout_session",
)
#: Shell variable names that would carry one of them. An echo or printf of any
#: of these, in any step of the fulfillment workflow, is a finding whatever the
#: step's env says, and so is declaring one in an env block.
PII_VARIABLES = (
    "BUYER_EMAIL",
    "CUSTOMER_EMAIL",
    "EMAIL",
    "DELIVER_TO",
    "IN_DELIVER_TO",
    "BUNDLE_ID",
    "IN_BUNDLE_ID",
    "PROGRAM_NAME",
    "IN_PROGRAM_NAME",
    "ORGANIZATION",
    "ORG_NAME",
    "LOGO",
    "IN_LOGO",
    "AGENCY_IDS",
    "IN_AGENCY_IDS",
    "DOWNLOAD_URL",
    "PROMISED_BY",
    "SESSION_ID",
    "CHECKOUT_SESSION",
)
#: The one input the fulfillment workflow may take.
ORDER_REF_INPUT = "order_ref"
#: The command that masks the collected order. It must run before anything
#: else reads the file.
MASK_COMMAND = "bundle_order mask request.json"

_INPUT_REF = re.compile(r"inputs\.([A-Za-z_][A-Za-z0-9_-]*)")
_XTRACE = re.compile(r"(^|[\s;&|(])set\s+(-[a-zA-Z]*x[a-zA-Z]*|-o\s+xtrace)\b|\bbash\s+-[a-zA-Z]*x")
_VERBOSE_CURL = re.compile(r"\bcurl\b[^\n]*\s(-[a-zA-Z]*v[a-zA-Z]*|--verbose|--trace\S*)(\s|$)")
_PRINTS = re.compile(r"\b(echo|printf|cat|tee)\b|\$GITHUB_STEP_SUMMARY|::(error|warning|notice)")


def _steps(workflow: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    return [(job, step) for job, spec in workflow["jobs"].items() for step in spec.get("steps", [])]


def _dispatch_inputs(workflow: dict[Any, Any]) -> list[str]:
    # PyYAML reads the bare key `on:` as the boolean True (YAML 1.1).
    triggers = workflow.get("on", workflow.get(True)) or {}
    dispatch = triggers.get("workflow_dispatch") if isinstance(triggers, dict) else None
    return sorted((dispatch or {}).get("inputs") or {}) if isinstance(dispatch, dict) else []


def _strings(value: Any) -> list[str]:
    """Every key and string value in a parsed workflow, recursively."""
    if isinstance(value, dict):
        return [s for k, v in value.items() for s in (str(k), *_strings(v))]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return [value] if isinstance(value, str) else []


def _foreign_inputs(value: object) -> list[str]:
    """Input references in a string, other than the order reference."""
    return [ref for ref in _INPUT_REF.findall(str(value)) if ref != ORDER_REF_INPUT]


def _workflow_findings(workflow: dict[Any, Any]) -> list[str]:
    """The declared inputs and the strings rendered for the whole run."""
    findings: list[str] = []
    inputs = _dispatch_inputs(workflow)
    if inputs != [ORDER_REF_INPUT]:
        findings.append(f"declares inputs {inputs}; it may take {ORDER_REF_INPUT} alone")
    for field in ("name", "run-name"):
        findings += [
            f"the workflow {field} renders inputs.{r}"
            for r in _foreign_inputs(workflow.get(field) or "")
        ]
    group = (workflow.get("concurrency") or {}).get("group") or ""
    findings += [f"the concurrency group renders inputs.{r}" for r in _foreign_inputs(group)]
    return findings


def _step_field_findings(label: str, step: dict[str, Any]) -> list[str]:
    """What a step carries in its env block and its rendered fields."""
    findings: list[str] = []
    for name, value in (step.get("env") or {}).items():
        if str(name) in PII_VARIABLES:
            findings.append(f"{label} puts {name} in an env block, which the log prints")
        findings += [f"{label} env {name} carries inputs.{r}" for r in _foreign_inputs(value)]
    rendered = [step.get("name") or "", step.get("if") or ""]
    rendered += list((step.get("with") or {}).values())
    for value in rendered:
        findings += [f"{label} renders inputs.{r}" for r in _foreign_inputs(value)]
    if "upload-artifact" in str(step.get("uses") or ""):
        findings.append(f"{label} publishes a run artifact")
    return findings


def _script_findings(label: str, run: str) -> list[str]:
    """What a step's script could print."""
    findings = [
        f"{label} interpolates inputs.{ref} into its script; use env"
        for ref in _INPUT_REF.findall(run)
    ]
    if _XTRACE.search(run):
        findings.append(f"{label} turns on xtrace, which prints every expanded command")
    if _VERBOSE_CURL.search(run):
        findings.append(f"{label} runs a verbose curl, which prints headers and URLs")
    printing = [line for line in run.splitlines() if _PRINTS.search(line)]
    findings += [
        f"{label} prints ${var}: {line.strip()}"
        for line in printing
        for var in PII_VARIABLES
        if re.search(rf"\${{?{var}\b", line)
    ]
    if "/download/" in run or "--download-url" in run:
        findings.append(f"{label} puts the download link on a command line")
    return findings


def _mask_order_findings(steps: list[tuple[str, dict[str, Any]]]) -> list[str]:
    """The step that masks the collected order must be the first to read it,
    and must mask before it does anything else with the file."""
    for job, step in steps:
        run = str(step.get("run") or "")
        if "request.json" not in run:
            continue
        label = f"{job}/{step.get('name') or '?'}"
        if MASK_COMMAND not in run:
            return [f"{label} reads the order before any step has masked it"]
        before = run[: run.index(MASK_COMMAND)].splitlines()
        early = [
            line.strip()
            for line in before
            if "request.json" in line and not line.strip().startswith("aws s3 cp ")
        ]
        return [f"{label} uses the order before masking it: {early[0]}"] if early else []
    return ["no step masks the collected order"]


def pii_log_findings(workflow: dict[Any, Any]) -> list[str]:
    """Every way the fulfillment workflow could put a buyer's details into a
    public run log. Empty means none was found.

    Checked: the declared inputs (the order reference alone); input references
    in env blocks and rendered fields (the order reference alone); inputs
    interpolated straight into a script; env variables named for a buyer
    field; xtrace and verbose curl, which print what a script expands; any
    echo, printf, cat, tee, annotation or summary line that expands a buyer
    variable; the download link on a command line; a run artifact; and the
    order of operations, so that the step that masks the collected order is
    the first to read it and masks before doing anything else with it.
    """
    steps = _steps(workflow)
    findings = _workflow_findings(workflow)
    for job, step in steps:
        label = f"{job}/{step.get('name') or step.get('uses') or '?'}"
        findings += _step_field_findings(label, step)
        findings += _script_findings(label, str(step.get("run") or ""))
    return findings + _mask_order_findings(steps)


def _report_bundle() -> dict[str, Any]:
    import yaml

    loaded: dict[str, Any] = yaml.safe_load(_workflow("report-bundle.yml"))
    return loaded


def test_the_fulfillment_workflow_cannot_print_buyer_details() -> None:
    """The lint, on the real file. See pii_log_findings for what it checks."""
    assert pii_log_findings(_report_bundle()) == []


def test_no_workflow_takes_a_buyer_field_as_a_dispatch_input() -> None:
    """Not only the fulfillment workflow: any workflow_dispatch input of any
    workflow in a public repository is printed in that run's log."""
    import yaml

    for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
        declared = _dispatch_inputs(yaml.safe_load(path.read_text(encoding="utf-8")))
        leaked = sorted(set(declared) & set(BUYER_FIELDS))
        assert not leaked, f"{path.name} takes buyer field(s) {leaked} as dispatch inputs"


def _digest_step() -> dict[str, Any]:
    """The Daily run's feed-health digest step, the one scheduled step that reads
    real subscribers' addresses."""
    import yaml

    workflow = yaml.safe_load(_workflow("scorecard.yml"))
    found = [
        step
        for step in workflow["jobs"]["collect"]["steps"]
        if step.get("name") == "Send feed-health digest"
    ]
    assert len(found) == 1, "the digest step moved or was renamed; update this test with it"
    return dict(found[0])


def test_the_digest_step_keeps_its_sender_out_of_the_script_text() -> None:
    """A run log prints a step's script after expanding any expression in it, so
    a sender interpolated into the command is published. It travels through the
    environment instead, which the command reads itself. The command is still the
    sending one: a dry run prints every recipient."""
    step = _digest_step()
    run = str(step["run"])
    assert "${{" not in run, run
    assert "notify --send" in run, run
    assert "--from" not in run, run
    assert "SES_FROM" in (step.get("env") or {}), step.get("env")


def test_no_workflow_expands_the_sender_address_into_a_script() -> None:
    import yaml

    for path in sorted((ROOT / ".github" / "workflows").glob("*.y*ml")):
        for job, step in _steps(yaml.safe_load(path.read_text(encoding="utf-8"))):
            run = str(step.get("run") or "")
            assert "vars.SES_FROM" not in run, (
                f"{path.name} {job}/{step.get('name')} expands vars.SES_FROM into its script"
            )


def test_the_concurrency_group_is_per_order_and_names_only_the_reference() -> None:
    """GitHub keeps one pending run per concurrency group, so a shared group
    would let a third arrival evict a queued, paid order. Scoped per order, an
    eviction can only drop a duplicate run of the same build. The reference
    is random and not derived from the bundle id, so naming it here publishes
    nothing."""
    group = str((_report_bundle().get("concurrency") or {}).get("group") or "")
    assert group == "report-bundle-${{ inputs.order_ref }}", group


# The negative controls. Each one re-introduces a leak into the real file's
# text, proves the edit landed (a sabotage that silently no-ops would read as
# a pass), and requires the lint to report it.
_SABOTAGE = {
    "echo of a buyer variable": (
        "bundle_order email request.json manifest.json\n",
        'bundle_order email request.json manifest.json\n          echo "$BUYER_EMAIL"\n',
        'echo "$BUYER_EMAIL"',
    ),
    "a buyer field back as an input": (
        "  workflow_dispatch:\n    inputs:\n",
        "  workflow_dispatch:\n    inputs:\n      deliver_to:\n"
        '        description: "x"\n        required: false\n        type: string\n',
        "deliver_to",
    ),
    "a buyer input carried in env": (
        "          ORDER_REF: ${{ inputs.order_ref }}\n        run: |\n"
        '          set -euo pipefail\n          aws s3 cp "s3://',
        "          ORDER_REF: ${{ inputs.order_ref }}\n"
        "          DELIVER_TO: ${{ inputs.deliver_to }}\n        run: |\n"
        '          set -euo pipefail\n          aws s3 cp "s3://',
        "DELIVER_TO",
    ),
    "xtrace": (
        '          set -euo pipefail\n          aws s3 cp "s3://${ARTIFACTS_BUCKET}/program-requests/',
        '          set -euxo pipefail\n          aws s3 cp "s3://${ARTIFACTS_BUCKET}/program-requests/',
        "set -euxo pipefail",
    ),
    "verbose curl": (
        "          : > unhydrated.txt\n",
        "          curl -v https://example.org/ping\n          : > unhydrated.txt\n",
        "curl -v",
    ),
    "the order read before it is masked": (
        "          uv run python -m scorecard_pipeline.bundle_order mask request.json\n",
        "          jq . request.json\n"
        "          uv run python -m scorecard_pipeline.bundle_order mask request.json\n",
        "jq . request.json",
    ),
    "the download link on a command line": (
        "bundle_order email request.json manifest.json\n",
        "bundle_order email request.json manifest.json "
        '--download-url "${BUNDLE_API_BASE}/download/x"\n',
        "--download-url",
    ),
}


@pytest.mark.parametrize("case", sorted(_SABOTAGE))
def test_the_lint_catches_each_leak_put_back(case: str) -> None:
    import yaml

    anchor, replacement, marker = _SABOTAGE[case]
    raw = _workflow("report-bundle.yml")
    assert raw.count(anchor) == 1, f"the sabotage anchor for {case!r} no longer matches the file"
    mutated_text = raw.replace(anchor, replacement)
    assert mutated_text != raw and marker in mutated_text
    assert pii_log_findings(yaml.safe_load(raw)) == [], "the control needs a clean baseline"
    mutated: dict[str, Any] = yaml.safe_load(mutated_text)
    # The mutation reached the parsed workflow, not just the text.
    assert any(marker in s for s in _strings(mutated)), f"{case!r} did not survive parsing"
    findings = pii_log_findings(mutated)
    assert findings, f"the lint did not notice {case}"


def test_the_lint_catches_an_echo_of_the_buyer_address_in_any_form() -> None:
    """The specific regression named in the incident: an `echo "$BUYER_EMAIL"`
    reintroduced anywhere. Braced, unbraced, printf and a summary write are
    all the same leak."""
    base = _report_bundle()
    for line in (
        'echo "$BUYER_EMAIL"',
        'echo "sent to ${BUYER_EMAIL}"',
        'printf "%s\\n" "$DELIVER_TO"',
        'echo "$PROGRAM_NAME" >> "$GITHUB_STEP_SUMMARY"',
        'echo "::notice::link ${DOWNLOAD_URL}"',
    ):
        mutated = copy.deepcopy(base)
        step = next(s for _j, s in _steps(mutated) if s.get("name") == "Email the download link")
        step["run"] = f"{step['run']}{line}\n"
        assert line in step["run"] and line not in json.dumps(base, default=str)
        findings = pii_log_findings(mutated)
        assert any(" prints $" in finding for finding in findings), f"the lint missed: {line}"


def test_the_delivery_email_is_built_from_the_stored_order() -> None:
    """The refund promise is computed once, in the Lambda, and travels inside
    the stored order: setup_handler stores ``promised_by``, bundle_order's
    email command reads it back, and test_bundle_order.py holds the email to
    printing it. What this pins is the step between them. It must hand the
    email command the collected order, or every delivery email would ship
    without the date it was due and nothing would fail."""
    run = str(_named_step("Email the download link")["run"])
    assert "bundle_order email request.json manifest.json" in run


def test_the_watchdog_watches_the_workflow_that_delivers_paid_orders() -> None:
    """report-bundle.yml fulfills a purchase, and nothing else notices it fail.

    It is dispatched rather than scheduled, so there is no cadence for a
    staleness check to bite on and no published page that looks wrong when it
    stops. A failed run means a buyer paid, was told the build had started,
    and will receive nothing -- visible only to somebody who opens the
    Actions tab.

    The two conclusions this check has to keep apart are the point of it:
    an empty run list is the normal state before the first sale and must
    pass, while a `gh` call that could not answer must fail. The
    `|| echo '[]'` idiom the other two steps use cannot tell them apart, so
    this one reads `gh`'s own exit status instead.
    """
    workflow = _workflow("watchdog.yml")
    watch = workflow[workflow.index("  watch:") : workflow.index("  production-lighthouse:")]
    step_at = watch.index("The most recent program report bundle run did not fail")
    step = watch[step_at:]

    assert "--workflow report-bundle.yml" in step
    assert "set -euo pipefail" in step
    assert "if ! latest=$(gh run list" in step, (
        "the call's own failure must be distinguishable from an empty result"
    )
    assert "Could not read the Program report bundle run list" in step
    assert "jq 'length'" in step and "-eq 0" in step, (
        "a repository with no completed bundle runs has sold nothing and is healthy"
    )
    assert '[ -z "$conclusion" ]' in step, (
        "an unreadable run list must be an error, not an implied pass"
    )


def test_a_failed_paid_bundle_run_says_so_without_naming_the_order() -> None:
    """The failure of a paid fulfillment run has to be visible, and the way it
    is made visible has to be one that works.

    A failed render used to leave no trace anybody reads: the setup form had
    already told the buyer the build was starting, the delivery email only
    exists on the success path, and the capability row is removed by its
    30-day TTL.

    Two rules hold the repair. The annotation and summary are public, so they
    carry no bundle id -- the generic rules above forbid it and this pins the
    arrangement. And there is no alert email: the address this step used to
    mail is on a domain with no MX record, so it was delivered nowhere, and a
    notification that cannot arrive is the same defect as no notification. The
    channels that do work are watchdog.yml, which reads this workflow's
    conclusion every six hours, and the daily reconciler's issue.
    """
    workflow = _workflow("report-bundle.yml")
    assert "if: ${{ failure() }}" in workflow, (
        "a run that fulfills a paid order must say so when it fails"
    )
    say_at = workflow.index("Say that a paid order failed")
    say = workflow[say_at:]
    assert "::error::" in say
    assert "$GITHUB_STEP_SUMMARY" in say
    assert "this log is public" in say, "the reason the order is not named belongs next to it"
    assert "aws ses send-email" not in say, (
        "the alert address has no MX record, so mailing it is alerting that reaches nobody"
    )

    # And nowhere else in this workflow either. The one send that remains is
    # the delivery email, which goes to the buyer's own address on the success
    # path; an alert to the sending identity is the shape this forbids.
    for block in workflow.split("      - name: "):
        if "send-email" in block or "bundle-email" in block:
            assert '--to "$SES_FROM"' not in block, (
                "mailing the sending identity is a send that succeeds and a delivery that does not"
            )


# ---------------------------------------------------------------------------
# report-bundle.yml: "I could not read it" must not reach a buyer as
# "that agency has not published one"
# ---------------------------------------------------------------------------

_BASH = shutil.which("bash") or "/bin/bash"


def _hydrate_step() -> dict[str, Any]:
    for _job, step in _steps(_report_bundle()):
        if str(step.get("name") or "") == "Hydrate the requested artifacts from S3":
            return step
    raise AssertionError("report-bundle.yml no longer hydrates the requested artifacts")


def _run_hydrate(
    tmp_path: Path, ids: list[str], *, blips: set[str]
) -> subprocess.CompletedProcess[str]:
    """Run the hydrate step with a stubbed `aws`, `jq` and `sleep`.

    `blips` are the ids the stub fails on the way a transient S3 error fails
    (no 404 in the message); every other id answers 404. Running the script is
    the point: what is being tested is which of those two answers reaches the
    buyer, and that is a decision the shell makes.
    """
    work = tmp_path / "pipeline"
    (work / ".." / "data" / "artifacts").resolve().mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    (work / "plan.json").write_text(json.dumps({"current": ids, "refused": []}))
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    (stubs / "aws").write_text(
        "#!/bin/sh\n"
        'for arg in "$@"; do case "$arg" in s3://*) key="$arg";; esac; done\n'
        'case "$key" in\n'
        "  *index.json) exit 0 ;;\n"
        f"  {'|'.join(f'*/{blip}/*' for blip in sorted(blips)) or '__none__'})\n"
        '    echo "download failed: Connection reset by peer" >&2; exit 1 ;;\n'
        "  *)\n"
        '    echo "fatal error: An error occurred (404) when calling the HeadObject operation: '
        'Not Found" >&2; exit 1 ;;\n'
        "esac\n"
    )
    (stubs / "sleep").write_text("#!/bin/sh\nexit 0\n")
    for stub in stubs.iterdir():
        stub.chmod(0o755)
    summary = tmp_path / "summary.md"
    done = subprocess.run(  # noqa: S603 - fixed shell and a repository-owned workflow step
        [_BASH, "-c", str(_hydrate_step()["run"])],
        cwd=work,
        env={
            **os.environ,
            "PATH": f"{stubs}:{os.environ['PATH']}",
            "ARTIFACTS_BUCKET": "example-artifacts",
            "GITHUB_STEP_SUMMARY": str(summary),
        },
        capture_output=True,
        text=True,
    )
    done.stdout += summary.read_text() if summary.exists() else ""
    return done


def test_an_agency_s3_never_published_still_builds_the_bundle(tmp_path: Path) -> None:
    """A 404 is S3 answering. That agency has no published artifact, the
    manifest says so, and the other reports are still worth delivering."""
    done = _run_hydrate(tmp_path, ["alpha", "beta"], blips=set())
    assert done.returncode == 0, done.stderr
    assert "not published" in done.stdout
    assert (tmp_path / "pipeline" / "unhydrated.txt").read_text().split() == ["alpha", "beta"]


def test_an_artifact_s3_would_not_answer_for_does_not_ship_as_not_published(
    tmp_path: Path,
) -> None:
    """The defect this closes, run end to end.

    `scorecard bundle` classifies an id with no artifact on disk as
    `not_published`, and the manifest and delivery email print the reason as
    "tracked, but no scorecard is published for it yet". After three failed
    reads of our own bucket that sentence is a claim about the agency
    manufactured from a failed read, and the buyer -- who is paying for a
    judgment about exactly that agency's data -- cannot tell it apart from
    the true one. The run fails instead, which is recoverable: a re-run with
    the same inputs fills the same S3 key behind the same link.
    """
    done = _run_hydrate(tmp_path, ["alpha", "beta"], blips={"beta"})
    assert done.returncode != 0, "a bundle was built on an S3 read that never answered"
    assert "::error::" in done.stdout
    assert (tmp_path / "pipeline" / "unreadable.txt").read_text().split() == ["beta"]
    # The id is a paying program's caseload and the summary is public.
    assert "beta" not in done.stdout.split("::error::")[-1].split("\n")[0]
    assert "- beta" not in done.stdout


# report-bundle.yml: an uploaded archive that cannot be emailed is not delivered
# ---------------------------------------------------------------------------


def _named_step(name: str) -> dict[str, Any]:
    for _job, step in _steps(_report_bundle()):
        if str(step.get("name") or "") == name:
            return step
    raise AssertionError(f"report-bundle.yml no longer has a {name!r} step")


def _run_named_step(name: str, tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    """Run one step's own script with `uv` and `aws` stubbed.

    The script is executed rather than pattern-matched, because what is being
    checked is a decision it makes at run time: whether it proceeds, and
    whether it fails when it cannot. The stubs record their arguments, so "no
    email was attempted" is an observation and not an inference.
    """
    stubs = tmp_path / "stubs"
    stubs.mkdir(parents=True)
    for tool in ("uv", "aws"):
        (stubs / tool).write_text(f'#!/bin/sh\nprintf "{tool} %s\\n" "$*" >> "$STUB_LOG"\nexit 0\n')
        (stubs / tool).chmod(0o755)
    log = tmp_path / "stub.log"
    environment = {
        **os.environ,
        "PATH": f"{stubs}:{os.environ['PATH']}",
        "STUB_LOG": str(log),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "summary.md"),
        **env,
    }
    done = subprocess.run(  # noqa: S603 - fixed shell and a repository-owned workflow step
        [_BASH, "-c", str(_named_step(name)["run"])],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    done.stdout = done.stdout + (log.read_text() if log.exists() else "")
    return done


_GATE = "Refuse to start without the delivery configuration"
_CONFIGURED = {
    "ARTIFACTS_BUCKET": "example-artifacts",
    "BUNDLE_API_BASE": "https://api.example/",
    "SES_FROM": "reports@example",
    "ORDER_REF": "f" * 32,
}


def test_the_delivery_configuration_is_checked_before_anything_runs() -> None:
    """A missing delivery variable must fail the run, not skip a step.

    Gated in a step's `if:`, a blank BUNDLE_API_BASE or SES_FROM skipped the
    send, the job ended green, and the archive sat in S3 -- which is the only
    thing the daily reconciler looks at (`_capability_finding` asks S3 whether
    the object exists). One deleted repository variable would have stopped
    delivery for every paid order without a red run, an alarm or a finding.
    So the check is the first step, and no delivery step is conditional.
    """
    steps = [step for _job, step in _steps(_report_bundle())]
    assert str(steps[0].get("name") or "") == _GATE, "the configuration gate must run first"
    assert "if" not in steps[0]
    for name in ("Upload the archive behind its capability key", "Email the download link"):
        condition = str(_named_step(name).get("if") or "")
        assert not condition, f"{name!r} is conditional ({condition}); a skip reads as delivered"


def test_a_blank_delivery_route_fails_the_run_and_sends_nothing(tmp_path: Path) -> None:
    """Run the gate. Any blank variable: non-zero exit, an annotation saying
    why, and no tool invoked."""
    for blank in ("ARTIFACTS_BUCKET", "BUNDLE_API_BASE", "SES_FROM"):
        env = {**_CONFIGURED, blank: ""}
        done = _run_named_step(_GATE, tmp_path / blank, **env)
        assert done.returncode != 0, f"a blank {blank} left the run green"
        assert "::error::" in done.stdout, f"a blank {blank} failed without saying why"
        assert "uv " not in done.stdout and "aws " not in done.stdout


def test_the_gate_refuses_anything_but_an_order_reference(tmp_path: Path) -> None:
    """The reference is interpolated into an S3 key and printed in the failure
    summary, so a value that is not 32 lowercase hex characters never gets
    that far -- including one a person pasted a buyer's address into."""
    for n, bad in enumerate(("", "F" * 32, "f" * 31, "buyer@example.org", "../" + "f" * 29)):
        done = _run_named_step(_GATE, tmp_path / str(n), **{**_CONFIGURED, "ORDER_REF": bad})
        assert done.returncode != 0, f"the gate accepted {bad!r}"
        assert bad == "" or bad not in done.stdout.split("::error::")[-1]
    ok = _run_named_step(_GATE, tmp_path / "ok", **_CONFIGURED)
    assert ok.returncode == 0, ok.stderr


def test_the_email_step_builds_the_link_inside_python(tmp_path: Path) -> None:
    """The download link and the buyer's address never appear on a command
    line or in the step's environment: the step names two files, and the
    stored order and the environment supply the rest inside Python. A guard
    that also broke the send would be worse than the hole it closes, so the
    send is observed too."""
    step = _named_step("Email the download link")
    assert set(step.get("env") or {}) == {"BUNDLE_API_BASE", "SES_FROM"}
    done = _run_named_step("Email the download link", tmp_path, **_CONFIGURED)
    assert done.returncode == 0, done.stderr
    assert (
        "uv run --with boto3 python -m scorecard_pipeline.bundle_order email "
        "request.json manifest.json"
    ) in done.stdout
    assert "/download/" not in done.stdout and "--download-url" not in done.stdout


def test_the_built_archive_is_never_kept_on_the_run() -> None:
    """A run artifact of this repository is published, and the bundle is not.

    The archive is the paid deliverable. Its README.txt and manifest.json both
    print the 32-hex bundle id, which is the download capability that fetches
    it from S3 for thirty days (setup_handler: "the capability in the email is
    the credential"), and request.json names the buyer. This repository is
    public: every signed-in GitHub account has read access, so every one of
    them could download that artifact for its whole retention window, and the
    REST artifact listing answers with no token at all.
    """
    workflow = _report_bundle()
    for job, step in _steps(workflow):
        uses = str(step.get("uses") or "")
        assert "upload-artifact" not in uses, (
            f"{job}/{step.get('name')} publishes a run artifact; a run artifact of a public "
            "repository is published, and the bundle archive is a paid deliverable that "
            "carries its own download capability"
        )
        paths = str((step.get("with") or {}).get("path") or "")
        for built in ("bundle.zip", "manifest.json", "request.json"):
            assert built not in paths, f"{job}/{step.get('name')} publishes {built}"

    # And no summary tells a reader to go and get it there.
    raw = _workflow("report-bundle.yml")
    assert "attached to this run" not in raw.replace("is not attached to this run", "")
