"""Agency page content: each finding printed once, and the earlier-rubric feed history."""

from __future__ import annotations

import json
import re
from html import unescape
from pathlib import Path
from typing import Any

from scorecard_pipeline.render_site import (
    FEED_HISTORY_MAX_PERIODS,
    _feed_history_section,
    _finding_handoff,
    _guided_fix_flow,
    _render_agency,
)

FIXTURE = Path(__file__).parent / "fixtures" / "golden_site" / "data" / "artifacts"
A = "a" * 64
B = "b" * 64


def _visible_text(html: str) -> str:
    """Page text a reader sees, without the copy-ready textareas' payload."""
    html = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S | re.I)
    html = re.sub(r"<textarea.*?</textarea>", "", html, flags=re.S | re.I)
    return unescape(re.sub(r"<[^>]+>", " ", html))


def _artifact() -> dict[str, Any]:
    artifact: dict[str, Any] = json.loads((FIXTURE / "yolobus" / "latest.json").read_text())
    return artifact


# --- each finding once -------------------------------------------------------


def test_scorecard_handoff_points_at_the_card_instead_of_repeating_it() -> None:
    art = _artifact()
    first = art["top_fixes"][0]
    html = _finding_handoff(art, "yolobus", "/agency/yolobus/", cards_on_page=True)
    panels = re.sub(r"<textarea.*?</textarea>", "", html, flags=re.S | re.I)
    assert first["what"] not in unescape(panels)
    assert first["fix"] not in unescape(panels)
    assert f'href="#finding-{first["code"]}">Fix 01 in Top things to fix</a>' in html
    # The copy payload still carries everything the copy button sends.
    textarea = re.search(r"<textarea.*?>(.*?)</textarea>", html, flags=re.S | re.I)
    assert textarea is not None
    assert first["what"] in unescape(textarea.group(1))
    assert first["fix"] in unescape(textarea.group(1))


def test_brief_and_board_handoffs_keep_the_full_text() -> None:
    art = _artifact()
    html = _finding_handoff(art, "yolobus", "/agency/yolobus/brief/")
    panels = re.sub(r"<textarea.*?</textarea>", "", html, flags=re.S | re.I)
    assert art["top_fixes"][0]["what"] in unescape(panels)
    assert "Top things to fix</a>" not in html


def test_handoff_reference_uses_the_card_number_when_a_fix_has_no_code() -> None:
    art = _artifact()
    art["top_fixes"] = [{"what": "No code.", "fix": "Do a thing."}, *art["top_fixes"][:2]]
    html = _finding_handoff(art, "yolobus", "/agency/yolobus/", cards_on_page=True)
    second = art["top_fixes"][1]["code"]
    assert f'href="#finding-{second}">Fix 02 in Top things to fix</a>' in html


def test_guided_flow_names_each_fix_by_its_card() -> None:
    art = _artifact()
    html = _guided_fix_flow(art, "yolobus", has_fixlog=False)
    for number, fix in enumerate(art["top_fixes"], start=1):
        assert f'<a href="#finding-{fix["code"]}">Fix {number:02d}</a>' in html
        assert fix["fix"] not in unescape(html)


def test_full_scorecard_prints_each_finding_once_outside_the_copy_text() -> None:
    art = _artifact()
    text = _visible_text(_render_agency(art))
    for fix in art["top_fixes"]:
        # The card states the evidence; "Everything we checked" may list it
        # again as part of the complete list, and nothing else may.
        assert text.count(fix["what"]) <= 2, fix["code"]
        assert text.count(fix["fix"]) <= 2, fix["code"]


def test_negative_control_the_old_handoff_repeats_the_finding() -> None:
    art = _artifact()
    old = _finding_handoff(art, "yolobus", "/agency/yolobus/")
    new = _finding_handoff(art, "yolobus", "/agency/yolobus/", cards_on_page=True)
    what = art["top_fixes"][0]["what"]

    def strip(html: str) -> str:
        return unescape(re.sub(r"<textarea.*?</textarea>", "", html, flags=re.S | re.I))

    assert what in strip(old)
    assert what not in strip(new)


# --- feed history -----------------------------------------------------------


def _row(
    date: str, sha: str | None, rubric: str, grade: str = "C", score: float = 70.0, **kw: Any
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": date,
        "rubric_version": rubric,
        "grade": grade,
        "score": score,
        "validator_version": "8.0.1",
        "scoring_profile_id": "us-default",
        "scoring_profile_rubric_version": rubric,
        "reader_archive_profile": "raw-v1",
        "categories": {"correctness": 80.0},
    }
    if sha:
        row["feed_sha256"] = sha
    row.update(kw)
    return row


def test_history_shows_earlier_rubric_grades_labeled_and_separate() -> None:
    history = [
        _row("2026-06-16", A, "1.1", "C", 79.3, days_until_expiry=198),
        _row("2026-07-10", A, "1.1", "C", 79.3, days_until_expiry=174),
        _row("2026-08-06", B, "1.3", "B", 81.0, days_until_expiry=120),
        _row("2026-10-02", B, "1.4", "C", 75.5, days_until_expiry=55),
        _row("2026-10-03", B, "1.4", "C", 75.5, days_until_expiry=54),
    ]
    html = _feed_history_section(history)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    assert "Feed history" in text
    assert (
        "C, 79.3 under rubric 1.1, an earlier scoring contract; not comparable with today’s grade"
        in text
    )
    assert (
        "B, 81 under rubric 1.3, an earlier scoring contract; not comparable with today’s grade"
        in text
    )
    assert "Current rubric: see the trend above" in text
    # The current contract's scores are never printed here.
    assert "75.5" not in text
    # Newest first, each file named, and the service end date as published then.
    assert text.index("2026-10-02") < text.index("2026-08-06") < text.index("2026-06-16")
    assert "2026-06-16 to 2026-07-10 (2 checks)" in text
    assert A[:12] in html and B[:12] in html
    assert "2026-12-31" in text  # 2026-06-16 + 198 days


def test_history_says_not_recorded_instead_of_inventing() -> None:
    history = [_row("2026-06-16", None, "1.1"), _row("2026-10-03", B, "1.4")]
    text = unescape(re.sub(r"<[^>]+>", " ", _feed_history_section(history)))
    # No file hash and no service end date were recorded: both cells say so.
    assert text.count("not recorded") == 3  # the old file, and both service dates
    assert "C, 70 under rubric 1.1" in text


def test_history_adds_nothing_when_everything_is_already_the_trend() -> None:
    history = [_row("2026-10-02", B, "1.4"), _row("2026-10-03", B, "1.4")]
    assert _feed_history_section(history) == ""
    assert _feed_history_section([]) == ""


def test_history_is_bounded() -> None:
    shas = [f"{i:064x}" for i in range(FEED_HISTORY_MAX_PERIODS + 5)]
    history = [_row(f"2026-08-{i + 1:02d}", s, "1.4") for i, s in enumerate(shas)]
    html = _feed_history_section(history)
    assert html.count("<tr><td>") == FEED_HISTORY_MAX_PERIODS
    assert f"of {len(shas)} periods" in html
