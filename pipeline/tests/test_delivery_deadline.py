"""The two-business-day delivery promise, and the machinery behind it.

`/bundle/` tells a buyer, on a page taking real money, that the archive
arrives "always within two business days. If it is later than that, the
purchase is refunded." That is a refund liability, so these check the date
behind it rather than the sentence describing it.
"""

from __future__ import annotations

import datetime as dt
import decimal
import json
import re
from pathlib import Path

import pytest

from scorecard_pipeline import deadline, program_refunds

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "web" / "bundle" / "plan.json"

# How the number is spelled where a buyer reads it. A digit and a word are two
# renderings of one promise and both have to track the constant.
_SPELLED = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five"}


def _at(iso: str) -> dt.datetime:
    return dt.datetime.fromisoformat(iso)


# ---------------------------------------------------------------------------
# one promise, one number
# ---------------------------------------------------------------------------


def test_the_promise_cannot_disagree_with_itself() -> None:
    """The buyer-facing text and the computation must quote one number.

    `web/bundle/plan.json` feeds the purchase page, the prose on two pages
    spells it as a word, and `deadline.PROVISIONING_BUSINESS_DAYS` is what
    actually computes the date an order is held to. Three renderings of one
    commitment: if any drifts, a buyer is told one thing and refunded on
    another, and nobody finds out until it matters.
    """
    days = deadline.PROVISIONING_BUSINESS_DAYS
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    assert plan["provisioning_business_days"] == days, (
        "the purchase page renders from plan.json and the deadline is computed "
        "from the constant; they are the same promise"
    )

    spelled = _SPELLED[days]
    for page in ("web/bundle/index.html", "web/bundle/setup/index.html"):
        text = (ROOT / page).read_text(encoding="utf-8")
        assert f"{spelled} business days" in text, page
        # And no OTHER count of business days on the same page, which is how a
        # half-finished edit leaves two promises standing.
        others = {
            match
            for match in re.findall(r"([a-z]+) business days", text)
            if match != spelled and match in _SPELLED.values()
        }
        assert not others, f"{page} states a different promise as well: {others}"

    docs = (ROOT / "docs" / "program-plan.md").read_text(encoding="utf-8")
    assert f"{spelled} business days" in docs


def test_the_refund_promise_is_still_stated_where_the_buyer_buys() -> None:
    """The machinery is worth nothing if the commitment quietly disappears
    from the page. If the promise is ever withdrawn that should be a
    deliberate edit that fails here first."""
    text = (ROOT / "web" / "bundle" / "index.html").read_text(encoding="utf-8")
    assert "refunded" in text


# ---------------------------------------------------------------------------
# the calendar
# ---------------------------------------------------------------------------


def test_two_business_days_skips_weekends() -> None:
    # Thursday 10 September 2026 -> Monday 14th, not Saturday 12th.
    assert deadline.deadline_date(_at("2026-09-10T09:00:00+00:00")) == dt.date(2026, 9, 14)
    # Friday -> Tuesday.
    assert deadline.deadline_date(_at("2026-09-11T09:00:00+00:00")) == dt.date(2026, 9, 15)
    # Monday -> Wednesday.
    assert deadline.deadline_date(_at("2026-09-14T09:00:00+00:00")) == dt.date(2026, 9, 16)


def test_the_hour_of_the_checkout_never_shortens_the_promise() -> None:
    """Counting starts the day after, so one minute past midnight and one
    minute to midnight on the same day are promised the same date. A clock
    that could shave a day off is the direction this must never fail in."""
    early = deadline.deadline_date(_at("2026-09-14T07:01:00+00:00"))
    late = deadline.deadline_date(_at("2026-09-15T06:59:00+00:00"))
    assert early == late == dt.date(2026, 9, 16)


