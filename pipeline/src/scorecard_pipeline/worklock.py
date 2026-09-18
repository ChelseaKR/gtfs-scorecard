"""One feed at a time in the memory-heavy part of a score.

The intraday refresh re-scores its changed feeds several at a time
(rescore.py), because most of one feed's wall clock is waiting: a download, and
for a realtime publisher the sampling window, three samples thirty seconds
apart. None of that needs memory or CPU. Validating and scoring does, and the
one runner loss this pipeline has recorded (issue #297) was a validator taking
the runner down on its own. So concurrent `scorecard run` processes take turns
at that part and overlap only the waiting.

The turn is an exclusive ``flock`` on the file named by
``SCORECARD_HEAVY_LOCK``. With the variable unset, which is every caller except
the intraday rescore, both context managers here do nothing, so a daily shard,
a targeted score or a local run behaves exactly as it did before this existed.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import IO

HEAVY_LOCK_ENV = "SCORECARD_HEAVY_LOCK"

# The open lock file while this process holds its turn, else None. One per
# process: `scorecard run` scores one feed per process.
_held: IO[str] | None = None


def held() -> bool:
    """Whether this process is inside its heavy section right now."""
    return _held is not None


@contextmanager
def heavy_section() -> Iterator[None]:
    """Hold the shared turn for the duration of the block.

    Re-entrant within a process, so a helper that takes the turn itself can be
    called from code that already holds it.
    """
    global _held
    path = os.environ.get(HEAVY_LOCK_ENV, "").strip()
    if not path or _held is not None:
        yield
        return
    handle = open(path, "a")  # noqa: SIM115 - held across the yield, closed below
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        _held = handle
        try:
            yield
        finally:
            _held = None
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()


@contextmanager
def outside_heavy_section() -> Iterator[None]:
    """Give the turn up for a wait that needs no memory, then take it back.

    For the realtime sampling window: a process sleeping between samples has
    no reason to keep every other feed out of its validator. A no-op when this
    process does not hold the turn.
    """
    global _held
    handle = _held
    if handle is None:
        yield
        return
    _held = None
    fcntl.flock(handle, fcntl.LOCK_UN)
    try:
        yield
    finally:
        fcntl.flock(handle, fcntl.LOCK_EX)
        _held = handle
