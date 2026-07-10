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
> artifacts to S3 and sends the digest. The self-serve submission form (§3),
> the fan-out compute (§4), and instant scoring (§5) are written but not yet
> applied. The steps below are the from-scratch runbook, so they still read as
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
   workflow falls back to the maintainer's CloudFront domain
   (`scorecard.yml`'s `SCORECARD_CDN_BASE` default), which a fork does not
   want to inherit.

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

Lets an agency add itself from `web/submit.html` without opening a pull request.

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
table, per-IP rate limiting, and a reserved concurrency cap. This is the one
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

## Scheduled jobs (GitHub Actions, no AWS needed)

The runbook above covers the AWS stacks. Day-to-day operations run entirely in
Actions; this is the inventory an operator should know exists:

| Workflow | Cadence | What it does |
| --- | --- | --- |
| `scorecard.yml` | daily | The full sharded re-score, commit, deploy, optional S3 mirror and SES digest. |
| `refresh.yml` | hourly | Cheap intraday tier: change/down detection by conditional GET, no validator (ADR 0010). |
| `rt-monitor.yml` | every 3 h | Short realtime sampling burst across agencies into `data/rt-health` (ADR 0012). |
| `rt-archive.yml` | manual | Bounded high-resolution realtime polling session for one agency (ADR 0012). |
| `watchdog.yml` | every 6 h | Independent uptime and freshness check, no AWS dependency. |
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

## Teardown

Each stack is `terraform destroy` from its directory. Unset the matching Actions
variable first so the daily run stops trying to use it.

## Cost

At a few thousand small JSON files refreshed daily, S3 and CloudFront sit in or
near the free tier, and SES is fractions of a cent per email. The
single-digit-dollars-a-month budget in `CLAUDE.md` holds well into Year 2; see
the roadmap's per-tier cost notes.
