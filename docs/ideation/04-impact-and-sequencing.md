# Impact, sequencing, and gates

Drafted 2026-07-01. A cross-cut over every ID in `02-large-scale-fixes.md`
(FIX-01…FIX-13) and `03-expansions.md` (EXP-01…EXP-17): where each sits on impact
versus effort, what depends on what, a Now/Next/Later sequence that runs *beside*
the existing roadmaps rather than repeating them, and an honest, separated list of
the items that cannot proceed without a human, an SME, real accumulated data,
infrastructure spend, or a legal answer.

This is a planning aid, not a commitment. Impact is judged against the two people
the tool exists for (the inherited-feed manager and the liaison) and the portfolio
ethos (honesty enforced in code, reproducibility, accessibility). Effort tiers
match the source files: S ≈ days, M ≈ 1–2 weeks, L ≈ a month, XL ≈ a quarter.

## The matrix

Impact is High / Med / Low. "Depends on" names the load-bearing prerequisite (not
every soft link). "Gate" flags a non-engineering blocker, detailed in the last
section.

| ID | One-line | Impact | Effort | Depends on | Gate |
|---|---|---|---|---|---|
| FIX-01 | Record how each feed was fetched (origin vs mirror, UA) | High | S–M | — | — |
| FIX-02 | Content-addressed raw-feed archive for reproducibility | High | M | follow-ups S3 | infra + legal |
| FIX-03 | One source of truth for presentation constants | Med | M | — | — |
| FIX-04 | Decompose `render_site.py` behind golden files | Med | L | — | — |
| FIX-05 | Property-based + wider mutation testing of the math | High | M | — | — |
| FIX-06 | Governed validator/rubric upgrades (shadow + report) | High | M | (FIX-02 helps) | — |
| FIX-07 | Grade margins + weight-sensitivity study | High | S+M | — | — |
| FIX-08 | Managed plain-language coverage (metric + queue + gate) | High | M | — | SME (editorial) |
| FIX-09 | Behavioral frontend test harness | Med–High | M | — | — |
| FIX-10 | Machine-enforce the per-agency data contract | High | M | — | — |
| FIX-11 | Public pipeline-health surface | High | M | — | — |
| FIX-12 | Shard + schema-gate `agencies.yaml` | Med | M | — | — |
| FIX-13 | Data-plane remediation beyond the S3 cutover | Med–High | M–L | follow-ups 1–3 | human (decision) |
| EXP-01 | Measurement-confidence read on each card | High | S–M | FIX-01, FIX-11 | — |
| EXP-02 | Plain-language "grade story" per agency | High | M | history | — |
| EXP-03 | Fix-effort estimates calibrated from outcomes | Med | M | FIX-02 | real-data + time |
| EXP-04 | Calendar-aware freshness (seasonal vs lapse) | Med–High | M | — | — |
| EXP-05 | Accessibility depth as a celebrated sub-score | High | M | — | SME (AT) + infra |
| EXP-06 | Interactive methodology sandbox | Med–High | M | FIX-03, FIX-07 | — |
| EXP-07 | National vendor-regression radar | High | M–L | FIX-01 | partner (vendor) |
| EXP-08 | Community-contributable fix knowledge base | High | M | FIX-08 | human (moderation) |
| EXP-09 | Citable per-agency feed-quality record | Med | S–M | FIX-02, FIX-10 | legal (serving) |
| EXP-10 | Consumer freshness/uptime commitment | Med | S | FIX-11 | — |
| EXP-11 | Closed-loop guided fix + verification receipt | High | M | RR:R4/R5, autofix | red-line watch |
| EXP-12 | Scheduled portfolio digest for liaisons | Med–High | S–M | alerts stack | consent |
| EXP-13 | Predict feeds about to lapse | High | L | FIX-02, dataset | real-data + infra |
| EXP-14 | Place-based multi-standard mobility-data health | High* | XL | Canada scale, GBFS | partner + infra |
| EXP-15 | Forkable "stand up your own scorecard" template | Med–High | L | RR:E11 | partner (adopters) |
| EXP-16 | Policy-effect study (did RY2026 move quality?) | High | M–L | national_trend, dataset | real-data + SME |
| EXP-17 | Extract honesty primitives to shared STANDARDS | Med–High | M | — | portfolio owner |

\* EXP-14's impact is high only if a real place-level user asks; absent that, it is
a scope risk, not a win.

## Reading the matrix

