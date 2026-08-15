"""The inverted NTD join: reporter roster in, match tier out.

The tiers exist so a reader can decide how much evidence to accept, so each one
is tested on its own, and the two that are easiest to get wrong get the most
attention: an alphanumeric NTD ID must survive as a string, and a vendor host
must not be read as an agency's own domain.
"""

from __future__ import annotations

from typing import Any

from scorecard_pipeline.ntd_coverage import (
    FIXED_ROUTE_MODES,
    STRONG_TIERS,
    TIER_ORDER,
    CatalogIndex,
    FeedRecord,
    Match,
    Reporter,
    atlas_ntd_ids_with_a_feed,
    classify,
    name_tokens,
    obligated_reporters,
    registrable_host,
    summarize,
)


def roster_row(**over: str) -> dict[str, str]:
    row = {
        "NTD ID": "90218",
        "Agency Name": "Riverside County Transportation Commission",
        "Doing Business As": "",
        "State": "CA",
        "Reporter Type": "Full Reporter",
        "Organization Type": "MPO, COG or Other Planning Agency",
        "URL": "http://www.rctc.org/",
    }
    row.update(over)
    return row


def mode_row(ntd_id: str, mode: str, year: str = "2024") -> dict[str, str]:
    return {"NTD ID": ntd_id, "Mode": mode, "Report Year": year}


def reporter(**over: str) -> Reporter:
    values = {
        "ntd_id": "90218",
        "name": "Riverside County Transportation Commission",
        "dba": "",
        "state": "CA",
        "reporter_type": "Full Reporter",
        "organization_type": "MPO",
        "url": "http://www.rctc.org/",
    }
    values.update(over)
    return Reporter(**values)


def classify_against(
    who: Reporter,
    *,
    registry: list[FeedRecord] | None = None,
    by_ntd_id: dict[str, list[str]] | None = None,
    atlas: frozenset[str] = frozenset(),
    catalog: list[FeedRecord] | None = None,
) -> tuple[str, str]:
    match = classify(
        who,
        registry_by_ntd_id=by_ntd_id or {},
        registry=CatalogIndex(registry or [], label="registry"),
        atlas_ntd_ids=atlas,
        catalog=CatalogIndex(catalog or [], label="mdb"),
    )
    return match.tier, match.evidence


class TestRegistrableHost:
    def test_a_subdomain_folds_to_the_agency_domain(self) -> None:
        # gtfs.muni.org and www.muni.org are the same agency; the join has to
        # see that or it misses the commonest publishing shape there is.
        assert registrable_host("https://gtfs.muni.org/People_Mover.zip") == "muni.org"
        assert registrable_host("http://www.muni.org/") == "muni.org"

    def test_a_non_url_has_no_host(self) -> None:
        assert registrable_host("") == ""
        assert registrable_host("not a url") == ""
        assert registrable_host("https:///no-host") == ""

    def test_a_bare_hostname_url_keeps_its_single_label(self) -> None:
        assert registrable_host("https://localhost/gtfs.zip") == "localhost"

    def test_a_port_is_not_part_of_the_domain(self) -> None:
        assert registrable_host("http://feeds.example.org:8080/a.zip") == "example.org"


class TestNameTokens:
    def test_boilerplate_alone_leaves_nothing_to_match_on(self) -> None:
        # "Regional Transit Authority" is every third agency in the country.
        assert name_tokens("Regional Transit Authority") == frozenset()

    def test_the_distinctive_part_survives(self) -> None:
        assert "spokane" in name_tokens("Spokane Transit Authority")


