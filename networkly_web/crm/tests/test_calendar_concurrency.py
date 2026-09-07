"""Calendar changes must read the latest committed revision before writing."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone as dt_timezone
from threading import Event

import pytest
from django.db import close_old_connections, connection, transaction
from django.test import RequestFactory
from django.utils import timezone

from accounts.models import User
from crm import calendar_views
from crm.models import CalendarEvent


@pytest.mark.django_db(transaction=True)
def test_reschedule_waits_for_the_current_revision_and_duration(monkeypatch):
    if connection.vendor != "postgresql":
        pytest.skip("requires PostgreSQL row locks")
    user = User.objects.create_user(email="calendar-race@example.com", password="x")
    start = datetime(2026, 9, 7, 10, tzinfo=dt_timezone.utc)
    event = CalendarEvent.all_objects.create(
        user=user, title="Interview", starts_at=start, ends_at=start + timedelta(hours=1),
    )
    entered, read = Event(), Event()
    original = calendar_views._own_manual_event

    def observe_read(user, pk):
        entered.set()
        row = original(user, pk)
        read.set()
        return row

    monkeypatch.setattr(calendar_views, "_own_manual_event", observe_read)

    def reschedule():
        close_old_connections()
        try:
            request = RequestFactory().post("/app/calendar/reschedule/", {
                "day": "2026-09-08", "at": "15:00",
            })
            request.user = user
            with timezone.override("UTC"):
                return calendar_views.calendar_reschedule(request, event.pk).status_code
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with transaction.atomic():
            current = CalendarEvent.objects.for_user(user).select_for_update().get(pk=event.pk)
            future = pool.submit(reschedule)
            assert entered.wait(5), "reschedule worker did not start"
            blocked_on_revision = not read.wait(0.2)
            current.ics_sequence = 7
            current.ends_at = start + timedelta(hours=2)
            current.save(update_fields=["ics_sequence", "ends_at"])
        assert future.result(timeout=5) == 302

    assert blocked_on_revision, "reschedule read an obsolete revision without waiting for its writer"
    event.refresh_from_db()
    assert event.ics_sequence == 8
    assert event.starts_at == datetime(2026, 9, 8, 15, tzinfo=dt_timezone.utc)
    assert event.ends_at - event.starts_at == timedelta(hours=2)
