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


def _presented_conformance_payloads(source: str) -> list[dict[str, object]]:
    catalog = json.loads(
        (ROOT / "pipeline" / "src" / "scorecard_pipeline" / "locales" / "app.en.json").read_text()
    )

    def criteria(*, valid: bool, current: bool, accessible: bool) -> list[dict[str, object]]:
        return [
            {"key": "valid", "met": valid, "detail": "STORED VALID ENGLISH"},
            {"key": "current", "met": current, "detail": "STORED CURRENT ENGLISH"},
            {"key": "accessible", "met": accessible, "detail": "STORED ACCESS ENGLISH"},
        ]

    cases = [
        {
            "mark": {
                "version": 2,
                "summary": "STORED CURRENT SUMMARY",
                "criteria": criteria(valid=False, current=False, accessible=False),
            },
            "place": "stop",
            "artifact": {"categories": {"correctness": {"status": "skipped"}}},
        },
        {
            "mark": {
                "version": 1,
                "summary": "STORED LEGACY SUMMARY",
                "criteria": criteria(valid=True, current=False, accessible=False),
            },
            "place": "stop",
            "artifact": {
                "categories": {
                    "correctness": {"status": "measured", "findings": []},
                }
            },
        },
        {
            "mark": {
                "summary": "STORED LEGACY SUMMARY",
                "criteria": criteria(valid=True, current=True, accessible=False),
            },
            "place": "terminal",
            "artifact": {
                "categories": {
                    "correctness": {"status": "measured", "findings": []},
                    "freshness": {"details": {"days_until_expiry": 72}},
                    "completeness": {
                        "details": {
                            "accessibility": {
                                "stops_stated_pct": 100,
                                "trips_stated_pct": 0,
                            }
                        }
                    },
                }
            },
        },
        {
            "mark": {
                "version": 2,
                "summary": "STORED CURRENT SUMMARY",
                "criteria": criteria(valid=True, current=True, accessible=True),
            },
            "place": "terminal",
            "artifact": {
                "categories": {
                    "correctness": {"status": "measured", "findings": []},
                    "freshness": {"details": {"days_until_expiry": 120}},
                    "completeness": {
                        "details": {
                            "accessibility": {
                                "stops_stated_pct": 95,
                                "trips_stated_pct": 96,
                            }
                        }
                    },
                }
            },
        },
        {
            "mark": {"version": 2, "summary": "STORED CURRENT SUMMARY", "criteria": []},
            "place": "stop",
            "artifact": {},
        },
        {
            "mark": {
                "version": 2,
                "summary": "STORED CURRENT SUMMARY",
                "criteria": criteria(valid=False, current=False, accessible=True),
            },
            "place": "stop",
            "artifact": {
                "categories": {
                    "correctness": {
                        "status": "measured",
                        "findings": [{"severity": "ERROR"}, {"severity": "error"}],
                    },
                    "freshness": {"details": {"days_until_expiry": 10}},
                    "completeness": {
                        "details": {
                            "accessibility": {
                                "stops_stated_pct": 95,
                                "trips_stated_pct": 95,
                            }
                        }
                    },
                }
            },
        },
        {
            "mark": {
                "version": 2,
                "summary": "STORED CURRENT SUMMARY",
                "criteria": criteria(valid=True, current=False, accessible=True),
            },
            "place": "stop",
            "artifact": {
                "categories": {
                    "correctness": {"status": "measured", "findings": []},
                    "freshness": {"details": {"days_until_expiry": -3}},
                    "completeness": {
                        "details": {
                            "accessibility": {
                                "stops_stated_pct": 95,
                                "trips_stated_pct": 95,
                            }
                        }
                    },
                }
            },
        },
        {
            "mark": {
                "version": 2,
                "summary": "STORED CURRENT SUMMARY",
                "criteria": criteria(valid=True, current=True, accessible=True),
            },
            "place": "stop",
            "artifact": {
                "snapshot_date": "2026-07-13",
                "categories": {
                    "correctness": {"status": "measured", "findings": []},
                    "freshness": {
                        "details": {
                            "days_until_expiry": 26834,
                            "service_horizon_status": "unusually_distant",
                        }
                    },
                    "completeness": {
                        "details": {
                            "accessibility": {
                                "stops_stated_pct": 95,
                                "trips_stated_pct": 95,
                            }
                        }
                    },
                },
            },
        },
    ]
    harness = r"""
const strings = JSON.parse(process.argv[3]);
const t = (key, params) => strings[key].replace(
  /\{(\w+)\}/g,
  (match, name) => params && Object.prototype.hasOwnProperty.call(params, name)
    ? String(params[name])
    : match
);
const numericValue = eval("(" + process.argv[1] + ")");
const plainNumber = eval("(" + process.argv[2] + ")");
const presentedConformanceCriterionDetail = eval("(" + process.argv[4] + ")");
const presentedConformanceCriteria = eval("(" + process.argv[5] + ")");
const presentedConformanceSummary = eval("(" + process.argv[6] + ")");
const effectiveServiceHorizonStatus = (details) => details.service_horizon_status || "unknown";
const cases = JSON.parse(process.argv[7]);
process.stdout.write(JSON.stringify(cases.map(({mark, place, artifact}) => ({
  summary: presentedConformanceSummary(mark, place, artifact),
  criteria: presentedConformanceCriteria(artifact, mark, place),
}))));
"""
    node = shutil.which("node")
    assert node is not None
    completed = subprocess.run(  # noqa: S603 - fixed executable and test-owned inputs
        [
            node,
            "-e",
            harness,
            _function_source(source, "numericValue"),
            _function_source(source, "plainNumber"),
            json.dumps(catalog),
            _function_source(source, "presentedConformanceCriterionDetail"),
            _function_source(source, "presentedConformanceCriteria"),
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


def test_spa_localizes_current_and_legacy_conformance_from_semantic_fields() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()

    payloads = _presented_conformance_payloads(app)
    summaries = [str(payload["summary"]) for payload in payloads]

    assert summaries == [
        "This feed does not meet the conformance requirements yet. Here is what the mark needs: "
        "Validation has not run for this feed yet. No service end date could be read. "
        "Accessibility completeness has not been measured.",
        "Two requirements remain for this feed to earn the conformance mark. "
        "No service end date could be read. Accessibility completeness has not been measured.",
        "One requirement remains for this feed to earn the conformance mark. "
        "States wheelchair access on 100% of terminals and 0% of trips; "
        "the mark needs 90% of each.",
        "This feed earns the conformance mark: valid, current, and stating wheelchair access "
        "on nearly every terminal and trip.",
        "Conformance progress is shown by the criteria below.",
        "Two requirements remain for this feed to earn the conformance mark. "
        "2 validator errors to resolve. Service data runs out in 10 days; renew to qualify.",
        "One requirement remains for this feed to earn the conformance mark. "
        "Service data expired 3 days ago.",
        "This feed earns the conformance mark: valid, current, and stating wheelchair access "
        "on nearly every stop and trip.",
    ]
    assert all("stored" not in summary.casefold() for summary in summaries)
    assert payloads[2]["criteria"] == [
        {"key": "valid", "met": True, "detail": "Passes validation with no errors."},
        {"key": "current", "met": True, "detail": "Service data covers the next 72 days."},
        {
            "key": "accessible",
            "met": False,
            "detail": (
                "States wheelchair access on 100% of terminals and 0% of trips; "
                "the mark needs 90% of each."
            ),
        },
    ]
    distant = payloads[-1]["criteria"]
    assert isinstance(distant, list)
    assert distant[1]["detail"] == (
        "The published window is current, but its service end date is unusually distant; "
        "confirm that date is intentional."
    )
    assert "mark.summary" not in _function_source(app, "presentedConformanceSummary")
    conformance_section = _function_source(app, "conformanceSection")
    assert "c.detail ||" not in conformance_section
    assert "conformance_status_met" in conformance_section
    assert "conformance_head_awarded" in conformance_section


def test_generated_compare_reader_archive_profile_resolver_fails_closed() -> None:
    from scorecard_pipeline.pages_tools import _render_compare_page

    _assert_reader_profile_resolver_fails_closed(_render_compare_page([]))


def test_spa_ignores_legacy_corrected_feed_download_urls() -> None:
    app = (ROOT / "web" / "src" / "app.js").read_text()

    assert "autofix.download_url" not in app
    assert "Download corrected feed" not in app
    assert "Safe fixes you can run locally" in app
    assert "The scorecard does not publish a modified feed" in app
