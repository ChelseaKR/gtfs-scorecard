"""The registry block writer emits one scalar per value, whatever the value is.

``mobilitydb.render_yaml`` writes the blocks that discovery and the self-serve
form propose for the registry. The layout is written by hand to match the
registry's style; every value in it is written by PyYAML, and the finished
text is parsed back before it is returned. These tests hold both halves, plus
the two input boundaries in front of the writer: catalog cells are reduced to
one line, and the registry loader refuses a name or URL that is not one.
"""

from __future__ import annotations

import re

import pytest
import yaml

from scorecard_pipeline import mobilitydb
from scorecard_pipeline.agencies import AgencyConfigError, parse_agencies
from scorecard_pipeline.mobilitydb import (
    ProposedAgency,
    RegistryRenderError,
    _cell,
    _scalar,
    render_yaml,
)

# The line breaks YAML recognizes besides LF: CR, NEL, LINE SEPARATOR and
# PARAGRAPH SEPARATOR.
SEPARATORS = ["\r", "\x85", "\u2028", "\u2029"]

# Every shape of value that a plain YAML scalar would read back as something
# else: a second key, a different type, a comment, a collection, an alias.
HOSTILE_VALUES = [
    *(f"Demo{sep}    large_feed: true" for sep in SEPARATORS),
    *(f"Demo{sep}    large_feed:{sep}      true" for sep in SEPARATORS),
    *(f"Demo{sep}    alias_of:\tother" for sep in SEPARATORS),
    *(f"Demo{sep}  - id: second{sep}    name: Second" for sep in SEPARATORS),
    *(f"{sep}Demo{sep}" for sep in SEPARATORS),
    "Demo\n    large_feed: true",
    "Demo\r\n    large_feed: true",
    "Demo\ttabbed",
    "Demo\x00nul",
    "Demo\x1bescape\x7fdelete",
    "\ufeffDemo",
    "License: https://example.org/terms",
    "Demo # not a comment",
    "Demo: with colon",
    "Demo:",
    "- Demo",
    "? Demo",
    "| Demo",
    "> Demo",
    "&anchor Demo",
    "*alias",
    "!tag Demo",
    "%YAML 1.2",
    "@Demo",
    "`Demo`",
    "{name: Demo}",
    "[Demo, Transit]",
    "---",
    "...",
    "'Demo'",
    '"Demo"',
    'Demo "quoted" name',
    "Demo \\ backslash: here",
    " leading space",
    "trailing space ",
    "",
    "NO",
    "no",
    "yes",
    "on",
    "true",
    "null",
    "~",
    "123",
    "1.5",
    "0x1F",
    "1_000",
    "2026-11-17",
    "Société de transport de Montréal",
    "東京都交通局",
    "Demo \U0001f68c Transit",
]


@pytest.mark.parametrize("value", HOSTILE_VALUES)
def test_every_scalar_reads_back_as_the_one_string_it_was_written_from(value: str) -> None:
    written = _scalar(value)
    assert "\n" not in written
    assert yaml.safe_load(f"key: {written}\n") == {"key": value}


@pytest.mark.parametrize("value", HOSTILE_VALUES)
def test_a_hostile_value_in_every_text_field_adds_no_key_and_no_entry(value: str) -> None:
    proposal = ProposedAgency(
        id="demo-transit",
        name=value,
        static_gtfs_url=value,
        mdb_id=value,
        country=value,
        subdivision_code=value,
        subdivision_name=value,
        rt_urls={
            "trip_updates": value,
            "vehicle_positions": value,
            "service_alerts": value,
        },
        rt_note=value,
        license_note=value,
        feed_status=value,
        is_official=True,
    )
    rendered = render_yaml([proposal])
    document = yaml.safe_load("agencies:\n" + rendered)

    assert list(document) == ["agencies"]
    (entry,) = document["agencies"]
    expected: dict[str, object] = {
        "id": "demo-transit",
        "name": value,
        "static_gtfs_url": value,
        "feed_status": value,
        "is_official": True,
        "rt_urls": {
            "trip_updates": value,
            "vehicle_positions": value,
            "service_alerts": value,
        },
    }
    # Empty optional fields are left out, as before.
    if value:
        expected |= {
            "country": value,
            "subdivision_code": value,
            "subdivision_name": value,
            "mdb_id": value,
            "rt_note": value,
            "license_note": value,
        }
    assert entry == expected

    # One line per field: no value carried a line of its own into the block.
    field_line = re.compile(r"^(  - |    |      )[a-z_]+:( .*)?$")
    lines = [line for line in rendered.split("\n") if line]
    assert all(field_line.match(line) for line in lines), lines
    assert len(lines) == len(entry) + len(expected["rt_urls"])  # type: ignore[arg-type]


