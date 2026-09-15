# Ads import-ready: Google Search campaign for the program report bundle

Companion to [`docs/paid-search-readiness.md`](paid-search-readiness.md) (PR #442,
merged 2026-09-14). That document did all the keyword research, ad copy
drafting, and budget math; this file only repackages it into a form you can
import mechanically. **No new keywords, ad copy, or budget numbers were
invented here** — everything below traces back to a specific section of the
readiness doc, cited inline.

## Start here: the one number to enter

**Daily budget: $10.00.**

That is the readiness doc's own recommended starting point (§4: "$10/day
($70/week)... cheap enough that even zero sales for several weeks is a
bounded, known cost"). Enter it as-is in Campaign settings — it is not a
range you need to interpret.

Max CPC bid: the doc gives a range, "a cap around $8-10" (§4). The CSV below
uses **$9.00** (the midpoint) on every keyword row as a single number to
start from. Raise it to $10 or drop it to $8 in Google Ads Editor before
posting if you'd rather use either end of that range — both are within what
the readiness doc already reviewed.

## What's in `ads-import-ready-google-ads.csv`

One CSV, one campaign, ready for **Google Ads Editor → Account → Import →
From File**. Row-by-row:

- **1 campaign row**: "GTFS Scorecard - Program Report Bundle", Search
  network only (Display and Search Partners excluded, per §7 owner step 2),
  $10.00/day, Manual CPC.
- **4 ad group rows**, one per §2 ad copy variant: Compliance and audit
  (variant A), Program and TA-center (variant B), Validator and report
  (variant C), Vendor and consultancy (variant D).
- **20 keyword rows** — every Tier 1 and Tier 2 keyword from §1, in Phrase
  match, sorted into the ad group whose theme it names in §7 owner step 3/4.
  Three of the most literal Tier 1 terms are additionally entered a second
  time in Exact match (the doc's own instruction, §7 step 4: "the tightest
  few Tier 1 terms additionally in Exact match" — it doesn't name which
  ones, so this pass picked the three that most literally name the product
  category or deliverable: "gtfs compliance audit tool," "gtfs quality
  scorecard for transit agencies," and "gtfs data quality board report").
  Tier 3 terms are **not** in this list — the readiness doc explicitly
  keeps them out of the bid list (§1: "source for negatives" only).
- **4 ad rows** (Responsive Search Ads) — the exact headlines and
  descriptions from §2, verbatim, one ad per ad group, all pointed at
  `https://gtfsscorecard.org/bundle/` per §2's landing-page recommendation.
- **28 negative-keyword rows** at the campaign level: all 8 Tier 3 terms
  (§1) plus all 20 terms from the explicit negative list (§1). Encoded as
  `Match Type = Campaign Negative` (see confidence note below).

### Keyword → ad group mapping (not explicit in the source doc — made here)

The readiness doc names four ad-copy themes (§2: Compliance/audit,
Program/TA-center, Validator/report, Vendor/consultancy) and instructs
"Tier 1 in Phrase match per its themed ad group... Tier 2... split across
the closest-matching ad group" (§7 step 4) without spelling out which
keyword goes in which group. This pass assigned each keyword to the group
whose theme it most literally matches (e.g. "gtfs validator report" →
Validator and report; "state dot gtfs oversight tool" → Program and
TA-center). This is an organizing decision, not new content — every keyword
text and every ad group name is already in the source doc. Re-sort rows in
Editor before posting if a different grouping reads better to you.

## Google Ads Editor CSV format: what I verified, and my confidence level

I fetched Google's current support pages rather than assuming a remembered
format (support.google.com/google-ads/editor/answer/57747 "CSV file
columns" and answer/56368 "Prepare a CSV file"), plus cross-checked with a
couple of independent Editor-focused tools/guides.

**High confidence** (directly confirmed by Google's own current docs):
- Google Ads Editor CSV is a **one-row-per-entity** format — a campaign, an
  ad group, a keyword, and an ad are each their own row, distinguished by
  which columns are populated (not a flattened wide table). That's the
  structure used above.
- The header names used (`Campaign`, `Ad Group`, `Keyword`, `Match Type`,
  `Final URL`, `Headline 1`–`15`, `Description 1`–`4`, `Status`, etc.) are
  confirmed current column names, several with documented aliases (e.g.
  `Match Type` is interchangeable with `Type` / `Criterion Type` /
  `Keyword Type`).
- `Status` takes `Enabled` / `Paused` / `Removed`.

**Moderate confidence** (documented but with less verbatim detail than I'd
like):
- Positive keyword match type as a column value (`Broad` / `Phrase` /
  `Exact`) rather than bracket/quote syntax in the keyword text itself —
  Google's doc example used this pattern, so that's what the CSV does.
- Negative keyword encoding. Google's own help text (as fetched) says to
  enter `Negative` for an ad-group-level negative and `Campaign negative`
  for a campaign-level one, in the same Type/Match Type column — that's
  what this CSV uses (`Campaign Negative`, since every negative here is
  campaign-level). A couple of third-party Editor guides instead show
  `Negative Exact` / `Negative Phrase` as literal values. I went with the
  wording that came from Google's own page rather than the secondary
  sources, but **this is the single row-type in this file most likely to
  need a tweak** — Editor's import screen shows a full preview/diff before
  anything is posted, so if the 28 negative rows don't map the way you
  expect, that will be visible there before you confirm.
- Exact bid-strategy-type string values (`Manual CPC` here) and network
  values (`Google search` here) are written in the plain, human-readable
  form Google's docs use in examples; Editor is generally tolerant of
  capitalization/spacing per its own docs, but I did not find an
  exhaustive enum list to check these two specific strings against.

**Net: import via File → Import → From File, and read the preview screen
before posting** — that's true for any Editor CSV regardless of format
confidence, and it's the actual safety net here, not just a suggestion.

## Not in the CSV (still worth doing, per the readiness doc)

Ad extensions (§7 owner step 7: sitelinks to `/bundle/#plans-h`, a price
extension, callout extensions, a structured snippet) aren't part of the
task this file covers and have a less certain CSV shape than campaigns/ad
groups/keywords/ads. Add them directly in the Google Ads UI or Editor's
extension tabs after the campaign above is live — §7 step 7 of the
readiness doc already has the exact copy for each.

The conversion-tracking action (§7 owner step 8) is a separate, code-linked
step (setting `google_ads_conversion_action` in Terraform) — not something
a CSV import touches.
