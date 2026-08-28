"""A render failure says which feed it happened to.

#308. A TypeError in `_accessibility_score` took down four pipeline runs, three
Intraday and one Daily, over roughly 20 hours. Every traceback ended the same
way, naming the function, the line and the type:

    File "scorecard_pipeline/render_site.py", line 2713, in _render_agency
      _accessibility_substat(cat, artifact) + _fares_substat(cat)
    File "scorecard_pipeline/render_site.py", line 998, in _accessibility_score
      earned = float(comp.get("wheelchair_stops", 0)) + ...
    TypeError: float() argument must be a string or a real number, not 'NoneType'

None of them named which feed's artifact was being rendered. `render_site` logs
nothing per agency, so the surrounding log was a list of rollup paths and then
the traceback. The bug only fires for a stops-less demand-response feed, a small
and identifiable set, and the slug would have made it a five-minute job. It also
could not be recovered from the committed corpus: across 30,578 committed
artifacts with a measured completeness category, zero carry a null wheelchair
component, so the triggering feed is one the live run scored and this repo does
not hold.

These tests pin both halves: the slug reaches the traceback, and the original
exception is still the cause rather than being swallowed.
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline import render_site as render_site_module
from scorecard_pipeline.render_site import render_site

NOW = dt.datetime(2026, 7, 13, 12, tzinfo=dt.UTC)


def _fixture_site(isolated_repo_root: Path) -> None:
    shutil.copytree(Path(__file__).parent / "fixtures" / "golden_site", isolated_repo_root)


def test_a_failing_agency_page_names_the_agency(
    isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fixture_site(isolated_repo_root)
    original = render_site_module._render_agency

    def explode(artifact: dict[str, Any], *args: Any, **kwargs: Any) -> str:
        if artifact["agency"]["id"] == "yolobus":
            raise TypeError("float() argument must be a string or a real number, not 'NoneType'")
        return str(original(artifact, *args, **kwargs))

    monkeypatch.setattr(render_site_module, "_render_agency", explode)
    with pytest.raises(RuntimeError, match="rendering agency 'yolobus'"):
        render_site(NOW)


def test_the_original_failure_is_kept_as_the_cause(
    isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not proposing to swallow the exception: the run must still fail, loudly."""
    _fixture_site(isolated_repo_root)
    original = render_site_module._render_agency

    def explode(artifact: dict[str, Any], *args: Any, **kwargs: Any) -> str:
        if artifact["agency"]["id"] == "yolobus":
            raise TypeError("not 'NoneType'")
        return str(original(artifact, *args, **kwargs))

    monkeypatch.setattr(render_site_module, "_render_agency", explode)
    with pytest.raises(RuntimeError) as excinfo:
        render_site(NOW)
    cause = excinfo.value.__cause__
    assert isinstance(cause, TypeError)
    assert "not 'NoneType'" in str(cause)


def test_a_failure_anywhere_in_the_feed_s_pages_is_named(
    isolated_repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The board packet and the call brief are rendered in the same iteration."""
    _fixture_site(isolated_repo_root)
    original = render_site_module._render_board_page

    def explode(artifact: dict[str, Any], *args: Any, **kwargs: Any) -> str:
        if artifact["agency"]["id"] == "unitrans":
            raise ValueError("board packet blew up")
        return str(original(artifact, *args, **kwargs))

    monkeypatch.setattr(render_site_module, "_render_board_page", explode)
    with pytest.raises(RuntimeError, match="rendering agency 'unitrans'"):
        render_site(NOW)


def test_a_clean_render_is_untouched(isolated_repo_root: Path) -> None:
    """The wrapper adds nothing to the happy path."""
    _fixture_site(isolated_repo_root)
    render_site(NOW)
    assert (isolated_repo_root / "web" / "agency" / "yolobus" / "index.html").exists()
