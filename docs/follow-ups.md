# Follow-ups

Deferred work with enough context to pick up later. Each item says why it is
not done yet and the concrete steps to finish it. Strategic framing for the two
big ones lives in `docs/roadmap.md`; this file is the operational checklist.

## S3 as the artifact source of truth (roadmap Year 1)

**Status: complete as of 2026-07-10.** The original
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
2. **Assemble from S3 in `pages.yml` — done.** A live Pages job successfully
   assumed the read-only role. Pages hydrates the compact index, current agency
   artifacts, and newest two dated snapshots before rendering. Complete trends
   live in `index.json`; older records and corrected ZIPs remain on the artifact
   CDN, keeping deployments bounded as the archive grows.
3. **Stop committing generated data and pages — done.** Daily and intraday jobs
   publish score artifacts to S3. Pages renders the public tree in CI. Git keeps
   the cutover snapshot as an outage/fork fallback. The intraday job publishes
   `liveness.json` to S3, so no scheduled automation writes generated data to
   `main`. `publish.rebuild_index()` preserves compact
   S3-only trend points that are absent from a clean checkout.
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

The web app's runtime source remains same-origin Pages. The committed artifacts
and prerendered pages are the final cutover snapshot; future generated changes
deploy from CI without growing git history. ADR 0030 records why the existing
history is not rewritten.

## Fan-out compute (`infra/compute`, roadmap Year 2)

**Status: deferred, and not a plain `terraform apply`.** At ~1,748 configured feeds the
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

## Streaming reader for national-scale feeds

**Status: open. Two reviewed feeds cannot be scored today.** The gtfs.de
Germany-wide aggregate and the Swiss national timetable have a `stop_times.txt`
of 1.9 GiB and 2.4 GiB. Scorecard's own table reader (`gtfs.py`) loads a table
whole into memory and caps a single table at 1 GiB (`MAX_MEMBER_BYTES`), so any
metric that reads `stop_times.txt` this way raises `TableTooLargeError` and the
feed produces no scorecard. The archive-shape guard and the Java validator both
handle these feeds; only the in-memory table reader does not. Raising the cap is
not safe: loading a 2.4 GiB table whole risks a Python out-of-memory even on a
16 GiB runner.

Consumers of `stop_times.txt` in the daily scoring path: `ferry_profile`
(already made to skip an oversized table), `routability`, and the realtime
readers `rt_drift` and `rt` (only for feeds that publish realtime). All are
zero-deduction and descriptive, so none changes a grade.

Two ways forward, a product decision:

1. **Stream the table.** Give `gtfs.py` a row-iterating reader for the large
   tables and move each consumer above to the aggregates it actually needs
   (counts, per-trip first/last stop). Memory-safe and accurate. Raises the
   tool's ceiling so it can score a national feed. The larger change.
2. **Treat national aggregates as a distinct class.** Either mark their
   whole-table metrics "not assessed" with a stated reason, or keep national
   aggregates out of the small-agency-focused reviewed cohort. Smaller change,
   but it is a framing decision about what the scorecard measures.

Until one is chosen, these two feeds are curated but unscored, and the European
beta gate reports 99.2% of its reviewed cohort measured rather than 100%.
Verkehrsverbund Rhein-Neckar, whose largest table fits the cap, does score.
