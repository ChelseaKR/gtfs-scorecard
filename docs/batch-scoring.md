# Score a list of feeds you hold

`scorecard try --batch` scores every feed in a CSV the same way `scorecard try`
scores one, then writes a private rollup across them. It is for a state program
liaison whose agencies the public registry does not list, a consultancy with a
client portfolio, or a workshop that pre-scores the feeds its attendees bring.

Nothing is published. Nothing is added to the registry. Every file lands in the
folder you name.

## The CSV

| Column | Required | What it holds |
| --- | --- | --- |
| `name` | yes | The name to show for the feed. |
| `url` | yes | A direct `http` or `https` link to the GTFS zip, or a path to a local zip. A relative path is read from the CSV's own folder. |
| `country` | yes | The two-letter ISO country code the feed is validated under, such as `US` or `CA`. |
| `ntd_id` | no | The feed's NTD reporter id, carried into the rollup as a label. |
| `large_feed` | no | `true` applies the large-feed limits, as `scorecard try --large-feed` does. Blank means false. |

```csv
name,url,country
Sampletown Transit,https://example.org/gtfs.zip,US
Riverbend Shuttle,exports/riverbend.zip,US
```

The contract for one row is published at `/schemas/batch-feeds.schema.json`.

## Run it

```sh
cd pipeline
uv run scorecard try --batch ../feeds.csv --out ../batch-2026-09 --date 2026-09-11
```

`--out` must be a new or empty folder. `--batch-workers` sets how many feeds are
scored at once, from 1 to 4 (default 2). Each one runs the Java validator, so
more workers need more memory.

The whole CSV is checked before anything is downloaded. A missing or unknown
column, a bad country code, a malformed row, or the same feed listed twice stops
the run with the row number, and nothing is fetched.

## What it writes

- `feeds/<name>.json` and `feeds/<name>.html`: one scorecard for each feed that
  could be scored, the same files `scorecard try --json-out` and `--html`
  write.
- `rollup.md`, `rollup.html`, and `rollup.csv`: the cohort rollup.
  `rollup.json` holds the same content for scripts.

The rollup lists every feed in CSV order. It names the feeds whose service ends
within 30 days or has already ended. It counts the fixes that appear in more
than one feed's top fixes, the same way a published program rollup does. It
ends with one worklist for each theme in [program campaigns](program-campaigns.md).

## A feed that could not be scored

A dead link, an unreadable archive, or a missing local file appears as a row
marked "not scored", with the reason. It never gets a grade, it is never counted
as a zero, and a worklist never counts it as already clear. The run still exits
0 so the rest of the rollup is usable. Add `--strict` to exit 1 when any feed
could not be scored.

## What the rollup is not

It is not a ranking. Feeds stay in the order of your CSV, and the worklists
leave out grades and scores. It is not published or shared: the files exist
only where you wrote them.

A local feed is named by its file name, never its full path, so a rollup can be
forwarded without showing your folder layout. Running the same CSV with the
same `--date` gives byte-identical files.

The `gtfs-quality-workshop` pre-score runbook can point here for feeds the
registry does not list.
