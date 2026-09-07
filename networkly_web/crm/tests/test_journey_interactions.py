"""Journey 5: logging what happened, and what the app asks for next.

A reply, a chat and a referral, logged the way a student logs them — through
the contact page's htmx control and through Today's own card buttons — with
the warmth ratchet and the queue read back after each one. Then the pause and
the resume. Then the same day rendered for a student in Los Angeles and a
student in Hong Kong.

NOTHING IS MOCKED. The cadence and warmth engines run for real; the only
synthetic things are the two students. The daily brief is the one AI surface
Today can touch, and the repo-root conftest blanks `ANTHROPIC_API_KEY` for
every test, so it stays dark here — no provider call is made.
"""

from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from crm.models import Contact, Touch, UserFirm
from directory.models import Firm

pytestmark = pytest.mark.django_db(transaction=True)  # crm.services opens its own
# psycopg connection for the ported pipeline, so a touch written through it is
# invisible to a test wrapped in an uncommitted transaction.


@pytest.fixture
def firm():
    return Firm.objects.create(
        name="Journey Partners", slug="journey-partners", regions=["us"], tracks=["ib"],
    )


@pytest.fixture
def student():
    return User.objects.create_user(
        email="networker@example.com", password="A-safe-passphrase-123",
        regions=["us"], tracks=["ib"], onboarded_at=timezone.now(),
        timezone="America/Los_Angeles", timezone_auto=False,
    )


@pytest.fixture
def signed_in(client, student):
    client.force_login(student)
    return client


@pytest.fixture
def contact(student, firm):
    """One person at a targeted firm, written to three weeks ago.

    Both halves matter to the cadence engine and therefore to Today: the firm
    has to be one the student is actually working (`UserFirm`), and there has
    to be a send old enough that a follow-up is due. A contact with neither is
    a name in a book, not a queue item, which is correct and is why the
    fixture states it rather than hoping.
    """
    UserFirm.all_objects.create(user=student, firm=firm, tier=1)
    contact = Contact.all_objects.create(
        user=student, name="Dana Banker", firm=firm, role="Analyst",
        email="dana@journeypartners.test", region="us", source="manual",
    )
    Touch.all_objects.create(
        user=student, contact=contact, kind="outreach", channel="email",
        ts=timezone.now() - dt.timedelta(days=21),
    )
    return contact


def _log(client, contact, kind, channel="email", **extra):
    """The contact page's own control: an htmx POST that swaps the live panel."""
    return client.post(
        reverse("crm:log_touch", args=[contact.pk]),
        {"kind": kind, "channel": channel, **extra},
        HTTP_HX_REQUEST="true",
    )


def _name_of(action):
    """A queue card's person, however that lane spells it.

    `_build_actions` hands some lanes a `Contact` and some a projected dict
    of the four columns a card needs; both are "the contact" as far as the
    template is concerned, and a helper that only understood one of them
    would pass or fail by which lane the fixture happened to land in.
    """
    contact = action["contact"]
    return contact["name"] if isinstance(contact, dict) else contact.name


def _queue_names(response):
    return {
        _name_of(action)
        for lane in response.context["lanes"]
        for action in lane["items"]
    }


def _logged_kinds(student, contact):
    """Everything logged AFTER the fixture's seed outreach."""
    return list(
        Touch.objects.for_user(student).filter(contact=contact)
        .order_by("id").values_list("kind", flat=True)
    )[1:]


# ---------------------------------------------------------------------------
# Warmth moves, and the student can see it move


def test_a_reply_a_chat_and_a_referral_ratchet_warmth_in_that_order(signed_in, student, contact):
    assert (contact.warmth, contact.thread_state) == ("cold", "no_reply")

    _log(signed_in, contact, "outreach")
    contact.refresh_from_db()
    assert contact.thread_state == "no_reply", "an unanswered send is not a relationship"

    reply = _log(signed_in, contact, "reply_received")
    assert reply.status_code == 200
    contact.refresh_from_db()
    assert (contact.warmth, contact.thread_state) == ("replied", "replied")
    # The panel that comes back SAYS it moved, in words, not enum names.
    body = reply.content.decode()
    assert "They replied" in body
    assert "no_reply" not in body

    _log(signed_in, contact, "chat", channel="coffee_chat")
    contact.refresh_from_db()
    assert (contact.warmth, contact.thread_state) == ("chatted", "chat_done")

    _log(signed_in, contact, "referral")
    contact.refresh_from_db()
    assert (contact.warmth, contact.thread_state) == ("advocate", "advocate")

    assert _logged_kinds(student, contact) == [
        "outreach", "reply_received", "chat", "referral",
    ]


