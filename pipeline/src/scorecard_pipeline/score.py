"""Combine category results into an overall grade and the top 3 fixes.

Weights follow the rubric (docs/rubric.md): Correctness 35%, Freshness 20%,
Rider experience completeness 25%, Realtime quality 20%. Categories not yet
measured (Phase 1 ships only the first two) are excluded and the remaining
weights renormalized, so an agency is never punished for a category the
scorecard hasn't computed.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .metrics import CategoryResult, Finding

CATEGORY_WEIGHTS = {
    "correctness": 0.35,
    "freshness": 0.20,
    "completeness": 0.25,
    "realtime": 0.20,
}

GRADE_BANDS = [(90.0, "A"), (80.0, "B"), (70.0, "C"), (60.0, "D"), (0.0, "F")]

# The overall score is published to one decimal. The letter and the band
# margins have to be derived from that same published number, not from the
# unrounded value behind it: a raw 79.96875 publishes as "80.0", and grading
# the raw value labeled it C while docs/rubric.md and the published
# scoring.json both say 80 is a B. Nine live artifacts carried a letter that
# contradicted their own printed score that way (bus-eireann, express-bus-ie,
# slieve-bloom-coach-tours, cape-ann-transportation-authority-cata-447,
# sandy-area-metro-sam at 80.0/C; regional-transportation-commission-rtc at
# 70.0/D; stan-nancy, ukmerge-public-transport,
# vilnius-district-public-transport at 60.0/F), each with a
# margin_to_next_band of 0.0. The grade bands themselves are unchanged; this
# only makes the letter agree with the number beside it.
PUBLISHED_SCORE_DECIMALS = 1


def published_score(score: float) -> float:
    """The 0-100 overall score exactly as it appears in the artifact.

    Every letter, band token, and margin has to be computed from this, so that
    a reader who applies the published bands to the published score gets the
    published letter.
    """
    return round(score, PUBLISHED_SCORE_DECIMALS)


def published_overall(score: float) -> dict[str, Any]:
    """The whole published ``overall`` block a raw score earns.

    The single place the artifact's score, letter and band margins are derived,
    so the three can never be computed from different numbers. Anything that
    re-derives a current surface from an already-published score (publish's
    reindex, the index.json trend points) calls this rather than copying a
    stored letter forward, and ``validate_artifact`` refuses to write an
    ``overall`` block that disagrees with it.
    """
    value = published_score(score)
    margin_up, margin_down = grade_margins(value)
    return {
        "score": value,
        "grade": letter_grade(value),
        "margin_to_next_band": margin_up,
        "margin_to_lower_band": margin_down,
    }


#: The words every surface prints beside a letter grade whose freshness was
#: not measured (rubric 1.5). The letter is still the one the measured
#: categories earn, but it describes less of the feed than a full grade does,
#: so it is never shown bare: not on the agency page, the board one-pager, the
#: paid report, the badges, or a row of the API, dataset, or CSV exports.
PARTIAL_FRESHNESS_QUALIFIER = "partial: freshness not measured"


def grade_qualifier(artifact: object) -> str | None:
    """The qualifier a published grade must carry, or None for a full grade.

    Read from the artifact itself, so a surface built from an older artifact
    (one published before ``overall.grade_qualifier`` existed) still says so:
    a freshness category that is present but not measured makes the grade
    partial, whatever the reason -- an expired Mobility Database mirror copy
    held out of the grade (hold_mirror_freshness), or a feed whose calendar
    could not be read. This is the same rule ``Scorecard.to_json`` uses to
    write ``overall.grade_qualifier``, so the artifact and every surface built
    from it agree. Unmeasured freshness is never turned into a value here; the
    qualifier is the whole answer.
    """
    if not isinstance(artifact, Mapping):
        return None
    overall = artifact.get("overall")
    if not isinstance(overall, Mapping) or not overall.get("grade"):
        return None
    stated = overall.get("grade_qualifier")
    if isinstance(stated, str) and stated:
        return stated
    categories = artifact.get("categories")
    fresh = categories.get("freshness") if isinstance(categories, Mapping) else None
    if isinstance(fresh, Mapping) and fresh.get("status") not in (None, "measured"):
        return PARTIAL_FRESHNESS_QUALIFIER
    return None


def qualified_grade(grade: object, qualifier: object) -> str:
    """``"C"`` or ``"C (partial: freshness not measured)"``: the one display form."""
    text = str(grade)
    return f"{text} ({qualifier})" if isinstance(qualifier, str) and qualifier else text


# A dated, plain-language log of methodology versions, newest first. Surfaced on
# the public "how to read" page and in scoring.json so a reader can tell a score
# change apart from a rule change and see exactly when each rubric version took
# effect. The versions and dates are the repository's own (RUBRIC_VERSION, and
# the commit that introduced each). Prepend a new entry whenever the rubric, its
# weights, deductions, grade bands, or what it measures change.
#
# A VALIDATOR_VERSION bump (validate.py) is a methodology change too: run
# `scorecard canary --candidate-version <X.Y.Z>` (or the validator-canary.yml
# workflow) first, attach its impact report to the bump PR, and prepend the
# dated entry the report generates — "Validator X→Y: median score …, N of M
# sampled agencies changed grade band, driven by <code>." — so the observed
# national effect ships with the change (canary.py, docs/rubric.md "Governed
# upgrades").
METHODOLOGY_CHANGELOG: list[dict[str, str]] = [
    {
        "rubric_version": "1.5",
        "effective_date": "2026-11-05",
        "summary": (
            "When the feed URL on file cannot be downloaded and the Mobility "
            "Database mirror copy scored instead has already ended, freshness is "
            "no longer graded from that copy's dates. It is shown as not measured "
            "and left out of the grade, the same way unmeasured realtime is, and "
            "the failed download becomes the first fix. The letter grade is kept, "
            'but it is marked "partial: freshness not measured" everywhere it '
            "appears: agency pages, board reports, badges, and the API, dataset, "
            "and CSV exports (overall.grade_qualifier and a grade_qualifier "
            "column). The same mark goes on any grade whose freshness was not "
            "measured for another reason, such as a calendar that could not be "
            "read. Unmeasured freshness is never shown as 0 or as fresh. "
            "Mirror copies that are still current, and every feed downloaded from "
            "its own URL, are graded as before."
        ),
    },
    {
        "rubric_version": "1.4",
        "effective_date": "2026-10-01",
        "summary": (
            "A trip now counts as having a headsign when it carries trip_headsign or "
            "when every one of its stop times carries stop_headsign, as the GTFS "
            "reference allows. Feeds that publish destinations only per stop, such "
            "as TriMet's, were scored as having none. Artifacts keep the literal "
            "trip_headsign share and add a count of trips credited through "
            "stop_headsign. See ADR 0060. When feed_info's end date is earlier than "
            "a service calendar that runs on, the expiry finding now names both "
            "dates and asks for that one field to be corrected. Freshness still "
            "scores the declared end date, so no score moves (ADR 0061)."
        ),
    },
    {
        "rubric_version": "1.3",
        "effective_date": "2026-07-24",
        "summary": (
            "The headsign component no longer treats a blank trip_headsign as a "
            "defect when every trip on a route follows one closed stop pattern, "
            "one shape, and one direction. This corrects a false positive found "
            "through maintainer feedback on MRC de Joliette's one-way loop routes. "
            "Routes with multiple directions or patterns retain the check, and "
            "the guidance no longer tells producers to copy route names into "
            "trip_headsign."
        ),
    },
    {
        "rubric_version": "1.2",
        "effective_date": "2026-07-13",
        "summary": (
            "Realtime quality now assesses only the GTFS-Realtime feed kinds an agency "
            "publishes. Unconfigured kinds are neutral, and TripUpdates coverage or "
            "VehiclePositions plausibility enters the score only when that kind is configured. "
            "Finding points use the same measurable-component denominator as the category "
            "score, and a dependent measure drops out when its endpoint produced no successful "
            "sample. "
            "A fixed-corpus replay projected 15 of 31 partial-feed artifacts changing letter "
            "bands; see docs/rubric-impact-1.2.md."
        ),
    },
    {
        "rubric_version": "1.1",
        "effective_date": "2026-06-16",
        "summary": (
            "The most rider-affecting fix is ranked first, and every grade now "
            "carries the validator and rubric version that produced it, so a "
            "trend can tell a feed change apart from a methodology change."
        ),
    },
    {
        "rubric_version": "1.0",
        "effective_date": "2026-06-11",
        "summary": (
            "First published rubric: four weighted categories (Correctness 35%, "
            "Freshness 20%, Rider experience 25%, Realtime 20%), A-F grade bands, "
            "scored on the MobilityData gtfs-validator and anchored to the "
            "California Transit Data Guidelines v4.0."
        ),
    },
]


def methodology_changelog() -> list[dict[str, str]]:
    """The dated methodology changelog, newest first (see METHODOLOGY_CHANGELOG).

    Returned as fresh copies so a caller cannot mutate the module constant.
    """
    return [dict(entry) for entry in METHODOLOGY_CHANGELOG]


def methodology() -> dict[str, Any]:
    """A machine-readable description of how the grade is computed: category
    weights, grade bands, and the correctness severity deductions.

    Published as scoring.json so a consumer or a skeptic can read the weights
    and reproduce or contest the grade, rather than treating the letter as an
    opaque opinion. The narrative version lives in docs/rubric.md.
    """
    from . import RUBRIC_VERSION
    from .metrics import COUNT_MULTIPLIER_TIERS, SEVERITY_BASE_DEDUCTION, WIDESPREAD_MULTIPLIER

    multiplier_tiers: list[dict[str, Any]] = [
        {"max_instances": threshold, "multiplier": mult}
        for threshold, mult in COUNT_MULTIPLIER_TIERS
    ]
    multiplier_tiers.append({"max_instances": None, "multiplier": WIDESPREAD_MULTIPLIER})

    return {
        "rubric_version": RUBRIC_VERSION,
        "overall": (
            "Weighted average of the measured categories. The weights of any "
            "unmeasured category are renormalized, so an agency is never punished "
            "for a category it does not have (for example, realtime)."
        ),
        "category_weights": dict(CATEGORY_WEIGHTS),
        "grade_bands": [{"min_score": floor, "grade": letter} for floor, letter in GRADE_BANDS],
        "correctness": {
            "start_score": 100.0,
            "deduction_per_distinct_notice_code": dict(SEVERITY_BASE_DEDUCTION),
            "count_scaling": (
                "Per distinct notice code, not per instance. The base deduction is "
                "multiplied by a tier based on how many instances the code has, so "
                "one systemic export bug cannot zero the score."
            ),
            "count_multiplier_tiers": multiplier_tiers,
        },
        "source": (
            "Scored on top of the MobilityData gtfs-validator. Full methodology "
            "with citations: docs/rubric.md."
        ),
        "changelog": methodology_changelog(),
    }


@dataclass(frozen=True)
class Scorecard:
    """One agency's complete scored result for one snapshot."""

    overall_score: float
    grade: str
    categories: dict[str, CategoryResult]
    top_fixes: list[Finding]
    #: Categories that were read but deliberately not graded, keyed by name,
    #: each with the plain-language reason shown in place of a score (see
    #: hold_mirror_freshness). Empty for almost every feed.
    held: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        cats: dict[str, Any] = {}
        for name, weight in CATEGORY_WEIGHTS.items():
            if name in self.categories:
                payload = self.categories[name].to_json()
                payload["weight"] = weight
                cats[name] = payload
            elif name in self.held:
                cats[name] = {
                    "name": name,
                    "status": "not_yet_measured",
                    "weight": weight,
                    **self.held[name],
                }
            else:
                cats[name] = {
                    "name": name,
                    "status": "not_yet_measured",
                    "weight": weight,
                    "summary": "Not scored yet. Nothing here counts against the grade.",
                }
        overall = published_overall(self.overall_score)
        if "freshness" not in self.categories:
            # One rule with grade_qualifier(): freshness not measured, for any
            # reason (held out from an expired mirror copy, or no readable
            # calendar), makes the grade partial on every surface, this one
            # included. Kept beside the letter, not folded into it, so
            # overall.grade stays one of A-F and the qualifier is never dropped.
            overall["grade_qualifier"] = PARTIAL_FRESHNESS_QUALIFIER
        return {
            # score, grade, and the two margins all come out of published_overall,
            # so the letter is always the letter the printed score earns. The
            # margins say how close that letter sits to its band edges (FIX-07),
            # so a near-boundary grade reads as "a B, 0.4 points from an A" rather
            # than a verdict; margin_to_next_band is null for an A, which has no
            # higher band.
            "overall": overall,
            "categories": cats,
            "top_fixes": [{**f.to_json(), "rank": i + 1} for i, f in enumerate(self.top_fixes)],
        }


