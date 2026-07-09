## What and why

<!-- A sentence or two on the change and the motivation. Link any issue. -->

## Acceptance criteria

<!-- What observable behavior proves this done? -->

## Rollback plan

<!-- Revert the merge commit? Feature-flag? Anything stateful (data, a
     schema, a published artifact) that a plain revert won't undo? -->

## Dependency rationale

<!-- Only if this PR adds/bumps a dependency: one line on why, mirroring the
     inline rationale style already used in pipeline/pyproject.toml. -->

## ISO/IEC 25010 characteristic

<!-- Which quality characteristic this change is primarily in service of
     (functional suitability, performance efficiency, compatibility, usability,
     reliability, security, maintainability, portability) — helps a reviewer
     weigh the change against the right bar. -->

## Checks

- [ ] `make verify` passes locally (lint, format, mypy, tests + 92% branch coverage, AAA contrast, plain-language readability, no bare TODO/FIXME/HACK)
- [ ] Findings and UI copy frame issues as fixes, in plain language
- [ ] Accessibility (any web/HTML change): the `Accessibility` axe gate and the contrast gate pass; a new page/route is added to `.pa11yci.json`; keyboard-operable with visible focus, correct labels/roles, no colour-only meaning, respects reduced motion
- [ ] If a primary task changed (nav, forms, scorecard, map, theme): the manual AT pass in [docs/accessibility-testing.md](../docs/accessibility-testing.md) was re-run and its log updated
