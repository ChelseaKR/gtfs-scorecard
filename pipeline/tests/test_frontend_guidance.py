import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _function_source(source: str, name: str) -> str:
    start = source.index(f"function {name}(")
    opening = source.index("{", start)
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated JavaScript function {name}")


def _reader_profile_results(source: str) -> list[str]:
    cases = [
        {},
        {"fetch": {"reader_archive_normalized": True}},
        {"fetch": {"reader_archive_normalized": False}},
        {"fetch": {"reader_archive_profile": "raw-v1"}},
        {
            "fetch": {
                "reader_archive_profile": "flat-single-root-v1",
                "reader_archive_normalized": True,
            }
        },
        {
            "reader_archive_profile": "raw-v1",
            "fetch": {"reader_archive_profile": "raw-v1"},
        },
        {
            "reader_archive_profile": "raw-v1",
            "fetch": {"reader_archive_profile": "flat-single-root-v1"},
        },
        {
            "reader_archive_profile": "flat-single-root-v1",
            "fetch": {"reader_archive_profile": "raw-v1"},
        },
        {
            "fetch": {
                "reader_archive_profile": "raw-v1",
                "reader_archive_normalized": True,
            }
        },
        {
            "fetch": {
                "reader_archive_profile": "flat-single-root-v1",
                "reader_archive_normalized": False,
            }
        },
        {"fetch": {"reader_archive_normalized": "true"}},
    ]
    harness = """
const resolve = eval("(" + process.argv[1] + ")");
const cases = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(cases.map(resolve)));
"""
    node = shutil.which("node")
    assert node is not None
    completed = subprocess.run(  # noqa: S603 - fixed executable and test-owned inputs
        [
            node,
            "-e",
            harness,
            _function_source(source, "readerArchiveProfile"),
            json.dumps(cases),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


def _assert_reader_profile_resolver_fails_closed(source: str) -> None:
    assert _reader_profile_results(source) == [
        "raw-v1",
        "flat-single-root-v1",
        "raw-v1",
        "raw-v1",
        "flat-single-root-v1",
        "raw-v1",
        "",
        "",
        "",
        "",
        "",
    ]


def test_spa_ntd_and_guidance_are_country_aware() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()
    assert 'artifact.agency?.country || "US"' in app
    assert '!== "US") return ""' in app
    assert "standardsSection(artifact, dirRecord)" in app
    assert (
        'showUsPolicyToolsForCountry(dirRecord?.country || artifact.agency?.country || "US")' in app
    )
    assert "document.querySelector('.site-footer a[href=\"/ntd/\"]')" in app
    assert 'dirRecord?.country || artifact.agency?.country || "US"' in app
    assert (
        "artifact = { ...artifact, agency: { ...artifact.agency, country: effectiveCountry } };"
        in app
    )


def test_spa_has_no_hand_maintained_state_guidance_table() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()
    assert "const STATE_STANDARDS" not in app
    assert "JURISDICTION_GUIDANCE" in app
    assert "SUPPORT_RESOURCES" in app
    assert 'const CW = "/crosswalk/"' in app
    assert "blob/main/docs/crosswalk.md" not in app


def test_spa_fix_points_name_the_category_scale() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()
    assert "worth about +${Math.round(f.points)} points in its category</span>" in app


def test_spa_comparisons_disclose_the_full_producer_contract() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()
    assert "required_scoring_profile_id" in app
    assert "required_validator_version" in app
    assert "required_reader_archive_profile" in app
    assert "required_measured_categories" in app
    assert "come from distinct feed bytes" in app
    assert "function readerArchiveProfile(record)" in app
    assert 'hasOwnProperty.call(value, "reader_archive_profile")' in app
    assert 'hasOwnProperty.call(fetchBlock, "reader_archive_profile")' in app
    assert "readerProfile = readerArchiveProfile(point)" in app
    assert "readerArchive: readerArchiveProfile(art)" in app
    assert "aContract.readerArchive === bContract.readerArchive" in app
    assert "reader archive profile" in app


def test_spa_reader_archive_profile_resolver_fails_closed() -> None:
    _assert_reader_profile_resolver_fails_closed((ROOT / "web" / "src" / "app.js").read_text())


def test_generated_compare_reader_archive_profile_resolver_fails_closed() -> None:
    from scorecard_pipeline.pages_tools import _render_compare_page

    _assert_reader_profile_resolver_fails_closed(_render_compare_page([]))


def test_spa_ignores_legacy_corrected_feed_download_urls() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()

    assert "autofix.download_url" not in app
    assert "Download corrected feed" not in app
    assert "Safe fixes you can run locally" in app
    assert "The scorecard does not publish a modified feed" in app
