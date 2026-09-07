"""The pace ring counts work done, not work dated.

`crm.today._pace`'s own docstring is the argument for this file:

    The numerator used to be every touch of any kind. Measured on the
    founder's live data it read 9/14 in a week he had sent nothing at all
    ... A progress meter that fills while you do nothing is the same class
    of over-claim as a "New" badge that means "we imported it" — the goal
    was always honest, the numerator never was.

That fix removed the wrong KINDS from the numerator and left the window
open at the top: `ts__date__gte=week_start` has a floor and no ceiling, so
a touch dated in the future is counted as work already done.

Future-dated touches are not hypothetical here. `crm.services.log_touch`
takes `now=` — "when the interaction actually happened, if known (e.g. a
captured email's Date header)" — and neither the Gmail path nor the sent
sweep clamps a skewed header to the present. `crm.today._recent_activity`
names the same shape in its own comment ("a chat hand-logged with
tomorrow's date, or a caller whose clock runs behind the touch's") and
says `networkly_domain.cadence` and `.scoring` both guard it rather than
assume it cannot happen.

The rail's answer to that shape is to clamp the printed number and keep the
row, which is a deliberate, documented decision about a display. The ring
is not a display of one row; it is a count, and it feeds `_daily_cap`.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone as dt_timezone
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from crm.models import Contact, Touch
from crm.today import PACE_TOUCH_KINDS, _daily_cap, _pace

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def student():
    return User.objects.create_user(
        email="pace@example.com", password="x", weekly_touch_goal=10)


@pytest.fixture
def jane(student):
    return Contact.all_objects.create(user=student, name="Jane Banker")


def _touch(student, jane, *, kind="outreach", at):
    return Touch.all_objects.create(
        user=student, contact=jane, kind=kind, channel="email", ts=at)


def _earlier_this_week(delta):
    """`now - delta`, but never before today's local midnight.

    The ring's floor is the Monday of the current week, so "two hours ago"
    is only inside the window when today has been running for two hours.
    On a Monday between 00:00 and 02:00 (the project clock is UTC) a plain
    `now() - 2h` lands on Sunday, and CI on 7 September 2026 at 00:57 UTC
    saw exactly that: `assert 0 == 2`. Midnight today is always on or after
    the floor and never after now, so it is the safe near edge.
    """
    now = timezone.now()
    midnight = timezone.make_aware(
        datetime.combine(timezone.localdate(), time.min))
    return max(midnight, now - delta)


def test_outreach_is_one_of_the_kinds_the_ring_counts():
    """A fence: if `outreach` ever leaves `PACE_TOUCH_KINDS`, every
    assertion below would pass for the wrong reason."""
    assert "outreach" in PACE_TOUCH_KINDS


def test_a_touch_dated_tomorrow_is_not_work_done_this_week(student, jane):
    """Three days out is still on the near side of the ring's only bound,
    which is a floor. Nothing has been sent."""
    today = timezone.localdate()
    _touch(student, jane, at=timezone.now() + timedelta(days=3))

    assert _pace(student, today)["done"] == 0


def test_a_future_touch_does_not_shrink_todays_plan(student, jane):
    """The consequence, and the reason this is not only a cosmetic count.
    `_daily_cap` divides what is LEFT of the weekly goal across the working
    days that remain, so every phantom credit in the numerator takes work
    off today's queue. A chat hand-logged for next week makes the student's
    plan smaller today."""
    today = timezone.localdate()
    for day in range(1, 9):
        _touch(student, jane, at=timezone.now() + timedelta(days=day))

    pace = _pace(student, today)

    assert pace["done"] == 0
    assert pace["remaining"] == 10
    assert _daily_cap(pace["goal"], pace["done"], today) == _daily_cap(10, 0, today)


def test_the_ring_never_claims_progress_the_student_has_not_made(student, jane):
    """`hit` and `pct` are the same number wearing different clothes. A week
    whose entire goal sits in the future must not read as finished."""
    today = timezone.localdate()
    for day in range(1, 11):
        _touch(student, jane, at=timezone.now() + timedelta(days=day))

    pace = _pace(student, today)

    assert pace["pct"] == 0
    assert not pace["hit"]


# ---------------------------------------------------------------------------
# The floor and the present are unchanged. These are the fence around the fix.
# ---------------------------------------------------------------------------

def test_a_touch_logged_earlier_today_still_counts(student, jane):
    today = timezone.localdate()
    _touch(student, jane, at=_earlier_this_week(timedelta(minutes=5)))

    assert _pace(student, today)["done"] == 1


def test_a_touch_logged_at_this_very_moment_still_counts(student, jane):
    """The boundary is inclusive of now: a touch written by the request
    being served must not fall off the edge of its own count."""
    today = timezone.localdate()
    _touch(student, jane, at=timezone.now())

    assert _pace(student, today)["done"] == 1


def test_a_touch_from_before_this_week_still_does_not_count(student, jane):
    today = timezone.localdate()
    _touch(student, jane, at=timezone.now() - timedelta(days=today.weekday() + 3))

    assert _pace(student, today)["done"] == 0


def test_a_mix_counts_only_the_part_that_has_happened(student, jane):
    today = timezone.localdate()
    _touch(student, jane, at=_earlier_this_week(timedelta(hours=2)))
    _touch(student, jane, kind="follow_up",
           at=_earlier_this_week(timedelta(hours=1)))
    _touch(student, jane, kind="thank_you", at=timezone.now() + timedelta(days=2))

    assert _pace(student, today)["done"] == 2


def test_the_mix_still_counts_two_in_the_first_hours_of_a_monday(student, jane):
    """The clock CI failed under, pinned: Monday 7 September 2026, 00:57 UTC.
    The week floor is that same day, so anything dated "earlier" must stay on
    the Monday side of midnight to be work done this week."""
    monday_early = datetime(2026, 9, 7, 0, 57, tzinfo=dt_timezone.utc)
    with mock.patch("django.utils.timezone.now", return_value=monday_early):
        today = timezone.localdate()
        assert today.weekday() == 0
        _touch(student, jane, at=_earlier_this_week(timedelta(hours=2)))
        _touch(student, jane, kind="follow_up",
               at=_earlier_this_week(timedelta(hours=1)))
        _touch(student, jane, kind="thank_you",
               at=timezone.now() + timedelta(days=2))

        assert _pace(student, today)["done"] == 2
