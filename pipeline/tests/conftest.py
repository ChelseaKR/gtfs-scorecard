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


@pytest.fixture(autouse=True)
def offline_robots() -> Generator[None, None, None]:
    """Answer every robots.txt read with "no file" so no test touches the network.

    Tests of the robots rules themselves install their own checker
    (ADR 0070).
    """
    from scorecard_pipeline.robots_policy import (
        RobotsChecker,
        RobotsResponse,
        reset_shared_checker,
    )

    reset_shared_checker(RobotsChecker(get=lambda url: RobotsResponse(404, url, "", "")))
    yield
    reset_shared_checker(None)


#: Every User-Agent value any test put on the wire, for tests/test_user_agent.py.
WIRE_USER_AGENTS: list[str] = []


@pytest.fixture(autouse=True)
def no_browser_user_agent_on_the_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail any test whose code sends a browser-like User-Agent (ADR 0075).

    Patched at ``http.client.HTTPConnection.putheader``, the point both
    ``requests`` (through urllib3) and ``urllib.request`` write headers to the
    socket, so no client in the pipeline can get around it by building its own
    session. Tests that stand up a local server therefore check every request
    they make, not only the ones a test names.
    """
    import http.client

    from scorecard_pipeline.user_agent import is_browser_like

    original = http.client.HTTPConnection.putheader

    def guarded(self: http.client.HTTPConnection, header: str | bytes, *values: object) -> None:
        name = header.decode("latin-1") if isinstance(header, bytes) else str(header)
        if name.lower() == "user-agent":
            value = " ".join(
                v.decode("latin-1") if isinstance(v, bytes) else str(v) for v in values
            )
            WIRE_USER_AGENTS.append(value)
            if is_browser_like(value):
                raise AssertionError(
                    f"a request was sent with a browser-like User-Agent: {value!r}"
                )
        original(self, header, *values)  # type: ignore[arg-type]

    monkeypatch.setattr(http.client.HTTPConnection, "putheader", guarded)
