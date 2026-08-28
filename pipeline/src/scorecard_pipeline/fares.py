"""Classify a feed's fare model and check that fares are actually applied.

GTFS-Fares v2 splits a fare into a product (what a rider buys) and leg rules
(which trips it applies to). A feed can publish fare products and still show
riders no fare, because nothing wires the products to any trip. That is not a
validator error, so the gtfs-validator passes it, but to a trip planner the fare
is invisible. This names the fare model and catches that published-but-not-applied
gap, framed as a fix. In this first slice the findings do not change the grade
(ADR 0008); the validator covers the structural validity of the fare files.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .gtfs import read_tables
from .metrics import Finding


@dataclass(frozen=True)
class FaresProfile:
    """What the scorecard knows about a feed's fare data."""

    model: str  # "none" | "legacy" | "v2"
    has_products: bool
    has_leg_rules: bool
    has_transfer_rules: bool
    product_count: int
    applied: bool  # a trip planner can show a fare for a trip

    def to_details(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "has_products": self.has_products,
            "has_leg_rules": self.has_leg_rules,
            "has_transfer_rules": self.has_transfer_rules,
            "product_count": self.product_count,
            "applied": self.applied,
        }


def detect_fares(gtfs_zip_path: str) -> FaresProfile:
    """Classify the fare model and whether fares are applied to trips."""
    tables = read_tables(
        gtfs_zip_path,
        [
            "fare_attributes.txt",
            "fare_products.txt",
            "fare_leg_rules.txt",
            "fare_transfer_rules.txt",
        ],
    )
    has_v1 = bool(tables["fare_attributes.txt"])
    products = tables["fare_products.txt"]
    has_v2 = bool(products)
    has_leg_rules = bool(tables["fare_leg_rules.txt"])
    has_transfer_rules = bool(tables["fare_transfer_rules.txt"])

    if has_v2:
        model = "v2"
        # v2 fares are usable only when leg rules wire products to trips.
        applied = has_leg_rules
    elif has_v1:
        model = "legacy"
        # A v1 flat fare is usable on its own.
        applied = True
    else:
        model = "none"
        applied = False

    return FaresProfile(
        model=model,
        has_products=has_v2,
        has_leg_rules=has_leg_rules,
        has_transfer_rules=has_transfer_rules,
        product_count=len(products),
        applied=applied,
    )


def fares_findings(profile: FaresProfile) -> list[Finding]:
    """Findings for the fare model, framed as fixes. Zero-deduction in this first
    slice (ADR 0008): they guide without moving the grade. The absent-fares and
    fare-free cases are handled by the completeness category itself."""
    if profile.model == "v2" and not profile.has_leg_rules:
        return [
            Finding(
                code="scorecard_fares_published_not_applied",
                severity="WARNING",
                count=profile.product_count,
                what="The feed publishes fare products but no fare_leg_rules saying "
                "which trips they apply to.",
                why="Trip planners can't attach a price to a trip, so riders still "
                "see no fare even though products are published.",
                fix="Add fare_leg_rules.txt linking each fare product to the trips "
                "it applies to (by network, area, or time).",
                effort="A rules file; one rule can cover a flat fare across the network.",
                deduction=0.0,
            )
        ]
    return []


# --- Fares v2: rider categories, fare media, and contactless (cEMV) readiness ---
#
# These files extend Fares v2 with who pays which fare and how they pay.
# rider_categories.txt was adopted into the GTFS spec in Feb 2025; it groups
# riders (adult, child, senior, student, and similar eligibility groups) so an
# app can show the right discounted fare. fare_media.txt declares the payment
# methods a fare can be loaded onto or paid with (transit cards, mobile apps,
# cash, contactless bank cards). Open-loop contactless EMV (cEMV / tap-to-pay)
# gained validator support in 2026 and is declared through a fare_media row whose
# fare_media_type is the contactless EMV value.
RIDER_CATEGORIES_FILE = "rider_categories.txt"
FARE_MEDIA_FILE = "fare_media.txt"

