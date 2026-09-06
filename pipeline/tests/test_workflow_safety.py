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


def test_the_intraday_refresh_has_a_floor_under_its_rescore_loop() -> None:
    """`refresh.yml` deploys roughly nine times a day and turned every
    per-feed failure into an `echo`. Nothing counted them, so a cycle in which
    every changed feed failed to re-score still ran reindex, rollups,
    render-site, the S3 publish and the Pages deploy, and reported success.
    `scorecard.yml` has had a floor since #298; this tier had none at all
    (`grep -n '::error\\|exit 1' refresh.yml` returned nothing)."""
    workflow = _workflow("refresh.yml")
    step_at = workflow.index("Re-score only the feeds that changed")
    step = workflow[step_at : workflow.index("Rebuild index and rollups", step_at)]

    assert "::error::" in step, "a cycle that refreshed nothing must fail, not warn"
    assert "exit 1" in step
    assert '[ "$refreshed" -eq 0 ]' in step, (
        "the floor has to be counted from real per-feed outcomes, not inferred"
    )
    assert "::warning title=partial refresh::" in step, (
        "a partial refresh must still say how much of it was partial"
    )


def test_the_intraday_rescore_loop_tells_unchanged_apart_from_failed() -> None:
    """`scorecard run` reserves exit 2 for "the feed had not changed after
    all". `scorecard.yml` has always separated it; this loop treated every
    non-zero exit identically, which would make the new floor fire on a cycle
    where nothing needed doing the moment --skip-unchanged is added here."""
    workflow = _workflow("refresh.yml")
    step_at = workflow.index("Re-score only the feeds that changed")
    step = workflow[step_at : workflow.index("Rebuild index and rollups", step_at)]

    assert '[ "$EXIT" -eq 2 ]' in step


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
