# Deploy runbook

Everything in this repo runs for free on GitHub Actions plus GitHub Pages, and
that is how the pilot runs today. This file is for the optional AWS pieces that
the rollout roadmap (`docs/roadmap.md`) needs as the registry grows: the
feed-health email digest, the self-serve forms, and a CDN in front of the
published JSON.

All the code and Terraform for these is written and tested. None of it is
required to keep the site live.

Standing up your own branded instance rather than deploying the maintainer's?
Start at [docs/fork-quickstart.md](fork-quickstart.md); it sequences the
branding config (`instance.yaml`) and the deploy steps below in order.

> **Current deployment status (maintainer's account).** The artifacts CDN (§1)
> and the feed-health digest (§2) are applied and live: `gtfsscorecard.org` is
> verified in SES and out of the sandbox, and the daily workflow mirrors
> artifacts to S3 and sends the digest. The self-serve submission form (§3) is
> also applied and live. The fan-out compute (§4) and instant scoring (§5) are
> written but not yet applied. The steps below are the from-scratch runbook, so they still read as
> operator work to do — follow them for a fork or a clean rebuild, and skip
> the stacks that are already up.

## Who this is for

One operator with:

- An AWS account and credentials configured locally (`aws configure` or SSO).
- `terraform` >= 1.5 and the `aws` CLI installed.
- Admin (or close) on the `ChelseaKR/gtfs-scorecard` repo, to set Actions
  variables and secrets.

The five stacks use **local** Terraform state by design, except `artifacts`,
which keeps state in S3. They are independent; apply only the ones you want.

## What turns each feature on

The daily workflow (`.github/workflows/scorecard.yml`) already has the deploy
steps. They are gated on repository **variables**, so they stay off until you
set them, and forks keep working with nothing set:

| Feature | Set this Actions variable | Also needs |
| --- | --- | --- |
| Mirror artifacts to the CDN bucket | `ARTIFACTS_BUCKET` | `AWS_ROLE_ARN` secret, `infra/artifacts` applied |
| Send the feed-health email digest | `SES_FROM` | a verified SES sender, `infra/alerts` applied |
| AWS region (optional) | `AWS_REGION` | defaults to `us-west-2` |

Set variables and secrets under **Settings → Secrets and variables → Actions**.

## 0. One-time: remote state bucket (only for `artifacts`)

`infra/artifacts/backend.tf` keeps Terraform state in an S3 bucket named
`gtfs-scorecard-tfstate-ckr`. Create it once before the first apply (skip if it
exists):

```sh
aws s3api create-bucket --bucket gtfs-scorecard-tfstate-ckr \
  --region us-west-2 --create-bucket-configuration LocationConstraint=us-west-2
aws s3api put-bucket-versioning --bucket gtfs-scorecard-tfstate-ckr \
  --versioning-configuration Status=Enabled
```

Use a different name if that one is taken, and update `backend.tf` to match.

## 1. Artifacts CDN (`infra/artifacts`)

Serves the published JSON from S3 + CloudFront instead of from Pages. Optional;
Pages carries the pilot fine.

```sh
cd infra/artifacts
cp terraform.tfvars.example terraform.tfvars   # edit bucket_name to be globally unique
terraform init
terraform apply
```

Then:

1. Read the outputs: `bucket_name` and `cdn_domain`.
2. Set the `ARTIFACTS_BUCKET` Actions variable to `bucket_name` and the
   `AWS_ROLE_ARN` secret to the OIDC role this stack creates. The next daily run
   mirrors `data/artifacts` to the bucket.
3. To point the web app at the CDN, set `window.SCORECARD_DATA_BASE` in
   `web/src/config.js` to `https://<cdn_domain>/data/artifacts`. The JSON
   contract is unchanged, so this is the only frontend change. Leaving it unset
   keeps the app reading from Pages.
4. **Forks:** set the `ARTIFACTS_CDN` Actions variable to your `cdn_domain`.
   When `ARTIFACTS_BUCKET` is set but `ARTIFACTS_CDN` is not, the daily
   workflow's CDN privacy canary falls back to the maintainer's CloudFront
   domain, which a fork does not want to inherit.

### How the daily run decides what to upload

The daily publish step does not use `aws s3 sync`. That command transfers a
file whenever the local modification time is newer than the object, and CI
checks the repository out fresh every run, so it re-uploaded all ~28,700
published objects each day to change about 3,100 of them.

`scorecard publish-artifacts` replaces it. It lists the destination prefix once
and compares each local file's MD5 against the object's ETag. The bucket uses
SSE-S3 and the command writes with a single `PutObject`, so a published
object's ETag is the MD5 of its bytes. A file is skipped only when its size and
its hash both match. A missing object, a different size, an ETag that is not a
content MD5, or a hash mismatch all upload. Measured against the live bucket,
that skips about 89% of the daily uploads and still publishes every change,
including the ones that keep the same byte length. `--size-only` would have cut
the same requests but would silently stop publishing a re-score whose length
did not change, so it is not used anywhere and a test in
`pipeline/tests/test_workflow_safety.py` keeps it out.

The same command applies the generated
`data/artifacts/.retired-current-artifacts.json` control manifest. Reindex
writes only sorted retired agency ids; the publisher expands them into the
fixed mutable names `latest.json`, `badge.json`, `badge.svg`,
`conformance.json`, `mark.svg`, and `geometry.geojson`. It rejects a manifest
that names a current canonical id or conflicts with a local file. This is not a
general `--delete`: date-shaped score evidence and every other S3 key remain
outside the deletion surface. Daily, intraday, and targeted activation runs
all apply the same cleanup while holding the shared artifact-publish lock.

A useful side effect: the bucket's `expire-dated-artifacts` lifecycle rule
matches objects tagged `artifact-class=dated`, and rewriting an object drops
its tags and restarts its age. While every dated artifact was rewritten daily,
none of them could ever reach the 400-day expiry. Dated artifacts that stop
being rewritten keep the tag the run that created them applied.

### One-time validator-cache privacy migration

Deployments created before the validator cache moved to the private
`cache/validator/` prefix may still contain
`data/artifacts/<agency>/validator-cache.json` objects. Upgrade in this order:

1. Apply `infra/artifacts` so the CloudFront viewer function and S3 origin
   policy deny the legacy key shape.
2. Deploy the current Pages workflow. It publishes an explicit file allowlist.
   Raw validator caches, structural fingerprints, finding-clearance state, and
   generated feed copies remain private; the renderer still turns reconciled
   receipts into public HTML.
3. Remove the old public-path objects from S3. The daily, intraday, and targeted
   publishers do this idempotently; an operator can perform the cleanup
   immediately with:

   ```sh
     aws s3 rm "s3://${ARTIFACTS_BUCKET}/data/artifacts" --recursive \
       --exclude "*" --include "*/validator-cache.json" \
       --include "*/structure.json" --include "*/fixlog.json" \
       --include "*/corrected.zip"
   ```

4. Verify a current `latest.json` returns HTTP 200 and the four former internal
   paths return HTTP 403 or 404 through the CDN. The daily workflow runs this
   public/private canary after each publication.

## 2. Feed-health email digest (`infra/alerts` + SES)

This is the highest-value piece: it emails an agency before its feed silently
expires. The subscribe API (double opt-in) and the send path are already built;
the send is off until you verify a sender and set `SES_FROM`.

1. **Verify a sender in SES.** Verify the domain `gtfsscorecard.org` (DKIM) or a
   single address like `alerts@gtfsscorecard.org`. A new SES account starts in
   the sandbox, which only sends to verified addresses; request production
   access before sending to real agencies.
2. **Apply the subscribe API** (if not already live):
   ```sh
   cd infra/alerts
   terraform init
   terraform apply -var ses_from=alerts@gtfsscorecard.org
   ```
   The `subscribe_url` output is the endpoint the web form posts to; it is
   already wired into `web/src/config.js`.
3. **Turn on sending.** Set the `SES_FROM` Actions variable to your verified
   sender. The daily `collect` job then runs
   `scorecard notify --send --from "$SES_FROM"` for confirmed subscribers only.
4. **Dry run first.** Locally, `scorecard notify` (no `--send`) reports how many
   emails would go out and to whom, without sending. Always check this before
   enabling the variable.

## 3. Self-serve submission form (`infra/submit`)

Lets an agency add itself from `web/submit.html` without manually opening a pull request.
The maintainer's endpoint is applied and wired into `web/src/config.js`; the
commands below are for a fork or clean rebuild. The service opens the pull
request on the submitter's behalf so a person still reviews every addition.

```sh
cd infra/submit
terraform init
terraform apply -var github_repo=ChelseaKR/gtfs-scorecard -var github_token=<PAT>
```

The `submit_url` output is the endpoint; wire it into the form's config the same
way the subscribe URL is wired. The `github_token` is a fine-grained PAT that can
open pull requests on this repo.

## 4. Fan-out compute (`infra/compute`, Year 2)

Only needed when the daily run outgrows the Actions matrix. EventBridge + SQS +
a container-image Lambda built from `pipeline/`. See
`docs/decisions/0003-fan-out-compute.md`; apply it the same way when the time
comes.

## 5. Instant scoring (`infra/instant-score`)

Scores any GTFS URL on demand for `web/try.html`: a container-image Lambda
(the same JVM base as `compute/`) behind API Gateway, with a DynamoDB jobs
table, per-IP rate limiting, explicit country context passed to the validator,
and a reserved concurrency cap. The public form requires a country; only
omitted legacy HTTP requests default to `US`. This is the one
deliberate exception to the cost ceiling (roughly $20-60/month at demo-era
volume); the funnel case and the guardrails are in
`docs/decisions/0029-instant-score-funnel.md`. Build and push the image, then:

```sh
cd infra/instant-score
terraform init
terraform apply -var image_uri=<ECR image> -var artifacts_bucket=<bucket>
```

The `instant_score_url` output is the endpoint `web/try.html` posts to; wire
it into `web/src/config.js` like the subscribe URL. Until it is applied, the
page's inline form stays disabled and falls back to the GitHub Issue Form
path (`onboard.yml`).

## 6. Program report bundle (`infra/program-bundle`)

The paid program tier's plumbing. Its runbook, including the Stripe test-mode
setup, the secrets, the apply, the end-to-end check, and the one file that
turns the tier on, lives in [program-plan.md](program-plan.md) so the whole
commercial decision reads in one place. Nothing in this section is needed to
keep the site up.

## Scheduled jobs (GitHub Actions, no AWS needed)

The runbook above covers the AWS stacks. Day-to-day operations run entirely in
Actions; this is the inventory an operator should know exists:

| Workflow | Cadence | What it does |
| --- | --- | --- |
| `scorecard.yml` | daily | The full sharded re-score, commit, deploy, optional S3 mirror and SES digest. |
| `refresh.yml` | every 3 h | Cheap intraday tier: change/down detection by conditional GET, no validator (ADR 0010). |
| `targeted-score.yml` | manual | Activates up to 25 reviewed registry agencies against the authoritative S3 corpus, then deploys. |
| `rt-monitor.yml` | every 3 h | Short realtime sampling burst across agencies into `data/rt-health` (ADR 0012). |
| `rt-archive.yml` | manual | Bounded high-resolution realtime polling session for one agency (ADR 0012). |
| `watchdog.yml` | every 6 h + weekly | Independent uptime and freshness checks, plus the weekly production Lighthouse run; no AWS dependency. |
| `discover.yml` | weekly | Checks expired feeds against the Mobility Database; opens PRs for moved URLs. |
| `equity.yml` | weekly | Refreshes the US equity overlay from Census ACS (ADR 0015). |
| `canada-equity.yml` | monthly | Refreshes the Canada overlay from StatCan CIMD (ADR 0027). |
| `otp-qa.yml` | weekly | Routing QA against containerized OpenTripPlanner (ADR 0014). |
| `dataset-release.yml` | monthly | Tags the citable `dataset-YYYY-MM` release with the flat exports. |
| `onboard.yml` | on issue | Scores a feed from a "score-request" issue and comments the scorecard. |
| `validator-canary.yml` | manual | Shadow-scores a candidate validator version for governed upgrades. |
| `tiles.yml` | manual | Rebuilds the national PMTiles route archive (needs tippecanoe). |
| `mutation.yml` | weekly | Advisory mutation testing of the scoring math. |
| `ci.yml`, `a11y.yml`, `e2e.yml`, `security.yml`, `pages.yml` | push/PR | The merge and deploy gates. |

The monthly dataset release has two hosting prerequisites: repository-level
immutable releases must remain enabled, and `SCHEDULED_WRITER_SSH_KEY` must
match the trusted public key in `.github/release-signers`. The signing secret is
available only to the tag-creation step and is removed from the runner before
bundle assembly. The workflow creates an SSH-signed annotated `dataset-YYYY-MM`
tag, verifies the local signature and hosted tag object, and then consumes the
selected successful Daily run's exact `github-pages` artifact. An intraday
deployment cannot replace that run-bound source.

Actions deliberately stops at a byte-verified draft because its repository
token cannot read the administration-only immutable-release setting. After a
successful run, an owner with an administration-capable `gh` credential checks
out clean, current `main` and runs the exact command printed in the job summary:

```sh
pipeline/scripts/promote_dataset_release.sh dataset-YYYY-MM WORKFLOW_RUN_ID
```

The command downloads that successful run's retained promotion package,
re-verifies its trusted tag, exact assets, checksums, provenance, server
digests, downloaded bytes, and immutable-release setting, and only then makes
the draft public. It safely resumes an interrupted exact draft; conflicting
drafts and partial public releases fail without publication. The administrative
credential never enters Actions.

`pages.yml` also runs as the deploy job of the daily, intraday, and targeted
data workflows. Its own push trigger ignores `data/rt-health/**`, so the
three-hourly realtime observation commit does not add a redundant site build of
its own; the observations go out with the next intraday refresh deploy, at most
three hours later. The refresh and the realtime sampler both run every three
hours, so an observation is never more than one sampling interval behind the
site.

### What each site build downloads from S3

A site build hydrates a deliberately bounded slice of the authoritative bucket:
the root documents, the program exports, and per-agency `latest.json`,
`badge.json`, `badge.svg`, `conformance.json`, `mark.svg`, plus today's and
yesterday's dated snapshots. The 400-day dated archive and every private
pipeline file stay in S3.

Per-agency `geometry.geojson` is handled separately because it is roughly two
thirds of that slice by bytes and changes only when an agency publishes new
route shapes. The workflow keeps a mirror of it in the Actions cache
(`route-geometry-v1-*`) and re-syncs from S3 only the objects S3 has modified
since the mirror was taken, then re-saves the mirror only when something moved.
The mirror holds published public data only. If it is ever wrong, deleting the
cache entry makes the next build fetch the geometry in full.

### Site structure and production Lighthouse checks

Both `a11y.yml` and `pages.yml` first validate every index/current-artifact
pair. When bounded hydration or lifecycle retention omitted the current dated
record, the build creates an ephemeral byte-identical copy of `latest.json`
before rendering. An existing dated record must already match. The workflows
then assemble a fresh `_site` directory and run the blocking structural check
before the page-budget check. The structural command is:

```sh
cd pipeline
uv run python scripts/check_site_seo.py \
  --site-root ../_site \
  --config ../site-seo.json \
  --report ../seo-report.json
```

It checks internal links, assets, forms, fragments, duplicate IDs, head-only
page metadata, exact canonical aliases, sitemap and robots rules, reciprocal
HTTPS language links, required structured-data identity and dates, and the
public no-tracking contract. A finding stops the build.

It also measures two things a page can get wrong while every element is
present. `title_length` and `description_length` in `site-seo.json` bound each
indexable page's title and description in characters, counted on the decoded
text so an escaped apostrophe counts as the one character a result renders.
The title bound is 60, the same budget `_agency_seo_metadata` has always held
agency titles to, and `site_shell.fit_seo_title` drops the site suffix rather
than the page's own name when a title would overrun it. A noindex page, a
canonical alias, and a redirect stub are excluded, as they are from the
sitemap and the duplicate-metadata check. Separately, `html.heading_level_skipped`
reports an outline that jumps a level, or opens below h1 on a page required to
carry one. Headings inside a hidden subtree are not counted: they are not in
the accessibility tree, and counting them would contradict the axe gate that
runs over the same markup.
Each workflow uploads its `seo-report.json` even on failure and retains it for
14 days.

The independent watchdog keeps its six-hour availability schedule and also
runs a production Lighthouse job every Sunday at 07:41 UTC. It makes three
runs against `/`, `/agencies/`, `/agency/unitrans/`, and
`/fix/expired_calendar/`, then retains the reports and log for 90 days. A
manual watchdog dispatch runs both the availability and Lighthouse jobs.

These are synthetic checks. The deployed pages do not load analytics, set
tracking cookies, or send visitor beacons. Search Console setup is deliberately
outside the deployment: the domain owner can complete DNS verification and
submit `https://gtfsscorecard.org/sitemap.xml`, but this repository must not
store Search Console credentials, API configuration, or an automated
submission workflow.

### Targeted agency activation

Use **Actions → Targeted agency activation → Run workflow** when a reviewed
agency is already present on the default branch but should be scored and made
visible before the next daily run. Enter one to 25 exact registry ids;
commas, spaces, and newlines are accepted. The dispatch rejects an empty list,
unknown or malformed ids, normalized duplicates, and more than 25 targets.

This path requires `ARTIFACTS_BUCKET` and the same `AWS_ROLE_ARN` OIDC role as
the daily publisher. It is intentionally unavailable to Pages-only forks:
without the authoritative bucket, a partial checkout cannot safely rebuild the
worldwide directory.

The workflow serializes with the daily collect and intraday refresh writer jobs.
Their shared concurrency group uses the 100-run FIFO queue, so a new intraday
refresh cannot replace a waiting activation or daily collect. The activation
captures the authoritative `index.json` bytes and ETag in one request, then uses
that compact manifest to fetch every registered `latest.json`, its indexed
current dated object, and optional fix receipt by exact key with bounded
concurrency. This avoids recursively listing the lifecycle-managed dated
archive. When a current dated object has expired, and only on a not-found
response, the hydrator copies the byte-identical latest payload to the local
dated path without recreating the remote object. A retained dated object must
match latest exactly. The selected agencies' complete retained directories and
the small `rollups/`, `changes/`, and `run/` namespaces are still hydrated in
full. Downloaded objects retain their S3 `LastModified` time so the bounded
publish sync skips retained files that were not changed locally.

S3 connections use a five-second connect timeout and a 30-second per-read
timeout. If a transient transport error interrupts a response body, hydration
closes and discards that attempt, then retries the complete object up to three
times with short deterministic backoff. Permanent S3 responses and local path,
write, or artifact-validation errors fail immediately; re-run the activation
after correcting those errors.

Before publication, the workflow checks the captured ETag again and uses the
same ETag as an `If-Match` condition on the final index commit. An unexpected
change aborts the commit and the operator can re-run against the new state.

Publication is additive and path-bounded: only selected agency directories,
`directory.json`, `scoring.json`, `rollups/`, `changes/`, and a changed
`index.json` are uploaded. There is no whole-tree sync and no remote delete.
The selected dated snapshots receive the same lifecycle tag as daily scores.
The targeted run reads but never writes `run/`, so `/status/` continues to
describe the daily pipeline rather than presenting a manual activation as a
full-corpus run. A successful publish calls the normal Pages workflow with the
data-refresh performance gate in advisory mode; accessibility still blocks.

## Teardown

Each stack is `terraform destroy` from its directory. Unset the matching Actions
variable first so the daily run stops trying to use it.

## Cost

At a few thousand small JSON files refreshed daily, S3 and CloudFront sit in or
near the free tier, and SES is fractions of a cent per email. The
single-digit-dollars-a-month budget in `CLAUDE.md` holds well into Year 2; see
the roadmap's per-tier cost notes.
