"""Shared test fixtures: synthetic GTFS zips and validator reports."""

from __future__ import annotations

import zipfile
from collections.abc import Callable, Generator
from pathlib import Path

import pytest


@pytest.fixture
def make_gtfs_zip(tmp_path: Path) -> Callable[..., Path]:
    """Build a minimal GTFS zip from a mapping of filename -> CSV text."""

    def _make(files: dict[str, str], name: str = "gtfs.zip") -> Path:
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as zf:
            for filename, text in files.items():
                zf.writestr(filename, text)
        return path

    return _make


@pytest.fixture(autouse=True)
def isolated_repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point all pipeline paths at a throwaway directory."""
    monkeypatch.setenv("SCORECARD_ROOT", str(tmp_path / "repo"))
    return tmp_path / "repo"


@pytest.fixture(autouse=True)
def isolated_registry() -> Generator[None, None, None]:
    """Empty the module-global registry around every test.

    A test that calls load_agencies() otherwise leaks the real registry into
    every later test in the process, and artifact-tree walkers are bounded to
    registered ids whenever the registry is non-empty.
    """
    from scorecard_pipeline.config import AGENCIES

    AGENCIES.clear()
    yield
    AGENCIES.clear()
