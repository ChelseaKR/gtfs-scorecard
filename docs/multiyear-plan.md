# Multiyear plan, 2026-2029

Last updated: 2026-08-27

This file puts the project's existing planning documents into one ordered arc.
It does not replace them. [`roadmap.md`](roadmap.md) still holds the
infrastructure gates and the maintenance triggers,
[`product-roadmap.md`](product-roadmap.md) still holds the user-value argument,
[`feature-roadmap.md`](feature-roadmap.md) is still the 90-day ship list, and
[`ideation/`](ideation/) is still the historical planning record with its own
promotion rule. Every phase below cites where it came from.

Three of those documents were written at different times and none sequences the
others. That is the gap this file closes. It also records, in one place, which
phases an agent can finish and which are waiting on a named person, a licence
answer, or a decision that belongs to the owner.

## The argument

`roadmap.md` decided the next job: prove that a specific GTFS problem can move
from an alert, through an accepted named action, to a comparable recheck of the
intended feed, to a provenance-stamped closure. `feature-roadmap.md` step 2
puts that pilot in "active" and step 3 in "depends on a participant request".
It has been there since 2026-07-25 and issue #185 has been open since
2026-07-23.

A multiyear plan cannot be built on a step that waits on people who have not
agreed yet. So this arc has two tracks running at different speeds.

**Track A** is what the project can make true about itself while it waits: the
claims it publishes should be claims its own code can support, and the gates
that assert those claims should be capable of failing. This is not filler. The
recurring defect in this repo is a guardrail that is present, green, and
structurally incapable of failing, and the pilot's whole premise is that a
closure receipt can be trusted. A project that cannot keep its own gates honest
is not ready to issue receipts.

**Track B** is the closure work itself, in the order `roadmap.md` and
`product-roadmap.md` already put it. Its phases stay unstarted, with their gates
named, until participants exist.

## Track A: every published claim is one the code can support

### Phase 1 (2026 Q3) — The plain-language gate reads every finding

**Source:** `CLAUDE.md` quality bar ("Every metric in the rubric has a docstring
linking the rationale in rubric.md. No metric ships without its plain-language
explanation written"); `ideation/02-large-scale-fixes.md` FIX-08, which shipped
`check_readability.py` as the mechanism for that promise.

`check_readability.py` is merge-blocking and measured only
`notices.TRANSLATIONS`. The other half of the finding copy on an agency page is
written inline at each `Finding(...)` site, and had never been measured. 118
strings; 23 of them missed the bars the gate already enforced.

Done means: an inventory that reads both families from source, fails closed on
any site it cannot account for, prints what it deliberately does not measure,
and passes over rewritten copy without moving a threshold. ADR 0048.

### Phase 2 (2026 Q3) — The gate reads the rest of the authored reader copy

**Source:** the limit ADR 0048 states for itself; `CLAUDE.md`'s promise covers
every metric, not only findings.

A finding is not the only prose on the page. Each scored category carries a
`summary` sentence, `recommend.py` carries the beyond-the-grade block, and
`consequence.py` carries the impact sentences. Same promise, same bars, same
fail-closed inventory, one family at a time.

**Depends on Phase 1.**

### Phase 3 (2026 Q3) — Two guardrails that cannot currently fail

**Source:** issue #309 (the complexity ratchet drifts and nothing checks it,
measured drifting twice in seven days); issue #310 (the weight-sensitivity study
grades on the unrounded score, outside the `_validate_published_overall` guard
that exists to stop exactly that bug).

Both are the same shape as Phase 1: a control that reads as enforcement and is
not. #309 already names the repo's own precedent for the fix.

### Phase 4 (2026 Q3) — A failure names the feed it happened to

**Source:** issue #308, promised as a follow-up in #306, after four pipeline
runs died over roughly 20 hours on one feed's artifact and the traceback did not
say which feed.

## Track A continued: numbers and denominators that do not mislead

### Phase 5 (2026 Q4) — Say that the public corpus aggregates exclude realtime feeds

**Source:** issue #248; `docs/comparison-policy.md`, which already states the
homogeneity rule that causes it.

Every feed with measured realtime, 7% of the corpus and the only agencies doing
the thing the site spends a page encouraging, falls out of the `/pulse/` corpus
average, `api/v1/trend.json`, and the change lists. The reasoning is sound. The
disclosure is missing, and the omission points against the reader this project
is for.

The issue records three options. Option 1, state it plainly on the surfaces that
carry the number, is a disclosure and is built here. Options 2 and 3 re-base a
published methodology number and belong on the FIX-06 shadow-scoring path with a
methodology announcement, so they are the owner's call, not an agent's.

### Phase 6 (2026 Q4) — Publish the reporter counts the NTD analysis already produced

**Source:** issue #278.

