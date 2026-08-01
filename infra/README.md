# infra — artifact hosting and (later) fan-out compute

Terraform for the pieces the rollout roadmap (`docs/roadmap.md`) needs as the
registry grows past what committing JSON to git and serving it from GitHub
Pages can carry.

Status: **partly applied.** The artifacts CDN (`artifacts/`) and the
feed-health digest (`alerts/`, documented in the deploy runbook) are deployed
and live on the maintainer's account, as is the self-serve submission form
(`submit/`). The fan-out compute (`compute/`) and instant scoring
(`instant-score/`) are written but not yet applied. None of this is needed to keep the site up:
the public scorecard runs on GitHub Actions plus Pages at zero cost (ADR 0001,
ADR 0002). The unapplied modules are here so the move is a `terraform apply`
and a secret, not a rewrite, the day the agency count (or, for instant-score,
the funnel case in ADR 0029) calls for it.

For end-to-end operator steps (state bucket, applies in order, the Actions
variables that switch each feature on, SES verification), follow the
[deploy runbook](../docs/deploy.md). The notes below are a per-module quick
reference.

## Modules

- `artifacts/` — S3 bucket for published JSON artifacts plus a CloudFront
  distribution in front of it (Year 1 of the roadmap). The JSON contract is
  unchanged, so pointing the web app at the CloudFront domain (see
  `web/src/config.js`) is the only frontend change. **Deployed.**
- `alerts/` — the opt-in feed-health email digest: an API Gateway + Lambda
  subscribe endpoint (double opt-in), a DynamoDB store of confirmed
  subscribers, and the SES send path the daily run calls. **Deployed; SES is
  verified for `gtfsscorecard.org` and out of the sandbox** (see
  `docs/decisions/0004-opt-in-alerts.md` and the deploy runbook).
- `submit/` — a Lambda the self-serve "add your agency" form posts to, which
  opens a pull request on the repo. **Deployed** on the maintainer's account and
  wired into `web/src/config.js`; forks fall back to the manual pull-request
  walkthrough until their own endpoint is configured.
- `compute/` — EventBridge schedule, SQS queue, and a container-image Lambda
  that runs the validator, for when the daily run outgrows the Actions matrix
  (Year 2). Scaffolding with the wiring and IAM; the worker image is built from
  `pipeline/` (see `docs/decisions/0003-fan-out-compute.md`). Not yet applied.
- `instant-score/` — a container-image Lambda (same JVM base as `compute/`)
  behind API Gateway that scores any GTFS URL on demand for `web/try.html`,
  with its own DynamoDB jobs table, per-IP rate limiting, and a reserved
  concurrency cap. A deliberate exception to the cost ceiling, justified as a
  funnel investment rather than steady-state infrastructure (see
  `docs/decisions/0029-instant-score-funnel.md`). Not yet applied; until it is,
  `web/try.html`'s inline form stays disabled and the page falls back to its
  existing GitHub Issue Form path.

## Cost-allocation tags

Every module sets provider-level `default_tags`, so each taggable resource it
creates carries:

| tag | value |
| --- | --- |
| `project` | `gtfs-scorecard` (from `var.project`) |
| `component` | the module directory: `artifacts`, `alerts`, `submit`, `compute`, `instant-score` |
| `managed-by` | `terraform` |

`project` is the activated cost-allocation tag key in Cost Explorer, so an
untagged resource shows up as account-wide untagged spend and never reaches
this project's budget. Declaring the tags on the provider rather than on each
resource means resources added later are covered by default.

Two limits are worth knowing before reading a bill:

- Some resource types take no tags at all (S3 bucket sub-configurations, IAM
  inline policies and policy attachments, CloudFront functions, origin access
  controls, response-headers policies, API Gateway routes and integrations,
  Route 53 records, Lambda permissions). Their cost either rolls up into the
  parent resource or is zero.
