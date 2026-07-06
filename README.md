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
District). Beyond the pilots, the scorecard now scores ~1,100 agencies across
the United States, all refreshed daily.

**Live:** [gtfsscorecard.org](https://gtfsscorecard.org/) — refreshed daily by
a scheduled pipeline run.

**Status:** Beta. All four rubric categories score for ~1,100 agencies
nationally; any agency can be added via `agencies.yaml`.

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
[docs/feeds.md](docs/feeds.md). The plan for taking this from two pilots to
many agencies is split in two: the infrastructure and scaling plan is in
[docs/roadmap.md](docs/roadmap.md), and what the product becomes for its users
is in [docs/product-roadmap.md](docs/product-roadmap.md).

## Quickstart

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and Java 17+
(the validator jar is downloaded automatically on first run).

```sh
cd pipeline
uv sync
uv run scorecard run --all
```

This fetches today's snapshot of each pilot feed, validates and scores it,
and writes artifacts to `data/artifacts/<agency>/<date>.json` plus a
`latest.json` and a cross-agency `index.json`. Re-running a day is
idempotent. Checks (from the repo root; mirrors the CI gate):

```sh
make verify
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
service. The Year 1 software is built and tested. What remains is operator work
that needs an AWS account, a verified sending domain, and a decision to spend
(single-digit dollars a month); the [deploy runbook](docs/deploy.md) walks
through it stack by stack.

| Roadmap piece | In the repo | State |
| --- | --- | --- |
| Mobility Database sync | `scorecard sync` (`mobilitydb.py`) | run on demand |
| Sharded daily run | `scorecard shards` + CI matrix | live in Actions |
| Expiry/regression alerts | `scorecard alerts`, `notify --send`, `infra/alerts` | subscribe API live; send wired and gated on the `SES_FROM` variable, off until a sender is verified |
| Self-serve submission form | `web/submit.html`, `infra/submit` | built; endpoint needs `terraform apply` |
| Artifacts on S3 + CloudFront | `infra/artifacts` | built; daily mirror gated on `ARTIFACTS_BUCKET`; site serves from Pages until applied |
| Fan-out compute (Year 2) | `infra/compute` (SQS + worker) | built; apply when the daily run outgrows the Actions matrix |

The first California cohort drafted from the Mobility Database is already curated
into [`agencies.yaml`](agencies.yaml) and scored daily.

## Add your agency

Any agency with a public GTFS feed can be added with one YAML block in
[`agencies.yaml`](agencies.yaml) and a pull request; the walkthrough is
[docs/add-your-agency.md](docs/add-your-agency.md). The web form at
[`web/submit.html`](web/submit.html) does the same without YAML once its
serverless endpoint (`infra/submit`) is deployed.

## Standards conformance

This repo is governed by the shared portfolio standards vendored at
[`docs/standards/`](docs/standards/) (pinned to a tag — never edited locally;
see the integrity note in that directory's history). Per
`docs/standards/README.md`'s conformance rule, every applicable standard is
declared here; none is silently skipped.

| Standard | Applies? |
|---|---|
| [CODE-QUALITY](docs/standards/CODE-QUALITY-STANDARD.md) | Applies (Python; TS/Node N/A — `web/` is no-build vanilla JS) |
| [SECURITY & SUPPLY-CHAIN](docs/standards/SECURITY-AND-SUPPLY-CHAIN-STANDARD.md) | Applies (ASVS L1 shape: no auth, no PII store) |
| [CI/CD](docs/standards/CI-CD-STANDARD.md) | Applies |
| [OBSERVABILITY](docs/standards/OBSERVABILITY-STANDARD.md) | Applies — Tier B (frontend) + Tier C (batch pipeline); see [ADR 0031](docs/decisions/0031-observability-tier.md) |
| [ACCESSIBILITY](docs/standards/ACCESSIBILITY-STANDARD.md) | Applies fully — civic content, self-declared WCAG 2.2 AAA (see [docs/accessibility.md](docs/accessibility.md), [docs/vpat.md](docs/vpat.md)) |
| [INTERNATIONALIZATION](docs/standards/INTERNATIONALIZATION-STANDARD.md) | Applies — civic transit data, public-facing; N/A path unavailable |
| AI-EVALUATION | **N/A** — no model inference in any user-facing or decision-making path (`AI-EVALUATION-STANDARD` §0); the MCP server (`server.json`) is read-only data retrieval, no LLM SDK. Flips to APPLIES on first LLM SDK use. |
| [QUALITY & METRICS](docs/standards/QUALITY-AND-METRICS-STANDARD.md) | Applies (data-quality/lineage named for this repo explicitly) |
| [DOCUMENTATION](docs/standards/DOCUMENTATION-STANDARD.md) | Applies |
| [RELEASE & VERSIONING](docs/standards/RELEASE-AND-VERSIONING-STANDARD.md) | Applies — marketplace action tags (`v1`/`v1.0.0`), monthly dataset releases, MCP registry entry |
| [RESPONSIBLE-TECH](docs/standards/RESPONSIBLE-TECH-FRAMEWORK.md) | Applies (audits A-F; AI-governance rows N/A — no AI system) |

Open gaps per standard, as of the most recent conformance audit, are tracked
in [docs/standards-conformance-gaps.md](docs/standards-conformance-gaps.md)
rather than restated here.

## Observability

**Tier B (frontend) + Tier C (batch pipeline)** — not the
`OBSERVABILITY-STANDARD`'s default Tier-A mapping for this repo's class;
see [ADR 0031](docs/decisions/0031-observability-tier.md) for why. In short:
the deployed system is a scheduled Actions batch job plus a static site, not
a long-lived hosted service (`infra/compute`, the piece that would make this
Tier A, is built but not applied). Tier C's health/tracing/SLO controls are
N/A (no network surface to probe); Tier B's Core Web Vitals lab gate applies
and is tracked as open work (Lighthouse currently asserts accessibility only).
Real-user-monitoring beacons are declined by design — see the ADR.

## Versioning

SemVer. The public API surface is the published JSON schema
(`schema_version`), the GitHub Action's inputs (`action.yml`), and the CLI
(`docs/api.md`). `pipeline/pyproject.toml`'s `[project].version` is the single
source of truth; `CITATION.cff` and `server.json` mirror it, and
`pipeline/scripts/check_versions.py` fails `make verify` if they drift.
Supported-version policy: latest major only — this is a single-deployment
civic tool, not a library with multiple consumers pinned to old majors.

This repo also **produces releases**: the marketplace GitHub Action (tagged
`v1`), monthly citable dataset releases (`dataset-release.yml`), and an MCP
registry entry (`server.json`).

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

`CLAUDE.md` is the build spec: product framing, rubric, phased plan, and
quality bar. Execute phases in order. Hard rules: every metric ships with
its plain-language explanation; accessibility (WCAG 2.2 AAA) is
non-negotiable in the web app; agencies without realtime are shown
neutrally, never shamed.

## Maintainer

Built and maintained by [Chelsea Kelly-Reif](https://chelseakr.com), starting
from the transit systems in Davis, California. Contributions and corrections are
welcome; agencies can ask to be added or removed under the
[listing and removal policy](docs/listing-policy.md).
