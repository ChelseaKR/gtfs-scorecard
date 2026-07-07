# GTFS Scorecard

> Is your transit agency's GTFS feed any good? A plain-language quality grade,
> the three things to fix, and why each one matters to riders.

[![CI](https://github.com/ChelseaKR/gtfs-scorecard/actions/workflows/ci.yml/badge.svg)](https://github.com/ChelseaKR/gtfs-scorecard/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-GTFS%20Scorecard%20gate-2ea44f?logo=github)](https://github.com/marketplace/actions/gtfs-scorecard-gate)
[![Live site](https://img.shields.io/badge/live-gtfsscorecard.org-2ea44f)](https://gtfsscorecard.org)

[![GTFS Scorecard: a plain-language quality grade for a transit agency's feed](https://gtfsscorecard.org/og.png)](https://gtfsscorecard.org)

A data quality scorecard for small transit agencies. It fetches an agency's
**GTFS Schedule and GTFS-Realtime** feeds, runs the canonical MobilityData
validator, and turns the results into a letter grade with a short list of
concrete fixes, including NTD certification readiness, written for the transit
manager who inherited the feed from a vendor, not for developers.

Pilot agencies: [Unitrans](https://unitrans.ucdavis.edu) (ASUCD / City of
Davis) and [Yolobus](https://yolobus.com) (Yolo County Transportation
District). Beyond the pilots, the scorecard now tracks ~1,490 agencies across
the United States and Canada (~1,450 with published scorecard pages), all
refreshed daily.

**Live:** [gtfsscorecard.org](https://gtfsscorecard.org/) — refreshed daily by
a scheduled pipeline run.

**Status:** Beta. All four rubric categories score for ~1,450 agencies across
the US and Canada; any agency can be added via `agencies.yaml`.

## What an agency gets

- An overall grade and four category scores: correctness, freshness, rider
  experience completeness, and realtime quality.
- "Top 3 things to fix", in plain language with effort hints. Findings are
  framed as fixes, never as failures.
- An NTD certification-readiness read (published, valid, current) and a flag
  for whether the feed's `agency_id` matches the agency's NTD ID.
- Trend history, one JSON artifact per agency per day.
- An embeddable grade badge (`<agency>/badge.svg`) the agency can put on its
  own developer page.

The scoring methodology, with citations to the California Transit Data
Guidelines v4.0 and the validator's rule taxonomy, is in
[docs/rubric.md](docs/rubric.md). Methodology changes are governed: a
validator-version bump must attach the shadow-run impact report from
`scorecard canary` before it lands (rubric.md, "Governed upgrades").
Feed sources and licenses are in
[docs/feeds.md](docs/feeds.md). Forward planning is split in two: the
infrastructure and scaling plan is in [docs/roadmap.md](docs/roadmap.md), and
what the product becomes for its users is in
[docs/product-roadmap.md](docs/product-roadmap.md).

## What's on the site

Each agency gets a scorecard page, plus three companion pages written for the
different seats at an agency check-in: a board one-pager
(`/agency/<id>/board/`), a call-prep brief (`/brief/`), and a fix log
(`/fixes/`). Around those sit:

- **National views** — the national pulse (`/pulse/`), most common problems
  (`/problems/`), realtime reliability (`/realtime/`), newer-capability
  adoption (`/adoption/`), accessibility data coverage, NTD readiness
  (`/ntd/`), US and Canada equity overlays (`/equity/`), and national route
  maps (`/map/`, `/routes/`).
- **Program pages** (`/program/<state>/`) for 46 states plus DC and named
  cohorts from [`rollups.yaml`](rollups.yaml), each with the fixes shared
  across the group.
- **Practitioner tools** — score any feed on the spot (`/try.html`), check a
  feed before publishing (`/check/`), compare two agencies (`/compare/`),
  query the dataset with SQL in the browser (`/query/`), and put feed quality
  in a vendor contract (`/procurement/`).
- **A fix knowledge base** (`/fix/<rule>/`, one plain-language page per common
  validator finding) and the standards crosswalk (`/crosswalk/`).
- **Machine-readable surfaces** — the versioned read API
  ([docs/api.md](docs/api.md)), a Parquet table for bulk SQL, per-agency
  badges and conformance marks, Atom change feeds, monthly citable dataset
  releases, and a read-only MCP server ([docs/mcp.md](docs/mcp.md)).

## Quickstart

Requires Python 3.11+, [uv](https://docs.astral.sh/uv/), and Java 17+
(the validator jar is downloaded automatically on first run).

```sh
cd pipeline
uv sync
uv run scorecard run --all
```

This fetches today's snapshot of each pilot feed, validates and scores it,
and writes artifacts to `data/artifacts/<agency>/<date>.json` plus a
`latest.json` and a cross-agency `index.json`. Re-running a day is
idempotent. Checks:

```sh
uv run pytest && uv run ruff check src tests && uv run mypy
```

### Run the web app locally

The frontend reads the JSON artifacts over HTTP. Serve the repo root and open
the page through `http://`, not by double-clicking the file:

```sh
cd ..            # repo root, so data/artifacts/ is reachable
python3 -m http.server 8000
# then open http://localhost:8000/web/index.html
```

Opening `web/index.html` as a `file://` URL leaves the page stuck on
"Loading scorecards…": browsers block ES module loading and `fetch` over
`file://`, so the app never runs. Any static server works; the only requirement
is that `data/artifacts/` sits one level above `web/`, which the
`../data/artifacts` fallback in `web/src/app.js` expects.

## Use it in CI

Gate your own pipeline on feed quality with the published action. It scores the
feed, prints the grade and the top fixes in the job log, and fails the build if
the feed drops below `min-grade` or expires within `min-days-to-expiry`:

```yaml
- uses: ChelseaKR/gtfs-scorecard@v1
  with:
    feed-url: https://your-agency.example/google_transit.zip
    min-grade: C
    min-days-to-expiry: 14
```

Both thresholds are optional; leave one blank to skip that check. Full input
reference and a complete workflow are in [docs/ci-action.md](docs/ci-action.md).

## Operating at scale

Beyond `run`, the CLI carries the commands the rollout plan needs:

```sh
scorecard sync --country US --state California   # propose agencies.yaml entries
                                                 # from the Mobility Database
scorecard shards --count 4                        # JSON fan-out plan for CI
scorecard reindex                                 # rebuild index.json from disk
scorecard rollups                                 # publish program rollup artifacts
scorecard render-site                             # crawlable static pages + sitemap
scorecard alerts --out digest.md                  # expiry/regression digest
scorecard notify                                  # per-subscriber digest (dry run)
```

`notify` builds a feed-health email for each opt-in subscriber in
[`subscriptions.yaml`](subscriptions.yaml), containing only the agencies they
follow and only when one needs attention. It prints the emails by default; the
daily workflow sends them via SES once an operator verifies a sender, applies
the SES grant in `infra/artifacts`, and sets the `SES_FROM` repo variable.

The daily workflow fans agencies out across a parallel matrix and can mirror
artifacts to a CloudFront-backed S3 bucket once `infra/artifacts` is applied
(ADR 0002). Program rollups are configured in [`rollups.yaml`](rollups.yaml) as
named cohorts (a liaison's own agencies, a district, the whole state) and shown
at `#/programs`; an agency "needs attention" when its feed is expiring or its
grade regressed, not merely when it scores below a B. The published JSON is a
documented read API ([docs/api.md](docs/api.md)); a flat catalog of every agency
(grade, score, feed URL, days-to-expiry, top fix) is served at `/catalog.json`
and `/catalog.csv` so a consumer needs one request, not one per agency.

### Roadmap status: built vs deployed

The [roadmap](docs/roadmap.md) plans the path from two pilot feeds to a national
service. The Year 1 software is built, tested, and mostly deployed; the
[deploy runbook](docs/deploy.md) walks through the AWS stacks and carries the
current deployment status.

| Roadmap piece | In the repo | State |
| --- | --- | --- |
| Mobility Database sync | `scorecard sync` (`mobilitydb.py`) | run on demand |
| Sharded daily run | `scorecard shards` + CI matrix | live in Actions |
| Expiry/regression alerts | `scorecard alerts`, `notify --send`, `infra/alerts` | applied and live; SES sender verified, digest sends daily |
| Artifacts on S3 + CloudFront | `infra/artifacts` | applied and live; daily mirror on, site still serves from Pages |
| Self-serve submission form | `web/submit.html`, `infra/submit` | built; endpoint needs `terraform apply` |
| Instant scoring | `web/try.html`, `infra/instant-score` | built; falls back to the issue-form path until applied (ADR 0029) |
| Fan-out compute (Year 2) | `infra/compute` (SQS + worker) | built; apply when the daily run outgrows the Actions matrix |

The cohort drafted from the Mobility Database has grown well past the first
California pass: [`agencies.yaml`](agencies.yaml) now carries ~1,490 curated
agencies across the US and Canada, scored daily.

## Add your agency

Any agency with a public GTFS feed can be added with one YAML block in
[`agencies.yaml`](agencies.yaml) and a pull request; the walkthrough is
[docs/add-your-agency.md](docs/add-your-agency.md). The web form at
[`web/submit.html`](web/submit.html) does the same without YAML once its
serverless endpoint (`infra/submit`) is deployed.

## Layout

```
agencies.yaml   the agencies the scorecard tracks; add yours here
rollups.yaml    program rollups (portfolio views across many agencies)
pipeline/       Python pipeline: fetch -> validate -> score -> publish
web/            static frontend; reads only published JSON
infra/          Terraform: artifacts CDN, submission function, fan-out compute
docs/           feeds, rubric, roadmap, api, fixes/ (KB), decisions/ (ADRs)
data/           raw snapshots (ignored) and published artifacts (committed)
```

## For Claude Code

`CLAUDE.md` is the build spec: product framing, rubric, and quality bar. The
original four build phases have shipped; current direction lives in the
roadmaps and [docs/ideation/](docs/ideation/). Hard rules: every metric ships
with its plain-language explanation; accessibility (WCAG 2.2 AAA) is
non-negotiable in the web app; agencies without realtime are shown
neutrally, never shamed.

## Maintainer

Built and maintained by [Chelsea Kelly-Reif](https://chelseakr.com), starting
from the transit systems in Davis, California. Contributions and corrections are
welcome; agencies can ask to be added or removed under the
[listing and removal policy](docs/listing-policy.md).