def letter_grade(score: float) -> str:
    for floor, letter in GRADE_BANDS:
        if score >= floor:
            return letter
    return "F"


def grade_margins(score: float) -> tuple[float | None, float]:
    """How far ``score`` sits from its grade band's edges: (points up to the
    floor of the next-higher band, points down to the current band's own floor).

    GRADE_BANDS makes 89.9 a B and 90.1 an A; publishing the distance keeps the
    letter honest about that edge (FIX-07): 89.9 is "a B, 0.1 points from an A",
    not just a B. The upward margin is None for an A, which has no higher band.
    Rounded to one decimal, like the published score.
    """
    next_floor: float | None = None
    for floor, _letter in GRADE_BANDS:
        if score >= floor:
            margin_up = None if next_floor is None else round(next_floor - score, 1)
            return margin_up, round(score - floor, 1)
        next_floor = floor
    # Below every band cannot occur from the rubric, but degrade to the F band
    # (its floor and the D floor above it) like letter_grade's F fallback.
    return round(GRADE_BANDS[-2][0] - score, 1), round(score - GRADE_BANDS[-1][0], 1)


# A finding that makes the feed unusable to riders (expired, or an error that
# breaks parsing) must outrank a completeness gap, however many stops the gap
# touches. Tier 0 = the feed is broken or expiring; tier 1 = rider-experience
# gaps; tier 2 = informational. This is what keeps an expired feed's top fix
# "re-export your feed" instead of "set wheelchair_boarding on 300 stops".
_OPERATIONAL_CODES = (
    "scorecard_feed_expired",
    "scorecard_feed_expiring_soon",
    "scorecard_feed_end_date_before_calendar",
    "scorecard_no_expiry_date",
)


