# Public comparison policy

The open dataset includes every scored feed. Ranked lists and percentiles are a
narrower presentation and use additional guardrails so unlike records are not
made to look directly comparable.

A feed is eligible for a public ranked comparison only when:

- it has a dated snapshot and numeric overall score;
- correctness, freshness, and rider-experience completeness were measured; and
- its published service data is not more than one year expired.

Realtime remains optional and is not an eligibility condition. A small agency
without realtime is never excluded for that reason.

Ranked output is withheld until at least 20 feeds meet the rules. The API then
returns empty ranked lists plus a `comparison` object with eligible and excluded
counts, the minimum cohort, and exclusion counts by reason. The records remain
available in the agency list and open dataset.

These rules reduce false precision; they do not turn a score into a judgment of
service quality, staff performance, or compliance. Public wording should treat
low scores as support signals and link to the concrete fixes. Vendor host
comparisons remain internal and must not be republished as a blame board.
