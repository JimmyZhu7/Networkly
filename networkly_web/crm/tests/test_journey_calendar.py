"""Journey 6: a meeting, and the calendar somebody subscribed to.

Nothing is mocked. The subscription feed is fetched over HTTP with no session
at all, exactly as a calendar client fetches it.

All three of this journey's verbs are user actions, and the two that were
missing are the two the subscription cares about. RESCHEDULE moves the row in
place, so the `UID` a subscriber is holding stays the same and only `SEQUENCE`
goes up: the meeting moves on their phone rather than disappearing and
reappearing somewhere else. CANCEL keeps the row too, and sets `cancelled_at`,
so the feed says `STATUS:CANCELLED` about a meeting the student called off
themselves — which until now only a cancellation arriving from their mailbox or
from Google could produce. Remove still deletes outright and is tested here as
the narrower verb it is.

Both new routes refuse anything that is not the student's own typed row. A
Google-mirrored event is a view-only grant Networkly cannot move, and a captured
chat's time is still owned by the mailbox that keeps re-reading its invite; each
is a 404 rather than a button that appears to work.
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


def test_rescheduling_a_meeting_keeps_its_uid_and_raises_the_sequence(signed_in, student, day):
    """The whole point of the route: one row, moved.

    A student who typed the wrong hour used to have exactly one move —
    remove, then add — and that is a different row, so a subscribed client
    lost one UID and gained another and showed the meeting vanishing rather
    than moving. Same pk, same UID, one higher SEQUENCE is what tells the
    calendar already holding this meeting that the copy it has is stale.
    """
    _add(signed_in, day, at="09:30")
    event = CalendarEvent.objects.for_user(student).get()
    _, before = _feed(signed_in, student)
    assert "SEQUENCE:0" in before

    moved_to = day + dt.timedelta(days=1)
    response = signed_in.post(
        reverse("crm:calendar_reschedule", args=[event.pk]),
        {"day": moved_to.isoformat(), "at": "14:00"})

    assert response.status_code == 302
    event.refresh_from_db()
    assert CalendarEvent.objects.for_user(student).count() == 1, "moved in place"
    assert _local(event, student) == "14:00"
    assert event.starts_at.astimezone(ZoneInfo(student.timezone)).date() == moved_to
    assert event.ics_sequence == 1

    _, body = _feed(signed_in, student)
    assert _uid(event) in body, "the subscriber's copy keeps its identity"
    assert "SEQUENCE:1" in body, "and is marked as a newer revision of it"
    assert "STATUS:CANCELLED" not in body


def test_clearing_the_time_turns_a_meeting_into_an_all_day_entry(signed_in, student, day):
    """The other half of getting the date wrong. Blank time means the same
    thing here as on the add form: a fact about the day, not a 00:00 slot."""
    _add(signed_in, day, at="09:30")
    event = CalendarEvent.objects.for_user(student).get()

    signed_in.post(reverse("crm:calendar_reschedule", args=[event.pk]),
                   {"day": day.isoformat(), "at": ""})

    event.refresh_from_db()
    assert event.all_day is True
    _, body = _feed(signed_in, student)
    assert f"DTSTART;VALUE=DATE:{day:%Y%m%d}" in body


def test_a_meeting_with_an_end_keeps_its_length_when_it_moves(signed_in, student, day):
    """A stated hour is an hour wherever it lands. Rewriting `starts_at`
    alone would leave a DTEND before its DTSTART on anything moved later."""
    _add(signed_in, day, at="09:30")
    event = CalendarEvent.objects.for_user(student).get()
    event.ends_at = event.starts_at + dt.timedelta(hours=1)
    event.save(update_fields=["ends_at"])

    signed_in.post(reverse("crm:calendar_reschedule", args=[event.pk]),
                   {"day": day.isoformat(), "at": "16:00"})

    event.refresh_from_db()
    assert event.ends_at - event.starts_at == dt.timedelta(hours=1)
    assert _local(event, student) == "16:00"


def test_an_unreadable_date_moves_nothing_and_says_so(signed_in, student, day):
    _add(signed_in, day, at="09:30")
    event = CalendarEvent.objects.for_user(student).get()

    response = signed_in.post(
        reverse("crm:calendar_reschedule", args=[event.pk]),
        {"day": "not-a-date", "at": "14:00"}, follow=True)

    event.refresh_from_db()
    assert _local(event, student) == "09:30"
    assert event.ics_sequence == 0, "nothing changed, so no subscriber was told"
    assert "nothing moved" in response.content.decode()


def test_the_reschedule_control_is_on_the_page_for_a_typed_event(signed_in, student, day):
    _add(signed_in, day, at="09:30")
    event = CalendarEvent.objects.for_user(student).get()

    html = signed_in.get(reverse("crm:calendar")).content.decode()

    assert reverse("crm:calendar_reschedule", args=[event.pk]) in html
    assert reverse("crm:calendar_cancel", args=[event.pk]) in html
    assert "Reschedule" in html


# ---------------------------------------------------------------------------
# Cancel — and what actually happens instead


def test_cancelling_an_event_keeps_its_uid_and_says_cancelled_on_the_feed(signed_in, student, day):
    """The verb the student never had.

    Deleting the row takes the meeting out of the .ics, so a calendar that
    already synced it drops it with no explanation. Cancelling keeps the UID
    and lets the feed say the meeting is off and the hour is free, which is
    what somebody planning their week around it needs told.
    """
    _add(signed_in, day)
    event = CalendarEvent.objects.for_user(student).get()
    assert _uid(event) in _feed(signed_in, student)[1]

    cancelled = signed_in.post(reverse("crm:calendar_cancel", args=[event.pk]))

    assert cancelled.status_code == 302
    event.refresh_from_db()
    assert event.cancelled_at is not None
    assert event.ics_sequence == 1, "a subscriber holds an older copy of this"

    _, body = _feed(signed_in, student)
    assert _uid(event) in body, "the meeting keeps its identity"
    assert "STATUS:CANCELLED" in body
    assert "TRANSP:TRANSPARENT" in body, "and stops occupying the slot"
    assert "SEQUENCE:1" in body


def test_the_page_says_who_cancelled_it_and_offers_no_second_cancel(signed_in, student, day):
    _add(signed_in, day)
    event = CalendarEvent.objects.for_user(student).get()
    signed_in.post(reverse("crm:calendar_cancel", args=[event.pk]))

    html = signed_in.get(reverse("crm:calendar")).content.decode()

    assert "You cancelled this event" in html
    assert reverse("crm:calendar_cancel", args=[event.pk]) not in html
    assert reverse("crm:calendar_reschedule", args=[event.pk]) not in html
    assert reverse("crm:calendar_delete", args=[event.pk]) in html, "removal is still the way out"


def test_cancelling_twice_changes_nothing_the_second_time(signed_in, student, day):
    _add(signed_in, day)
    event = CalendarEvent.objects.for_user(student).get()
    signed_in.post(reverse("crm:calendar_cancel", args=[event.pk]))
    event.refresh_from_db()
    first = event.cancelled_at

    signed_in.post(reverse("crm:calendar_cancel", args=[event.pk]))

    event.refresh_from_db()
    assert event.cancelled_at == first
    assert event.ics_sequence == 1, "no revision a subscriber has to re-read"


def test_removing_a_cancelled_event_is_still_available_and_still_deletes(signed_in, student, day):
    """Cancel is the default; Remove is the escape hatch for a row that
    should never have existed. Both stay, and they do different things."""
    _add(signed_in, day)
    event = CalendarEvent.objects.for_user(student).get()
    signed_in.post(reverse("crm:calendar_cancel", args=[event.pk]))

    removed = signed_in.post(reverse("crm:calendar_delete", args=[event.pk]))

    assert removed.status_code == 302
    assert not CalendarEvent.objects.for_user(student).exists()
    _, body = _feed(signed_in, student)
    assert _uid(event) not in body


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


def test_a_stranger_can_neither_move_nor_cancel_someone_elses_meeting(signed_in, student, day):
    """404, and the same 404 a pk that never existed gets. These two routes
    are new, so unlike the delete endpoint they have no replayed-form case to
    stay inert for — and answering differently for a real row than for an
    imaginary one would make another student's pk a probe."""
    _add(signed_in, day, at="09:30")
    event = CalendarEvent.objects.for_user(student).get()

    other = User.objects.create_user(email="stranger@example.com",
                                     password="A-safe-passphrase-123")
    signed_in.force_login(other)

    assert signed_in.post(reverse("crm:calendar_reschedule", args=[event.pk]),
                          {"day": day.isoformat(), "at": "23:00"}).status_code == 404
    assert signed_in.post(reverse("crm:calendar_cancel", args=[event.pk])).status_code == 404

    event.refresh_from_db()
    assert _local(event, student) == "09:30"
    assert event.cancelled_at is None
    assert event.ics_sequence == 0


