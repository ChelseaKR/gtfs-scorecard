"""Following a catalog retirement to a successor we do not track (ADR 0069)."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

from scorecard_pipeline import catalog_repoint as cr
from scorecard_pipeline.agencies import parse_agencies
from scorecard_pipeline.catalog_repoint import (
    Repoint,
    apply_repoints,
    check_successor_robots,
    find_repoints,
    render_repoints_md,
)
from scorecard_pipeline.config import Agency
from scorecard_pipeline.mobilitydb import parse_catalog
from scorecard_pipeline.robots_policy import RobotsChecker, RobotsResponse, RobotsVerdict

HEADER = (
    "id,data_type,entity_type,location.country_code,location.subdivision_name,provider,name,"
    "is_official,urls.direct_download,urls.authentication_type,urls.license,status,"
    "static_reference,redirect.id\n"
)


def _row(
    mdb: str,
    provider: str,
    url: str,
    *,
    status: str = "active",
    redirect: str = "",
    state: str = "Missouri",
    auth: str = "0",
    official: str = "true",
    license_url: str = "",
) -> str:
    return (
        f"{mdb},gtfs,,US,{state},{provider},,{official},{url},{auth},{license_url},"
        f"{status},,{redirect}\n"
    )


def _registry(*entries: dict[str, Any]) -> list[Agency]:
    return parse_agencies({"agencies": list(entries)})


def _entry(aid: str, name: str, url: str, mdb: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": aid,
        "name": name,
        "country": "US",
        "subdivision_code": "US-MO",
        "subdivision_name": "Missouri",
        "static_gtfs_url": url,
        "mdb_id": mdb,
        **extra,
    }


KC_CATALOG = HEADER + (
    _row(
        "mdb-187",
        "Kansas City Transit",
        "http://old.example/kc.zip",
        status="deprecated",
        redirect="mdb-3519",
    )
    + _row(
        "mdb-3519",
        "Kansas City Transit",
        "https://new.example/kc.zip",
        license_url="https://new.example/terms",
    )
)
KC = _entry("kc-transit", "Kansas City Transit", "http://old.example/kc.zip", "187")


def test_a_retired_record_moves_to_its_one_untracked_successor() -> None:
    [repoint] = find_repoints(parse_catalog(KC_CATALOG), _registry(KC))

    assert repoint.ready
    assert repoint.agency_id == "kc-transit"
    assert repoint.successor_mdb_id == "mdb-3519"
    assert repoint.successor_url == "https://new.example/kc.zip"
    assert repoint.successor_license_note == "License: https://new.example/terms"


def test_negative_control_a_tracked_successor_is_not_a_repair() -> None:
    """Same catalog; the only change is that the registry already tracks the successor."""
    tracked = _entry("kc-transit-new", "Kansas City Transit", "https://new.example/kc.zip", "")
    registry = _registry(KC, tracked)
    assert any(a.static_gtfs_url == "https://new.example/kc.zip" for a in registry)

    assert find_repoints(parse_catalog(KC_CATALOG), registry) == []
    # And without the tracked successor the proposal is back.
    assert [r.agency_id for r in find_repoints(parse_catalog(KC_CATALOG), _registry(KC))] == [
        "kc-transit"
    ]


def test_a_record_the_catalog_has_not_retired_is_left_alone() -> None:
    catalog = HEADER + _row("mdb-187", "Kansas City Transit", "http://old.example/kc.zip")
    assert find_repoints(parse_catalog(catalog), _registry(KC)) == []


def test_the_redirect_chain_is_followed_to_the_current_record() -> None:
    catalog = HEADER + (
        _row(
            "mdb-187",
            "Kansas City Transit",
            "http://old.example/kc.zip",
            status="deprecated",
            redirect="mdb-200",
        )
        + _row(
            "mdb-200",
            "Kansas City Transit",
            "http://mid.example/kc.zip",
            status="deprecated",
            redirect="mdb-300",
        )
        + _row("mdb-300", "Kansas City Transit", "https://now.example/kc.zip")
    )
    [repoint] = find_repoints(parse_catalog(catalog), _registry(KC))
    assert (repoint.successor_mdb_id, repoint.ready) == ("mdb-300", True)


def test_two_current_successors_are_held_as_ambiguous() -> None:
    catalog = HEADER + (
        _row(
            "mdb-187",
            "Kansas City Transit",
            "http://old.example/kc.zip",
            status="deprecated",
            redirect="mdb-301|mdb-302",
        )
        + _row("mdb-301", "Kansas City Transit", "https://a.example/kc.zip")
        + _row("mdb-302", "Kansas City Transit", "https://b.example/kc.zip")
    )
    [repoint] = find_repoints(parse_catalog(catalog), _registry(KC))
    assert repoint.hold == (cr.SUCCESSOR_AMBIGUOUS,)


def test_a_keyed_successor_is_held_not_written() -> None:
    catalog = HEADER + (
        _row(
            "mdb-187",
            "Kansas City Transit",
            "http://old.example/kc.zip",
            status="deprecated",
            redirect="mdb-3519",
        )
        + _row("mdb-3519", "Kansas City Transit", "https://api.example/kc?key", auth="1")
    )
    [repoint] = find_repoints(parse_catalog(catalog), _registry(KC))
    assert repoint.hold == (cr.SUCCESSOR_NOT_OPEN,)


def test_a_successor_in_another_state_under_another_name_is_held() -> None:
    """The catalog really did this: a New York county redirected to a Hawaii agency."""
    catalog = HEADER + (
        _row(
            "mdb-5",
            "St Lawrence County Public Transit",
            "http://old.example/slc.zip",
            status="deprecated",
            redirect="mdb-2608",
            state="New York",
        )
        + _row(
            "mdb-2608", "Hawaii Mass Transit Agency", "https://hi.example/gtfs.zip", state="Hawaii"
        )
    )
    retired = _entry(
        "st-lawrence",
        "St Lawrence County Public Transit",
        "http://old.example/slc.zip",
        "5",
        subdivision_code="US-NY",
        subdivision_name="New York",
    )
    [repoint] = find_repoints(parse_catalog(catalog), _registry(retired))
    assert not repoint.ready
    assert "different_subdivision" in repoint.hold
    assert "name_not_a_rename" in repoint.hold


def test_a_note_that_names_the_current_host_holds_the_move() -> None:
    pinned = {**KC, "operating_note": "Tracked on old.example by curator choice."}
    [repoint] = find_repoints(parse_catalog(KC_CATALOG), _registry(pinned))
    assert repoint.hold == (cr.NOTE_PINS_CURRENT_HOST,)


def _policy_checker(responses: Mapping[str, RobotsResponse | Exception]) -> RobotsChecker:
    """A checker running ADR 0070's real policy over canned /robots.txt answers."""

    def fake_get(url: str) -> RobotsResponse:
        answer = responses[url]
        if isinstance(answer, Exception):
            raise answer
        return answer

    return RobotsChecker(get=fake_get)


