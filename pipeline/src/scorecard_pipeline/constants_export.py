"""Presentation constants shared by the pipeline and the web app, exported once.

The SPA (web/src/app.js) used to hand-mirror the pipeline's presentation
vocabulary: grade bands and ranks, category labels and order, severity labels,
the stale-feed threshold, the rule-link table, and the fix-guide base URL.
Several of those carried "keep in sync" comments, and only the nav had a drift
test. This module ends the mirroring: it renders the Python definitions into
``web/src/generated/constants.js``, an ES module the app imports, so the two
languages agree by construction. ``scorecard render-constants`` refreshes the
file (``render-site`` runs it too); ``tests/test_generated_constants.py``
fails CI when the committed copy no longer matches a fresh render.

Constants whose semantics live elsewhere are imported from their home module
(``metrics.STALE_FEED_DAYS``, ``score.GRADE_BANDS``, ``site_shell``'s category
and severity labels, the ``rule_links`` table). Presentation constants that had
no single Python home before (grade order and rank, size-tier display words,
the fix-guide base URL) are defined here, and the Python renderers import them
from here for the same one-definition guarantee.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import repo_root
from .jurisdiction_guidance import (
    JURISDICTION_GUIDANCE,
    SUPPORT_RESOURCES,
    UNIVERSAL_GUIDANCE,
    US_NTD_GUIDANCE,
    US_STATE_SUBDIVISION_CODES,
)
from .metrics import STALE_FEED_DAYS
from .rule_links import AUTHORITY_LABELS, RULE_LINKS, VALIDATOR_RULES_PAGE
from .score import GRADE_BANDS
from .site_shell import CATEGORY_LABELS, CATEGORY_ORDER, SEVERITY_LABELS

# Where a finding's plain-language fix page lives. The notice-to-fix knowledge
# base is Markdown under docs/fixes/<code>.md; GitHub renders it, so the app
# links each finding to its page by code.
FIX_DOCS_BASE = "https://github.com/ChelseaKR/gtfs-scorecard/blob/main/docs/fixes/"

# Worst-to-best grade order and rank, derived from the grade bands so a grade
# letter cannot exist in score.py without a rank here. Used wherever two grades
# are compared (regression detection, `scorecard try` CI gating) and as the
# split-flap reel index on the agency hero.
GRADE_ORDER: list[str] = [letter for _, letter in reversed(GRADE_BANDS)]
GRADE_RANK: dict[str, int] = {letter: rank for rank, letter in enumerate(GRADE_ORDER)}

# Size-tier display words for peer-context lines ("mid-size", not the
# directory's "medium" token), keyed by size_tier.
TIER_LABELS = {"small": "small", "medium": "mid-size", "large": "large"}

# Repo-relative path of the generated ES module.
GENERATED_PATH = Path("web") / "src" / "generated" / "constants.js"

_HEADER = (
    "// GENERATED — do not edit; run `scorecard render-constants`.\n"
    "// Source of truth: pipeline/src/scorecard_pipeline/constants_export.py\n"
    "// (grade bands from score.py, STALE_FEED_DAYS from metrics.py, category and\n"
    "// severity labels from site_shell.py, rule links from rule_links.py).\n"
    "// pipeline/tests/test_generated_constants.py fails CI when this file drifts.\n"
)


def _exports() -> dict[str, Any]:
    """Name -> value for every constant the generated module exports, in the
    order they are emitted. Every value must be JSON-serializable."""
    return {
        "STALE_FEED_DAYS": STALE_FEED_DAYS,
        "GRADE_BANDS": [{"min_score": floor, "grade": letter} for floor, letter in GRADE_BANDS],
        "GRADE_ORDER": GRADE_ORDER,
        "GRADE_RANK": GRADE_RANK,
        "CATEGORY_LABELS": CATEGORY_LABELS,
        "CATEGORY_ORDER": CATEGORY_ORDER,
        "SEVERITY_LABELS": SEVERITY_LABELS,
        "TIER_LABELS": TIER_LABELS,
        "FIX_DOCS_BASE": FIX_DOCS_BASE,
        "VALIDATOR_RULES_PAGE": VALIDATOR_RULES_PAGE,
        "AUTHORITY_LABELS": AUTHORITY_LABELS,
        "RULE_LINKS": {
            code: {
                "kind": link.kind,
                "url": link.url,
                "canonical": link.canonical,
                "authority": link.authority,
            }
            for code, link in RULE_LINKS.items()
        },
        "UNIVERSAL_GUIDANCE": UNIVERSAL_GUIDANCE,
        "US_NTD_GUIDANCE": US_NTD_GUIDANCE,
        "JURISDICTION_GUIDANCE": JURISDICTION_GUIDANCE,
        "SUPPORT_RESOURCES": SUPPORT_RESOURCES,
        "US_STATE_SUBDIVISION_CODES": US_STATE_SUBDIVISION_CODES,
    }


def render_constants_js() -> str:
    """The generated ES module as one deterministic string, so the committed
    copy can be compared byte-for-byte against a fresh render."""
    parts = [_HEADER]
    for name, value in _exports().items():
        parts.append(f"export const {name} = {json.dumps(value, sort_keys=True, indent=2)};\n")
    return "\n".join(parts)


def write_constants(path: Path | None = None) -> Path:
    """Write the generated module (default: web/src/generated/constants.js
    under the repo root) and return the path written."""
    target = path if path is not None else repo_root() / GENERATED_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(render_constants_js())
    return target
