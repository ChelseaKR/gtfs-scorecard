# Standards conformance: applicability and review items

This repo is governed by the shared portfolio standards vendored at
[`docs/standards/`](standards/) and pinned by
[`docs/standards/.standards-version`](standards/.standards-version). The
`standards-pin` required check verifies every vendored byte against the reviewed
v1.0.1 manifest. Vendored files are not edited locally.

This is the applicability declaration required by the standards. It records
honest review items, not an aspirational percentage. Evidence lives in the
linked artifacts and required workflows.

| Standard | Applies? | Current evidence and remaining review items (2026-07-10) |
|---|---|---|
| [CODE-QUALITY](standards/CODE-QUALITY-STANDARD.md) | Applies (Python and a no-build vanilla-JS frontend) | Ruff, mypy, pytest, golden rendering, browser tests, and the main-branch ruleset are enforced. The documented complexity ratchet and accepted mutation survivors remain managed quality work, not silent omissions. |
| [SECURITY & SUPPLY-CHAIN](standards/SECURITY-AND-SUPPLY-CHAIN-STANDARD.md) | Applies (ASVS L1 shape: no auth or PII store) | pip-audit, CodeQL, container scanning, archive preflight limits, a time-bounded VEX, CycloneDX SBOM, signed release manifest, and provenance attestations are wired. The VEX expires 2026-10-08 and must be renewed only after upstream review. |
| [CI/CD](standards/CI-CD-STANDARD.md) | Applies | Required checks, dependency review, CodeQL, zizmor, OpenSSF Scorecard, pinned actions, least-privilege permissions, concurrency controls, and deployment smoke checks are present. Terraform modules are format-checked and validated offline per module in CI (`iac.yml`, added 2026-07-17); applies remain operator work. |
| [OBSERVABILITY](standards/OBSERVABILITY-STANDARD.md) | Applies as Tier B frontend + Tier C batch; see [ADR 0031](decisions/0031-observability-tier.md) | Lighthouse gates performance, accessibility, LCP, CLS, and total blocking time. Batch run summaries and failure artifacts provide the Tier C operational record. |
| [ACCESSIBILITY](standards/ACCESSIBILITY-STANDARD.md) | Applies fully; the public target is WCAG 2.2 AAA | Axe, contrast, keyboard, 320px reflow, reduced motion, forced colors, target size, and Lighthouse are automated. The remaining review-gate item is a dated human VoiceOver or NVDA walkthrough; automation is not represented as that attestation. See [manual test log](accessibility-testing.md) and [VPAT](vpat.md). |
| [INTERNATIONALIZATION](standards/INTERNATIONALIZATION-STANDARD.md) | Applies | Reviewed `en`/`es` catalogs have key-parity tests and `/es/` provides a Spanish-first agency lookup with explicit scope. The feature API separately measures rider-facing GTFS `translations.txt`; that does not mean this interface is translated. Full technical scorecard localization remains steward-gated work, not a claim made by this release. |
| AI-EVALUATION | **N/A** | No model inference exists in a user-facing or decision-making path. The MCP server retrieves read-only data and does not use an LLM SDK. Reassess on first model integration. |
| [QUALITY & METRICS](standards/QUALITY-AND-METRICS-STANDARD.md) | Applies | Data lineage, validation, test gates, CWV budgets, rollback steps, and the [release checklist](release-checklist.md) are documented and enforced where automatable. |
| [DOCUMENTATION](standards/DOCUMENTATION-STANDARD.md) | Applies | README conformance links, this declaration, ADRs, runbooks, API docs, standards manifest, and the self-contained `standards-pin` gate are present. |
| [RELEASE & VERSIONING](standards/RELEASE-AND-VERSIONING-STANDARD.md) | Applies | Versions are cross-checked; changelog generation, tag-triggered releases, CycloneDX SBOM, VEX, signed checksum manifest, and build-provenance attestations are wired. Protected stable tags remain a repository-administration control. |
| [RESPONSIBLE-TECH](standards/RESPONSIBLE-TECH-FRAMEWORK.md) | Applies; AI-governance rows are N/A | The [audit register](RESPONSIBLE-TECH-AUDITS.md), consequence scan, bias review, DPIA-lite, and threat model are committed under `docs/audits/`. |

Two items remain deliberately review-gated or externally operated: a human
screen-reader pass, and the separately documented S3 source-of-truth cutover.
Neither is silently treated as complete.
