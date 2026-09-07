"""A stale request user cannot authorize more AI work after account closure."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from assistant import agent, tools, views
from assistant.lifecycle import INACTIVE_TEXT
from assistant.models import AdvisorMemory, ChatConversation, ChatMessage, ChatTurnReservation
from billing import credits
from billing.models import CreditLedger
from .test_agent import FakeClient, FakeStreamingClient, _response, _text, _tool_use


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def student():
    return get_user_model().objects.create_user(email="lifecycle@example.com", password="x", plan="pro")


@pytest.fixture
def conversation(student):
    return ChatConversation.objects.for_user(student).create(user=student, title="Lifecycle")


def _deactivate(student, *, deleted=False):
    get_user_model().objects.filter(pk=student.pk).update(
        **({"deleted_at": timezone.now()} if deleted else {"is_active": False})
    )


def _client(streaming, response):
    return FakeStreamingClient([([], response)]) if streaming else FakeClient([response])


def _run(student, conversation, client, streaming):
    if streaming:
        events = list(agent.stream_turn(student, conversation, "hello", client=client))
        assert events[-1] == {"type": "notice", "kind": "failed", "text": INACTIVE_TEXT}
        assert not any(event["type"] == "done" for event in events)
    else:
        result = agent.run_turn(student, conversation, "hello", client=client)
        assert not result.ok
        assert result.reason == "inactive_user"
        assert result.reply.text == INACTIVE_TEXT


def _refunded(student, balance):
    assert credits.balance(student) == balance
    assert CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_REFUND).count() == 1
    assert ChatTurnReservation.objects.for_user(student).get().status == ChatTurnReservation.REFUNDED


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("deleted", [False, True])
def test_inactive_account_cannot_start_a_turn(student, conversation, streaming, deleted):
    _deactivate(student, deleted=deleted)
    client = _client(streaming, _response([_text("private answer")], "end_turn"))
    _run(student, conversation, client, streaming)
    assert client.requests == []
    assert not ChatMessage.objects.for_user(student).exists()
    assert not CreditLedger.objects.for_user(student).exists()


@pytest.mark.parametrize("streaming", [False, True])
def test_deactivation_during_context_build_prevents_provider_call(student, conversation, streaming):
    balance = credits.balance(student)
    original = agent._api_messages

    def prepare(*args):
        messages = original(*args)
        _deactivate(student)
        return messages

    client = _client(streaming, _response([_text("private answer")], "end_turn"))
    with patch.object(agent, "_api_messages", side_effect=prepare):
        _run(student, conversation, client, streaming)
    assert client.requests == []
    _refunded(student, balance)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("deleted", [False, True])
@pytest.mark.parametrize("provider_failure", [False, True])
def test_deactivation_during_provider_call_blocks_tools_and_refunds(student, conversation, streaming, deleted, provider_failure):
    balance = credits.balance(student)
    response = _response([_tool_use("remember", {"fact": "private fact"})], "tool_use")
    client = _client(streaming, response)
    method = "stream" if streaming else "create"
    original = getattr(client.messages, method)

    def provider(**kwargs):
        response = original(**kwargs)
        _deactivate(student, deleted=deleted)
        if provider_failure:
            raise RuntimeError("provider failed after account closure")
        return response

    with patch.object(client.messages, method, side_effect=provider), patch.object(tools, "execute") as execute:
        _run(student, conversation, client, streaming)
    execute.assert_not_called()
    assert len(client.requests) == 1
    assert not ChatMessage.objects.for_user(student).filter(role="assistant").exists()
    _refunded(student, balance)


@pytest.mark.parametrize("streaming", [False, True])
def test_deactivation_between_tools_stops_remaining_writes(student, conversation, streaming):
    balance = credits.balance(student)
    response = _response([
        _tool_use("remember", {"fact": "first fact"}, "one"),
        _tool_use("remember", {"fact": "second fact"}, "two"),
    ], "tool_use")
    client = _client(streaming, response)
    original = tools._HANDLERS["remember"]

    def remember(user, args):
        result = original(user, args)
        _deactivate(student)
        return result

    with patch.dict(tools._HANDLERS, {"remember": remember}):
        _run(student, conversation, client, streaming)
    assert list(AdvisorMemory.objects.for_user(student).values_list("text", flat=True)) == ["first fact"]
    assert len(client.requests) == 1
    _refunded(student, balance)


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("provider_failure", [False, True])
def test_hard_deletion_during_provider_call_does_not_recreate_data(student, conversation, streaming, provider_failure):
    user_id = student.pk
    client = _client(streaming, _response([_text("private answer")], "end_turn"))
    method = "stream" if streaming else "create"
    original = getattr(client.messages, method)

    def provider(**kwargs):
        response = original(**kwargs)
        get_user_model().objects.filter(pk=user_id).delete()
        if provider_failure:
            raise RuntimeError("provider failed after account closure")
        return response

    with patch.object(client.messages, method, side_effect=provider):
        _run(student, conversation, client, streaming)
    assert not get_user_model().objects.filter(pk=user_id).exists()
    assert not ChatMessage.objects.for_user(student).exists()
    assert not CreditLedger.objects.for_user(student).exists()


def test_stream_completed_before_deactivation_skips_optional_title(student, conversation):
    conversation.title = ""
    conversation.save(update_fields=["title"])
    client = FakeStreamingClient([([], _response([_text("Done")], "end_turn"))])
    stream = agent.stream_turn(student, conversation, "hello", client=client)
    assert next(stream)["type"] == "done"
    _deactivate(student)
    assert list(stream) == []
    assert client.messages.title_requests == []
    assert ChatTurnReservation.objects.for_user(student).get().status == ChatTurnReservation.SETTLED


def test_send_shows_lifecycle_notice_without_loading_more_private_state(student, conversation, client):
    client.force_login(student)
    provider = FakeClient([_response([_text("private answer")], "end_turn")])
    original = provider.messages.create

    def create(**kwargs):
        _deactivate(student)
        return original(**kwargs)

    with patch.object(agent, "is_configured", return_value=True), \
         patch.object(agent, "get_client", return_value=provider), \
         patch.object(provider.messages, "create", side_effect=create), \
         patch.object(views, "_context", side_effect=AssertionError("private state after account closure")):
        response = client.post(reverse("assistant:send"), {"conversation": conversation.pk, "message": "hello"})
    assert response.status_code == 200
    assert INACTIVE_TEXT in response.content.decode()
    assert "private answer" not in response.content.decode()
