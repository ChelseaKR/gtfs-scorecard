# Proposed upstream change to ACCESSIBILITY-STANDARD.md (portfolio-standards)

**Status:** Draft — not yet opened as a PR against `ChelseaKR/portfolio-standards`.
**Author context:** Written 2026-07-05 during gtfs-scorecard remediation. The vendored copy of
`docs/standards/ACCESSIBILITY-STANDARD.md` in this repo had been edited in-repo
away from the pinned `v1.0.1` tag instead of upstreaming the change. That was
wrong regardless of whether the new text was accurate, so the vendored file has
been restored byte-identical to `v1.0.1` (blob `1a80fc25a8b27905523aaa1a7932a13123884d07`).
This document captures what, if anything, from those edits was actually worth
proposing upstream — for a human to file as a real PR on `portfolio-standards`,
not for this repo to self-apply.

## The three edits that were made in-repo (now reverted)

1. Intro paragraph: added "`gtfs-scorecard` is fully WCAG 2.2 AAA across its
   site, with a per-criterion Accessibility Conformance Report at its
   `docs/accessibility.md`" to the list of repos exceeding the AA floor.
2. AUTO-GATES table, Lighthouse row: changed "`gtfs-scorecard` ... runs **no**
   a11y CI — it MUST wire LHCI" to "... now ships its ACR and a merge-blocking
   design-token contrast gate in CI; LHCI, axe-core, and pa11y still to wire."
3. §2.2 footnote: added "and `gtfs-scorecard` meets 2.4.12 and 2.4.13 site-wide
   (3.3.9 is N/A: no authentication)."

## Verification against the current repo state (2026-07-05)

| Claim | Verified? | Evidence |
|---|---|---|
| Ships a per-criterion ACR at `docs/accessibility.md` | **True** | `docs/accessibility.md` exists, dated, per-criterion table; `docs/vpat.md` (VPAT 2.5 Rev, dated 2026-06-22) cross-references it. |
| LHCI wired, blocking | **True, but not "still to wire"** — it is already wired | `.github/workflows/pages.yml:44-49`, `npx @lhci/cli@0.14 autorun` against `lighthouserc.json` (`categories:accessibility` ≥ 0.95), as a deploy gate. The edit's own claim that LHCI is "still to wire" was already stale when written. |
| axe-core wired, blocking | **True, but not "still to wire"** | `.github/workflows/a11y.yml` runs `pa11y-ci@3` with `"runners": ["axe"]` — axe is the rule engine underneath pa11y-ci, blocking on push+PR. |
| pa11y wired, blocking | **True, but not "still to wire"** | Same job, `--config .pa11yci.json`, no `continue-on-error`. |
| Merge-blocking design-token contrast gate | **True** | `pipeline/scripts/check_contrast.py`, invoked from `Makefile` / `ci.yml`, asserts AAA (7:1) across all themes. |
| Meets 2.4.13 Focus Appearance site-wide | **True** | `docs/accessibility.md:74` — "2.4.13 Focus Appearance | MET | ...". |
| Meets 2.4.12 Focus Not Obscured (Enhanced) site-wide | **Not verified — no evidence found** | `2.4.12` does not appear anywhere in `docs/accessibility.md` or `docs/vpat.md`. Either the criterion was never actually assessed, or it's an oversight in the ACR. This half of edit 3 should **not** be upstreamed as-is. |

## What's actually worth proposing upstream

Only the parts that are true and don't require re-litigating the standard's
own criticism should move. Suggested real diff for a `portfolio-standards` PR
(post v1.0.1, targeting a v1.0.2 release):

1. Intro paragraph: safe to add the AAA + ACR sentence, since both are real
   and dated.
2. Lighthouse row: **do not** copy the in-repo edit verbatim (it wrongly says
   LHCI/axe/pa11y are "still to wire" when they are in fact already blocking).
   Instead propose: *"`gtfs-scorecard` **≥ 0.95** (ships a blocking LHCI gate
   in `pages.yml`, blocking pa11y-ci/axe in `a11y.yml`, and a merge-blocking
   AAA design-token contrast gate; performance/CWV categories not yet
   asserted — tracked as OBS/P1-9)."* This is more accurate than either the
   original v1.0.1 text (now stale in the other direction) or the self-edit.
3. §2.2 footnote: propose adding **only** the 2.4.13 claim, with a citation to
   `docs/accessibility.md:74`. Leave 2.4.12 out until it is actually assessed
   and recorded in the ACR — filing that gap is tracked separately (add a
   2.4.12 row to `docs/accessibility.md` as a small follow-up; not blocking
   this proposal).

## Next step (manual, for the repo owner)

Open a PR on `ChelseaKR/portfolio-standards` against `ACCESSIBILITY-STANDARD.md`
using the language above (not the reverted in-repo edits verbatim). On merge
and tag (v1.0.2+), Renovate's custom manager (`renovate.json:5-13`) will bump
`docs/standards/.standards-version` here and pull the vendored copy through
the normal front door.