class TestObligatedReporters:
    def test_only_fixed_route_modes_put_a_reporter_in_scope(self) -> None:
        roster = [roster_row(), roster_row(**{"NTD ID": "00001", "Agency Name": "Dial A Ride"})]
        modes = [mode_row("90218", "MB"), mode_row("00001", "DR")]
        found = obligated_reporters(roster, modes, report_year="2024")
        assert [r.ntd_id for r in found] == ["90218"]

    def test_demand_response_and_vanpool_are_out_of_scope(self) -> None:
        assert "DR" not in FIXED_ROUTE_MODES
        assert "VP" not in FIXED_ROUTE_MODES

    def test_another_report_year_does_not_leak_in(self) -> None:
        modes = [mode_row("90218", "MB", year="2022")]
        assert obligated_reporters([roster_row()], modes, report_year="2024") == []

    def test_an_alphanumeric_ntd_id_is_kept_as_a_string(self) -> None:
        # Real roster values include "A0015" and "03R06". Anything that casts
        # the column to an integer drops them or renumbers them.
        roster = [roster_row(**{"NTD ID": "A0015"})]
        found = obligated_reporters(roster, [mode_row("A0015", "MB")], report_year="2024")
        assert [r.ntd_id for r in found] == ["A0015"]

    def test_a_leading_zero_is_not_stripped(self) -> None:
        roster = [roster_row(**{"NTD ID": "00447"})]
        found = obligated_reporters(roster, [mode_row("00447", "FB")], report_year="2024")
        assert [r.ntd_id for r in found] == ["00447"]

    def test_a_division_row_does_not_duplicate_its_parent(self) -> None:
        roster = [roster_row(), roster_row(**{"Doing Business As": "a division row"})]
        found = obligated_reporters(roster, [mode_row("90218", "MB")], report_year="2024")
        assert len(found) == 1
        assert found[0].dba == ""

    def test_blank_ids_never_become_a_reporter(self) -> None:
        roster = [roster_row(**{"NTD ID": ""})]
        found = obligated_reporters(roster, [mode_row("", "MB")], report_year="2024")
        assert found == []

    def test_names_pairs_the_legal_name_with_the_trading_name(self) -> None:
        who = reporter(dba="RTA")
        assert who.names == ("Riverside County Transportation Commission", "RTA")


class TestTiers:
    def test_an_ntd_id_on_a_registry_record_is_the_strongest_evidence(self) -> None:
        tier, evidence = classify_against(reporter(), by_ntd_id={"90218": ["riverside"]})
        assert tier == "registry_ntd_id"
        assert evidence == "registry:riverside"

    def test_an_exact_name_in_the_same_state_matches(self) -> None:
        records = [FeedRecord("rctc", "CA", "Riverside County Transportation Commission")]
        assert classify_against(reporter(), registry=records)[0] == "registry_name_exact"

    def test_the_same_name_in_another_state_does_not(self) -> None:
        records = [FeedRecord("rctc", "TX", "Riverside County Transportation Commission")]
        assert classify_against(reporter(), registry=records)[0] == "no_candidate"

    def test_the_agency_website_domain_matches_its_own_feed_host(self) -> None:
        records = [FeedRecord("rctc", "CA", "Something Else", ("https://gtfs.rctc.org/a.zip",))]
        assert classify_against(reporter(), registry=records)[0] == "registry_domain"

    def test_a_vendor_host_shared_by_many_records_proves_nothing(self) -> None:
        # Four records on one host is a vendor, not an agency domain, so a
        # reporter whose website is that vendor must not match all four.
        shared = [
            FeedRecord(f"a{n}", "CA", f"Agency {n}", (f"https://data.vendor.com/{n}.zip",))
            for n in range(4)
        ]
        who = reporter(name="Unlisted Agency", url="https://www.vendor.com/")
        assert classify_against(who, registry=shared)[0] == "no_candidate"

    def test_a_close_name_matches_and_a_merely_similar_one_does_not(self) -> None:
        close = [FeedRecord("sta", "WA", "Spokane Transit")]
        who = reporter(name="Spokane Transit Authority", state="WA", url="")
        assert classify_against(who, registry=close)[0] == "registry_name_exact"
        far = [FeedRecord("avta", "WA", "Antelope Valley Transit Authority")]
        assert classify_against(who, registry=far)[0] == "no_candidate"

    def test_the_atlas_is_consulted_only_after_our_own_registry(self) -> None:
        records = [FeedRecord("rctc", "CA", "Riverside County Transportation Commission")]
        assert (
            classify_against(reporter(), registry=records, atlas=frozenset({"90218"}))[0]
            == "registry_name_exact"
        )
        assert classify_against(reporter(), atlas=frozenset({"90218"}))[0] == "atlas_ntd_id"

    def test_a_catalog_only_reporter_is_labelled_as_such(self) -> None:
        catalog = [FeedRecord("mdb-9", "CA", "Riverside County Transportation Commission")]
        tier, evidence = classify_against(reporter(), catalog=catalog)
        assert tier == "catalog_name_exact"
        assert evidence == "mdb:mdb-9"

    def test_a_shared_placename_is_weak_evidence_and_says_so(self) -> None:
        # "Sitka Tribe of Alaska" against "RIDE Sitka": worth surfacing for a
        # human, never worth counting as a match.
        records = [FeedRecord("ride-sitka", "AK", "RIDE Sitka")]
        who = reporter(name="Sitka Tribe of Alaska", state="AK", url="")
        tier, evidence = classify_against(who, registry=records)
        assert tier == "weak_shared_token"
        assert evidence == "registry:ride-sitka"
        assert tier not in STRONG_TIERS

    def test_a_token_carried_by_many_records_is_not_rare_enough_to_surface(self) -> None:
        records = [FeedRecord(f"line{n}", "AK", f"Coastal Line {n}") for n in range(4)]
        who = reporter(name="Coastal Ferry Service", state="AK", url="")
        assert classify_against(who, registry=records)[0] == "no_candidate"

    def test_a_reporter_absent_everywhere_lands_in_no_candidate(self) -> None:
        assert classify_against(reporter(name="Nowhere Village Council"))[0] == "no_candidate"