@pytest.mark.parametrize(
    ("answer", "ready", "code"),
    [
        (RobotsResponse(404, "https://n/robots.txt", "text/html", ""), True, "no_robots_file"),
        (
            RobotsResponse(200, "https://n/robots.txt", "text/plain", "User-agent: *\nAllow: /"),
            True,
            "allowed_by_robots",
        ),
        (
            RobotsResponse(
                200, "https://n/robots.txt", "text/plain", "User-agent: *\nDisallow: /a"
            ),
            False,
            "disallowed_by_robots",
        ),
        (RobotsResponse(403, "https://n/robots.txt", "text/html", ""), False, "robots_status_403"),
        (RobotsResponse(503, "https://n/robots.txt", "text/html", ""), False, "robots_status_503"),
        (
            RobotsResponse(200, "https://n/landing", "text/html", "<html>"),
            False,
            "robots_redirected_off",
        ),
        (
            RobotsResponse(200, "https://n/robots.txt", "text/html", "<!doctype html>"),
            False,
            "robots_not_a_rules_file",
        ),
        (OSError("down"), False, "robots_unreachable"),
    ],
)
def test_successor_url_is_held_unless_the_adr_0070_policy_allows_it(
    answer: RobotsResponse | Exception, ready: bool, code: str
) -> None:
    proposal = Repoint("a", "A", "1", "http://o/a", "mdb-2", "A", "https://n/a")
    checker = _policy_checker({"https://n/robots.txt": answer})

    [out] = check_successor_robots([proposal], checker.check)

    assert out.ready is ready
    assert out.hold == (() if ready else (code,))
    if not ready:
        text = render_repoints_md([out])
        assert "Held:" in text
        assert code not in text  # the report says it in words, not as a code