**Do-first quadrant — high impact, low-to-moderate effort, no gate.** FIX-01,
FIX-05, FIX-07, FIX-10, FIX-11, and then EXP-01 and EXP-10 that consume them. Every
one converts a claim the project already makes in prose (reproducible, correct,
daily-fresh, honest about coverage) into a claim the pipeline enforces. This is the
highest-leverage cluster in the whole folder because the credibility of a
trust-brand product is exactly the thing least safe to leave asserted.

**Invest-deliberately quadrant — high impact, high effort.** FIX-04 (render
decomposition), FIX-08 (coverage governance), EXP-07 (vendor radar), EXP-13
(predictive lapse), EXP-16 (policy study). Worth doing, but each is a month or more
and several carry a gate; schedule them singly, behind the do-first cluster.

**Fill-in quadrant — moderate impact, low effort.** FIX-03, EXP-04, EXP-10,
EXP-12. Cheap, useful, and good candidates to interleave when a larger item is
blocked on a gate.

**Hold-until-gated quadrant — high effort and/or uncertain demand.** EXP-14
(XL, needs a named user and a second toolchain), EXP-15 (needs adopters), FIX-02
and everything hanging off it (needs the AWS/cost decision). These are real, but
starting them ahead of their gate is how a focused tool becomes an unfocused
platform — the exact scope risk named in `RESEARCH-ROADMAP.md`.

## Dependency notes

A few chains matter more than the table's single "depends on" column shows.

- **The provenance spine.** FIX-01 (fetch source) → EXP-01 (confidence read) and
  → EXP-07 (vendor radar keyed on producing tool) and → EXP-09 (record cites the
  provenance block). FIX-01 is small and unlocks three downstream items; do it
  early.
- **The reproducibility spine.** FIX-02 (raw archive) is the deepest dependency in
  the folder: EXP-03 (calibrated effort), EXP-09 (byte-reproducible record), EXP-13
  (behavioral prediction), and cleaner FIX-06 shadow runs all improve or unblock
  with it. But FIX-02 itself waits on the S3/AWS cutover in `follow-ups.md` and on
  a feed-license answer. It is the single highest-value gated item.
- **The single-source spine.** FIX-03 (generated constants) is a prerequisite for
  EXP-06 (the sandbox and the pipeline must agree by construction) and de-risks
  FIX-04 (decompose the renderer once the constants stop being scattered). Sequence
  FIX-03 before EXP-06 and before, not during, FIX-04.
- **The status spine.** FIX-11 (public health) feeds EXP-10 (consumer commitment)
  and EXP-01 (confidence). One surface, two outward-facing products.
- **The data-plane order.** FIX-13 (history remediation) must follow the
  `follow-ups.md` S3 cutover steps 1–3, so there is one migration story, not two.
- **The retention loop.** EXP-11 stitches shipped pieces (RR:R4 cleared-findings,
  RR:R5 tool detection, `autofix.py`) into one flow; it needs no new data, only
  integration, but it brushes the no-editor red line and must be built with that
  guardrail explicit.

## Now / Next / Later — a track beside the existing roadmaps

The existing plans already own two tracks: the operational finish-what-is-built
sprint (`RESEARCH-ROADMAP.md`: RR:R1–R4, R6–R9) and the multiyear scaling roadmap
(`roadmap.md` Years 1–3). This folder proposes a third, **the trust-and-depth
track**, sequenced so it does not collide with either. It assumes the RR first
sprint lands first.

**Now (0–1 quarter) — enforce the claims.** The ungated do-first cluster, ordered
by dependency:

1. **FIX-01** — fetch provenance. Small, and it is the one place the "states it"
   brand currently does not state it; unblocks EXP-01/07/09.
2. **FIX-10** — a JSON Schema for the per-agency artifact, validated in CI. The
   primary public contract is currently enforced only by prose.
3. **FIX-05** — property-based tests plus wider mutation scope on `metrics.py` and
   `rt.py`. The grade is the product; its math should be tested as invariants.
4. **FIX-07 (margins half)** — publish each grade's distance to its band edge; the
   sensitivity study can follow.
5. **FIX-11** — the public pipeline-health surface, then **EXP-10** (the consumer
   commitment) and **EXP-01** (the confidence read) over it.
6. **FIX-03** — generated presentation constants, clearing the way for EXP-06.

