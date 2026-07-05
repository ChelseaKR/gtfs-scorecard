# infra — artifact hosting and (later) fan-out compute

Terraform for the pieces the rollout roadmap (`docs/roadmap.md`) needs as the
registry grows past what committing JSON to git and serving it from GitHub
Pages can carry.

Status: **partly applied.** The artifacts CDN (`artifacts/`) and the
feed-health digest (`alerts/`, documented in the deploy runbook) are deployed
and live on the maintainer's account; the fan-out compute (`compute/`), the
self-serve submission form (`submit/`), and instant scoring (`instant-score/`)
are written but not yet applied. None of this is needed to keep the site up:
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
  opens a pull request on the repo. Written; not yet applied (the form falls
  back to the manual pull-request walkthrough until it is).
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

## Apply (artifacts CDN)

```sh
cd infra/artifacts
terraform init
terraform apply -var="bucket_name=gtfs-scorecard-artifacts" -var="project=gtfs-scorecard"
```

Outputs the bucket name and the CloudFront domain. Put the domain in the
`deploy` GitHub environment as `ARTIFACTS_CDN`, and add `aws s3 sync` of
`data/artifacts` to the daily workflow's collect job (gated on AWS secrets;
the step is a no-op without them, so forks and the pilot keep working).

## Cost

At a few thousand small JSON files refreshed daily, S3 storage and request
costs are cents, and CloudFront egress for a low-traffic civic site is within
the free tier or close to it. The single-digit-dollars-a-month budget in
`CLAUDE.md` holds well into Year 2; see the roadmap's cost notes per tier.

`instant-score/` is the one deliberate exception once applied: each request
runs a JVM validator invocation, estimated at roughly $20-60/month at
demo-era volume (`docs/decisions/0029-instant-score-funnel.md`). Rate
limiting, reserved concurrency, and the existing feed-size cap bound the
downside; revisit the estimate before relaxing any of them.
