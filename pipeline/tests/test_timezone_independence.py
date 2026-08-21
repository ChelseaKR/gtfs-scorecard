"""Stored and graded dates must come from UTC, never the runner's local zone.

`render_site` once computed `catalog.json`'s Google gate with `dt.date.today()`
while the rest of the render worked from a frozen UTC instant. A machine behind
UTC published a different verdict than the page rendered beside it, and the
golden suite went red for part of every day. That one site is pinned by
`test_render_site.py::test_catalog_google_gate_follows_the_frozen_instant_not_the_local_clock`;
these tests pin the rest of the pipeline, where the same read fed
`snapshot_date`, registry validation, and the expiry comparisons.

About the zone pair: Pacific/Kiritimati (UTC+14) and Pacific/Midway (UTC-11)
are 25 hours apart, so at no instant can both share UTC's calendar date. Running
an assertion under both therefore catches a local-clock read at every hour,
instead of only during the window where one zone happens to disagree.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import time
import tokenize
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.config import utc_today

# UTC+14 and UTC-11. See the module docstring for why the pair, not one zone.
EXTREME_ZONES = ("Pacific/Kiritimati", "Pacific/Midway")

PIPELINE_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    not hasattr(time, "tzset"), reason="switching the process zone needs a POSIX time.tzset"
)


def expected_utc_date() -> dt.date:
    """The oracle, spelled out rather than borrowed from the code under test.

    Asserting against `utc_today()` would compare a broken implementation with
    itself; `dt.datetime.now(dt.UTC)` cannot pick up the process zone whatever
    TZ says.
    """
    return dt.datetime.now(dt.UTC).date()


@contextlib.contextmanager
def local_zone(name: str) -> Iterator[None]:
    """Run the block as though the machine sat in `name`."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = name
    time.tzset()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = previous
        time.tzset()


def test_utc_today_reads_the_same_date_in_every_zone() -> None:
    seen = {}
    for zone in EXTREME_ZONES:
        with local_zone(zone):
            seen[zone] = (utc_today(), dt.date.today())

    assert {utc for utc, _ in seen.values()} == {expected_utc_date()}, seen
    # And the trap was armed: reading the machine's clock instead of UTC would
    # have answered differently in at least one of these two zones, whatever
    # the hour. Without this line the test above would pass on a broken build.
    assert any(local != utc for utc, local in seen.values()), seen


# --------------------------------------------------------------- registry


VALID_ENTRY: dict[str, Any] = {
    "id": "demo",
    "name": "Demo Transit",
    "static_gtfs_url": "https://example.org/gtfs.zip",
}
REUSE_EVIDENCE: dict[str, Any] = {
    "decision": "approved",
    "source_kind": "official_portal",
    "provider_source_url": "https://data.example.org/datasets/demo",
    "terms_url": "https://data.example.org/terms",
    "scope": ["gtfs_schedule"],
    "attribution": "Demo Transit Authority",
    "reviewed_by": "Registry curator",
    "reviewed_on": "2026-07-16",
    "identity_reviewed": True,
}


def _entry_reviewed_on(day: dt.date) -> dict[str, Any]:
    evidence = {**REUSE_EVIDENCE, "reviewed_on": day.isoformat()}
    return {"agencies": [{**VALID_ENTRY, "reuse_evidence": evidence}]}


def test_reviewed_on_is_judged_against_utc_not_the_runner_zone() -> None:
    """A review dated today must load, and one dated tomorrow must not, anywhere.

    Both halves matter. On a machine behind UTC the old local read rejected a
    review a curator had legitimately filed today; on a machine ahead of it the
    same read accepted one dated a day in the future. One of the two zones below
    exercises one of those at any hour.
    """
    from scorecard_pipeline.agencies import AgencyConfigError, parse_agencies

    today = expected_utc_date()
    for zone in EXTREME_ZONES:
        with local_zone(zone):
            (agency,) = parse_agencies(_entry_reviewed_on(today))
            assert agency.reuse_evidence is not None
            with pytest.raises(AgencyConfigError, match="must not be in the future"):
                parse_agencies(_entry_reviewed_on(today + dt.timedelta(days=1)))


