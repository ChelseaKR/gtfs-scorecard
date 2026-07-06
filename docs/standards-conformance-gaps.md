# Standards conformance: applicability and open gaps

This repo is governed by the shared portfolio standards vendored at
[`docs/standards/`](standards/) (pinned to a tag; see
[`docs/standards/.standards-version`](standards/.standards-version) — never
edit those files locally, see `docs/standards/README.md` §"How a repo
declares conformance" and the integrity note in
[`docs/decisions/`](decisions/) history around 2026-07-05).

Per that README's rule 1, silent omission of a standard is itself a defect.
This page is the applicability declaration `README.md`'s conformance table
links to, plus a running list of the gaps a 2026-07-05 audit found, so the
link actually resolves to something instead of a placeholder. It is updated
as gaps close; it is not a substitute for the review-gated artifacts each
standard names (those live under `docs/` per-topic — the ACR at
`docs/accessibility.md`, the VPAT at `docs/vpat.md`, the mutation-testing
log at `docs/mutation-testing.md`, and so on).

| Standard | Applies? | Headline gaps (2026-07-05 audit) |
|---|---|---|
| [CODE-QUALITY](standards/CODE-QUALITY-STANDARD.md) | Applies (Python; TS/Node/frontend-toolchain N/A — `web/` is no-build vanilla JS, no `package.json` anywhere) | Branch-protection/required-reviews gates were unenforced (fixed 2026-07-05, see `.github/rulesets/main.json`); a 16-function complexity ratchet is tracked in `docs/lint-complexity-ratchet.md`; mutation score is short of the 70% target on 2 of 3 scoped modules (`docs/mutation-testing.md`). |
| [SECURITY & SUPPLY-CHAIN](standards/SECURITY-AND-SUPPLY-CHAIN-STANDARD.md) | Applies (ASVS L1 shape: no auth, no PII store) | No dependency-vulnerability scan (pip-audit/osv-scanner), no CodeQL, no container scan, no SBOM/signing yet — tracked in the remediation P1 items; `docs/RESPONSIBLE-TECH-AUDITS.md` (§F declarations) not yet written. |
| [CI/CD](standards/CI-CD-STANDARD.md) | Applies (19 workflows) | Required-status-checks ruleset landed 2026-07-05 (`.github/rulesets/main.json`); zizmor/CodeQL-for-actions/OpenSSF Scorecard not yet wired. |
| [OBSERVABILITY](standards/OBSERVABILITY-STANDARD.md) | Applies — **Tier B (frontend) + Tier C (batch)**, not the standard's default Tier A mapping; see [ADR 0031](decisions/0031-observability-tier.md) | Lighthouse CWV (LCP/INP/CLS) gate not yet added (accessibility-only today); structured JSON logging for the batch pipeline is polish, not urgent at this tier. |
| [ACCESSIBILITY](standards/ACCESSIBILITY-STANDARD.md) | Applies fully — civic content, self-declared WCAG 2.2 AAA | Strongest standard in this repo (62%); open items are REVIEW-GATE artifacts: a committed dated screen-reader walkthrough (template only exists today) and a few AUTO specs (320px reflow, reduced-motion, target-size). |
| [INTERNATIONALIZATION](standards/INTERNATIONALIZATION-STANDARD.md) | Applies — civic transit data, public-facing; the N/A path is unavailable | No `locales/` catalog yet; all UI strings are hardcoded English. Largest single remaining item in the remediation plan (P1-13); the civic multilingual-obligations review (P2-8) follows once a catalog exists. |
| AI-EVALUATION | **N/A** — no model inference in any user-facing or decision-making path (`AI-EVALUATION-STANDARD.md` §0); the MCP server (`server.json`) is read-only data retrieval, no LLM SDK. Flips to APPLIES on first LLM SDK use. | — |
| [QUALITY & METRICS](standards/QUALITY-AND-METRICS-STANDARD.md) | Applies (QM-10 data-quality/lineage named for this repo explicitly) | Performance/CWV budget not yet gated (see Observability row); release checklist / DoD artifact not yet written (remediation P2-5). |
| [DOCUMENTATION](standards/DOCUMENTATION-STANDARD.md) | Applies | This page + the README conformance table are the DOC-11/12/13 fix landing 2026-07-05; a CI job asserting the standards-pin byte-identity (DOC-01) is tracked as remediation P1-8. |
| [RELEASE & VERSIONING](standards/RELEASE-AND-VERSIONING-STANDARD.md) | Applies — marketplace action tags (`v1`/`v1.0.0`), monthly dataset releases, MCP registry entry | Weakest applicable standard (18%): tags are lightweight/unsigned, no CHANGELOG yet, no SBOM/provenance/signing on releases. Version numbers reconciled to `1.0.0` across `pyproject.toml`/`CITATION.cff`/`server.json` 2026-07-05 (`pipeline/scripts/check_versions.py` keeps them from drifting again); a real tag-triggered release pipeline is remediation P1-10. |
| [RESPONSIBLE-TECH](standards/RESPONSIBLE-TECH-FRAMEWORK.md) | Applies (audits A-F; AI-governance rows N/A — no AI system) | `docs/RESPONSIBLE-TECH-AUDITS.md` and the `docs/audits/` pack (consequence scan, bias review, DPIA-lite, threat model) not yet written — remediation P2-2/P2-3. |

**Overall:** roughly 35% strict conformance / 39% with the Observability
Tier-A block correctly re-tiered (2026-07-05 audit). The dominant failure
mode was not missing engineering — several standards here (accessibility,
code quality) are strong — it was gates that existed but weren't
merge-blocking, and declarations (like this page) that didn't exist yet.
Re-run the audit periodically and update this table; do not let it go stale
the way the README's prior silence did.
