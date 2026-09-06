"""A Google-owned row is the student's own calendar, restated.

`crm.models.CalendarEvent.SOURCE_GCAL` says what the three sources mean, and
it is not decoration:

    a `capture` row is something Coverage FOUND in the student's mail and can
    be argued with; a `gcal` row is the student's own calendar restated,
    read-only, and the place to change it is Google Calendar.

`capture.gcal_live._upsert_event` already enforces one half of that. Its
`mirrors_google` flag stops a Google sync overwriting the title, notes and
location of a row the mailbox created, because that row's source owns its
context.

The other half was missing. `capture.gmail._upsert_scheduled_chat` finds its
row by `ics_uid` with no source filter, and a Google event's `iCalUID` is the
same string the invite email carries — that is the whole point of a UID. So
the mailbox pass could reach a Google-owned row and rewrite it.

Which of the two rows exists first is a scheduling coin-flip: the calendar
job runs every five minutes and the mail poll on its own cadence, and the
invite email and the calendar entry arrive together. Adoption in the
mail-first direction is designed and tested (`test_gcal_sync.py::
test_a_synced_event_adopts_the_row_the_invite_already_made`). This file is
the calendar-first direction.

`transaction=True` for the reason `test_gmail.py` documents: applying a
finding calls `crm.services.log_touch`, which opens its own connection.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from capture.gmail import apply_findings
from crm.models import CalendarEvent, Contact

pytestmark = pytest.mark.django_db(transaction=True)

User = get_user_model()

UID = "7fa93ce0abcd1234@google.com"


@pytest.fixture
def student():
    return User.objects.create_user(email="gcal-owner@example.com", password="x")


@pytest.fixture
def lily(student):
    return Contact.all_objects.create(
        user=student, name="Lily Liu", email="lily.liu@barclays.com")


def _at(days=0, hour=15):
    return timezone.localtime(timezone.now()).replace(
        hour=hour, minute=0, second=0, microsecond=0) + timedelta(days=days)


def _google_row(student, *, starts_at, uid=UID, title="Networking coffee — Barclays"):
    """Exactly what `gcal_live._upsert_event` writes on the create path:
    `source=gcal`, `kind=event`, a stated time, and no `invite_sent_at`,
    because a Google event never came from an invite this module read."""
    return CalendarEvent.all_objects.create(
        user=student,
        external_id="g-evt-1",
        ics_uid=uid,
        title=title,
        description="Bring the pitch.",
        location="Level 28",
        starts_at=starts_at,
        all_day=False,
        kind=CalendarEvent.KIND_EVENT,
        source=CalendarEvent.SOURCE_GCAL,
        time_confidence=1.0,
        time_evidence="",
    )


def _invite(thread_id, when, *, sent_at=None, uid=UID):
    """One finding in `GmailFindingsProvider`'s shape."""
    return {
        "name": "Lily Liu", "found": True, "email": "lily.liu@barclays.com",
        "thread_id": thread_id, "chat_status": "scheduled",
        "chat_scheduled_at": when.isoformat(), "ics_uid": uid,
        "occurred_at": sent_at.isoformat() if sent_at else None,
        "evidence": "Calendar invite received: Coffee Chat",
    }


# ---------------------------------------------------------------------------
# The damaging case: the meeting was moved in Google, and the original invite
# is still sitting in the mailbox's rolling window.
# ---------------------------------------------------------------------------

def test_a_stale_invite_cannot_drag_a_google_owned_meeting_back(student, lily):
    """The student moved the chat from Tuesday to Thursday in Google
    Calendar; sync mirrored Thursday onto the row. The ORIGINAL Tuesday
    invite has not aged out of the mail window yet.

    On a Google-owned row `invite_sent_at` is None — not because the
    provenance is unknown, but because there never was an invite. The
    recency guard reads that null as "no time to protect" and opens, so the
    Tuesday DTSTART walks in and moves a meeting Google says is on Thursday.
    """
    thursday = _at(days=3, hour=11)
    tuesday = _at(days=1, hour=15)
    row = _google_row(student, starts_at=thursday)

    apply_findings(student, [_invite("t-1", tuesday, sent_at=_at(days=-2))])

    row.refresh_from_db()
    assert row.starts_at == thursday


def test_the_mailbox_never_takes_ownership_of_a_google_row(student, lily):
    """The compounding half. Flipping `source` to `capture` is not just a
    label: `gcal_live._upsert_event`'s `mirrors_google` test is
    `existing.source == SOURCE_GCAL`, so once the row reads `capture`,
    Google stops mirroring its own title, notes and location onto it
    forever. One mail pass permanently detaches the row from the calendar
    it is supposed to be restating."""
    row = _google_row(student, starts_at=_at(days=3, hour=11))

    apply_findings(student, [_invite("t-1", _at(days=3, hour=11), sent_at=_at())])

    row.refresh_from_db()
    assert row.source == CalendarEvent.SOURCE_GCAL


