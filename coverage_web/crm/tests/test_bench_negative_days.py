"""The bench cannot say a meeting happened a negative number of days ago.

`crm.today._recent_activity` already settled this question for the Recent
Activity rail, and settled it in writing:

    CLAMPED AT 0, not just falsy-checked. `recent` has no `ts__lte` guard
    ... so a touch dated after `as_of` sorts to the top of the feed rather
    than being excluded from it. An unclamped negative day count rendered
    "-2d ago" for a touch 2 days in the future -- a wrong result,
    demonstrated in `test_the_activity_rail_does_not_render_a_negative_day_count`.

`_opening_bench` computes the same figure the same way, off a query with the
same missing bound, and hands it to the template as `days_since`. The
template spends it directly:

    Last interaction {{ b.days_since }} day{{ b.days_since|pluralize }} ago

`_opening_keep_warms` is the third site and is already safe by accident: its
`idle < OPENING_MIN_IDLE_DAYS` gate drops anything negative before the number
can be shown. The bench has no such gate, so it is the one surface where the
string the rail refuses to print can still appear.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from crm.models import Contact, Touch, UserFirm
from crm.today import _opening_bench
from directory.models import Firm, FirmDate

pytestmark = pytest.mark.django_db(transaction=True)


def _user(**kw):
    return get_user_model().objects.create_user(
        email="bench-days@example.com", password="pw12345!", **kw)


def _firm_with_opening(user):
    """The same shape `test_bench.py::_firm_with_opening` uses: a tiered firm
    with a confirmed date inside `OPENING_HORIZON_DAYS` but outside
    `pre_deadline_reping_days`, so a warm parked contact benches without also
    tripping the engine's own branch-3 re-ping."""
    firm = Firm.objects.create(name="Nomura", slug="nomura-bench-days")
    UserFirm.all_objects.create(user=user, firm=firm, tier=1)
    FirmDate.objects.create(
        firm=firm, event_kind="app_close", region="us",
        date=timezone.localdate() + timedelta(days=34),
        confidence=1.0, precision="day",
    )
    return firm


def _bench_row(user, *, touch_at):
    firm = _firm_with_opening(user)
    katy = Contact.all_objects.create(
        user=user, name="Katy Chen", firm=firm, region="us",
        warmth="chatted", thread_state="parked",
    )
    Touch.all_objects.create(
        user=user, contact=katy, kind="chat", channel="email", ts=touch_at)
    rows = _opening_bench(user, list(Contact.objects.for_user(user)), [],
                          timezone.localdate())
    return rows[0] if rows else None


def test_a_future_touch_never_renders_a_negative_day_count():
    """A chat hand-logged with next week's date, or a captured header from a
    sender whose clock runs ahead. The bench must not report it as
    "Last interaction -4 days ago"."""
    row = _bench_row(_user(), touch_at=timezone.now() + timedelta(days=4))

    assert row is not None
    assert row["days_since"] >= 0


def test_a_touch_dated_today_reads_as_zero():
    """The clamp's own boundary, and the value the sentence is built for."""
    row = _bench_row(_user(), touch_at=timezone.now() - timedelta(hours=2))

    assert row is not None
    assert row["days_since"] == 0


def test_an_ordinary_past_touch_is_untouched():
    """The fence. Clamping the floor must not move any real figure."""
    row = _bench_row(_user(), touch_at=timezone.now() - timedelta(days=21))

    assert row is not None
    assert row["days_since"] == 21
