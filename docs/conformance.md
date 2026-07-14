# Conformance mark

The grade is a gradient from A to F. The conformance mark is a bright line: a
feed either earns it or it does not. An agency can put the mark on its developer
page as a credential, and a state program can point to it as a clear bar.

The mark does not change any category score. It reads the scores the pipeline
already computes and applies three pass/fail checks.

## What a feed must clear

All three must hold at once:

1. **Valid** — the GTFS validator finds no errors. Warnings and info notices do
   not block the mark; errors are the ones that break a rider's trip.
2. **Current** — the service calendar has not lapsed and is not inside the
   expiry window. A feed about to run out does not qualify until it is renewed.
3. **Accessible** — the feed states wheelchair access on at least 90% of stops
   and 90% of trips. This measures what the feed publishes, not whether a stop
   is physically usable.

A feed that misses is shown as "not yet", with the specific gap named, never as
a failure.

## What gets published

When a feed earns the mark, the pipeline writes two files next to its artifacts:

- `mark.svg` — an embeddable seal, written only when the mark is earned, so the
  file's presence is the credential. A feed that later loses the mark has the
  seal removed.
- `conformance.json` — the machine-readable result (`awarded`, `status`, the
  three criteria with `met` and a plain-language detail). Always written.

The agency page shows the mark, its three checks, and a copy-paste embed when
the mark is earned.

## Embedding

When earned, copy the snippet from the agency page, or build it directly:

```markdown
[![GTFS conformance mark](https://<site>/data/artifacts/<agency-id>/mark.svg)](https://<site>/agency/<agency-id>/)
```

## Why these three

The mark combines published validity, currency, and the accessibility floor that
the rubric treats as a values statement. It does not cover the separate RY2026
agency_id/P-50 identity requirement or certify NTD compliance. The official
check remains the agency's own D-10 and P-50 filing.
