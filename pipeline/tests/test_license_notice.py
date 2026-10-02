"""Tests for the share-alike reuse notice: the trigger, the page, and the flat export (#372).

The owner decision (2026-09-19) is that a share-alike feed is admitted, with a
notice. What these tests hold:

- the notice appears only when a block affirmatively says share-alike for a
  license it names, and never for unknown, absent, false, or contradictory
  blocks (absence must not render as a value);
- the page section is real text under a real heading, escapes what it prints,
  and clears the plain-language bars;
- the export field is present only when some record has a notice, and every
  other export is byte-for-byte what it was;
- rendering the whole site with one share-alike record changes exactly the
  files that carry that record and nothing else.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import shutil
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.config import Agency, LicenseBlock
from scorecard_pipeline.dataset import (
    COLUMNS,
    NOTICE_COLUMN,
    SCHEMA_VERSION_BASE,
    SCHEMA_VERSION_WITH_NOTICE,
    build_quality_dataset,
    to_csv,
)
from scorecard_pipeline.license_audit import CLASSES
from scorecard_pipeline.license_ledger import LICENSE_IDS, parse_block
from scorecard_pipeline.license_notice import (
    LICENSE_NAMES,
    LINK_TEXT,
    TITLE,
    WHAT_IT_ASKS,
    LicenseNotice,
    notice_for_agency,
    notice_for_block,
    notice_html,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = Path(__file__).parent / "fixtures" / "golden_site"
TODAY = dt.date(2026, 9, 19)

SHARE_ALIKE = {
    "id": "ODbL-1.0",
    "attribution_required": True,
    "redistribution_allowed": "unknown",
    "share_alike": True,
    "status": "unreviewed",
}


def block(**overrides: Any) -> LicenseBlock:
    return parse_block({**SHARE_ALIKE, **overrides}, today=TODAY)


def agency(agency_id: str = "demo", license_block: LicenseBlock | None = None) -> Agency:
    return Agency(
        id=agency_id,
        name=agency_id.title(),
        static_gtfs_url=f"https://example.org/{agency_id}.zip",
        license_block=license_block,
    )


# --- the trigger ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("license_id", "name_part"),
    [
        ("ODbL-1.0", "Open Database License (ODbL) 1.0"),
        ("CC-BY-SA-4.0", "CC BY-SA 4.0"),
        ("CC-BY-SA-3.0", "CC BY-SA 3.0"),
        ("CC-BY-SA", "version not recorded"),
    ],
)
def test_a_block_that_says_share_alike_for_a_named_license_gets_a_notice(
    license_id: str, name_part: str
) -> None:
    notice = notice_for_block(block(id=license_id))
    assert notice is not None
    assert name_part in notice.license_name
    assert notice.license_name in notice.sentences[0]
    assert notice.license_id == license_id


def test_a_named_license_outside_the_vocabulary_is_named_as_the_curator_wrote_it() -> None:
    notice = notice_for_block(block(id="other", name="National open data terms"))
    assert notice is not None
    assert notice.license_name == "National open data terms"
    bespoke = notice_for_block(block(id="proprietary-terms", name="Bespoke terms 2026"))
    assert bespoke is not None
    assert "Bespoke terms 2026" in bespoke.sentences[0]


def test_every_share_alike_class_has_a_reader_facing_name() -> None:
    share_alike_ids = {c.id for c in CLASSES if c.share_alike}
    assert set(LICENSE_NAMES) == share_alike_ids
    assert all(name.strip() for name in LICENSE_NAMES.values())


UNKNOWN_TERMS: dict[str, Any] = {
    "attribution_required": "unknown",
    "redistribution_allowed": "unknown",
    "share_alike": "unknown",
}


@pytest.mark.parametrize("license_id", LICENSE_IDS)
@pytest.mark.parametrize("share_alike", [False, "unknown"])
def test_negative_control_no_block_says_share_alike_means_no_notice(
    license_id: str, share_alike: Any
) -> None:
    """The control for absence-as-a-value: a license that is not affirmatively
    share-alike must never be given the notice, whatever its class."""
    raw: dict[str, Any] = {**SHARE_ALIKE, "id": license_id, "share_alike": share_alike}
    if license_id in ("other", "proprietary-terms"):
        raw["name"] = "A named license"
    assert notice_for_block(parse_block(raw, today=TODAY)) is None


def test_an_unknown_license_never_gets_a_notice_even_when_the_block_contradicts_itself() -> None:
    """id unknown with share_alike true is a contradiction the lint reports. The
    notice cannot name a license nobody knows, and must not guess one."""
    unknown_true = block(id="unknown", attribution_required="unknown", share_alike=True)
    assert notice_for_block(unknown_true) is None
    all_unknown = block(id="unknown", **UNKNOWN_TERMS)
    assert notice_for_block(all_unknown) is None


def test_a_block_marking_a_non_share_alike_license_share_alike_gets_no_notice() -> None:
    """Naming CC BY 4.0 as share-alike would be false, so the notice stays out
    and the lint's share_alike_mismatch is where the contradiction shows."""
    assert notice_for_block(block(id="CC-BY-4.0")) is None
    assert notice_for_block(block(id="CC0-1.0", attribution_required=False)) is None