def test_a_403_at_robots_txt_is_no_file_only_on_an_allowlisted_object_store() -> None:
    s3 = Repoint("a", "A", "1", "http://o/a", "mdb-2", "A", "https://bucket.s3.amazonaws.com/a.zip")
    city = Repoint("b", "B", "3", "http://o/b", "mdb-4", "B", "https://transit.city.example/b.zip")
    forbidden = {
        "https://bucket.s3.amazonaws.com/robots.txt": RobotsResponse(403, "", "", ""),
        "https://transit.city.example/robots.txt": RobotsResponse(403, "", "", ""),
    }

    out = check_successor_robots([s3, city], _policy_checker(forbidden).check)

    assert out[0].ready
    assert out[1].hold == ("robots_status_403",)


def test_robots_refusal_holds_only_ready_proposals_and_costs_no_request_for_held() -> None:
    ready = Repoint("a", "A", "1", "http://o/a", "mdb-2", "A", "https://n/a")
    held = Repoint("b", "B", "3", "http://o/b", "mdb-4", "B", "https://n/b", hold=("x",))
    asked: list[str] = []

    def refuse(url: str) -> RobotsVerdict:
        asked.append(url)
        return RobotsVerdict(False, "robots_status_403")

    out = check_successor_robots([ready, held], refuse)

    assert asked == ["https://n/a"]
    assert out[0].hold == ("robots_status_403",)
    assert out[1] == held
    # An allowed answer leaves a ready proposal ready.
    allowed = check_successor_robots([ready], lambda _url: RobotsVerdict(True, "no_robots_file"))
    assert allowed[0].ready


SHARD = (
    "agencies:\n"
    "  # A hand-written comment that must survive.\n"
    "  - id: kc-transit\n"
    "    name: Kansas City Transit\n"
    "    country: US\n"
    "    subdivision_code: US-MO\n"
    "    subdivision_name: Missouri\n"
    "    static_gtfs_url: http://old.example/kc.zip\n"
    "    mdb_id: 187\n"
    "    license_note: No stated data license in the Mobility Database; verify before publishing.\n"
    "\n"
    "  - id: other\n"
    "    name: Other Transit\n"
    "    static_gtfs_url: http://old.example/kc.zip/other\n"
    "    mdb_id: '900'\n"
    "    license_note: Curator-read terms; attribution to Other Transit.\n"
)


def _ready(agency_id: str = "kc-transit", **kw: Any) -> Repoint:
    base: dict[str, Any] = {
        "agency_id": agency_id,
        "agency_name": "Kansas City Transit",
        "mdb_id": "187",
        "current_url": "http://old.example/kc.zip",
        "successor_mdb_id": "mdb-3519",
        "successor_name": "Kansas City Transit",
        "successor_url": "https://new.example/kc.zip",
        "successor_license_note": "License: https://new.example/terms",
    }
    base.update(kw)
    return Repoint(**base)


def test_apply_moves_url_and_id_and_records_the_evidence() -> None:
    updated, changed = apply_repoints(SHARD, [_ready()])

    assert changed == ["kc-transit"]
    assert "# A hand-written comment that must survive." in updated
    assert (
        "  # Mobility Database mdb-187 is deprecated and redirects to mdb-3519; "
        "the feed URL follows it (ADR 0069).\n  - id: kc-transit\n"
    ) in updated
    after = {a.id: a for a in parse_agencies(yaml.safe_load(updated))}
    assert after["kc-transit"].static_gtfs_url == "https://new.example/kc.zip"
    assert after["kc-transit"].mdb_id == "3519"  # the shard's bare numeric style
    assert after["kc-transit"].license_note == "License: https://new.example/terms"
    # The neighbor, whose URL even shares a prefix, is untouched.
    assert after["other"].static_gtfs_url == "http://old.example/kc.zip/other"
    assert after["other"].mdb_id == "900"


def test_apply_keeps_a_curator_note_and_quoted_id_style() -> None:
    item = _ready("other", mdb_id="900", successor_mdb_id="mdb-901")
    updated, changed = apply_repoints(SHARD, [item])
    assert changed == ["other"]
    assert "    mdb_id: '901'\n" in updated
    assert "license_note: Curator-read terms; attribution to Other Transit." in updated


def test_apply_does_not_churn_one_unstated_license_into_another() -> None:
    item = _ready(successor_license_note="No stated data license in the source catalog.")
    updated, _ = apply_repoints(SHARD, [item])
    assert "No stated data license in the Mobility Database; verify before publishing." in updated


def test_negative_control_a_held_proposal_is_never_written() -> None:
    held = _ready(hold=("robots_status_403",))
    assert not held.ready
    assert apply_repoints(SHARD, [held]) == (SHARD, [])
    # The same proposal without the hold is written, so the hold is what stopped it.
    assert apply_repoints(SHARD, [_ready()])[1] == ["kc-transit"]


