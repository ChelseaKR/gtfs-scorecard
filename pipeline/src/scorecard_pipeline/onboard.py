"""Self-serve instant onboarding: score a feed from a GitHub issue.

The registry submission flow (submit.html) is curated and asks a person to merge
a pull request before a feed is scored. This is the other half: a rider, agency
staffer, or liaison who just wants to see a grade now, without waiting for a
review or learning what YAML is.

The flow is serverless by way of GitHub Actions, the same compute the daily run
uses. A web page deep-links to a pre-filled issue form; a workflow scores the
submitted URL with ``scorecard try`` and posts the scorecard back as a comment.
This module owns the two pure pieces that flow needs: reading the feed URL and
name out of the rendered issue form, and rendering the scored artifact as a
plain-language comment. The issue body is untrusted input, so the parser only
accepts an http(s) URL and never executes anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# GitHub renders an issue *form* as markdown: each field becomes a "### Label"
# heading followed by the value (or "_No response_" when left blank). We read the
# two fields the score-a-feed form defines by their labels.
_FEED_URL_LABEL = "GTFS Schedule URL"
_NAME_LABEL = "Agency name"
_NO_RESPONSE = "_No response_"

_SECTION = re.compile(r"^###\s+(?P<label>.+?)\s*$", re.MULTILINE)
_URL_RE = re.compile(r"https?://[^\s<>\")']+", re.IGNORECASE)


def _require_dict(value: object, field: str) -> dict[str, object]:
    """Narrow a JSON artifact field to a dict, raising if the shape is wrong.

    Extracted so each call site in :func:`render_comment` is one line instead
    of an inline branch, keeping that function's cyclomatic complexity down
    (CODE-QUALITY-STANDARD CQ-05) rather than relying on ``assert`` (S101:
    stripped under ``python -O``, so an explicit raise is used instead).
    """
    if not isinstance(value, dict):
        raise TypeError(f"scorecard artifact {field!r} must be a dict")
    return value


@dataclass(frozen=True)
class ScoreRequest:
    url: str
    name: str


def _sections(body: str) -> dict[str, str]:
    """Split a rendered issue-form body into {label: value}."""
    out: dict[str, str] = {}
    matches = list(_SECTION.finditer(body))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        out[m.group("label").strip()] = body[start:end].strip()
    return out


def parse_issue_form(body: str) -> ScoreRequest | None:
    """Read a feed URL and agency name from a score-a-feed issue body.

    Returns None when no usable http(s) URL is present, so the workflow can leave
    a helpful comment instead of scoring nothing. The name falls back to a generic
    label rather than failing, since the URL is the only thing truly required.
    The URL is taken from the form's field when present, otherwise the first
    http(s) URL anywhere in the body, so a free-text issue still works.
    """
    sections = _sections(body)

    url_field = sections.get(_FEED_URL_LABEL, "")
    url_match = _URL_RE.search(url_field) or _URL_RE.search(body)
    if url_match is None:
        return None
    url = url_match.group(0).rstrip(".,)")

    # Collapse the name to a single line: it is shown in the scorecard and also
    # flows into a CI step output, where a stray newline could inject a line.
    name = " ".join(sections.get(_NAME_LABEL, "").split())
    if not name or name == _NO_RESPONSE:
        name = "this feed"
    return ScoreRequest(url=url, name=name)


_GRADE_BLURB = {
    "A": "This feed is in strong shape.",
    "B": "This feed is in good shape, with a few things worth tightening.",
    "C": "This feed works, and a handful of fixes would lift it.",
    "D": "This feed has gaps that affect riders. The fixes below are the place to start.",
    "F": "This feed needs attention before riders can rely on it.",
}

_CAT_LABELS = {
    "correctness": "Correctness",
    "freshness": "Freshness",
    "completeness": "Rider experience",
    "realtime": "Realtime",
}


def render_comment(artifact: dict[str, object], *, page_url: str | None = None) -> str:
    """Render a scored artifact as a GitHub issue comment in markdown.

    Leads with the grade, then the category scores, then the top fixes in plain
    language. Mirrors the agency page's framing: fixes, never failures. A feed
    with no realtime shows that category neutrally rather than as a zero.
    """
    overall = _require_dict(artifact.get("overall", {}), "overall")
    grade = str(overall.get("grade", "?"))
    score = overall.get("score", "?")
    agency = _require_dict(artifact.get("agency", {}), "agency")
    name = str(agency.get("name", "this feed"))

    lines = [
        f"## GTFS Scorecard: {name}",
        "",
        f"**Grade {grade}** ({score}/100). {_GRADE_BLURB.get(grade, '')}".rstrip(),
        "",
        "| Category | Score |",
        "| --- | --- |",
    ]
    categories = _require_dict(artifact.get("categories", {}), "categories")
    for key, label in _CAT_LABELS.items():
        cat = categories.get(key, {})
        if not isinstance(cat, dict):
            continue
        status = cat.get("status")
        if status == "measured":
            lines.append(f"| {label} | {cat.get('score', '?')} |")
        else:
            lines.append(f"| {label} | not yet published |")
    lines.append("")

    fixes = artifact.get("top_fixes", [])
    if not isinstance(fixes, list):
        raise TypeError("scorecard artifact 'top_fixes' must be a list")
    if fixes:
        lines.append("### Top things to fix")
        lines.append("")
        for fix in fixes:
            if not isinstance(fix, dict):
                continue
            what = str(fix.get("fix") or fix.get("what") or "").strip()
            effort = str(fix.get("effort") or "").strip()
            tail = f" _{effort}_" if effort else ""
            lines.append(f"- {what}{tail}")
        lines.append("")
    else:
        lines.append("No score-moving fixes stood out. Nice work.")
        lines.append("")

    if page_url:
        lines.append(f"See the full scorecard: {page_url}")
        lines.append("")
    lines.append(
        "This is a one-off check. To track this feed over time, "
        "[add your agency](https://gtfsscorecard.org/submit.html)."
    )
    return "\n".join(lines) + "\n"