class TestAtlasIds:
    def test_an_operator_with_a_static_feed_contributes_its_ntd_id(self) -> None:
        docs = [
            {
                "feeds": [{"id": "f-1", "urls": {"static_current": "https://e.org/a.zip"}}],
                "operators": [
                    {
                        "tags": {"us_ntd_id": "90218"},
                        "associated_feeds": [{"feed_onestop_id": "f-1"}],
                    }
                ],
            }
        ]
        assert atlas_ntd_ids_with_a_feed(docs) == frozenset({"90218"})

    def test_an_operator_whose_feeds_have_no_static_url_does_not(self) -> None:
        docs = [
            {
                "feeds": [{"id": "f-1", "urls": {}}],
                "operators": [
                    {
                        "tags": {"us_ntd_id": "90218"},
                        "associated_feeds": [{"feed_onestop_id": "f-1"}],
                    }
                ],
            }
        ]
        assert atlas_ntd_ids_with_a_feed(docs) == frozenset()

    def test_a_joint_tag_contributes_every_id_it_names(self) -> None:
        # Unlike the feed-to-reporter crosswalk, which drops an ambiguous tag
        # rather than stamp the wrong ID on a feed, "does some feed exist for
        # this reporter" is answered yes for each ID in a joint tag.
        docs = [
            {
                "feeds": [{"id": "f-1", "urls": {"static_current": "https://e.org/a.zip"}}],
                "operators": [
                    {
                        "tags": {"us_ntd_id": "90218,90219"},
                        "associated_feeds": [{"feed_onestop_id": "f-1"}],
                    }
                ],
            }
        ]
        assert atlas_ntd_ids_with_a_feed(docs) == frozenset({"90218", "90219"})

    def test_an_untagged_operator_is_skipped(self) -> None:
        docs: list[dict[str, Any]] = [
            {"feeds": [], "operators": [{"tags": {}, "associated_feeds": []}]}
        ]
        assert atlas_ntd_ids_with_a_feed(docs) == frozenset()

    def test_an_empty_atlas_is_not_an_error(self) -> None:
        assert atlas_ntd_ids_with_a_feed([]) == frozenset()


class TestSummarize:
    def test_the_strict_and_lenient_counts_bracket_the_answer(self) -> None:
        matches = [
            *[classify_against_stub("registry_ntd_id") for _ in range(3)],
            *[classify_against_stub("weak_shared_token") for _ in range(2)],
            classify_against_stub("no_candidate"),
        ]
        coverage = summarize(matches, report_year="2024", obligated=6)
        assert coverage.tracked_by_registry == 3
        assert coverage.discoverable_elsewhere == 0
        # Lenient counts the two weak matches as found; strict does not.
        assert coverage.no_candidate_lenient == 1
        assert coverage.no_candidate_strict == 3

    def test_every_tier_is_reported_even_at_zero(self) -> None:
        coverage = summarize([], report_year="2024", obligated=0)
        assert set(coverage.by_tier) == set(TIER_ORDER)
        assert sum(coverage.by_tier.values()) == 0


def classify_against_stub(tier: str) -> Match:
    return Match(tier, "")
