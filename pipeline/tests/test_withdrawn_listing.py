"""Withdrawing a listing nobody could measure, and what the consumers do with it.

``score_feed_content`` now refuses to grade a feed it could not read
(test_unmeasurable_feed.py). That closed the mechanism. It did nothing about the
22 scorecards already published from before it existed, each carrying a letter
for a feed whose ``stops`` and ``trips`` both measured zero -- 21 F's and one C.

Those letters are withdrawn here, by the path the registry already had for a
retired feed: the mutable current pointers go
(``artifact_lifecycle.MUTABLE_PUBLIC_ARTIFACT_NAMES``), the dated evidence
stays, and the registry records why. ``docs/listing-policy.md`` gained a
"Feeds we could not read" section for it, because the nearest existing rule --
"we do not leave a permanent failing grade on an agency that no longer exists"
-- is about agencies that ended, and most of these agencies still run buses.

The alternative, publishing a "could not be read" state in place of the grade,
was rejected: an ``overall`` with no score and no grade is required by five
schemas and read unguarded by about seventeen call sites, three of which would
misreport rather than fail. Those three are the reason this file spends most of
its length on consumers rather than on the withdrawal itself:

* ``web/src/app.js`` renders a missing grade as a large split-flap **F**
  (``String(grade || "F")``);
* ``publish._history_entry`` reads ``artifact["overall"]["score"]`` unguarded;
* ``feeddiff`` defaults a missing score to ``0.0``, which would reach Atom
  subscribers as a double-digit regression that never happened.

Withdrawal has to route around all three, and "it happens not to reach them" is
only worth as much as a test that says so.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

import pytest

from scorecard_pipeline.artifact_lifecycle import (
    MUTABLE_PUBLIC_ARTIFACT_NAMES,
    reconcile_retired_current_artifacts,
)
from scorecard_pipeline.config import Agency, artifacts_dir, register
from scorecard_pipeline.feeddiff import diff_artifacts
from scorecard_pipeline.fetch import FetchResult
from scorecard_pipeline.metrics import CategoryResult
from scorecard_pipeline.publish import build_artifact, publish, rebuild_index
from scorecard_pipeline.render_site import _scope_index_to_canonical_registry, compute_changes
from scorecard_pipeline.score import build_scorecard

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO_ROOT / "data" / "artifacts"

#: The listings withdrawn on 2026-09-01, derived by measurement rather than
#: copied: every committed ``latest.json`` whose rider-experience details report
#: ``stops == 0`` and ``trips == 0``. Their published letters at the time were
#: F for all but `boxcar`, which published a C.
#:
#: Seven were active canonical registry records and are now
#: ``feed_status: inactive``. Two (`high-desert-point`, `hut-airport-shuttle`)
#: were already retired aliases whose current pointers had gone stale in the
#: committed corpus. Thirteen have no registry record at all and were already
#: outside every current-corpus job; their pointers were stale in the same way.
WITHDRAWN_2026_09_01 = frozenset(
    {
        "anaheim-resort-transportation-art",
        "anaheim-resort-transportation-art-100",
        "beloit-transit",
        "beloit-transit-392",
        "boxcar",
        "catalina-express",
        "citrus-county-transit-630",
        "cobb-community-transit-cct-354",
        "detroit-people-mover-417",
        "high-desert-point",
        "high-desert-point-636",
        "hut-airport-shuttle",
        "hut-airport-shuttle-635",
        "jaunt-inc-1324",
        "lakexpress-342",
        "massachusetts-area-express-max",
        "massachusetts-area-express-max-431",
        "miami-dade-transit-331",
        "santa-clarita-transit",
        "santa-clarita-transit-812",
        "staten-island-ferry-518",
        "xpress-2355",
    }
)

#: The seven that were live listings a reader could reach: active canonical
#: registry records, present in the published index, rendered as a page. The
#: other fifteen were already outside the canonical registry and reached nobody
#: through the site; only their committed artifacts still said otherwise.
WITHDRAWN_FROM_THE_LIVE_SITE = frozenset(
    {
        "anaheim-resort-transportation-art",
        "beloit-transit",
        "boxcar",
        "catalina-express",
        "massachusetts-area-express-max",
        "santa-clarita-transit",
        "xpress-2355",
    }
)

_DATED = "[0-9]" * 4 + "-[0-9][0-9]-[0-9][0-9].json"

GENERATED_AT = dt.datetime(2026, 6, 11, 12, 0, tzinfo=dt.UTC)
FEED_SHA = "a" * 64
HEALTHY = Agency(
    id="unitrans",
    name="Unitrans",
    static_gtfs_url="https://example.org/gtfs.zip",
    license_note="test",
)


# --- what withdrawal did to the committed corpus -----------------------------


def test_withdrawal_left_no_current_pointer() -> None:
    """No latest.json, badge, conformance credential, mark, or geometry."""
    surviving = {
        f"{agency_id}/{name}"
        for agency_id in sorted(WITHDRAWN_2026_09_01)
        for name in MUTABLE_PUBLIC_ARTIFACT_NAMES
        if (ARTIFACTS / agency_id / name).exists()
    }
    assert not surviving, "withdrawn listings still publish current pointers: " + ", ".join(
        sorted(surviving)
    )


def test_withdrawal_deleted_nothing_that_was_measured() -> None:
    """Whatever a withdrawn listing still holds is dated evidence, intact.

    Nine of the 22 carry dated records in git and keep every one of them. The
    other thirteen never had any here: they are hydrated current-only snapshots
    of ids that left the registry, whose dated evidence lives in the object
    store, which the retirement plan does not touch (it expands ids into the
    six mutable names and nothing else). Either way, withdrawal removes
    pointers, never measurements -- so nothing but dated files may remain.
    """
    with_history = 0
    for agency_id in sorted(WITHDRAWN_2026_09_01):
        agency_dir = ARTIFACTS / agency_id
        if not agency_dir.exists():
            continue  # every file was a current pointer; the directory went with them
        dated = sorted(agency_dir.glob(_DATED))
        assert sorted(path.name for path in agency_dir.iterdir()) == [
            path.name for path in dated
        ], f"{agency_id} holds something that is neither dated evidence nor removed"
        with_history += bool(dated)
        for path in dated:
            artifact = json.loads(path.read_text())
            assert artifact["snapshot_date"] == path.stem
            assert artifact["agency"]["id"] == agency_id
    assert with_history == 9


def test_a_withdrawn_listing_is_gone_from_the_published_index() -> None:
    """index.json is what the directory, the app, and the change feed read."""
    index = json.loads((ARTIFACTS / "index.json").read_text())
    still_listed = sorted(WITHDRAWN_2026_09_01 & set(index["agencies"]))
    assert not still_listed, "withdrawn listings are still indexed: " + ", ".join(still_listed)


@pytest.fixture
def real_registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, Agency]:
    """The repository's own registry, read without touching global state."""
    from scorecard_pipeline.agencies import read_agencies

    monkeypatch.setenv("SCORECARD_ROOT", str(REPO_ROOT))
    return {agency.id: agency for agency in read_agencies()}


