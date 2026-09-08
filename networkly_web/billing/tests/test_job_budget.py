"""Real ledger, fault boundaries, and concurrent admission for provider jobs."""

import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import connections
from django.utils import timezone

from billing import credits
from billing.job_budget import reserve_job, reconcile_job_reservations, JobBudget
from billing.models import AIJobReservation, CreditLedger

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(settings):
    settings.CREDIT_PLANS = {"free": {"monthly_grant": 60, "message_cost": 1, "daily_burst": 15}}
    settings.BETA_ENABLED = False
    return get_user_model().objects.create_user(email="job-budget@example.test", password="x", timezone="UTC")


def reserve(owner, **kwargs):
    return reserve_job(owner, kind=CreditLedger.KIND_SPEND_RESCAN,
                       requested_units=kwargs.pop("requested_units", 30), units_per_credit=10, **kwargs)


def leave(owner, amount):
    current = credits.balance(owner)
    CreditLedger.all_objects.create(user=owner, kind="adjust", delta=amount-current)


def expire(job):
    AIJobReservation.objects.for_user(job.user).filter(pk=job.reservation_id).update(
        expires_at=timezone.now() - timedelta(seconds=1))


def test_reserves_before_calls_and_partial_settlement_is_idempotent(owner):
    before = credits.balance(owner)
    job = reserve(owner)
    assert credits.balance(owner) == before - 3
    assert credits.daily_spent(owner) == 3
    for _ in range(11):
        assert job.start_unit()
        assert not job.start_unit()
        assert job.complete_unit(success=True)
        assert not job.complete_unit(success=True)
    assert job.finish()
    assert not job.finish()
    assert not job.start_unit()
    assert credits.balance(owner) == before - 2
    assert credits.daily_spent(owner) == 2
    assert credits.month_usage(owner) == 2
    row = AIJobReservation.objects.for_user(owner).get(pk=job.reservation_id)
    assert (row.started_units, row.successful_units, row.charged_credits) == (11, 11, 2)
    assert CreditLedger.objects.for_user(owner).filter(kind="refund").count() == 1


def test_failure_and_no_work_refund_reserved_credit(owner):
    before = credits.balance(owner)
    job = reserve(owner)
    assert job.start_unit()
    assert job.complete_unit(success=False)
    assert job.finish(reason="provider_failed")
    assert credits.balance(owner) == before
    empty = reserve(owner)
    assert empty.finish()
    assert credits.balance(owner) == before


def test_admission_is_capped_by_daily_guard_and_balance(owner):
    leave(owner, 2)
    job = reserve(owner, requested_units=500)
    assert job.allowed_units == 20
    assert reserve(owner) is None
    assert not credits.can_spend(owner, 1)
    job.finish()
    credits.spend(owner, 14, "spend_chat")
    CreditLedger.all_objects.create(user=owner, delta=30, kind="adjust")
    job = reserve(owner)
    assert job.allowed_units == 10
    assert reserve(owner) is None


def test_duplicate_attempt_is_not_replayed_before_or_after_completion(owner):
    job = reserve(owner, job_key="rescan:one")
    assert reserve(owner, job_key="rescan:one") is None
    job.finish()
    assert reserve(owner, job_key="rescan:one") is None


def test_recovery_retains_uncertain_call_and_releases_unstarted_units(owner):
    before = credits.balance(owner)
    job = reserve(owner)
    assert job.start_unit()
    expire(job)
    assert not job.start_unit()
    assert reconcile_job_reservations(user=owner) == {"checked": 1, "recoverable": 1, "recovered": 0}
    assert credits.balance(owner) == before - 3
    assert reconcile_job_reservations(user=owner, apply=True)["recovered"] == 1
    assert credits.balance(owner) == before - 1
    assert not job.complete_unit(success=True)
    assert not job.finish()
    assert reconcile_job_reservations(user=owner, apply=True)["recovered"] == 0


def test_live_reservation_is_not_recovered_and_expired_never_started_is_refunded(owner):
    before = credits.balance(owner)
    job = reserve(owner)
    assert reconcile_job_reservations(apply=True)["checked"] == 0
    expire(job)
    assert not job.start_unit()
    assert reconcile_job_reservations(apply=True)["recovered"] == 1
    assert credits.balance(owner) == before


def test_account_closure_fences_stale_instance_and_deletion_never_recreates(owner):
    job = reserve(owner)
    get_user_model().objects.filter(pk=owner.pk).update(is_active=False)
    assert not job.start_unit()
    assert reserve(owner) is None
    assert job.finish()
    pk = owner.pk
    get_user_model().objects.filter(pk=pk).delete()
    assert not job.start_unit()
    assert not job.complete_unit(success=False)
    assert not job.finish()
    assert reserve(owner) is None


def test_another_tenant_cannot_finish_start_or_recover_job(owner):
    job = reserve(owner)
    other = get_user_model().objects.create_user(email="other-job@example.test", password="x")
    row = AIJobReservation.objects.for_user(owner).get(pk=job.reservation_id)
    forged = JobBudget(other, row, 600)
    assert not forged.start_unit()
    assert not forged.finish()
    expire(job)
    assert reconcile_job_reservations(user=other, apply=True)["checked"] == 0
    assert AIJobReservation.objects.for_user(owner).get(pk=row.pk).status == "pending"


