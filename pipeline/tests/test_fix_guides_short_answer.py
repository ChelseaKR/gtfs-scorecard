"""Every fix guide opens with the way it is typed into a search box.

The H1 is a plain phrase (with the finding code in front when it fits the
60-character title budget), and a "The short answer" section carries the
one-line fix right under the code. The first paragraph after the code is also
what the page uses as its meta description, so it has to fit that budget.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

GUIDES = sorted(
    p
    for p in (Path(__file__).resolve().parents[2] / "docs" / "fixes").glob("*.md")
    if p.stem != "README"
)


def problems(text: str) -> list[str]:
    found: list[str] = []
    h1 = re.search(r"^# (.+)$", text, flags=re.M)
    if not h1 or not 15 <= len(h1.group(1)) <= 60:
        found.append("h1 length")
    if h1 and h1.group(1).startswith("Fix:"):
        found.append("h1 still starts with Fix:")
    answer = re.search(r"^## The short answer\n\n(.+?)\n\n", text, flags=re.M | re.S)
    if not answer:
        found.append("no short answer")
    else:
        body = " ".join(answer.group(1).split())
        if not 50 <= len(body) <= 155:
            found.append("short answer length")
        if "Fix:" not in body:
            found.append("short answer names no fix")
    code = re.search(r"^Code: `[^`]+`", text, flags=re.M)
    if answer and code and answer.start() < code.start():
        found.append("short answer before code line")
    return found


def test_there_are_guides_to_check() -> None:
    assert len(GUIDES) >= 41


@pytest.mark.parametrize("path", GUIDES, ids=lambda p: p.stem)
def test_guide_leads_with_the_search_phrase_and_the_one_line_fix(path: Path) -> None:
    assert problems(path.read_text()) == [], path.name


@pytest.mark.parametrize("path", GUIDES[:3], ids=lambda p: p.stem)
def test_negative_control_the_check_fails_without_a_short_answer(path: Path) -> None:
    text = path.read_text()
    sabotaged = re.sub(r"## The short answer\n\n.+?\n\n", "", text, count=1, flags=re.S)
    assert sabotaged != text  # the sabotage applied
    assert "no short answer" in problems(sabotaged)
    long_h1 = re.sub(r"^# .+$", "# " + "x" * 80, text, count=1, flags=re.M)
    assert long_h1 != text
    assert "h1 length" in problems(long_h1)
