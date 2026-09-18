"""Stand-in for the two commands action.yml's composite step runs: `uv` and `python`.

tests/test_action_evidence_packet.py puts one shim for each on PATH and both
exec this file, naming which tool they stand for. Every call is appended to
``$STUB_CALLS`` as one JSON array, so a test can read back exactly what the
step ran, with which arguments, in which order.

* ``python SCRIPT ARGS`` runs the real script, so action/render_result.py is
  the code under test, not a copy of it.
* ``uv run ... scorecard try`` does not score anything: the validator is a
  Java download. It writes ``$STUB_ARTIFACT_FILE`` to ``--json-out`` unless
  ``$STUB_TRY_WRITES`` is ``0``, and exits ``$STUB_TRY_RC``.
* ``uv run ... scorecard diff`` writes a fixed line to ``--out`` and exits
  ``$STUB_DIFF_RC``.
* ``uv run ... scorecard retest`` runs the real command in process, so a retest
  the step asks for is judged by the code that ships.
"""

from __future__ import annotations

import json
import os
import runpy
import shutil
import sys
from pathlib import Path


def _log(argv: list[str]) -> None:
    with Path(os.environ["STUB_CALLS"]).open("a") as handle:
        handle.write(json.dumps(argv) + "\n")


def _flag(argv: list[str], name: str) -> str:
    return argv[argv.index(name) + 1]


def _scorecard(verb: str, rest: list[str]) -> int:
    if verb == "try":
        print("stub: scorecard try scored the feed")
        if os.environ.get("STUB_TRY_WRITES", "1") == "1":
            out = Path(_flag(rest, "--json-out"))
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(os.environ["STUB_ARTIFACT_FILE"], out)
        return int(os.environ.get("STUB_TRY_RC", "0"))
    if verb == "diff":
        Path(_flag(rest, "--out")).write_text("stub: scorecard diff\n")
        return int(os.environ.get("STUB_DIFF_RC", "0"))
    if verb == "retest":
        from scorecard_pipeline.cli import main as scorecard_main

        return scorecard_main([verb, *rest])
    print(f"stub: no stand-in for scorecard {verb}", file=sys.stderr)
    return 99


def main() -> int:
    tool, *argv = sys.argv[1:]
    _log([tool, *argv])
    if tool == "python":
        script, *rest = argv
        sys.argv = [script, *rest]
        runpy.run_path(script, run_name="__main__")
        return 0
    verb_at = argv.index("scorecard") + 1
    return _scorecard(argv[verb_at], argv[verb_at + 1 :])


if __name__ == "__main__":
    raise SystemExit(main())
