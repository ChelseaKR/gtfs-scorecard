# Follow-ups

Deferred work with enough context to pick up later. Each item says why it is
not done yet and the concrete steps to finish it. Strategic framing for the two
big ones lives in `docs/roadmap.md`; this file is the operational checklist.

## S3 as the artifact source of truth (roadmap Year 1)

**Status: steps 1 and 4 are applied in AWS and step 2 is wired; step 3 (the
actual cutover) waits for the first live-verified Pages sync — see below.** The original
driver was the daily run losing refreshes to git push races. That is now
fixed in code — shards publish only the agencies they scored (no cross-shard
clobber), and a rejected push replays the generated files onto the latest
`main` instead of rebasing (which conflicted on binary artifacts like
`web/api/v1/agencies.parquet`). With reliability handled, moving artifacts
off git is now just cleanup (keeping the repo from growing by a few thousand
JSON files a day) and is not urgent.

The validator cache already supports this move: `vcache.py` has an S3 tier
(`VALIDATOR_CACHE_BUCKET` / `ARTIFACTS_BUCKET`) so the cache survives once
`data/artifacts` stops being committed.

Steps, in order:

1. **Pages read role — done.** `aws_iam_role.pages_read` in
   `infra/artifacts/github_oidc.tf` grants only `s3:GetObject` +
   `s3:ListBucket` on the artifacts bucket, trusted for both
   `repo:ChelseaKR/gtfs-scorecard:ref:refs/heads/main` and
   `repo:ChelseaKR/gtfs-scorecard:environment:github-pages`. Its output
   `pages_read_role_arn` was applied on 2026-07-10 and stored as the
   `PAGES_AWS_ROLE_ARN` Actions secret.
2. **Assemble from S3 in `pages.yml` — wired, pending its first live verification.** Both the
   `lighthouse` and `deploy` jobs now sync `s3://<bucket>/data/artifacts` into
   `_site/data/artifacts` after the `cp -r data/artifacts` fallback, gated on
   `vars.ARTIFACTS_BUCKET` and non-fatal on failure (`|| echo "::warning
   ..."`). Corrected feed ZIPs stay on the artifact CDN and are excluded from
   Pages; only the 560 MiB public JSON/SVG/GeoJSON set is assembled. The role
   and secret now exist. Before step 3, trigger one deploy
   and confirm in the run log that
   the sync step actually authenticated and copied objects (not just skipped
   on the unset variable).
3. **Stop committing `data/artifacts`** in the `collect` job (drop it from the
   `git add` path list). **Not done — do not do this until step 2 is proven on
   a live deploy**, since after it S3 is the sole source of the dated history
   the trend charts read. The S3 sync is already additive (no `--delete`).
4. **Lifecycle policy — done.** `aws_s3_bucket_lifecycle_configuration.artifacts`
   in `infra/artifacts/main.tf` expires objects tagged `artifact-class=dated`
   after 400 days, plus a 30-day noncurrent-version expiration now that
   versioning is on. The collect job's "Tag today's dated artifacts" step
   (`scorecard.yml`) applies the tag to each day's `<agency>/<date>.json` as
   it's synced; `latest.json`, `badge.json`, `directory.json`, and the
   validator cache never match that filename pattern, so they're never tagged
   and never expire. The lifecycle configuration was applied on 2026-07-10.
   Artifact history synced to the bucket before this step
   existed stays untagged (and therefore un-expiring) until something
   re-touches it, which fails open rather than deleting unclassified history.

The web app's runtime data source does not change: it keeps reading same-origin
from Pages, so there is no CDN-staleness risk (see the note in
`web/src/config.js`). The prerendered SEO pages under `web/` still deploy via
Pages and stay committed for now.

**Fold in when executing step 3.** `docs/decisions/0030-data-plane-history-remediation.md`
(ADR 0030) decided that stopping `web/agency/**` from being committed —
building it in `pages.yml` from `render-site` instead, the same way `_site/`
is already assembled — should happen in the same cutover as step 3, so there
is one migration story instead of two. Add that `pages.yml` render step and
drop `web/agency/**` from the collect job's `git add` path list alongside step
3, not as a separate follow-up. ADR 0030 also covers (and rejects, for now) an
orphan `data` branch / separate data repo and any history rewrite — see that
ADR for the reasoning.

## Fan-out compute (`infra/compute`, roadmap Year 2)

**Status: deferred, and not a plain `terraform apply`.** At ~1,490 agencies the
GitHub Actions matrix handles the daily run in well under an hour, so this is
premature. More importantly, applying `infra/compute` stands up an EventBridge
schedule that would run the pipeline **in addition to** the Actions cron — two
schedulers, double runs, double cost — until the Actions schedule is removed. So
activating it is a migration, not an apply.

When the registry outgrows the Actions matrix, the cutover is:

1. Build the worker image from `pipeline/` and push it to ECR.
2. `terraform apply infra/compute` (EventBridge + SQS + container Lambda).
3. Wire the enqueue/worker path (`infra/compute/enqueue.py`, `worker.py`) and
   confirm a run end to end against the SQS queue.
4. **Remove the `schedule:` trigger from `.github/workflows/scorecard.yml`** so
   only one scheduler runs. Keep `workflow_dispatch` for manual runs.

See `docs/decisions/0003-fan-out-compute.md` for the original design.
