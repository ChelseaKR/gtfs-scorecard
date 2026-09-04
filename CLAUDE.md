# CLAUDE.md — gtfs-scorecard (Small-Agency GTFS Quality Scorecard)

> Root instruction file for the `gtfs-scorecard` repo. Read fully before writing code.

> **Status (2026-08):** the four build phases below have shipped, and the pilot
> grew into a live service: the registry carries more than 2,600 curated feed
> records, with more than 2,100
> published scorecards, still concentrated in the US and Canada and now
> carrying reviewed global canaries, scored daily at gtfsscorecard.org, with a
> versioned read API, a GitHub Marketplace action, and an MCP server. This file
> remains the product spec
> (framing, rubric, quality bar — those hold). For what exists now, read
> `README.md`; for what's next, `docs/roadmap.md`, `docs/product-roadmap.md`,
> and `docs/ideation/`.

## What this is

A web dashboard plus ingestion pipeline that scores the quality of a transit agency's GTFS
Schedule and GTFS-Realtime feeds, designed around the needs of small and rural agencies and the
state staff who support them. Pilot agencies: **Unitrans** (ASUCD/City of Davis) and **Yolobus**
(Yolo County Transportation District) — the builder's home systems in Davis, CA.

The user to design for is not a developer. It is (a) the transit manager at a 20-bus agency who
inherited the GTFS export from a vendor and has no way to know if it's any good, and (b) a
Caltrans district liaison or Cal-ITP-style customer success manager preparing for an agency
check-in who wants one screen that says "here's how your data is doing and here are the three
things to fix."

## Why it exists

California's statewide transit data programs (the Caltrans transit data guidelines, Cal-ITP's
customer success work with small and rural agencies) created the playbook for helping small
agencies publish good GTFS, and the people doing that support need one screen they can have
open during an agency call. This scorecard is built for that conversation.

Implications:
- **Empathy over engineering flash.** The differentiator is the framing of findings as plain-
  language, prioritized recommendations, not the pipeline.
- **Demo-ability is a hard requirement.** A live URL showing real Unitrans and Yolobus data,
  loading fast, presentable on a phone across a café table.
- Public framing everywhere: an open-source data quality tool for small transit agencies,
  piloted in Yolo County.

Additional private working context, if any, lives in `CLAUDE.local.md` (gitignored); read it
when present, never commit it or echo its contents into tracked files.

## Data sources (verify, don't assume)

- Discover the canonical GTFS Schedule and GTFS-RT endpoints for Unitrans and Yolobus via the
  Mobility Database (mobilitydatabase.org) and transit.land. Record the exact URLs, license
  terms, and update cadence in `docs/feeds.md`. Respect polling etiquette: GTFS-RT no more than
  every 30–60s during demo capture windows, schedule feed daily.
- California-specific context worth citing in docs: Caltrans has GTFS quality guidelines and
  Cal-ITP publishes GTFS guidance for CA agencies. Fetch and read these before finalizing the
  scoring rubric so the rubric maps to what CA agencies are actually asked to do.
- The MobilityData `gtfs-validator` (Java, canonical) and its notice taxonomy: run it as a
  subprocess or in CI against pilot feeds and ingest its JSON report rather than reimplementing
  hundreds of validation rules. This project's value-add is the scoring, trending, and
  plain-language layer on top — not re-validating GTFS from scratch.

## Architecture

Two deployable pieces, kept deliberately small:

```
gtfs-scorecard/
├── CLAUDE.md
├── README.md
├── pipeline/                      # Python 3.11+, runs on a schedule
│   ├── pyproject.toml
│   ├── src/scorecard_pipeline/
│   │   ├── fetch.py               # download static GTFS; sample GTFS-RT snapshots
│   │   ├── validate.py            # wrap MobilityData gtfs-validator; parse JSON notices
│   │   ├── metrics.py             # compute scorecard metrics (see rubric below)
│   │   ├── rt_drift.py            # schedule-vs-realtime adherence from RT samples
│   │   ├── score.py               # rubric → category scores → letter grade + top 3 fixes
│   │   └── publish.py             # write versioned JSON artifacts to object storage
│   └── tests/
├── web/                           # static frontend, no backend server
│   ├── index.html                 # agency picker + scorecards
│   └── src/                       # vanilla TS or lightweight React; charts via Recharts/d3
├── infra/                         # IaC for the pipeline schedule + storage + hosting
└── docs/
    ├── feeds.md                   # source endpoints, licenses, cadence
    ├── rubric.md                  # full scoring methodology, with citations
    └── decisions/                 # short ADRs for anything non-obvious
```

Infrastructure: serverless AWS, mirroring the builder's existing job-alert pipeline patterns —
EventBridge schedule → Lambda (or a small Fargate task if the Java validator needs more memory)
→ S3 for JSON artifacts → CloudFront + S3 static hosting for the web app. Total run cost must
stay in single-digit dollars/month. IaC in Terraform or SAM, committed. If the Java validator is
too heavy for Lambda, run it in GitHub Actions on a cron and commit/publish artifacts — boring is
fine; document the tradeoff in an ADR.

The frontend reads only pre-computed JSON. No API server, no database. History = dated JSON
artifacts; trends are computed at publish time.

## The scoring rubric (the actual product)

Four categories, each 0–100, with an overall weighted grade. Every metric must carry: a plain-
language explanation, why a rider or agency should care, and a concrete fix. Draft rubric —
refine against Caltrans/Cal-ITP guidance once fetched:

