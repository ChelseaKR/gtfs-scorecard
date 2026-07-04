# 0029 — Instant scoring: a paid on-demand runner as a deliberate funnel exception

Status: accepted (written; infrastructure not yet applied)

## Context

`web/try.html` already lets a visitor score any GTFS Schedule URL, but the
backend is a GitHub Issue Form (`.github/ISSUE_TEMPLATE/score-a-feed.yml`) and
the `onboard.yml` Actions workflow: opening a "score-request" issue runs
`scorecard try` and comments the grade back. This is free and keeps the
static-first, near-zero-cost posture (CLAUDE.md), but it asks a visitor who is
not a developer — the exact audience CLAUDE.md names — to create a GitHub
account and wait for a bot comment before seeing whether their feed is any
good.

An external market pass (recorded in the sibling `gtfs-scorecard-plans`
folder, not in this repo) found that `gtfs.org`'s getting-started page routes
essentially all schedule-validation traffic to a single existing tool, and
that no scored, interpreted answer exists for an "is my feed OK?" visitor
without a PR-and-wait step. Meeting that visitor with a graded result in about
a minute, from a plain web form, was judged the single highest-value unlock
available (`06-beyond-static-unlocks.md`, Tier 1; `03-feature-plan.md`, A4).

Scoring a feed on demand needs a real compute step (download the feed, run
the Java validator, run the pipeline), which cannot run inside a static site
and cannot fit the existing zip-package Lambdas (`infra/alerts`,
`infra/submit`): the validator needs a JVM.

## Decision

Add `infra/instant-score`: a container-image Lambda (the same base pattern as
`infra/compute`'s worker) behind an API Gateway HTTP API, plus a DynamoDB
table this module owns outright.

- **The Lambda is asynchronous internally.** API Gateway hard-caps a proxied
  Lambda at 30 seconds; scoring a real feed can run longer. `POST /score`
  returns a `job_id` in well under a second and fires a second, async
  self-invocation (`InvocationType="Event"`) that does the actual work and
  writes a terminal status. `GET /score/{id}` polls it. This keeps the
  request/response contract simple for the web form without needing a queue.
- **The jobs table is Terraform-owned**, unlike the subscriptions table in
  `infra/alerts` (which predates that module and is only read as a data
  source). A scoring job is inherently ephemeral — TTL auto-expires each row
  30 days after creation, matching the "shareable result URL that expires
  unless claimed" design — so there is no pre-existing store to adopt.
- **Abuse control covers all three named dependencies from the growth-plans
  A4 writeup** (rate limiting, a zip-size cap, and a queue-depth limit),
  adapted to a queueless design:
  - a per-IP fixed-window counter in the shared rate-limit table (5
    requests/hour, tighter than alerts' 10/hour, because each request costs a
    JVM run), plus a gateway-level throttle (5 req/s, burst 10) as a hard
    ceiling in front of the Lambda;
  - the zip-size cap already exists at the shared fetch layer
    (`net.MAX_DOWNLOAD_BYTES`, 512 MB) and applies to `run_adhoc` unchanged,
    so this module needs no new size guard;
  - `reserved_concurrent_executions` (default 5) is the queue-depth analog:
    it bounds concurrent JVM runs across both invocation shapes (the sync
    HTTP route and the async self-invoke that does the scoring), since this
    design uses a self-invoke instead of an SQS queue.
- **The validator jar is baked into the image** (same jar, same SHA-256 check,
  as `infra/compute`'s Dockerfile) so a cold start never depends on a network
  call to GitHub Releases.
- **The cost ceiling is deliberately relaxed.** CLAUDE.md's
  single-digit-dollars-a-month guardrail is a hard constraint for the
  always-on render path, but the growth-plans folder's Tier-1 analysis frames
  this specific spend (~$20–60/month at demo-era volume, driven by Lambda
  compute for the JVM validator) as a funnel investment, not steady-state
  infrastructure, and CLAUDE.md's own architecture section already allows this
  kind of exception when documented in an ADR.

## Consequences

- `web/try.html` gets a real backend behind the same form a visitor already
  sees, with no GitHub account required and a result in about a minute
  instead of an async issue comment. The GitHub Issue Form path is left in
  place, not removed, as a zero-cost fallback if the Lambda endpoint is
  disabled or `SCORECARD_TRY_URL` is unset.
- This is the first infra module in the repo where Terraform creates and owns
  a DynamoDB table rather than treating one as a pre-existing data source.
  Destroying this module's state also destroys the jobs table; that is
  intended, since nothing durable is stored there.
- Like `infra/compute` and `infra/submit`, this module is written and
  reviewable now but not applied. Applying it (building the image, pushing to
  ECR, `terraform apply`) is a deliberate operator step, not something CI or
  this change does automatically.
- If the per-use cost or abuse volume grows beyond the Tier-1 estimate, revisit
  before extending it further (e.g. before removing the gateway throttle or
  raising the per-IP limit).