def test_apply_leaves_a_block_without_an_mdb_id_untouched() -> None:
    shard = "agencies:\n  - id: kc-transit\n    name: K\n    static_gtfs_url: http://o/k.zip\n"
    assert apply_repoints(shard, [_ready()]) == (shard, [])


def test_report_lists_ready_and_held_with_reasons() -> None:
    report = render_repoints_md(
        [
            _ready(),
            _ready("held-one", agency_name="Held Transit", hold=(cr.SUCCESSOR_NOT_OPEN,)),
            _ready("flagged", agency_name="Flagged Transit", hold=("different_subdivision",)),
        ]
    )
    assert "**1** are ready" in report
    assert "**2** are held" in report
    assert "now https://new.example/kc.zip" in report
    assert "the successor needs a key" in report
    assert "different state or province" in report


def test_supersessions_command_applies_ready_moves_and_holds_robots_refusals(
    tmp_path: Path, isolated_repo_root: Path, request: pytest.FixtureRequest
) -> None:
    from scorecard_pipeline import robots_policy
    from scorecard_pipeline.cli import main

    shard = isolated_repo_root / "registry" / "us.yaml"
    shard.parent.mkdir(parents=True)
    shard.write_text(
        yaml.safe_dump(
            {
                "agencies": [
                    _entry("kc-transit", "Kansas City Transit", "http://old.example/kc.zip", "187"),
                    _entry(
                        "stl-transit", "Saint Louis Transit", "http://old.example/stl.zip", "50"
                    ),
                ]
            },
            sort_keys=False,
        )
    )
    (isolated_repo_root / "registry" / "index.yaml").write_text("shards:\n  - registry/us.yaml\n")
    catalog = tmp_path / "catalog.csv"
    catalog.write_text(
        KC_CATALOG
        + _row(
            "mdb-50",
            "Saint Louis Transit",
            "http://old.example/stl.zip",
            status="deprecated",
            redirect="mdb-51",
        )
        + _row("mdb-51", "Saint Louis Transit", "https://blocked.example/stl.zip")
    )

    asked: list[str] = []

    def fake_get(url: str) -> RobotsResponse:
        # No network: the real ADR 0070 policy classifies these canned answers.
        asked.append(url)
        if "blocked.example" in url:
            return RobotsResponse(403, url, "text/html", "Forbidden")
        return RobotsResponse(404, url, "text/html", "")

    robots_policy.reset_shared_checker(RobotsChecker(get=fake_get))
    request.addfinalizer(robots_policy.reset_shared_checker)
    report = tmp_path / "report.md"

    assert main(["supersessions", "--catalog", str(catalog), "--out", str(report), "--apply"]) == 0

    after = {a.id: a for a in parse_agencies(yaml.safe_load(shard.read_text()))}
    assert after["kc-transit"].static_gtfs_url == "https://new.example/kc.zip"
    assert after["stl-transit"].static_gtfs_url == "http://old.example/stl.zip"
    text = report.read_text()
    assert "## Retired, with a successor we do not track yet" in text
    assert "answered 403" in text
    assert "off-limits" in text
    # Each successor origin was read once, through the policy's own getter.
    assert sorted(asked) == [
        "https://blocked.example/robots.txt",
        "https://new.example/robots.txt",
    ]


def test_a_retired_twin_of_the_same_record_does_not_block_the_repair() -> None:
    """The dedupe kept the dead-URL twin canonical and aliased the live one."""
    twin = _entry(
        "kc-transit-3519",
        "Kansas City Transit",
        "https://new.example/kc.zip",
        "",
        alias_of="kc-transit",
        feed_status="deprecated",
    )
    [repoint] = find_repoints(parse_catalog(KC_CATALOG), _registry(KC, twin))
    assert (repoint.agency_id, repoint.ready) == ("kc-transit", True)

    # Negative control: the same twin aliased to a different record is another
    # tracker, so this is a duplicate for a curator, not a repair.
    other = _entry("other-transit", "Other Transit", "https://other.example/o.zip", "")
    elsewhere = {**twin, "alias_of": "other-transit"}
    registry = _registry(KC, other, elsewhere)
    assert next(a for a in registry if a.id == "kc-transit-3519").alias_of == "other-transit"
    assert find_repoints(parse_catalog(KC_CATALOG), registry) == []