def _fix_tier(finding: Finding) -> int:
    if finding.severity == "ERROR" or finding.code in _OPERATIONAL_CODES:
        return 0
    if finding.severity == "WARNING":
        return 1
    return 2


def _fix_priority(finding: Finding) -> tuple[int, float, int]:
    """Order candidate fixes by rider impact first (tier), then by score impact
    and how widespread they are."""
    return (_fix_tier(finding), -finding.deduction, -finding.count)


#: What the refusal says, in one sentence, everywhere it is said.
NOTHING_WAS_READ = (
    "no GTFS schedule data could be read from this archive: it has no stops and "
    "no trips, so neither freshness nor rider experience could be measured and "
    "there is no feed to grade"
)


class UnreadableFeedError(ValueError):
    """The archive carried no schedule content, so there is no grade to publish.

    Raised instead of returning a scorecard whose overall rests on correctness
    alone. Correctness can score such an archive -- the validator has notices to
    report about what is missing -- but a letter derived from it describes a
    feed that was never read.

    Both available answers were fabrications. Before the absence fix the
    published grade was an F built from two 0.0s nobody measured; with the
    absence fix and no refusal it becomes a B or an A, because correctness
    starts at 100 and an empty archive gives it almost nothing to deduct for.
    `beloit-transit` would have moved F to B and `boxcar` C to A. A feed with no
    stops and no trips earning a B is a worse published claim than the F it
    replaces, and neither letter is true. "Could not be read" is.

    Subclasses ValueError deliberately. A response body that is not a zip
    already raises ValueError out of ``fetch.fetch_static``, and every caller
    that refuses a feed on that basis -- ``scorecard try`` prints "could not
    score <url>: ..." and exits 1 -- refuses this one by the same path, with no
    new handling. One refusal, two causes, not two concepts.
    """


