"""Focused tests for the evidence-gated European coverage beta."""

from __future__ import annotations

import datetime as dt
from types import SimpleNamespace
from typing import Any

import pytest

from scorecard_pipeline.global_coverage import (
    EUROPE_BETA_COUNTRY_CODES,
    build_global_coverage,
)
from scorecard_pipeline.location import normalize_subdivision

NOW = dt.datetime(2026, 7, 16, 12, 0, tzinfo=dt.UTC)

_SUBDIVISIONS = {
    "AT": "AT-9",
    "BE": "BE-BRU",
    "CH": "CH-ZH",
    "DE": "DE-BE",
    "ES": "ES-MD",
    "FR": "FR-NOR",
    "GB": "GB-ENG",
    "IE": "IE-D",
    "IT": "IT-88",
    "NL": "NL-NH",
    "NO": "NO-03",
    "PT": "PT-11",
    "US": "US-CA",
}


def _evidence(
    *,
    decision: str = "approved",
    scope: tuple[str, ...] = ("gtfs_schedule",),
    identity_reviewed: object = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        decision=decision,
        source_kind="official_portal",
        provider_source_url="https://data.example.org/datasets/sample",
        terms_url="https://data.example.org/terms",
        scope=scope,
        attribution="Example transport authority",
        reviewed_by="ChelseaKR",
        reviewed_on="2026-07-16",
        identity_reviewed=identity_reviewed,
    )


def _agency(
    feed_id: str,
    *,
    country: str = "FR",
    evidence: object | None = None,
    feed_status: str = "active",
    alias_of: str = "",
    organization_id: str = "",
) -> SimpleNamespace:
    code = _SUBDIVISIONS[country]
    canonical_code, subdivision_name = normalize_subdivision(country, code)
    assert canonical_code and subdivision_name
    return SimpleNamespace(
        id=feed_id,
        name=f"Feed {feed_id}",
        static_gtfs_url=f"https://feeds.example.org/{feed_id}.zip",
        country=country,
        subdivision_code=canonical_code,
        subdivision_name=subdivision_name,
        feed_status=feed_status,
        alias_of=alias_of,
        organization_id=organization_id,
        reuse_evidence=_evidence() if evidence is None else evidence,
    )


def _directory_row(
    agency: SimpleNamespace,
    *,
    retrieved_at: object = "2026-07-16T10:00:00+00:00",
) -> dict[str, Any]:
    return {
        "id": agency.id,
        "country": agency.country,
        "subdivision_code": agency.subdivision_code,
        "subdivision_name": agency.subdivision_name,
        "retrieved_at": retrieved_at,
        "scorecard_url": f"https://gtfsscorecard.org/agency/{agency.id}/",
    }


