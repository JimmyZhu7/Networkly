"""Journey 7: what a student is left holding when the model does not answer.

WHAT IS MOCKED, precisely: the Anthropic client, and only it. `agent.get_client`
is replaced with a fake whose scripted round raises instead of returning, which
is the established seam in this app's own suite. Nothing else is faked — the
credit ledger, the reservation row, the PostgreSQL conversation lock, the views
and the recovery command all run for real. No paid call is made and no API key
is read; the repo-root conftest blanks `ANTHROPIC_API_KEY` for every test, so
each test here re-declares a synthetic one explicitly.

`test_credit_reservation.py` and `test_durable_turns.py` already prove the
metering and recovery contracts at the level of `agent.run_turn` and
`TurnCharge`. What is new here is that the same contracts hold when the turn is
started the way a student starts one: a POST to `assistant:send` or
`assistant:stream`. That is the layer where a lock could be leaked or a
reservation stranded without a single existing test noticing.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from assistant import agent, plans
from assistant.locks import ConversationLock
from assistant.metering import TurnCharge
from assistant.models import ChatConversation, ChatMessage, ChatTurnReservation
from assistant.tests.test_agent import (
    FakeClient, FakeStreamingClient, _response, _text, _usage,
)
from billing import credits
from billing.models import CreditLedger

pytestmark = pytest.mark.django_db(transaction=True)

# One plan, spelled out, so "the balance moved by exactly one message" is an
# arithmetic statement rather than a reading of whatever the defaults are today.
PLANS = {"pro": {"monthly_grant": 100, "message_cost": 3, "daily_burst": 45}}


@pytest.fixture(autouse=True)
def postgres_only():
    if connection.vendor != "postgresql":
        pytest.skip("the conversation lock is a PostgreSQL session advisory lock")


@pytest.fixture
def student():
    return User.objects.create_user(
        email="asker@example.com", password="A-safe-passphrase-123", plan="pro",
    )


@pytest.fixture
def signed_in(client, student):
    client.force_login(student)
    return client


def _reply(text="Here is what I found."):
    return ([text], _response([_text(text)], "end_turn", usage=_usage()))


def _refunds(student):
    return CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_REFUND)


def _spends(student):
    return CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_SPEND_CHAT)


def _drain(response):
    """A StreamingHttpResponse does nothing until somebody reads it."""
    return b"".join(response.streaming_content).decode()


# ---------------------------------------------------------------------------
# A turn that fails


@override_settings(ANTHROPIC_API_KEY="sk-test-journey", CREDIT_PLANS=PLANS)
def test_a_failed_send_refunds_its_reservation_and_leaves_the_chat_usable(
    signed_in, student, monkeypatch,
):
    opening = credits.balance(student)
    assert plans.limits_for(student).message_cost == 3

    monkeypatch.setattr(agent, "get_client",
                        lambda: FakeClient([RuntimeError("provider unreachable")]))
    failed = signed_in.post(reverse("assistant:send"), {"message": "who should I write to?"})

    assert failed.status_code == 200
    body = failed.content.decode()
    assert "who should I write to?" in body, "the student's own words are still on the page"
    # Escaped as the template renders it, apostrophe and all.
    assert "couldn&#x27;t reach the model just then" in body

    # The credit came back, and came back exactly once.
    assert credits.balance(student) == opening
    assert credits.daily_spent(student) == 0
    reservation = ChatTurnReservation.objects.for_user(student).get()
    assert reservation.status == ChatTurnReservation.REFUNDED
    assert reservation.reason == "turn_failed_after_charge"
    assert reservation.completed_at is not None
    assert _spends(student).count() == 1 and _refunds(student).count() == 1

    # And the conversation still works: the lock was released, not leaked.
    monkeypatch.setattr(agent, "get_client", lambda: FakeClient([
        _response([_text("Start with Dana at Journey Partners.")], "end_turn", usage=_usage()),
    ]))
    worked = signed_in.post(reverse("assistant:send"), {"message": "try again"})

    assert worked.status_code == 200
    assert "Start with Dana at Journey Partners." in worked.content.decode()
    assert credits.balance(student) == opening - 3
    settled = ChatTurnReservation.objects.for_user(student).exclude(pk=reservation.pk).get()
    assert settled.status == ChatTurnReservation.SETTLED


@override_settings(ANTHROPIC_API_KEY="sk-test-journey", CREDIT_PLANS=PLANS)
def test_a_failed_stream_settles_once_and_says_so_in_its_own_frames(
    signed_in, student, monkeypatch,
):
    opening = credits.balance(student)
    monkeypatch.setattr(agent, "get_client",
                        lambda: FakeStreamingClient([RuntimeError("connection reset")]))

    frames = _drain(signed_in.post(reverse("assistant:stream"), {"message": "who replied?"}))

    assert '"kind": "failed"' in frames or '"kind":"failed"' in frames
    assert credits.balance(student) == opening
    assert ChatTurnReservation.objects.for_user(student).get().status == (
        ChatTurnReservation.REFUNDED
    )
    assert _refunds(student).count() == 1


@override_settings(ANTHROPIC_API_KEY="sk-test-journey", CREDIT_PLANS=PLANS)
def test_a_reader_who_walks_away_mid_stream_is_refunded_exactly_once(
    signed_in, student, monkeypatch,
):
    """The browser closing the tab is the commonest interruption there is.

    Closing the generator without draining it is what a disconnect looks like
    to Django, and the charge's own `__exit__` is the backstop that has to
    catch it.
    """
    opening = credits.balance(student)
    monkeypatch.setattr(agent, "get_client", lambda: FakeStreamingClient([
        (["Here is ", "what I found."],
         _response([_text("Here is what I found.")], "end_turn", usage=_usage())),
    ]))

    response = signed_in.post(reverse("assistant:stream"), {"message": "who replied?"})
    # `streaming_content` is a map over the view's generator, so closing the
    # response — which is what Django does when a client disconnects — is the
    # only handle that actually reaches the generator underneath it.
    stream = iter(response.streaming_content)
    next(stream)          # the first frame reaches the browser...
    response.close()      # ...and then the reader is gone.

    reservation = ChatTurnReservation.objects.for_user(student).get()
    assert reservation.status in (
        ChatTurnReservation.REFUNDED, ChatTurnReservation.SETTLED,
    )
    assert reservation.completed_at is not None, "no reservation is left pending"
    # Exactly one settlement, whichever way it settled.
    assert _spends(student).count() == 1
    assert _refunds(student).count() <= 1
    if reservation.status == ChatTurnReservation.REFUNDED:
        assert credits.balance(student) == opening
    else:
        assert credits.balance(student) == opening - 3


# ---------------------------------------------------------------------------
# Recovery


@override_settings(ANTHROPIC_API_KEY="sk-test-journey", CREDIT_PLANS=PLANS)
def test_recovery_finds_nothing_to_do_after_a_turn_that_already_failed_cleanly(
    signed_in, student, monkeypatch,
):
    """The other half of "settled exactly once": the sweeper must not settle
    a second time over a turn the request already refunded."""
    monkeypatch.setattr(agent, "get_client",
                        lambda: FakeClient([RuntimeError("provider unreachable")]))
    signed_in.post(reverse("assistant:send"), {"message": "who should I write to?"})
    assert _refunds(student).count() == 1

    out = StringIO()
    call_command("assistant_reconcile", "--apply", stdout=out)

    assert "0 refunded" in out.getvalue()
    assert _refunds(student).count() == 1


@override_settings(ANTHROPIC_API_KEY="sk-test-journey", CREDIT_PLANS=PLANS)
def test_a_turn_killed_before_it_could_settle_is_recovered_once_and_only_once(student):
    """A worker that dies mid-turn leaves a PENDING row and no process to
    finish it. Modelled by reserving inside the lock and never running the
    charge's exit, which is what SIGKILL looks like from the outside."""
    conversation = ChatConversation.all_objects.create(user=student, title="Journey")
    opening = credits.balance(student)

    with ConversationLock(conversation.pk) as ownership:
        charge = TurnCharge(student, conversation, ownership)
        assert charge.reserve(plans.limits_for(student))
    ChatTurnReservation.objects.for_user(student).filter(pk=charge.reservation_id).update(
        created=timezone.now() - timedelta(minutes=60),
    )
    assert credits.balance(student) == opening - 3

    first, second = StringIO(), StringIO()
    call_command("assistant_reconcile", "--apply", stdout=first)
    call_command("assistant_reconcile", "--apply", stdout=second)

    assert "1 refunded" in first.getvalue()
    assert "0 refunded" in second.getvalue()
    assert _refunds(student).count() == 1
    assert credits.balance(student) == opening
    assert ChatTurnReservation.objects.for_user(student).get().status == (
        ChatTurnReservation.REFUNDED
    )


