"""The shared turn concurrent `scorecard run` processes take at heavy work.

`flock` locks belong to an open file description, so a second `open()` of the
same path in this process contends exactly as a sibling process would. That is
what `_other_holder_can_lock` uses to read the lock's state from outside.
"""

from __future__ import annotations

import fcntl
from pathlib import Path

import pytest

from scorecard_pipeline import worklock
from scorecard_pipeline.worklock import HEAVY_LOCK_ENV, heavy_section, held, outside_heavy_section


def _other_holder_can_lock(path: Path) -> bool:
    with path.open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False
        fcntl.flock(handle, fcntl.LOCK_UN)
        return True


@pytest.fixture
def lock_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "heavy.lock"
    monkeypatch.setenv(HEAVY_LOCK_ENV, str(path))
    return path


def test_without_the_variable_both_managers_do_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every caller but the intraday rescore runs exactly as it did before."""
    monkeypatch.delenv(HEAVY_LOCK_ENV, raising=False)
    with heavy_section():
        assert not held()
        with outside_heavy_section():
            assert not held()
    assert worklock._held is None


def test_a_blank_variable_is_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(HEAVY_LOCK_ENV, "  ")
    with heavy_section():
        assert not held()


def test_the_heavy_section_excludes_every_other_holder(lock_path: Path) -> None:
    with heavy_section():
        assert held()
        assert not _other_holder_can_lock(lock_path)
    assert not held()
    assert _other_holder_can_lock(lock_path)


def test_the_heavy_section_is_reentrant(lock_path: Path) -> None:
    with heavy_section():
        with heavy_section():
            assert held()
        # The inner block must not have released the outer one's turn.
        assert held()
        assert not _other_holder_can_lock(lock_path)
    assert _other_holder_can_lock(lock_path)


def test_waiting_gives_the_turn_back_and_takes_it_again(lock_path: Path) -> None:
    with heavy_section():
        with outside_heavy_section():
            assert not held()
            assert _other_holder_can_lock(lock_path)
        assert held()
        assert not _other_holder_can_lock(lock_path)


def test_the_turn_is_released_when_the_block_raises(lock_path: Path) -> None:
    with pytest.raises(RuntimeError), heavy_section():
        raise RuntimeError("validator failed")
    assert not held()
    assert _other_holder_can_lock(lock_path)


def test_the_turn_is_retaken_when_the_wait_raises(lock_path: Path) -> None:
    """A failed download inside the wait must not leave the run scoring unlocked."""
    with heavy_section():
        with pytest.raises(OSError), outside_heavy_section():
            raise OSError("connection reset")
        assert held()
        assert not _other_holder_can_lock(lock_path)


def test_waiting_outside_a_turn_is_a_no_op(lock_path: Path) -> None:
    with outside_heavy_section():
        assert not held()
    assert _other_holder_can_lock(lock_path)


# ---------------------------------------------------------------------------
# Where a `scorecard run` takes its turn and where it gives it back


def test_scorecard_run_scores_inside_the_turn(
    lock_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import argparse

    from scorecard_pipeline import cli
    from scorecard_pipeline.config import Agency

    agency = Agency(id="unitrans", name="Unitrans", static_gtfs_url="https://u.example/g.zip")
    monkeypatch.setattr(cli, "AGENCIES", {agency.id: agency})
    during: list[bool] = []

    def fake_run(agency_id: str, *_args: object, **_kwargs: object) -> cli.RunOutcome:
        during.append(held())
        return cli.RunOutcome(path=f"{agency_id}.json", mirrored=False, cache_hit=False)

    monkeypatch.setattr(cli, "run_agency", fake_run)
    args = argparse.Namespace(
        all=False,
        agency=agency.id,
        date=None,
        force_fetch=False,
        rt_samples=1,
        rt_interval=0,
        skip_rt=True,
        skip_unchanged=False,
        outcome_out=None,
    )

    assert cli._cmd_run(args, argparse.ArgumentParser()) == 0
    assert during == [True]
    assert not held()


def test_the_download_gives_the_turn_back(lock_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Waiting on an agency's server is not heavy work; a sibling may validate meanwhile."""
    import datetime as dt
    import io
    import zipfile

    from scorecard_pipeline import fetch as fetchmod
    from scorecard_pipeline.config import Agency

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("agency.txt", "agency_name\nX")
    during: list[bool] = []

    def download(_agency: Agency, dest: Path, _limits: object) -> fetchmod.FetchProvenance:
        during.append(held() or not _other_holder_can_lock(lock_path))
        dest.write_bytes(buffer.getvalue())
        return fetchmod.FetchProvenance(
            source="origin", final_url="https://x.example/g.zip", max_attempts=1
        )

    monkeypatch.setattr(fetchmod, "_download_with_mirror_fallback", download)
    agency = Agency(id="x", name="X", static_gtfs_url="https://x.example/g.zip")

    with heavy_section():
        fetchmod.fetch_static(agency, dt.date(2026, 9, 18))
        assert held()

    assert during == [False]
