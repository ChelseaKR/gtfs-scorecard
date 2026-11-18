"""Nothing on the site blinks or moves for more than five seconds on its own.

WCAG 2.2.2 (Pause, Stop, Hide) covers anything that starts by itself, runs
alongside other content and lasts more than five seconds: it needs a way to
stop it. The site has no pause control, so its animations have to end on their
own inside that window. The scorecard's status dot used to blink for as long
as the page was open, next to the grade a reader is trying to take in.

`prefers-reduced-motion` already switches every animation off for readers who
ask the system for that. This is about everyone else.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCES = (ROOT / "web" / "src" / "styles.css", ROOT / "web" / "index.html")

_ANIMATION = re.compile(r"(?<![-a-z])animation\s*:\s*([^;}]+)")
_TIME = re.compile(r"(?<![\w.])(\d*\.?\d+)(ms|s)\b")
LIMIT_SECONDS = 5.0


def _seconds(value: str, unit: str) -> float:
    return float(value) / 1000 if unit == "ms" else float(value)


def _run_time(shorthand: str) -> float:
    """Total seconds one `animation` shorthand runs: delay + duration x count."""
    times = [_seconds(v, u) for v, u in _TIME.findall(shorthand)]
    duration = times[0] if times else 0.0
    delay = times[1] if len(times) > 1 else 0.0
    without_times = _TIME.sub("", re.sub(r"\([^)]*\)", "", shorthand))
    count = re.search(r"(?<![\w.-])(\d+(?:\.\d+)?)(?![\w.-])", without_times)
    return delay + duration * (float(count.group(1)) if count else 1.0)


def test_no_animation_runs_forever() -> None:
    for source in SOURCES:
        for shorthand in _ANIMATION.findall(source.read_text(encoding="utf-8")):
            assert "infinite" not in shorthand, (
                f"{source.name}: `animation: {shorthand.strip()}` never stops, "
                "and the page has no control to pause it"
            )


def test_every_animation_ends_within_five_seconds() -> None:
    for source in SOURCES:
        for shorthand in _ANIMATION.findall(source.read_text(encoding="utf-8")):
            if "infinite" in shorthand:
                continue  # reported by the test above
            assert _run_time(shorthand) <= LIMIT_SECONDS, (
                f"{source.name}: `animation: {shorthand.strip()}` runs longer "
                f"than {LIMIT_SECONDS:g} seconds"
            )


def test_run_time_reads_the_shorthand() -> None:
    assert _run_time("blip 2s steps(1) 2") == 4.0
    assert _run_time("rise 420ms cubic-bezier(0.2, 0.7, 0.2, 1) both") == 0.42
    assert _run_time("fade 1s ease 500ms 3") == 3.5