- Resources this repo only reads through a data source are not covered: the
  `gtfs-scorecard-subscriptions` and `gtfs-scorecard-ratelimit` DynamoDB
  tables, the SES identity for `gtfsscorecard.org`, the `gtfsscorecard.com`
  hosted zone, the Terraform state bucket, the ECR repositories holding the
  container images, and the log groups Lambda creates on first invocation.
  Tag those in the console (or bring them under Terraform) if their spend
  needs to be attributed too.

Cost allocation is not retroactive: usage recorded before a tag exists stays
untagged in past bills, so the tags only show up in the budget after the next
`terraform apply` and the following billing period.

## Apply (artifacts CDN)

```sh
cd infra/artifacts
terraform init
terraform apply -var="bucket_name=gtfs-scorecard-artifacts" -var="project=gtfs-scorecard"
```

Outputs the bucket name and the CloudFront domain. Set the `ARTIFACTS_BUCKET`
and `ARTIFACTS_CDN` repository **variables** (Settings → Secrets and variables
→ Actions) and the `AWS_ROLE_ARN` secret; the daily workflow's collect job
already carries the `scorecard publish-artifacts` upload of `data/artifacts`,
gated on those variables, so it is a no-op until they are set and forks keep
working.

## The gtfsscorecard.com redirect

`infra/artifacts/redirect.tf` parks the defensive `.com` domain and 301s it to
the canonical `.org`. It is one S3 website bucket per hostname, because an S3
website endpoint chooses the bucket from the request's `Host` header: the
apex is served by a bucket named `gtfsscorecard.com`, `www` by one named
`www.gtfsscorecard.com`. Route 53 resolves an S3-website alias by matching the
record name to the bucket name, so both alias targets must be the *regional*
`website_domain` (`s3-website-us-west-2.amazonaws.com`), never the
bucket-prefixed `website_endpoint`.

The module is already applied, so adding the `www` bucket is an incremental
plan: two new resources (`aws_s3_bucket.redirect_com_www` and its public
access block plus website configuration) and one in-place update to
`aws_route53_record.com_www`'s alias target. Nothing existing is destroyed and
the apex is untouched.

Run `terraform plan` with the same variables as the apply block above. Expect
`3 to add, 1 to change, 0 to destroy`. After the apply, allow the
Route 53 change a minute to propagate, then check the redirect on both names:

```sh
curl -sSI http://gtfsscorecard.com/     | head -2   # 301 -> https://gtfsscorecard.org/
curl -sSI http://www.gtfsscorecard.com/ | head -2   # 301 -> https://gtfsscorecard.org/
```

Both hostnames are HTTP-only; S3 website endpoints cannot serve TLS. Adding
`https://` on the `.com` would take CloudFront plus an ACM certificate, which
is not worth owning for a parked redirect nobody is asked to type.

## Cost

Measured, not estimated: S3 was **$50.07 in July 2026**, against about 92,000
objects in `gtfs-scorecard-artifacts-ckr`. Storage is not what costs that —
the published bytes are a couple of gigabytes, a dollar or so a month at
Standard rates. Requests are: the publish path re-uploaded objects whose
content had not changed, because `aws s3 sync` transfers on a newer local
mtime and CI checks out fresh on every run. The daily job stopped doing that
in `scorecard.yml`, and the intraday refresh in `refresh.yml`; expect the
figure to fall, and re-read the bill rather than this paragraph before
trusting a number.

CloudFront egress for a low-traffic civic site is still within the free tier
or close to it. The single-digit-dollars-a-month budget in `CLAUDE.md` did not
hold through Year 1 and should be treated as a target to defend, not a
description of the bill; the roadmap's per-tier cost notes are estimates that
have not been reconciled against actual spend.

`instant-score/` is the one deliberate exception once applied: each request
runs a JVM validator invocation, estimated at roughly $20-60/month at
demo-era volume (`docs/decisions/0029-instant-score-funnel.md`). Rate
limiting, reserved concurrency, and the existing feed-size cap bound the
downside; revisit the estimate before relaxing any of them.