def test_cross_month_refund_does_not_expand_new_day_allowance(owner):
    past = timezone.datetime(2026, 8, 31, 23, 50, tzinfo=timezone.get_default_timezone())
    future = timezone.datetime(2026, 9, 1, 0, 5, tzinfo=timezone.get_default_timezone())
    with patch("django.utils.timezone.now", return_value=past):
        job = reserve(owner)
    with patch("django.utils.timezone.now", return_value=future):
        credits.spend(owner, 5, "spend_chat")
        assert job.finish()
        assert credits.daily_spent(owner) == 5
        assert credits.month_usage(owner) == 5
    with patch("django.utils.timezone.now", return_value=past):
        assert credits.daily_spent(owner) == 0


def test_linked_refunds_cannot_overrefund_or_target_a_grant(owner):
    credits.balance(owner)
    credits.spend(owner, 2, "spend_chat")
    source = CreditLedger.objects.for_user(owner).filter(kind="spend_chat").get()
    credits.refund(owner, 1, refund_of=source)
    with pytest.raises(ValueError):
        credits.refund(owner, 2, refund_of=source)
    grant = CreditLedger.objects.for_user(owner).filter(kind="grant").get()
    with pytest.raises(ValueError):
        credits.refund(owner, 1, refund_of=grant)
    assert CreditLedger.objects.for_user(owner).filter(refund_of=source).count() == 1


@pytest.mark.parametrize("kwargs", [{"requested_units": -1}, {"requested_units": True},
    {"requested_units": 10001}, {"lease_seconds": 1}, {"lease_seconds": 3601},
    {"job_key": ""}, {"job_key": "x"*161}])
def test_bad_admission_inputs_never_write(owner, kwargs):
    with pytest.raises(ValueError):
        reserve(owner, **kwargs)
    assert not AIJobReservation.objects.for_user(owner).exists()
    assert not CreditLedger.objects.for_user(owner).exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_jobs_cannot_both_call_provider_using_last_credit(owner):
    leave(owner, 1)
    barrier = threading.Barrier(2)
    results, failures = [], []
    def worker(kind):
        try:
            barrier.wait(timeout=10)
            job = reserve_job(owner, kind=kind, requested_units=10, units_per_credit=10)
            results.append(job)
        except BaseException as exc:
            failures.append(exc)
        finally:
            connections.close_all()
    threads = [threading.Thread(target=worker, args=(kind,)) for kind in ("spend_rescan", "spend_autopilot")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()
    assert not failures
    assert sum(job is not None for job in results) == 1
    assert credits.balance(owner) == 0


@pytest.mark.django_db(transaction=True)
def test_provider_boundary_has_no_open_database_transaction(owner):
    job = reserve(owner)
    assert not connections["default"].in_atomic_block
    assert job.start_unit()
    assert not connections["default"].in_atomic_block
    assert job.complete_unit(success=True)
    assert not connections["default"].in_atomic_block
    assert job.finish()


def test_refunded_jobs_still_count_toward_account_attempt_limit(owner, monkeypatch):
    monkeypatch.setattr("billing.job_budget.MAX_RESERVATIONS_PER_HOUR", 2)
    before = credits.balance(owner)
    for kind in ("spend_brief", "spend_autopilot"):
        job = reserve_job(owner, kind=kind, requested_units=1, units_per_credit=1)
        assert job.start_unit()
        assert job.complete_unit(success=False)
        assert job.finish()
    assert credits.balance(owner) == before
    assert reserve(owner) is None
    other = get_user_model().objects.create_user(email="fresh-budget@example.test", password="x")
    assert reserve(other) is not None
    future = timezone.now() + timedelta(hours=1, seconds=1)
    with patch("django.utils.timezone.now", return_value=future):
        assert reserve(owner) is not None


def test_failed_units_and_long_batches_cannot_bypass_provider_attempt_limit(owner, monkeypatch):
    monkeypatch.setattr("billing.job_budget.MAX_PROVIDER_UNITS_PER_HOUR", 2)
    job = reserve(owner)
    AIJobReservation.objects.for_user(owner).filter(pk=job.reservation_id).update(
        created=timezone.now() - timedelta(hours=2))
    for _ in range(2):
        assert job.start_unit()
        assert job.complete_unit(success=False)
    assert not job.start_unit()
    assert job.finish()
    replacement = reserve_job(owner, kind="spend_brief", requested_units=1, units_per_credit=1)
    assert replacement is not None
    assert not replacement.start_unit()
    assert replacement.finish()
    future = timezone.now() + timedelta(hours=2)
    with patch("django.utils.timezone.now", return_value=future):
        fresh = reserve(owner)
        assert fresh.start_unit()


@pytest.mark.django_db(transaction=True)
def test_concurrent_job_kinds_share_final_provider_attempt(owner, monkeypatch):
    monkeypatch.setattr("billing.job_budget.MAX_PROVIDER_UNITS_PER_HOUR", 1)
    jobs = [reserve_job(owner, kind=kind, requested_units=1, units_per_credit=1)
            for kind in ("spend_rescan", "spend_autopilot")]
    barrier = threading.Barrier(2)
    results, failures = [], []
    def worker(job):
        try:
            barrier.wait(timeout=10)
            results.append(job.start_unit())
        except BaseException as exc:
            failures.append(exc)
        finally:
            connections.close_all()
    threads = [threading.Thread(target=worker, args=(job,)) for job in jobs]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
        assert not thread.is_alive()
    assert not failures
    assert results.count(True) == 1