def test_the_registry_records_every_withdrawal_that_needed_one(
    real_registry: dict[str, Agency],
) -> None:
    """A corpus refresh must not quietly bring a withdrawn listing back.

    Deleting the pointers alone would last exactly until the next daily run
    rescored the feed. The registry is the durable half: seven records carry
    ``feed_status: inactive``, which takes them out of every current-corpus job,
    and the rest were already outside the canonical registry.
    """
    by_id = real_registry
    for agency_id in sorted(WITHDRAWN_2026_09_01):
        agency = by_id.get(agency_id)
        if agency is None:
            continue  # no registry record at all: already outside every run
        assert not agency.is_canonical_feed, (
            f"{agency_id} is withdrawn but still a canonical registry record, "
            "so the next run would publish it again"
        )
    for agency_id in sorted(WITHDRAWN_FROM_THE_LIVE_SITE):
        assert by_id[agency_id].feed_status == "inactive"


def test_a_withdrawal_never_redirects_a_reader_to_a_withdrawn_page(
    real_registry: dict[str, Agency],
) -> None:
    """A retained alias has to end somewhere a reader can actually land.

    `xpress` was a retired record redirecting to `xpress-2355`, which is one of
    the withdrawn 22. Withdrawing the target without dropping the redirect would
    have pointed readers at a page that no longer exists -- the registry's own
    alias-chain rule catches it, and this keeps that resolution in place.
    """
    by_id = real_registry
    for agency in by_id.values():
        target = agency.alias_of
        while target:
            assert target not in WITHDRAWN_2026_09_01, (
                f"{agency.id} redirects readers to {target}, which is withdrawn"
            )
            target = by_id[target].alias_of


# --- consumer: the reindex path that mints history points --------------------


def _withdrawn_agency(agency_id: str = "unreadable-demo") -> Agency:
    return Agency(
        id=agency_id,
        name="Unreadable Demo",
        static_gtfs_url="https://example.org/gtfs.zip",
        license_note="test",
        feed_status="inactive",
    )


def _publish_two_days(agency: Agency) -> None:
    register(agency)
    for date, score in ((dt.date(2026, 6, 17), 72.0), (dt.date(2026, 6, 18), 26.2)):
        fetch = FetchResult(
            agency_id=agency.id,
            path=Path("/tmp/gtfs.zip"),
            url=agency.static_gtfs_url,
            fetched_date=date,
            sha256=FEED_SHA,
            size_bytes=1024,
            reused=False,
        )
        card = build_scorecard([CategoryResult(name="correctness", score=score, summary="s")])
        publish(build_artifact(agency, fetch, card, GENERATED_AT))


