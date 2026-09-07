"""The burst guard's day, and the usage line's month, belong to the student.

`billing.credits`'s module docstring is explicit that these functions are
called from two places: mid-request, where `accounts.middleware.
TimezoneMiddleware` has already activated the student's own zone, and from a
bare cron tick (`gmail_backfill`, `autopilot`) where nothing is activated at
all and `get_current_timezone()` is therefore `settings.TIME_ZONE` — "UTC".

Every test here runs with NOTHING activated, which is the cron shape. A
student in `America/Los_Angeles` is seven or eight hours behind UTC, so
"midnight, their time" and "midnight UTC" are different instants and the
window between them is where a spend gets counted against the wrong day.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.utils import timezone

from billing import credits
from billing.models import CreditLedger

User = get_user_model()

pytestmark = pytest.mark.django_db

LA = ZoneInfo("America/Los_Angeles")

_PLANS = {
    "free": {"monthly_grant": 60, "message_cost": 1, "daily_burst": 15},
    "pro": {"monthly_grant": 180, "message_cost": 3, "daily_burst": 45},
}


@pytest.fixture
def angeleno():
    """The founder's own account shape: `User.timezone` is
    `America/Los_Angeles` (see the memory note on timezone anchoring), not
    the blank default, which is what makes the skew visible at all."""
    return User.objects.create_user(
        email="la-student@example.com", password="x", timezone="America/Los_Angeles"
    )


@pytest.fixture
def frozen(monkeypatch):
    """Pin `django.utils.timezone.now`. `localdate()` reads the module
    global, so patching it there reaches every caller in `credits`."""

    def _freeze(instant):
        monkeypatch.setattr(timezone, "now", lambda: instant)
        return instant

    return _freeze


def _spend_at(user, cost, instant, kind=CreditLedger.KIND_SPEND_CHAT):
    """One spend row stamped at an exact instant. `created` is
    `auto_now_add`, so it has to be forced with a queryset update."""
    row = CreditLedger.all_objects.create(user=user, delta=-cost, kind=kind)
    CreditLedger.all_objects.filter(pk=row.pk).update(created=instant)
    return row


def _assert_cron_shape():
    """Nothing activated — the state a management command runs in."""
    assert timezone.get_current_timezone_name() == "UTC"


# ---------------------------------------------------------------------------
# The daily burst window
# ---------------------------------------------------------------------------
@override_settings(CREDIT_PLANS=_PLANS)
def test_the_burst_window_is_the_students_own_day_not_the_utc_day(angeleno, frozen):
    """2026-09-06, 18:30 in Los Angeles, which is already the 7th in UTC.

    Two spends, one on each side of UTC midnight:

      * 17:30 local (00:30Z on the 7th) — squarely today for the student
      * 19:00 local YESTERDAY (02:00Z on the 6th) — yesterday for them

    A window anchored on the student's local DATE but built with UTC's
    midnight spans `[Sep 6 00:00Z, Sep 7 00:00Z)`, which contains exactly
    the wrong one of those two.
    """
    _assert_cron_shape()
    frozen(dt.datetime(2026, 9, 7, 1, 30, tzinfo=dt.timezone.utc))  # 18:30 PDT, Sep 6

    _spend_at(angeleno, 5, dt.datetime(2026, 9, 7, 0, 30, tzinfo=dt.timezone.utc))  # 17:30 PDT Sep 6
    _spend_at(angeleno, 3, dt.datetime(2026, 9, 6, 2, 0, tzinfo=dt.timezone.utc))  # 19:00 PDT Sep 5

    assert credits.daily_spent(angeleno) == 5


@override_settings(CREDIT_PLANS=_PLANS)
def test_an_evening_spend_still_counts_against_tonights_burst_guard(angeleno, frozen):
    """The consequence, stated as the guard rather than the counter: five
    evening spends against a burst of five must close the gate. Under a UTC
    window every one of them lands on "tomorrow" and the guard never fires,
    which is the abuse backstop silently switched off between 5pm and
    midnight, every single day, for a West Coast account."""
    _assert_cron_shape()
    frozen(dt.datetime(2026, 9, 7, 1, 30, tzinfo=dt.timezone.utc))  # 18:30 PDT, Sep 6

    for minute in range(5):
        _spend_at(angeleno, 1, dt.datetime(2026, 9, 7, 0, minute, tzinfo=dt.timezone.utc))

    with override_settings(
        CREDIT_PLANS={"free": {"monthly_grant": 60, "message_cost": 1, "daily_burst": 5}}
    ):
        assert credits.daily_spent(angeleno) == 5
        assert not credits.can_spend(angeleno, 1)


@override_settings(CREDIT_PLANS=_PLANS)
def test_the_burst_window_covers_the_whole_twenty_five_hour_fall_back_day(angeleno, frozen):
    """1 November 2026 is the US fall-back: Los Angeles runs 2am PDT back to
    1am PST, so that local day is twenty-five hours long.

    A window whose end is `start + timedelta(days=1)` is twenty-four
    absolute hours and stops at 23:00 local, orphaning the last hour of the
    student's day. The end has to be midnight of the NEXT local date, not
    midnight plus a day.
    """
    _assert_cron_shape()
    frozen(dt.datetime(2026, 11, 2, 6, 0, tzinfo=dt.timezone.utc))  # 22:00 PST, Nov 1

    # 23:30 PST on 1 November — the twenty-fifth hour of that local day.
    _spend_at(angeleno, 4, dt.datetime(2026, 11, 2, 7, 30, tzinfo=dt.timezone.utc))
    # 00:30 PST on 2 November — the next local day, must not be counted.
    _spend_at(angeleno, 9, dt.datetime(2026, 11, 2, 8, 30, tzinfo=dt.timezone.utc))

    assert credits.daily_spent(angeleno) == 4


@override_settings(CREDIT_PLANS=_PLANS)
def test_a_blank_timezone_account_still_counts_its_utc_day(frozen):
    """The default `User.timezone` is blank, which resolves to the project
    zone. Nothing about the fix may move that account's window."""
    _assert_cron_shape()
    plain = User.objects.create_user(email="plain@example.com", password="x")
    frozen(dt.datetime(2026, 9, 6, 23, 0, tzinfo=dt.timezone.utc))

    _spend_at(plain, 2, dt.datetime(2026, 9, 6, 22, 0, tzinfo=dt.timezone.utc))
    _spend_at(plain, 7, dt.datetime(2026, 9, 5, 22, 0, tzinfo=dt.timezone.utc))

    assert credits.daily_spent(plain) == 2