def test_google_keeps_the_title_it_put_on_the_students_calendar(student, lily):
    """"Networking coffee — Barclays" is what the student sees in Google.
    Rewriting it to "Chat with Lily Liu" makes the two calendars disagree
    about the same meeting, and the row is the read-only one."""
    row = _google_row(student, starts_at=_at(days=3, hour=11))

    apply_findings(student, [_invite("t-1", _at(days=3, hour=11), sent_at=_at())])

    row.refresh_from_db()
    assert row.title == "Networking coffee — Barclays"


def test_a_prose_reading_cannot_move_a_google_owned_meeting(student, lily):
    """A sentence we parsed out of an email is the weakest evidence in the
    system. It is already refused against a stated row, and a Google row is
    stated by construction — but only the `time_reported` test stands
    between them, so this pins the outcome rather than the mechanism."""
    thursday = _at(days=3, hour=11)
    row = _google_row(student, starts_at=thursday)

    finding = _invite("t-1", _at(days=1, hour=17), sent_at=_at())
    finding["prose_time"] = {
        "kind": "booking", "dated": True, "confidence": 0.6,
        "evidence": "shall we say Tuesday at 5?",
    }
    apply_findings(student, [finding])

    row.refresh_from_db()
    assert row.starts_at == thursday
    assert row.time_confidence == 1.0
    assert row.time_evidence == ""


# ---------------------------------------------------------------------------
# What the mailbox may still do — the join has to keep working.
# ---------------------------------------------------------------------------

def test_the_mailbox_may_still_name_the_person_and_the_thread(student, lily):
    """Refusing to rewrite the row is not refusing to recognise it. The
    whole reason Today can show a prep card for a Google meeting is that the
    mailbox knows which contact it is with, and which thread it came from.
    Those are facts mail owns and Google does not have."""
    row = _google_row(student, starts_at=_at(days=3, hour=11))

    apply_findings(student, [_invite("thread-abc", _at(days=3, hour=11), sent_at=_at())])

    row.refresh_from_db()
    assert row.contact_id == lily.pk
    assert row.thread_id == "thread-abc"


def test_a_mail_owned_row_is_still_the_mailboxs_to_move(student, lily):
    """The guard is scoped to Google-owned rows. A row the mailbox created
    keeps behaving exactly as it did — this is the regression fence around
    the fix, not a new rule about capture rows."""
    tuesday = _at(days=1, hour=15)
    thursday = _at(days=3, hour=11)
    row = CalendarEvent.all_objects.create(
        user=student, thread_id="t-1", ics_uid=UID,
        title="Chat with Lily Liu", starts_at=tuesday,
        invite_sent_at=_at(days=-3), all_day=False,
        kind=CalendarEvent.KIND_CHAT, source=CalendarEvent.SOURCE_CAPTURE,
        contact=lily, time_confidence=1.0, time_evidence="",
    )

    apply_findings(student, [_invite("t-1", thursday, sent_at=_at(days=-1))])

    row.refresh_from_db()
    assert row.starts_at == thursday
    assert row.source == CalendarEvent.SOURCE_CAPTURE


def test_a_google_row_is_not_created_by_the_mailbox_in_the_first_place(student, lily):
    """With no row at all the mailbox still books the chat. The guard must
    not turn "do not overwrite Google" into "do not schedule anything"."""
    tuesday = _at(days=1, hour=15)

    apply_findings(student, [_invite("t-1", tuesday, sent_at=_at())])

    row = CalendarEvent.all_objects.filter(user=student, ics_uid=UID).get()
    assert row.source == CalendarEvent.SOURCE_CAPTURE
    assert row.starts_at == tuesday
    assert row.contact_id == lily.pk


def test_applying_the_same_invite_twice_over_a_google_row_stays_quiet(student, lily):
    """Replay. The second pass has nothing left to say, so it must not
    report a chat as newly scheduled — the same honesty rule the
    before/after snapshot enforces on capture rows."""
    row = _google_row(student, starts_at=_at(days=3, hour=11))
    finding = _invite("thread-abc", _at(days=3, hour=11), sent_at=_at())

    apply_findings(student, [dict(finding)])
    second = apply_findings(student, [dict(finding)])

    row.refresh_from_db()
    assert second.chats_scheduled == 0
    assert row.source == CalendarEvent.SOURCE_GCAL
    assert CalendarEvent.all_objects.filter(user=student, ics_uid=UID).count() == 1
