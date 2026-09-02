"""The complexity ratchet is checked against ruff instead of by hand.

`docs/lint-complexity-ratchet.md` is the register of every function over the
`max-complexity = 10` floor. Its header tells a maintainer to re-run ruff and
rewrite the table whenever a row changes, and nothing enforced that, so the
table drifted: 13 of 15 recorded numbers were wrong on 2026-08-15, and four
rows had drifted again five workdays later (#309).

A number that only moves when somebody remembers to re-run a command
understates the debt by default. A ratchet that can silently loosen is not a
ratchet, and this repo already refuses that shape elsewhere:
`test_required_status_checks.py` fails a pull-request job that is neither
required nor listed with a reason, because "there is no third option where it
quietly runs and blocks nothing".

File and line are deliberately not gated. They churn on every unrelated edit
above a function, and gating them would make the register noisy rather than
accurate. Every failure here prints the regenerated table, so a sync is a
copy-paste rather than a manual reconciliation.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "lint-complexity-ratchet.md"
PIPELINE = ROOT / "pipeline"
SRC = PIPELINE / "src"

_RUFF = re.compile(
    r"^(?P<path>[^:]+):(?P<line>\d+):\d+: C901 `(?P<name>[^`]+)` "
    r"is too complex \((?P<complexity>\d+) > \d+\)$"
)
_ROW = re.compile(
    r"^\| `(?P<name>[^`]+)` \| `(?P<location>[^`]+)` \| (?P<complexity>\d+) \| (?P<note>.*) \|$"
)
# A figure quoted in the file's own prose, e.g. "`render_site` (54)".
_PROSE_FIGURE = re.compile(r"`(?P<name>[A-Za-z_][A-Za-z0-9_]*)` \((?P<complexity>\d+)\)")


def _ruff_report() -> dict[str, tuple[str, int]]:
    """What ruff says today: function name -> (src-relative file:line, complexity).

    `--ignore-noqa` is what the file's own header tells a maintainer to run, so
    a suppressed function still appears. Without it the register would only
    ever list functions nobody had suppressed, which is the opposite of a debt
    register.
    """
    ruff = shutil.which("ruff", path=str(PIPELINE / ".venv" / "bin")) or shutil.which("ruff")
    assert ruff, "ruff is a project dev dependency and must be on PATH for this gate"
    completed = subprocess.run(  # noqa: S603 - resolved ruff binary over this checkout
        [ruff, "check", "--select", "C901", "--ignore-noqa", "--output-format", "concise", "src"],
        cwd=PIPELINE,
        capture_output=True,
        text=True,
        check=False,
    )
    report: dict[str, tuple[str, int]] = {}
    for line in completed.stdout.splitlines():
        match = _RUFF.match(line.strip())
        if match is None:
            continue
        name = match["name"]
        assert name not in report, (
            f"two functions named {name!r} are over the floor; the register keys on the "
            "name, so one of them has to be renamed before this gate can describe both"
        )
        report[name] = (f"{match['path']}:{match['line']}", int(match["complexity"]))
    assert report, f"ruff reported nothing over the floor:\n{completed.stdout}{completed.stderr}"
    return report


def _rows(doc: Path = DOC) -> list[tuple[str, str, int, str]]:
    """The tracked-exceptions table, in the order it is written."""
    rows: list[tuple[str, str, int, str]] = []
    for line in doc.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line.strip())
        if match is not None:
            rows.append((match["name"], match["location"], int(match["complexity"]), match["note"]))
    assert rows, "the tracked-exceptions table is missing or no longer parses"
    return rows


def _suppression_sites() -> dict[str, str]:
    """Every live `# noqa: C901`, as function name -> file:line."""
    sites: dict[str, str] = {}
    for path in sorted(SRC.rglob("*.py")):
        lines = path.read_text(encoding="utf-8").splitlines()
        for number, line in enumerate(lines, start=1):
            if "noqa: C901" not in line:
                continue
            match = re.search(r"def\s+([A-Za-z_][A-Za-z0-9_]*)", line)
            assert match, f"{path.name}:{number} suppresses C901 away from a def line"
            sites[match[1]] = f"{path.relative_to(SRC).as_posix()}:{number}"
    return sites


def _regenerated_table(
    report: dict[str, tuple[str, int]], rows: list[tuple[str, str, int, str]]
) -> str:
    """The table as it should read, keeping each row's existing note."""
    notes = {name: note for name, _, _, note in rows}
    ordered = sorted(report.items(), key=lambda item: (-item[1][1], item[0]))
    lines = ["| Function | File:line | Complexity | Note |", "|---|---|---|---|"]
    for name, (location, complexity) in ordered:
        note = notes.get(name, "TRACKED: write the rationale and a refactor candidate here.")
        lines.append(f"| `{name}` | `{location}` | {complexity} | {note} |")
    return "\n".join(lines)


def _sync_hint(report: dict[str, tuple[str, int]], rows: list[tuple[str, str, int, str]]) -> str:
    return (
        "\n\nRewrite the tracked-exceptions table in docs/lint-complexity-ratchet.md as:\n\n"
        + _regenerated_table(report, rows)
    )


