# Vendor remediation evidence packets

An evidence packet gives an agency a concrete, reproducible work order to send
to the person or vendor that produces its GTFS feed. It is generated from one
published scorecard artifact and does not compare vendors or agencies.

```sh
cd pipeline
uv run scorecard evidence-packet \
  ../data/artifacts/example/latest.json \
  --format markdown \
  --out example-remediation.md
```

Use `--format json` for procurement records or automation. The packet records:

- the agency, scorecard URL, snapshot date, grade, and score;
- the exact feed URL and SHA-256 checked;
- validator, rubric, scoring profile, reader archive profile, measured category
  set, and artifact schema versions;
- each prioritized finding, current instance count, requested change, and
  effort hint; and
- a retest contract that expects the same notice code to be absent.

The packet ID is derived from the agency, snapshot, feed hash, and complete
producer and measured-category contract. The retest must keep the rubric,
scoring profile, validator, reader archive profile, and measured category set.
Running the command twice on the same artifact produces the same packet. The
original artifact remains the source of truth.

The wording is intentionally narrow. A packet describes the feed as published;
it does not infer who caused a problem, rank a vendor, or make a contract or
compliance determination. An agency and vendor can document an agreed exception
when zero instances is not the right acceptance condition.

## Retest a new export against the packet

`scorecard retest` runs a packet's acceptance tests against a new export. It
scores the feed the way `scorecard try` does, then reports each finding in the
packet as cleared, still present, or not comparable.

```sh
cd pipeline
uv run scorecard retest example-packet.json ./corrected-gtfs.zip \
  --country US \
  --json-out example-retest.json \
  --markdown-out example-retest.md
```

The feed can be a local zip or a direct link. The record carries both feed
hashes, both producer contracts, and a verdict for every finding. The
Markdown version is written to be pasted into a ticket.

The exit code is 0 when every finding is cleared and 1 when any finding is
still present. It is 2 when the command could not judge: the packet was
refused, the feed could not be read, or a finding could not be compared.

- **Cleared** means the notice is absent from the retest. A notice raised with
  a count of zero, such as "0 of 0 stops don't say whether a wheelchair user
  can board there", is still present.
- **Not comparable** has two causes. If the retest ran under a different
  rubric, scoring profile, validator, or reader archive profile, every finding
  is not comparable and none is reported cleared. If one finding's category
  was not measured in the retest, that finding alone is not comparable. A
  retest never samples realtime, so a realtime finding is never cleared by one.
- The packet is checked before any download. It is refused when it is
  malformed, requests no work, has an incomplete producer contract, or expects
  a nonzero number of instances for a finding.

Pass the `--country` the packet's scorecard used. The packet does not record
it, and the validator's country setting changes some checks, such as phone
number formats.

### What a retest record is not

A retest record is not a closure receipt. It does not confirm who published the
feed or that it is the agency's canonical export. It does not say who caused or
fixed a finding, and nothing in it is published.
