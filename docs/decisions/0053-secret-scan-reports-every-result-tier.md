# ADR 0053: The history secret scan reports every result tier, in two lanes

**Status:** Accepted (2026-09-06)

## Context

TruffleHog files every finding into one of three result tiers:

- **`verified`** — it presented the credential to the provider and the provider
  said it is live.
- **`unknown`** — verification could not be completed.
- **`unverified`** — it asked, and the provider said no.

`trufflehog.yml` ran `--results=verified`. That means the weekly full-history
sweep could report only credentials that still work **right now**.

A credential that leaked and was later **revoked** answers "no", so it is
`unverified` and never `verified`. Revocation is the normal end state of a real
incident: somebody notices, the key is rotated, and the bytes stay in the history
forever. A sweep that exists specifically to find what was committed and taken
back out therefore could not fail on the single case it was written for, and went
green for it.

Measured 2026-09-06 on a throwaway clone with a real-shaped AWS key planted in one
commit and deleted in the next. The plant was confirmed present in history and
absent at HEAD before any of these numbers were trusted, and the key was
deliberately **not** AWS's documented example credential — TruffleHog filters that
one out under every tier, so a sabotage using it silently no-ops and reads as a
pass:

    --only-verified                        exit 0,   nothing reported
    --results=verified                     exit 0,   nothing reported
    --results=verified,unknown             exit 0,   nothing reported
    --results=verified,unknown,unverified  exit 183, unverified_secrets: 1

## What the widened tier reports on this repository

All 931 commits of `main` were re-scanned in an isolated clone with trufflehog
3.97.1 and the existing `--exclude-detectors=Lob`. The result was **0 verified and
34 unverified** findings, and every one of the 34 is a fact about somebody else's
infrastructure or a synthetic fixture:

| detector | count | where | what it is |
|---|---|---|---|
| `AWSSessionKey` | 12 | `data/artifacts/**/*.json` | `AWSAccessKeyId=ASIA…` inside a presigned S3 URL recorded as `fetch.final_url` when the pipeline downloaded a public feed from `api.gtfs-data.jp` |
| `AzureSasToken` | 12 | `data/artifacts/**/*.json` | `sig=…` inside a presigned Azure Blob URL from `api-public.odpt.org`, one of them with a two-minute SAS window (`st=…15:48:27Z&se=…15:50:27Z`) |
| `RailwayApp` | 6 | `data/artifacts/**/*.json` | a feed UUID in the same URLs, which that detector's pattern mistakes for a token |
| `URI` | 3 | `pipeline/tests/` | synthetic DSNs on `example.org`: `alice:password@`, `alice:secret@`, `user:secret@` |

The first three are **other operators' temporary download credentials**, captured
as provenance for a feed this project fetched from their open-data portal. They
are expired by construction, they are not ours, and nothing this project does
could rotate them. The fourth is three hand-written test fixtures.

## Decision

The job runs **two lanes**, both over the full history:

    lane 1  --results=verified,unknown,unverified
            --exclude-detectors=Lob,URI,AWSSessionKey,AzureSasToken,RailwayApp

    lane 2  --results=verified --exclude-detectors=Lob     (if: ${{ !cancelled() }})

Lane 2 is the previous gate, unchanged, over every path. That is what makes lane
1's four extra exclusions cost nothing: the two lanes together are a **strict
superset** of what this job checked before. `!cancelled()` so a lane 1 failure
does not hide lane 2's verdict, while a cancelled run still stops both.

Both lanes now also carry `version: "3.97.1"`. The action's `version:` input
selects the image that scans (`ghcr.io/trufflesecurity/trufflehog:${VERSION}`) and
defaults to `latest`, so the `uses:` SHA pinned only the wrapper: this gate was
pinned at v3.95.8 and running whatever upstream had published most recently. The
ref was resolved **forward** to v3.97.1 rather than the input being pinned back to
3.95.8, so nothing is downgraded — ADR 0044 already rejected pinning backwards.

`pipeline/tests/test_trufflehog_workflow.py` holds all of it, including the
property that every detector lane 1 excludes stays armed in lane 2. Run against
the pre-change workflow it fails four of its six assertions.

## Consequences

- The sweep can now fail on a credential that leaked and was later revoked, which
  is what it was built to catch.
- `URI`, `AWSSessionKey`, `AzureSasToken` and `RailwayApp` no longer fail the job
  on `unverified`/`unknown` findings anywhere in the tree, only on `verified`
  ones. For a **live** credential in any of those shapes, coverage is exactly what
  it was before this change.
- This widens the SEC-19 narrowing declared for ADR 0044 rather than replacing it;
  `docs/standards-conformance-gaps.md` records both.
- The exclusions should be revisited if the pipeline stops recording
  `fetch.final_url` verbatim, or if those detectors stop matching presigned URLs.
  Removing the four names and getting a clean widened run is the test.

## Alternatives rejected

- **Leave the tier at `verified`.** That is the defect. It is the setting that
  cannot fail on a revoked credential.
- **Exclude `data/artifacts/` by path.** Wrong axis, and ADR 0044 already rejected
  it for `pipeline/tests/`. The workflow says in terms not to widen this to path
  exclusions. A detector name is the narrow instrument; a directory is not.
- **Widen the tier with no exclusions.** The job would be red every week on 34
  findings that are nobody's leak, and a gate that is always red is a gate nobody
  reads.
- **One lane with the four detectors off.** That would trade real verified-tier
  coverage for the fix. Lane 2 is the price of lane 1 being safe.
- **Strip presigned query strings out of `data/artifacts/**`.** That would edit
  recorded provenance to make a scanner quiet, which is the wrong direction: the
  artefact is a record of what was fetched.

[ADR 0044]: 0044-trufflehog-lob-detector-exclusion.md