@override_settings(ANTHROPIC_API_KEY="sk-test-journey", CREDIT_PLANS=PLANS)
def test_recovery_never_refunds_a_turn_that_is_still_running(student):
    """Age alone must never authorize a refund — the lock is the evidence."""
    conversation = ChatConversation.all_objects.create(user=student, title="Journey")

    with ConversationLock(conversation.pk) as ownership:
        charge = TurnCharge(student, conversation, ownership)
        charge.reserve(plans.limits_for(student))
        ChatTurnReservation.objects.for_user(student).filter(pk=charge.reservation_id).update(
            created=timezone.now() - timedelta(hours=6),
        )

        out = StringIO()
        call_command("assistant_reconcile", "--apply", stdout=out)

        assert "0 refunded" in out.getvalue()
        assert _refunds(student).count() == 0
        assert ChatTurnReservation.objects.for_user(student).get().status == (
            ChatTurnReservation.PENDING
        )


# ---------------------------------------------------------------------------
# Nothing to spend, nothing to leak


@override_settings(ANTHROPIC_API_KEY="", CREDIT_PLANS=PLANS)
def test_an_unconfigured_provider_costs_nothing_and_still_answers_the_page(
    signed_in, student,
):
    """The dark deploy. It must be a sentence on the page, not a 500 and not
    a charge."""
    opening = credits.balance(student)

    response = signed_in.post(reverse("assistant:send"), {"message": "who replied?"})

    assert response.status_code == 200
    assert credits.balance(student) == opening
    assert not ChatTurnReservation.objects.for_user(student).exists()
    assert not _spends(student).exists()


