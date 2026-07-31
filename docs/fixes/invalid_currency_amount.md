---
date_published: "2026-07-03"
date_modified: "2026-07-03"
---

# Fix: a fare amount has the wrong number of decimals

Code: `invalid_currency_amount` (MobilityData validator)

## What this means

A fare price in `fare_attributes.txt` (or a Fares v2 amount) has more or fewer
decimal places than its currency allows. US dollars take two decimals, so `2`
or `2.5` is wrong where `2.00` or `2.50` is meant; a zero-decimal currency takes
none.

## Why it matters

This is an error. Apps that read fares may reject the amount or show the wrong
price, so a rider sees a fare that is off by a factor of ten or no fare at all.
It usually comes from a fare typed without the cents, or a currency code that
does not match how the amount was written.

## How to fix it

- **Match the decimals to the currency.** For `USD`, write every amount with two
  decimals (`1.75`, `2.00`). Check that `currency_type` is the right ISO code.
- **Fix the flagged rows** the validator names; the others in the same file
  usually have the same pattern, so correct them together.

## How long it usually takes

A quick edit of the fare file. The hardest part is noticing the missing cents.
