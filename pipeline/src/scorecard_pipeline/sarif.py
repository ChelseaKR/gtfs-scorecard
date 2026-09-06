"""SARIF 2.1.0 output, so validator notices land in a pull request's Security tab.

The Action prints one ``::error`` line and a job summary. A maintainer who keeps
GTFS in git gets no per-file annotation from that, and the sibling
``tods-validate`` already ships ``--format sarif`` for the same audience. SARIF
is a static file, so this adds no service and stays deterministic and offline.

Two things about this file are deliberate and should survive editing.

**A zero-result SARIF is not a clean feed.** SARIF has no shape that says "I did
not run"; an empty ``results`` array renders in GitHub's UI exactly like a feed
with nothing wrong. So a run that could not read the feed emits
``executionSuccessful: false`` and a ``toolExecutionNotifications`` entry
carrying the reason (:func:`unreadable_feed_sarif`), and never an empty
successful run. This is the same refusal ``UnreadableValidatorReportError``
makes on the scoring side, in the one output format that would otherwise present
the absence as a pass.

**A sampled count is labelled as sampled.** The gtfs-validator reports at most a
handful of example rows per notice code, and ``validate.parse_report_data`` keeps
five of them. One SARIF result is emitted per notice *code*, carrying the true
total in its message and as many locations as there are samples. Emitting one
result per sampled row would publish "5 problems" about a code with 23
instances, which is an undercount wearing the clothes of a complete count.
"""

from __future__ import annotations

import hashlib
from typing import Any

from .rule_links import rule_link_for
from .validate import NoticeGroup, ValidationReport

__all__ = [
    "SARIF_SCHEMA_URI",
    "SARIF_VERSION",
    "build_sarif",
    "unreadable_feed_sarif",
]

SARIF_VERSION = "2.1.0"
SARIF_SCHEMA_URI = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json"

TOOL_NAME = "GTFS Scorecard"
TOOL_INFORMATION_URI = "https://gtfsscorecard.org/"

#: gtfs-validator severity -> SARIF level. INFO maps to ``note`` rather than
#: being dropped: a notice we chose not to show is still a notice the validator
#: raised, and silently discarding it would understate the feed.
_LEVELS = {"ERROR": "error", "WARNING": "warning", "INFO": "note"}

#: Keys the gtfs-validator uses inside a sample notice for the file, the row,
#: and the field. Read tolerantly: the sample payload's shape varies per notice
#: type and an unknown key must produce a file-level result, never a wrong one.
_FILE_KEYS = ("filename", "fileName")
_ROW_KEYS = ("csvRowNumber", "rowNumber")
_FIELD_KEYS = ("fieldName", "columnName")