def test_every_function_over_the_floor_has_a_row() -> None:
    report = _ruff_report()
    rows = _rows()
    missing = sorted(set(report) - {name for name, _, _, _ in rows})
    assert not missing, (
        f"over the floor with no row in the register: {', '.join(missing)}"
        + _sync_hint(report, rows)
    )


def test_every_row_still_names_a_function_over_the_floor() -> None:
    report = _ruff_report()
    rows = _rows()
    stale = sorted({name for name, _, _, _ in rows} - set(report))
    assert not stale, (
        f"listed as debt but no longer over the floor: {', '.join(stale)}. Delete the row "
        "rather than editing around it." + _sync_hint(report, rows)
    )


def _drifted(
    report: dict[str, tuple[str, int]], rows: list[tuple[str, str, int, str]]
) -> list[str]:
    """Rows whose recorded complexity disagrees with what ruff reports."""
    return [
        f"{name}: recorded {recorded}, ruff says {report[name][1]}"
        for name, _, recorded, _ in rows
        if name in report and report[name][1] != recorded
    ]


def test_every_recorded_complexity_matches_ruff() -> None:
    report = _ruff_report()
    rows = _rows()
    wrong = _drifted(report, rows)
    assert not wrong, (
        "the register understates the debt:\n  " + "\n  ".join(wrong) + _sync_hint(report, rows)
    )


def test_rows_are_in_descending_complexity_order() -> None:
    report = _ruff_report()
    rows = _rows()
    recorded = [complexity for _, _, complexity, _ in rows]
    assert recorded == sorted(recorded, reverse=True), (
        "the register is out of its own declared sort order" + _sync_hint(report, rows)
    )


def test_every_suppression_site_has_a_row() -> None:
    """The file's stated rule: no new `# noqa: C901` without a row."""
    report = _ruff_report()
    rows = _rows()
    listed = {name for name, _, _, _ in rows}
    unlisted = sorted(name for name in _suppression_sites() if name not in listed)
    assert not unlisted, (
        f"suppressed with no row in the register: {', '.join(unlisted)}" + _sync_hint(report, rows)
    )


def test_prose_figures_agree_with_the_table() -> None:
    """A number quoted in the file's own prose drifts the same way a row does."""
    report = _ruff_report()
    rows = _rows()
    body = DOC.read_text(encoding="utf-8")
    prose = "\n".join(line for line in body.splitlines() if not _ROW.match(line.strip()))
    wrong = [
        f"prose says {name} is {int(match['complexity'])}, ruff says {report[name][1]}"
        for match in _PROSE_FIGURE.finditer(prose)
        if (name := match["name"]) in report and report[name][1] != int(match["complexity"])
    ]
    assert not wrong, "\n  ".join(["stale figures in the prose:", *wrong]) + _sync_hint(
        report, rows
    )


def _mutated(tmp_path: Path, old: str, new: str) -> Path:
    """A copy of the real register with one edit, for the self-tests below."""
    body = DOC.read_text(encoding="utf-8")
    assert body.count(old) == 1, f"{old!r} is not a unique line of the register"
    copy = tmp_path / "ratchet.md"
    copy.write_text(body.replace(old, new), encoding="utf-8")
    return copy


def test_a_drifted_number_is_reported(tmp_path: Path) -> None:
    """Proof the comparison bites, against a real edited register."""
    report = _ruff_report()
    name, (_, complexity) = max(report.items(), key=lambda item: item[1][1])
    row = next(
        line for line in DOC.read_text(encoding="utf-8").splitlines() if f"| `{name}` |" in line
    )
    drifted = _mutated(tmp_path, row, row.replace(f"| {complexity} |", f"| {complexity - 1} |", 1))
    assert _drifted(report, _rows(drifted)) == [
        f"{name}: recorded {complexity - 1}, ruff says {complexity}"
    ]


def test_a_deleted_row_is_reported(tmp_path: Path) -> None:
    report = _ruff_report()
    name = min(report, key=lambda key: report[key][1])
    row = next(
        line for line in DOC.read_text(encoding="utf-8").splitlines() if f"| `{name}` |" in line
    )
    without = _mutated(tmp_path, row + "\n", "")
    listed = {listed_name for listed_name, _, _, _ in _rows(without)}
    assert sorted(set(report) - listed) == [name]


def test_an_out_of_order_table_is_reported(tmp_path: Path) -> None:
    lines = DOC.read_text(encoding="utf-8").splitlines()
    rows = [line for line in lines if _ROW.match(line.strip())]
    swapped = _mutated(tmp_path, rows[0] + "\n" + rows[1], rows[1] + "\n" + rows[0])
    recorded = [complexity for _, _, complexity, _ in _rows(swapped)]
    assert recorded != sorted(recorded, reverse=True)


def test_the_regenerated_table_reproduces_a_synced_file() -> None:
    """The hint the failures print is the table itself, not an approximation."""
    report = _ruff_report()
    rows = _rows()
    regenerated = _regenerated_table(report, rows)
    for name, _, complexity, _ in rows:
        if name in report:
            assert f"| `{name}` | `{report[name][0]}` | {complexity} |" in regenerated
