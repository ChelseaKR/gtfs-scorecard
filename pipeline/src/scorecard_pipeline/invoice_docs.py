"""The blank quote a buyer can read before asking for one (docs/invoice/).

A public agency or program that cannot pay through a card link buys the program
report bundle by quote, purchase order, and invoice (``/invoice/``). The quote
is a document the seller fills in and sends. This module writes the blank one:
Markdown to read on GitHub and a printable HTML copy, both from one function,
with every line item and price read from ``web/bundle/plan.json``.

Why generated rather than typed. A price copied into a document keeps quoting
after the plan changes, which is the rule ``web/bundle/plan.json`` already holds
for every page (docs/decisions/0049). ``make sync-invoice-docs`` rewrites the
files, and ``tests/test_invoice_docs.py`` fails CI when they drift from the plan.

Nothing here invents a fact about the seller. Every identity, tax, payment, and
terms field is a visible ``[OWNER FILL: ...]`` marker, and every field the buyer
supplies is a ``[BUYER FILL: ...]`` marker. A quote with a marker left in it is
not ready to send, and ``unfilled_markers`` finds them.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

from .site_shell import _repo_root

# The plan entries a quote can carry, in the order the page lists them. The
# monthly card subscription is not one of them: by invoice the refresh is billed
# once a year.
QUOTE_PRODUCTS: tuple[str, ...] = ("bundle_25", "bundle_100", "refresh_yr")

_MARKER_RE = re.compile(r"\[(?:OWNER|BUYER) FILL: [^\]]+\]")

_MD = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable("table")

_CSS = """
body { font: 16px/1.5 Georgia, "Times New Roman", serif; color: #111; background: #fff;
  max-width: 46rem; margin: 2rem auto; padding: 0 1rem; }