def _documents(
    agencies: list[SimpleNamespace],
    *,
    retrieved_at: dict[str, object] | None = None,
    translations: dict[str, object] | None = None,
    feature_count: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    retrieved_at = retrieved_at or {}
    translations = translations or {}
    directory = {
        "agencies": [
            _directory_row(
                agency,
                retrieved_at=retrieved_at.get(agency.id, "2026-07-16T10:00:00+00:00"),
            )
            for agency in agencies
        ]
    }
    rows = [
        {
            "id": agency.id,
            "translations_measured": translations.get(agency.id, True),
        }
        for agency in agencies
    ]
    features = {
        "feed_record_count": len(rows) if feature_count is None else feature_count,
        "feeds": rows,
    }
    return directory, features


def _criteria(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["key"]: row for row in payload["criteria"]}


def _exceptions(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["key"]: row for row in payload["exceptions"]}


def test_gate_selects_only_active_canonical_european_feeds_with_explicit_evidence() -> None:
    eligible = _agency("eligible", organization_id="shared-operator")
    same_operator = _agency("second-feed", organization_id="shared-operator")
    candidates = [
        eligible,
        same_operator,
        _agency("outside-scope", country="US"),
        _agency("inactive", feed_status="inactive"),
        _agency("alias", alias_of="eligible"),
        _agency("unapproved", evidence=_evidence(decision="hold")),
        _agency("rt-only", evidence=_evidence(scope=("gtfs_realtime",))),
        # Legacy narrative/official fields are intentionally not permission.
        SimpleNamespace(
            **{
                **vars(_agency("no-evidence")),
                "reuse_evidence": None,
                "license_note": "Open license",
                "is_official": True,
                "mdb_id": "mdb-1",
            }
        ),
    ]
    directory, features = _documents([eligible, same_operator])

    payload = build_global_coverage(
        candidates,
        directory,
        features,
        NOW.isoformat(),
        now=NOW,
    )

    assert payload["cohort"]["feed_record_count"] == 2
    assert [row["id"] for row in payload["records"]] == ["eligible", "second-feed"]
    # Two registry feed records remain two even when they share one operator.
    assert {row["organization_id"] for row in payload["records"]} == {"shared-operator"}
    assert payload["scope"]["unit"] == "feed_records"
    assert payload["records"][0]["reuse_evidence"] == {
        "decision": "approved",
        "source_kind": "official_portal",
        "provider_source_url": "https://data.example.org/datasets/sample",
        "terms_url": "https://data.example.org/terms",
        "scope": ["gtfs_schedule"],
        "attribution": "Example transport authority",
        "reviewed_by": "ChelseaKR",
        "reviewed_on": "2026-07-16",
        "identity_reviewed": True,
    }
    assert payload["methodology"]["registry_permission_fields_not_used"] == [
        "license_note",
        "is_official",
        "mdb_id",
    ]
    assert "NeTEx" in " ".join(payload["limitations"])


def test_all_exact_thresholds_are_inclusive_and_make_the_gate_ready() -> None:
    # 260 makes both percentage boundaries exact: 104/260 = 40% and
    # 247/260 = 95%.  The other eleven countries keep the breadth gate at 12.
    distribution = {
        "FR": 104,
        "DE": 15,
        "ES": 15,
        "IE": 15,
        "IT": 15,
        "NL": 15,
        "PT": 15,
        "BE": 15,
        "AT": 15,
        "CH": 15,
        "NO": 6,
        "GB": 15,
    }
    agencies = [
        _agency(f"{country.lower()}-{index:03d}", country=country)
        for country, count in distribution.items()
        for index in range(count)
    ]
    assert len(agencies) == 260
    stale = {agency.id for agency in agencies[-13:]}
    directory, features = _documents(
        agencies,
        retrieved_at={
            agency.id: "2026-07-08T11:59:59+00:00" for agency in agencies if agency.id in stale
        },
    )

    payload = build_global_coverage(
        agencies,
        directory,
        features,
        NOW.isoformat(),
        now=NOW,
    )
    criteria = _criteria(payload)

    assert payload["ready"] is True
    assert payload["status"] == "ready"
    assert criteria["reviewed_feed_records"]["actual"] == 260
    assert criteria["countries"]["actual"] == 12
    assert criteria["largest_country_share"]["actual"] == 40.0
    assert criteria["fresh_scorecards"]["actual"] == 95.0
    assert criteria["translations_measured"]["actual"] == 100.0
    assert criteria["portable_location"]["actual"] == 100.0
    assert criteria["identity_reviewed"]["actual"] == 100.0
    assert all(row["met"] is True for row in criteria.values())
    assert payload["cohort"]["largest_country"] == {
        "country_code": "FR",
        "country_name": "France",
        "feed_record_count": 104,
        "share_pct": 40.0,
    }


def test_display_rounding_cannot_make_raw_ratios_pass() -> None:
    # Both values display on the threshold after one-decimal rounding, but the
    # underlying ratios are just outside it: 801/2001 > 40% and
    # 1900/2001 < 95%.
    distribution = {
        "FR": 801,
        "DE": 110,
        "ES": 110,
        "IE": 110,
        "IT": 110,
        "NL": 110,
        "PT": 110,
        "BE": 110,
        "AT": 110,
        "CH": 110,
        "NO": 105,
        "GB": 105,
    }
    agencies = [
        _agency(f"rounded-{country.lower()}-{index:03d}", country=country)
        for country, count in distribution.items()
        for index in range(count)
    ]
    assert len(agencies) == 2_001
    stale = {agency.id for agency in agencies[-101:]}
    directory, features = _documents(
        agencies,
        retrieved_at={
            agency.id: "2026-07-08T00:00:00+00:00" for agency in agencies if agency.id in stale
        },
    )

    payload = build_global_coverage(
        agencies,
        directory,
        features,
        NOW.isoformat(),
        now=NOW,
    )
    criteria = _criteria(payload)

    assert criteria["largest_country_share"]["actual"] == 40.0
    assert criteria["largest_country_share"]["met"] is False
    assert criteria["fresh_scorecards"]["actual"] == 95.0
    assert criteria["fresh_scorecards"]["met"] is False
    assert payload["ready"] is False


def test_empty_cohort_has_null_percentages_and_cannot_pass() -> None:
    payload = build_global_coverage(
        [],
        {"agencies": []},
        {"feed_record_count": 0, "feeds": []},
        NOW.isoformat(),
        now=NOW,
    )
    criteria = _criteria(payload)

    assert payload["ready"] is False
    assert payload["cohort"] == {
        "feed_record_count": 0,
        "country_count": 0,
        "feature_record_count": 0,
        "largest_country": None,
    }
    for key in (
        "largest_country_share",
        "fresh_scorecards",
        "translations_measured",
        "portable_location",
        "identity_reviewed",
    ):
        assert criteria[key]["actual"] is None
        assert criteria[key]["met"] is False
    assert criteria["feature_denominator_disclosed"]["met"] is True


def test_freshness_is_inclusive_and_rejects_future_missing_and_malformed_timestamps() -> None:
    agencies = [_agency(key) for key in ("boundary", "future", "missing", "bad", "stale")]
    directory, features = _documents(
        agencies,
        retrieved_at={
            "boundary": "2026-07-09T14:00:00+02:00",  # exactly seven days ago
            "future": "2026-07-16T12:00:01+00:00",
            "missing": None,
            "bad": "2026-07-16T12:00:00",  # no offset is not auditable
            "stale": "2026-07-09T11:59:59+00:00",
        },
    )

    payload = build_global_coverage(
        agencies,
        directory,
        features,
        NOW.isoformat(),
        now=NOW,
    )
    by_id = {row["id"]: row for row in payload["records"]}
    exceptions = _exceptions(payload)

    assert by_id["boundary"]["fresh"] is True
    assert by_id["boundary"]["freshness_status"] == "fresh"
    assert by_id["future"]["freshness_status"] == "future_retrieved_at"
    assert by_id["missing"]["freshness_status"] == "missing_retrieved_at"
    assert by_id["bad"]["freshness_status"] == "malformed_retrieved_at"
    assert by_id["stale"]["freshness_status"] == "stale_scorecard"
    assert exceptions["future_retrieved_at"]["feed_record_ids"] == ["future"]
    assert exceptions["missing_retrieved_at"]["feed_record_ids"] == ["missing"]
    assert exceptions["malformed_retrieved_at"]["feed_record_ids"] == ["bad"]
    assert exceptions["stale_scorecard"]["feed_record_ids"] == ["stale"]


def test_translation_boolean_location_pair_and_identity_are_not_inferred() -> None:
    agencies = [
        _agency("boolean-true"),
        _agency("integer-one"),
        _agency("string-true"),
        _agency("false", evidence=_evidence(identity_reviewed=False)),
    ]
    directory, features = _documents(
        agencies,
        translations={
            "boolean-true": True,
            "integer-one": 1,
            "string-true": "true",
            "false": False,
        },
    )
    # A recognized code paired with the wrong official name must not pass.
    directory["agencies"][1]["subdivision_name"] = "Bretagne"

    payload = build_global_coverage(
        agencies,
        directory,
        features,
        NOW.isoformat(),
        now=NOW,
    )
    criteria = _criteria(payload)
    by_id = {row["id"]: row for row in payload["records"]}

    assert criteria["translations_measured"]["numerator"] == 1
    assert criteria["translations_measured"]["actual"] == 25.0
    assert by_id["integer-one"]["translations_measured"] is False
    assert criteria["portable_location"]["numerator"] == 3
    assert criteria["portable_location"]["actual"] == 75.0
    assert by_id["integer-one"]["portable_location_valid"] is False
    assert criteria["identity_reviewed"]["numerator"] == 3
    assert criteria["identity_reviewed"]["actual"] == 75.0
    assert by_id["false"]["identity_reviewed"] is False


def test_portable_location_accepts_country_only_but_rejects_half_a_subdivision_pair() -> None:
    country_only = _agency("country-only")
    country_only.subdivision_code = ""
    country_only.subdivision_name = ""
    code_only = _agency("code-only")
    directory, features = _documents([country_only, code_only])
    directory["agencies"][1]["subdivision_name"] = ""

    payload = build_global_coverage(
        [country_only, code_only],
        directory,
        features,
        NOW.isoformat(),
        now=NOW,
    )
    by_id = {row["id"]: row for row in payload["records"]}

    assert by_id["country-only"]["portable_location_valid"] is True
    assert by_id["code-only"]["portable_location_valid"] is False
    assert _criteria(payload)["portable_location"]["actual"] == 50.0


def test_feature_denominator_is_validated_from_the_feature_document() -> None:
    agencies = [_agency("one"), _agency("two")]
    directory, features = _documents(agencies, feature_count=3)

    payload = build_global_coverage(
        agencies,
        directory,
        features,
        NOW.isoformat(),
        now=NOW,
    )
    criterion = _criteria(payload)["feature_denominator_disclosed"]
    exception = _exceptions(payload)["feature_denominator_not_disclosed"]

    assert payload["feature_finder"] == {
        "source_feed_record_count": 3,
        "source_row_count": 2,
        "reviewed_europe_feed_record_count": 2,
        "reviewed_europe_feature_record_count": 2,
        "denominator_disclosed": False,
    }
    assert criterion["actual"] is False
    assert criterion["met"] is False
    assert exception["count"] == 1
    assert exception["feed_record_ids"] == []
    assert payload["ready"] is False


def test_scope_is_exactly_eu27_plus_five_neighbouring_markets() -> None:
    expected = {
        "AT",
        "BE",
        "BG",
        "CH",
        "CY",
        "CZ",
        "DE",
        "DK",
        "EE",
        "ES",
        "FI",
        "FR",
        "GB",
        "GR",
        "HR",
        "HU",
        "IE",
        "IS",
        "IT",
        "LI",
        "LT",
        "LU",
        "LV",
        "MT",
        "NL",
        "NO",
        "PL",
        "PT",
        "RO",
        "SE",
        "SI",
        "SK",
    }
    assert expected == EUROPE_BETA_COUNTRY_CODES


def test_reference_timestamps_must_include_an_offset() -> None:
    with pytest.raises(ValueError, match="generated_at"):
        build_global_coverage([], {"agencies": []}, {"feed_record_count": 0, "feeds": []}, "bad")
    with pytest.raises(ValueError, match="now must include"):
        build_global_coverage(
            [],
            {"agencies": []},
            {"feed_record_count": 0, "feeds": []},
            NOW.isoformat(),
            now=dt.datetime(2026, 7, 16, 12, 0),
        )
