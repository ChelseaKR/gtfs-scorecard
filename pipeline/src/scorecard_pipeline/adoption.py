"""A covered-set view of which newer GTFS capabilities agencies publish.

The completeness category already records, per agency, whether a feed carries
GTFS-Flex (demand-responsive/dial-a-ride service), fare data (legacy
``fare_attributes`` or the newer Fares v2 products and leg rules), station
modelling with GTFS-Pathways, and rider-facing text in ``translations.txt``
(see ``flex.py``, ``fares.py``, ``pathways.py``, ``translations.py``).
That answers the question for one agency. Programs deciding where to invest, and
anyone asking whether it is worth adding these to a feed, ask a different one:
across the feeds tracked here, how many publish each optional part of the spec,
and where?

This module rolls the per-agency detail up into one covered-set picture: the share
of feeds publishing flexible service, fare data (and how many use Fares v2),
accessible station paths, and translations, plus portable country/subdivision
groups, a legacy U.S.-state breakdown, and a short sample of feeds that already
publish each. It
is pure over the per-agency artifacts the renderer already reads, so it adds no
per-agency work and is safe to re-run. It changes no grade.
"""

from __future__ import annotations

from typing import Any

from .location_rollups import portable_location_fields, portable_location_rollups

# Fare model values recorded by fares.detect_fares(): no fare data, the legacy
# fare_attributes model, or the newer Fares v2 products + leg rules.
_FARE_MODELS = ("none", "legacy", "v2")


def _string_list(value: Any) -> list[str]:
    """Clean a list-shaped artifact field without splitting malformed text."""
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _nonnegative_int(value: Any) -> int:
    """A producer count, or zero when an older/malformed detail is not numeric."""
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def adoption_record(artifact: dict[str, Any]) -> dict[str, Any] | None:
    """Extract one agency's capability-adoption record from its artifact.

    Reads the flex, fares, pathways, and translations detail the completeness
    category already stores. Returns None when completeness was not measured, or was measured
    before these details were recorded (an older artifact), so a missing read is
    skipped rather than counted as "does not publish".
    """
    comp = artifact.get("categories", {}).get("completeness", {})
    if comp.get("status") != "measured":
        return None
    details = comp.get("details") or {}
    # fares detail is always written for a measured feed; its absence marks an
    # artifact from before capability detail was recorded.
    if not isinstance(details.get("fares"), dict):
        return None
    flex = details.get("flex") or {}
    fares = details.get("fares") or {}
    pathways = details.get("pathways") or {}
    # cemv detail arrived later than the others (field adopted 2025-09); an
    # artifact scored before it reads as not-declared, never as an error.
    cemv = details.get("cemv") or {}
    # Translation measurement arrived after the original capability contract.
    # An older artifact with no block stays unknown, distinct from a current
    # feed that was checked and does not publish translations.txt.
    translations_detail = details.get("translations")
    if isinstance(translations_detail, dict):
        translations: dict[str, Any] = translations_detail
        translations_measured = True
    else:
        translations = {}
        translations_measured = False
    fare_model = str(fares.get("model", "none") or "none")
    if fare_model not in _FARE_MODELS:
        fare_model = "none"
    agency = artifact.get("agency", {})
    location = portable_location_fields(agency)
    return {
        "id": agency.get("id", ""),
        "name": agency.get("name", agency.get("id", "")),
        "state": (agency.get("state", "") or "Unlocated") if location["country"] == "US" else "",
        **location,
        "has_flex": bool(flex.get("has_flex")),
        "fare_model": fare_model,
        "has_fares": fare_model != "none",
        "has_fares_v2": fare_model == "v2",
        "has_pathways": bool(pathways.get("has_pathways")),
        "has_step_free": bool(pathways.get("has_step_free")),
        "has_cemv": bool(cemv.get("supported")),
        "translations_measured": translations_measured,
        "has_translations": (
            translations.get("has_translations") is True if translations_measured else None
        ),
        "translation_count": (
            _nonnegative_int(translations.get("translation_count"))
            if translations_measured
            else None
        ),
        "translation_languages": (
            _string_list(translations.get("languages")) if translations_measured else None
        ),
        "translated_tables": (
            _string_list(translations.get("translated_tables")) if translations_measured else None
        ),
        "feed_lang": (
            translations.get("feed_lang")
            if translations_measured and isinstance(translations.get("feed_lang"), str)
            else None
        ),
    }


