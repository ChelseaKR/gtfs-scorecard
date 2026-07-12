# Product roadmap

A multiyear view of what the scorecard does for its users and how that deepens
over time. This is the product companion to [`roadmap.md`](roadmap.md), which is
the infrastructure plan (how to scale the pipeline and hosting). That one is
about capacity; this one is about user value. Revise both as the pilot teaches
us what agencies actually need.

For the staged plan to turn this from a tool you look at into a service agencies
rely on — monitoring and alerts, the standards crosswalk, the supporter
workspace, and how it sustains itself — see [`service-plan.md`](service-plan.md).

## Who it is for, and the one job

Two users share one screen:

- The transit manager who inherited a GTFS export from a vendor and has no way
  to know whether it is any good.
- The program liaison (a Caltrans-district or Cal-ITP-style customer success
  role) who needs one screen open during an agency check-in that says how the
  data is doing and the three things to fix.

The job the product does is to turn a wall of validator output into a grade, a
reason to care, and the next fix, written in plain language and framed as fixes
rather than failures.

## Principles that do not move

Every item below is checked against these.

- Findings are framed as fixes, not failures. Absence of realtime is shown
  neutrally, never as a zero.
- No leaderboard that shames small agencies. Benchmarking, when it arrives, is
  context and encouragement.
- We score on top of the canonical MobilityData validator. We do not
  re-validate GTFS and we do not become a GTFS editor.
- Accessibility data gets prominent placement. It is a values statement and a
  real gap.
- Plain language, fast, mobile-first, open source.

## Where the product is today

About 1,140 US and Canadian agencies scored daily (piloted with Unitrans and
Yolobus, first cohort drawn from California); per-agency scorecards with a
grade, top-three fixes, a full findings list, and a named "fixed since last
check" diff; companion pages per agency for a board packet, call prep, and the
fix log; an "over time" trend with a per-category "what changed" summary;
program rollups for 46 states plus DC and named cohorts; opt-in feed-health
email digests and webhooks, with a weekly portfolio digest for liaisons;
embeddable badges and conformance marks; a notice-to-fix knowledge base with
per-vendor tool profiles; a searchable national directory; self-serve
submission and on-the-spot feed scoring; a versioned read API with a Parquet
table and a read-only MCP server; national views of problems, adoption,
realtime reliability, equity, and NTD readiness; crawlable pages on its own
domain; and a security-hardened pipeline. The next three years make it a
habit, then a reference, then infrastructure.

## Year 1: deepen and retain

The goal is the second visit. A scorecard checked once is a curiosity; one
checked monthly is a tool.

- **The retention loop.** Expiry and regression email digests, and the trend and
  "what changed" view on each scorecard, are the reasons someone comes back.
  These are shipped; the work now is tuning what counts as worth an alert.
- **Close the fix loop further.** Shipped: the scorecard names which findings
  cleared between runs, so a manager sees a specific fix land.
- **The knowledge base toward the whole taxonomy.** Each validator notice gets a
  plain-language page with the setting to change in the common scheduling tools.
  This is the durable differentiator and the main organic-search entry point.
  The highest-prevalence notices are covered; the long tail remains open work.
- **Per-vendor fix instructions.** Shipped as tool profiles: where the export
  tool is detected, the fix names that tool.
- **Two-minute onboarding.** Shipped: the self-serve form and the instant-score
  funnel open a pull request without the submitter knowing what YAML is.

Signals of success: agencies returning month over month, fix pages as the top
organic entry points, and the first agencies that visibly raise their grade.

## Year 2: broaden and benchmark

Coverage and context. Once the corpus is national, the product can tell each
agency where it stands and tell a program where to spend its time.

- **National coverage**, drawn from the Mobility Database. The scoring already
  generalizes; this is curation and trust at scale.
- **Benchmarking with care.** Percentile context for an agency's own size band,
  shown privately on its page and framed as encouragement, never as a ranking.
- **Vendor-level intelligence.** Aggregate by the scheduling tool that produced
  the feed, to see which exports tend to drop fare data or ship stale calendars.
  This is the finding a statewide program acts on, visible only at scale.
- **The liaison workspace.** Saved cohorts, an attention queue sorted worst-first,
  and a report to bring to an agency call. The rollup view is the seed.
- **Realtime maturity.** Sustained sampling, drift trends over time, and
  vehicle-accessibility scoring alongside the stop.

Signals of success: a program staffer planning their week from the cohort view,
and the first catch of a vendor update that broke one field across many feeds.

## Year 3: platform and ecosystem

Let other tools and programs build on it, and let agencies own their place in it.

- **A public read API and richer badges.** The artifacts are already public JSON;
  make it a documented, versioned API so agency sites and dashboards can pull a
  grade. Every badge links back, which is how the tool spreads without a
  marketing budget.
- **Verified self-management.** An agency proves control of its feed domain and
  from then on manages its own entry, including supplying realtime keys through a
  secure path rather than a pull request.
- **Meet agencies where they work.** Optionally deliver findings as issues on a
  feed's repository, a scheduled digest, or a webhook on a grade change.
- **White-label for programs.** The same rubric and pipeline under a statewide
  program's banner and agency list. Because the system is static artifacts plus a
  stateless pipeline, an instance is a configuration and a deploy, not a fork.
- **Beyond the US.** The region-specific parts of the rubric become pluggable so
  other jurisdictions map it to their own guidance.
- **The dataset as a public good.** Years of daily scores is a record of how
  transit data quality changes over time, useful to researchers and policy and
  published openly.

Signals of success: a third-party tool embedding the grade, a program running
its own branded instance, and the dataset cited in transit-data work.

## What we will not build

Naming the off-ramps keeps the product honest.

- Not a GTFS editor or a feed host. We point at the fix; the agency makes it in
  their own tool.
- Not a re-implementation of the validator. We adopt MobilityData's notices and
  add the scoring, trending, and plain language.
- Not a public ranking or a compliance hammer. The grade serves the conversation
  between an agency and the person helping it.
