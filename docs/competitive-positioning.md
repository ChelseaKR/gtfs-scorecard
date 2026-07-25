# Competitive position: verify feed fixes and correct bad recommendations

Last reviewed: 2026-07-25

## Decision

GTFS Scorecard should not compete to become another validator, feed editor,
catalogue, or visual feed inspector. Those jobs are already served by capable
open projects and public programs. The defensible job is to carry evidence
through two accountable feedback loops:

```text
alert -> named owner or vendor action -> exact-feed recheck ->
provenance-stamped verified closure

producer challenge -> exact-feed review -> bounded rule correction ->
corrected result and explanation
```

The grade remains a useful triage surface. The reusable GitHub Action is a
distribution path. Neither is a durable advantage by itself. The product earns
an advantage only if it can show, without overstating causality, that a specific
problem was assigned, changed in newly published feed bytes, and independently
rechecked, or that a specific recommendation was challenged, tested against the
feed's actual structure, and corrected without weakening unrelated cases.

## Where the work overlaps

This is a cooperative landscape, not a replacement market. Each project below
does a job the scorecard should reuse, link to, or complement.

| Project | Documented job | Implication for GTFS Scorecard |
|---|---|---|
| [Mobility Database catalogs](https://github.com/MobilityData/mobility-database-catalogs) | Publishes a worldwide catalogue with source identity, status, access, location, and license pointers. | Use it for discovery and source provenance. Do not build a competing feed registry or treat catalogue metadata as permission to republish a feed. |
| [Transitland feed versions](https://www.transit.land/documentation/concepts/static-gtfs-feed-versions/) | Archives distinct static GTFS versions, records checksums, and derives version metadata. | Link to its archive where useful. The scorecard's dated artifacts should add remediation context, not duplicate a general archive. |
| [MobilityData canonical GTFS Schedule validator](https://github.com/MobilityData/gtfs-validator) | Validates a local file or URL against GTFS Schedule rules and produces HTML and JSON reports. | Keep it as the rule engine and preserve its notice codes and version. Do not reimplement its taxonomy. |
| [gtfs.guru](https://github.com/abasis-ltd/gtfs.guru) | Provides a fast Rust validator across desktop, CLI, Python, web, WebAssembly, and CI surfaces. | Validation speed, local processing, and CI portability are active areas of competition. They are not a credible moat for this project. |
| [GTFS Analyzer](https://github.com/ttezer/gtfs-analyzer) | Runs locally in the browser and adds quality scores, operational analysis, maps, prioritization, fix guidance, and before-and-after run comparison that labels rules fixed, new, decreased, or increased. | A score, prioritized remediation list, and observational finding-clearance diff are no longer distinctive. Focus on what happens after a maintainer receives the list. |
| [GTFS Lens](https://github.com/strada-360/gtfs-lens) | Gives agency staff visual calendar, timetable, map, stop, and plain-language views of public or private feeds. | Do not build another broad feed viewer. Link from a finding to the best inspection surface when that helps a maintainer diagnose it. |
| [Ohtli](https://ohtli.codeandomexico.org/) | Offers browser-based static GTFS creation and editing for organizations with limited technical capacity. | Treat editing as an upstream partner job. Provide a precise handoff and verify the export after it is published. |
| [National RTAP GTFS Builder and support](https://www.nationalrtap.org/Technology-Tools/GTFS-Builder/Support) | Helps rural and tribal providers create and manage GTFS, with office hours and technical-assistance resources. | Do not replace human support. Give support staff a short action queue and evidence that a requested change landed. |
| [California Transit Data Guidelines](https://dot.ca.gov/cal-itp/california-transit-data-guidelines) and the [California GTFS Quality Dashboard](https://reports.dds.dot.ca.gov/) | Define California's quality expectations, provide technical assistance, and publish recurring provider reports. | Map findings to the guidance and support the check-in workflow. Do not present the scorecard as an official compliance determination. |

The public materials reviewed above do not establish an uncontested market
gap. Several projects already cover validation, scoring, visualization, and fix
prioritization. The narrower opportunity is independent evidence that a request
resulted in a comparable change to the intended published feed.

The shipped finding-clearance log is therefore parity, not the moat. It records
that a finding was present and then absent under a compatible measurement
contract, and deliberately does not say who changed the feed or why. The moat
begins only when an accepted action with accountable ownership is joined to
exact before-and-after evidence for the intended published feed. Until that
workflow is proven, call the shipped record a finding clearance, not a verified
remediation or closure.

Recommendation correction is a separate record. It does not claim that the
producer changed a feed. It shows that a producer challenged the scorecard's
advice, the project checked the affected rows and service pattern, and a bounded
rule or explanation changed as a result. That loop matters because generic
advice can be wrong even when its underlying completeness percentage is
calculated correctly.

### First recommendation-correction case

In [issue #180](https://github.com/ChelseaKR/gtfs-scorecard/issues/180), the
producer of MRC de Joliette's feed challenged advice to populate blank
`trip_headsign` values on one-way loop routes. Review showed that 152 of 164
trips already had headsigns. The 12 blanks were frequency templates for six
routes, and each affected route had one closed stop pattern, one shape, and one
direction. Repeating the route name would conflict with GTFS Best Practices,
while inventing clockwise or counterclockwise labels was unsupported.

The scoring rule was narrowed to credit only this verifiable simple-loop case.
Ambiguous, malformed, multi-pattern, or incomplete cases retain the existing
recommendation. The feed was rerun under the new contract, the headsign advice
disappeared, and the producer received the evidence and corrected result. This
is one useful trust-building case, not yet proof of a repeatable advantage.

## What not to build

- A second GTFS rule engine or a compatibility race with the canonical
  validator.
- A general GTFS editor, hosting service, or feed archive.
- Another map-first feed explorer.
- A public agency leaderboard or percentile system. It creates pressure without
  helping a maintainer close work, and mixed rubrics make comparisons unsafe.
- A replacement for Cal-ITP, National RTAP, or local technical-assistance staff.
  Their relationships and mandate are inputs to the workflow.
- Features justified mainly by page views, Action installs, or the number of
  feeds scored. Those measure distribution and processing, not remediation.

## The wedge: a verified remediation record

A closure record should be issued only when the evidence supports each link in
the chain:

1. **Alert.** Record the feed identity, source URL, fetched-at time, content
   hash, validator version, scoring profile, rubric version, notice fingerprint,
   and the relevant source rows.
2. **Ownership.** Attach the responsible organization or role and, when the
   participant agrees, an external ticket identifier. Keep personal contact
   details out of public artifacts.
3. **Action.** Turn the finding into a vendor-ready request with the affected
   file or field, rider relevance, expected result, and a concrete recheck
   condition.
4. **Exact-feed recheck.** Fetch newly published bytes from the same verified
   feed identity. A URL match alone is insufficient when aliases, regional
   bundles, or mirrored feeds are ambiguous.
5. **Verified closure.** Preserve before-and-after hashes and finding evidence.
   If the validator, rubric, measured category, or feed identity changed, label
   the result non-comparable instead of crediting the workflow for a fix.

This proves a published-data change, not a rider outcome. Claims about trip
planning, accessibility, or ridership still require separate evidence.

## The second loop: a recommendation-correction record

A recommendation-correction record should preserve:

1. The original scorecard, feed hash, raw metric, recommendation text, and
   measurement contract.
2. The producer's challenge and the operational context needed to test it,
   without exposing private contact details.
3. The exact source rows and structural facts that support or reject the
   challenge.
4. The bounded code, rubric, or wording change, including cases that must remain
   unchanged.
5. Focused regression tests, a rerun of the challenged feed, and a plain
   explanation to the producer.

Do not build a dedicated challenge form or public correction dashboard from one
case. Keep the loop manual until at least three independent recommendation
challenges from two organizations have been reviewed. Then decide whether the
repeated evidence warrants a template, issue type, or API record.

## Advantages that can compound

These advantages exist only after repeated real-world closures. They cannot be
created by adding more dashboard features.

| Asset | How it compounds | Guardrail |
|---|---|---|
| Outcome corpus | Links each notice, requested action, export context, elapsed time, and verified result. More closures reveal which advice works. | Publish only evidence that participants may share. Never infer causality from a cleared notice alone. |
| Recommendation-challenge corpus | Links producer context to exact feed structures, corrected advice, and protected regression cases. Repeated challenges reveal where generic guidance needs sharper boundaries. | Record accepted and rejected challenges. Do not tune a general rule to one feed without bounded evidence. |
| Tested fix playbooks | Vendor-specific instructions can be ordered by observed closure evidence rather than author confidence. | Show sample size, tool version, and unsuccessful attempts. |
| Workflow fit | Integrations with the ticketing, email, webhook, or repository surfaces maintainers already use reduce the cost of assigning work. | Integrate only after the concierge pilot shows the actual handoff. Do not build a new ticket system first. |
| Feed-identity and provenance discipline | Reproducible receipts build trust with agencies, vendors, support programs, and researchers. | Fail closed on ambiguous identity or changed measurement contracts. |
| Program and vendor learning | Aggregated, non-ranking evidence can identify recurring export defects and effective interventions across feeds. | Require a comparable cohort and avoid public claims about individual vendor performance from small samples. |
| Open distribution | The site, API, MCP server, and reusable Action can put the same evidence in different workflows. | Treat reach as an acquisition channel, not proof of value or a moat. |

The hardest asset to copy is the trusted outcome dataset plus the relationships
needed to produce it. The code for a receipt is straightforward. Getting a
maintainer or vendor to accept a request, publish a change, and let an
independent service preserve the evidence is not.

## Ninety-day pilot

Recruit one support-program liaison and two feed maintainers or vendors. Keep
the service concierge-led until the handoff is understood.

| Period | Work |
|---|---|
| Days 1-14 | Select a small set of actionable recurring findings. Confirm feed identity, publication path, owners, privacy boundaries, and the systems where work is already tracked. Capture a before artifact. |
| Days 15-60 | Send vendor-ready requests through the participant's existing channel. Record assignment and status. Recheck the published feed after each reported change and draft closure receipts. |
| Days 61-90 | Repeat the workflow with less facilitation. Audit every receipt, interview participants, and decide whether to automate, integrate, narrow, or stop. |

The pilot passes only if all of the following are true:

- At least two of the three participants turn an alert into a named request.
- At least six requests are created and at least three reach verified closure
  across two participant organizations.
- Median time from alert to named owner is five business days or less after the
  first guided cycle.
- Every closure receipt can be reproduced from its recorded feed bytes, tool
  versions, and finding fingerprint. No non-comparable change is counted.
- Median hands-on support time is twenty minutes or less per request by the
  third cycle.

Stop or change the wedge if fewer than two participants create requests after
two guided cycles, or if no fix reaches a verified closure by day 90. Do not
scale the concierge process if it still takes more than thirty minutes of
support time per request after the third cycle. Pause automated receipts after
any false closure until the identity or comparability fault is corrected.
Marketplace visibility, repository stars, Action installs, and scorecard views
are not pilot success criteria.

## Recommendation for the MobilityData Slack `#gtfs` channel

The project is worth sharing after the deployed scorecards, API, documentation,
and tagged Action all describe the same released measurement contract. Share it
as a request to test the remediation loop, not as the launch of another
validator. Do not claim a Marketplace listing until the public listing itself is
verified.

Suggested post:

> We built GTFS Scorecard, an open-source daily monitoring and plain-language
> triage layer for small transit agencies on top of MobilityData's canonical
> validator. We are now testing the next step: turn an alert into a vendor-ready
> request, recheck newly published bytes from the same feed, and preserve a
> reproducible closure record when the fix lands. We are looking for one
> support-program liaison and two feed maintainers or vendors for a 90-day
> pilot. If you handle GTFS support and can test the full alert-to-closure
> workflow, we would value your critique. [Live scorecards](https://gtfsscorecard.org/)
> and [source](https://github.com/ChelseaKR/gtfs-scorecard).

This framing credits the validator and neighboring projects, states that the
verification workflow is being tested, and asks the channel for evidence rather
than attention.

## Strategic risks

- **False attribution.** A finding may clear because the validator changed or a
  different feed was fetched. The receipt must fail closed when comparison is
  unsafe.
- **Overcorrection.** A valid producer challenge may tempt the project to exempt
  superficially similar feeds. Require structural evidence and regression cases
  that preserve the recommendation for ambiguous patterns.
- **Workflow capture by a larger program.** Cal-ITP, a vendor, or a catalogue
  could add closure tracking. The response is interoperability and an open,
  portable evidence format, not feature volume.
- **Participation bias.** Cooperative maintainers may produce better outcomes
  than the agencies most in need of support. Report pilot selection and avoid
  generalizing conversion rates.
- **Vendor and agency trust.** Public accountability can become public shaming.
  Default owner and ticket details to private, publish aggregate evidence only
  with adequate samples, and keep agency pages focused on fixes.
- **Operational burden.** Human follow-up can overwhelm a low-cost static
  service. Use the pilot's support-time threshold before promising scale.
- **Coverage bias.** The current corpus is concentrated in the United States and
  Canada. Do not present its finding mix or vendor patterns as representative of
  GTFS globally.