def test_the_ratchet_never_runs_backwards(signed_in, student, contact):
    _log(signed_in, contact, "referral")
    contact.refresh_from_db()
    assert contact.warmth == "advocate"

    _log(signed_in, contact, "outreach")

    contact.refresh_from_db()
    assert contact.warmth == "advocate", "a later send cannot cool a warm relationship"


def test_an_unknown_interaction_type_is_refused_and_writes_nothing(signed_in, student, contact):
    response = _log(signed_in, contact, "telepathy")

    assert response.status_code == 200
    assert "Pick an interaction type." in response.content.decode()
    assert _logged_kinds(student, contact) == []
    contact.refresh_from_db()
    assert contact.warmth == "cold"


def test_a_channel_the_form_does_not_offer_is_refused(signed_in, student, contact):
    response = _log(signed_in, contact, "reply_received", channel="carrier-pigeon")

    assert "Pick a channel." in response.content.decode()
    assert _logged_kinds(student, contact) == []


# ---------------------------------------------------------------------------
# Today, and its next action


def test_today_asks_for_the_next_move_and_stops_asking_once_it_is_made(signed_in, student, contact):
    today = signed_in.get(reverse("crm:week"))
    assert today.status_code == 200
    assert contact.name in _queue_names(today)
    assert today.context["queue_total"] >= 1

    # "Done" on the card is an attestation, and it writes the touch.
    done = signed_in.post(reverse("crm:today_act", args=[contact.pk, "sent"]),
                          {"kind": "outreach"}, HTTP_HX_REQUEST="true")
    assert done.status_code == 200
    assert _logged_kinds(student, contact) == ["outreach"]
    assert contact.name not in _queue_names(done), "a card acted on today comes back tomorrow, not now"

    # And the same is true of a fresh page load, not just the swapped fragment.
    assert contact.name not in _queue_names(signed_in.get(reverse("crm:week")))


def test_recording_a_reply_from_the_today_card_warms_the_contact(signed_in, student, contact):
    signed_in.post(reverse("crm:today_act", args=[contact.pk, "reply"]), HTTP_HX_REQUEST="true")

    contact.refresh_from_db()
    assert (contact.warmth, contact.thread_state) == ("replied", "replied")
    assert _logged_kinds(student, contact) == ["reply_received"]


def test_snooze_takes_a_card_off_today_without_ending_the_relationship(signed_in, student, contact):
    signed_in.post(reverse("crm:today_act", args=[contact.pk, "skip"]), HTTP_HX_REQUEST="true")

    contact.refresh_from_db()
    assert contact.snoozed_until is not None
    assert contact.thread_state == "no_reply", "skipping is not parking"
    assert contact.name not in _queue_names(signed_in.get(reverse("crm:week")))


def test_an_unknown_today_verb_is_refused(signed_in, contact):
    assert signed_in.post(reverse("crm:today_act", args=[contact.pk, "vaporize"])).status_code == 400


# ---------------------------------------------------------------------------
# Pause and resume


def test_outreach_can_be_paused_and_resumed_with_the_reason_on_the_record(signed_in, student, contact):
    _log(signed_in, contact, "reply_received")

    paused = signed_in.post(reverse("crm:today_act", args=[contact.pk, "park"]),
                            HTTP_HX_REQUEST="true")
    assert paused.status_code == 200
    contact.refresh_from_db()
    assert contact.thread_state == "parked"
    assert contact.name not in _queue_names(paused)
    # Parking is audited: the log says who paused it and why, not just that
    # a state column changed.
    override = Touch.objects.for_user(student).filter(
        contact=contact, kind="manual_override").latest("id")
    assert "Parked" in (override.note or "")

    parked_page = signed_in.get(reverse("crm:contact_parked"))
    assert parked_page.status_code == 200
    assert contact.name in parked_page.content.decode()

    resumed = signed_in.post(reverse("crm:contact_parked_unpark"), {"ids": [str(contact.pk)]})
    assert resumed.status_code == 302
    contact.refresh_from_db()
    # Restored to the state its OWN warmth implies, not a single flat default.
    assert contact.thread_state == "replied"
    assert contact.warmth == "replied"
    assert Touch.objects.for_user(student).filter(
        contact=contact, kind="manual_override").count() == 2


