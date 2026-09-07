"""Concurrent and interrupted chat turns keep the credit gate truthful."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.db.models import Sum
from django.test import override_settings

from assistant import agent, plans
from assistant.metering import TurnCharge
from assistant.locks import ConversationLock
from assistant.models import ChatConversation, ChatMessage
from billing import credits
from billing.models import CreditLedger
from .test_agent import FakeClient, FakeStreamingClient, _response, _text


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def student():
    return get_user_model().objects.create_user(email="reserve@example.com", password="x", plan="pro")


@pytest.fixture
def conversation(student):
    row = ChatConversation(user=student, title="Credits")
    row.save()
    return row


@override_settings(CREDIT_PLANS={"pro": {"monthly_grant": 1, "message_cost": 3, "daily_burst": 45}})
def test_last_credit_allows_only_one_concurrent_turn_and_one_overdraw(student):
    if connection.vendor != "postgresql":
        pytest.skip("Requires the production database's row locks")
    assert credits.balance(student) == 1
    barrier = Barrier(2)

    def reserve():
        close_old_connections()
        try:
            user = get_user_model().objects.get(pk=student.pk)
            conversation = ChatConversation(user=user, title="Concurrent credit check")
            conversation.save()
            barrier.wait(timeout=10)
            with ConversationLock(conversation.pk) as ownership:
                with TurnCharge(user, conversation, ownership) as charge:
                    allowed = charge.reserve(plans.limits_for(user))
                    if allowed:
                        reply = ChatMessage(user=user, conversation=conversation, role="assistant",
                                            content=[{"type": "text", "text": "Done"}])
                        reply.save()
                        charge.keep(reply=reply)
                    return allowed
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: reserve(), range(2)))
    assert sorted(outcomes) == [False, True]
    # Public balances deliberately display zero once exhausted; the ledger
    # retains the one permitted overdraw and must contain only one charge.
    assert credits.balance(student) == 0
    assert CreditLedger.objects.for_user(student).aggregate(total=Sum("delta"))["total"] == -2
    assert CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_SPEND_CHAT).count() == 1
    assert credits.daily_spent(student) == 3


def test_credit_is_reserved_before_provider_call(student, conversation):
    before = credits.balance(student)
    client = FakeClient([_response([_text("Done")], "end_turn")])
    create = client.messages.create

    def checked_create(**kwargs):
        assert credits.balance(student) == before - plans.limits_for(student).message_cost
        return create(**kwargs)

    client.messages.create = checked_create
    assert agent.run_turn(student, conversation, "hello", client=client).ok
    assert credits.balance(student) == before - 3


def test_first_provider_failure_refunds_once_and_restores_burst(student, conversation):
    before = credits.balance(student)
    result = agent.run_turn(student, conversation, "hello", client=FakeClient([RuntimeError("offline")]))
    assert not result.ok
    assert credits.balance(student) == before
    assert credits.daily_spent(student) == 0
    assert CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_REFUND).count() == 1


def test_browser_disconnect_refunds_inflight_stream(student, conversation):
    before = credits.balance(student)
    client = FakeStreamingClient([
        (["First words"], _response([_text("A complete answer")], "end_turn")),
    ])
    stream = agent.stream_turn(student, conversation, "hello", client=client)
    assert next(stream) == {"type": "delta", "text": "First words"}
    assert credits.balance(student) == before - 3
    stream.close()
    assert credits.balance(student) == before
    assert credits.daily_spent(student) == 0


def test_completed_stream_retains_only_one_charge(student, conversation):
    before = credits.balance(student)
    client = FakeStreamingClient([([], _response([_text("Done")], "end_turn"))])
    assert list(agent.stream_turn(student, conversation, "hello", client=client))[-1]["type"] == "done"
    assert credits.balance(student) == before - 3
    assert not CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_REFUND).exists()


def test_unexpected_post_provider_failure_does_not_strand_reservation(student, conversation):
    before = credits.balance(student)
    client = FakeClient([_response([_text("Done")], "end_turn")])
    with patch.object(agent, "_log_usage", side_effect=RuntimeError("write failed")), pytest.raises(RuntimeError):
        agent.run_turn(student, conversation, "hello", client=client)
    assert credits.balance(student) == before
    assert credits.daily_spent(student) == 0
