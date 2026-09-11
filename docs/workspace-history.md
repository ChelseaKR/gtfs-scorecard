# Keeping a private history of a feed

`scorecard try --history DIR` keeps a record of every run for a feed that is
not in the public registry. `scorecard trend --history DIR` reads it back as a
trend, with the same expiry, regression, lapse-risk and anomaly alerts that
`scorecard alerts` sends for registered feeds. Nothing is published, and
nothing reaches the registry.

It is meant for a vendor watching many customer exports, a state program with
feeds that are not listed, or an agency that wants a history without being
listed.

## Record a run

```sh
cd pipeline
uv run scorecard try https://example.org/gtfs.zip \
  --name "Example Transit" \
  --history ../.scorecard-history
```

Each run appends one line to `.scorecard-history/example-transit/history.jsonl`.
The folder name comes from `--name`, or from the feed's host or file name when
there is none. Give each feed its own `--name`. A run is refused when the
folder already holds a different feed's history, so two feeds are never
compared with each other.

A run that could not score the feed writes nothing. A missed run is a gap in
the history, not a zero.

## What a record holds

Counts and codes only. A record holds the date, grade and score, each measured
category's score, each finding code with its count, the feed's SHA-256, the
days until the feed expires, and how the run was measured: rubric, scoring
profile, validator, reader archive profile and measured categories. It never
holds finding text or contact details, and a local zip is recorded by its file
name only.

The record format is published as
[`workspace-history.schema.json`](../web/schemas/workspace-history.schema.json).

## Read the trend

```sh
uv run scorecard trend --history ../.scorecard-history
uv run scorecard trend --history ../.scorecard-history --format html --out trend.html
```

`--format` takes `text`, `markdown` or `html`. The HTML file is self-contained
and loads nothing from the network. `--feed example-transit` limits the trend
to one feed.

Each row says how the run compares with the one before it.

- **Unchanged** means the same feed bytes, scored the same.
- **Same feed bytes** with a different score means the export did not change
  and the score did. The date column shows when.
- **New export** means different bytes, with the score change and any grade
  change.
- **Measured differently** means the rubric, scoring profile, validator,
  reader archive profile or measured categories changed. The row is shown and
  not compared, and the alerts read only the runs measured the same way as the
  newest one.

A line the history cannot read is skipped and named, with its file and line
number, in every format and in the log.

## Alerts

The alerts come from the same code as `scorecard alerts`, so the same history
raises the same items. Two things differ because the feed is private. A
structural export change is never raised, because `scorecard try` does not
compare an export's structure with the last one. And no alert links to a
scorecard page, because there is none.

The expiry countdown is the one the newest run recorded. Run `try --history`
again to refresh it.

## In GitHub Actions

The Action's `history-path` input does the same from a workflow, but it is on
`main` only and is not in the `v1.4.0` release (see
[CI Action](ci-action.md#which-ref-to-pin)). Until a release includes it, run
the command-line tool and keep the history between runs with the cache:

```yaml
      - uses: actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0
        with:
          path: .scorecard-history
          key: scorecard-history-${{ github.run_id }}
          restore-keys: scorecard-history-
      # Run `scorecard try ... --history .scorecard-history` here.
      - uses: actions/cache/save@55cc8345863c7cc4c66a329aec7e433d2d1c52a9 # v6.1.0
        if: always()
        with:
          path: .scorecard-history
          key: scorecard-history-${{ github.run_id }}
```

A cache can be evicted, and the history goes with it. To keep it for good,
commit the directory to a branch instead.