# GTFS fare_media_type enum (fare_media.txt). 4 = contactless EMV, i.e. an
# open-loop bank card or device tapped directly at the reader (tap-to-pay).
FARE_MEDIA_TYPE_FIELD = "fare_media_type"
FARE_MEDIA_TYPE_CONTACTLESS_EMV = "4"


@dataclass(frozen=True)
class FaresV2Profile:
    """What the scorecard knows about a feed's Fares v2 rider and payment data."""

    has_products: bool
    has_rider_categories: bool
    has_fare_media: bool
    has_contactless_emv: bool

    def to_details(self) -> dict[str, Any]:
        return {
            "has_products": self.has_products,
            "has_rider_categories": self.has_rider_categories,
            "has_fare_media": self.has_fare_media,
            "has_contactless_emv": self.has_contactless_emv,
        }


def _has_contactless_emv(fare_media_rows: list[dict[str, str]]) -> bool:
    """True when any fare_media row declares contactless EMV (tap-to-pay)."""
    return any(
        row.get(FARE_MEDIA_TYPE_FIELD, "").strip() == FARE_MEDIA_TYPE_CONTACTLESS_EMV
        for row in fare_media_rows
    )


def detect_fares_v2(gtfs_zip_path: str) -> FaresV2Profile:
    """Detect Fares v2 rider categories, fare media, and contactless readiness."""
    tables = read_tables(
        gtfs_zip_path,
        ["fare_products.txt", RIDER_CATEGORIES_FILE, FARE_MEDIA_FILE],
    )
    fare_media_rows = tables[FARE_MEDIA_FILE]
    return FaresV2Profile(
        has_products=bool(tables["fare_products.txt"]),
        has_rider_categories=bool(tables[RIDER_CATEGORIES_FILE]),
        has_fare_media=bool(fare_media_rows),
        has_contactless_emv=_has_contactless_emv(fare_media_rows),
    )


def fares_v2_findings_for(profile: FaresV2Profile) -> list[Finding]:
    """Fares v2 opportunities, framed as fixes. Pure: takes a profile so the
    logic is testable without building a zip. Zero-deduction in this slice
    (ADR 0008): they guide without moving the grade. A fare-free or no-fares feed
    (no fare products) gets nothing here, so agencies without fares aren't shamed."""
    if not profile.has_products:
        return []

    findings: list[Finding] = []
    if not profile.has_rider_categories:
        findings.append(
            Finding(
                code="scorecard_fares_v2_no_rider_categories",
                severity="INFO",
                count=0,
                what="The feed lists fare products but has no rider_categories.txt "
                "to say who each fare is for.",
                why="Apps can only show the full adult fare. Riders who qualify for a "
                "senior, youth, or student discount never see it.",
                fix="Add rider_categories.txt for the fares you already offer. Then "
                "point your fare products at those categories.",
                effort="Usually a short file naming the discount groups you already publish.",
                deduction=0.0,
            )
        )
    if not profile.has_fare_media:
        findings.append(
            Finding(
                code="scorecard_fares_v2_no_fare_media",
                severity="INFO",
                count=0,
                what="The feed publishes fare products but no fare_media.txt "
                "declaring how riders can pay.",
                why="Riders can't tell from the feed which payment methods you take. "
                "A transit card, a phone app, and tap-to-pay all look the same.",
                fix="Add fare_media.txt listing your accepted payment methods, "
                "including contactless EMV if riders can tap to pay.",
                effort="A short file; one row per payment method you accept.",
                deduction=0.0,
            )
        )
    return findings


def fares_v2_findings(gtfs_zip_path: str) -> list[Finding]:
    """Read a static GTFS zip and return its Fares v2 opportunities."""
    return fares_v2_findings_for(detect_fares_v2(gtfs_zip_path))
