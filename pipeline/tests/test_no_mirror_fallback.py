"""No Mobility Database mirror copies, and no catalog host whose robots.txt
does not allow us (ADR 0075)."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.robots_policy import RobotsChecker, RobotsResponse, reset_shared_checker
from scorecard_pipeline.sweep import can_resweep, needs_sweep, resweep

TODAY = dt.date(2026, 11, 5)
SCHEMA = Path(__file__).resolve().parents[2] / "web" / "schemas" / "artifact.schema.json"


def _artifact(source: str, *, days: int, fresh_score: float) -> dict[str, Any]:
    last = (dt.date(2026, 11, 4) + dt.timedelta(days=days)).isoformat()
    return {
        "agency": {"id": "copy", "name": "Copy Transit"},
        "snapshot_date": "2026-11-04",
        "overall": {"score": 0.0, "grade": "F"},
        "top_fixes": [],
        "feed": {"static_url": "https://x.example/g.zip", "reachable": False},
        "fetch": {"source": source, "final_url": "https://x.example/g.zip", "user_agent": "u"},
        "categories": {
            "correctness": {
                "name": "correctness",
                "status": "measured",
                "score": 90.0,
                "summary": "",
                "weight": 0.35,
                "findings": [],
                "details": {},
            },
            "completeness": {
                "name": "completeness",
                "status": "measured",
                "score": 70.0,
                "summary": "",
                "weight": 0.25,
                "findings": [],
                "details": {},
            },
            "freshness": {
                "name": "freshness",
                "status": "measured",
                "score": fresh_score,
                "summary": "",
                "weight": 0.20,
                "findings": [],
                "details": {
                    "has_feed_info": False,
                    "feed_version": None,
                    "service_type": "fixed",
                    "feed_start_date": None,
                    "feed_end_date": None,
                    "last_service_date": last,
                    "days_until_expiry": days,
                },
            },
        },
    }


@pytest.mark.parametrize("days", [-400, 45], ids=["expired-copy", "current-copy"])
def test_a_mirror_copy_has_its_freshness_held_never_a_value(days: int) -> None:
    artifact = _artifact("mirror", days=days, fresh_score=0.0 if days < 0 else 100.0)
    assert needs_sweep(artifact, TODAY)

    new, summary = resweep(artifact, TODAY)

    fresh = new["categories"]["freshness"]
    # Held the way score.hold_mirror_freshness holds it, current copy or lapsed:
    # no score and no countdown, only the copy's own dates under their own key.
    assert fresh["status"] == "not_yet_measured"
    assert fresh["reason"] == ("mirror_copy_expired" if days < 0 else "mirror_copy")
    assert "score" not in fresh and "details" not in fresh
    last = (dt.date(2026, 11, 4) + dt.timedelta(days=days)).isoformat()
    assert fresh["mirror_copy"]["service_end"] == last
    assert new["overall"]["grade_qualifier"] == "partial: freshness not measured"
    assert new["top_fixes"][0]["code"] == "scorecard_feed_download_failed"
    # The grade is over correctness and completeness alone: (90*.35+70*.25)/.6
    assert new["overall"]["score"] == pytest.approx(81.7, abs=0.05)
    assert summary["new_days"] is None
    # Held once, then left alone: nothing to re-measure.
    assert not can_resweep(new)


def test_a_mirror_copy_with_no_readable_end_date_is_held_too() -> None:
    """A copy whose calendar could not be read was scored 0; that is a value."""
    artifact = _artifact("mirror", days=-1, fresh_score=0.0)
    details = artifact["categories"]["freshness"]["details"]
    details.update(last_service_date=None, days_until_expiry=None)
    assert can_resweep(artifact)
    new, _ = resweep(artifact, TODAY)
    assert new["categories"]["freshness"]["status"] == "not_yet_measured"
    # Negative control: the same dateless freshness from the agency's own URL
    # is not reswept at all (nothing to recompute), as before.
    artifact["fetch"]["source"] = "origin"
    assert not can_resweep(artifact)


def test_an_origin_fetch_is_swept_as_before() -> None:
    """Negative control: the same artifact from the agency's own URL keeps a
    measured freshness that counts."""
    artifact = _artifact("origin", days=-400, fresh_score=0.0)
    new, summary = resweep(artifact, TODAY)
    assert new["categories"]["freshness"]["status"] == "measured"
    assert new["categories"]["freshness"]["score"] == 0.0
    assert new["overall"]["score"] < 81.7
    assert isinstance(summary["new_days"], int)


def test_a_held_artifact_matches_the_published_schema() -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA.read_text())
    # The one shape a held freshness may take (#566); a plain category cannot
    # carry the hold's reason or the copy's dates.
    held = schema["$defs"]["heldMirrorFreshness"]
    new, _ = resweep(_artifact("mirror", days=-3, fresh_score=0.0), TODAY)
    jsonschema.validate(new["categories"]["freshness"], {**held, "$defs": schema["$defs"]})


def _robots(by_host: dict[str, RobotsResponse]) -> None:
    from urllib.parse import urlsplit

    def get(url: str) -> RobotsResponse:
        return by_host.get(urlsplit(url).hostname or "", RobotsResponse(404, url, "", ""))

    reset_shared_checker(RobotsChecker(get=get))


SIGN_IN = RobotsResponse(
    200,
    "https://api.mobilitydatabase.org/?mode=login",
    "text/html",
    "<!doctype html><title>Sign in</title>",
)


def test_the_catalog_api_is_not_called_when_its_robots_txt_redirects_to_sign_in() -> None:
    from scorecard_pipeline import catalog_api

    _robots({"api.mobilitydatabase.org": SIGN_IN})
    calls: list[str] = []

    def post(url: str, *_: Any) -> dict[str, str]:
        calls.append(url)
        return {"access_token": "t"}

    def get(url: str, *_: Any) -> list[dict[str, Any]]:
        calls.append(url)
        return []

    with pytest.raises(catalog_api.CatalogPausedError, match=r"robots\.txt"):
        catalog_api.load_api_catalog(environ={"MOBILITY_FEED_API_TOKEN": "r"}, post=post, get=get)
    assert calls == []

    # Negative control: a host whose rules allow us is called.
    _robots({})
    assert (
        catalog_api.load_api_catalog(environ={"MOBILITY_FEED_API_TOKEN": "r"}, post=post, get=get)
        == []
    )
    assert calls


def test_the_feed_api_report_reuse_skips_a_host_robots_does_not_allow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scorecard_pipeline import feedapi

    _robots({"api.mobilitydatabase.org": SIGN_IN})
    monkeypatch.setattr(
        feedapi,
        "fetch_latest_dataset",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not call the API")),
    )
    assert feedapi.try_cached_report("1", "a" * 64, "8.0.1", "token") is None


def test_a_catalog_csv_is_read_only_where_robots_allows() -> None:
    from scorecard_pipeline.mobilitydb import fetch_catalog_bytes
    from scorecard_pipeline.robots_policy import RobotsRefusedError

    with pytest.raises(ValueError, match="disallows automated access"):
        fetch_catalog_bytes("https://files.mobilitydatabase.org/feeds_v2.csv")
    _robots(
        {
            "catalog.example": RobotsResponse(
                200,
                "https://catalog.example/robots.txt",
                "text/plain",
                "User-agent: *\nDisallow: /\n",
            )
        }
    )
    with pytest.raises(RobotsRefusedError):
        fetch_catalog_bytes("https://catalog.example/sources.csv")
