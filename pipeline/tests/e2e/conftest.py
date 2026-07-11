"""Fixtures for the behavioral browser tests: serve the real site locally.

The docroot mirrors the deployed layout (.github/workflows/pages.yml): the
contents of web/ at the site root, with the committed pipeline artifacts merged
in at /data/artifacts. It is assembled from symlinks (nothing is copied) and
served by the stdlib http.server on a random free 127.0.0.1 port for the whole
session, so the SPA shell at /app/, the prerendered /agency/<id>/ pages, and
the JSON artifacts app.js fetches (its "../data/artifacts" DATA_BASES entry
resolves to /data/artifacts from /app/) all come from this repository.

Every request that would leave 127.0.0.1 (a mapping CDN, for instance) is
aborted, so the tests exercise committed data only and never touch the network.
"""

from __future__ import annotations

import re
import threading
from collections.abc import Iterator
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from playwright.sync_api import Page, Route

# This file is pipeline/tests/e2e/conftest.py, so parents[3] is the repo root.
REPO_ROOT = Path(__file__).resolve().parents[3]

_EXTERNAL_URL = re.compile(r"^https?://(?!127\.0\.0\.1)")


class _QuietHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler without the per-request stderr log lines."""

    def log_message(self, format: str, *args: Any) -> None:
        pass


@pytest.fixture(scope="session")
def site_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A docroot assembled the way pages.yml assembles _site, via symlinks."""
    docroot = tmp_path_factory.mktemp("site")
    for entry in (REPO_ROOT / "web").iterdir():
        if entry.name != "data":
            (docroot / entry.name).symlink_to(entry)
    # web/data/ (the open-data landing page) and the committed artifacts share
    # the /data/ prefix on the deployed site; merge them the same way here.
    data_dir = docroot / "data"
    data_dir.mkdir()
    for entry in (REPO_ROOT / "web" / "data").iterdir():
        (data_dir / entry.name).symlink_to(entry)
    (data_dir / "artifacts").symlink_to(REPO_ROOT / "data" / "artifacts")
    return docroot


@pytest.fixture(scope="session")
def base_url(site_root: Path) -> Iterator[str]:
    """Origin of the locally served site, e.g. http://127.0.0.1:54321.

    Overrides the pytest-base-url fixture of the same name, so pytest-playwright
    contexts get it as their base URL too.
    """
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0),  # port 0: the OS picks a random free port
        partial(_QuietHandler, directory=str(site_root)),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


@pytest.fixture(scope="session")
def app_url(base_url: str) -> str:
    """The SPA shell (web/app/), from which app.js hash-routes."""
    return f"{base_url}/app/"


@pytest.fixture(autouse=True)
def _block_external_requests(page: Page) -> None:
    """Abort any request that would leave 127.0.0.1: hermetic and deterministic."""

    def _abort(route: Route) -> None:
        route.abort()

    page.route(_EXTERNAL_URL, _abort)
