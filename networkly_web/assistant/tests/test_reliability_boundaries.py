"""Ownership, socket lifecycle, and real concurrent private mutations."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.db.models.query import QuerySet
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from analytics.models import UserOpportunity
from assistant import agent, brief, tools
from assistant.locks import AccountGenerationLock, ConversationLock, OWNERSHIP_LOST_TEXT
from assistant.models import AdvisorMemory, ChatConversation, ChatMessage
from assistant import plans
from assistant.metering import TurnCharge
from assistant.recovery import reconcile_reservations
from billing import credits
from billing.models import AIJobReservation
from crm.models import Contact, Touch
from directory.models import Firm, Opportunity
from .test_agent import FakeClient, FakeStreamingClient, _response, _text

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("cache_outage", [False, True])
def test_free_daily_brief_throttle_and_cache_outage_never_call_provider(owner, monkeypatch, cache_outage):
    provider = Mock()
    monkeypatch.setattr(brief, "is_configured", lambda: True)
    monkeypatch.setattr(brief, "window_exceeded", Mock(return_value=True,
                         side_effect=RuntimeError("cache offline") if cache_outage else None))
    actions = [{"contact": {"id": 1, "name": "Ada", "firm_text": "Example"},
                "label": "Follow up", "reason": "Due", "closes_on": None}]
    assert brief.get_or_build(owner, actions, client=provider) is None
    provider.messages.create.assert_not_called()


@pytest.mark.parametrize("streaming", [False, True])
def test_refunded_chat_attempts_cannot_call_provider_without_limit(owner, monkeypatch, streaming):
    monkeypatch.setattr("assistant.metering.MAX_TURN_ATTEMPTS_PER_HOUR", 2)
    conversation = ChatConversation(user=owner, title="Failure retries")
    conversation.save()
    before = credits.balance(owner)
    for _ in range(2):
        assert not agent.run_turn(owner, conversation, "Retry", client=FakeClient([RuntimeError("offline")])).ok
    assert credits.balance(owner) == before
    provider = Mock()
    if streaming:
        frames = list(agent.stream_turn(owner, conversation, "Retry", client=provider))
        assert any(frame.get("kind") == "capped" and "in an hour" in frame.get("text", "") for frame in frames)
    else:
        result = agent.run_turn(owner, conversation, "Retry", client=provider)
        assert result.reason == "capped" and "in an hour" in result.reply.text
    provider.messages.create.assert_not_called()
    provider.messages.stream.assert_not_called()
    assert credits.balance(owner) == before


def test_brief_attempt_limit_has_accurate_notice_and_closed_owner_is_rejected(owner, client, monkeypatch):
    contact = Contact(user=owner, name="Brief contact")
    contact.save()
    client.force_login(owner)
    monkeypatch.setattr("crm.views.ai_brief.is_configured", lambda: True)
    monkeypatch.setattr("billing.job_budget.MAX_RESERVATIONS_PER_HOUR", 0)
    url = reverse("crm:contact_ai_brief", args=[contact.pk])
    response = client.post(url)
    assert response.status_code == 200
    assert "Too many brief requests" in response.content.decode()
    assert "midnight" not in response.content.decode()
    def close_before_admission(*args, **kwargs):
        get_user_model().objects.filter(pk=owner.pk).update(is_active=False)
        return None
    monkeypatch.setattr("billing.job_budget.reserve_job", close_before_admission)
    assert client.post(url).status_code == 400


@pytest.mark.parametrize("streaming", [False, True])
def test_rewind_failure_rolls_back_deletion_and_keeps_attachment(owner, client, monkeypatch, streaming):
    conversation = ChatConversation(user=owner, title="Original title")
    conversation.save()
    original = [{"type": "text", "text": "Original question"},
                {"type": "document", "_filename": "resume.pdf", "source": {"data": "private"}}]
    question = ChatMessage(user=owner, conversation=conversation, role="user", content=original)
    question.save()
    answer = ChatMessage(user=owner, conversation=conversation, role="assistant", content=[{"type": "text", "text": "Original answer"}])
    answer.save()
    real_save = ChatMessage.save
    def fail_save(message, *args, **kwargs):
        if message.pk == question.pk and kwargs.get("update_fields") == ["content"]:
            raise RuntimeError("fault after deleting later messages")
        return real_save(message, *args, **kwargs)
    monkeypatch.setattr(ChatMessage, "save", fail_save)
    client.force_login(owner)
    with pytest.raises(RuntimeError, match="fault after deleting"):
        response = client.post(reverse("assistant:edit_message"),
                               {"message": question.pk, "text": "Changed question", **({"stream": "1"} if streaming else {})})
        if streaming:
            list(response.streaming_content)
    question.refresh_from_db()
    conversation.refresh_from_db()
    assert question.content == original
    assert conversation.title == "Original title"
    assert ChatMessage.objects.for_user(owner).filter(pk=answer.pk).exists()


@pytest.mark.parametrize("streaming", [False, True])
def test_rewind_target_deleted_before_ownership_is_a_controlled_response(owner, client, monkeypatch, streaming):
    from assistant import metering
    conversation = ChatConversation(user=owner, title="Existing")
    conversation.save()
    question = ChatMessage(user=owner, conversation=conversation, role="user", content=[{"type": "text", "text": "Question"}])
    question.save()
    answer = ChatMessage(user=owner, conversation=conversation, role="assistant", content=[{"type": "text", "text": "Keep this reply"}])
    answer.save()
    original = metering._check_conversation
    checks = []
    def delete_before_refresh(user, convo):
        original(user, convo)
        checks.append(True)
        if len(checks) == 2:
            ChatMessage.objects.for_user(owner).filter(pk=question.pk).delete()
    monkeypatch.setattr(metering, "_check_conversation", delete_before_refresh)
    client.force_login(owner)
    response = client.post(reverse("assistant:edit_message"),
                           {"message": question.pk, "text": "Changed", **({"stream": "1"} if streaming else {})})
    if streaming:
        assert b"message is no longer available" in b"".join(response.streaming_content)
    else:
        assert response.status_code == 409
        assert b"message is no longer available" in response.content
    assert ChatMessage.objects.for_user(owner).filter(pk=answer.pk).exists()


@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("provider_error", [False, True])
def test_lost_ownership_returns_only_ephemeral_notice(owner, monkeypatch, streaming, provider_error):
    conversation = ChatConversation(user=owner, title="Existing conversation")
    conversation.save()
    ownerships = []
    real_enter = ConversationLock.__enter__
    def capture_ownership(ownership):
        entered = real_enter(ownership)
        ownerships.append(ownership)
        return entered
    monkeypatch.setattr(ConversationLock, "__enter__", capture_ownership)
    def lose_ownership(*args, **kwargs):
        ownerships[-1].database.close()
        if provider_error:
            raise RuntimeError("provider failed after session loss")
        return _response([_text("Stale answer must not persist")], "end_turn")
    provider = Mock()
    provider.messages.create.side_effect = lose_ownership
    @contextmanager
    def broken_stream(*args, **kwargs):
        yield SimpleNamespace(text_stream=iter(["Partial"]), get_final_message=lose_ownership)
    provider.messages.stream.side_effect = broken_stream
    before = credits.balance(owner)
    if streaming:
        events = list(agent.stream_turn(owner, conversation, "Question", client=provider))
        assert any(event.get("text") == OWNERSHIP_LOST_TEXT for event in events)
    else:
        result = agent.run_turn(owner, conversation, "Question", client=provider)
        assert result.reason == "ownership_lost"
        assert result.reply.pk is None and result.reply.text == OWNERSHIP_LOST_TEXT
    assert not ChatMessage.objects.for_user(owner).filter(role="assistant").exists()
    assert credits.balance(owner) == before


@pytest.fixture
def owner():
    return get_user_model().objects.create_user(email="boundaries@example.test", password="x")


@pytest.mark.parametrize("success", [True, False])
def test_owned_chat_transport_closes_on_success_or_failure(owner, monkeypatch, success):
    conversation = ChatConversation(user=owner, title="Existing chat")
    conversation.save()
    client = FakeClient([_response([_text("Answer")], "end_turn") if success else RuntimeError("offline")])
    client.close = Mock()
    monkeypatch.setattr(agent, "is_configured", lambda: True)
    monkeypatch.setattr(agent, "get_client", lambda: client)
    result = agent.run_turn(owner, conversation, "Question")
    assert result.ok is success
    client.close.assert_called_once()


def test_injected_client_is_not_closed_by_turn(owner):
    conversation = ChatConversation(user=owner, title="Existing chat")
    conversation.save()
    client = FakeClient([_response([_text("Answer")], "end_turn")])
    client.close = Mock()
    assert agent.run_turn(owner, conversation, "Question", client=client).ok
    client.close.assert_not_called()


def test_interrupted_stream_closes_owned_transport_and_refunds(owner, monkeypatch):
    conversation = ChatConversation(user=owner, title="Existing chat")
    conversation.save()
    client = FakeStreamingClient([(["First", " second"], _response([_text("First second")], "end_turn"))])
    client.close = Mock()
    monkeypatch.setattr(agent, "is_configured", lambda: True)
    monkeypatch.setattr(agent, "get_client", lambda: client)
    before = credits.balance(owner)
    stream = agent.stream_turn(owner, conversation, "Question")
    for event in stream:
        if event["type"] == "delta":
            break
    stream.close()
    client.close.assert_called_once()
    assert credits.balance(owner) == before


def test_daily_brief_singleflight_and_chat_namespace_are_independent(owner):
    with AccountGenerationLock(owner.pk) as first:
        assert first.acquired
        with AccountGenerationLock(owner.pk) as second:
            assert not second.acquired
        with ConversationLock(owner.pk) as chat:
            assert chat.acquired
        client = Mock()
        assert brief.get_or_build(owner, [], client=client) is None
        client.messages.create.assert_not_called()
    with AccountGenerationLock(owner.pk) as again:
        assert again.acquired


def test_daily_brief_owned_client_closes(owner, monkeypatch):
    client = Mock()
    client.messages.create.return_value = SimpleNamespace(content=[SimpleNamespace(text="Follow up with Ada.")])
    monkeypatch.setattr(brief, "is_configured", lambda: True)
    monkeypatch.setattr(brief, "get_client", lambda: client)
    actions = [{"contact": {"id": 1, "name": "Ada", "firm_text": "Example"}, "label": "Follow up", "reason": "Due", "closes_on": None}]
    assert brief.get_or_build(owner, actions)
    client.close.assert_called_once()


def test_abandoned_chat_refund_does_not_cancel_todays_unrelated_spend(owner):
    conversation = ChatConversation(user=owner, title="Before midnight")
    conversation.save()
    past = timezone.now() - timedelta(days=2)
    with patch("django.utils.timezone.now", return_value=past):
        with ConversationLock(conversation.pk) as ownership:
            charge = TurnCharge(owner, conversation, ownership)
            assert charge.reserve(plans.limits_for(owner))
    credits.spend(owner, 4, "spend_chat")
    assert reconcile_reservations(user=owner, apply=True)["refunded"] == 1
    assert credits.daily_spent(owner) == 4


def test_assistant_save_cannot_erase_concurrent_application_progress(owner, monkeypatch):
    firm = Firm.objects.create(name="Race firm", slug="race-firm")
    opportunity = Opportunity.objects.create(firm=firm, title="Role", url="https://example.test/role")
    tracked = UserOpportunity(user=owner, opportunity=opportunity)
    tracked.save()
    original = QuerySet.first
    changed = False
    def stale_read(queryset):
        nonlocal changed
        result = original(queryset)
        if queryset.model is UserOpportunity and result is not None and not changed:
            changed = True
            UserOpportunity.objects.for_user(owner).filter(pk=tracked.pk).update(applied_status="submitted")
        return result
    monkeypatch.setattr(QuerySet, "first", stale_read)
    result = tools._track_opportunity(owner, {"opportunity_id": opportunity.pk, "status": "saved"})
    assert result["saved"] is False
    tracked.refresh_from_db()
    assert tracked.applied_status == "submitted"


@pytest.mark.django_db(transaction=True)
def test_memory_cap_serializes_two_conversations(owner):
    for index in range(tools.MAX_MEMORIES - 1):
        AdvisorMemory(user=owner, text=f"Fact {index}").save()
    barrier = Barrier(2)
    def save(index):
        try:
            barrier.wait(timeout=10)
            try:
                tools.save_memory(owner, f"Concurrent {index}")
                return True
            except tools.MemoryFull:
                return False
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, [1, 2]))
    assert sorted(results) == [False, True]
    assert AdvisorMemory.objects.for_user(owner).count() == tools.MAX_MEMORIES


@pytest.mark.django_db(transaction=True)
def test_concurrent_brief_clicks_with_last_credit_call_provider_once(owner, settings, monkeypatch):
    settings.ANTHROPIC_API_KEY = "test"
    settings.CREDIT_PLANS = {"free": {"monthly_grant": 1, "message_cost": 1, "daily_burst": 10}}
    contact = Contact(user=owner, name="Ada")
    contact.save()
    provider = Mock(return_value="A short brief")
    monkeypatch.setattr("crm.views.ai_brief.generate_coffee_chat_brief", provider)
    clients = [Client(), Client()]
    for client in clients:
        client.force_login(owner)
    barrier = Barrier(2)
    def request(client):
        try:
            barrier.wait(timeout=10)
            return client.post(reverse("crm:contact_ai_brief", args=[contact.pk])).status_code
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(request, clients)) == [200, 200]
    provider.assert_called_once()
    assert credits.balance(owner) == 0
    assert AIJobReservation.objects.for_user(owner).filter(status="settled").count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_draft_clicks_create_one_touch(owner):
    contact = Contact(user=owner, name="Ada")
    contact.save()
    conversation = ChatConversation(user=owner, title="Draft")
    conversation.save()
    message = ChatMessage(user=owner, conversation=conversation, role="assistant", content=[
        {"type": "text", "text": f"```draft contact={contact.pk} channel=email kind=follow_up\nSubject: Hello\nHi Ada,\nCan we meet?\n```"}])
    message.save()
    clients = [Client(), Client()]
    for client in clients:
        client.force_login(owner)
    barrier = Barrier(2)
    def request(client):
        try:
            barrier.wait(timeout=10)
            return client.post(reverse("assistant:log_draft_touch"), {
                "message": message.pk, "contact": contact.pk, "kind": "follow_up", "channel": "email",
            }).status_code
        finally:
            connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(request, clients)) == [200, 200]
    assert Touch.objects.for_user(owner).filter(contact=contact).count() == 1
