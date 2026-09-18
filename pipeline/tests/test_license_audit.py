"""Tests for the licence audit: one licence per note, or unknown with its reason."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from scorecard_pipeline.config import Agency
from scorecard_pipeline.license_audit import (
    CLASSES,
    LINK_ONLY,
    MORE_THAN_ONE_LICENCE,
    NO_LICENCE_STATED,
    NO_NOTE,
    NOT_IN_VOCABULARY,
    SHARE_ALIKE_POLICY,
    UNKNOWN,
    classify_note,
    license_audit,
    render_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

NVBW_NOTE = (
    "Datenlizenz Deutschland Namensnennung 2.0 per NVBW's licence page; credit the dataset "
    'as "Datensatz der NVBW GmbH". This is the variant without the route network, so no '
    "OpenStreetMap-derived shapes and no ODbL condition apply."
)
ODBL_NOTE = (
    "Open Database License (ODbL), recorded by France's National Access Point; credit "
    "Région Bretagne, identify the ODbL, and preserve share-alike terms where they apply."
)


def agency(
    agency_id: str,
    note: str,
    *,
    country: str = "US",
    alias_of: str = "",
    feed_status: str = "active",
) -> Agency:
    return Agency(
        id=agency_id,
        name=agency_id.title(),
        static_gtfs_url=f"https://example.org/{agency_id}.zip",
        license_note=note,
        country=country,
        alias_of=alias_of,
        feed_status=feed_status,
    )


# --- one licence named --------------------------------------------------------


@pytest.mark.parametrize(
    ("note", "licence"),
    [
        (ODBL_NOTE, "ODbL-1.0"),
        (
            "CC BY-SA 3.0 DE per VGN's open data terms; commercial reuse is permitted with "
            "attribution to VGN and share-alike on redistributed data.",
            "CC-BY-SA-3.0",
        ),
        ("CC BY-SA through Sofia Municipality's open data portal.", "CC-BY-SA"),
        ("CC BY 4.0; credit Waltti, link the licence, and indicate any changes.", "CC-BY-4.0"),
        # An unversioned mention of the same licence is not a second licence.
        (
            "CC BY 4.0 per the Stadt Wien dataset record; the operator page states all data "
            "is published under CC BY with source credit.",
            "CC-BY-4.0",
        ),
        ("CC BY 2.1 Japan through the Tottori Prefecture open-data portal.", "CC-BY-2.1-JP"),
        (
            "CC BY 2.1 JP (the Japan jurisdiction port of Creative Commons Attribution 2.1).",
            "CC-BY-2.1-JP",
        ),
        ("CC BY through the Minho Access Point.", "CC-BY"),
        ("CC0 1.0 (public domain dedication); published as GTFS-JP open data.", "CC0-1.0"),
        ("Licence Ouverte 2.0 (Etalab), recorded by France's National Access Point.", "etalab-2.0"),
        ("Norwegian Licence for Open Government Data (NLOD) 2.0; free reuse.", "NLOD-2.0"),
        ("Datenlizenz Deutschland - Namensnennung 2.0 through NVBW's portal.", "DL-DE-BY-2.0"),
        ("Open Government Licence v3.0 through the operator's open data.", "OGL-UK-3.0"),
        ("Open Government Licence – Canada version 2.0: a worldwide licence.", "OGL-Canada-2.0"),
        ("License: https://opendatacommons.org/licenses/by/summary/", "ODC-By-1.0"),
        ("License: https://creativecommons.org/licenses/by/4.0/", "CC-BY-4.0"),
        (
            "Public domain as a United States Government work; published by the NPS.",
            "public-domain",
        ),
    ],
)
def test_a_note_naming_one_licence_gets_that_licence(note: str, licence: str) -> None:
    result = classify_note(note)
    assert result.licence == licence
    assert result.reason == ""
    assert result.known


def test_share_alike_follows_the_licence_class() -> None:
    assert classify_note(ODBL_NOTE).share_alike is True
    assert classify_note("CC BY 4.0; credit the operator.").share_alike is False


# --- no licence named -----------------------------------------------------------


@pytest.mark.parametrize(
    ("note", "reason"),
    [
        ("", NO_NOTE),
        (None, NO_NOTE),
        (
            "No stated data license in the Mobility Database; verify before publishing.",
            NO_LICENCE_STATED,
        ),
        ("License: https://www3.septa.org/developer/", LINK_ONLY),
        (
            "BC Transit Open Data Terms of Use: a non-exclusive licence to use the data.",
            NOT_IN_VOCABULARY,
        ),
        (
            "Estonia's public-transport open-data terms permit reuse with the data origin cited.",
            NOT_IN_VOCABULARY,
        ),
    ],
)
def test_a_note_naming_no_licence_is_unknown_and_says_why(note: str | None, reason: str) -> None:
    result = classify_note(note)
    assert result.licence == UNKNOWN
    assert result.reason == reason
    # Unknown is not "not share-alike". It is not known either way.
    assert result.share_alike is None


def test_a_municipal_licence_based_on_ogl_canada_is_not_ogl_canada() -> None:
    note = (
        "Open Government Licence – Halifax, based on version 2.0 of the Open Government "
        "Licence – Canada: a worldwide, royalty-free, perpetual, non-exclusive licence."
    )
    assert classify_note(note).reason == NOT_IN_VOCABULARY


def test_a_negated_mention_is_not_read_as_the_licence() -> None:
    """The NVBW notes name ODbL only to say it does not apply.

    A text search counts them as share-alike. The audit cannot tell a negation
    from a grant, so it refuses to pick: unknown, with both names kept for the
    curator.
    """
    result = classify_note(NVBW_NOTE)
    assert result.licence == UNKNOWN
    assert result.reason == MORE_THAN_ONE_LICENCE
    assert set(result.named) == {"ODbL-1.0", "DL-DE-BY-2.0"}
    assert result.share_alike is None
    assert result.names_share_alike


@pytest.mark.parametrize(
    "note",
    [
        "CC BY 4.0 through Palermo's portal. Tram data carries a CC BY-SA marking.",
        "CC0 for the schedule data. Route shapes carry the OpenStreetMap credit under ODbL.",
        "CC0 public domain dedication. The operator separately offers it under CC BY 4.0.",
    ],
)
def test_two_licences_in_one_note_are_never_resolved_by_a_pattern(note: str) -> None:
    result = classify_note(note)
    assert (result.licence, result.reason) == (UNKNOWN, MORE_THAN_ONE_LICENCE)
    assert len(result.named) == 2


def test_the_vocabulary_has_distinct_ids_and_every_pattern_compiles() -> None:
    ids = [c.id for c in CLASSES]
    assert len(ids) == len(set(ids))
    assert UNKNOWN not in ids
    for licence in CLASSES:
        assert licence.patterns
        for pattern in licence.patterns:
            re.compile(pattern)
        if licence.subsumes:
            assert licence.subsumes in ids


# --- the audit --------------------------------------------------------------------


def _fixture_registry() -> list[Agency]:
    return [
        agency("rennes", ODBL_NOTE, country="FR"),
        agency("rennes-old", ODBL_NOTE, country="FR", alias_of="rennes", feed_status="deprecated"),
        agency("nvbw", NVBW_NOTE, country="DE"),
        agency("waltti", "CC BY 4.0; credit Waltti.", country="FI"),
        agency("nostated", "No stated data license in the Mobility Database; verify."),
        agency(
            "wording", "CC BY 4.0; no share-alike obligation applies to this feed.", country="IE"
        ),
    ]


def test_the_audit_counts_every_record_once() -> None:
    report = license_audit(_fixture_registry())
    assert report["records"] == 6
    assert report["canonical_records"] == 5
    assert sum(report["by_licence"].values()) == report["records"]
    assert sum(report["unknown_by_reason"].values()) == report["by_licence"][UNKNOWN]
    assert report["by_licence"] == {"CC-BY-4.0": 2, "ODbL-1.0": 2, UNKNOWN: 2}
    assert report["unknown_by_reason"] == {MORE_THAN_ONE_LICENCE: 1, NO_LICENCE_STATED: 1}


def test_the_audit_reports_share_alike_without_a_verdict() -> None:
    share_alike = license_audit(_fixture_registry())["share_alike"]
    assert share_alike["policy"] == SHARE_ALIKE_POLICY == "undecided"
    assert "docs/follow-ups.md" in share_alike["policy_source"]
    assert share_alike["records"] == 2
    assert share_alike["canonical_records"] == 1
    assert share_alike["ids"] == ["rennes", "rennes-old"]
    assert share_alike["by_country"] == {"FR": 2}
    assert share_alike["named_with_another_licence"] == [
        {"id": "nvbw", "country": "DE", "named": ["ODbL-1.0", "DL-DE-BY-2.0"]}
    ]
    assert share_alike["mentioned_without_a_share_alike_licence"] == [
        {"id": "wording", "country": "IE", "licence": "CC-BY-4.0"}
    ]


def test_the_text_report_names_its_basis_and_the_open_decision() -> None:
    text = render_text(license_audit(_fixture_registry()))
    assert "Basis: The license_note of every registry record" in text
    assert "Share-alike policy: undecided" in text
    assert "Share-alike as the only named licence: 2 records (1 canonical)." in text
    assert "nvbw (DE): ODbL-1.0, DL-DE-BY-2.0" in text
    assert "wording (IE): CC-BY-4.0" in text


def test_the_committed_registry_reconciles_with_the_measured_text_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issue #372 measured share-alike by a case-insensitive text search.

    The audit's three share-alike buckets must add up to that search over the
    same notes, so a mention the vocabulary cannot read is reported rather than
    silently dropped. Asserts the reconciliation, not a count, so the test does
    not need editing as the registry grows.
    """
    from scorecard_pipeline.agencies import read_agencies

    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    agencies = read_agencies()
    search = re.compile(r"\bodbl\b|open database licen[cs]e|by[- ]sa\b|share[- ]?alike", re.I)
    searched = sum(1 for a in agencies if search.search(a.license_note or ""))

    share_alike = license_audit(agencies)["share_alike"]
    buckets = (
        share_alike["records"]
        + len(share_alike["named_with_another_licence"])
        + len(share_alike["mentioned_without_a_share_alike_licence"])
    )
    assert searched > 0, "the committed registry should carry share-alike notes"
    assert buckets == searched


# --- the verb ---------------------------------------------------------------------


def _write_registry(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "agencies.yaml").write_text(
        "agencies:\n"
        "  - id: rennes\n"
        "    name: STAR Rennes\n"
        "    static_gtfs_url: https://example.org/rennes.zip\n"
        "    country: FR\n"
        "    subdivision_code: FR-BRE\n"
        "    subdivision_name: Bretagne\n"
        "    license_note: Open Database License (ODbL); credit the operator.\n"
        "  - id: waltti\n"
        "    name: Waltti\n"
        "    static_gtfs_url: https://example.org/waltti.zip\n"
        "    license_note: CC BY 4.0; credit Waltti.\n"
    )


def test_the_verb_prints_json_and_never_fails(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline.cli import main

    _write_registry(isolated_repo_root)
    assert main(["license-audit", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["records"] == 2
    assert report["share_alike"]["ids"] == ["rennes"]


def test_the_verb_prints_text_by_default(
    isolated_repo_root: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from scorecard_pipeline.cli import main

    _write_registry(isolated_repo_root)
    assert main(["license-audit"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("Licence audit: 2 registry records (2 canonical).")
    assert "Share-alike policy: undecided" in out
