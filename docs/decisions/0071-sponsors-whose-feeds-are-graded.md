# ADR 0071: Sponsors whose feeds are graded

**Status:** Accepted (2026-10-23). Decided by the maintainer.

## Context

The project is about to approach sponsors. Two gaps in its published copy would
have become promises the project could not keep.

1. **Disclosure contradicted itself.** `/support/` said sponsors are disclosed
   on the page and in the repository, "always". The GitHub Sponsors profile, on
   the $5, $25 and $100 tiers, said being listed is available on request and
   anonymous is the default. A sponsor could quote either.
2. **Conflicts were not covered.** The no-influence rules (ADR 0049, 0054,
   0063) say a purchase buys no influence over grades, methodology or listings.
   Nothing said what happens when a sponsor's own feeds are graded, or when a
   sponsor is a vendor named in the vendor view (ADR 0005), or builds feeds for
   agencies this site grades. `/procurement/` drafts a contract clause that
   holds vendors to grade B, so a vendor that funds the site is a direct
   conflict.

## Decision

### 1. Disclosure

Anonymous by default, named on request, with one exception that protects
readers.

- Sponsors are named on the /support/ page and in the repository if they ask to
  be.
- Anonymous sponsors are counted and their total is shown.
- A sponsor that publishes a feed graded on this site, or sells GTFS products
  or services, is always named.

### 2. Conflicts

- The share of graded feed records that belong to a sponsor, or that a sponsor
  built, is published beside its name.
- A feed a sponsor built or publishes is scored and framed identically to every
  other feed, by the same code and rubric. A sponsor's corrections go through
  the same public claim form as everyone's.
- Sponsorship is accepted only at the listed tiers.
- No sponsorship is accepted while the sponsor has an open dispute about its own
  grade.
- Vendors may sponsor this project; sponsors are listed on /support/ and are
  graded by the same rubric as every other vendor.

## Reasoning

Private sponsors are a normal GitHub Sponsors option and the profile already
promised it, so anonymous-by-default breaks no promise and costs no sponsor.
"Always named" stays true in the one case where disclosure protects readers: a
sponsor with a stake in the grades. Publishing the sponsor's share of graded
records makes the size of the stake visible instead of leaving readers to guess.
Capping sponsorship at the listed tiers stops any one sponsor from becoming
large enough to matter. The dispute rule stops money arriving while a grade is
being contested. Accepting vendor money in public, with the same rubric, was
chosen over refusing it, because vendors and consultants are the likeliest
sponsors and the disclosure and share rules make the relationship checkable.

## What this commits the maintainer to

- **A ledger.** Each sponsor, whether named or anonymous, with the tier, the
  graded feed ids it publishes or built, and the resulting share of graded
  records. The count and total of anonymous sponsors are derived from it.
- **The dispute rule.** Defining "open dispute about its own grade" (a pending
  claim or correction request on one of its feeds) and checking the claim queue
  before accepting a sponsorship.
- **Deciding what "sells GTFS products or services" covers**, and applying it
  consistently. This is not yet defined; until it is, ask before accepting from
  any sponsor in the transit-software or consulting space.
- **Telling such a sponsor before they pay** that they cannot stay anonymous and
  that their share of graded records will be published.
- **Keeping the GitHub Sponsors profile in step.** The profile is outside this
  repository and cannot be tested. The three tiers carry the disclosure text in
  the pull request that introduced this ADR.
- **No special handling.** A sponsor's feed correction, dispute or grade is
  handled by the public claim path only.

## Consequences

- `web/support/index.html`, `docs/support.md`, `SUPPORT.md`, `web/about/index.html`
  and `web/procurement/index.html` carry the sentences above. A test
  (`test_sponsor_disclosure_copy.py`) holds each surface and this ADR to the
  same sentences.
- Nothing is owed to anyone today: `/support/` says there are no sponsors yet.
- Supersedes the unqualified sentence "Sponsors are disclosed on this page and
  in the repository, always."