def test_a_google_owned_meeting_is_not_the_manual_routes_to_touch(signed_in, student, day):
    """Networkly holds a view-only grant on a connected calendar. A move here
    would change the local copy, be undone by the next `gcal_sync`, and teach
    the student the page is unreliable — so the route refuses it outright and
    the popover never offers the control."""
    mirrored = CalendarEvent.all_objects.create(
        user=student, title="Standup",
        starts_at=timezone.now() + dt.timedelta(days=3),
        source=CalendarEvent.SOURCE_GCAL, external_id="g-1")

    assert signed_in.post(reverse("crm:calendar_reschedule", args=[mirrored.pk]),
                          {"day": day.isoformat(), "at": "10:00"}).status_code == 404
    assert signed_in.post(reverse("crm:calendar_cancel", args=[mirrored.pk])).status_code == 404

    mirrored.refresh_from_db()
    assert mirrored.cancelled_at is None
    assert mirrored.ics_sequence == 0

    html = signed_in.get(reverse("crm:calendar")).content.decode()
    assert reverse("crm:calendar_reschedule", args=[mirrored.pk]) not in html
    assert reverse("crm:calendar_cancel", args=[mirrored.pk]) not in html


def test_a_captured_chat_is_still_the_mailboxs_to_move(signed_in, student, day):
    """A captured chat has no upstream copy to restore, so Remove sticks and
    stays offered. Its `starts_at` is a different question: the mail poll
    re-reads the invite it came from, so a hand-typed time there is one the
    next run may overwrite. Moving it means moving the invite."""
    captured = CalendarEvent.all_objects.create(
        user=student, title="Chat with Jane Banker",
        starts_at=timezone.now() + dt.timedelta(days=3),
        source=CalendarEvent.SOURCE_CAPTURE, thread_id="t-1",
        kind=CalendarEvent.KIND_CHAT)

    assert signed_in.post(reverse("crm:calendar_reschedule", args=[captured.pk]),
                          {"day": day.isoformat(), "at": "10:00"}).status_code == 404
    assert signed_in.post(reverse("crm:calendar_cancel", args=[captured.pk])).status_code == 404

    html = signed_in.get(reverse("crm:calendar")).content.decode()
    assert reverse("crm:calendar_reschedule", args=[captured.pk]) not in html
    assert reverse("crm:calendar_delete", args=[captured.pk]) in html, "removal is untouched"


