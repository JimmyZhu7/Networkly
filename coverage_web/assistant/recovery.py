"""Conservative recovery of credits left pending by a killed worker."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from .locks import ConversationLock
from .metering import finish_reservation
from .models import ChatTurnReservation


DEFAULT_RECOVERY_MINUTES = 30


def reconcile_reservations(*, user=None, apply=False, older_than_minutes=DEFAULT_RECOVERY_MINUTES, limit=100):
    if older_than_minutes < 1 or not 1 <= limit <= 1000:
        raise ValueError("Recovery age must be positive and limit must be between 1 and 1000.")
    cutoff = timezone.now() - timedelta(minutes=older_than_minutes)
    users = get_user_model().objects.filter(
        assistant_reservations__status=ChatTurnReservation.PENDING,
        assistant_reservations__created__lt=cutoff,
    ).distinct().order_by("pk")
    if user is not None:
        users = users.filter(pk=user.pk)
    stats = {"checked": 0, "recoverable": 0, "busy": 0, "refunded": 0}
    for owner in users.iterator():
        rows = ChatTurnReservation.objects.for_user(owner).filter(
            status=ChatTurnReservation.PENDING, created__lt=cutoff,
        ).order_by("created", "pk")[:limit - stats["checked"]]
        for row in rows:
            stats["checked"] += 1
            # Age selects candidates, but NEVER proves a process is dead.
            # A live turn, however long, owns this same dedicated session
            # lock. A process kill releases it at PostgreSQL automatically.
            with ConversationLock(row.conversation_key) as ownership:
                if not ownership.acquired:
                    stats["busy"] += 1
                    continue
                ownership.ensure_owned()
                stats["recoverable"] += 1
                if apply and finish_reservation(
                    owner, row.pk, status=ChatTurnReservation.REFUNDED,
                    reason="abandoned_turn_recovered",
                ):
                    stats["refunded"] += 1
        if stats["checked"] >= limit:
            break
    return stats