def test_federal_holidays_are_not_business_days() -> None:
    """Independence Day 2026 falls on a Saturday, so it is observed on Friday
    3 July. A Thursday 2 July checkout therefore lands on Tuesday 7 July: the
    observed holiday, then the weekend, then two business days."""
    assert deadline.deadline_date(_at("2026-07-02T12:00:00+00:00")) == dt.date(2026, 7, 7)
    assert not deadline.is_business_day(dt.date(2026, 7, 3))
    assert deadline.is_business_day(dt.date(2026, 7, 2))


def test_the_holiday_rules_do_not_expire() -> None:
    """Computed from the rules, not listed, so there is no year at which this
    silently starts treating a holiday as a working day. Spot-checked against
    the observation shifts in both directions."""
    for year in range(2026, 2041):
        holidays = deadline.federal_holidays(year)
        assert len(holidays) == 11, year
        assert all(isinstance(day, dt.date) for day in holidays)
    # Saturday 4 July 2026 is observed on the Friday; Sunday 25 December 2033
    # is observed on the Monday.
    assert dt.date(2026, 7, 3) in deadline.federal_holidays(2026)
    assert dt.date(2033, 12, 26) in deadline.federal_holidays(2033)
    # Thanksgiving is the fourth Thursday, not the last one.
    assert dt.date(2030, 11, 28) in deadline.federal_holidays(2030)


def test_the_deadline_is_the_end_of_the_promised_day() -> None:
    """A bare date reads as end of day, and a deadline enforced earlier than
    the buyer would read it is the unfair direction."""
    at = _at("2026-09-14T09:00:00+00:00")
    day = deadline.deadline_date(at)
    end = deadline.deadline_epoch(at)
    assert dt.datetime.fromtimestamp(end, tz=dt.UTC).astimezone(deadline._zone()).date() == day
    assert dt.datetime.fromtimestamp(end, tz=dt.UTC).astimezone(deadline._zone()).hour == 23


def test_the_spoken_date_names_the_weekday_and_no_year() -> None:
    assert deadline.spoken_date(dt.date(2026, 9, 16)) == "Wednesday 16 September"
    sentence = deadline.promise_sentence(_at("2026-09-14T09:00:00+00:00"))
    assert "Wednesday 16 September" in sentence
    assert "refunded" in sentence


def test_business_days_after_refuses_a_negative_count() -> None:
    with pytest.raises(ValueError, match="negative"):
        deadline.business_days_after(dt.date(2026, 9, 14), -1)


# ---------------------------------------------------------------------------
# breach, and what a person does about it
# ---------------------------------------------------------------------------


def test_a_breach_needs_a_promise_a_deadline_and_no_archive() -> None:
    promised = deadline.deadline_epoch(_at("2026-09-14T09:00:00+00:00"))
    after = dt.datetime.fromtimestamp(promised + 3600, tz=dt.UTC)
    before = dt.datetime.fromtimestamp(promised - 3600, tz=dt.UTC)

    assert deadline.is_breached(promised, now=after, archive_present=False)
    # Delivered is never a breach, however late.
    assert not deadline.is_breached(promised, now=after, archive_present=True)
    # Not yet due is late at worst.
    assert not deadline.is_breached(promised, now=before, archive_present=False)
    # A row that made no promise cannot breach one. That is a subscription
    # refresh, or a row written before this field existed.
    for absent in (None, "", "soon"):
        assert not deadline.is_breached(absent, now=after, archive_present=False)