def _share(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    n = sum(1 for r in records if r.get(key))
    total = len(records)
    return {"count": n, "pct": round(100 * n / total, 1) if total else 0.0}


def _optional_share(records: list[dict[str, Any]], key: str) -> dict[str, Any]:
    """Share among rows where a later-added boolean was actually measured."""
    measured = [record for record in records if isinstance(record.get(key), bool)]
    count = sum(record[key] for record in measured)
    denominator = len(measured)
    return {
        "count": count,
        "pct": round(100 * count / denominator, 1) if denominator else 0.0,
        "measured_feed_record_count": denominator,
    }


def _location_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Capability counts for one country or subdivision."""
    return {
        "feed_records": len(records),
        # v1 compatibility alias. These rows count feed records, not distinct
        # operating organizations.
        "agencies": len(records),
        "flex": sum(bool(record.get("has_flex")) for record in records),
        "fares": sum(bool(record.get("has_fares")) for record in records),
        "fares_v2": sum(bool(record.get("has_fares_v2")) for record in records),
        "pathways": sum(bool(record.get("has_pathways")) for record in records),
        "step_free": sum(bool(record.get("has_step_free")) for record in records),
        "cemv": sum(bool(record.get("has_cemv")) for record in records),
        "translations": sum(record.get("has_translations") is True for record in records),
        "translations_measured": sum(
            record.get("translations_measured") is True for record in records
        ),
    }


def _state_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Legacy U.S.-state rows retained for the existing adoption table."""
    by_state: dict[str, dict[str, Any]] = {}
    for record in records:
        if record.get("country") != "US":
            continue
        bucket = by_state.setdefault(
            record["state"],
            {
                "state": record["state"],
                "agencies": 0,
                "flex": 0,
                "fares": 0,
                "fares_v2": 0,
                "pathways": 0,
                "translations": 0,
                "translations_measured": 0,
            },
        )
        bucket["agencies"] += 1
        bucket["flex"] += bool(record["has_flex"])
        bucket["fares"] += bool(record["has_fares"])
        bucket["fares_v2"] += bool(record["has_fares_v2"])
        bucket["pathways"] += bool(record["has_pathways"])
        bucket["translations_measured"] += record.get("translations_measured") is True
        bucket["translations"] += record.get("has_translations") is True

    return [
        {**by_state[state], "feed_records": by_state[state]["agencies"]}
        for state in sorted(by_state, key=lambda name: (-by_state[name]["agencies"], name))
    ]


def national_adoption(records: list[dict[str, Any]], *, top: int = 10) -> dict[str, Any]:
    """Roll per-agency adoption records up into the covered-set picture.

    Reports how many feeds were read, the count and share publishing each
    capability (flexible service, fare data, Fares v2, station pathways,
    step-free paths), the fare-model split, portable location groups, a
    U.S.-state breakdown, and a sample of feeds already publishing flex, Fares
    v2, and pathways. Derived entirely from ``adoption_record`` output, it is
    deterministic and safe to re-run. ``top`` caps the sample lists.
    """
    count = len(records)
    fare_models = {
        model: sum(record["fare_model"] == model for record in records) for model in _FARE_MODELS
    }
    states = _state_summaries(records)

    def sample(key: str) -> list[dict[str, Any]]:
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "state": r["state"],
                "country": r["country"],
                "subdivision_code": r["subdivision_code"],
                "subdivision_name": r["subdivision_name"],
            }
            for r in sorted((x for x in records if x.get(key)), key=lambda r: r["name"])
        ][:top]

    translation_sample = [
        {
            "id": r["id"],
            "name": r["name"],
            "state": r["state"],
            "country": r["country"],
            "subdivision_code": r["subdivision_code"],
            "subdivision_name": r["subdivision_name"],
            "translation_count": r.get("translation_count", 0),
            "languages": r.get("translation_languages") or [],
            "translated_tables": r.get("translated_tables") or [],
        }
        for r in sorted(
            (record for record in records if record.get("has_translations") is True),
            key=lambda record: record["name"],
        )
    ][:top]

    return {
        "measured_feed_record_count": count,
        # v1 compatibility alias. The metric denominator is feed records.
        "agency_count": count,
        "flex": _share(records, "has_flex"),
        "fares": _share(records, "has_fares"),
        "fares_v2": _share(records, "has_fares_v2"),
        "pathways": _share(records, "has_pathways"),
        "step_free": _share(records, "has_step_free"),
        "cemv": _share(records, "has_cemv"),
        "translations": _optional_share(records, "has_translations"),
        "fare_models": fare_models,
        "states": states,
        "countries": portable_location_rollups(records, _location_summary),
        "flex_sample": sample("has_flex"),
        "fares_v2_sample": sample("has_fares_v2"),
        "pathways_sample": sample("has_pathways"),
        "translations_sample": translation_sample,
    }
