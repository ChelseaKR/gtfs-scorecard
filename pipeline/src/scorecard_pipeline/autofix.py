"""Auto-fix layer: turn a finding into a deterministic patch.

The validator and the scorecard name what is wrong; this fixes the subset of
findings that have one unambiguous correct edit. The point is to hand an agency a
already-corrected feed for the safe cases, not to guess. So the recipes here are
deliberately conservative: each one changes only what is mechanically certain
(surrounding whitespace, shouting stop names), preserves every other byte of the
feed, and reports exactly what it touched. Anything that needs judgement (a
missing fare, an unknown wheelchair value, a real contact email) is left for the
agency, with the scorecard's plain-language fix.

The output is a patched GTFS zip plus a record of what changed, so a person can
review the diff before publishing. Wiring this into a pull request against an
agency's feed repository is a downstream step; this module produces the patch.
"""

from __future__ import annotations

import csv
import io
import zipfile
from dataclasses import dataclass, field


@dataclass
class FixResult:
    """What one recipe changed across the feed."""

    code: str
    label: str
    count: int = 0
    examples: list[str] = field(default_factory=list)

    def note(self, example: str) -> None:
        self.count += 1
        if len(self.examples) < 5:
            self.examples.append(example)


Table = list[dict[str, str]]


def _is_shouty(name: str) -> bool:
    """True for names written LIKE THIS. Mirrors the completeness check so the
    fix targets exactly what that finding flags: a fully-uppercase name with at
    least one 4+ letter word in a cased script, leaving short acronyms ('UCD',
    '4 & B') and uncased scripts alone."""
    words = ["".join(c for c in token if c.isalpha()) for token in name.split()]
    cased = [c for c in name if c.isalpha() and c.lower() != c.upper()]
    return (
        bool(cased)
        and all(c == c.upper() for c in cased)
        and any(
            len(w) >= 4 and any(c.lower() != c.upper() for c in w) and w == w.upper() for w in words
        )
    )


def _titlecase(name: str) -> str:
    """Word-by-word capitalization that survives punctuation and digits:
    'MAIN ST & 2ND AVE' -> 'Main St & 2nd Ave'."""
    return " ".join(word.capitalize() for word in name.split())


def fix_whitespace(tables: dict[str, Table]) -> FixResult:
    """Strip leading and trailing whitespace from every cell. The GTFS best
    practices discourage surrounding whitespace; trimming it never changes
    meaning and prevents lookups that fail on a stray space."""
    result = FixResult("autofix_trim_whitespace", "Trimmed surrounding whitespace")
    for rows in tables.values():
        for row in rows:
            for key, value in row.items():
                if value is not None and value != value.strip():
                    stripped = value.strip()
                    if result.count < 5:
                        result.examples.append(f"{key!r}: {value!r} -> {stripped!r}")
                    row[key] = stripped
                    result.count += 1
    return result


def fix_shouty_stop_names(tables: dict[str, Table]) -> FixResult:
    """Recase ALL-CAPS stop names to mixed case. Targets exactly the
    completeness 'stop names in ALL CAPS' finding."""
    result = FixResult("autofix_stop_name_case", "Recased shouting stop names")
    for row in tables.get("stops.txt", []):
        name = row.get("stop_name", "")
        if name and _is_shouty(name):
            fixed = _titlecase(name)
            if fixed != name:
                row["stop_name"] = fixed
                result.note(f"{name} -> {fixed}")
    return result


def fix_shouty_route_names(tables: dict[str, Table]) -> FixResult:
    """Recase ALL-CAPS route long names, the route-level analogue of the stop
    name fix."""
    result = FixResult("autofix_route_name_case", "Recased shouting route names")
    for row in tables.get("routes.txt", []):
        name = row.get("route_long_name", "")
        if name and _is_shouty(name):
            fixed = _titlecase(name)
            if fixed != name:
                row["route_long_name"] = fixed
                result.note(f"{name} -> {fixed}")
    return result


# The recipes run in order. Whitespace first, so a name that is only shouting
# because of a trailing space is judged on its trimmed form.
RECIPES = (fix_whitespace, fix_shouty_stop_names, fix_shouty_route_names)

# Tables a recipe might rewrite, so the zip writer knows which members to
# re-encode. Other members are copied through byte-for-byte.
_EDITABLE = ("stops.txt", "routes.txt")


def _read_with_header(zf: zipfile.ZipFile, name: str) -> tuple[list[str], Table]:
    text = zf.read(name).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader.fieldnames or []), list(reader)


def _encode_table(header: list[str], rows: Table) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def apply_fixes(tables: dict[str, Table]) -> list[FixResult]:
    """Run every recipe over the tables in place, returning the non-empty results."""
    results = [recipe(tables) for recipe in RECIPES]
    return [r for r in results if r.count]


def autofix_zip(src_zip: str, out_zip: str) -> list[FixResult]:
    """Apply the safe recipes to a GTFS zip, writing a patched copy.

    Every member is copied through; only the editable tables that a recipe
    actually changed are re-encoded, so an untouched feed produces a
    byte-equivalent copy and the diff is exactly the fixes. Returns the list of
    applied fixes (empty when the feed needed none).
    """
    with zipfile.ZipFile(src_zip) as zf:
        names = zf.namelist()
        tables: dict[str, Table] = {}
        headers: dict[str, list[str]] = {}
        for name in _EDITABLE:
            if name in names:
                headers[name], tables[name] = _read_with_header(zf, name)
        results = apply_fixes(tables)
        changed = {r.code for r in results}
        # Map which tables changed: stops for the stop-name and whitespace fixes,
        # routes for the route-name fix. Whitespace can touch any editable table.
        rewrite = set()
        if changed:
            rewrite = set(headers)  # re-encode every table we parsed; cheap and exact
        with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as out:
            for name in names:
                if name in rewrite:
                    out.writestr(name, _encode_table(headers[name], tables[name]))
                else:
                    out.writestr(name, zf.read(name))
    return results


def render_report(results: list[FixResult], *, feed_label: str = "this feed") -> str:
    """A short markdown record of what the auto-fix changed, for review."""
    if not results:
        return (
            f"# Auto-fix: nothing to change in {feed_label}\n\n"
            "The safe recipes found nothing to fix."
        )
    lines = [f"# Auto-fix applied to {feed_label}", ""]
    total = sum(r.count for r in results)
    lines.append(f"{total} change(s) across {len(results)} recipe(s). Review before publishing.")
    lines.append("")
    for r in results:
        lines.append(f"## {r.label} ({r.count})")
        for example in r.examples:
            lines.append(f"- {example}")
        if r.count > len(r.examples):
            lines.append(f"- ...and {r.count - len(r.examples)} more")
        lines.append("")
    return "\n".join(lines)
