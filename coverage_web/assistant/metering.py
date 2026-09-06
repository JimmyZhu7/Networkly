"""Durable chat credits, settled/refunded once under conversation ownership."""

from contextlib import AbstractContextManager
from functools import wraps
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from billing import credits
from .locks import BUSY_TEXT, ConversationLock
from .models import ChatConversation, ChatMessage, ChatTurnReservation


def finish_reservation(user, reservation_id, *, status, reason="", reply=None):
    """One short transaction commits the outcome and any compensating credit.

    Taking the user lock first matches reserve and the billing ledger's lock
    order. A repeated callback or recovery sees a terminal row and does nothing.
    """
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        row = ChatTurnReservation.objects.for_user(user).select_for_update().get(pk=reservation_id)
        if row.status != ChatTurnReservation.PENDING:
            return False
        if status == ChatTurnReservation.REFUNDED:
            credits.refund(user, row.cost, reason=reason, model=row.model, reservation_id=str(row.id))
        elif status == ChatTurnReservation.SETTLED:
            if reply is None or reply.user_id != user.pk or reply.conversation_id != row.conversation_key:
                raise ValueError("Settlement requires this conversation's saved answer.")
            saved = ChatMessage.objects.for_user(user).get(
                pk=reply.pk, conversation_id=row.conversation_key,
                role=ChatMessage.ROLE_ASSISTANT, notice="",
            )
            if not saved.text.strip():
                raise ValueError("An empty answer cannot settle a reservation.")
            row.reply = saved
        else:
            raise ValueError("A reservation can only settle or refund.")
        row.status, row.completed_at, row.reason = status, timezone.now(), reason
        row.save(update_fields=["status", "completed_at", "reason", "reply"])
    return True


class TurnCharge(AbstractContextManager):
    def __init__(self, user, conversation, ownership):
        self.user, self.conversation, self.ownership = user, conversation, ownership
        self.pending = False
        self.reservation_id = uuid4()

    def ensure_owned(self):
        self.ownership.ensure_owned()

    def reserve(self, limits):
        self.ensure_owned()
        with transaction.atomic():
            get_user_model().objects.select_for_update().get(pk=self.user.pk)
            if not credits.can_spend(self.user, limits.message_cost):
                return False
            row = ChatTurnReservation(
                id=self.reservation_id, user=self.user, conversation=self.conversation,
                conversation_key=self.conversation.pk, cost=limits.message_cost, model=limits.model,
            )
            row.save(force_insert=True)
            credits.spend(
                self.user, limits.message_cost, "spend_chat", model=limits.model,
                reservation_id=str(self.reservation_id),
            )
        self.pending = True
        return True

    def refund(self, *, reason, model=None):
        if self.pending:
            finish_reservation(self.user, self.reservation_id, status=ChatTurnReservation.REFUNDED, reason=reason)
            self.pending = False

    def keep(self, *, reply):
        if self.pending:
            self.ensure_owned()
            finish_reservation(self.user, self.reservation_id, status=ChatTurnReservation.SETTLED, reply=reply)
            self.pending = False

    def __exit__(self, *exc):
        self.refund(reason="turn_interrupted")
        return False


def _check_conversation(user, conversation):
    if not ChatConversation.objects.for_user(user).filter(pk=conversation.pk).exists():
        raise PermissionDenied("This conversation is unavailable.")
    conversation.refresh_from_db()


def charge_turn(function):
    @wraps(function)
    def wrapped(user, conversation, *args, **kwargs):
        from .agent import TurnResult, _notice
        _check_conversation(user, conversation)
        with ConversationLock(conversation.pk) as ownership:
            if not ownership.acquired:
                return TurnResult(ok=False, reason="busy", reply=_notice(user, conversation, "busy", BUSY_TEXT))
            _check_conversation(user, conversation)
            prepare = kwargs.pop("prepare_turn", None)
            if prepare is not None:
                prepare()
            with TurnCharge(user, conversation, ownership) as charge:
                result = function(user, conversation, *args, **kwargs, charge=charge)
                if result.ok:
                    charge.keep(reply=result.reply)
                return result
    return wrapped


def charge_stream(function):
    @wraps(function)
    def wrapped(user, conversation, *args, **kwargs):
        _check_conversation(user, conversation)
        with ConversationLock(conversation.pk) as ownership:
            if not ownership.acquired:
                yield {"type": "notice", "kind": "busy", "text": BUSY_TEXT}
                return
            _check_conversation(user, conversation)
            prepare = kwargs.pop("prepare_turn", None)
            if prepare is not None:
                prepare()
            with TurnCharge(user, conversation, ownership) as charge:
                stream = function(user, conversation, *args, **kwargs, charge=charge)
                try:
                    for event in stream:
                        if event.get("type") == "done":
                            reply = ChatMessage.objects.for_user(user).get(pk=event["message_id"], conversation=conversation)
                            charge.keep(reply=reply)
                        yield event
                finally:
                    stream.close()
    return wrapped
