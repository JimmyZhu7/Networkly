"""Reserve bounded provider work before making any non-chat AI requests.

Admission debits the shared ledger under its user-row lock. Each provider
call starts and completes in separate short transactions; no lock spans a
network request. A unique attempt key prevents two workers from executing
the same reservation. Never reuse a key for a distinct retry attempt.

Callers must start_unit immediately before each call, complete_unit on its
normal outcome (including known failure), and finish in a finally block.
Only one unit may be in flight. Expired/closed jobs cannot start more work.
Recovery charges successful units plus an uncertain in-flight unit, refunds
the unused remainder once, and fences the old worker. This intentionally
does not claim a provider call can be cancelled after it has been sent.
"""

from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import credits
from .models import AIJobReservation, CreditLedger

JOB_KINDS = frozenset({CreditLedger.KIND_SPEND_RESCAN, CreditLedger.KIND_SPEND_AUTOPILOT,
                       CreditLedger.KIND_SPEND_BRIEF})
DEFAULT_LEASE_SECONDS = 600
# Credit refunds do not erase provider attempts. These account-wide limits
# cover all non-chat jobs, including known failures and empty model answers.
MAX_RESERVATIONS_PER_HOUR = 60
MAX_PROVIDER_UNITS_PER_HOUR = 600


def _positive_integer(value, name, maximum):
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}.")
    return value


def _owner(user, *, active=False):
    rows = get_user_model().objects.select_for_update().filter(pk=user.pk)
    if active:
        rows = rows.filter(is_active=True, deleted_at__isnull=True)
    return rows.first()


