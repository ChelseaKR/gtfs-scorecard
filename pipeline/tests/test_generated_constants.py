"""The SPA's presentation constants (grade bands and ranks, category and
severity labels, tier words, thresholds, rule links) are generated from the
Python definitions into web/src/generated/constants.js, so the two languages
cannot drift the way the hand-kept mirrors once could. Same pattern as
test_static_nav.py: the committed generated file must exactly equal a fresh
render, so any change to the Python definitions fails CI until
`scorecard render-constants` is re-run and the result committed."""

from __future__ import annotations

import json
import re
from pathlib import Path

from scorecard_pipeline.constants_export import (
    GENERATED_PATH,
    render_constants_js,
    write_constants,
)

# The real repo (not the per-test tmp root that conftest points SCORECARD_ROOT
# at): this file is pipeline/tests/test_generated_constants.py, so parents[2]
# is the repo root.
_REPO = Path(__file__).resolve().parents[2]

_EXPORT_RE = re.compile(r"^export const (\w+) = (.+?);\n(?=\n|\Z)", re.M | re.S)


def test_committed_constants_match_render() -> None:
    committed = (_REPO / GENERATED_PATH).read_text()
    assert committed == render_constants_js(), (
        "web/src/generated/constants.js drifted from the Python definitions; "
        "run `scorecard render-constants` and commit the result"
    )


def test_render_is_marked_generated_and_every_export_is_json() -> None:
    # The module must announce itself as generated, and each export's payload
    # must parse as JSON, so a renderer regression cannot ship a module the
    # browser would reject.
    rendered = render_constants_js()
    assert rendered.startswith("// GENERATED")
    exports = _EXPORT_RE.findall(rendered)
    names = [name for name, _ in exports]
    for expected in (
        "STALE_FEED_DAYS",
        "GRADE_BANDS",
        "GRADE_ORDER",
        "GRADE_RANK",
        "CATEGORY_LABELS",
        "CATEGORY_ORDER",
        "SEVERITY_LABELS",
        "TIER_LABELS",
        "FIX_DOCS_BASE",
        "VALIDATOR_RULES_PAGE",
        "AUTHORITY_LABELS",
        "RULE_LINKS",
        "UNIVERSAL_GUIDANCE",
        "US_NTD_GUIDANCE",
        "JURISDICTION_GUIDANCE",
        "SUPPORT_RESOURCES",
        "US_STATE_SUBDIVISION_CODES",
    ):
        assert expected in names, f"missing export {expected}"
    for _name, payload in exports:
        json.loads(payload)  # raises on any non-JSON payload


def test_write_constants_defaults_to_repo_layout(isolated_repo_root: Path) -> None:
    # conftest points SCORECARD_ROOT at a throwaway root, so the default path
    # lands there (never in the real repo) and matches a fresh render.
    out = write_constants()
    assert out == isolated_repo_root / GENERATED_PATH
    assert out.read_text() == render_constants_js()


def test_write_constants_honors_an_explicit_path(tmp_path: Path) -> None:
    out = write_constants(tmp_path / "elsewhere" / "constants.js")
    assert out == tmp_path / "elsewhere" / "constants.js"
    assert out.read_text() == render_constants_js()
