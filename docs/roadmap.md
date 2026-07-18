# Roadmap: prove remediation before expanding

Last updated: 2026-07-16

This is the infrastructure and delivery roadmap for GTFS Scorecard. The
product counterpart is [`product-roadmap.md`](product-roadmap.md), and the
ordered near-term ship list is [`feature-roadmap.md`](feature-roadmap.md).
Earlier scale and expansion proposals remain available in [`ideation/`](ideation/)
as planning history, not as an active queue.

## Decision

The service already has enough distribution infrastructure to test its next
job. It should now prove that a specific GTFS problem can move through this
chain:

```text
alert -> accepted named action -> exact intended-feed recheck ->
provenance-stamped verified closure
```

The scorecards, read API, MCP server, GitHub Action, alerts, and program views
remain useful. They are the acquisition and evidence layer for this workflow.
Adding more validation, catalogue, or dashboard surface is not the current
goal. The full competitive decision and its evidence are in
[`competitive-positioning.md`](competitive-positioning.md).

## What is already shipped

The old regional and national scale plans landed ahead of their original
sequence. Treat these capabilities as baseline:

- The registry has more than 1,300 configured feed records in the current worldwide
  coverage, still concentrated in the United States and Canada. The artifact index
  has numeric current scores for more than 1,100 of them. The public status page
  reports the exact current configured and published counts.
- Sharded GitHub Actions validation, S3 artifacts, static Pages delivery, and
  public run health.
- A versioned read API, Parquet dataset, read-only MCP server, badges, and a
  reusable GitHub Action.
- Self-serve submissions, local and request-backed one-off checks, alerts,
  webhooks, program rollups, and liaison digests.
- Artifact schemas, fetch provenance, private raw-archive paths, comparable
  finding-clearance records, and fail-closed comparison rules.
- A notice-to-fix knowledge base, detected-tool guidance, and procurement
  language.

These features need maintenance, but none is a reason to defer the remediation
pilot.

## Parallel maintenance: consumer decision support

A MobilityData Slack consumer exposed a bounded problem in an already-shipped
surface: they looked in primary navigation and could not find the feature
finder. Once they found it, they said the accessibility detail supported their
decision, then named rider-facing translations and European coverage as the
remaining blockers.

This is one qualitative source. It justifies a small maintenance slice, not a
general expansion program:

- Put **Feed features** in primary navigation and deep-link to the focused
  finder.
- Measure `translations.txt`, including languages and translated tables, without
  changing grades.
- Keep old artifacts unknown until rescored and state the U.S.-heavy coverage
  denominator beside the filters.
- Use the evidence and thresholds in
  [`global-expansion.md`](global-expansion.md) before describing a European
  cohort as useful for decisions.

The translation detector and navigation change share the existing scoring and
static-render paths. They do not add a new service or compete with a participant
remediation cycle.

## Now: run the 90-day proof

### 1. Reusable release shipped