def reserve_job(user, *, kind, requested_units, units_per_credit, job_key=None,
                lease_seconds=DEFAULT_LEASE_SECONDS):
    """Return a newly owned budget, or None for no allowance/duplicate/closure.

    A missing job_key generates a fresh attempt, useful for a synchronous
    request. Queued jobs should provide a durable attempt identifier.
    """
    if kind not in JOB_KINDS:
        raise ValueError("Unsupported non-chat spending kind.")
    if type(requested_units) is not int or not 0 <= requested_units <= 10000:
        raise ValueError("requested_units must be an integer between 0 and 10000.")
    _positive_integer(units_per_credit, "units_per_credit", 1000)
    _positive_integer(lease_seconds, "lease_seconds", 3600)
    if lease_seconds < 60:
        raise ValueError("Lease must allow at least 60 seconds for provider work.")
    if job_key is None:
        job_key = str(uuid4())
    if not isinstance(job_key, str) or not job_key.strip() or len(job_key) > 160:
        raise ValueError("job_key must be a nonempty string of at most 160 characters.")
    if not requested_units:
        return None
    with transaction.atomic():
        owner = _owner(user, active=True)
        if owner is None:
            return None
        if AIJobReservation.objects.for_user(owner).filter(kind=kind, job_key=job_key).exists():
            return None
        recent = AIJobReservation.objects.for_user(owner).filter(
            created__gte=timezone.now() - timedelta(hours=1))
        if recent.count() >= MAX_RESERVATIONS_PER_HOUR:
            return None
        credits.ensure_monthly_grant(owner)
        credits.reconcile_plan_grant(owner)
        available = min(max(0, credits._raw_balance(owner)),
                        max(0, credits.plan_config(owner)["daily_burst"] - credits.daily_spent(owner)))
        allowed = min(requested_units, available * units_per_credit)
        if not allowed:
            return None
        cost = -(-allowed // units_per_credit)
        reservation_id = uuid4()
        debit = CreditLedger.all_objects.create(
            user=owner, delta=-cost, kind=kind,
            props={"job_reservation_id": str(reservation_id), "reserved_units": allowed},
        )
        row = AIJobReservation.all_objects.create(
            id=reservation_id, user=owner, kind=kind, job_key=job_key, debit=debit,
            allowed_units=allowed, units_per_credit=units_per_credit, reserved_credits=cost,
            expires_at=timezone.now() + timedelta(seconds=lease_seconds),
        )
    return JobBudget(user, row, lease_seconds)


def _finish_locked(row, *, recovered=False, reason=""):
    if row.status != AIJobReservation.PENDING:
        return False
    # An interrupted call may have reached the provider. Never refund that
    # uncertain unit and then allow another worker to spend the same budget.
    used = row.successful_units + row.started_units - row.completed_units
    charge = -(-used // row.units_per_credit)
    refund = row.reserved_credits - charge
    if refund:
        CreditLedger.all_objects.create(
            user_id=row.user_id, delta=refund, kind=CreditLedger.KIND_REFUND,
            refund_of_id=row.debit_id,
            props={"job_reservation_id": str(row.pk), "reason": reason},
        )
    row.charged_credits = charge
    row.status = AIJobReservation.RECOVERED if recovered else AIJobReservation.SETTLED
    row.completed_at, row.reason = timezone.now(), reason
    row.save(update_fields=["charged_credits", "status", "completed_at", "reason"])
    return True


class JobBudget:
    def __init__(self, user, row, lease_seconds):
        self.user, self.reservation_id = user, row.pk
        self.allowed_units, self.reserved_credits = row.allowed_units, row.reserved_credits
        self.lease_seconds = lease_seconds
        self._unit = None

    def start_unit(self):
        """Authorize exactly one call. False means do not call the provider."""
        with transaction.atomic():
            if _owner(self.user, active=True) is None:
                return False
            row = AIJobReservation.objects.for_user(self.user).select_for_update().filter(pk=self.reservation_id).first()
            if row is None or row.status != AIJobReservation.PENDING or row.expires_at <= timezone.now():
                return False
            if row.started_units != row.completed_units or row.started_units >= row.allowed_units:
                return False
            # Every started unit renews expires_at. This conservative window
            # includes all calls begun in the last hour, even in a job that
            # began earlier; old calls in a still-active batch also count.
            # The shared user lock serializes admission across job kinds.
            attempted = AIJobReservation.objects.for_user(self.user).filter(
                expires_at__gte=timezone.now() - timedelta(hours=1),
            ).aggregate(total=Sum("started_units"))["total"] or 0
            if attempted >= MAX_PROVIDER_UNITS_PER_HOUR:
                return False
            row.started_units += 1
            row.expires_at = timezone.now() + timedelta(seconds=self.lease_seconds)
            row.save(update_fields=["started_units", "expires_at"])
            self._unit = row.started_units
        return True

    def complete_unit(self, *, success):
        """Record a known outcome once. False means recovery already fenced it."""
        if type(success) is not bool:
            raise ValueError("success must be a boolean.")
        with transaction.atomic():
            if _owner(self.user) is None:
                return False
            row = AIJobReservation.objects.for_user(self.user).select_for_update().filter(pk=self.reservation_id).first()
            if (row is None or row.status != AIJobReservation.PENDING or self._unit is None
                    or row.started_units != self._unit or row.completed_units >= self._unit):
                return False
            row.completed_units += 1
            row.successful_units += int(success)
            row.expires_at = timezone.now() + timedelta(seconds=self.lease_seconds)
            row.save(update_fields=["completed_units", "successful_units", "expires_at"])
            self._unit = None
        return True

    def finish(self, *, reason="completed"):
        if not isinstance(reason, str) or len(reason) > 80:
            raise ValueError("reason must be a string of at most 80 characters.")
        with transaction.atomic():
            if _owner(self.user) is None:
                return False
            row = AIJobReservation.objects.for_user(self.user).select_for_update().filter(pk=self.reservation_id).first()
            return bool(row and _finish_locked(row, reason=reason))


def reconcile_job_reservations(*, user=None, apply=False, limit=100):
    """Inspect/recover expired reservations in bounded batches; dry-run default."""
    _positive_integer(limit, "limit", 1000)
    rows = AIJobReservation.all_objects.filter(status=AIJobReservation.PENDING,
                                             expires_at__lte=timezone.now())
    if user is not None:
        rows = rows.filter(user_id=user.pk)
    candidates = list(rows.order_by("expires_at", "pk").values_list("pk", "user_id")[:limit])
    stats = {"checked": 0, "recoverable": 0, "recovered": 0}
    for pk, owner_id in candidates:
        with transaction.atomic():
            owner = get_user_model().objects.select_for_update().filter(pk=owner_id).first()
            if owner is None:
                continue
            row = AIJobReservation.objects.for_user(owner).select_for_update().filter(pk=pk).first()
            stats["checked"] += 1
            if row is None or row.status != AIJobReservation.PENDING or row.expires_at > timezone.now():
                continue
            stats["recoverable"] += 1
            if apply and _finish_locked(row, recovered=True, reason="expired_worker_recovered"):
                stats["recovered"] += 1
    return stats
