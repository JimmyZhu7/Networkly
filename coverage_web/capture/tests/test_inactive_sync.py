"""Deactivation is authoritative even when a worker holds a stale user object.

All providers are replaced with offline fakes. Run serially with the main
Django suite; this module never requires Google, model, email or push keys.
"""
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.utils import timezone

from accounts.models import PushSubscription
from assistant import brief
from billing import credits
from capture import autopilot, gcal_live, gmail_live, gmail_residue
from capture.models import AutopilotRun, GmailConnection, GoogleCalendarConnection
from crm import ai_brief
from crm.models import CalendarEvent, Contact

pytestmark = pytest.mark.django_db(transaction=True)
User = get_user_model()


@pytest.fixture
def owners():
    active = User.objects.create_user(email="active-sync@example.test", password=None, onboarded_at=timezone.now())
    stale = User.objects.create_user(email="inactive-sync@example.test", password=None, onboarded_at=timezone.now())
    User.objects.filter(pk=stale.pk).update(is_active=False)
    assert stale.is_active  # Deliberately cached: this must not authorize work.
    return active, stale


def _gmail(user):
    return GmailConnection.all_objects.create(
        user=user, gmail_address=user.email, refresh_token_encrypted="unused",
        history_id="old-history", backfill_status="pending", rescan_status="pending",
    )


def _calendar(user):
    return GoogleCalendarConnection.all_objects.create(
        user=user, google_email=user.email, refresh_token_encrypted="unused", sync_token="old-cursor",
    )


def _command(name, *args, **kwargs):
    return call_command(name, *args, stdout=StringIO(), stderr=StringIO(), **kwargs)


@pytest.mark.parametrize("dry_run", [True, False])
def test_calendar_direct_sync_rejects_stale_inactive_owner_before_google(owners, dry_run):
    connection = _calendar(owners[1])
    with patch.object(gcal_live, "_calendar_client") as provider:
        with pytest.raises(gcal_live.GcalError, match="no longer active"):
            gcal_live.sync_connection(connection, dry_run=dry_run)
    provider.assert_not_called()
    connection.refresh_from_db()
    assert connection.sync_token == "old-cursor"
    assert not CalendarEvent.all_objects.filter(user=owners[1]).exists()


@pytest.mark.parametrize("apply", [True, False])
def test_calendar_command_selects_active_owner_only(owners, apply):
    active = _calendar(owners[0])
    inactive = _calendar(owners[1])
    with patch.object(gcal_live, "is_configured", return_value=True), patch.object(
        gcal_live, "sync_connection", return_value=gcal_live.GcalSyncResult(),
    ) as sync:
        _command("gcal_sync", apply=apply)
        assert [call.args[0].pk for call in sync.call_args_list] == [active.pk]
        assert sync.call_args.kwargs == {"dry_run": not apply}
        sync.reset_mock()
        _command("gcal_sync", user=inactive.user.email, apply=apply)
        sync.assert_not_called()


def test_calendar_deactivation_during_provider_read_preserves_cursor_and_events(owners):
    connection = _calendar(owners[0])
    client = MagicMock()

    def page():
        User.objects.filter(pk=owners[0].pk).update(is_active=False)
        return {"items": [{
            "id": "new-meeting", "status": "confirmed", "summary": "Should not be stored",
            "start": {"dateTime": "2026-09-10T10:00:00Z"},
        }], "nextSyncToken": "new-cursor"}

    client.events.return_value.list.return_value.execute.side_effect = page
    with patch.object(gcal_live, "_calendar_client", return_value=client):
        with pytest.raises(gcal_live.GcalError, match="changed during sync"):
            gcal_live.sync_connection(connection)
    connection.refresh_from_db()
    assert connection.sync_token == "old-cursor"
    assert not CalendarEvent.all_objects.filter(user=owners[0]).exists()


@pytest.mark.parametrize("entry", ["sync_connection", "preview_sync", "backfill_connection", "run_rescan", "register_watch"])
def test_gmail_public_entries_refuse_stale_inactive_owner_before_provider_or_credits(owners, entry):
    connection = _gmail(owners[1])
    with patch.object(gmail_live, "_gmail_client") as provider, patch.object(
        credits, "affordable_residue_threads",
    ) as allowance:
        with pytest.raises(gmail_live.GmailLiveError, match="no longer active"):
            getattr(gmail_live, entry)(connection)
    provider.assert_not_called()
    allowance.assert_not_called()
    connection.refresh_from_db()
    assert connection.history_id == "old-history"
    assert connection.backfill_status == connection.rescan_status == "pending"