Completed and refreshed 2026-07-16. Marketplace release `v1.3.0` is public. The immutable
tag, signed release evidence, floating `v1` tag, public
[Marketplace listing](https://github.com/marketplace/actions/gtfs-scorecard-gate),
and downstream consumer runs are verified. The distribution prerequisite for
asking the GTFS community to test the workflow is satisfied.

Evidence: the public
[downstream smoke run](https://github.com/ChelseaKR/gtfs-scorecard-action-smoke/actions/runs/29551173480)
passed against both `v1.3.0` and `v1`.

### 2. Recruit the pilot

Recruit one support-program liaison and two feed maintainers or vendors. The
Marketplace listing is verifiably public, so share the project in MobilityData
Slack `#gtfs` as a request to test the alert-to-closure workflow. Do not frame
the post as another validator launch.

Before a request is sent, confirm:

- the intended public feed and how its identity will be checked;
- the participant role responsible for the next action;
- the existing channel where the participant tracks work;
- what evidence may be public and what must remain private.

One evidence-backed candidate is Wasco Dial-a-Ride. Its official Caltrans DDS
archive is still the January 2022 upload and now scores as expired. Treat this
as a recruitment lead only: a cycle begins only if Wasco and a support-program
liaison accept the request and confirm the intended feed identity.

### 3. Run six concierge-led remediation requests

Start with a small set of recurring findings that have a concrete export or
data fix. For each request:

1. Capture the feed identity, source and final URLs, fetch time, content hash,
   validator version, rubric version, scoring profile, and finding fingerprint.
2. Record the accepted owner or responsible role and any participant-approved
   external ticket reference. Keep personal contact details private.
3. Send a vendor-ready action with the affected field, rider relevance,
   expected result, and recheck condition.
4. Fetch newly published bytes from the same intended feed after the
   participant reports a change.
5. Issue a closure receipt only when feed identity and the measurement contract
   remain comparable. Otherwise label the recheck non-comparable.

Use the participant's existing email, ticket, webhook, or repository workflow.
Do not build a replacement ticket system during the pilot.

### 4. Add only evidence the pilot requires

The pilot may require a small private manifest, durable before-and-after bytes,
a receipt document, or a manual review screen. Build the smallest missing part
after a real request exposes the gap. Keep public owner details out of artifacts
and fail closed when evidence is incomplete.

Extend the knowledge base only for findings used in the pilot. The full notice
taxonomy is not a release dependency.

### 5. Decide at day 90

The pilot passes only when all of these conditions hold:

- At least two participants turn an alert into a named request.
- At least six requests are created and three reach verified closure across two
  participant organizations.
- Median time from alert to named owner is five business days or less after the
  first guided cycle.
- Every receipt is reproducible from recorded bytes, versions, and the finding
  fingerprint. No non-comparable change is counted.
- Median hands-on support time is twenty minutes or less per request by the
  third cycle.

Stop or change the wedge if fewer than two participants create requests after
two guided cycles, or no request reaches verified closure by day 90. Do not
scale a process that still takes more than thirty minutes of support per request
after the third cycle. Pause automated receipts after any false closure until
the identity or comparability fault is fixed.

## Next: only after the proof passes

These items become planned work only after the day-90 gate:

- **Open receipt contract and verifier.** Publish a portable schema and a
  deterministic verifier for participant-approved closure evidence.
- **Agency-owned quality passport.** Let an agency carry its verified feed
  identity and closure history between vendors or support programs.
- **Evidence-ranked repair playbooks.** Order guidance by observed closure
  evidence, with sample size, tool version, and unsuccessful attempts visible.
- **One workflow integration.** Automate the handoff surface the pilot actually
  used most. Integrate with it instead of inventing a new work queue.
- **Procurement acceptance record.** Turn the receipt into a neutral way to
  check whether a contracted export change reached the published feed.
- **Program learning.** Aggregate comparable, permissioned evidence only after
  the sample is large enough to avoid claims about a single agency or vendor.

## Later: demand-gated options

These are valid options, not commitments:

| Option | Gate before work starts |
| --- | --- |
| Verified agency self-management | Repeated claim or correction volume makes manual review a measured burden. |
| White-label and regional guidance | A named program agrees to operate an instance and provide local review. |
| European GTFS beta curation | The reviewed cohort can meet the 250-feed, 12-country, freshness, identity, and licensing gate in `global-expansion.md`. |
| Full interface localization | A named language steward owns translation review, pseudolocale and RTL checks, and ongoing copy quality. |
| Broader worldwide curation | A local steward owns licensing, source verification, and the regional consent or partnership requirements. The phased, defensibility-ordered plan is [`global-coverage-roadmap.md`](global-coverage-roadmap.md); its partnership-gated phase names this same requirement. |
| Deeper realtime sampling | A named program needs the result, grants endpoint access, and funds a bounded sampling plan. |
| Research dataset expansion | Retention, privacy, licence, and citation requirements are settled. |
| Vendor or program intelligence | Enough comparable verified closures exist to report a pattern without ranking or blame. |

## Maintenance with explicit triggers

Maintenance does not compete with the pilot unless a threshold is crossed.

| Area | Trigger | Response |
| --- | --- | --- |
| Validation compute | Daily Actions can no longer finish inside the operating window or cost cap. | Measure the bottleneck, then consider queue-backed workers or Fargate. |
| Registry layout | Review, loading, or merge conflicts become a recurring operational problem. | Complete the mechanical shard split behind the existing schema gate. |
| Site renderer | A change repeatedly crosses unrelated pages or golden tests cannot isolate regressions. | Decompose the renderer incrementally behind existing output contracts. |
| Hosted one-off scoring | Repeated public requests cannot be served safely by the local or GitHub-backed paths. | Trial a capped service with abuse protection and a hard cost ceiling. |
| Realtime | Existing bounded checks miss a documented support decision. | Add the smallest sampling window that answers that decision. |
| Canonical feed URLs | A configured ZIP redirects to HTML or a retired host while a provider or catalog offers a current candidate. | Create a human identity and reuse review queue; never switch a feed automatically. |

## Work that is cut or parked

- A second validator, general GTFS editor, feed host, or map-first viewer.
- A general public feed archive. Private evidence retention may support receipts;
  public redistribution remains a separate legal decision.
- A continuous cross-agency realtime archive without a named user and budget.
- Public agency leaderboards, percentiles, or vendor rankings.
- A replacement CRM, ticketing product, or general support platform.
- Consumer-app scraping and a broad multimodal mobility-health index.
- AI-generated fixes in the graded or automatically verified path.
- Coverage growth used as a success measure by itself.

The current roadmap succeeds when participants close reproducible work with less
effort. Feed count, page views, stars, Action installs, and Marketplace presence
are distribution measures, not proof of that outcome.
