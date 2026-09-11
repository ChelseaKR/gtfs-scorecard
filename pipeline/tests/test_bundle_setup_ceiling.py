"""The setup form's client-side agency ceiling agrees with the server's caps.

`web/src/bundle-setup.js` refuses an oversized list before posting it, so a
buyer does not wait on a round trip to learn the obvious. It cannot know which
price was paid, so the number it checks is the largest cap across every plan,
and the per-plan limit stays the server's job (`PLAN_AGENCY_CAPS` in
`infra/program-bundle/common.py`).

Before this test the page said "A bundle covers at most 100 agencies" to every
buyer, including one who had bought the 25-agency bundle, whom the server then
refused at 26. These tests keep the two numbers from drifting apart again, and
keep the page from stating a limit as if it applied to the buyer's own plan.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SETUP_JS = REPO / "web" / "src" / "bundle-setup.js"
COMMON_PY = REPO / "infra" / "program-bundle" / "common.py"


def _load_common() -> Any:
    spec = importlib.util.spec_from_file_location("program_bundle_common", COMMON_PY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("program_bundle_common", module)
    spec.loader.exec_module(module)
    return module


def _client_ceiling() -> int:
    source = SETUP_JS.read_text(encoding="utf-8")
    found = re.findall(r"\.filter\(Boolean\)\.length\s*>\s*(\d+)", source)
    assert len(found) == 1, f"expected one agency-count guard in {SETUP_JS.name}, found {found}"
    return int(found[0])


def test_client_ceiling_equals_the_largest_plan_cap() -> None:
    caps = _load_common().PLAN_AGENCY_CAPS
    assert _client_ceiling() == max(caps.values()), (
        "bundle-setup.js refuses lists over a different number than the largest "
        f"plan cap {dict(caps)}; a buyer would be told the wrong limit"
    )


def test_client_message_does_not_promise_a_limit_to_every_plan() -> None:
    source = SETUP_JS.read_text(encoding="utf-8")
    smallest = min(_load_common().PLAN_AGENCY_CAPS.values())
    # The old copy read "A bundle covers at most 100 agencies", which is false
    # for anyone on the smallest plan. The ceiling message may name the maximum
    # only as a maximum across bundles, never as what "a bundle" covers.
    assert "A bundle covers at most" not in source
    assert f"at most {smallest}" not in source, (
        "the client must not hardcode a per-plan limit; the server answers with the plan's own cap"
    )
