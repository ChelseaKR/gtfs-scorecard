# Follow-ups

Deferred work with enough context to pick up later. Each item says why it is
not done yet and the concrete steps to finish it. Strategic framing for the two
big ones lives in `docs/roadmap.md`; this file is the operational checklist.

## S3 as the artifact source of truth (roadmap Year 1)

**Status: deferred.** The original driver was the daily run losing refreshes to
git push races. That is now fixed in code — shards publish only the agencies
they scored (no cross-shard clobber), and a rejected push replays the generated
files onto the latest `main` instead of rebasing (which conflicted on binary
artifacts like `web/api/v1/agencies.parquet`). With reliability handled, moving
artifacts off git is now just cleanup (keeping the repo from growing by a few
thousand JSON files a day) and is not urgent.

The validator cache already supports this move: `vcache.py` has an S3 tier
(`VALIDATOR_CACHE_BUCKET` / `ARTIFACTS_BUCKET`) so the cache survives once
`data/artifacts` stops being committed.

Remaining steps, in order:

1. **Pages read role.** Add an `aws_iam_role` in `infra/artifacts/github_oidc.tf`
   with only `s3:GetObject` + `s3:ListBucket` on the artifacts bucket, trusted
   for both `repo:ChelseaKR/gtfs-scorecard:ref:refs/heads/main` and
   `repo:ChelseaKR/gtfs-scorecard:environment:github-pages` (the deploy job sets
   `environment: github-pages`, which changes its OIDC `sub`). The existing
   deploy role is write-scoped; do not reuse it for the read-only Pages job.
   Output its ARN; store it as the `PAGES_AWS_ROLE_ARN` Actions secret.
2. **Assemble from S3 in `pages.yml`.** After the `cp -r data/artifacts`, add an
   AWS auth step (assume the read role) and
   `aws s3 sync s3://<bucket>/data/artifacts _site/data/artifacts`, gated on
   `vars.ARTIFACTS_BUCKET`. Keep the `cp` as a fallback so a fork or an S3 outage
   still serves the committed copy. Verify on one deploy that the site still has
   data before step 3.
3. **Stop committing `data/artifacts`** in the `collect` job (drop it from the
   `git add` path list). This is the cutover; only do it after step 2 is proven
   on a live deploy, since after it S3 is the sole source of the dated history
   the trend charts read. The S3 sync is already additive (no `--delete`).
4. **Lifecycle policy.** Add an S3 lifecycle rule to expire very old dated
   artifacts so the bucket stays bounded (the sync no longer prunes).

The web app's runtime data source does not change: it keeps reading same-origin
from Pages, so there is no CDN-staleness risk (see the note in
`web/src/config.js`). The prerendered SEO pages under `web/` still deploy via
Pages and stay committed.

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