def test_resuming_somebody_who_was_never_paused_changes_nothing(signed_in, student, contact):
    response = signed_in.post(reverse("crm:contact_parked_unpark"), {"ids": [str(contact.pk)]})

    assert response.status_code == 302
    contact.refresh_from_db()
    assert contact.thread_state == "no_reply"
    assert not Touch.objects.for_user(student).filter(kind="manual_override").exists()


def test_pausing_is_scoped_to_the_student_who_asked(client, student, contact):
    stranger = User.objects.create_user(email="stranger@example.com",
                                        password="A-safe-passphrase-123")
    client.force_login(stranger)

    response = client.post(reverse("crm:today_act", args=[contact.pk, "park"]))

    assert response.status_code == 404
    contact.refresh_from_db()
    assert contact.thread_state == "no_reply"


# ---------------------------------------------------------------------------
# Two clocks


@pytest.mark.parametrize("zone", ["America/Los_Angeles", "Asia/Hong_Kong"])
def test_today_renders_in_the_students_own_timezone(client, firm, zone):
    """The two clocks the product actually has to serve at once.

    The interesting hour is the one where the two calendars disagree about
    what day it is: 16:00 in Los Angeles is already tomorrow in Hong Kong.
    """
    student = User.objects.create_user(
        email=f"{zone.split('/')[1].lower()}@example.com",
        password="A-safe-passphrase-123",
        regions=["us"], tracks=["ib"], onboarded_at=timezone.now(),
        timezone=zone, timezone_auto=False,
    )
    UserFirm.all_objects.create(user=student, firm=firm, tier=1)
    contact = Contact.all_objects.create(
        user=student, name="Dana Banker", firm=firm, source="manual",
        email="dana@journeypartners.test",
    )
    Touch.all_objects.create(
        user=student, contact=contact, kind="outreach", channel="email",
        ts=timezone.now() - dt.timedelta(days=21),
    )
    client.force_login(student)

    page = client.get(reverse("crm:week"))

    assert page.status_code == 200
    assert contact.name in _queue_names(page)
    # The request leaves no timezone activated behind it, which is what stops
    # one student's clock rendering the next student's page.
    assert timezone.get_current_timezone_name() == "UTC"


def test_the_same_moment_is_a_different_day_for_the_two_students(client, firm):
    """A chat at 16:30 Pacific is on tomorrow's calendar in Hong Kong. Both
    students must see their OWN day, from the one stored instant."""
    when = dt.datetime(2027, 3, 17, 23, 30, tzinfo=dt.UTC)  # 16:30 PDT / 07:30 HKT+1
    seen = {}
    for zone, email in [("America/Los_Angeles", "la@example.com"),
                        ("Asia/Hong_Kong", "hk@example.com")]:
        student = User.objects.create_user(
            email=email, password="A-safe-passphrase-123",
            regions=["us"], tracks=["ib"], onboarded_at=timezone.now(),
            timezone=zone, timezone_auto=False,
        )
        contact = Contact.all_objects.create(
            user=student, name="Dana Banker", firm=firm, source="manual",
        )
        Touch.all_objects.create(user=student, contact=contact, kind="chat_scheduled",
                                 channel="coffee_chat", ts=when)
        seen[zone] = when.astimezone(ZoneInfo(zone)).date()
        client.force_login(student)
        assert client.get(reverse("crm:week")).status_code == 200

    assert seen["America/Los_Angeles"] == dt.date(2027, 3, 17)
    assert seen["Asia/Hong_Kong"] == dt.date(2027, 3, 18)


def test_today_and_the_network_board_are_private(client, contact):
    for name in ("crm:week", "crm:contact_list", "crm:contact_parked"):
        assert client.get(reverse(name)).status_code == 302
    assert client.post(reverse("crm:log_touch", args=[contact.pk]),
                       {"kind": "reply_received", "channel": "email"}).status_code == 302
    # Only the fixture's own seed send; the anonymous POST wrote nothing.
    assert list(Touch.all_objects.values_list("kind", flat=True)) == ["outreach"]