# --------------------------------------------------------------- published dates


def test_effort_calibration_generated_date_is_utc(isolated_repo_root: Path) -> None:
    from scorecard_pipeline.publish import _write_calibration

    path = isolated_repo_root / "data" / "effort-calibration.json"
    for zone in EXTREME_ZONES:
        with local_zone(zone):
            _write_calibration({})
            assert json.loads(path.read_text())["generated"] == expected_utc_date().isoformat()


def test_alert_digest_as_of_defaults_to_utc(isolated_repo_root: Path) -> None:
    from scorecard_pipeline.alerts import build_digest

    for zone in EXTREME_ZONES:
        with local_zone(zone):
            assert build_digest().as_of == expected_utc_date()


def test_portfolio_digest_as_of_defaults_to_utc(isolated_repo_root: Path) -> None:
    from scorecard_pipeline.portfolio_digest import build_portfolio_digest
    from scorecard_pipeline.rollups import Rollup

    rollup = Rollup(id="demo", name="Demo cohort", member_ids=("demo",))
    for zone in EXTREME_ZONES:
        with local_zone(zone):
            assert build_portfolio_digest(rollup).as_of == expected_utc_date()


# --------------------------------------------------------------- CLI defaults

# Every subcommand whose --date default becomes a stored snapshot date or the
# "today" a freshness/expiry comparison is graded against. No workflow passes
# --date, so these defaults are what the daily build actually runs on.
DATE_DEFAULT_COMMANDS: list[list[str]] = [
    ["run", "--all"],
    ["try", "https://example.org/gtfs.zip"],
    ["canary", "--candidate-version", "8.1.0"],
    ["freshness-sweep"],
    ["alerts"],
    ["notify"],
    ["portfolio-digest"],
    ["coverage-check"],
    ["campaign", "--rollup", "demo", "--kind", "calendar-renewal"],
]

# The routing-QA commands take the service date as an ISO string, not a date.
ISO_DATE_DEFAULT_COMMANDS: list[list[str]] = [
    ["otp", "--base", "https://otp.example.org", "--feed", "feed.zip"],
    ["otp-batch"],
]


