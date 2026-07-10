# Program support campaigns

A state, district, or regional support team can turn an existing rollup into a
bounded improvement campaign. Each campaign covers one fix theme, produces an
alphabetical agency worklist, and states how the campaign closes.

```sh
cd pipeline
uv run scorecard campaign \
  --rollup california \
  --kind calendar-renewal \
  --format markdown \
  --out california-calendar-renewal.md
```

Available campaign kinds are:

- `calendar-renewal`: reach at least 30 days of published service;
- `accessibility-fields`: publish known wheelchair values for stops and trips;
  and
- `rider-information`: publish rider-facing route names and trip destinations.

The baseline records agencies checked, agencies targeted, and agencies already
clear. A target leaves the worklist only after a later measured scorecard run
clears every finding in the campaign theme. This avoids counting a failed fetch
or skipped category as progress.

Campaign output intentionally omits grades and scores. It is a support worklist,
not a leaderboard. Run one theme at a time, send the relevant fix guidance, and
rebuild the same campaign after agencies republish to measure closeout.
