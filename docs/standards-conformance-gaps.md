# Standards conformance: applicability and review items

This repo is governed by the shared portfolio standards vendored at
[`docs/standards/`](standards/) and pinned by
[`docs/standards/.standards-version`](standards/.standards-version). The
`standards-pin` required check verifies every vendored byte against the reviewed
v2.0.0 manifest. Vendored files are not edited locally.

This is the applicability declaration required by the standards. It records
honest review items, not an aspirational percentage. Evidence lives in the
linked artifacts and required workflows.

## Re-assessment against v2.0.0 (2026-08-15)

The pin moved from v1.0.1 to v2.0.0 on 2026-08-09. Under the standards' own
release policy a MAJOR bump means gates tightened, so the rows below were
re-run against the v2.0.0 checker rather than carried forward. Result:
**21 of 25 machine-checkable controls pass**. Four do not, and they are not
all the same kind of thing.

**Two are real gaps in this repo.**

`release_workflow` fails the tightened hardening shape. v2.0.0 requires a
release workflow with a trusted-main checkout guard, a read-only signed-tag
verification job (`git verify-tag`, `merge-base --is-ancestor`, an
`allowedSignersFile`, and a `cat-file -t` tag-object check under
`contents: read`), and a separate checkout-free write job that re-reads the tag
object before publishing. `release-sign.yml` has the `workflow_dispatch` tag
input and does keyless Sigstore signing, and it has none of the other three.
This is a genuine open item, not a naming difference, and it is stated here
rather than claimed as met in the row below.

`DOC-21` (capability claim ledger, new in v2.0.0) fails: `docs/capabilities.md`
does not exist. The repo makes public capability claims in the README and on
the site and does not bind them to repository-local evidence in the shape the
standard asks for.

**Two are artifacts of how the checker scopes a repository, not gaps here.**
Recorded so a future reader does not try to fix a phantom.

`tests_directory` reports "tests/ MISSING". The check looks only for `tests/`
or `test/` at the repository root. This repo's suite is `pipeline/tests/`,
merge-blocking, behind a 92% branch-coverage floor, and `uv run pytest -q`
reports 2,629 passed and 12 skipped as of 2026-08-22. Nothing is missing.

`adr_log` passes but reports "1 ADR(s)". It counts only `docs/adr/`, which holds
the seed record. The 51 real decision records are in `docs/decisions/`, which
the check never looks at. The number it prints is not a count of this repo's
ADRs.

