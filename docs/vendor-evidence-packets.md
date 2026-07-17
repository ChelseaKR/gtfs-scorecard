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
- a retest contract that expects the same notice code to have zero instances.

The packet ID is derived from the agency, snapshot, feed hash, and complete
producer and measured-category contract. The retest must keep the rubric,
scoring profile, validator, reader archive profile, and measured category set.
Running the command twice on the same artifact produces the same packet. The
original artifact remains the source of truth.

The wording is intentionally narrow. A packet describes the feed as published;
it does not infer who caused a problem, rank a vendor, or make a contract or
compliance determination. An agency and vendor can document an agreed exception
when zero instances is not the right acceptance condition.