def _first(sample: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        value = sample.get(key)
        if value not in (None, ""):
            return value
    return None


def _artifact_uri(filename: str, base: str) -> str:
    """Where the feed's member sits in the repository being annotated.

    ``base`` is the feed's directory inside the checkout ("gtfs/" for a feed
    committed under gtfs/). A zip has no base and the member path stands alone.
    """
    prefix = base.strip("/")
    return f"{prefix}/{filename}" if prefix else filename


def _location(sample: dict[str, Any], base: str) -> dict[str, Any] | None:
    """One SARIF location from one sample notice, or None when it names no file.

    A row without a file is not placeable, so it produces no location rather
    than a guessed one. The result still exists; it simply carries no location,
    and its message says the validator gave no file context.
    """
    filename = _first(sample, _FILE_KEYS)
    if not filename:
        return None
    location: dict[str, Any] = {
        "physicalLocation": {"artifactLocation": {"uri": _artifact_uri(str(filename), base)}}
    }
    row = _first(sample, _ROW_KEYS)
    if isinstance(row, (int, float)) and not isinstance(row, bool) and int(row) > 0:
        # GTFS csvRowNumber counts the header as row 1, which is also how a text
        # editor and GitHub's annotation gutter count, so it maps straight over.
        location["physicalLocation"]["region"] = {"startLine": int(row)}
    return location


def _fingerprint(group: NoticeGroup, base: str) -> str:
    """A stable identity for this finding, so two runs dedupe rather than double.

    Built from the code, the first sample's file and field, and its row —
    deliberately not from the instance count, which moves as the feed is worked
    on. A fingerprint that changed when the count changed would show every
    partially-fixed finding as a brand-new alert.
    """
    sample = group.sample_notices[0] if group.sample_notices else {}
    filename = _first(sample, _FILE_KEYS) or ""
    field = _first(sample, _FIELD_KEYS) or ""
    row = _first(sample, _ROW_KEYS)
    row_text = str(int(row)) if isinstance(row, (int, float)) and not isinstance(row, bool) else ""
    parts = "\0".join(
        [group.code, _artifact_uri(str(filename), base) if filename else "", str(field), row_text]
    )
    return hashlib.sha256(parts.encode()).hexdigest()[:16]


def _message(group: NoticeGroup, what: str) -> str:
    """The result message: what it is, how many, and how many we can point at."""
    shown = sum(1 for sample in group.sample_notices if _first(sample, _FILE_KEYS))
    instances = "1 instance" if group.total == 1 else f"{group.total:,} instances"
    head = f"{what} ({instances})" if what else f"{group.code} ({instances})"
    if shown == 0:
        return (
            f"{head}. The validator reported no file for this notice, so this result "
            f"is not attached to a line."
        )
    if shown < group.total:
        return (
            f"{head}. The validator samples its examples, so {shown} of them are "
            f"located below; the rest are not listed anywhere."
        )
    return head


def _rule(group: NoticeGroup, what: str, why: str) -> dict[str, Any]:
    link = rule_link_for(group.code)
    rule: dict[str, Any] = {
        "id": group.code,
        "name": group.code,
        "shortDescription": {"text": what or group.code},
        "defaultConfiguration": {"level": _LEVELS.get(group.severity, "note")},
    }
    if why:
        rule["fullDescription"] = {"text": why}
    if link is not None:
        rule["helpUri"] = link.url
        rule["properties"] = {"authority": link.authority}
    return rule


def _driver(rules: list[dict[str, Any]], version: str) -> dict[str, Any]:
    return {
        "name": TOOL_NAME,
        "informationUri": TOOL_INFORMATION_URI,
        "version": version,
        "rules": rules,
    }


def build_sarif(
    report: ValidationReport,
    *,
    findings: dict[str, dict[str, str]] | None = None,
    base: str = "",
) -> dict[str, Any]:
    """A SARIF 2.1.0 log for one validator report.

    One result per notice code, carrying the true instance total and as many
    locations as the validator sampled. ``findings`` supplies the scorecard's
    plain-language ``what``/``why`` per code, so the Security tab says the same
    thing the scorecard page says rather than repeating a rule id.
    """
    lookup = findings or {}
    rules: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for group in report.notices:
        copy = lookup.get(group.code, {})
        what, why = copy.get("what", ""), copy.get("why", "")
        rules.append(_rule(group, what, why))
        locations = [
            location
            for location in (_location(sample, base) for sample in group.sample_notices)
            if location is not None
        ]
        result: dict[str, Any] = {
            "ruleId": group.code,
            "level": _LEVELS.get(group.severity, "note"),
            "message": {"text": _message(group, what)},
            "partialFingerprints": {"gtfsScorecardNotice/v1": _fingerprint(group, base)},
            "properties": {"instanceCount": group.total, "severity": group.severity},
        }
        if locations:
            result["locations"] = locations
        results.append(result)
    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {"driver": _driver(rules, report.validator_version)},
                "invocations": [{"executionSuccessful": True}],
                "results": results,
            }
        ],
    }


def unreadable_feed_sarif(reason: str, *, version: str = "unknown") -> dict[str, Any]:
    """A SARIF log for a feed that could not be scored at all.

    Zero results **and** ``executionSuccessful: false`` with the reason attached,
    because in SARIF those are the only two things that separate "nothing is
    wrong with this feed" from "nobody read this feed". Uploading the first
    shape for the second would put a green Security tab on a feed that was never
    opened.
    """
    return {
        "$schema": SARIF_SCHEMA_URI,
        "version": SARIF_VERSION,
        "runs": [
            {
                "tool": {"driver": _driver([], version)},
                "invocations": [
                    {
                        "executionSuccessful": False,
                        "toolExecutionNotifications": [
                            {
                                "level": "error",
                                "message": {
                                    "text": (
                                        f"The feed could not be scored, so no notice in this "
                                        f"file describes it and the absence of results means "
                                        f"nothing: {reason}"
                                    )
                                },
                            }
                        ],
                    }
                ],
                "results": [],
            }
        ],
    }