# ---------------------------------------------------------------------------
# The monthly usage line
# ---------------------------------------------------------------------------
@override_settings(CREDIT_PLANS=_PLANS)
def test_month_usage_starts_at_the_students_own_first_of_the_month(angeleno, frozen):
    """1 September, 10:00 in Los Angeles. A spend at 20:00 on 31 August
    local is the PREVIOUS month's usage; anchoring the 1st at UTC midnight
    pulls it forward into September and makes the Settings "used N so far
    this month" line disagree with the balance beside it."""
    _assert_cron_shape()
    frozen(dt.datetime(2026, 9, 1, 17, 0, tzinfo=dt.timezone.utc))  # 10:00 PDT, Sep 1

    _spend_at(angeleno, 6, dt.datetime(2026, 9, 1, 3, 0, tzinfo=dt.timezone.utc))  # 20:00 PDT Aug 31
    _spend_at(angeleno, 2, dt.datetime(2026, 9, 1, 16, 0, tzinfo=dt.timezone.utc))  # 09:00 PDT Sep 1

    assert credits.month_usage(angeleno) == 2


@override_settings(CREDIT_PLANS=_PLANS)
def test_a_refund_still_nets_out_of_the_students_own_day(angeleno, frozen):
    """The netting rule in `_NET_SPEND_KINDS` has to survive the window fix:
    a spend and its refund on the same LOCAL evening cancel to zero."""
    _assert_cron_shape()
    frozen(dt.datetime(2026, 9, 7, 1, 30, tzinfo=dt.timezone.utc))  # 18:30 PDT, Sep 6

    _spend_at(angeleno, 4, dt.datetime(2026, 9, 7, 0, 30, tzinfo=dt.timezone.utc))
    _spend_at(angeleno, -4, dt.datetime(2026, 9, 7, 0, 40, tzinfo=dt.timezone.utc),
              kind=CreditLedger.KIND_REFUND)

    assert credits.daily_spent(angeleno) == 0