h1 { font-size: 1.6rem; margin: 0 0 1rem; }
h2 { font-size: 1.15rem; margin: 1.6rem 0 0.4rem; }
table { border-collapse: collapse; width: 100%; margin: 0.6rem 0; }
th, td { border: 1px solid #555; padding: 0.4rem 0.5rem; text-align: left; vertical-align: top; }
th { background: #eee; }
@media print { body { margin: 0; max-width: none; font-size: 11pt; }
  h2 { break-after: avoid; } table, tr { break-inside: avoid; } }
"""


def load_bundle_plan(root: Path | None = None) -> dict[str, Any]:
    """The bundle plan the quote reads, from ``web/bundle/plan.json``."""
    path = (root or _repo_root()) / "web" / "bundle" / "plan.json"
    plan = json.loads(path.read_text())
    if not isinstance(plan, dict):
        raise ValueError(f"{path}: expected a JSON object")
    return plan


def _money(amount: int | float, currency: str) -> str:
    text = f"{amount:,.0f}" if float(amount).is_integer() else f"{amount:,.2f}"
    return f"${text}" if currency == "USD" else f"{text} {currency}"


def quote_line_items(plan: dict[str, Any]) -> list[dict[str, str]]:
    """One row per quotable product, read from the plan. A product the plan does
    not carry, or carries without a numeric price, is an error rather than a
    blank row: a quote must never show a price the plan does not state."""
    products = plan.get("products")
    if not isinstance(products, dict):
        raise ValueError("plan.json has no products object")
    currency = str(plan.get("currency") or "USD")
    rows: list[dict[str, str]] = []
    for key in QUOTE_PRODUCTS:
        product = products.get(key)
        if not isinstance(product, dict) or not isinstance(product.get("price"), (int, float)):
            raise ValueError(f"plan.json: product {key!r} has no numeric price")
        interval = product.get("interval")
        rows.append(
            {
                "key": key,
                "label": str(product.get("label") or key),
                "unit_price": _money(product["price"], currency),
                "billing": f"per {interval}" if interval else "once",
            }
        )
    return rows


def render_quote_markdown(plan: dict[str, Any]) -> str:
    """The blank quote as Markdown."""
    lines: list[str] = [
        "# Quote: GTFS Scorecard program report bundle",
        "",
        "This is a blank quote. The seller fills every `[OWNER FILL: ...]` field before",
        "sending it, and the buyer fills every `[BUYER FILL: ...]` field. Prices in the table",
        "are read from `web/bundle/plan.json`. See",
        "[Buy by invoice or purchase order](https://gtfsscorecard.org/invoice/).",
        "",
        "## Parties",
        "",
        "| | |",
        "| --- | --- |",
        "| Quote number | [OWNER FILL: quote number] |",
        "| Date issued | [OWNER FILL: date] |",
        "| Valid until | [OWNER FILL: date] |",
        "| Seller | [OWNER FILL: seller legal name] |",
        "| Seller address | [OWNER FILL: seller mailing address] |",
        "| Seller contact | [OWNER FILL: contact name and email] |",
        "| Buyer | [BUYER FILL: organization legal name] |",
        "| Buyer address | [BUYER FILL: billing address] |",
        "| Buyer contact | [BUYER FILL: contact name and email] |",
        "| Where the archive is sent | [BUYER FILL: delivery email] |",
        "",
        "## Line items",
        "",
        "| Item | Billing | Unit price (USD) | Quantity | Amount (USD) |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in quote_line_items(plan):
        lines.append(
            f"| {row['label']} | {row['billing']} | {row['unit_price']} "
            "| [BUYER FILL: quantity] | [OWNER FILL: quantity times unit price] |"
        )
    lines += [
        "| Another item, quoted separately | [OWNER FILL: billing] "
        "| [OWNER FILL: price] | [BUYER FILL: quantity] | [OWNER FILL: amount] |",
        "| **Total** | | | | [OWNER FILL: total] |",
        "",
        "## What is included",
        "",
        "One self-contained board report per agency id the buyer names, in a single archive,",
        "with a manifest that lists every id asked for and what happened to it. A program name,",
        "logo, and accent color appear on every cover. The numbers are the ones on the public",
        "site. A purchase buys no influence over grades, methodology, or which agencies are",
        "listed.",
        "",
        "Program name for the cover: [BUYER FILL: program name]",
        "",
        "Agency ids to include: [BUYER FILL: list of agency ids, up to the item's limit]",
        "",
        "## Terms",
        "",
        "- Payment terms: [OWNER FILL: payment terms]",
        "- What starts the delivery clock, and the delivery date: [OWNER FILL: trigger and date]",
        "- Refund terms for an invoiced order: [OWNER FILL: refund terms]",
        "- How to pay (remit-to details): [OWNER FILL: payment instructions]",
        "- Supplier forms supplied with this quote, if any: [OWNER FILL: list of forms]",
        "- Purchase order number, once issued: [BUYER FILL: purchase order number]",
        "",
        "## Acceptance",
        "",
        "To accept, cite the quote number on a purchase order, or sign below.",
        "",
        "| | Seller | Buyer |",
        "| --- | --- | --- |",
        "| Name | [OWNER FILL: name] | [BUYER FILL: name] |",
        "| Title | [OWNER FILL: title] | [BUYER FILL: title] |",
        "| Date | [OWNER FILL: date] | [BUYER FILL: date] |",
        "",
    ]
    return "\n".join(lines)


def render_printable_html(markdown: str, title: str) -> str:
    """A printable HTML copy of a Markdown document, with its own small
    stylesheet and no scripts, so it prints the same from any browser."""
    body = _MD.render(markdown)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"<style>{_CSS}</style>\n</head>\n<body>\n{body}</body>\n</html>\n"
    )


def unfilled_markers(text: str) -> list[str]:
    """Every ``[OWNER FILL: ...]`` and ``[BUYER FILL: ...]`` marker still in ``text``."""
    return _MARKER_RE.findall(text)


def sync_invoice_docs(root: Path | None = None) -> list[Path]:
    """Rewrite ``docs/invoice/quote-template.{md,html}`` from the plan. Returns the
    paths that changed (empty when in sync)."""
    base = root or _repo_root()
    markdown = render_quote_markdown(load_bundle_plan(base))
    outputs = {
        base / "docs" / "invoice" / "quote-template.md": markdown,
        base / "docs" / "invoice" / "quote-template.html": render_printable_html(
            markdown, "Quote: GTFS Scorecard program report bundle"
        ),
    }
    changed: list[Path] = []
    for path, content in outputs.items():
        if path.exists() and path.read_text() == content:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        changed.append(path)
    return changed