def test_the_new_routes_reject_a_request_with_no_csrf_token(student, day):
    """Every write on this page is a plain POST, so CSRF is the whole
    defence. Django's test client suppresses the check unless asked, which is
    why this one asks."""
    from django.test import Client

    strict = Client(enforce_csrf_checks=True)
    strict.force_login(student)
    event = CalendarEvent.all_objects.create(
        user=student, title="Superday",
        starts_at=timezone.now() + dt.timedelta(days=3))

    assert strict.post(reverse("crm:calendar_reschedule", args=[event.pk]),
                       {"day": day.isoformat(), "at": "10:00"}).status_code == 403
    assert strict.post(reverse("crm:calendar_cancel", args=[event.pk])).status_code == 403

    event.refresh_from_db()
    assert event.cancelled_at is None
    assert event.ics_sequence == 0


def test_the_calendar_page_and_its_write_routes_are_private(client, student, day):
    assert client.get(reverse("crm:calendar")).status_code == 302
    assert client.post(reverse("crm:calendar_add"),
                       {"title": "X", "kind": "event", "day": day.isoformat()}).status_code == 302
    assert client.post(reverse("crm:calendar_token_reset")).status_code == 302
    assert client.post(reverse("crm:calendar_reschedule", args=[1]),
                       {"day": day.isoformat()}).status_code == 302
    assert client.post(reverse("crm:calendar_cancel", args=[1])).status_code == 302
    assert not CalendarEvent.all_objects.exists()
    student.refresh_from_db()
    assert student.calendar_token, "the reset attempt left the real token alone"
