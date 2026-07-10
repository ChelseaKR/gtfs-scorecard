# Outcome measurement

The scorecard measures whether its recommended fixes later clear. This is more
useful than treating visits, clicks, or grade changes alone as success.

```sh
cd pipeline
uv run scorecard fix-outcomes --format markdown --out outcomes.md
```

The report walks each agency's dated artifacts and treats one continuous
appearance of a finding code as an episode. An episode resolves only when a
later run does not contain the code **and the same category was measured**. If
a feed was unreachable or a category was skipped, the finding stays open.

For each notice code the report provides:

- agencies and episodes observed;
- resolved and still-open episodes;
- median, fastest, and slowest observed days to resolution; and
- agencies where the same code recurred after clearing.

Open episodes are right-censored. A low observed resolution rate can mean a fix
is difficult, but it can also mean the finding is recent. The report therefore
keeps open counts visible and labels the rates as descriptive, not causal. It
does not collect user identities, page histories, or agency contact data.

Use the data to decide which fix guides need better instructions, which effort
hints need recalibration, and where a vendor export default may be causing
repeat work. Do not use it as a public agency ranking.
