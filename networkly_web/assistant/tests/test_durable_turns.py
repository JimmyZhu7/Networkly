"""Real PostgreSQL ownership and durable settlement; providers are all fake."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
import multiprocessing
from threading import Event
import time
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import close_old_connections, connection
from django.urls import reverse
from django.utils import timezone

from assistant import agent, plans
from assistant.locks import BUSY_TEXT, ConversationLock
from assistant.metering import TurnCharge, finish_reservation
from assistant.models import ChatConversation, ChatMessage, ChatTurnReservation
from assistant.recovery import reconcile_reservations
from billing import credits
from billing.models import CreditLedger
from .test_agent import FakeClient, FakeStreamingClient, _response, _text


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def student():
    return get_user_model().objects.create_user(email="durable@example.com", password="x", plan="pro")


@pytest.fixture
def conversation(student):
    row = ChatConversation(user=student, title="Durable turns")
    row.save()
    return row


def _abandon(student, conversation, *, age_minutes=60):
    # Closing a dedicated session has the same PostgreSQL ownership effect
    # as worker death. Deliberately omit TurnCharge.__exit__ to model SIGKILL.
    with ConversationLock(conversation.pk) as ownership:
        charge = TurnCharge(student, conversation, ownership)
        assert charge.reserve(plans.limits_for(student))
    ChatTurnReservation.objects.for_user(student).filter(pk=charge.reservation_id).update(
        created=timezone.now() - timedelta(minutes=age_minutes),
    )
    return charge.reservation_id


def _reserve_until_killed(user_id, conversation_id, output):
    close_old_connections()
    owner = get_user_model().objects.get(pk=user_id)
    conversation = ChatConversation.objects.for_user(owner).get(pk=conversation_id)
    with ConversationLock(conversation_id) as ownership:
        charge = TurnCharge(owner, conversation, ownership)
        assert charge.reserve(plans.limits_for(owner))
        output.put(str(charge.reservation_id))
        time.sleep(120)  # The parent kills this worker before normal cleanup.


def test_hard_killed_worker_releases_ownership_and_recovers_its_credit(student, conversation):
    if "fork" not in multiprocessing.get_all_start_methods():
        pytest.skip("This process-death regression requires POSIX fork.")
    before = credits.balance(student)
    # No inherited live database socket: both parent and child reconnect to
    # the already-configured pytest database after the fork.
    connection.close()
    context = multiprocessing.get_context("fork")
    output = context.Queue()
    worker = context.Process(target=_reserve_until_killed, args=(student.pk, conversation.pk, output))
    worker.start()
    try:
        reservation_id = output.get(timeout=10)
        ChatTurnReservation.objects.for_user(student).filter(pk=reservation_id).update(
            created=timezone.now() - timedelta(hours=1),
        )
        assert reconcile_reservations(apply=True)["busy"] == 1
        worker.kill()
        worker.join(timeout=10)
        assert not worker.is_alive()
        assert reconcile_reservations(apply=True)["refunded"] == 1
        assert reconcile_reservations(apply=True)["refunded"] == 0
        assert credits.balance(student) == before
    finally:
        if worker.is_alive():
            worker.kill()
            worker.join(timeout=10)
        output.close()


def test_abandoned_turn_refunds_exactly_once(student, conversation):
    before = credits.balance(student)
    reservation_id = _abandon(student, conversation)
    assert credits.balance(student) == before - 3
    assert reconcile_reservations(apply=True)["refunded"] == 1
    assert reconcile_reservations(apply=True)["refunded"] == 0
    row = ChatTurnReservation.objects.for_user(student).get(pk=reservation_id)
    assert row.status == ChatTurnReservation.REFUNDED
    assert row.completed_at is not None
    assert credits.balance(student) == before
    assert credits.daily_spent(student) == 0
    assert CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_REFUND).count() == 1


def test_age_never_authorizes_refund_while_owner_is_alive(student, conversation):
    before = credits.balance(student)
    with ConversationLock(conversation.pk) as ownership:
        with TurnCharge(student, conversation, ownership) as charge:
            assert charge.reserve(plans.limits_for(student))
            ChatTurnReservation.objects.for_user(student).filter(pk=charge.reservation_id).update(
                created=timezone.now() - timedelta(days=30),
            )
            stats = reconcile_reservations(apply=True)
            assert stats["busy"] == 1
            assert stats["refunded"] == 0
            assert credits.balance(student) == before - 3
    assert credits.balance(student) == before


def test_young_or_dry_run_reservations_are_not_refunded(student, conversation):
    reservation_id = _abandon(student, conversation, age_minutes=1)
    assert reconcile_reservations(apply=True)["checked"] == 0
    ChatTurnReservation.objects.for_user(student).filter(pk=reservation_id).update(
        created=timezone.now() - timedelta(hours=1),
    )
    stats = reconcile_reservations(apply=False)
    assert stats["recoverable"] == 1 and stats["refunded"] == 0
    assert ChatTurnReservation.objects.for_user(student).get(pk=reservation_id).status == "pending"


def test_two_recovery_workers_cannot_double_refund(student, conversation):
    reservation_id = _abandon(student, conversation)

    def recover(_):
        close_old_connections()
        try:
            owner = get_user_model().objects.get(pk=student.pk)
            return reconcile_reservations(user=owner, apply=True)["refunded"]
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(recover, range(2)))
    assert sum(results) == 1
    assert CreditLedger.objects.for_user(student).filter(
        kind=CreditLedger.KIND_REFUND, props__reservation_id=str(reservation_id),
    ).count() == 1


def test_refund_and_terminal_state_roll_back_together(student, conversation):
    reservation_id = _abandon(student, conversation)
    original_refund = credits.refund

    def interrupted_refund(*args, **kwargs):
        original_refund(*args, **kwargs)
        raise RuntimeError("Interrupted before terminal state")

    with patch("assistant.metering.credits.refund", side_effect=interrupted_refund), pytest.raises(RuntimeError):
        reconcile_reservations(apply=True)
    assert not CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_REFUND).exists()
    assert ChatTurnReservation.objects.for_user(student).get(pk=reservation_id).status == "pending"
    assert reconcile_reservations(apply=True)["refunded"] == 1


def test_settlement_and_saved_answer_commit_together(student, conversation):
    before = credits.balance(student)
    result = agent.run_turn(student, conversation, "hello", client=FakeClient([
        _response([_text("Complete answer")], "end_turn"),
    ]))
    row = ChatTurnReservation.objects.for_user(student).get()
    assert result.ok and row.status == "settled" and row.reply_id == result.reply.pk
    assert row.reply.text == "Complete answer"
    ChatTurnReservation.objects.for_user(student).filter(pk=row.pk).update(created=timezone.now() - timedelta(days=3))
    assert reconcile_reservations(apply=True)["refunded"] == 0
    assert credits.balance(student) == before - 3


def test_failed_settlement_rolls_back_answer_and_remains_refundable(student, conversation):
    before = credits.balance(student)
    original = finish_reservation

    def fail_settle(*args, **kwargs):
        if kwargs["status"] == ChatTurnReservation.SETTLED:
            raise RuntimeError("Database interruption")
        return original(*args, **kwargs)

    with patch("assistant.metering.finish_reservation", side_effect=fail_settle), pytest.raises(RuntimeError):
        agent.run_turn(student, conversation, "hello", client=FakeClient([
            _response([_text("Must roll back")], "end_turn"),
        ]))
    assert not ChatMessage.objects.for_user(student).filter(role="assistant").exists()
    assert credits.balance(student) == before
    assert ChatTurnReservation.objects.for_user(student).get().status == "refunded"


def test_deleted_chat_does_not_delete_refund_obligation(student, conversation):
    before = credits.balance(student)
    reservation_id = _abandon(student, conversation)
    key = conversation.pk
    conversation.delete()
    row = ChatTurnReservation.objects.for_user(student).get(pk=reservation_id)
    assert row.conversation_id is None and row.conversation_key == key
    assert reconcile_reservations(apply=True)["refunded"] == 1
    assert credits.balance(student) == before


def test_recovery_is_tenant_scoped(student, conversation):
    _abandon(student, conversation)
    other = get_user_model().objects.create_user(email="durable-other@example.com", password="x")
    assert reconcile_reservations(user=other, apply=True)["checked"] == 0
    row = ChatTurnReservation.objects.for_user(student).get()
    with pytest.raises(ChatTurnReservation.DoesNotExist):
        finish_reservation(other, row.pk, status=ChatTurnReservation.REFUNDED)
    assert ChatTurnReservation.objects.for_user(student).get().status == "pending"


def test_second_worker_is_rejected_before_history_or_provider_or_credit(student, conversation):
    entered, release = Event(), Event()

    def first():
        close_old_connections()
        try:
            owner = get_user_model().objects.get(pk=student.pk)
            chat = ChatConversation.objects.for_user(owner).get(pk=conversation.pk)
            client = FakeClient([])

            def create(**kwargs):
                assert not connection.in_atomic_block
                entered.set()
                assert release.wait(timeout=10)
                return _response([_text("Finished")], "end_turn")

            client.messages.create = create
            return agent.run_turn(owner, chat, "First request", client=client)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(first)
        try:
            assert entered.wait(timeout=10)
            second_client = FakeClient([])
            second = agent.run_turn(student, conversation, "Do not save this", client=second_client)
            assert second.reason == "busy" and BUSY_TEXT in second.reply.text
            assert second_client.requests == []
            assert not ChatMessage.objects.for_user(student).filter(content__contains=[{"type": "text", "text": "Do not save this"}]).exists()
            assert ChatTurnReservation.objects.for_user(student).count() == 1
        finally:
            release.set()
        assert running.result(timeout=10).ok


def test_stream_busy_notice_has_no_charge_or_persisted_input(student, conversation):
    with ConversationLock(conversation.pk):
        frames = list(agent.stream_turn(student, conversation, "retry later", client=FakeStreamingClient([])))
    assert frames == [{"type": "notice", "kind": "busy", "text": BUSY_TEXT}]
    assert not ChatMessage.objects.for_user(student).exists()
    assert not ChatTurnReservation.objects.for_user(student).exists()


@pytest.mark.parametrize("streaming", [False, True])
def test_edit_cannot_rewind_an_active_turn(student, conversation, client, streaming):
    question = ChatMessage(user=student, conversation=conversation, role="user", content=[{"type": "text", "text": "Original"}])
    question.save()
    answer = ChatMessage(user=student, conversation=conversation, role="assistant", content=[{"type": "text", "text": "Keep this answer"}])
    answer.save()
    client.force_login(student)
    with ConversationLock(conversation.pk):
        response = client.post(reverse("assistant:edit_message"), {
            "message": question.pk, "text": "Changed", **({"stream": "1"} if streaming else {}),
        })
        if streaming:
            assert b'"kind": "busy"' in b"".join(response.streaming_content)
        else:
            assert response.status_code == 409
    question.refresh_from_db()
    assert question.text == "Original"
    assert ChatMessage.objects.for_user(student).filter(pk=answer.pk).exists()


def test_delete_is_rejected_while_conversation_is_owned(student, conversation, client):
    client.force_login(student)
    with ConversationLock(conversation.pk):
        response = client.post(reverse("assistant:delete"), {"conversation": conversation.pk})
    assert response.status_code == 409
    assert ChatConversation.objects.for_user(student).filter(pk=conversation.pk).exists()


def test_busy_send_restores_text_without_persisting_it(student, conversation, client):
    client.force_login(student)
    with ConversationLock(conversation.pk):
        response = client.post(reverse("assistant:send"), {"conversation": conversation.pk, "message": "Keep my draft"})
    assert response.status_code == 200
    assert b"Keep my draft</textarea>" in response.content
    assert BUSY_TEXT.encode() in response.content
    assert not ChatMessage.objects.for_user(student).exists()


def test_recovery_command_is_dry_by_default_and_apply_is_idempotent(student, conversation):
    _abandon(student, conversation)
    output = StringIO()
    call_command("assistant_reconcile", stdout=output)
    assert "1 recoverable; 0 refunded (dry run)" in output.getvalue()
    call_command("assistant_reconcile", apply=True, stdout=StringIO())
    call_command("assistant_reconcile", apply=True, stdout=StringIO())
    assert CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_REFUND).count() == 1


def test_interrupted_tool_replay_reports_unknown_outcome_without_reexecuting():
    messages = [
        {"role": "assistant", "content": [{"type": "tool_use", "id": "lost", "name": "log_touch", "input": {}}]},
        {"role": "user", "content": [{"type": "text", "text": "What happened?"}]},
    ]
    fixed = agent._repair_interrupted_tools(messages)
    result = fixed[1]["content"][0]
    assert result["tool_use_id"] == "lost" and result["is_error"]
    assert "outcome is unknown" in result["content"]
    assert fixed[1]["content"][1]["text"] == "What happened?"
