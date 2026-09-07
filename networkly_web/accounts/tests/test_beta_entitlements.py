"""Invited individual beta access uses real users without changing billing plans.

All Google, Stripe, and model-facing work is mocked. The root task alone runs
these database tests, serially with the other launch checks.
"""
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from accounts import access, trials
from assistant import plans
from billing import credits, stripe_gateway
from billing.models import CreditLedger
from capture import gmail_live
from capture.management.commands.gmail_poll import Command as PollCommand
from capture.models import GmailConnection
from capture.tests.test_gmail_plan_gate import _fake_flow, _fake_gmail_client

pytestmark = pytest.mark.django_db(transaction=True)
User = get_user_model()


@pytest.fixture(autouse=True)
def beta(settings):
    settings.BETA_ENABLED = True
    settings.BETA_MAX_USERS = 100
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.CREDIT_PLANS = {
        "free": {"monthly_grant": 60, "message_cost": 1, "daily_burst": 15},
        "pro": {"monthly_grant": 180, "message_cost": 3, "daily_burst": 45},
    }
    settings.ASSISTANT_PLANS = {
        "free": {"model": "test-free-model", "daily_cap": 15},
        "pro": {"model": "test-individual-model", "daily_cap": 60},
    }


@pytest.fixture
def student():
    return User.objects.create_user(email="beta-entitlements@example.test", password="x", plan="free")


def _connection(user, **overrides):
    fields = dict(
        user=user, gmail_address=user.email, refresh_token_encrypted="unused-test-token",
        status="active", history_id="1000", backfill_status="done",
    )
    fields.update(overrides)
    return GmailConnection.all_objects.create(**fields)


def test_free_beta_user_gets_individual_plan_and_bounded_ai_without_stored_upgrade(student):
    assert access.has_individual_features(student)
    assert access.effective_plan(student) == "pro"
    assert access.plan_label(student) == "Free Beta"
    limits = plans.limits_for(student)
    assert limits.label == "Free Beta"
    assert limits.model == "test-individual-model"
    assert limits.message_cost == 3
    assert credits.plan_config(student) == {
        "plan": "pro", "monthly_grant": 180, "message_cost": 3, "daily_burst": 45,
    }
    assert credits.balance(student) == 180
    assert credits.balance(student) == 180
    assert CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_GRANT).count() == 1
    student.refresh_from_db()
    assert student.plan == "free"
    assert student.pro_trial_started_at is None
    assert student.pro_trial_ends_at is None


def test_beta_ai_stops_at_daily_burst_with_monthly_credits_remaining(student):
    assert credits.balance(student) == 180
    for _ in range(15):
        assert credits.can_spend(student, 3)
        credits.spend(student, 3, CreditLedger.KIND_SPEND_CHAT)
    assert credits.daily_spent(student) == 45
    assert credits.balance(student) == 135
    assert not credits.can_spend(student, 3)
    student.refresh_from_db()
    assert student.plan == "free"


def test_beta_monthly_balance_is_not_unlimited_or_refilled_on_repeated_requests(student):
    assert credits.balance(student) == 180
    credits.spend(student, 180, CreditLedger.KIND_SPEND_CHAT)
    assert credits.balance(student) == 0
    assert not credits.can_spend(student, 3)
    assert credits.balance(student) == 0
    assert CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_GRANT).count() == 1


def test_enabling_beta_reconciles_a_known_free_grant_once_without_changing_the_plan(student, settings):
    settings.BETA_ENABLED = False
    assert credits.balance(student) == 60
    settings.BETA_ENABLED = True
    assert credits.balance(student) == 180
    assert credits.balance(student) == 180
    assert CreditLedger.objects.for_user(student).filter(kind=CreditLedger.KIND_UPGRADE).count() == 1
    student.refresh_from_db()
    assert student.plan == "free"