def score_feed_content(
    reader_path: str,
    *,
    today: dt.date,
    service_type: str = "fixed",
    fare_free: bool = False,
) -> list[CategoryResult]:
    """The categories that read the archive, and the refusal when none could.

    Freshness and rider experience are the two that read the feed's own
    contents. Correctness is not one of them: it scores the validator's notices,
    and an archive with nothing in it still raises a handful, which is how an
    empty zip reached a correctness of 71.5 with nothing to check.

    This is the single place a feed's own contents are turned into categories,
    so the rule that an unreadable archive is not graded cannot be
    reimplemented, or forgotten, at one of the four call sites that score a feed
    (the daily run, ``scorecard try``, the validator canary, and reproduction).

    Returns whichever of freshness and rider experience were measurable, which
    may be one of the two: a feed with stops and trips but no calendar at all
    still has a measurable rider experience, and is still graded on it.
    Raises :class:`UnreadableFeedError` only when neither was measurable, which
    is to say when the archive described no service at all.
    """
    from .completeness import completeness
    from .gtfs import read_feed_dates
    from .metrics import freshness

    measured = [
        category
        for category in (
            freshness(read_feed_dates(reader_path), today=today, service_type=service_type),
            completeness(reader_path, fare_free=fare_free),
        )
        if category is not None
    ]
    if not measured:
        raise UnreadableFeedError(NOTHING_WAS_READ)
    return measured