def test_the_promise_reader_accepts_the_type_dynamodb_actually_returns() -> None:
    """The breach rule reads a number out of DynamoDB, and DynamoDB's number
    is not Python's.

    ``common.bundle_row`` writes ``deliver_by_epoch`` as an ``int``; boto3's
    resource layer stores that as ``{"N": "..."}`` and hands it back as a
    ``decimal.Decimal``. Measured against boto3 1.43.93:
    ``TypeSerializer().serialize(1789603199)`` is ``{'N': '1789603199'}`` and
    ``TypeDeserializer().deserialize(...)`` is ``Decimal('1789603199')``,
    for which ``isinstance(value, int | float)`` is ``False``.

    A reader written that way refused every promise this product has ever
    made, so no order could breach, the reconciler's title could never
    escalate to REFUND DUE and `scorecard program-refunds` always printed
    "no orders past the promise". The fake tables in
    test_program_bundle_handlers.py hand back the object they were given, so
    only the real type catches it. This is that type, named here once.
    """
    epoch = deadline.deadline_epoch(_at("2026-09-14T09:00:00+00:00"))

    for readable in (epoch, float(epoch), decimal.Decimal(epoch), str(epoch)):
        assert deadline.promised_epoch(readable) == float(epoch), readable

    # Absent, unreadable, or a bool -- none of which is a promise. `True` is
    # an `int`, and without the bool rule it would read as a deadline one
    # second after the epoch and breach on sight.
    unreadable: tuple[object, ...] = (None, "", "soon", True, False, float("nan"), [], {})
    for absent in unreadable:
        assert deadline.promised_epoch(absent) is None, absent


def test_a_breach_and_its_lateness_survive_the_storage_round_trip() -> None:
    """The same order, decided the same way, whichever of the two types the
    row arrives as. This is the assertion the live reader failed."""
    epoch = deadline.deadline_epoch(_at("2026-09-14T09:00:00+00:00"))
    after = dt.datetime.fromtimestamp(epoch + 86400, tz=dt.UTC)

    stored = decimal.Decimal(epoch)  # what a scan of the bundles table returns
    assert deadline.is_breached(stored, now=after, archive_present=False)
    assert deadline.days_late(stored, now=after) == deadline.days_late(epoch, now=after) == 1.0
    assert not deadline.is_breached(stored, now=after, archive_present=True)


def test_the_promise_reads_back_as_the_day_the_buyer_was_told() -> None:
    """The stored epoch is the last second of the promised day in the
    promise's own zone, which is the next morning in UTC. Reading it back in
    UTC names a day the buyer was never told, on the one report whose job is
    to settle whether that day was met."""
    checkout = _at("2026-09-14T09:00:00+00:00")
    told = deadline.deadline_date(checkout)
    epoch = deadline.deadline_epoch(checkout)

    assert told.isoformat() == "2026-09-16"
    assert deadline.promised_day(epoch) == told
    assert deadline.promised_day(decimal.Decimal(epoch)) == told
    # The bug this replaced, stated so it cannot come back by accident.
    assert dt.datetime.fromtimestamp(epoch, tz=dt.UTC).date() != told
    assert deadline.promised_day(None) is None


def _row(bundle_id: str, promised: int | None, **extra: object) -> dict[str, object]:
    row: dict[str, object] = {
        "bundle_id": bundle_id,
        "session_id": "cs_test_exampleref",
        "deliver_to": "liaison@example.org",
        "program_name": "Example Program",
    }
    if promised is not None:
        row["deliver_by_epoch"] = promised
    row.update(extra)
    return row


def test_the_refund_list_names_only_orders_that_are_actually_owed() -> None:
    promised = deadline.deadline_epoch(_at("2026-09-14T09:00:00+00:00"))
    now = dt.datetime.fromtimestamp(promised + 86400 * 2, tz=dt.UTC)
    rows = [
        _row("a" * 32, promised),  # breached
        _row("b" * 32, promised),  # built, so not breached
        _row("c" * 32, None),  # a refresh: no promise was made
        _row("d" * 32, promised + 86400 * 30),  # not due yet
        {"bundle_id": "session#cs_x", "deliver_by_epoch": promised},  # not an order
        {"bundle_id": "checkout#cs_y", "deliver_by_epoch": promised},  # not an order
    ]
    orders = program_refunds.breached_orders(rows, archive_present=lambda b: b == "b" * 32, now=now)
    assert [o["bundle_id"] for o in orders] == ["a" * 32]
    assert orders[0]["days_late"] == 2.0
    assert orders[0]["session_id"] == "cs_test_exampleref"