def test_gmail_active_owner_still_reaches_read_only_provider(owners):
    connection = _gmail(owners[0])
    with patch.object(gmail_live, "_gmail_client") as provider, patch.object(
        gmail_live, "_list_new_messages", return_value=([], "new-history"),
    ):
        assert gmail_live.preview_sync(connection)["latest_history_id"] == "new-history"
    provider.assert_called_once_with(connection)


def test_gmail_backfill_and_rescan_queues_skip_inactive_without_consuming_jobs(owners):
    from capture.management.commands.gmail_backfill import Command
    active, inactive = [_gmail(user) for user in owners]
    with patch.object(gmail_live, "is_configured", return_value=True), patch.object(
        Command, "_run_backfill",
    ) as backfill, patch.object(Command, "_run_rescan") as rescan:
        _command("gmail_backfill", dry_run=True)
    assert [call.args[0].pk for call in backfill.call_args_list] == [active.pk]
    assert [call.args[0].pk for call in rescan.call_args_list] == [active.pk]
    inactive.refresh_from_db()
    assert inactive.backfill_status == inactive.rescan_status == "pending"


@pytest.mark.parametrize("kind", ["backfill", "rescan"])
def test_mail_queue_deactivation_after_selection_does_not_mark_running(owners, kind):
    from capture.management.commands.gmail_backfill import Command
    connection = _gmail(owners[1])
    with patch.object(gmail_live, "backfill_connection") as backfill, patch.object(
        gmail_live, "run_rescan",
    ) as rescan:
        getattr(Command(), f"_run_{kind}_locked")(connection, dry_run=False, prefix="")
    backfill.assert_not_called()
    rescan.assert_not_called()
    connection.refresh_from_db()
    assert getattr(connection, f"{kind}_status") == "pending"


def test_import_backfill_skips_inactive_owner(owners):
    _gmail(owners[1])
    contact = Contact.all_objects.create(user=owners[1], name="Private contact", email="contact@example.test")
    with patch.object(gmail_live, "is_configured", return_value=True), patch.object(
        gmail_live, "backfill_connection",
    ) as scan:
        assert gmail_live.backfill_new_contacts(owners[1], [contact]) is None
    scan.assert_not_called()


def test_autopilot_direct_and_claim_paths_refuse_inactive_without_credit_or_queue_writes(owners):
    user = owners[1]
    decide = MagicMock()
    with patch.object(autopilot, "preview") as preview, patch.object(credits, "can_spend") as allowance:
        assert autopilot.start_run(user) == ("inactive_user", None)
        report = autopilot.run_autopilot(user, decide=decide)
    assert not report.ok and report.reason == "inactive_user"
    preview.assert_not_called()
    allowance.assert_not_called()
    decide.assert_not_called()
    assert not AutopilotRun.all_objects.filter(user=user).exists()
    run = AutopilotRun.all_objects.create(user=user, status=AutopilotRun.STATUS_QUEUED)
    assert autopilot.claim_run(run) is False
    run.refresh_from_db()
    assert run.status == AutopilotRun.STATUS_QUEUED


def test_autopilot_worker_selects_active_queue_only(owners):
    active, inactive = [AutopilotRun.all_objects.create(user=user, status=AutopilotRun.STATUS_QUEUED) for user in owners]
    with patch.object(autopilot, "execute_run", return_value=autopilot.AutopilotReport()) as execute:
        _command("capture_autopilot_worker")
    assert [call.args[0].pk for call in execute.call_args_list] == [active.pk]
    inactive.refresh_from_db()
    assert inactive.status == AutopilotRun.STATUS_QUEUED


def test_claimed_autopilot_deactivated_before_execution_is_failed_without_model_call(owners):
    run = AutopilotRun.all_objects.create(user=owners[1], status=AutopilotRun.STATUS_RUNNING)
    decide = MagicMock()
    report = autopilot.execute_run(run, decide=decide)
    assert report.reason == "inactive_user"
    decide.assert_not_called()
    run.refresh_from_db()
    assert run.status == AutopilotRun.STATUS_FAILED
    assert run.credits_spent == 0


