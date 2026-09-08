"""Ownership, socket lifecycle, and real concurrent private mutations."""

from concurrent.futures import ThreadPoolExecutor
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
from assistant.locks import AccountGenerationLock, ConversationLock
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
