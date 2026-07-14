# Finding-clearance measurement

The scorecard measures whether findings later disappear from compatible feed
checks. This is more useful than treating visits, clicks, or grade changes
alone as success, but it is not evidence that a particular intervention caused
the change.

```sh
cd pipeline
uv run scorecard fix-outcomes --format markdown --out outcomes.md
```

The report walks each agency's dated artifacts and treats one continuous
appearance of a finding code as an episode. An episode clears only when a later
run uses the same complete producer contract, does not contain the code, and
measures the same category. If a feed was unreachable, a category was skipped,
or the methodology changed, the finding does not produce a clearance claim.

For each notice code the report provides:

- agencies and episodes observed;
- resolved and still-open episodes;
- median, fastest, and slowest observed days to resolution; and
- agencies where the same code recurred after clearing.

Open episodes are right-censored. A low observed clearance rate can mean the
finding is difficult, but it can also mean the finding is recent. The report
therefore keeps open counts visible and labels the rates as descriptive, not
causal. A disappearance does not show who changed the feed, why it changed, or
how much staff effort it took. The report does not collect user identities,
page histories, or agency contact data.

Use the data to decide which fix guides need better instructions, which effort
hints need recalibration, and where a vendor export default may be causing
repeat work. Do not use it as a public agency ranking.