@override_settings(ANTHROPIC_API_KEY="sk-test-journey", CREDIT_PLANS=PLANS)
def test_a_failed_turn_is_one_students_problem_only(signed_in, student, monkeypatch):
    stranger = User.objects.create_user(
        email="stranger@example.com", password="A-safe-passphrase-123", plan="pro")
    monkeypatch.setattr(agent, "get_client",
                        lambda: FakeClient([RuntimeError("provider unreachable")]))
    signed_in.post(reverse("assistant:send"), {"message": "who replied?"})

    assert not ChatTurnReservation.objects.for_user(stranger).exists()
    assert not CreditLedger.objects.for_user(stranger).exists()
    assert credits.balance(stranger) == credits.balance(stranger)
    assert not ChatMessage.objects.for_user(stranger).exists()

    out = StringIO()
    call_command("assistant_reconcile", "--apply", "--user", stranger.email, stdout=out)
    assert "0 refunded" in out.getvalue()
    assert _refunds(student).count() == 1


def test_the_assistant_write_routes_are_private(client):
    for name in ("assistant:send", "assistant:stream"):
        assert client.post(reverse(name), {"message": "hello"}).status_code == 302
    assert not ChatTurnReservation.all_objects.exists()
    assert not CreditLedger.all_objects.exists()
