"""Journey 6: a meeting, and the calendar somebody subscribed to.

Nothing is mocked. The subscription feed is fetched over HTTP with no session
at all, exactly as a calendar client fetches it.

Two of this journey's three verbs do not exist as user actions, and the tests
that say so are named for it rather than skipped. RESCHEDULE has no route: the
only way to move an event is to remove it and add another, which mints a new
`UID` and therefore reads to every subscriber as "that meeting vanished and a
different one appeared". CANCEL has no route either: the page's Remove button
hard-deletes, so the feed never carries `STATUS:CANCELLED` for anything a
student cancelled themselves — only for a cancellation that arrived from their
mailbox or from Google. Both are pinned below as the behaviour that is really
there, so the day either gains a route the failing assertion is the reminder.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from crm.models import CalendarEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def student():
    return User.objects.create_user(
        email="scheduler@example.com", password="A-safe-passphrase-123",
        timezone="America/Los_Angeles", timezone_auto=False,
    )


@pytest.fixture
def signed_in(client, student):
    client.force_login(student)
    return client


@pytest.fixture
def day():
    """Inside the feed's own window (now-30d to now+400d), and never a literal."""
    return timezone.localdate() + dt.timedelta(days=21)


def _add(client, day, *, title="Superday, Journey Partners", at="09:30", kind="event"):
    return client.post(reverse("crm:calendar_add"), {
        "title": title, "kind": kind, "day": day.isoformat(), "at": at,
        "location": "New York", "description": "Bring the pitch",
    })


def _feed(client, student):
    student.refresh_from_db()
    response = client.get(reverse("crm:calendar_ics", args=[student.calendar_token]))
    return response, response.content.decode()


def _local(event, student):
    """The wall clock the STUDENT typed.

    Not `timezone.localtime`: the view activates the student's zone for the
    duration of the request and deactivates it after, so by the time a test
    reads the row the active zone is UTC again and `localtime` would answer
    in the wrong clock. The stored instant is right; the question is whose
    calendar you read it on.
    """
    return event.starts_at.astimezone(ZoneInfo(student.timezone)).strftime("%H:%M")


def _uid(event):
    return f"UID:coverage-ev-{event.pk}@coverage.app"


# ---------------------------------------------------------------------------
# Create


def test_a_meeting_added_by_hand_reaches_the_subscription_feed(signed_in, student, day):
    added = _add(signed_in, day)

    assert added.status_code == 302
    event = CalendarEvent.objects.for_user(student).get()
    assert event.title == "Superday, Journey Partners"
    assert event.source == CalendarEvent.SOURCE_MANUAL
    assert event.all_day is False
    assert _local(event, student) == "09:30"

    page = signed_in.get(reverse("crm:calendar"))
    assert page.status_code == 200
    assert "Superday, Journey Partners" in page.content.decode()

    response, body = _feed(signed_in, student)
    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/calendar")
    assert _uid(event) in body
    assert "SUMMARY:Superday\\, Journey Partners" in body
    assert "LOCATION:New York" in body
    assert "STATUS:CANCELLED" not in body


def test_the_feed_needs_no_session_and_the_wrong_token_is_a_404(client, signed_in, student, day):
    _add(signed_in, day)
    student.refresh_from_db()

    anonymous = client.get(reverse("crm:calendar_ics", args=[student.calendar_token]))
    assert anonymous.status_code == 200
    assert "Superday" in anonymous.content.decode()

    assert client.get(reverse("crm:calendar_ics", args=["not-this-token"])).status_code == 404


def test_a_bad_date_keeps_the_typed_values_instead_of_clearing_the_form(signed_in, student):
    response = signed_in.post(reverse("crm:calendar_add"), {
        "title": "Superday", "kind": "event", "day": "not-a-date", "at": "09:30",
    })

    assert response.status_code == 400
    assert response.context["form_open"] is True
    assert "Superday" in response.content.decode()
    assert not CalendarEvent.objects.for_user(student).exists()


# ---------------------------------------------------------------------------
# Reschedule — and what actually happens instead


