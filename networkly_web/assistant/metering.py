"""Durable chat credits, settled/refunded once under conversation ownership."""

from contextlib import AbstractContextManager
from datetime import timedelta
from functools import wraps
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from billing import credits
from billing.models import CreditLedger
from .client import close_client
from .locks import BUSY_TEXT, OWNERSHIP_LOST_TEXT, ConversationLock, OwnershipLostError
from .lifecycle import INACTIVE_TEXT, InactiveAccountError, require_active_user
from .models import ChatConversation, ChatMessage, ChatTurnReservation

MAX_TURN_ATTEMPTS_PER_HOUR = 60
ATTEMPT_LIMIT_TEXT = "You've requested too many replies recently. Try again in an hour."


class StaleMessageError(RuntimeError):
    """A previous edit removed this target before the current edit acquired ownership."""


def finish_reservation(user, reservation_id, *, status, reason="", reply=None):
    """One short transaction commits the outcome and any compensating credit.

    Taking the user lock first matches reserve and the billing ledger's lock
    order. A repeated callback or recovery sees a terminal row and does nothing.
    """
    with transaction.atomic():
        # Hard deletion cascades the ledger and reservations. Cleanup of a
        # now-absent account must not recreate data or turn a stopped stream
        # into an exception while trying to refund a deleted reservation.
        if get_user_model().objects.select_for_update().filter(pk=user.pk).first() is None:
            return False
        row = ChatTurnReservation.objects.for_user(user).select_for_update().get(pk=reservation_id)
        if row.status != ChatTurnReservation.PENDING:
            return False
        if status == ChatTurnReservation.REFUNDED:
            debit = CreditLedger.objects.for_user(user).filter(
                kind=CreditLedger.KIND_SPEND_CHAT, props__reservation_id=str(row.id),
            ).first()
            credits.refund(user, row.cost, refund_of=debit,
                           reason=reason, model=row.model, reservation_id=str(row.id))
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
        self._clients = []
        self.block_notice = ""

    def open_client(self, factory):
        client = factory()
        self._clients.append(client)
        return client

    def ensure_owned(self):
        self.ownership.ensure_owned()
        require_active_user(self.user)

    def reserve(self, limits):
        self.ensure_owned()
        with transaction.atomic():
            owner = get_user_model().objects.select_for_update().filter(pk=self.user.pk).first()
            if owner is None or not owner.is_active or owner.deleted_at is not None:
                raise InactiveAccountError(INACTIVE_TEXT)
            attempted = CreditLedger.objects.for_user(owner).filter(
                kind=CreditLedger.KIND_SPEND_CHAT,
                created__gte=timezone.now() - timedelta(hours=1),
            ).count()
            if attempted >= MAX_TURN_ATTEMPTS_PER_HOUR:
                self.block_notice = ATTEMPT_LIMIT_TEXT
                return False
            if not credits.can_spend(owner, limits.message_cost):
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
        try:
            self.refund(reason="turn_interrupted")
        finally:
            for client in self._clients:
                close_client(client)
            self._clients.clear()
        return False


def _check_conversation(user, conversation):
    if not ChatConversation.objects.for_user(user).filter(pk=conversation.pk).exists():
        raise PermissionDenied("This conversation is unavailable.")
    conversation.refresh_from_db()


def charge_turn(function):
    @wraps(function)
    def wrapped(user, conversation, *args, **kwargs):
        from .agent import TurnResult, _notice
        def inactive():
            return TurnResult(ok=False, reason="inactive_user", reply=_notice(
                user, conversation, ChatMessage.NOTICE_FAILED, INACTIVE_TEXT,
            ))

        try:
            require_active_user(user)
        except InactiveAccountError:
            return inactive()
        _check_conversation(user, conversation)
        with ConversationLock(conversation.pk) as ownership:
            if not ownership.acquired:
                return TurnResult(ok=False, reason="busy", reply=_notice(user, conversation, "busy", BUSY_TEXT))
            _check_conversation(user, conversation)
            prepare = kwargs.pop("prepare_turn", None)
            with TurnCharge(user, conversation, ownership) as charge:
                try:
                    charge.ensure_owned()
                    if prepare is not None:
                        prepare()
                    result = function(user, conversation, *args, **kwargs, charge=charge)
                    if result.ok:
                        charge.keep(reply=result.reply)
                    return result
                except InactiveAccountError:
                    charge.refund(reason="account_inactive")
                    return inactive()
                except OwnershipLostError:
                    charge.refund(reason="ownership_lost")
                    return TurnResult(ok=False, reason="ownership_lost", reply=_notice(
                        user, conversation, ChatMessage.NOTICE_FAILED, OWNERSHIP_LOST_TEXT,
                    ))
                except StaleMessageError as exc:
                    return TurnResult(ok=False, reason="stale_message", reply=_notice(
                        user, conversation, ChatMessage.NOTICE_FAILED, str(exc),
                    ))
    return wrapped


def charge_stream(function):
    @wraps(function)
    def wrapped(user, conversation, *args, **kwargs):
        try:
            require_active_user(user)
        except InactiveAccountError:
            yield {"type": "notice", "kind": "failed", "text": INACTIVE_TEXT}
            return
        _check_conversation(user, conversation)
        with ConversationLock(conversation.pk) as ownership:
            if not ownership.acquired:
                yield {"type": "notice", "kind": "busy", "text": BUSY_TEXT}
                return
            _check_conversation(user, conversation)
            prepare = kwargs.pop("prepare_turn", None)
            with TurnCharge(user, conversation, ownership) as charge:
                stream = None
                try:
                    charge.ensure_owned()
                    if prepare is not None:
                        prepare()
                    stream = function(user, conversation, *args, **kwargs, charge=charge)
                    for event in stream:
                        if event.get("type") == "done":
                            reply = ChatMessage.objects.for_user(user).get(pk=event["message_id"], conversation=conversation)
                            charge.keep(reply=reply)
                        yield event
                except InactiveAccountError:
                    charge.refund(reason="account_inactive")
                    yield {"type": "notice", "kind": "failed", "text": INACTIVE_TEXT}
                except OwnershipLostError:
                    charge.refund(reason="ownership_lost")
                    yield {"type": "notice", "kind": "failed", "text": OWNERSHIP_LOST_TEXT}
                except StaleMessageError as exc:
                    yield {"type": "notice", "kind": "failed", "text": str(exc)}
                finally:
                    if stream is not None:
                        stream.close()
    return wrapped