#: The lead fix when the configured feed URL failed and an expired Mobility
#: Database mirror copy was scored instead (hold_mirror_freshness).
FEED_DOWNLOAD_FAILED = "scorecard_feed_download_failed"

#: Plain words for the exception class fetch.py records as ``origin_error``.
_ORIGIN_ERROR_WORDS = {
    "SSLError": "its HTTPS certificate was not accepted",
    "HTTPError": "the server answered with an error instead of the file",
    "ConnectTimeout": "the server did not answer in time",
    "ReadTimeout": "the server stopped sending data before the file finished",
    "Timeout": "the server did not answer in time",
    "ConnectionError": "the connection to the server failed",
    "ChunkedEncodingError": "the download was cut off partway through",
    "ContentDecodingError": "the download was cut off partway through",
    "UnresolvableHostError": "its host name does not resolve",
    "TooManyRedirects": "the address redirects in a loop",
}


def hold_mirror_freshness(
    categories: list[CategoryResult],
    *,
    fetch_source: str,
    configured_url: str,
    origin_error: str | None,
) -> tuple[list[CategoryResult], dict[str, dict[str, Any]], Finding] | None:
    """Stop grading a mirror copy's lapsed calendar as the agency's own.

    When the configured URL fails, fetch.py scores the Mobility Database's
    hosted copy instead. That copy is whatever the catalog last cached,
    sometimes years old, so "service ended 670 days ago" describes the copy,
    not the feed the agency publishes today. Grading it as freshness 0 put an
    F on current feeds (SacRT, Grand Valley Transit) and led with "re-export
    your calendar" for agencies whose calendars were fine. Absence is not a
    value: freshness of the current feed is unknown, so it is held out of the
    grade the way unmeasured realtime is, and the one thing we do know --
    the feed could not be downloaded -- becomes the first fix.

    Returns None (nothing to change) unless the bytes came from the mirror
    and that copy's service has already ended. A mirror copy that is still
    current is graded normally; its dates still describe live service.
    Otherwise returns the categories without freshness, the held freshness
    entry, and the lead fix.
    """
    if fetch_source != "mirror":
        return None
    fresh = next((c for c in categories if c.name == "freshness"), None)
    if fresh is None:
        return None
    days = fresh.details.get("days_until_expiry")
    if not isinstance(days, int) or days >= 0:
        return None
    start = fresh.details.get("feed_start_date")
    end = fresh.details.get("effective_expiry_date") or fresh.details.get("last_service_date")
    ended = f" ended its service on {end}" if end else "'s service has ended"
    held = {
        "reason": "mirror_copy_expired",
        "summary": (
            "Not graded. The feed URL on file could not be downloaded, and the "
            f"Mobility Database mirror copy scored instead{ended}. That date "
            "describes the copy, not the feed the agency publishes today, so it "
            "does not count against the grade."
        ),
        # The copy's dates under their own key, never days_until_expiry: an
        # expiry countdown here would be counted as the agency's lapse again.
        "mirror_copy": {"service_start": start, "service_end": end},
    }
    from urllib.parse import urlsplit

    words = _ORIGIN_ERROR_WORDS.get(origin_error or "", "the download failed")
    host = urlsplit(configured_url).hostname or configured_url
    timeout = origin_error in {"ConnectTimeout", "ReadTimeout", "Timeout", "ConnectionError"}
    lead = Finding(
        code=FEED_DOWNLOAD_FAILED,
        severity="ERROR",
        count=1,
        what=f"The feed URL on file, {configured_url}, could not be downloaded: {words}.",
        why=(
            "Trip planners download the feed from that address too. The grade here "
            f"was measured on an older Mobility Database copy whose service ended {end}, "
            "so freshness is not graded until the current feed can be downloaded."
            if end
            else "Trip planners download the feed from that address too. The grade here "
            "was measured on an older Mobility Database copy, so freshness is not "
            "graded until the current feed can be downloaded."
        ),
        fix=(
            f"Renew or repair the HTTPS certificate on {host}, so apps can download "
            "the feed without a certificate error."
            if origin_error == "SSLError"
            else f"Restore the {host} address, or publish the new feed address so apps "
            "and this scorecard can find the feed."
            if origin_error == "UnresolvableHostError"
            else f"Check that {configured_url} still serves your current feed. If the "
            "feed moved, publish the new address."
            if origin_error == "HTTPError"
            else f"Make sure {configured_url} answers requests from outside your "
            "network. Some firewalls block the cloud servers that trip planners "
            "download from."
            if timeout
            else f"Make sure {configured_url} serves your current feed to anyone who requests it."
        ),
        effort="Usually a server or hosting setting, not a change to the feed itself.",
        deduction=0.0,
    )
    return [c for c in categories if c.name != "freshness"], {"freshness": held}, lead