`/ntd/` answers "45.0% of 1,125 tracked feeds", over this project's registry.
The reader wants the reporter denominator: how many NTD reporters obligated to
publish GTFS have nothing discoverable at all. `ntd_coverage.py` and the
committed RY2024 snapshot already compute it, and `data/ntd/PROVENANCE.md` says
in as many words that nothing reads them: "Neither is read by the pipeline, the
site, or the public API."

Done means the tiered reporter counts reach `/ntd/` and `api/v1/`, each with its
own denominator stated, the existing tracked-feed figure untouched beside them,
and a reporter with no discoverable feed shown as a limit of what open
catalogues can see rather than as a zero.

## Track B: the closure proof, in the order the roadmaps already set

Every phase here is gated on people. None of it is startable by an agent, and
none of it is started.

### Phase 7 (gated) — First closure receipt, produced by hand

**Source:** `feature-roadmap.md` step 3; `roadmap.md` "Run six concierge-led
remediation requests"; issue #185.

**Blocked on:** one support-program liaison and two feed maintainers or vendors
accepting a named request, and confirming feed identity, owner role, handoff
channel and privacy boundary. Wasco Dial-a-Ride is a recorded recruitment lead,
not a participant.

**Unblocked by:** a human sending the recruitment request and someone accepting
it. Nothing in the codebase is the obstacle.

### Phase 8 (gated) — Open receipt schema and deterministic verifier

**Source:** `roadmap.md` "Next: only after the proof passes";
`feature-roadmap.md` "Queue after a passing pilot" item 1.

**Blocked on:** Phase 7 producing at least one real receipt. `roadmap.md` step 4
is explicit that the schema is built after a real request exposes the gap, so
building it first would be inventing a contract for a workflow nobody has run.

### Phase 9 (gated) — Agency-owned quality passport

**Source:** `roadmap.md` "Next"; `product-roadmap.md` "Next: turn proven
practice into a product".

**Blocked on:** Phase 8, and on the permissioned closure history it carries.

### Phase 10 (gated) — Evidence-ranked repair playbooks; one handoff integration; procurement acceptance record

**Source:** `roadmap.md` "Next"; `feature-roadmap.md` queue items 3 to 5.

**Blocked on:** enough closures to rank by observed evidence rather than author
confidence, and on pilot evidence naming which handoff channel to automate.
`feature-roadmap.md` step 4 forbids building a generic workflow UI before the
pilot identifies the channel.

## Track C: demand-gated options, unchanged

These are recorded here so the arc is complete, with the gate each one already
carries. None is an agent task, and none is promoted.

| Option | Named gate | Source |
| --- | --- | --- |
| European GTFS beta curation | The reviewed cohort meets the 250-feed, 12-country, freshness, identity and licensing gate; Sweden needs Trafiklab credentials | `roadmap.md` "Later"; `global-expansion.md` |
| Full interface localization | A named language steward owns translation review, pseudolocale, RTL and ongoing copy quality. Engineering prerequisites are already in place (ADR 0038) | issue #251; `feature-roadmap.md` "Still steward-gated" |
| Accessibility completeness with depth (EXP-05) | A real assistive-technology SME pass, plus a second validator's runtime cost | `ideation/03-expansions.md` EXP-05 |
| Public vendor-regression surface (EXP-07) | One vendor interview; public copy stays aggregate and non-ranking | `ideation/03-expansions.md` EXP-07 |
| Community notice-to-fix knowledge base (EXP-08) | An ongoing moderation commitment | `ideation/03-expansions.md` EXP-08 |
| Stand up your own scorecard (EXP-15) | External adopters; RR:E11 pluggable region rubric first | `ideation/03-expansions.md` EXP-15 |
| Policy-effect study (EXP-16) | History spanning the RY2026 dates, plus a methodology SME | `ideation/03-expansions.md` EXP-16 |
| Byte-exact raw archive on S3 (FIX-02 tier) | An AWS account and the cost gate; public redistribution needs the feed-licence answer | `ideation/02-large-scale-fixes.md` FIX-02 |
| VoiceOver walkthrough | A human running assistive technology | issue #186 |
| Add-your-agency walkthrough from a clean fork | An outside contributor | issue #188 |

## Work that stays cut

Repeating this so the arc cannot be read as reopening it. Each is a decision
with a stated reason in `roadmap.md`, `feature-roadmap.md`, or
`ideation/04-impact-and-sequencing.md`: a second validator, a general GTFS
editor, a feed host, a public raw-feed archive, a continuous cross-agency
realtime archive, public agency or vendor rankings, a replacement ticket system,
consumer-app scraping, a broad multimodal index without a named place-level
user, AI-generated fixes in the graded or automatically verified path, and
coverage growth used as a success measure by itself.

## How to read a phase

Built means the code, the tests and the documentation are in the repository and
`make verify` is green over them. Gated means a named person, licence answer, or
owner decision is missing, and the gate is named above. No phase is represented
in the codebase by a stub, a placeholder, or a dead configuration key: work that
is not done lives in this file, not in the source.
