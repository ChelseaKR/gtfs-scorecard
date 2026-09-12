"""When a program report bundle is promised by (docs/program-plan.md).

``/bundle/`` tells a buyer, on a page taking real money: the archive arrives
"normally within the hour and always within two business days. If it is later
than that, the purchase is refunded." That sentence is a refund liability, so
the date behind it has to be computed somewhere rather than believed.

**One function, one number.** ``PROVISIONING_BUSINESS_DAYS`` is the Python
side of the promise and ``web/bundle/plan.json``'s ``provisioning_business_days``
is the side the purchase page renders from.
``tests/test_delivery_deadline.py`` fails if they, or the prose that spells the
number in words, ever disagree. A promise computed twice is a promise that will
eventually contradict itself, and the contradiction will be discovered by the
buyer.

**Anchored to the checkout, not to the form.** The clock starts when Stripe
records the payment. A buyer who pays on Friday and fills in the setup form on
Monday was promised two business days from Friday, and reading the anchor off
the form would quietly hand us the weekend.

**America/Los_Angeles, end of day.** The buyer's timezone is unknown and
guessing it would be worse than choosing one and saying so. This one is
defensible: the promise is operational, kept by a person re-dispatching a
failed run, and that person and this project are in California. The deadline is
the end of that day in that zone, which is how a reader parses "by Tuesday 16
September" anyway.

**US federal holidays are not business days**, and they are computed from the
rules rather than listed. A hardcoded table of dates is a calendar bomb: it
passes every test until the year it silently runs out. The rules (nth weekday
of a month, plus the Saturday-to-Friday and Sunday-to-Monday observation
shifts) do not expire.
"""

from __future__ import annotations

import datetime as dt

# The promise, in days. `web/bundle/plan.json` carries the same number for the
# purchase page, and a test holds the two together.
PROVISIONING_BUSINESS_DAYS = 2

# Named so the reason travels with the value. See the module docstring.
DEADLINE_ZONE = "America/Los_Angeles"

_SATURDAY = 5
_SUNDAY = 6


def _nth_weekday(year: int, month: int, weekday: int, nth: int) -> dt.date:
    """The nth given weekday of a month; nth=-1 means the last one."""
    if nth < 0:
        last = (
            dt.date(year, month + 1, 1) - dt.timedelta(days=1)
            if month < 12
            else dt.date(year, 12, 31)
        )
        return last - dt.timedelta(days=(last.weekday() - weekday) % 7)
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(weekday - first.weekday()) % 7 + 7 * (nth - 1))


def _observed(day: dt.date) -> dt.date:
    """The day a fixed-date federal holiday is actually taken off."""
    if day.weekday() == _SATURDAY:
        return day - dt.timedelta(days=1)
    if day.weekday() == _SUNDAY:
        return day + dt.timedelta(days=1)
    return day


def federal_holidays(year: int) -> frozenset[dt.date]:
    """The eleven US federal holidays for a year, as observed.

    Computed from the rules, never from a table: a list of dates is correct
    until the year it runs out and says nothing when it does.
    """
    return frozenset(
        {
            _observed(dt.date(year, 1, 1)),  # New Year's Day
            _nth_weekday(year, 1, 0, 3),  # Martin Luther King, Jr. Day
            _nth_weekday(year, 2, 0, 3),  # Washington's Birthday
            _nth_weekday(year, 5, 0, -1),  # Memorial Day
            _observed(dt.date(year, 6, 19)),  # Juneteenth
            _observed(dt.date(year, 7, 4)),  # Independence Day
            _nth_weekday(year, 9, 0, 1),  # Labor Day
            _nth_weekday(year, 10, 0, 2),  # Columbus Day
            _observed(dt.date(year, 11, 11)),  # Veterans Day
            _nth_weekday(year, 11, 3, 4),  # Thanksgiving Day
            _observed(dt.date(year, 12, 25)),  # Christmas Day
        }
    )


def is_business_day(day: dt.date) -> bool:
    """Weekdays that are not an observed federal holiday."""
    return day.weekday() < _SATURDAY and day not in federal_holidays(day.year)


def business_days_after(start: dt.date, days: int) -> dt.date:
    """The date ``days`` business days after ``start``.

    Counting starts the day after ``start``, so a checkout at any hour of
    Monday is promised by end of Wednesday and not by end of Tuesday. The
    hour of the checkout never shortens the promise.
    """
    if days < 0:
        raise ValueError("days must not be negative")
    day = start
    remaining = days
    while remaining > 0:
        day += dt.timedelta(days=1)
        if is_business_day(day):
            remaining -= 1
    return day


def _zone() -> dt.tzinfo:
    from zoneinfo import ZoneInfo

    return ZoneInfo(DEADLINE_ZONE)


def deadline_date(checkout_at: dt.datetime) -> dt.date:
    """The date a checkout's bundle is promised by, in DEADLINE_ZONE."""
    local = checkout_at.astimezone(_zone()) if checkout_at.tzinfo else checkout_at
    return business_days_after(local.date(), PROVISIONING_BUSINESS_DAYS)


def deadline_epoch(checkout_at: dt.datetime) -> int:
    """The last second of the promised day, as a unix timestamp.

    End of day, because that is how a reader parses a bare date, and because
    a deadline the buyer would read as later than we enforce it is the one
    direction this must never fail in.
    """
    day = deadline_date(checkout_at)
    end = dt.datetime.combine(day, dt.time(23, 59, 59), tzinfo=_zone())
    return int(end.timestamp())


def from_epoch(checkout_epoch: int) -> dt.datetime:
    """A Stripe ``created`` timestamp as an aware datetime."""
    return dt.datetime.fromtimestamp(int(checkout_epoch), tz=dt.UTC)


def spoken_date(day: dt.date) -> str:
    """The date as the buyer is told it: "Tuesday 16 September".

    No year, no zero padding, no abbreviation. It is at most two business
    days away, so the year adds nothing and the weekday is the part a reader
    actually plans around.
    """
    return f"{day:%A} {day.day} {day:%B}"


def promise_sentence(checkout_at: dt.datetime) -> str:
    """The one sentence every buyer-facing surface says about timing.

    Every caller uses this rather than composing its own, so the confirmation
    page, the delivery email and anything added later cannot drift apart.
    """
    return (
        f"Your reports are promised by {spoken_date(deadline_date(checkout_at))}. "
        "If they are later than that, the purchase is refunded."
    )


def is_breached(deliver_by_epoch: object, *, now: dt.datetime, archive_present: bool) -> bool:
    """Whether an order is past the date it was promised by, with nothing built.

    The one rule. The reconciler reports breaches and `scorecard
    program-refunds` lists them for the person who has to act; if each decided
    for itself what "late" meant, the alert and the refund list would
    eventually disagree about the same order.

    A row with no readable ``deliver_by_epoch`` made no such promise. That is
    a subscription refresh, or a row written before this field existed, and
    neither can breach a commitment nobody gave. Such an order is not lost:
    it is still reported as undelivered, on the archive alone.
    """
    if archive_present or not isinstance(deliver_by_epoch, int | float):
        return False
    return now.timestamp() > float(deliver_by_epoch)


def days_late(deliver_by_epoch: object, *, now: dt.datetime) -> float | None:
    """How far past the promise, in days, or None when there was no promise."""
    if not isinstance(deliver_by_epoch, int | float):
        return None
    return (now.timestamp() - float(deliver_by_epoch)) / 86400
