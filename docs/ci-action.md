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
      - uses: ChelseaKR/gtfs-scorecard@v1
        with:
          feed-url: https://example.org/gtfs/feed.zip
          name: Example Transit
          country: CA
          min-grade: B
          min-days-to-expiry: 14
```

`@v1` follows the latest compatible v1 release. Pin the current full version
tag (`@v1.5.0`) or a commit SHA when you want an exact, unchanging contract.

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
| `baseline` | no | _(skip)_ | A prior scorecard artifact to compare this run against: a file path, an `https` URL, or `agency@YYYY-MM-DD` / `agency@latest`. |
| `fail-on-regression` | no | `false` | Fail the build when the comparison shows a regression, or cannot be made because the two runs are different measurements. |
| `ref` | no | _(ignored)_ | Deprecated compatibility input. The scorer is bundled with the Action release and always matches the selected Action ref. |

Leave a threshold blank to skip it. With neither `min-grade` nor
`min-days-to-expiry` set, the action prints the scorecard and always passes,
which is useful as an informational step.

One input fails with no threshold set, because it produces no scorecard to
gate: an archive the scorer could read no schedule data out of — no stops and
no trips — is refused rather than graded, exactly as a response body that is not
a zip is. The step fails with `could not score <url>: ...` and `passed` is
`false`. Until 2026-09, such a feed was graded and the default configuration
reported `passed=true` for it.

## Outputs and job summary

The action exposes `grade`, `score`, `days-to-expiry`, `passed`,
`result-json`, `comparable`, and `regressed`. The complete JSON is written
before thresholds are applied, so later steps can upload or inspect it even
when the gate fails. `comparable` and `regressed` are blank unless you set
`baseline`.

```yaml
      - id: gtfs
        uses: ChelseaKR/gtfs-scorecard@v1
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

## Comparing against a baseline

Set `baseline` to compare this run with a previous scorecard, so a pull request
cannot quietly regress a published feed:

```yaml
      - uses: ChelseaKR/gtfs-scorecard@v1
        with:
          feed-url: https://example.org/gtfs/feed.zip
          baseline: example-transit@latest
          fail-on-regression: true
```

The comparison runs `scorecard diff`, which decides whether the two runs are the
same measurement **before** it reports anything. Two artifacts scored under
different rubric versions, scoring profiles, validator versions, reader archive
profiles, or measured categories are different measurements, and the difference
between them is not a statement about the feed. The job summary names which of
those differs.

What each result does to the build:

| Result | `comparable` | `regressed` | Build |
|---|---|---|---|
| No regression | `true` | `false` | Passes. |
| Regressed: grade dropped, or a finding appeared or grew | `true` | `true` | Fails when `fail-on-regression` is `true`. |
| Not comparable: the two runs are different measurements | `false` | _(blank)_ | Fails when `fail-on-regression` is `true`. |
| The baseline could not be read at all | _(blank)_ | _(blank)_ | **Always fails.** |

The last two rows are the point. "I cannot tell you whether this regressed" is
not a pass, so a regression gate fails closed on it. And a `baseline` the action
could not read is a broken input rather than a fact about the feed, so it fails
whatever `fail-on-regression` is set to: a gate that shrugs at its own missing
baseline is a gate that cannot fail.

When a run stops measuring a category — realtime, say, because the endpoint
stopped answering — the findings in that category disappear from the artifact.
They are listed as **not measured in the newer artifact**, never as cleared.
Nobody looked at them, which is not the same as their being fixed.

## Saving the HTML report

Set `html` to keep the rendered scorecard as a build artifact:

```yaml
      - uses: ChelseaKR/gtfs-scorecard@v1
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
