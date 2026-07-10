# Responsible technology audit register

**Reviewed:** 2026-07-10  
**Scope:** GTFS Scorecard website, pipeline, public API, GitHub Action, alerts, and
optional serverless infrastructure. The product performs deterministic validation and
scoring; it does not use model inference or make eligibility decisions.

| Review | Artifact | Result | Recheck |
| --- | --- | --- | --- |
| Consequence scan | [`audits/consequence-scan.md`](audits/consequence-scan.md) | Proceed with named safeguards | Methodology or ranking change |
| Bias and disparate-impact review | [`audits/bias-review.md`](audits/bias-review.md) | Proceed; comparisons remain bounded and optional RT stays neutral | Rubric/data-source change |
| DPIA-lite | [`audits/dpia-lite.md`](audits/dpia-lite.md) | Low privacy risk; minimize subscriptions and logs | New personal-data field or processor |
| Threat model | [`audits/threat-model.md`](audits/threat-model.md) | Key abuse paths mitigated and CI-gated | New write API, auth, or infrastructure |

## Declarations

- No sensitive rider data, trip histories, precise user locations, or protected-class
  attributes are collected.
- Public agency data is scored, not people. Grades are not service-quality,
  compliance, procurement, or staff-performance certifications.
- Missing realtime is neutral. Ranked comparisons require measured, current records and
  a minimum cohort; individual scorecards remain available when rankings are suppressed.
- Feed corrections and agency claims require evidence and human review. Opening a request
  never verifies control or changes the registry automatically.
- Alert subscriptions use double opt-in, store only the minimum delivery information,
  and support removal.
- The accessibility target is WCAG 2.2 AAA. Automated evidence is merge-blocking;
  human assistive-technology evidence remains a maintained review artifact, not something
  automation can fabricate.

These are engineering assessments, not legal opinions or certifications.
