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
