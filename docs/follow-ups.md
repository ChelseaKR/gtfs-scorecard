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
   artifacts, and today/yesterday dated snapshots before rendering. It validates
   each index/latest pair and materializes a missing current dated record from
   those same bytes, so stale-but-current citations still resolve after bounded
   hydration or lifecycle retention. Complete trends live in `index.json`;
   older records and corrected ZIPs remain on the artifact CDN, keeping
   deployments bounded as the archive grows.
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

**Status: deferred, and not a plain `terraform apply`.** At ~2,261 configured feeds the
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

**Status: deferred; scoring is unblocked with an explicit measurement gap.** The
gtfs.de Germany-wide aggregate and the Swiss national timetable have a
`stop_times.txt` of 1.9 GiB and 2.4 GiB. Scorecard's whole-table reader
(`gtfs.py`) caps a single table at 1 GiB (`MAX_MEMBER_BYTES`). Raising the cap is
not safe: loading a 2.4 GiB table whole risks a Python out-of-memory even on a
16 GiB runner. The daily pipeline now publishes the graded scorecard and marks
the zero-deduction routability block unmeasured with reason `table_too_large`.

Consumers of `stop_times.txt` in the daily scoring path: `ferry_profile`
(already made to skip an oversized table), `routability`, and the realtime
readers `rt_drift` and `rt` (only for feeds that publish realtime). All are
zero-deduction and descriptive, so none changes a grade.

The remaining improvement is:

1. **Stream the table.** Give `gtfs.py` a row-iterating reader for the large
   tables and move each consumer above to the aggregates it actually needs
   (counts, per-trip first/last stop). Memory-safe and accurate. Raises the
   tool's ceiling so it can score a national feed. The larger change.

Until streaming ships, these aggregates are scored but do not claim the two
router-free checks over `stop_times.txt`. Verkehrsverbund Rhein-Neckar, whose
largest table fits the cap, continues to receive those checks.

## Reduce `/compare/`, then tighten its Lighthouse aggregation

**Status: open, opened 2026-08-10.** [ADR 0045](decisions/0045-lighthouse-lcp-budget-and-warmup-run.md)
left `lighthouserc.routes.json` untouched rather than lowering its performance
floor to 0.75 to make a real regression pass. `/compare/` slowed measurably on 2026-08-07: median LCP
went from 3077 ms to 3454 ms and median performance from 0.895 to 0.850, between
runs 31139147660 and 31139709133. About a fifth of `/compare/` runs now land near
4053 ms, a mode absent before that date. The old floor kept passing only because
`aggregationMethod: "median-run"` silently asserts category scores as best-of-N;
switching the routes floor to a true median would fail 5 of 50 recent jobs until
the page is reduced. Both configs run in the same required `axe` job, so
tightening before fixing would block every merge rather than flag one page.

Steps:

1. Diff what `/compare/` loads across those two commits. The step coincides with
   the artifacts snapshot refresh to the live corpus, so the first suspect is
   payload growth in the data the page carries, not the page's own code. The
   page currently ships about 94 KB of HTML against the home page's 8 KB, and
   that payload grows with the registry, so the number will keep moving.
2. Reduce the payload, then confirm median `/compare/` performance clears 0.80
   over several `a11y.yml` jobs.
3. Only then switch the routes config to `aggregationMethod: "median"`, keeping
   the floor at 0.80, and update ADR 0045 and the
   [conformance gaps](standards-conformance-gaps.md) entry.

The floor stays at 0.80 throughout. What is deferred is the tightening, not the
standard.

## Decide the share-alike question for records already listed

**Status: open, opened 2026-09-01.** Two findings from the 2026-09-01 coverage
pass are the same question, and neither is safe to settle inside a wave whose
job was adding records.

**France and ODbL.** 158 French records in the registry cite ODbL in their
`license_note`, including entries in `registry/fr/idf.yaml`, while
[`docs/feeds.md`](feeds.md) records ODbL French datasets as *excluded* and names
Île-de-France as an example of the exclusion. Both cannot be right. The records
arrived in the 2026-07-23 National Access Point pass; the exclusion predates it.

**Estonia and CC BY-SA 3.0.** Estonia's national Public Transport Register is
published under CC BY-SA 3.0 on the national open-data portal, and the
`terms_url` carried by `estonia-public-transport-register` and
`tallinn-public-transport-tlt` now returns 404.

The 2026-09-01 pass applied the strict reading to new admissions and changed
nothing already listed. That cost roughly 84 ODbL French datasets (Tisséo
Toulouse, STAR Rennes, TAG Grenoble among them) and 19 Estonian county feeds,
all of which pass every other gate.

What has to be decided, once, for both:

1. Does this project redistribute share-alike GTFS? The gates say no. The
   registry says yes for 160 records.
2. If yes, `docs/feeds.md` and the admission gates need amending, and the ~103
   deferred datasets become admissible.
3. If no, the 160 existing records need retiring, which reduces published
   coverage and unpublishes live scorecards. That is a listing-policy action,
   not a curation one, and the affected agencies should be handled under
   [`listing-policy.md`](listing-policy.md).

Do not resolve this by editing one side quietly to match the other.

## Teach `discover` to check its own replacement candidate

**Status: open, opened 2026-09-01.** All five feeds that
[`feed-discovery.md`](feed-discovery.md) lists under "Likely replaced" were
re-checked on 2026-09-01: every tracked URL the repo uses is live and serving a
zip, and two of the proposed replacements are not (MVV München's candidate
returns 404, Rockford's refuses the connection). Applying that report
unreviewed, or running `scorecard discover --apply` against it, would swap two
working feeds for dead links.

The report is already written as suggestions to verify by hand, which is what
saved it. A HEAD check on the candidate before listing it under "Likely
replaced" would stop a dead replacement being proposed at all.

## Feed sources blocked by the pipeline's HTTP client, not by policy

**Status: open, opened 2026-09-01.** Several feeds pass source, licence,
identity and calendar and fail only on how this pipeline fetches:

- **Yamaguchi (JP-35)**, one of the two remaining empty Japanese prefectures.
  Iwakuni City and Hikari City publish official, CC BY, keyless, in-date feeds
  on the prefecture's CKAN. `curl` fetches them; the pipeline's client refuses
  the handshake with `TLSV1_ALERT_INSUFFICIENT_SECURITY`.
- **Grand River Transit (CA-ON)**: `webapps.regionofwaterloo.ca` offers a DH key
  the client refuses, and the catalog mirror 403s.
- **Canberra (AU-ACT)**: `transport.act.gov.au` now answers every non-browser
  client with a Cloudflare interstitial, including with full browser headers.
  The licence is fine and `data.act.gov.au` names the exact archives.

These are worth separating from licence and freshness rejections when reading
coverage gaps: no amount of sourcing effort closes them.
