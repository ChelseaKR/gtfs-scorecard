# CI Action: gate a build on feed quality

Run the scorecard inside any GitHub Actions workflow and fail the build when a
GTFS Schedule feed drops below a grade or is about to expire. This is the same
`scorecard try` gate the project uses, packaged so a vendor or agency can catch
a bad export before it ships.

## What it does

The action downloads the feed, runs the MobilityData gtfs-validator, scores it
against the rubric, and exits non-zero when a threshold you set is breached.
Nothing is published; the feed is scored in place and the result is the build's
pass or fail.

## Quick start

Add a step to a workflow. This example fails the build if a nightly export
grades below B or has under 14 days of service left:

```yaml
name: Check the GTFS feed
on:
  schedule:
    - cron: "0 8 * * *"
  workflow_dispatch:

jobs:
  gtfs-quality:
    runs-on: ubuntu-latest
    steps:
      - uses: ChelseaKR/gtfs-scorecard@v1.4.0
        with:
          feed-url: https://example.org/gtfs/feed.zip
          name: Example Transit
          country: CA
          min-grade: B
          min-days-to-expiry: 14
```

### Which ref to pin

Name a full release tag, as the example does, or a commit SHA. `v1.4.0` is the
newest published Action release, so a workflow that pins it runs a build whose
behaviour is written down on this page and cannot change underneath it.

**The floating major `@v1` is not recommended.** The Marketplace convention
offers it, and this repository keeps it for the consumers who already use it,
but it is a single mutable pointer: it moves to the newest `v1.x.y` on release
day, so a workflow naming it changes what it runs with no commit, no review and
no diff on your side. It has not moved since 2026-07-25, while `main` has taken
on hundreds of commits since, so its next move will be a large jump made
silently in every workflow that names it. Pin a release and upgrade on purpose.

**What `v1.4.0` does not yet include.** The refusal of an unreadable archive
described under [Inputs](#inputs) is on `main` and is in no published release.
`@v1.4.0` — and `@v1`, which points at the same commit today — still grade an
archive that carries no schedule data rather than refusing it. Version 1.5.0
has a `CHANGELOG.md` entry but no tag and no release, so there is nothing newer
to pin to yet. Tag namespaces and what each one promises are in
[docs/release-checklist.md](release-checklist.md#tag-namespaces).

## Inputs

| Input | Required | Default | Meaning |
|-------|----------|---------|---------|
| `feed-url` | yes | | Direct link to a GTFS Schedule zip. |
| `min-grade` | no | _(skip)_ | Fail if the overall grade is below this letter: A, B, C, D, or F. |
| `min-days-to-expiry` | no | _(skip)_ | Fail if the feed expires within this many days. A feed with no expiry date fails this check. |
| `name` | no | feed host | Agency name shown in the printed report. |
| `country` | no | `US` | Assigned ISO 3166-1 alpha-2 feed country passed to the validator. |
| `html` | no | _(skip)_ | Path to also write a standalone HTML scorecard, relative to the workspace. |
| `json` | no | runner temporary file | Path for the complete machine-readable scorecard artifact. |
| `summary` | no | `true` | Write a plain-language scorecard to the GitHub job summary. |
| `ref` | no | _(ignored)_ | Deprecated compatibility input. The scorer is bundled with the Action release and always matches the selected Action ref. |

Leave a threshold blank to skip it. With neither `min-grade` nor
`min-days-to-expiry` set, the action prints the scorecard and always passes,
which is useful as an informational step.

One input fails with no threshold set, because it produces no scorecard to
gate: an archive the scorer could read no schedule data out of — no stops and
no trips — is refused rather than graded, exactly as a response body that is not
a zip is. The step fails with `could not score <url>: ...` and `passed` is
`false`. Before that change such a feed was graded and the default
configuration reported `passed=true` for it.

**This behaviour is on `main` only.** It is in no published release, so it is
not what `@v1.4.0` or `@v1` do today. See [Which ref to pin](#which-ref-to-pin).

## Outputs and job summary

The action exposes `grade`, `score`, `days-to-expiry`, `passed`, and
`result-json`. The complete JSON is written before thresholds are applied, so
later steps can upload or inspect it even when the gate fails.

```yaml
      - id: gtfs
        uses: ChelseaKR/gtfs-scorecard@v1.4.0
        with:
          feed-url: https://example.org/gtfs/feed.zip
          min-grade: B
          json: artifacts/gtfs-scorecard.json

      - if: always()
        run: |
          echo "grade=${{ steps.gtfs.outputs.grade }}"
          echo "passed=${{ steps.gtfs.outputs.passed }}"
          echo "result=${{ steps.gtfs.outputs.result-json }}"
```

By default the job summary includes the grade, service days remaining, and the
top three fixes. Set `summary: "false"` to suppress it. A failed gate also emits
a concise workflow annotation while preserving the full result file.

## Saving the HTML report

Set `html` to keep the rendered scorecard as a build artifact:

```yaml
      - uses: ChelseaKR/gtfs-scorecard@v1.4.0
        with:
          feed-url: https://example.org/gtfs/feed.zip
          min-grade: C
          html: scorecard.html
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: gtfs-scorecard
          path: scorecard.html
```

The `if: always()` keeps the report even when the gate fails, which is when you
most want to read it.

## How it runs

The action is a composite that sets up Java 17 (the validator is a Java tool)
and `uv`, then runs the bundled `scorecard` CLI from the same immutable Action
release. It does not clone the service repository a second time. Release tags
carry a bounded Action distribution tree rather than the scored artifact corpus.
The first run downloads the validator jar, so expect a slower cold start.

## Notes

- This gates GTFS Schedule feeds. Realtime scoring needs sampling over a window
  and is not part of the build gate.
- Grades follow `docs/rubric.md`. If a grade looks off, read the printed
  findings: the gate reports the same categories the dashboard does.
