# Buy by invoice or purchase order

The program report bundle can be bought without a card link. This is for a public
agency, a state program, or a technical-assistance center whose rules call for a
quote, a purchase order, and an invoice. The page for buyers is
[gtfsscorecard.org/invoice/](https://gtfsscorecard.org/invoice/).

The product is the one described in [program-plan.md](../program-plan.md): one
archive of board reports, one per agency id the buyer names, with the buyer's
program name, logo, and accent on each cover and a manifest that accounts for
every id. A purchase buys no influence over grades, methodology, or which
agencies are listed. An agency's own board report stays free.

## What you can ask for

- One bundle, up to 25 agencies.
- One bundle, up to 100 agencies.
- The monthly refresh, billed once a year.
- Something else for a program. Describe it in the request and the quote says what
  is and is not included.

Every price is read from `web/bundle/plan.json`, the same file the bundle page
uses, so a price here cannot disagree with the one there.

## Steps

1. Fill in the form on the invoice page. It writes an email in your own mail
   program. Nothing is sent until you press send there. The page stores nothing
   and makes no request that carries what you typed.
2. The reply is a quote. [`quote-template.md`](quote-template.md) shows its
   fields, and [`quote-template.html`](quote-template.html) is the same blank quote
   laid out for printing.
3. Accept the quote the way your office requires, for example with a purchase
   order that cites the quote number.
4. You receive an invoice that cites your purchase order number.
5. The archive is built and sent to the address you named.

Do not put card numbers, bank details, or tax identifiers in the request. A quote
does not need them. If your office needs supplier forms, a registration, or a
particular purchase order format, say so in the request.

## The blank quote

The quote template is generated from the plan so its line items and prices match
the bundle page. After a price changes in `web/bundle/plan.json`, run:

```sh
make sync-invoice-docs
```

`pipeline/tests/test_invoice_path.py` fails the build when the committed files and
the plan disagree. Seller identity, payment, terms, and buyer fields are visible
`[OWNER FILL: ...]` and `[BUYER FILL: ...]` markers. A quote that still contains
one is not ready to send.