def test_disabling_beta_restores_real_free_access_without_mutating_billing_state(student, settings):
    assert plans.plan_of(student) == "pro"
    settings.BETA_ENABLED = False
    assert not access.has_individual_features(student)
    assert plans.plan_of(student) == "free"
    assert plans.limits_for(student).model == "test-free-model"
    assert credits.plan_config(student)["monthly_grant"] == 60
    student.refresh_from_db()
    assert student.plan == "free"


def test_poller_includes_active_free_and_pro_but_excludes_inactive_and_revoked(student):
    free = _connection(student)
    pro = _connection(User.objects.create_user(email="beta-pro@example.test", password="x", plan="pro"))
    _connection(User.objects.create_user(email="beta-inactive@example.test", password="x", plan="free", is_active=False))
    _connection(User.objects.create_user(email="beta-revoked@example.test", password="x", plan="free"), status="revoked")
    command = PollCommand()
    assert {row.pk for row in command._select(None)} == {free.pk, pro.pk}
    assert [row.pk for row in command._select(student.email)] == [free.pk]


def test_poller_reverts_to_paid_selection_when_beta_is_disabled(student, settings):
    _connection(student)
    pro = _connection(User.objects.create_user(email="paid-after-beta@example.test", password="x", plan="pro"))
    settings.BETA_ENABLED = False
    assert [row.pk for row in PollCommand()._select(None)] == [pro.pk]


def test_beta_free_gmail_connect_registers_watch_but_never_starts_a_trial(student, settings):
    settings.GMAIL_LIVE_TOKEN_KEY = gmail_live.Fernet.generate_key().decode()
    settings.PRO_TRIAL_TRIGGER = "gmail_connect"
    fake_google = _fake_gmail_client(student.email)
    with patch.object(gmail_live, "_flow", return_value=_fake_flow()), \
            patch.object(gmail_live, "build", return_value=fake_google), \
            patch.object(gmail_live, "register_watch") as register:
        connection = gmail_live.connect_gmail(student, "offline-code", "https://app.example.test/callback")
    register.assert_called_once()
    assert connection.backfill_status == "pending"
    student.refresh_from_db()
    assert student.plan == "free"
    assert student.pro_trial_started_at is None and student.pro_trial_ends_at is None


def test_watch_renewal_uses_the_same_active_beta_entitlement(student):
    eligible = _connection(student)
    _connection(User.objects.create_user(email="inactive-renewal@example.test", password="x", is_active=False))
    with patch.object(gmail_live, "is_push_configured", return_value=True), \
            patch.object(gmail_live, "register_watch") as register:
        gmail_live.renew_watches()
    assert [call.args[0].pk for call in register.call_args_list] == [eligible.pk]


@pytest.mark.parametrize("active", [True, False])
def test_push_notifications_respect_beta_access_and_account_activity(student, active):
    student.is_active = active
    student.save(update_fields=["is_active"])
    connection = _connection(student)
    with patch.object(gmail_live, "sync_connection") as sync:
        gmail_live.process_notification(connection.gmail_address, "1001")
    assert sync.call_count == int(active)


def test_beta_free_account_has_no_weekly_rescan_throttle(student):
    connection = _connection(student, rescan_status="done", rescan_completed_at=timezone.now())
    assert gmail_live.free_rescan_unlocks_at(connection) is None


def test_beta_trial_start_and_banners_are_no_ops(student):
    assert trials.start_trial_if_eligible(student, trigger="gmail_connect") is False
    student.pro_trial_started_at = timezone.now() - timedelta(days=20)
    student.pro_trial_ends_at = timezone.now() - timedelta(days=1)
    student.save(update_fields=["pro_trial_started_at", "pro_trial_ends_at"])
    assert trials.trial_days_left(student) is None
    assert trials.trial_ended_notice(student) is None
    student.refresh_from_db()
    assert student.plan == "free"