**Next (1–2 quarters) — deepen and stabilize.** FIX-06 (governed upgrades), FIX-09
(frontend behavioral tests), FIX-04 (render decomposition behind goldens), FIX-12
(registry sharding), FIX-08 (coverage governance, with its editorial gate named),
and the depth expansions that need only integration: EXP-02 (grade story), EXP-04
(calendar-aware freshness), EXP-06 (methodology sandbox), EXP-09 (citable record),
EXP-11 (closed-loop fix), EXP-12 (portfolio digest). Land **FIX-02** here the
moment its AWS/cost gate clears, because so much depends on it.

**Later (multi-quarter, gated) — the bets.** FIX-13 (history remediation, after
the S3 cutover), and the H3 expansions once their gates open: EXP-03 and EXP-13
(need accumulated history), EXP-05 (needs an AT/accessibility SME pass and a second
validator), EXP-07 and EXP-08 (need a vendor interview and a moderation
commitment), EXP-16 (needs history spanning the RY2026 dates plus a methodology
SME), EXP-14 (needs a named place-level user), EXP-15 (needs external adopters),
EXP-17 (needs the portfolio owner's cross-repo intent).

The through-line: spend the ungated near term making the honesty claims
enforced rather than asserted, then deepen, and let every gated bet wait behind a
declared gate rather than a faked one.

## Items behind a gate (declared, not worked around)

Per the portfolio ethos, these gates are stated so nothing below is built by
pretending its gate is met. Grouped by the kind of gate.

**Infrastructure / cost gate** (needs the AWS account and must hold the
single-digit-dollars-a-month line):
- **FIX-02** raw-feed archive — the S3 bucket decision from `follow-ups.md`.
- **FIX-13** history remediation — depends on the same cutover.
- **EXP-13** predictive lapse model — needs the Parquet dataset store.
- **EXP-14** place-based index — a second (GBFS) validator toolchain.
- **EXP-05** accessibility depth — a modest second-validator runtime cost.

**Real-data / time-depth gate** (needs longitudinal history the panel has not yet
accumulated, or that is discarded today — see FIX-02):
- **EXP-03** finding-clearance timing — needs compatible retained histories.
- **EXP-13** predictive lapse — needs behavioral history depth.
- **EXP-16** policy-effect study — needs history spanning the RY2026 effective
  dates.

**Human / SME gate** (needs sustained human judgment or a specialist the repo
cannot synthesize):
- **FIX-08** plain-language coverage — sustained editorial curation.
- **EXP-05** accessibility depth — a real assistive-technology / accessibility SME
  pass, the same gate `RESEARCH-ROADMAP.md` names for RR:R6.
- **EXP-08** community KB — an ongoing moderation commitment.
- **EXP-16** policy study — a methodology SME to keep causal claims honest.
- **FIX-13** history remediation — an irreversible maintainer decision on history
  and citation-tag continuity.

**Partner / external-user gate** (needs a real user or partner to ask, per the
`RESEARCH-ROADMAP.md` "validate before building" risk):
- **EXP-07** vendor radar (outward framing) — the one vendor interview.
- **EXP-14** place-based index — a named place-level user.
- **EXP-15** forkable template — external adopters (a state DOT, National RTAP).
- **EXP-12** portfolio digest — lighter: an extension of the ADR 0004 consent
  model to cohort subscriptions.

**Legal gate** (needs the feed-license question answered):
- **FIX-02** raw archive — redistribution rights vary by feed; a private-to-
  pipeline archive is safe, public reproduction is not, until answered.
- **EXP-09** citable record — serving an archived copy inherits the same question.

**Portfolio-owner gate:**
- **EXP-17** shared-standard extraction — a cross-repo act only the maintainer can
  authorize.

**Red-line watch** (not a gate but a boundary to honor at build time):
- **EXP-11** and **EXP-14** must each be checked against the standing deliberate
  no's — no feed editor, no punitive ranking, no platform sprawl. EXP-11 stays safe
  because the agency always publishes; EXP-14 stays safe only if a real place-level
  user is driving it.

## The honest bottom line

Nothing here is validated with a real user, costed against the budget guardrail,
or approved by the maintainer. The strongest, safest work is the ungated Now
cluster: it makes the trust-brand claims true in code, needs no partner and no
new infrastructure, and is mostly S/M effort. The most valuable *gated* item is
FIX-02, because the reproducibility spine unlocks four downstream expansions. The
biggest scope risk is EXP-14. Everything else is honest optionality, held behind a
gate that is declared rather than skipped.