def test_no_block_and_no_record_mean_no_notice() -> None:
    assert notice_for_block(None) is None
    assert notice_for_agency(None) is None
    assert notice_for_agency(agency()) is None
    assert notice_for_agency(agency(license_block=block())) is not None


def test_a_share_alike_notice_does_not_depend_on_review_status() -> None:
    """The block records the license as a fact, so an unreviewed proposal and a
    reviewed block say the same thing to a reader."""
    reviewed = block(status="reviewed", reviewed_by="curator", reviewed_on="2026-09-01")
    assert notice_for_block(reviewed) is not None
    assert notice_for_block(block(status="needs_review")) is not None


# --- the words ------------------------------------------------------------------


def test_the_notice_names_the_license_and_says_what_share_alike_asks() -> None:
    notice = notice_for_block(block())
    assert notice is not None
    text = " ".join(notice.sentences)
    assert "Open Database License (ODbL) 1.0" in text
    assert WHAT_IT_ASKS in text
    assert "under the same license" in text
    assert "credit the source" in text
    assert "publisher's license terms" in text


def test_the_credit_line_and_terms_link_appear_only_when_recorded() -> None:
    bare = notice_for_block(block())
    assert bare is not None
    assert "credit" in " ".join(bare.sentences)
    assert "asks for this credit" not in " ".join(bare.sentences)
    assert "<a " not in notice_html(bare)

    full = notice_for_block(
        block(attribution="Réseau Demo.", terms_url="https://data.example.org/terms")
    )
    assert full is not None
    assert "The publisher asks for this credit: Réseau Demo." in full.sentences
    html = notice_html(full)
    assert f'<a href="https://data.example.org/terms">{LINK_TEXT}</a>' in html