def test_reindex_mints_no_history_point_for_a_withdrawn_agency() -> None:
    """``_history_entry`` is never reached for one, so it cannot invent a score.

    The unguarded ``float(artifact["overall"]["score"])`` in ``_history_entry``
    is the reason a "could not be read" artifact was not published instead. The
    withdrawal path keeps that call site away from these agencies entirely:
    ``registered_agency_dirs`` filters the walk to canonical ids first.
    """
    agency = _withdrawn_agency()
    _publish_two_days(agency)

    rebuild_index()

    index = json.loads((artifacts_dir() / "index.json").read_text())
    assert agency.id not in index["agencies"]
    # The dated evidence it skipped is still on disk and still complete.
    dated = sorted((artifacts_dir() / agency.id).glob(_DATED))
    assert [path.stem for path in dated] == ["2026-06-17", "2026-06-18"]


def test_reindex_drops_a_stale_current_pointer_and_keeps_the_dated_record() -> None:
    """The S3 plan and the local tree agree, and neither touches dated files."""
    agency = _withdrawn_agency()
    _publish_two_days(agency)
    # A pointer left behind by an earlier run, before the withdrawal.
    stale = artifacts_dir() / agency.id / "latest.json"
    stale.write_text(json.dumps({"overall": {"score": 26.2, "grade": "F"}}))

    plan = reconcile_retired_current_artifacts(artifacts_dir(), {agency.id: agency})

    assert agency.id in plan.agency_ids
    assert not stale.exists()
    assert sorted(path.name for path in (artifacts_dir() / agency.id).iterdir()) == [
        "2026-06-17.json",
        "2026-06-18.json",
    ]


# --- consumer: the change feed Atom subscribers read -------------------------


