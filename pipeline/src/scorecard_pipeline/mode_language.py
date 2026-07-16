"""Mode-aware presentation language for scored artifacts.

Service mode is descriptive and ungraded.  This module changes only human-facing
copy after scoring, so a ferry feed does not ask its reader to mentally translate
bus vocabulary and a mixed feed does not pretend one vehicle type represents it.
Technical identifiers, GTFS field names, URLs, and category scores are untouched.
"""

from __future__ import annotations

import copy
import re
from typing import Any

_TEXT_KEYS = {
    "summary",
    "what",
    "why",
    "fix",
    "effort",
    "description",
    "detail",
    "note",
    "title",
    "action",
    "impact",
    "label",
}

_SHORT_MODE_LABELS = {
    "tram": "Tram",
    "subway": "Metro",
    "rail": "Rail",
    "bus": "Bus",
    "ferry": "Ferry",
    "cable_tram": "Cable tram",
    "aerial_lift": "Aerial lift",
    "funicular": "Funicular",
    "trolleybus": "Trolleybus",
    "monorail": "Monorail",
    "other": "Other",
}


def language_kind(artifact: dict[str, Any]) -> str:
    """Return ``ferry``, ``bus``, or the safe ``generic`` presentation kind."""
    profile = artifact.get("mode_profile")
    if not isinstance(profile, dict) or profile.get("measured") is not True:
        return "generic"
    if profile.get("ferry_only") is True:
        return "ferry"
    if profile.get("is_multimodal") is not True and profile.get("primary_mode") == "bus":
        return "bus"
    return "generic"


def mode_label(artifact: dict[str, Any]) -> str | None:
    """Compact, truthful label for the scorecard's ungraded service-mode ribbon."""
    profile = artifact.get("mode_profile")
    if not isinstance(profile, dict) or profile.get("measured") is not True:
        return None
    modes = profile.get("modes")
    if not isinstance(modes, list):
        return None
    keys = [str(row.get("key")) for row in modes if isinstance(row, dict) and row.get("key")]
    if not keys:
        return None
    labels = [_SHORT_MODE_LABELS.get(key, "Other") for key in keys]
    if len(labels) <= 3:
        return " + ".join(labels)
    return f"{' + '.join(labels[:2])} + {len(labels) - 2} more"


def _preserve_case(original: str, replacement: str) -> str:
    if original.isupper():
        return replacement.upper()
    if original[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def _word(text: str, source: str, replacement: str) -> str:
    return re.sub(
        rf"\b{source}\b",
        lambda match: _preserve_case(match.group(0), replacement),
        text,
        flags=re.IGNORECASE,
    )


def adapt_text(text: str, kind: str) -> str:
    """Adapt one narrative string without changing GTFS field/file names."""
    if kind == "bus":
        return text

    plural = "vessels" if kind == "ferry" else "transit vehicles"
    singular = "vessel" if kind == "ferry" else "transit vehicle"
    adapted = _word(_word(text, "buses", plural), "bus", singular)
    adapted = re.sub(
        r"\bwrong streets\b",
        "wrong path",
        adapted,
        flags=re.IGNORECASE,
    )
    adapted = re.sub(
        r"\bwrong corner\b",
        "wrong terminal" if kind == "ferry" else "wrong boarding location",
        adapted,
        flags=re.IGNORECASE,
    )
    if kind != "ferry":
        return adapted

    # These are deliberately phrase-level substitutions: ``stops.txt``,
    # ``stop_id``, and validator rule identifiers remain technically exact.
    ferry_phrases = (
        (r"\baccessible stops\b", "accessible terminals"),
        (r"\bflagged stops\b", "flagged terminals"),
        (r"\bbusiest stops\b", "busiest terminals"),
        (r"\bevery stop\b", "every terminal"),
        (r"\bSome stops exist\b", "Some terminals exist"),
        (r"\bRiders at the stop\b", "Riders at the terminal"),
        (r"\bwalk to a stop\b", "go to a terminal"),
        (r"(\b\d+(?:\.\d+)?%? of (?:\d+ )?)stops\b", r"\1terminals"),
        (r"\bSome stops sit\b", "Some terminals sit"),
        (r"\bper flagged stop\b", "per flagged terminal"),
        (r"\bno trip ever stops at them\b", "no trip serves them"),
        (r"\bwhat the vessel displays\b", "the published sailing destination"),
        (r"\bwhich direction a vessel is going\b", "which destination a sailing serves"),
    )
    for source, replacement in ferry_phrases:
        adapted = re.sub(source, replacement, adapted, flags=re.IGNORECASE)
    return adapted


def _adapt_container(value: Any, kind: str) -> Any:
    if isinstance(value, list):
        return [_adapt_container(item, kind) for item in value]
    if not isinstance(value, dict):
        return value
    adapted: dict[str, Any] = {}
    for key, item in value.items():
        if key in _TEXT_KEYS and isinstance(item, str):
            adapted[key] = adapt_text(item, kind)
        elif isinstance(item, (dict, list)):
            adapted[key] = _adapt_container(item, kind)
        else:
            adapted[key] = item
    return adapted


def adapt_artifact_language(artifact: dict[str, Any]) -> dict[str, Any]:
    """Return a copy with narrative surfaces adapted to the measured mode."""
    result = copy.deepcopy(artifact)
    kind = language_kind(result)
    categories = result.get("categories")
    if isinstance(categories, dict):
        result["categories"] = _adapt_container(categories, kind)
    for key in ("top_fixes", "recommendations"):
        if isinstance(result.get(key), list):
            result[key] = _adapt_container(result[key], kind)
    routability = result.get("routability")
    if isinstance(routability, dict) and isinstance(routability.get("findings"), list):
        routability["findings"] = _adapt_container(routability["findings"], kind)
    return result