def _readability() -> Any:
    path = REPO_ROOT / "pipeline" / "scripts" / "check_readability.py"
    spec = importlib.util.spec_from_file_location("check_readability", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_notice_clears_the_plain_language_bars() -> None:
    readability = _readability()
    notice = notice_for_block(block(attribution="Demo Transit.", terms_url="https://x.example/t"))
    assert notice is not None
    text = " ".join(notice.sentences)
    assert readability.check_text("license notice", text) == []
    assert readability.check_text("license notice title", TITLE + ".") == []


# --- the page section -----------------------------------------------------------


class _Structure(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def test_the_section_is_a_labelled_region_with_a_real_heading() -> None:
    notice = notice_for_block(block(terms_url="https://data.example.org/terms"))
    assert notice is not None
    parser = _Structure()
    parser.feed(notice_html(notice))
    tags = {tag: attrs for tag, attrs in parser.tags}
    assert tags["section"]["aria-labelledby"] == "license-notice-h"
    assert tags["h2"]["id"] == "license-notice-h"
    assert TITLE in "".join(parser.text)


def test_the_section_does_not_rely_on_colour_or_an_icon() -> None:
    """WCAG 1.4.1: meaning is in the heading and the words. No inline style, no
    aria-hidden glyph, no colour name, nothing that only shows as an icon."""
    notice = notice_for_block(block(terms_url="https://data.example.org/terms"))
    assert notice is not None
    html = notice_html(notice)
    for forbidden in (
        "style=",
        "aria-hidden",
        "&#10003;",
        "&#9888;",
        "color",
        "colour",
        "<svg",
        "<img",
    ):
        assert forbidden not in html, forbidden
    assert "share-alike" in TITLE


def test_everything_the_notice_prints_is_escaped() -> None:
    notice = LicenseNotice(
        license_id="other",
        license_name="<script>alert(1)</script> & co",
        terms_url='https://x.example/"onmouseover="bad',
        attribution="<b>Demo</b>",
    )
    html = notice_html(notice)
    assert "<script>" not in html
    assert "<b>" not in html
    assert '"onmouseover="bad' not in html
    assert "&lt;script&gt;" in html


# --- the agency scorecard page ---------------------------------------------------


def _artifact(agency_id: str = "unitrans") -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (FIXTURE / "data" / "artifacts" / agency_id / "latest.json").read_text()
    )
    return data


def _history(agency_id: str = "unitrans") -> list[dict[str, Any]]:
    index = json.loads((FIXTURE / "data" / "artifacts" / "index.json").read_text())
    return list(index["agencies"][agency_id]["history"])


def test_a_page_without_a_notice_is_byte_identical_to_one_that_never_heard_of_it() -> None:
    from scorecard_pipeline.render_site import _render_agency

    without = _render_agency(_artifact(), _history())
    explicit_none = _render_agency(_artifact(), _history(), license_notice=None)
    assert without == explicit_none
    assert "license-notice" not in without
    assert "share-alike" not in without.lower()


def test_a_page_with_a_notice_shows_it_once_in_the_report_body() -> None:
    from scorecard_pipeline.render_site import _render_agency

    notice = notice_for_block(block(terms_url="https://data.example.org/terms"))
    assert notice is not None
    page = _render_agency(_artifact(), _history(), license_notice=notice)
    plain = _render_agency(_artifact(), _history())
    assert page.count('id="license-notice-h"') == 1
    assert page.count("<h2 ") == plain.count("<h2 ") + 1
    assert escape(TITLE) in page
    assert "Open Database License (ODbL) 1.0" in page
    # Inside the report body, ahead of the fixes, so it is read before anything is acted on.
    assert page.index('class="report-content"') < page.index("license-notice-h")
    assert page.index("license-notice-h") < page.index('id="fixes-h"')
    # Removing the notice's own block gives back exactly the page without it.
    assert page.replace("\n    " + notice_html(notice), "") == plain


# --- the flat export ------------------------------------------------------------


def _sample_index() -> dict[str, Any]:
    point = {
        "date": "2026-09-01",
        "grade": "B",
        "score": 84,
        "rubric_version": "1.2",
        "categories": {"correctness": 80, "freshness": 90, "completeness": 85},
        "days_until_expiry": 60,
    }
    return {
        "agencies": {
            "a-share": {"name": "A Share", "history": [point]},
            "b-plain": {"name": "B Plain", "history": [point]},
            "c-unknown": {"name": "C Unknown", "history": [point]},
        }
    }


def _registry() -> list[Agency]:
    unknown = parse_block(
        {
            "id": "unknown",
            "attribution_required": "unknown",
            "redistribution_allowed": "unknown",
            "share_alike": "unknown",
            "status": "needs_review",
        },
        today=TODAY,
    )
    return [agency("a-share", block()), agency("b-plain"), agency("c-unknown", unknown)]


def test_the_export_has_no_notice_column_until_a_record_carries_a_notice() -> None:
    plain = build_quality_dataset(_sample_index(), agencies=[agency("a-share"), agency("b-plain")])
    assert plain["generated_fields"] == list(COLUMNS)
    assert plain["schema_version"] == SCHEMA_VERSION_BASE == "1.3"
    assert all(NOTICE_COLUMN not in row for row in plain["rows"])
    assert to_csv(plain).splitlines()[0] == ",".join(COLUMNS)
    # ...and with no registry at all, as several callers build it.
    assert build_quality_dataset(_sample_index())["generated_fields"] == list(COLUMNS)


def test_the_export_carries_the_notice_for_share_alike_records_only() -> None:
    dataset = build_quality_dataset(_sample_index(), agencies=_registry())
    assert dataset["generated_fields"] == [*COLUMNS, NOTICE_COLUMN]
    assert dataset["schema_version"] == SCHEMA_VERSION_WITH_NOTICE == "1.4"
    rows = {row["id"]: row for row in dataset["rows"]}
    expected = notice_for_block(block())
    assert expected is not None
    assert rows["a-share"][NOTICE_COLUMN] == expected.export_text()
    assert "Open Database License (ODbL) 1.0" in rows["a-share"][NOTICE_COLUMN]
    # Every other row has the field, empty: no notice, and never a permissive value.
    assert rows["b-plain"][NOTICE_COLUMN] is None
    assert rows["c-unknown"][NOTICE_COLUMN] is None


def test_the_csv_carries_the_same_words_and_a_blank_cell_elsewhere() -> None:
    import csv
    import io

    dataset = build_quality_dataset(_sample_index(), agencies=_registry())
    reader = list(csv.DictReader(io.StringIO(to_csv(dataset))))
    assert reader[0].keys() == {*COLUMNS, NOTICE_COLUMN}
    by_id = {row["id"]: row for row in reader}
    assert by_id["a-share"][NOTICE_COLUMN] == dataset["rows"][0][NOTICE_COLUMN]
    assert by_id["b-plain"][NOTICE_COLUMN] == ""
    assert by_id["c-unknown"][NOTICE_COLUMN] == ""


def test_an_explicit_schema_version_still_wins() -> None:
    dataset = build_quality_dataset(_sample_index(), schema_version="9.9", agencies=_registry())
    assert dataset["schema_version"] == "9.9"


# --- the whole site: exactly the files that carry the record change ---------------


def _render(root: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    monkeypatch.setenv("SCORECARD_ROOT", str(root))
    from scorecard_pipeline.render_site import render_site

    liveness = json.loads((root / "data" / "liveness.json").read_text())
    checked = [
        dt.datetime.fromisoformat(str(feed["checked_at"]))
        for feed in liveness.get("feeds", {}).values()
        if feed.get("checked_at")
    ]
    now = (max(checked) if checked else dt.datetime.now(dt.UTC)) + dt.timedelta(hours=2)
    written = render_site(now=now)
    web = root / "web"
    out: dict[str, bytes] = {}
    for path in written:
        raw = path.read_bytes()
        if path.suffix in (".json", ".geojson") and b"generated_at" in raw:
            try:
                obj = json.loads(raw)
                obj.pop("generated_at", None)
                raw = json.dumps(obj, sort_keys=True).encode()
            except (json.JSONDecodeError, AttributeError):
                pass
        out[str(path.relative_to(web))] = raw
    return out


def test_rendering_with_one_share_alike_record_changes_only_the_files_that_carry_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Render the golden fixture twice, once as committed (no license blocks) and
    once with one record marked share-alike. The only files that differ are that
    record's scorecard page and the flat exports; every other page, file and the
    stylesheet is byte-for-byte identical."""
    plain_root = tmp_path / "plain"
    marked_root = tmp_path / "marked"
    shutil.copytree(FIXTURE, plain_root)
    shutil.copytree(FIXTURE, marked_root)
    registry = marked_root / "agencies.yaml"
    text = registry.read_text()
    marker = "  - id: unitrans\n"
    assert marker in text
    registry.write_text(
        text.replace(
            marker,
            marker + "    license:\n"
            "      id: ODbL-1.0\n"
            "      attribution_required: true\n"
            "      redistribution_allowed: unknown\n"
            "      share_alike: true\n"
            "      status: unreviewed\n",
            1,
        )
    )

    plain = _render(plain_root, monkeypatch)
    marked = _render(marked_root, monkeypatch)

    assert plain.keys() == marked.keys()
    changed = {rel for rel in plain if plain[rel] != marked[rel]}
    assert "agency/unitrans/index.html" in changed
    assert {"dataset.json", "dataset.csv"} <= changed
    allowed = {
        "agency/unitrans/index.html",
        "dataset.json",
        "dataset.csv",
        "api/v1/agencies.json",
        "api/v1/agencies.parquet",
    }
    assert changed <= allowed, sorted(changed - allowed)
    assert "src/styles.css" not in changed
    page = marked["agency/unitrans/index.html"].decode()
    assert escape(TITLE) in page
    assert "license-notice" not in plain["agency/unitrans/index.html"].decode()
    dataset = json.loads(marked["dataset.json"])
    assert dataset["schema_version"] == "1.4"
    unitrans = next(row for row in dataset["rows"] if row["id"] == "unitrans")
    assert "Open Database License (ODbL) 1.0" in unitrans["license_notice"]
    assert all(row["license_notice"] is None for row in dataset["rows"] if row["id"] != "unitrans")


def test_the_release_validator_accepts_an_export_that_carries_the_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dataset release refuses any export that disagrees with the canonical
    build. It must accept the notice column, and still refuse an edited one."""
    from scorecard_pipeline.dataset_release import DatasetReleaseError, validate_release_inputs

    root = tmp_path / "site"
    shutil.copytree(FIXTURE, root)
    registry = root / "agencies.yaml"
    marker = "  - id: unitrans\n"
    registry.write_text(
        registry.read_text().replace(
            marker,
            marker + "    license:\n"
            "      id: ODbL-1.0\n"
            "      attribution_required: true\n"
            "      redistribution_allowed: unknown\n"
            "      share_alike: true\n"
            "      status: unreviewed\n",
            1,
        )
    )
    _render(root, monkeypatch)

    from scorecard_pipeline.agencies import read_agencies

    current = {a.id: a for a in read_agencies() if a.is_canonical_feed}
    kwargs: dict[str, Any] = {
        "artifacts_root": root / "data" / "artifacts",
        "web_root": root / "web",
        "current_registry": current,
        "retired_registry_ids": set(),
    }
    validate_release_inputs(**kwargs)

    dataset_csv = root / "web" / "dataset.csv"
    original = dataset_csv.read_text(encoding="utf-8")
    dataset_csv.write_text(
        original.replace("Share-alike license.", "Free to use."), encoding="utf-8"
    )
    with pytest.raises(DatasetReleaseError):
        validate_release_inputs(**kwargs)
