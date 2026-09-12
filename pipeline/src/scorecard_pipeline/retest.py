"""Retest a new export against a vendor evidence packet (#366).

``scorecard evidence-packet`` writes a work order: each prioritized finding,
with an acceptance test expecting the notice to be absent once the feed is
rescored under the same producer contract. Nothing executed that test. This
module is the comparator. Given a packet and the artifact produced by scoring
a new export through the ``scorecard try`` path, it says for each packet
finding whether the notice was cleared, is still present, or cannot be
compared.

A retest record is deliberately narrow. It is not a closure receipt, it does
not establish that the feed is the agency's canonical export or who published
it, it attributes no cause, and it publishes nothing.

Three rules carry the honesty of the verdicts.

* **Cleared means absent, not a count of zero.** A category can raise a notice
  whose count is 0: "0 of 0 stops don't say whether a wheelchair user can
  board there" is raised, with a deduction, for an archive whose stops table
  is empty. Reading the count would call that notice cleared when the very
  same bytes are retested. So a notice is cleared only when its code is not in
  the retest category's findings at all, and "still present" carries whatever
  count the notice reports, zero included.
* **The producer contract decides whether anything is comparable.** If the
  rubric, the scoring profile, the profile's rubric version, the validator
  version or the reader archive profile differs from the packet's, every
  finding is non-comparable and none is reported cleared.
* **Whether a finding's own category was measured decides that finding only.**
  The measured-category set moves the overall score's denominator, not the
  instance count of a notice inside one measured category, and an ad-hoc
  retest never samples realtime. Requiring the whole set to match would make
  every packet from an agency with realtime unretestable, so a finding whose
  category was not measured in the retest is non-comparable on its own, and
  any difference in the set is recorded in the record rather than hidden.
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

from .comparisons import producer_contract
from .evidence_packet import PACKET_SCHEMA_VERSION, acceptance_contract, observe_notice

RETEST_SCHEMA_VERSION = "1.0"
RECORD_TYPE = "gtfs-scorecard-retest"

CLEARED = "cleared"
STILL_PRESENT = "still_present"
NON_COMPARABLE = "non_comparable"
ALL_CLEARED = "all_cleared"

# The first five producer-contract elements, named in `producer_contract` order.
# The sixth, the measured-category set, is compared per finding (module docstring).
CONTRACT_FIELDS = (
    "rubric_version",
    "scoring_profile_id",
    "scoring_profile_rubric_version",
    "validator_version",
    "reader_archive_profile",
)

EXIT_CODES = {ALL_CLEARED: 0, STILL_PRESENT: 1, NON_COMPARABLE: 2}

NOTE = (
    "This record compares one export against an evidence packet's acceptance tests. "
    "It is not a closure receipt. It does not confirm who published the feed or that "
    "it is the agency's canonical export, and it does not say who caused or fixed a "
    "finding."
)

_LABELS = {
    CLEARED: "Cleared",
    STILL_PRESENT: "Still present",
    NON_COMPARABLE: "Not comparable",
}


class PacketError(ValueError):
    """The packet cannot be retested. Raised before any feed is fetched."""


Contract = tuple[str, str, str, str, str, tuple[str, ...]]


def _is_count(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def validate_packet(packet: Any) -> dict[str, Any]:
    """Return ``packet`` if it can be retested, else raise :class:`PacketError`.

    Everything that would make a retest meaningless is refused here, before a
    download or a validator run: a packet that is not one, a packet that
    requests no work (a retest over nothing would report "every finding
    cleared" having examined none), a producer contract with a missing field,
    work items whose contract disagrees with the baseline, and an acceptance
    test expecting a nonzero number of instances, which is an agreed exception
    this verb cannot confirm.
    """
    checked, baseline_contract, items = _validate_envelope(packet)
    for index, item in enumerate(items, start=1):
        _validate_work_item(index, item, baseline_contract)
    return checked


def _validate_envelope(packet: Any) -> tuple[dict[str, Any], Contract, list[Any]]:
    if not isinstance(packet, dict):
        raise PacketError("the packet is not a JSON object")
    version = packet.get("schema_version")
    major = PACKET_SCHEMA_VERSION.split(".")[0]
    if not isinstance(version, str) or version.split(".")[0] != major:
        raise PacketError(
            f"unsupported packet schema_version {version!r}; this build reads {major}.x packets"
        )
    packet_id = packet.get("packet_id")
    if not isinstance(packet_id, str) or not packet_id:
        raise PacketError("the packet has no packet_id")
    agency = packet.get("agency")
    if not isinstance(agency, dict) or not isinstance(agency.get("id"), str):
        raise PacketError("the packet names no agency")
    baseline = packet.get("baseline")
    if not isinstance(baseline, dict):
        raise PacketError("the packet has no baseline block")
    baseline_contract = acceptance_contract(baseline)
    if baseline_contract is None:
        raise PacketError(
            "the packet's baseline producer contract is incomplete (rubric, scoring "
            "profile, validator, reader archive profile and measured categories are "
            "all required); regenerate it with `scorecard evidence-packet`"
        )
    items = packet.get("work_items")
    if not isinstance(items, list):
        raise PacketError("the packet has no work_items list")
    if not items:
        raise PacketError("the packet requests no work, so there is nothing to retest")
    return packet, baseline_contract, items


def _validate_work_item(index: int, item: Any, baseline_contract: Contract) -> None:
    where = f"work item {index}"
    if not isinstance(item, dict):
        raise PacketError(f"{where} is not an object")
    acceptance = item.get("acceptance_test")
    if not isinstance(acceptance, dict):
        raise PacketError(f"{where} has no acceptance_test")
    code = acceptance.get("notice_code")
    if not isinstance(code, str) or not code:
        raise PacketError(f"{where} names no notice code")
    where = f"{where} ({code})"
    if item.get("notice_code", code) != code:
        raise PacketError(f"{where}: its notice_code and its acceptance test disagree")
    _validate_acceptance_test(where, acceptance, baseline_contract)


def _validate_acceptance_test(
    where: str, acceptance: dict[str, Any], baseline_contract: Contract
) -> None:
    category = acceptance.get("category")
    if not isinstance(category, str):
        raise PacketError(f"{where}: the acceptance test's category is not a string")
    if acceptance.get("required_category_status") != "measured":
        raise PacketError(f"{where}: the acceptance test does not require a measured category")
    expected = acceptance.get("expected_instances")
    if not _is_count(expected):
        raise PacketError(f"{where}: expected_instances is not a non-negative integer")
    if expected != 0:
        raise PacketError(
            f"{where} expects {expected} instances. A retest judges the zero-instance "
            "acceptance test `scorecard evidence-packet` writes; an agreed exception "
            "is outside what it can confirm"
        )
    contract = acceptance_contract(acceptance)
    if contract is None:
        raise PacketError(f"{where}: the acceptance test's producer contract is incomplete")
    if contract != baseline_contract:
        raise PacketError(
            f"{where}: the acceptance test names a different producer contract from "
            "the packet's baseline"
        )
    if category and category not in baseline_contract[5]:
        raise PacketError(
            f"{where}: names category {category!r}, which the baseline did not measure"
        )


def describe_source(feed: str) -> str:
    """How the record names the retested feed.

    A URL is recorded as given. A local file is recorded by name only: the
    record is meant to be pasted into a ticket, and an absolute path would
    carry a user name and a directory layout into it for no evidential gain,
    since the feed's SHA-256 already identifies the bytes.
    """
    if urllib.parse.urlparse(feed).scheme in {"http", "https"}:
        return feed
    return f"local file {Path(feed).name}"


def _contract_dict(contract: Contract) -> dict[str, Any]:
    fields: dict[str, Any] = dict(zip(CONTRACT_FIELDS, contract[:5], strict=True))
    fields["measured_categories"] = list(contract[5])
    return fields


def _contract_reason(differences: list[dict[str, str]]) -> str:
    changed = "; ".join(
        f"{item['field']} {item['baseline'] or 'not recorded'} in the packet, "
        f"{item['retest'] or 'not recorded'} in the retest"
        for item in differences
    )
    return f"the retest was produced under a different contract ({changed})"


def _evaluate(
    item: dict[str, Any],
    *,
    categories: dict[str, Any],
    differences: list[dict[str, str]],
) -> dict[str, Any]:
    acceptance = item["acceptance_test"]
    code = str(acceptance["notice_code"])
    category = str(acceptance["category"])
    entry: dict[str, Any] = {
        "priority": item.get("priority"),
        "notice_code": code,
        "category": category or None,
        "baseline_instances": item.get("current_instances"),
        "verdict": NON_COMPARABLE,
        "retest_instances": None,
        "reason": None,
    }
    if differences:
        entry["reason"] = _contract_reason(differences)
        return entry
    if not category:
        entry["reason"] = (
            "the packet does not name the category this finding came from, so there is "
            "no measured result to read it from"
        )
        return entry
    result = categories.get(category)
    if not isinstance(result, dict) or result.get("status") != "measured":
        entry["reason"] = f"the retest did not measure {category}"
        return entry
    observation = observe_notice(result, code)
    if observation is None:
        entry["reason"] = (
            f"the retest's {category} findings for this notice carry no readable count"
        )
        return entry
    if observation.present:
        entry["verdict"] = STILL_PRESENT
        entry["retest_instances"] = observation.instances
    else:
        entry["verdict"] = CLEARED
        entry["retest_instances"] = 0
    return entry


def build_retest_record(
    packet: dict[str, Any],
    retest_artifact: dict[str, Any],
    *,
    retest_source: str,
    country: str | None = None,
) -> dict[str, Any]:
    """Compare a validated packet with the artifact a retest produced.

    Pure: the only date in the record is the retest artifact's own snapshot
    date, so identical inputs give an identical record.
    """
    baseline = packet["baseline"]
    baseline_contract = acceptance_contract(baseline)
    if baseline_contract is None:  # validate_packet refuses this; kept as a guard
        raise PacketError("the packet's baseline producer contract is incomplete")
    retest_contract = producer_contract(retest_artifact)
    differences = [
        {"field": field, "baseline": expected, "retest": actual}
        for field, expected, actual in zip(
            CONTRACT_FIELDS, baseline_contract[:5], retest_contract[:5], strict=True
        )
        if expected != actual
    ]
    categories = retest_artifact.get("categories")
    findings = [
        _evaluate(
            item,
            categories=categories if isinstance(categories, dict) else {},
            differences=differences,
        )
        for item in packet["work_items"]
    ]
    summary = {
        "findings": len(findings),
        CLEARED: sum(1 for entry in findings if entry["verdict"] == CLEARED),
        STILL_PRESENT: sum(1 for entry in findings if entry["verdict"] == STILL_PRESENT),
        NON_COMPARABLE: sum(1 for entry in findings if entry["verdict"] == NON_COMPARABLE),
    }
    if summary[STILL_PRESENT]:
        outcome = STILL_PRESENT
    elif summary[NON_COMPARABLE]:
        outcome = NON_COMPARABLE
    else:
        outcome = ALL_CLEARED

    feed = retest_artifact.get("feed")
    retest_sha = feed.get("sha256") if isinstance(feed, dict) else None
    baseline_sha = baseline.get("feed_sha256")
    same_bytes = baseline_sha == retest_sha if baseline_sha and retest_sha else None
    agency = packet["agency"]
    return {
        "schema_version": RETEST_SCHEMA_VERSION,
        "record_type": RECORD_TYPE,
        "retest_date": retest_artifact.get("snapshot_date"),
        "packet": {
            "packet_id": packet["packet_id"],
            "schema_version": packet["schema_version"],
            "agency": {"id": agency["id"], "name": str(agency.get("name") or agency["id"])},
            "baseline_snapshot_date": baseline.get("snapshot_date"),
        },
        "baseline": {
            "feed_sha256": baseline_sha,
            "contract": _contract_dict(baseline_contract),
        },
        "retest": {
            "source": retest_source,
            "country": country,
            "feed_sha256": retest_sha,
            "contract": _contract_dict(retest_contract),
        },
        "same_bytes_as_baseline": same_bytes,
        "contract_comparison": {
            "comparable": not differences,
            "differences": differences,
            "measured_categories_added": [
                category for category in retest_contract[5] if category not in baseline_contract[5]
            ],
            "measured_categories_removed": [
                category for category in baseline_contract[5] if category not in retest_contract[5]
            ],
        },
        "findings": findings,
        "summary": summary,
        "outcome": outcome,
        "note": NOTE,
    }


def retest_exit_code(record: dict[str, Any]) -> int:
    """0 when every finding cleared, 1 when any is still present, 2 otherwise.

    A definite "still present" outranks "not comparable" when both occur: it is
    the verdict a CI gate exists to catch, and the record names every finding
    either way.
    """
    return EXIT_CODES[str(record["outcome"])]


def _outcome_sentence(record: dict[str, Any]) -> str:
    summary = record["summary"]
    total = summary["findings"]
    if record["outcome"] == ALL_CLEARED:
        return f"All {total} findings in the packet are cleared."
    if record["outcome"] == STILL_PRESENT:
        return f"{summary[STILL_PRESENT]} of {total} findings are still present."
    return f"{summary[NON_COMPARABLE]} of {total} findings could not be compared."


def render_retest_markdown(record: dict[str, Any]) -> str:
    """Render a retest record as Markdown that can be pasted into a ticket."""
    packet = record["packet"]
    baseline = record["baseline"]
    retest = record["retest"]
    summary = record["summary"]
    base_contract = baseline["contract"]
    new_contract = retest["contract"]

    def cell(value: Any) -> str:
        return str(value) if value else "not recorded"

    lines = [
        f"# GTFS retest: {packet['agency']['name']}",
        "",
        f"Packet `{packet['packet_id']}`, baseline "
        f"{packet.get('baseline_snapshot_date') or 'date not recorded'}. "
        f"Retested {record.get('retest_date') or 'on an unrecorded date'} from "
        f"{retest['source']}.",
        "",
        f"**{_outcome_sentence(record)}** Cleared: {summary[CLEARED]}. "
        f"Still present: {summary[STILL_PRESENT]}. "
        f"Not comparable: {summary[NON_COMPARABLE]}.",
        "",
        "| | Packet baseline | Retest |",
        "| --- | --- | --- |",
        f"| Feed SHA-256 | `{cell(baseline['feed_sha256'])}` | `{cell(retest['feed_sha256'])}` |",
    ]
    for field, label in (
        ("rubric_version", "Rubric"),
        ("scoring_profile_id", "Scoring profile"),
        ("scoring_profile_rubric_version", "Scoring profile rubric"),
        ("validator_version", "Validator"),
        ("reader_archive_profile", "Reader archive profile"),
    ):
        lines.append(f"| {label} | {cell(base_contract[field])} | {cell(new_contract[field])} |")
    lines.append(
        "| Measured categories | "
        f"{', '.join(base_contract['measured_categories']) or 'none'} | "
        f"{', '.join(new_contract['measured_categories']) or 'none'} |"
    )
    lines.append("")
    if record["same_bytes_as_baseline"]:
        lines.extend(
            [
                "The retest feed has the same SHA-256 as the packet's baseline, so these are "
                "the same bytes.",
                "",
            ]
        )
    lines.extend(
        [
            "## Findings",
            "",
            "| # | Notice | Category | Baseline count | Retest count | Result |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for entry in record["findings"]:
        retest_count = entry["retest_instances"]
        lines.append(
            f"| {entry['priority']} | `{entry['notice_code']}` | {entry['category'] or 'unknown'} "
            f"| {entry['baseline_instances']} "
            f"| {'' if retest_count is None else retest_count} "
            f"| {_LABELS[entry['verdict']]} |"
        )
    reasons = [entry for entry in record["findings"] if entry["reason"]]
    if reasons:
        lines.extend(["", "Why a finding could not be compared:", ""])
        lines.extend(f"- `{entry['notice_code']}`: {entry['reason']}." for entry in reasons)
    lines.extend(["", f"_{record['note']}_", ""])
    return "\n".join(lines)