def _index_with(agency_id: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    return {"agencies": {agency_id: {"name": "Unreadable Demo", "history": history}}}


_HISTORY = [
    {
        "date": "2026-06-17",
        "categories": {"correctness": 99.0, "freshness": 100.0, "completeness": 15.0},
        "score": 73.0,
        "grade": "C",
        "rubric_version": "1.3",
        "feed_sha256": "a" * 64,
        "scoring_profile_id": "gtfs-scorecard-1.3",
        "scoring_profile_rubric_version": "1.3",
        "reader_archive_profile": "raw-v1",
        "validator_version": "8.0.1",
    },
    {
        "date": "2026-06-18",
        "categories": {"correctness": 99.0, "freshness": 100.0, "completeness": 15.0},
        "score": 73.0,
        "grade": "C",
        "rubric_version": "1.3",
        "feed_sha256": "a" * 64,
        "scoring_profile_id": "gtfs-scorecard-1.3",
        "scoring_profile_rubric_version": "1.3",
        "reader_archive_profile": "raw-v1",
        "validator_version": "8.0.1",
    },
]


def test_a_withdrawn_agency_sends_no_change_to_atom_subscribers() -> None:
    """Removed from the index is removed from the feed, silently and correctly.

    A withdrawal is not an event about the feed's quality. ``compute_changes``
    reads the index and nothing else, so an agency that is no longer indexed is
    never compared and never announced.
    """
    assert compute_changes({"agencies": {}}) == []
    assert compute_changes(_index_with("unreadable-demo", _HISTORY)) == []


def test_the_fabricated_regression_this_avoids_is_real() -> None:
    """The break test for the route not taken.

    Publishing a scoreless "could not be read" artifact would have appended a
    history point that ``compute_changes`` reads through ``.get("score", 0)``.
    This shows what subscribers would have been told: a 73-point drop to an F
    that no measurement supports. The withdrawal emits nothing instead, which is
    the whole argument for it.
    """
    unreadable_point = {**_HISTORY[-1], "date": "2026-06-19"}
    unreadable_point.pop("score")
    unreadable_point.pop("grade")

    changes = compute_changes(_index_with("unreadable-demo", [*_HISTORY, unreadable_point]))

    assert len(changes) == 1
    assert changes[0]["regressed"] is True
    assert changes[0]["score_delta"] == -73.0
    assert changes[0]["to_grade"] is None


def test_feeddiff_over_withdrawn_evidence_reads_real_scores() -> None:
    """``diff_artifacts``' ``0.0`` default is never reached by this path.

    Withdrawal removed pointers, not scores. Every dated artifact a withdrawn
    agency kept still carries a numeric ``overall.score`` and a letter, so even
    a consumer that diffs the preserved history gets a real number out.
    """
    for agency_id in sorted(WITHDRAWN_2026_09_01):
        dated = sorted((ARTIFACTS / agency_id).glob(_DATED))
        for path in dated:
            overall = json.loads(path.read_text())["overall"]
            assert isinstance(overall["score"], (int, float))
            assert not isinstance(overall["score"], bool)
            assert overall["grade"] in {"A", "B", "C", "D", "F"}
        if len(dated) < 2:
            continue
        prev, curr = (json.loads(path.read_text()) for path in dated[-2:])
        diff = diff_artifacts(prev, curr)
        expected = round(curr["overall"]["score"] - prev["overall"]["score"], 1)
        assert diff.score_delta == expected
        assert diff.prev_grade == prev["overall"]["grade"]
        assert diff.curr_grade == curr["overall"]["grade"]


# --- consumer: the site and the app ------------------------------------------


def test_rendering_scopes_a_stale_index_to_the_canonical_registry() -> None:
    """Deploy re-applies the boundary even from a previously committed index.

    Reindex enforces it first. This is the second gate, and it is the one that
    matters if a deploy starts from an index committed before the withdrawal.
    """
    index = _index_with("unreadable-demo", _HISTORY)
    index["agencies"]["unitrans"] = {"name": "Unitrans", "history": _HISTORY}

    removed = _scope_index_to_canonical_registry(
        index, {"unreadable-demo": _withdrawn_agency(), "unitrans": HEALTHY}
    )

    assert removed == 1
    assert sorted(index["agencies"]) == ["unitrans"]


def test_the_next_render_publishes_no_row_and_no_page_for_a_withdrawn_id(
    real_registry: dict[str, Agency],
) -> None:
    """The catalog, the dataset export, and the crawlable pages all drop them.

    Deploy runs ``scorecard render-site`` and only then copies ``web/`` into the
    published tree, so what is served is always regenerated. The renderer builds
    every catalog and dataset row from the registry-scoped index, skipping any
    id without a ``latest.json``, and deletes the generated page directory of an
    id the index no longer carries. This runs both of those selections over the
    real committed corpus rather than a fixture, because the claim being made is
    about this corpus.

    The committed ``web/`` tree itself is left as it is: it is the frozen
    cutover snapshot kept as an outage and fork fallback (docs/follow-ups.md,
    "Stop committing generated data and pages"), it is internally consistent
    only as a whole, and it is regenerated before anything is served.
    """
    index = json.loads((ARTIFACTS / "index.json").read_text())
    _scope_index_to_canonical_registry(index, real_registry)

    catalog_ids = {
        agency_id
        for agency_id in index["agencies"]
        if (ARTIFACTS / agency_id / "latest.json").exists()
    }
    assert catalog_ids, "no catalog rows at all; the selection is not running"
    assert not (catalog_ids & WITHDRAWN_2026_09_01)

    pages = REPO_ROOT / "web" / "agency"
    if pages.exists():
        surviving = {
            page.name
            for page in pages.iterdir()
            if page.is_dir() and page.name in index["agencies"]
        }
        assert not (surviving & WITHDRAWN_2026_09_01), (
            "a withdrawn id would keep its generated page through the render prune"
        )


def test_the_app_needs_an_index_entry_before_it_will_render_a_grade() -> None:
    """The ``String(grade || "F")`` sites are unreachable for a withdrawn id.

    The app's agency route reads the index first and only fetches
    ``<id>/latest.json`` inside the branch where the index has the agency. A
    withdrawn agency has neither, so the route takes ``renderNotFound`` and no
    grade is rendered from a missing value. Pinned against the source because
    the ordering, not the fetch, is what makes the fabricated F unreachable.
    """
    app = (REPO_ROOT / "web" / "src" / "app.js").read_text()
    route = app[app.index("async function route()") :]
    agency_branch = route[route.index("#\\/agency\\/") :]
    guard = agency_branch.index("if (index.agencies[match[1]])")
    fetch_latest = agency_branch.index("fetchJson(`${match[1]}/latest.json`)")
    not_found = agency_branch.index("renderNotFound(match[1])")

    assert guard < fetch_latest, "the app fetches a scorecard before checking the index"
    assert fetch_latest < not_found
    assert "renderNotFound" in agency_branch


def test_no_withdrawn_agency_can_be_reached_as_a_published_scorecard() -> None:
    """The pair the app requires -- an index entry and a latest.json -- is gone.

    One without the other is the dangerous state: an index entry with no
    artifact makes the route throw into ``renderError``, and an artifact with no
    index entry leaves a bookmarked URL serving a grade the directory disowns.
    Neither exists for any of the 22.
    """
    index = json.loads((ARTIFACTS / "index.json").read_text())
    for agency_id in sorted(WITHDRAWN_2026_09_01):
        assert agency_id not in index["agencies"]
        assert not (ARTIFACTS / agency_id / "latest.json").exists()