**Two README shape failures, both now fixed.** DOC-11's executable checker
wants a `Standard`-first header with a state column, and the old two-column
`Standard | Applies?` table parsed as no table at all, so all fifteen
declarations were invisible. The table is now
`Standard | State | Standard document`, with every declaration preserved and
plain-text row labels (#294, merged 2026-08-22). DOC-17 wants a
quickstart-class heading in the README's first 60 lines; the Quickstart section
sat at line 92 and has been moved above the positioning prose, to line 19,
unchanged in content.

**What is not enforced.** `standards-pin.yml` verifies vendored bytes against
the pinned tag. It does not run the conformance checker, so none of the control
gates above blocks a merge in this repo. The four results were produced by
running `automation/conformance_check.py --repo . --no-network` by hand on
2026-08-15. Wiring that into CI is an open owner decision.

| Standard | Applies? | Current evidence and remaining review items (rows dated 2026-07-10 except where noted; re-assessed against v2.0.0 on 2026-08-15) |
|---|---|---|
| [CODE-QUALITY](standards/CODE-QUALITY-STANDARD.md) | Applies (Python and a no-build vanilla-JS frontend) | Ruff, mypy, pytest, golden rendering, browser tests, and the main-branch ruleset are enforced. The documented complexity ratchet and accepted mutation survivors remain managed quality work, not silent omissions. |
| [SECURITY & SUPPLY-CHAIN](standards/SECURITY-AND-SUPPLY-CHAIN-STANDARD.md) | Applies (ASVS L1 shape: no auth or PII store) | pip-audit, CodeQL, container scanning, archive preflight limits, a time-bounded VEX, CycloneDX SBOM, signed release manifest, and provenance attestations are wired. The VEX expires 2026-10-08 and must be renewed only after upstream review. **Narrowing (declared 2026-08-10):** the scheduled TruffleHog gate (SEC-19) now passes `--exclude-detectors=Lob`. That detector matches pytest function names of a certain length and its verifier confirms them as live keys, so it produced 94 verified false positives and no true ones. Every other detector still runs and still fails the job; see [ADR 0044](decisions/0044-trufflehog-lob-detector-exclusion.md). **Widened (declared 2026-09-06):** SEC-19 previously ran `--results=verified`, which reports a finding only when the provider confirms the credential is live -- so it could not fail on a credential that leaked and was then REVOKED, which is the normal end state of a real incident and the case a history sweep exists for. The job now runs two lanes: all three result tiers with `URI`, `AWSSessionKey`, `AzureSasToken` and `RailwayApp` off, and the previous verified-only gate unchanged beside it with those four still armed, so the pair is a strict superset of what it checked before. Those four are off in the widened lane only because it surfaces 34 findings that are other operators' expired presigned feed-download URLs recorded as provenance under `data/artifacts/`, plus three synthetic `example.org` DSNs in `pipeline/tests/`. Both steps now pin `version: "3.97.1"`; the input was absent, so the SHA pinned only the wrapper and the scan ran `latest`. See [ADR 0053](decisions/0053-secret-scan-reports-every-result-tier.md). |
| [CI/CD](standards/CI-CD-STANDARD.md) | Applies | Required checks, dependency review, CodeQL, zizmor, OpenSSF Scorecard, pinned actions, least-privilege permissions, concurrency controls, and deployment smoke checks are present. Terraform modules are format-checked and validated offline per module in CI (`iac.yml`, added 2026-07-17); applies remain operator work. |
| [OBSERVABILITY](standards/OBSERVABILITY-STANDARD.md) | Applies as Tier B frontend + Tier C batch; see [ADR 0031](decisions/0031-observability-tier.md) | Lighthouse gates performance, accessibility, LCP, CLS, and total blocking time. Batch run summaries and failure artifacts provide the Tier C operational record. **Divergence (declared 2026-08-10):** the core Lighthouse LCP budget is 2750 ms, not the 2500 ms lab gate [OBS-23] sets. Measurement over a week of `main` showed the first Lighthouse run of every job is a cold Chrome start, and that `median-run` selects its run by first-contentful-paint and time-to-interactive rather than by LCP, so the old budget was asserting startup cost with 12 ms of headroom. Steady-state LCP is 2134 ms. The budget is now a true median of five runs, and a blocking `first-contentful-paint` gate of 2000 ms was added as the tighter tripwire on the same paint path. The vendored standard is unedited. The representative-routes performance floor of 0.80 likewise sits below the ≥0.9 Lighthouse target in QUALITY-AND-METRICS §2 and [PERF-02]. That gap predates this change and is declared here rather than left implicit. It was not lowered further to accommodate the `/compare/` regression; reducing that page and then tightening its aggregation is tracked in [follow-ups](follow-ups.md). See [ADR 0045](decisions/0045-lighthouse-lcp-budget-and-warmup-run.md). |
| [ACCESSIBILITY](standards/ACCESSIBILITY-STANDARD.md) | Applies fully; the public target is WCAG 2.2 AAA | Axe, contrast, keyboard, 320px reflow, reduced motion, forced colors, target size, and Lighthouse are automated. The remaining review-gate item is a dated human VoiceOver or NVDA walkthrough; automation is not represented as that attestation. See [manual test log](accessibility-testing.md) and [VPAT](vpat.md). |
| [INTERNATIONALIZATION](standards/INTERNATIONALIZATION-STANDARD.md) | Applies | Reviewed `en`/`es` catalogs have key-parity tests and `/es/` provides a Spanish-first agency lookup with explicit scope. The feature API separately measures rider-facing GTFS `translations.txt`; that does not mean this interface is translated. Full technical scorecard localization remains steward-gated work, not a claim made by this release. |
| AI-EVALUATION | **N/A** | No model inference exists in a user-facing or decision-making path. The MCP server retrieves read-only data and does not use an LLM SDK. Reassess on first model integration. |
| [QUALITY & METRICS](standards/QUALITY-AND-METRICS-STANDARD.md) | Applies | Data lineage, validation, test gates, CWV budgets, rollback steps, and the [release checklist](release-checklist.md) are documented and enforced where automatable. |
| [DOCUMENTATION](standards/DOCUMENTATION-STANDARD.md) | Applies, with one declared divergence | README conformance links, this declaration, ADRs, runbooks, API docs, standards manifest, and the self-contained `standards-pin` gate are present. **Divergence (declared 2026-08-05):** the agent build entrypoint lives in `CLAUDE.md`, not in a README "For Claude Code" section, which is where §2's table and §7 place it. The move was made 2026-07-19 to keep the README first-contact prose readable for agency staff; the README's "Guardrails" section states the same hard rules and points to `CLAUDE.md`. The note in `CLAUDE.md` previously cited a "§9 [DOC-18]" for this, which does not exist in the pinned v1.0.1 standard, so it is recorded here as a divergence rather than as conformance. **v2.0.0 items (assessed 2026-08-15):** DOC-11's executable README-table checker and DOC-17's first-60-lines quickstart gate both failed on shape; the table was fixed by #294 and the quickstart move landed with this change, both on 2026-08-22. DOC-18 and DOC-19 pass. DOC-21 is a new open gap: there is no `docs/capabilities.md` binding public capability claims to repository-local evidence. The divergence note above refers to the v1.0.1 text; §7's first bullet was amended in v2.0.0 and DOC-18 now *requires* agent instructions to live outside the README, so what was a declared divergence is conformance under the current pin. |
| [RELEASE & VERSIONING](standards/RELEASE-AND-VERSIONING-STANDARD.md) | Applies, with one open gap | Versions are cross-checked; changelog generation, tag-triggered releases, CycloneDX SBOM, VEX, signed checksum manifest, and build-provenance attestations are wired. Protected stable tags remain a repository-administration control. **Open gap (v2.0.0, dated 2026-08-15):** `release-sign.yml` does not meet the tightened release-hardening shape. It is missing the trusted-main checkout/ref guard, the read-only signed-tag verification job, and the checkout-free write job that re-reads the tag object before publishing. Adopting the pinned reusable `release-authorize.yml` from portfolio-standards would satisfy all three; that has not been done. |
| [RESPONSIBLE-TECH](standards/RESPONSIBLE-TECH-FRAMEWORK.md) | Applies; AI-governance rows are N/A | The [audit register](RESPONSIBLE-TECH-AUDITS.md), consequence scan, bias review, DPIA-lite, and threat model are committed under `docs/audits/`. |

Two items remain deliberately review-gated or externally operated: a human
screen-reader pass, and the separately documented S3 source-of-truth cutover.
Neither is silently treated as complete.

[OBS-23]: standards/OBSERVABILITY-STANDARD.md
[PERF-02]: standards/PERFORMANCE-STANDARD.md