def test_there_is_no_reschedule_route_so_moving_a_meeting_mints_a_new_uid(signed_in, student, day):
    """DOCUMENTS A GAP, and fails the day it closes.

    A student who typed the wrong hour has one move available: remove the
    event and add it again. That is a different row, so the subscription feed
    loses one UID and gains another, and a subscribed client shows the meeting
    disappearing rather than moving.
    """
    _add(signed_in, day, at="09:30")
    original = CalendarEvent.objects.for_user(student).get()

    signed_in.post(reverse("crm:calendar_delete", args=[original.pk]))
    _add(signed_in, day, at="14:00")
    moved = CalendarEvent.objects.for_user(student).get()

    assert moved.pk != original.pk, "no route updates an event in place"
    _, body = _feed(signed_in, student)
    assert _uid(original) not in body
    assert _uid(moved) in body
    assert _local(moved, student) == "14:00"


# ---------------------------------------------------------------------------
# Cancel — and what actually happens instead


def test_removing_an_event_drops_it_from_the_feed_rather_than_cancelling_it(signed_in, student, day):
    """DOCUMENTS A GAP, and fails the day it closes.

    The page's only removal control hard-deletes. The feed therefore never
    says `STATUS:CANCELLED` about anything the student cancelled themselves;
    the event simply stops being there.
    """
    _add(signed_in, day)
    event = CalendarEvent.objects.for_user(student).get()
    assert _uid(event) in _feed(signed_in, student)[1]

    removed = signed_in.post(reverse("crm:calendar_delete", args=[event.pk]))

    assert removed.status_code == 302
    assert not CalendarEvent.objects.for_user(student).exists()
    _, body = _feed(signed_in, student)
    assert _uid(event) not in body
    assert "STATUS:CANCELLED" not in body


def test_a_cancellation_that_arrives_from_the_mailbox_does_reach_the_feed(signed_in, student, day):
    """The one path that produces a real cancellation, kept whole.

    Nothing in the HTTP layer sets `cancelled_at`; the Gmail and Google
    Calendar pipelines do. This asserts the FEED's half of that contract — a
    cancelled event keeps its identity and releases the time it was holding,
    which is what a subscriber needs in order to show it as cancelled rather
    than silently forget it.
    """
    _add(signed_in, day)
    event = CalendarEvent.objects.for_user(student).get()

    event.cancelled_at = timezone.now()
    event.save(update_fields=["cancelled_at"])

    _, body = _feed(signed_in, student)
    assert _uid(event) in body, "a cancelled meeting keeps its identity"
    assert "STATUS:CANCELLED" in body
    assert "TRANSP:TRANSPARENT" in body, "and stops occupying the slot"


# ---------------------------------------------------------------------------
# The subscription itself


def test_resetting_the_link_revokes_every_existing_subscription(client, signed_in, student, day):
    _add(signed_in, day)
    student.refresh_from_db()
    old = reverse("crm:calendar_ics", args=[student.calendar_token])
    assert client.get(old).status_code == 200

    reset = signed_in.post(reverse("crm:calendar_token_reset"))

    assert reset.status_code == 302
    student.refresh_from_db()
    new = reverse("crm:calendar_ics", args=[student.calendar_token])
    assert new != old
    assert client.get(old).status_code == 404
    assert client.get(new).status_code == 200


def test_one_students_calendar_is_not_in_another_students_feed(signed_in, student, day):
    _add(signed_in, day, title="Superday, Journey Partners")
    event = CalendarEvent.objects.for_user(student).get()

    other = User.objects.create_user(email="other@example.com", password="A-safe-passphrase-123")
    signed_in.force_login(other)

    _, body = _feed(signed_in, other)
    assert "Superday" not in body
    assert _uid(event) not in body
    # And another student's pk on the delete route finds nothing to delete.
    assert signed_in.post(reverse("crm:calendar_delete", args=[event.pk])).status_code == 302
    assert CalendarEvent.objects.for_user(student).filter(pk=event.pk).exists()


def test_the_calendar_page_and_its_write_routes_are_private(client, student, day):
    assert client.get(reverse("crm:calendar")).status_code == 302
    assert client.post(reverse("crm:calendar_add"),
                       {"title": "X", "kind": "event", "day": day.isoformat()}).status_code == 302
    assert client.post(reverse("crm:calendar_token_reset")).status_code == 302
    assert not CalendarEvent.all_objects.exists()
    student.refresh_from_db()
    assert student.calendar_token, "the reset attempt left the real token alone"
