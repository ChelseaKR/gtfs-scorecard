# Public comparison policy

The open dataset and directory include every published scorecard. The public
site does not publish absolute highest- or lowest-scoring lists, individual
national percentiles, or size-peer percentiles. A score is evidence about one
published feed, not a judgment of service quality, staff performance, or
compliance.

Aggregate score summaries and named change views use a narrower comparison
cohort. A feed record is included only when:

- it has a dated snapshot and numeric overall score;
- correctness, freshness, and rider-experience completeness were measured;
- it uses the current rubric version;
- it uses the current scoring profile and canonical validator version;
- it belongs to the selected homogeneous measured-category set, so a
  three-category overall score is never mixed with a four-category score;
- its published service data is not more than one year expired;
- it is an active canonical registry record, not an alias; and
- its feed identity is unambiguous. Repeated Mobility Database IDs, normalized
  feed URLs, or exact current feed hashes are excluded until reconciled.

Realtime remains optional and is not an eligibility condition. A small agency
without realtime is never excluded for that reason.

Named changes compare a feed only with its own prior check, and only when both
checks use the same current rubric, scoring profile, validator, and measured
category set. The historical `api/v1/leaderboard.json` path is retained for v1
consumers, but its `top` and `bottom` arrays are always empty. It carries guarded
`most_improved` and `most_declined` change rows plus a `comparison` object
explaining exclusions.

Every excluded record remains available in the scorecard directory and open
dataset. Vendor-host comparisons remain internal and must not be republished as
a blame board.
