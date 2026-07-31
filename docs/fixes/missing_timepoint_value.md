---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: stop times without a timepoint value

Code: `missing_timepoint_value` (MobilityData validator)

## What this means

`stop_times.txt` has a `timepoint` column, but some rows leave it blank. The
column says whether each arrival time is a real, scheduled checkpoint
(`timepoint=1`) or an interpolated estimate (`timepoint=0`). Blank rows leave
consumers guessing which kind each time is.

## Why it matters

Trip planners and realtime systems treat checkpoint times differently from
estimates: a checkpoint anchors predictions, an estimate can flex. When the
field is blank, an app has to assume, and its assumption may present your
estimated times as promises. Riders then hold the schedule to a precision it
never claimed.

## How to fix it

- **In your export settings**, look for an option that writes timepoint flags,
  often tied to which stops your schedulers mark as time checks. If your tool
  wrote the column at all, it usually can fill it.
- **If every published time is a real scheduled time**, setting `timepoint=1`
  on all rows is honest and clears the warning.
- **If only some stops are time checks**, mark those `1` and the rest `0`; the
  scheduling data usually already knows which is which.

## How long it usually takes

Usually one export setting. If the column has to be filled from scratch, a
bulk edit keyed on your time-check stops does it in an afternoon.
