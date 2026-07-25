# GTFS Scorecard

> Daily, plain-language GTFS quality scorecards for small transit agencies:
> see the current grade, the three things to fix, and why each one matters.

[![CI](https://github.com/ChelseaKR/gtfs-scorecard/actions/workflows/ci.yml/badge.svg)](https://github.com/ChelseaKR/gtfs-scorecard/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![GitHub Marketplace](https://img.shields.io/badge/Marketplace-GTFS%20Scorecard%20gate-2ea44f?logo=github)](https://github.com/marketplace/actions/gtfs-scorecard-gate)
[![Live site](https://img.shields.io/badge/live-gtfsscorecard.org-2ea44f)](https://gtfsscorecard.org)

[![GTFS Scorecard: plain-language GTFS quality and prioritized fixes](https://gtfsscorecard.org/og.png)](https://gtfsscorecard.org)

GTFS Scorecard is a daily data-quality service for small transit agencies and
the program staff, maintainers, and vendors who support them. It publishes
dated grades, prioritized fixes, history, program views, practitioner tools,
and open data. It does not implement a competing GTFS validator. Correctness
findings come from MobilityData's canonical validator.

## Where it fits

GTFS Scorecard is the evidence and triage layer:

1. [Mobility Database](https://mobilitydatabase.org/) and
   [Transitland](https://www.transit.land/) help identify public feeds and
   their sources or versions.
2. The [MobilityData GTFS validator](https://github.com/MobilityData/gtfs-validator)
   supplies canonical specification findings.
3. An agency, vendor, editor, or support program changes and publishes the
   feed through its existing workflow.
4. A 90-day GTFS Scorecard pilot is testing the final handoff: link an accepted
   action to the intended feed, run a comparable recheck, and preserve the
   result.

The [California GTFS Quality Dashboard](https://reports.dds.dot.ca.gov/)
inspired the project's daily scorecard and support-program framing. GTFS
Scorecard is independent and is not an official compliance determination.

Pilot agencies: [Unitrans](https://unitrans.ucdavis.edu) (ASUCD / City of
Davis) and [Yolobus](https://yolobus.com) (Yolo County Transportation
District). Beyond the pilots, the registry contains more than 2,100 curated
feed records, mostly in the United States and Canada, plus reviewed canaries
across Europe, Asia-Pacific, and South America. The repository
keeps the generated corpus registry-bounded, with more than 1,100 numeric
scorecards published. Scoring is scheduled daily, and the public status
page reports the exact current configured and published counts along with when
the latest run completed. A feed record is not always a distinct transit agency: regional
feeds, modal variants, and retired aliases are counted separately while the
identity registry is reconciled.

**Live:** [gtfsscorecard.org](https://gtfsscorecard.org/) — with the latest
completed-run evidence at [gtfsscorecard.org/status](https://gtfsscorecard.org/status/).

**Status:** Beta. The public scorecards and daily evidence service are live.
The remediation workflow is being tested and is not yet a proven service.
Realtime quality is scored only when a usable realtime feed is configured and
measured; otherwise it is shown neutrally as not yet measured. Any agency can
be added through `registry/intake.yaml`.

## Use, adopt, or contribute

- **Check a feed:** browse
  [gtfsscorecard.org](https://gtfsscorecard.org/), or
  request a [one-off score](https://github.com/ChelseaKR/gtfs-scorecard/issues/new?template=score-a-feed.yml).
- **Track an agency:** use the
  [self-serve submission form](https://gtfsscorecard.org/submit.html), or follow
  the [repository walkthrough](docs/add-your-agency.md) to open a pull request.
- **Gate a feed in CI:** add the
  [GTFS Scorecard Marketplace Action](https://github.com/marketplace/actions/gtfs-scorecard-gate)
  to a feed repository.
- **Test what happens after the scorecard:** read
  [the remediation pilot request](https://github.com/ChelseaKR/gtfs-scorecard/issues/185)
  if you can take a finding through an accepted request and same-feed recheck.
- **Contribute:** choose a
  [bounded open issue](https://github.com/ChelseaKR/gtfs-scorecard/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22)
  or read [CONTRIBUTING.md](CONTRIBUTING.md). Feed corrections, accessibility
  review, and practitioner feedback are useful without changing scoring code.

## Quickstart

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and Java 17+
(the validator jar is downloaded automatically on first run).

```sh
cd pipeline
uv sync
uv run scorecard run --all
```

This fetches today's snapshot of every configured feed, validates and scores it,
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

## What an agency gets

- An overall grade from the categories that can be measured: correctness,
  freshness, rider experience completeness, and, when available, realtime
  quality.
- "Top 3 things to fix", in plain language with effort hints. Findings are
  framed as fixes, never as failures.
- For U.S. agencies only, an NTD GTFS-readiness read (published, valid,
  current, and `agency_id` present) plus a neutral check of whether `agency_id`
  happens to equal the five-digit NTD ID. Equality is optional; RY2026 presence
  and the P-50 crosswalk are not.
- Trend history, one JSON artifact per agency per day.
- An embeddable grade badge (`<agency>/badge.svg`) the agency can put on its
  own developer page.

The scoring methodology, with citations to the California Transit Data
Guidelines v4.0 and the validator's rule taxonomy, is in
[docs/rubric.md](docs/rubric.md). Methodology changes are governed: a
validator-version bump must attach the shadow-run impact report from
`scorecard canary` before it lands (rubric.md, "Governed upgrades").
The grade, weights, thresholds, and fix order are GTFS Scorecard policy choices,
not an official MobilityData grade or a universal quality standard.
Feed sources and licenses are in
[docs/feeds.md](docs/feeds.md). Forward planning is split in two: the
infrastructure and scaling plan is in [docs/roadmap.md](docs/roadmap.md), and
what the product becomes for its users is in
[docs/product-roadmap.md](docs/product-roadmap.md).

## What's on the site

Each agency gets a scorecard page, plus three companion pages written for the
different seats at an agency check-in: a board one-pager
(`/agency/<id>/board/`), a call-prep brief (`/brief/`), and, when comparable
finding-clearance records exist, a clearance log (`/fixes/`). Around those sit:

- **Coverage views** — the coverage overview (`/pulse/`), most common problems
  (`/problems/`), realtime reliability (`/realtime/`), optional-feature
  adoption and accessibility data coverage (`/adoption/`), a consumer feature
  finder with translation-language and accessibility filters
  (`/app/#/?view=features`), and worldwide
  agency and route maps (`/map/`, `/routes/`). U.S.-specific NTD readiness
  (`/ntd/`) and equity (`/equity/`) stay available as regional modules.
- **Program pages** (`/program/<state>/`) for 46 states plus DC and named
  cohorts from [`rollups.yaml`](rollups.yaml), each with the fixes shared
  across the group.
- **Practitioner tools** — request a one-off score through GitHub or run it
  locally (`/try.html`), check a feed before publishing (`/check/`), compare two agencies (`/compare/`),
  query the dataset with SQL in the browser (`/query/`), and put feed quality
  in a vendor contract (`/procurement/`).
- **Board-ready outputs** — each agency has a printable one-pager; see the
  [live Unitrans example](https://gtfsscorecard.org/agency/unitrans/board/), or
  generate a self-contained, custom-branded offline report with the
  [board-report tool](docs/board-report.md).
- **A fix knowledge base** (`/fix/<rule>/`, one plain-language page per common
  validator finding) and the standards crosswalk (`/crosswalk/`).
- **Machine-readable surfaces** — the versioned read API
  ([docs/api.md](docs/api.md)), a Parquet table for bulk SQL, per-agency
  badges and conformance marks, Atom change feeds, monthly citable dataset
  releases, and a read-only MCP server ([docs/mcp.md](docs/mcp.md)).

The country controls describe only the current covered set. They are not a
census of a country or region. The live evidence and readiness result for a
bounded European GTFS beta are on the
[status page](https://gtfsscorecard.org/status/#global-coverage); the release
gate and scope limits are in [docs/global-expansion.md](docs/global-expansion.md).

## Use it in CI

Gate your own pipeline on feed quality with the published action. It scores the
feed, prints the grade and the top fixes in the job log, and fails the build if
the feed drops below `min-grade` or expires within `min-days-to-expiry`:

```yaml
- uses: ChelseaKR/gtfs-scorecard@v1
  with:
    feed-url: https://your-agency.example/google_transit.zip
    country: CA
    min-grade: C
    min-days-to-expiry: 14
```

`country` is the feed's assigned ISO 3166-1 alpha-2 code; it defaults to `US`
for existing workflows. Both thresholds are optional; leave one blank to skip that check. Full input
reference and a complete workflow are in [docs/ci-action.md](docs/ci-action.md).

## Operating at scale

Beyond `run`, the CLI carries the commands the rollout plan needs:

```sh
scorecard sync --country US --state California   # propose keyless, untracked
                                                 # Mobility Database entries
scorecard shards --count 4                        # JSON fan-out plan for CI
scorecard reindex                                 # rebuild index.json from disk
scorecard rollups                                 # publish program rollup artifacts
scorecard render-site                             # crawlable static pages + sitemap
scorecard alerts --out digest.md                  # expiry/regression digest
scorecard notify                                  # per-subscriber digest (dry run)
```

Add `--source-metadata-out <path>` to `scorecard sync` for a source receipt
that accounts for every Mobility Database Schedule row as excluded, filtered,
already tracked, duplicate, conflicted, or proposed for review. It never edits
the registry and does not treat a catalog proposal as permission to republish.

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

The [roadmap](docs/roadmap.md) plans the path from two pilot feeds to a
worldwide-capable service. The Year 1 software is built, tested, and mostly deployed; the
[deploy runbook](docs/deploy.md) walks through the AWS stacks and carries the
current deployment status.

| Roadmap piece | In the repo | State |
| --- | --- | --- |
| Mobility Database sync | `scorecard sync` (`mobilitydb.py`) | run on demand |
| Scheduled scoring run | `scorecard shards` + CI matrix | daily schedule live in Actions; observed completion is on `/status/` |
| Expiry/regression alerts | `scorecard alerts`, `notify --send`, `infra/alerts` | applied and live; SES sender verified, digest sends daily |
| Artifacts on S3 + CloudFront | `infra/artifacts` | applied and live; daily mirror on, site still serves from Pages |
| Self-serve submission form | `web/submit.html`, `infra/submit` | applied and live; submissions open reviewable pull requests |
| Instant scoring | `web/try.html`, `infra/instant-score` | built; falls back to the issue-form path until applied (ADR 0029) |
| Fan-out compute (Year 2) | `infra/compute` (SQS + worker) | built; apply when the daily run outgrows the Actions matrix |

The cohort drafted from the Mobility Database has grown well past the first
California pass: the manifest-backed [`registry`](registry/README.md) now
carries more than 2,100 curated feed records, mostly across the US and Canada,
with a 528-record reviewed European cohort across 26 countries.
It now includes a geographically diverse reviewed canary cohort, scored daily
(a 2026-07 dedupe pass removed ~350 records that duplicated an already-listed
feed).

## Add your agency

Any agency with a public GTFS feed can be added with one YAML block in
[`registry/intake.yaml`](registry/intake.yaml) and a pull request; the walkthrough is
[docs/add-your-agency.md](docs/add-your-agency.md). The live web form at
[`web/submit.html`](web/submit.html) does the same without YAML through the
deployed `infra/submit` endpoint; every submission still opens a pull request
for human review before publication.

## Support

The public scorecards, data, API, local pre-publish check, and request-backed
one-off scoring remain free. The [support page](https://gtfsscorecard.org/support/)
explains the project's infrastructure needs and accepts sponsorship inquiries;
it does not advertise a payment rail that is not ready.

## Standards conformance

This repo is governed by the shared portfolio standards vendored at
[`docs/standards/`](docs/standards/) (pinned to a tag — never edited locally;
see the integrity note in that directory's history). Per
`docs/standards/README.md`'s conformance rule, every applicable standard is
declared here; none is silently skipped.

| Standard | Applies? |
|---|---|
| [Code Quality](docs/standards/CODE-QUALITY-STANDARD.md) | Applies (Python; TS/Node N/A — `web/` is no-build vanilla JS) |
| [Security & Supply-Chain](docs/standards/SECURITY-AND-SUPPLY-CHAIN-STANDARD.md) | Applies (ASVS L1 shape: no auth, no PII store) |
| [CI/CD](docs/standards/CI-CD-STANDARD.md) | Applies |
| [Observability](docs/standards/OBSERVABILITY-STANDARD.md) | Applies — Tier B (frontend) + Tier C (batch pipeline); see [ADR 0031](docs/decisions/0031-observability-tier.md) |
| [Accessibility](docs/standards/ACCESSIBILITY-STANDARD.md) | Applies fully — civic content, self-declared WCAG 2.2 AAA (see [docs/accessibility.md](docs/accessibility.md), [docs/vpat.md](docs/vpat.md)) |
| [Internationalization](docs/standards/INTERNATIONALIZATION-STANDARD.md) | Applies — civic transit data, public-facing; exemption path unavailable |
| AI Evaluation | N/A — no LLM/model component: no model inference in any user-facing or decision-making path (`AI-EVALUATION-STANDARD` §0); the MCP server (`server.json`) is read-only data retrieval, no LLM SDK. Flips to APPLIES on first LLM SDK use. |
| [Quality & Metrics](docs/standards/QUALITY-AND-METRICS-STANDARD.md) | Applies (data-quality/lineage named for this repo explicitly) |
| [Documentation](docs/standards/DOCUMENTATION-STANDARD.md) | Applies |
| [Release & Versioning](docs/standards/RELEASE-AND-VERSIONING-STANDARD.md) | Applies — reusable Action tags (`v1`/`v1.4.0`), monthly dataset releases, MCP registry entry |
| [Responsible-Tech Framework](docs/standards/RESPONSIBLE-TECH-FRAMEWORK.md) | Applies (audits A-F; AI-governance rows N/A — no AI system) |

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

## Run your own instance

A state DOT, national RTAP, or country program can fork this repo and stand
up its own branded instance — own domain, own agency registry, own
organization name — from config and a deploy, no code change:
[docs/fork-quickstart.md](docs/fork-quickstart.md).

## Layout

```
registry/       manifest-backed agency shards; add yours to intake.yaml
instance.example.yaml   fork branding template; copy to instance.yaml to rebrand
rollups.yaml    program rollups (portfolio views across many agencies)
pipeline/       Python pipeline: fetch -> validate -> score -> publish
web/            static frontend; reads only published JSON
infra/          Terraform: artifacts CDN, submission function, fan-out compute
docs/           feeds, rubric, roadmap, api, fixes/ (KB), decisions/ (ADRs)
data/           raw snapshots (ignored) and published artifacts (committed)
```

## Guardrails

Three rules hold everywhere in this project: every metric is published with a
plain-language explanation of what it means; accessibility (WCAG 2.2 AAA) is
non-negotiable in the web app; and an agency without a realtime feed is shown
neutrally, never shamed. Contributor and agent-facing build rules live in
`CLAUDE.md`; current direction beyond the shipped roadmap is worked in the
open as labeled notes in [docs/ideation/](docs/ideation/).

## Maintainer

Built and maintained by [Chelsea Kelly-Reif](https://chelseakr.com), starting
from the transit systems in Davis, California. Contributions and corrections are
welcome; agencies can ask to be added or removed under the
[listing and removal policy](docs/listing-policy.md).