def test_residue_and_both_briefs_skip_private_prompt_building_for_inactive_owner(owners):
    connection = _gmail(owners[1])
    contact = Contact.all_objects.create(user=owners[1], name="Private contact")
    with patch.object(gmail_residue, "is_configured", return_value=True), patch.object(
        gmail_residue, "_classify_one",
    ) as classify, patch.object(ai_brief, "is_configured", return_value=True), patch.object(
        ai_brief, "build_prompt",
    ) as prompt, patch.object(ai_brief, "complete_text") as complete:
        stats = gmail_residue.run_residue_stage(connection, [{"thread_id": "private", "message": {}}])
        assert stats["residue_threads_processed"] == 0
        assert ai_brief.generate_coffee_chat_brief(contact) is None
        client = MagicMock()
        assert brief.get_or_build(owners[1], [], client=client) is None
    classify.assert_not_called()
    prompt.assert_not_called()
    complete.assert_not_called()
    assert not client.mock_calls


def test_residue_stops_before_next_paid_call_after_deactivation(owners):
    connection = _gmail(owners[0])

    def classify(*args, **kwargs):
        User.objects.filter(pk=owners[0].pk).update(is_active=False)
        return "ambiguous", ""

    with patch.object(gmail_residue, "is_configured", return_value=True), patch.object(
        gmail_residue, "_classify_one", side_effect=classify,
    ) as provider, patch.object(gmail_residue, "apply_findings") as apply:
        stats = gmail_residue.run_residue_stage(connection, [
            {"thread_id": f"thread-{i}", "message": {}} for i in range(2)
        ])
    assert provider.call_count == stats["residue_threads_processed"] == 1
    apply.assert_not_called()


@pytest.fixture
def subscriptions(owners, settings):
    settings.VAPID_PUBLIC_KEY = "offline-public"
    settings.VAPID_PRIVATE_KEY = "offline-private"
    return [PushSubscription.all_objects.create(
        user=user, endpoint=f"https://fcm.googleapis.com/{user.pk}", p256dh="unused", auth="unused",
    ) for user in owners]


def test_push_direct_sender_checks_fresh_owner_state(owners, subscriptions):
    from accounts import push
    with patch.object(push, "webpush") as provider:
        push.send_notification(subscriptions[1], title="Private", body="Details", url="/calendar/")
        provider.assert_not_called()
        push.send_notification(subscriptions[0], title="Private", body="Details", url="/calendar/")
        provider.assert_called_once()


def test_push_command_does_not_even_assemble_inactive_deadlines(owners, subscriptions):
    from accounts.management.commands import send_deadline_push_alerts as command
    with patch.object(command, "_due_rows", return_value=[]) as assemble:
        _command("send_deadline_push_alerts")
    assert [call.args[0].pk for call in assemble.call_args_list] == [owners[0].pk]
    with pytest.raises(CommandError):
        _command("send_deadline_push_alerts", user=owners[1].email)


def test_digest_command_does_not_assemble_or_email_inactive_accounts(owners, mailoutbox):
    from crm.management.commands import send_weekly_digest as command
    with patch.object(command, "assemble_digest", return_value=None) as assemble:
        _command("send_weekly_digest")
    assert [call.args[0].pk for call in assemble.call_args_list] == [owners[0].pk]
    assert mailoutbox == []
    with pytest.raises(CommandError):
        _command("send_weekly_digest", user=owners[1].email)


def test_gmail_deactivated_during_fetch_does_not_apply_findings_or_advance_cursor(owners):
    connection = _gmail(owners[0])

    def fetch(*args):
        User.objects.filter(pk=owners[0].pk).update(is_active=False)
        return {"id": "private-message"}

    with patch.object(gmail_live, "_gmail_client"), patch.object(
        gmail_live, "_list_new_messages", return_value=(["private-message"], "new-history"),
    ), patch.object(gmail_live, "_fetch_message", side_effect=fetch), patch.object(
        gmail_live, "classify_message_findings", return_value=[{"private": "finding"}],
    ) as classify, patch.object(gmail_live, "apply_findings") as apply:
        with pytest.raises(gmail_live.GmailLiveError, match="no longer active"):
            gmail_live.sync_connection(connection)
    classify.assert_not_called()
    apply.assert_not_called()
    connection.refresh_from_db()
    assert connection.history_id == "old-history"