1. **Correctness (35%)** — from gtfs-validator notices, weighted by severity. Surface counts,
   but translate the top notices: "4 stops are more than 100m from their street location —
   riders' trip planners will point them to the wrong corner."
2. **Freshness (20%)** — feed_info validity window present and current; calendar covers the next
   N weeks; days until service expiration (the classic small-agency failure: the feed silently
   expires and trip planners drop the agency).
3. **Rider experience completeness (25%)** — wheelchair_boarding populated on stops/trips;
   fare data present; stop names human-readable; headsigns present; agency contact/url valid.
   Accessibility fields get prominent placement — this is a values statement and a real gap.
4. **Realtime quality (20%)** — RT feed reachable and fresh (header timestamp lag); % of
   scheduled trips represented in TripUpdates during sampled windows; vehicle positions
   plausible (on/near route shape); schedule-vs-RT drift distribution. If an agency has no RT
   feed, show "Not yet published" neutrally, not as a zero — small agencies without RT shouldn't
   be shamed.

Each agency page leads with: overall grade, trend arrow, and **"Top 3 things to fix"** in
imperative plain language with effort hints (e.g., "Likely a one-line fix in your scheduling
software export settings").

## Build plan

> All four phases are done, including Phase 4's manifest-backed agency
> registry. The phases stay here as the record of the intended shape;
> current work is tracked in the roadmap docs named at the top.

### Phase 1 — Pipeline to first artifact (week 1)
- Feed discovery and `docs/feeds.md`. Fetch + archive static GTFS for both agencies.
- gtfs-validator integration; parse notices into a normalized findings model.
- Correctness + Freshness metrics; `score.py` producing the JSON artifact schema (version it:
  `schema_version` field from day one).
- Definition of done: one command produces `unitrans/2026-06-XX.json` and `yolobus/...` locally.

### Phase 2 — Web app (week 2)
- Static site: agency picker, scorecard page (grade, categories, top-3 fixes, findings table
  with severity filters), trend chart once ≥2 artifacts exist.
- WCAG 2.2 AAA: semantic HTML, keyboard navigable, color contrast checked, no color-only meaning,
  charts with text alternatives. This is non-negotiable and should be visibly done well — the
  audience reviews accessibility for a living.
- Mobile-first layout (the demo happens on a phone).
- Deploy behind a real URL.

### Phase 3 — Realtime + completeness (week 3)
- RT sampling job (capture windows of TripUpdates/VehiclePositions via gtfs-realtime-bindings),
  rt_drift metrics, Realtime category live for whichever pilot agencies publish RT.
- Rider-experience completeness metrics.
- `docs/rubric.md` finished with citations to Caltrans/Cal-ITP guidance and the validator notice
  taxonomy.

### Phase 4 — Generalize (post-coffee)
- Manifest-backed registry config so any feed URL can be added; document "add
  your agency in 10 minutes."
- Optional: a third pilot agency (e.g., an MST-sized system) added live during a demo — keep
  this in the back pocket, do not pre-build.

## Quality bar

- Pipeline: pytest with recorded fixture feeds (a trimmed real GTFS zip in tests/fixtures);
  ruff + mypy in CI; the publish step is idempotent and safe to re-run.
- Frontend: Lighthouse accessibility score ≥ 95; loads under 2s on 4G.
- Every metric in the rubric has a docstring linking the rationale in rubric.md. No metric ships
  without its plain-language explanation written.
- Git history tells a clean story; conventional commits.

## Writing style for all public docs and UI copy

Plain, concrete, practitioner-facing. At most one em dash per page, prefer zero. No rhetorical
rule-of-three constructions. No hype adjectives. UI copy addresses the agency reader directly
and respectfully; findings are framed as fixes, never as failures. Vary paragraph and sentence
openings; do not over-polish.

## Open questions to resolve early (all resolved)

1. Feed URLs and licenses for Unitrans and Yolobus — resolved in `docs/feeds.md`.
2. Pilot GTFS-RT — Yolobus publishes three open RT feeds and the Realtime category scores them. Unitrans moved passenger predictions from UmoIQ to Swiftly in March 2026, but no public Swiftly GTFS-RT endpoint is documented; realtime remains unmeasured and nothing is deducted.
3. Validator runtime — Actions-cron with a sharded matrix; see `docs/decisions/0001-validator-runtime.md`.
4. Caltrans/Cal-ITP guidance — cited throughout `docs/rubric.md` and mapped in `docs/crosswalk.md`.

## Agent entrypoint (moved from README "For Claude Code", 2026-07-19)

This file is the build spec: product framing, rubric, and quality bar. The
original four build phases have shipped; current direction lives in the
roadmaps and `docs/ideation/`. Hard rules: every metric ships with its
plain-language explanation; accessibility (WCAG 2.2 AAA) is non-negotiable in
the web app; agencies without realtime are shown neutrally, never shamed.
(Agent-facing instructions live here, not in the README; the README states the
same guardrails for visitors under "Guardrails" and points here. Under the
v1.0.1 pin this was a declared divergence: that standard's §2 table assigned the
Claude Code build entrypoint to the README and its §7 told an agent to start
there, and it had no §9. The pin moved to v2.0.0 on 2026-08-09, which added §9
"Audience register" and amended §7's first bullet, so DOC-18 now requires the
arrangement this repo already had. Re-checked 2026-08-15: `agent_docs_separated`
passes. What was a divergence is conformance under the current pin.)
