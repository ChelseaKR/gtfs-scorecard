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


def _feed_source_ledes(source: str) -> list[str]:
    cases = [
        {"feed": {"source_provenance": "official"}, "confidence": {"fetch_source": "origin"}},
        {"feed": {"source_provenance": "archive"}, "confidence": {"fetch_source": "origin"}},
        {"feed": {"source_provenance": "archive"}, "confidence": {"fetch_source": "mirror"}},
        {
            "feed": {"source_provenance": "third_party"},
            "confidence": {"fetch_source": "origin"},
        },
        {
            "feed": {"source_provenance": "unverified"},
            "confidence": {"fetch_source": "origin"},
        },
        {"feed": {}, "confidence": {"fetch_source": "origin"}},
    ]
    harness = """
const lede = eval("(" + process.argv[1] + ")");
const cases = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(cases.map(lede)));
"""
    node = shutil.which("node")
    assert node is not None
    completed = subprocess.run(  # noqa: S603 - fixed executable and test-owned inputs
        [
            node,
            "-e",
            harness,
            _function_source(source, "feedSourceLede"),
            json.dumps(cases),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


def _presented_conformance_summaries(source: str) -> list[str]:
    criteria = [
        {"key": "valid", "met": False, "detail": "Validation has not run."},
        {"key": "current", "met": False, "detail": "No service end date could be read."},
        {
            "key": "accessible",
            "met": False,
            "detail": "Accessibility completeness has not been measured.",
        },
    ]
    cases = [
        [{"version": 2, "summary": "Current versioned summary.", "criteria": criteria}, "stop"],
        [
            {
                "summary": "This feed is close to the conformance mark.",
                "criteria": criteria,
            },
            "stop",
        ],
        [
            {
                "version": 1,
                "summary": "This feed is close to the conformance mark.",
                "criteria": [
                    {**criteria[0], "met": True},
                    criteria[1],
                    criteria[2],
                ],
            },
            "stop",
        ],
        [
            {
                "version": 1,
                "summary": "This feed is close to the conformance mark.",
                "criteria": [
                    {**criteria[0], "met": True},
                    {**criteria[1], "met": True},
                    criteria[2],
                ],
            },
            "stop",
        ],
        [
            {
                "version": 1,
                "summary": "This feed is close to the conformance mark.",
                "criteria": [{**criterion, "met": True} for criterion in criteria],
            },
            "terminal",
        ],
        [{"version": 1, "summary": "This feed is close.", "criteria": []}, "stop"],
    ]
    harness = """
const present = eval("(" + process.argv[1] + ")");
const cases = JSON.parse(process.argv[2]);
process.stdout.write(JSON.stringify(cases.map(([mark, place]) => present(mark, place))));
"""
    node = shutil.which("node")
    assert node is not None
    completed = subprocess.run(  # noqa: S603 - fixed executable and test-owned inputs
        [
            node,
            "-e",
            harness,
            _function_source(source, "presentedConformanceSummary"),
            json.dumps(cases),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)  # type: ignore[no-any-return]


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


def test_spa_feed_source_lede_never_infers_agency_ownership_from_fetch_success() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()

    assert _feed_source_ledes(app) == [
        "Based on the official feed source on file",
        "Based on an archived feed source on file",
        "Based on a Mobility Database mirror copy of an archived feed listing",
        "Based on a third-party feed source on file",
        "Based on the feed source on file; publisher ownership is not verified",
        "Based on the feed source on file; publisher ownership is not verified",
    ]
    assert "Based on the feed this agency publishes" not in app


def test_spa_rederives_legacy_conformance_guidance_from_criteria() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()

    summaries = _presented_conformance_summaries(app)

    assert summaries == [
        "Current versioned summary.",
        "This feed does not meet the conformance requirements yet. Here is what the mark needs: "
        "Validation has not run. No service end date could be read. "
        "Accessibility completeness has not been measured.",
        "Two requirements remain for this feed to earn the conformance mark. "
        "No service end date could be read. Accessibility completeness has not been measured.",
        "One requirement remains for this feed to earn the conformance mark. "
        "Accessibility completeness has not been measured.",
        "This feed earns the conformance mark: valid, current, and stating wheelchair access "
        "on nearly every terminal and trip.",
        "Conformance progress is shown by the criteria below.",
    ]
    assert all("close" not in summary.casefold() for summary in summaries[1:])


def test_generated_compare_reader_archive_profile_resolver_fails_closed() -> None:
    from scorecard_pipeline.pages_tools import _render_compare_page

    _assert_reader_profile_resolver_fails_closed(_render_compare_page([]))


def test_spa_ignores_legacy_corrected_feed_download_urls() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()

    assert "autofix.download_url" not in app
    assert "Download corrected feed" not in app
    assert "Safe fixes you can run locally" in app
    assert "The scorecard does not publish a modified feed" in app