@pytest.mark.parametrize("argv", DATE_DEFAULT_COMMANDS, ids=lambda argv: argv[0])
def test_cli_date_default_is_utc(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    from scorecard_pipeline import cli

    assert _parsed_date(cli, argv, monkeypatch) == [expected_utc_date()] * len(EXTREME_ZONES)


@pytest.mark.parametrize("argv", ISO_DATE_DEFAULT_COMMANDS, ids=lambda argv: argv[0])
def test_cli_iso_date_default_is_utc(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    from scorecard_pipeline import cli

    expected = expected_utc_date().isoformat()
    assert _parsed_date(cli, argv, monkeypatch) == [expected] * len(EXTREME_ZONES)


def _parsed_date(cli: Any, argv: list[str], monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """Parse `argv` once per zone and return the --date argparse settled on.

    Dispatch is stubbed out: the parser is built inside `main`, and the default
    is evaluated as the parser is built, so this is the narrowest way to read
    back what a real invocation would have used.
    """
    seen: list[Any] = []

    def capture(args: Any, parser: Any) -> int:
        seen.append(args.date)
        return 0

    monkeypatch.setattr(cli, "_dispatch", capture)
    for zone in EXTREME_ZONES:
        with local_zone(zone):
            assert cli.main(argv) == 0
    return seen


# --------------------------------------------------------------- source guard


def _executable_source(path: Path) -> str:
    """The file's code with comments and string literals dropped.

    Prose about the bug (this module, `config.utc_today`, the note left in
    `render_site`) must not read as a fresh occurrence of it.
    """
    lines = []
    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type in {tokenize.COMMENT, tokenize.STRING}:
                continue
            lines.append(token.string if token.type != tokenize.NL else "\n")
    return "".join(lines)


BANNED_CLOCK_READS = (
    "date.today()",  # the machine's zone, not UTC
    "datetime.utcnow()",  # naive, and deprecated since 3.12
    ".now()",  # naive local time; pass dt.UTC
)


# Directories that hold code this repository did not write: the Lambda packaging
# step vendors its dependencies into `infra/submit/build/`, and a virtualenv or a
# byte-cache can appear anywhere. All three are gitignored, so CI never sees
# them, and the guard was failing only on the laptop of whoever had run the build
# last. It named `urllib3/connection.py` when it did, which is not a file anyone
# here can fix.
NOT_OUR_SOURCE = frozenset({"build", "dist", "__pycache__", ".venv", "venv", "site-packages"})


def _is_our_source(path: Path) -> bool:
    return NOT_OUR_SOURCE.isdisjoint(path.parts)


def test_no_pipeline_module_reads_the_machines_local_clock() -> None:
    """Keep the fix from being undone one convenient one-liner at a time.

    `dt.datetime.now(dt.UTC)` and `dt.datetime.fromtimestamp(epoch, tz)` are
    both fine and are how the pipeline already reads time; these three spellings
    silently pick up whatever zone the process happens to be running in.

    `infra/` is in scope because the Lambda and queue workers write the same
    artifacts as the CI matrix. AWS runtimes default to UTC, which is exactly
    what made this class of bug invisible until somebody ran the same code on a
    laptop. Build output under `infra/` is not in scope: see `NOT_OUR_SOURCE`.
    """
    offenders = []
    sources = sorted((PIPELINE_ROOT / "src").rglob("*.py"))
    sources += sorted((PIPELINE_ROOT / "scripts").rglob("*.py"))
    sources += sorted((PIPELINE_ROOT.parent / "infra").rglob("*.py"))
    sources = [path for path in sources if _is_our_source(path)]
    assert sources, "the guard found no sources to scan"
    for path in sources:
        code = _executable_source(path)
        for banned in BANNED_CLOCK_READS:
            if banned in code:
                offenders.append(f"{path.relative_to(PIPELINE_ROOT.parent)}: {banned}")

    assert offenders == [], (
        "these read the runner's local clock; use scorecard_pipeline.config.utc_today() "
        "or dt.datetime.now(dt.UTC): " + ", ".join(offenders)
    )


def test_source_guard_would_catch_a_reintroduced_local_read(tmp_path: Path) -> None:
    """The guard above passes on an empty search as readily as on a clean tree."""
    sample = tmp_path / "sample.py"
    sample.write_text(
        '"""A docstring mentioning dt.date.today() must not trip the guard."""\n'
        "import datetime as dt\n"
        "\n"
        "GOOD = dt.datetime.now(dt.UTC).date()  # dt.date.today() in a comment\n"
    )
    assert not any(banned in _executable_source(sample) for banned in BANNED_CLOCK_READS)

    sample.write_text("import datetime as dt\n\nBAD = dt.date.today()\n")
    code = _executable_source(sample)
    assert [banned for banned in BANNED_CLOCK_READS if banned in code] == ["date.today()"]


def test_the_guard_skips_vendored_build_output_but_not_our_own_infra_code() -> None:
    """A vendored dependency under `infra/submit/build/` is not ours to fix.

    The gitignored Lambda bundle put `urllib3/connection.py` in the offender
    list, so `make verify` failed for anyone who had packaged the submit
    function locally while CI, checking out a clean tree, stayed green.
    """
    root = PIPELINE_ROOT.parent
    assert _is_our_source(root / "infra" / "submit" / "handler.py")
    assert not _is_our_source(root / "infra" / "submit" / "build" / "urllib3" / "connection.py")
    assert not _is_our_source(root / "pipeline" / "src" / "__pycache__" / "cached.py")
    assert not _is_our_source(root / "pipeline" / ".venv" / "lib" / "somedep.py")