def test_the_refund_list_reads_the_table_as_the_table_answers_it() -> None:
    """`scorecard program-refunds` scans the real bundles table, so every row
    it sees carries `Decimal`, not `int`. Listed with the type it was written
    as and the type it is read back as, the answer has to be the same order
    and the same lateness; the list that decides whether money is owed cannot
    depend on which of the two a fixture happened to use.

    And the date it prints is the date the buyer was told, in the promise's
    own zone -- not the UTC morning after it.
    """
    checkout = _at("2026-09-14T09:00:00+00:00")
    told = deadline.deadline_date(checkout)
    promised = deadline.deadline_epoch(checkout)
    now = dt.datetime.fromtimestamp(promised + 86400 * 2, tz=dt.UTC)
    stored = [_row("a" * 32, None, deliver_by_epoch=decimal.Decimal(promised))]

    orders = program_refunds.breached_orders(stored, archive_present=lambda _b: False, now=now)
    assert [o["bundle_id"] for o in orders] == ["a" * 32]
    assert orders[0]["days_late"] == 2.0
    assert orders[0]["promised_by"] == told.isoformat() == "2026-09-16"
    assert told.isoformat() in program_refunds.render(orders, now=now)

    as_written = program_refunds.breached_orders(
        [_row("a" * 32, promised)], archive_present=lambda _b: False, now=now
    )
    assert as_written == orders, "the stored type must not change the answer"


def test_the_refund_report_prints_commands_and_runs_nothing() -> None:
    """The deployed Stripe key is restricted to reading Checkout Sessions and
    cannot refund, deliberately. This is the other half of that posture: the
    person sees the exact commands and decides. A tool that could move money
    on a schedule is not wanted here."""
    promised = deadline.deadline_epoch(_at("2026-09-14T09:00:00+00:00"))
    now = dt.datetime.fromtimestamp(promised + 86400, tz=dt.UTC)
    orders = program_refunds.breached_orders(
        [_row("a" * 32, promised)], archive_present=lambda _b: False, now=now
    )
    report = program_refunds.render(orders, now=now)

    assert "stripe refunds create" in report
    assert "cs_test_exampleref" in report
    assert "liaison@example.org" in report, "local output may name the order; that is the point"
    assert "refunded" in report

    source = (ROOT / "pipeline" / "src" / "scorecard_pipeline" / "program_refunds.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("subprocess", "os.system", "stripe.Refund", "requests.post", "urllib"):
        assert forbidden not in source, f"the refund path must not be able to execute: {forbidden}"


def test_the_report_says_so_plainly_when_nothing_is_owed() -> None:
    """An empty report has to read as an answer, not as a tool that did not
    run. This is the shape that gets mistaken for success everywhere else in
    this codebase."""
    report = program_refunds.render([], now=_at("2026-09-16T09:00:00+00:00"))
    assert "No program orders are past" in report
    assert "2026-09-16" in report


def test_the_page_prints_the_date_it_was_given_and_computes_none_of_it() -> None:
    """The other half of "one promise, one number": the browser must not work
    the date out for itself.

    A second implementation of a business-day calculation in JavaScript would
    pass every test here and still disagree with the server the first time a
    public holiday fell between the checkout and the deadline. The server
    computes it, stores it against the order, and sends the sentence; the page
    prints what it was given.
    """
    script = (ROOT / "web" / "src" / "bundle-setup.js").read_text(encoding="utf-8")
    assert "body.promise" in script, "the page must render the server's sentence"

    body = script[script.index("resp.ok && body.ok") :]
    body = body[: body.index("enable(true)")]
    # Comments are stripped first. A gate that reads prose fires on the note
    # explaining why the rule exists, which is how these get weakened.
    code = "\n".join(line.split("//")[0] for line in body.splitlines())
    for arithmetic in ("Date(", "getDay", "getMonth", "setDate", "86400", "toLocaleDateString"):
        assert arithmetic not in code, (
            f"the confirmation computes its own deadline ({arithmetic}); the promise "
            "is one function in one language"
        )