def test_ordinary_values_keep_the_registry_style_byte_for_byte() -> None:
    proposal = ProposedAgency(
        id="davis-community-transit",
        name="Davis Community Transit",
        static_gtfs_url="https://example.org/gtfs.zip?token=a&b=c",
        mdb_id="mdb-123",
        country="CA",
        subdivision_code="CA-ON",
        subdivision_name="Ontario",
        rt_urls={
            "service_alerts": "https://example.org/alerts.pb",
            "trip_updates": "https://example.org/tu.pb",
        },
        rt_note="Realtime is published by the vendor.",
        license_note="License: https://example.org/terms",
        is_official=False,
    )
    assert render_yaml([proposal]) == (
        "  - id: davis-community-transit\n"
        "    name: Davis Community Transit\n"
        "    static_gtfs_url: https://example.org/gtfs.zip?token=a&b=c\n"
        "    country: CA\n"
        "    subdivision_code: CA-ON\n"
        "    subdivision_name: Ontario\n"
        "    mdb_id: mdb-123\n"
        "    feed_status: active\n"
        "    is_official: false\n"
        "    rt_urls:\n"
        "      trip_updates: https://example.org/tu.pb\n"
        "      service_alerts: https://example.org/alerts.pb\n"
        "    rt_note: Realtime is published by the vendor.\n"
        '    license_note: "License: https://example.org/terms"\n'
    )


def test_a_country_code_yaml_reads_as_a_boolean_is_quoted() -> None:
    proposal = ProposedAgency(
        id="ruter", name="Ruter", static_gtfs_url="https://example.no/gtfs.zip", country="NO"
    )
    rendered = render_yaml([proposal])
    assert '    country: "NO"\n' in rendered
    (agency,) = parse_agencies(yaml.safe_load("agencies:\n" + rendered))
    assert agency.country == "NO"


def test_render_yaml_refuses_a_block_that_does_not_read_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The read-back check is independent of the scalar writer.

    With the writer replaced by one that passes values through untouched, a
    value holding a line break would add a key. The block is refused instead.
    """
    monkeypatch.setattr(mobilitydb, "_scalar", lambda value: value)
    proposal = ProposedAgency(
        id="demo-transit",
        name="Demo\r    large_feed:\r      true",
        static_gtfs_url="https://example.org/gtfs.zip",
    )
    with pytest.raises(RegistryRenderError, match="does not read back"):
        render_yaml([proposal])


def test_render_yaml_of_nothing_is_empty() -> None:
    assert render_yaml([]) == ""


def test_a_catalog_cell_is_reduced_to_one_line() -> None:
    row = {"provider": "  Demo\u2028Transit\x85Authority\r\nof\tDavis\x00 "}
    assert _cell(row, "provider") == "Demo Transit Authority of Davis"
    assert _cell({"provider": "\u2028\r\n"}, "provider", "name") == ""
    assert _cell({"provider": "\x85", "name": "Fallback"}, "provider", "name") == "Fallback"


@pytest.mark.parametrize("sep", [*SEPARATORS, "\n", "\t", "\x00", "\x7f"])
def test_registry_loader_refuses_a_name_that_is_not_one_line(sep: str) -> None:
    entry = {
        "id": "demo-transit",
        "name": f"Demo{sep}Transit",
        "static_gtfs_url": "https://example.org/gtfs.zip",
    }
    with pytest.raises(AgencyConfigError, match="name must be one line"):
        parse_agencies({"agencies": [entry]})


@pytest.mark.parametrize("name", ["Demo <b>Transit</b>", "Demo > Transit", "<Demo"])
def test_registry_loader_refuses_markup_characters_in_a_name(name: str) -> None:
    entry = {"id": "demo-transit", "name": name, "static_gtfs_url": "https://example.org/g.zip"}
    with pytest.raises(AgencyConfigError, match="name must not contain"):
        parse_agencies({"agencies": [entry]})


@pytest.mark.parametrize("sep", [*SEPARATORS, "\n", "\t", " "])
def test_registry_loader_refuses_a_url_that_is_not_one_token(sep: str) -> None:
    base = {"id": "demo-transit", "name": "Demo Transit"}
    with pytest.raises(AgencyConfigError, match="static_gtfs_url must be one line"):
        parse_agencies(
            {"agencies": [base | {"static_gtfs_url": f"https://example.org/g.zip{sep}x"}]}
        )
    with pytest.raises(AgencyConfigError, match=r"rt_urls\.trip_updates must be one line"):
        parse_agencies(
            {
                "agencies": [
                    base
                    | {
                        "static_gtfs_url": "https://example.org/g.zip",
                        "rt_urls": {"trip_updates": f"https://example.org/tu{sep}x"},
                    }
                ]
            }
        )


def test_registry_loader_still_accepts_ordinary_international_names() -> None:
    names = [
        "Société de transport de Montréal",
        "東京都交通局",
        "AC Transit (Alameda-Contra Costa)",
        "Bi-State Development & Metro",
        "L'Île-Perrot / Vaudreuil",
        "  Padded Transit  ",
    ]
    entries = [
        {"id": f"agency-{i}", "name": name, "static_gtfs_url": "https://example.org/g.zip"}
        for i, name in enumerate(names)
    ]
    agencies = parse_agencies({"agencies": entries})
    assert [a.name for a in agencies] == [name.strip() for name in names]