def test_beta_expiry_job_neither_downgrades_nor_emails_or_resets_scan_state(student):
    student.plan = "pro"
    student.pro_trial_started_at = timezone.now() - timedelta(days=20)
    student.pro_trial_ends_at = timezone.now() - timedelta(days=1)
    student.save(update_fields=["plan", "pro_trial_started_at", "pro_trial_ends_at"])
    connection = _connection(student, rescan_status="done", rescan_completed_at=timezone.now())
    original_scan = connection.rescan_completed_at
    with patch.object(trials, "send_trial_ended_email") as send, \
            patch.object(trials, "reset_free_rescan_throttle") as reset:
        out = StringIO()
        call_command("pro_trial_expire", stdout=out)
    send.assert_not_called()
    reset.assert_not_called()
    student.refresh_from_db()
    connection.refresh_from_db()
    assert student.plan == "pro"
    assert connection.rescan_completed_at == original_scan
    assert "paused" in out.getvalue().lower()


def test_trial_ended_email_is_suppressed_even_if_called_directly(student):
    student.pro_trial_ends_at = timezone.now() - timedelta(days=1)
    assert trials.send_trial_ended_email(student) is False
    assert not mail.outbox


@pytest.mark.parametrize("pack", ["small", "unknown-pack"])
def test_beta_checkout_cannot_call_stripe_even_with_keys_and_a_direct_post(client, student, settings, pack):
    settings.STRIPE_SECRET_KEY = "sk_test_configured_for_regression"
    client.force_login(student)
    with patch.object(stripe_gateway, "is_configured", return_value=True), \
            patch.object(stripe_gateway, "create_checkout_session") as checkout:
        response = client.post(reverse("billing:checkout", args=[pack]))
    checkout.assert_not_called()
    assert response.status_code == 302
    assert response.url == reverse("accounts:settings") + "#credits"
    student.refresh_from_db()
    assert student.plan == "free"


def test_beta_still_processes_verified_receipts_for_purchases_made_before_beta(client):
    with patch.object(stripe_gateway, "is_configured", return_value=True), \
            patch.object(stripe_gateway, "handle_webhook_event") as receipt:
        response = client.post(reverse("billing:webhook"), data=b'{"type":"checkout.session.completed"}',
                               content_type="application/json", HTTP_STRIPE_SIGNATURE="signed-test-receipt")
    assert response.status_code == 200
    receipt.assert_called_once_with(b'{"type":"checkout.session.completed"}', "signed-test-receipt")


def test_beta_pricing_states_the_real_allowance_and_has_no_paid_or_team_ctas(client):
    response = client.get(reverse("core:pricing"))
    assert response.status_code == 200
    assert "core/pricing_beta.html" in {template.name for template in response.templates}
    assert response.context["advisor_pro_grant"] == 180
    assert response.context["beta_message_cost"] == 3
    assert response.context["beta_daily_burst"] == 45
    body = response.content.decode()
    assert "180 AI credits each month" in body
    assert "Individual Beta" in body
    assert "$0" in body
    assert "100 invited users" in body
    assert "/billing/checkout/" not in body
    assert "/billing/waitlist/join/" not in body
    assert "Enterprise" not in body
    assert "Notify me when Pro opens" not in body


def test_beta_settings_and_assistant_meter_match_access_without_paid_upsells(client, student):
    client.force_login(student)
    with patch.object(gmail_live, "is_configured", return_value=True), \
            patch.object(stripe_gateway, "is_configured", return_value=True):
        response = client.get(reverse("accounts:settings"))
    assert response.status_code == 200
    context = response.context
    assert context["credits"]["plan_label"] == "Free Beta"
    assert context["credits"]["monthly_grant"] == 180
    assert context["credits"]["trial_days_left"] is None
    assert context["credits"]["trial_ended"] is None
    assert context["gmail_live"]["is_pro"] is True
    body = response.content.decode()
    assert "All individual features are free during the beta" in body
    assert "/billing/checkout/" not in body
    assert "Buy more credits" not in body
    assert "Pro trial ·" not in body
    meter = client.get(reverse("assistant:credits"))
    assert meter.status_code == 200
    assert meter.json()["plan_label"] == "Free Beta"
    assert meter.json()["balance"] == context["credits"]["balance"]
    student.refresh_from_db()
    assert student.plan == "free"