def build_scorecard(
    categories: list[CategoryResult],
    *,
    held: dict[str, dict[str, Any]] | None = None,
    lead_fix: Finding | None = None,
) -> Scorecard:
    """Weight measured categories into an overall 0-100 score and pick the
    three highest-impact fixes (most rider-affecting first).

    ``held`` and ``lead_fix`` come from :func:`hold_mirror_freshness`: a held
    category is shown with its reason and never weighted, and the lead fix is
    ranked first ahead of the scored findings."""
    if len({c.name for c in categories}) != len(categories):
        raise ValueError("duplicate category name in scorecard input")
    measured = {c.name: c for c in categories}
    if not measured:
        raise ValueError("at least one measured category is required")

    total_weight = sum(CATEGORY_WEIGHTS[name] for name in measured)
    overall = sum(c.score * (CATEGORY_WEIGHTS[c.name] / total_weight) for c in measured.values())

    # Only findings that actually move the score are candidate "top fixes"; a
    # zero-deduction note (e.g. an informational finding) is never surfaced as
    # something to fix first.
    all_findings = [f for c in measured.values() for f in c.findings if f.deduction > 0]
    lead = [lead_fix] if lead_fix is not None else []
    top = lead + sorted(all_findings, key=_fix_priority)[: 3 - len(lead)]

    return Scorecard(
        overall_score=overall,
        grade=str(published_overall(overall)["grade"]),
        categories=measured,
        top_fixes=top,
        held=dict(held or {}),
    )


def build_scorecard_for_fetch(
    categories: list[CategoryResult],
    *,
    fetch_source: str,
    configured_url: str,
    origin_error: str | None,
) -> Scorecard:
    """build_scorecard, with an expired mirror copy's freshness held out.

    The one entry point for every caller that knows how the bytes were
    fetched (the daily run and reproduction), so they cannot disagree."""
    hold = hold_mirror_freshness(
        categories,
        fetch_source=fetch_source,
        configured_url=configured_url,
        origin_error=origin_error,
    )
    if hold is None:
        return build_scorecard(categories)
    kept, held, lead = hold
    return build_scorecard(kept, held=held, lead_fix=lead)
