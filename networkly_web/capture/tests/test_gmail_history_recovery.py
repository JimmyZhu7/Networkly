"""Expired Gmail history queues free recovery without losing queue state."""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from googleapiclient.errors import HttpError

from capture import gmail_live, gmail_residue
from capture.gmail import SyncResult
from capture.models import GmailConnection
from .test_gmail_connect import _http_error


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def connection():
    user = get_user_model().objects.create_user(email="recovery@example.com", password="x", plan="pro")
    return GmailConnection.objects.for_user(user).create(
        user=user, gmail_address=user.email, refresh_token_encrypted="unused",
        history_id="40", status="active", backfill_status="done",
    )


def _expired_sync(connection, *, client=None):
    client = client or MagicMock()
    client.users.return_value.getProfile.return_value.execute.return_value = {"historyId": "100"}
    with patch.object(gmail_live, "_gmail_client", return_value=client), \
         patch.object(gmail_live, "_list_new_messages", side_effect=_http_error(404, "Expired history")):
        gmail_live.sync_connection(connection)


@pytest.mark.parametrize("initial,expected", [
    ("none", "pending"), ("done", "pending"), ("pending", "pending"),
    ("failed", "failed"), ("running", "running"),
])
def test_expired_history_queues_or_preserves_existing_recovery(connection, initial, expected):
    prior_time = timezone.now()
    connection.backfill_status = initial
    connection.backfill_started_at = prior_time
    connection.backfill_completed_at = prior_time
    connection.rescan_status = "done"
    connection.rescan_completed_at = prior_time
    connection.save()
    _expired_sync(connection)
    connection.refresh_from_db()
    assert connection.history_id == "100"
    assert connection.backfill_status == expected
    if initial in ("none", "done"):
        assert connection.backfill_started_at is None
        assert connection.backfill_completed_at is None
    else:
        assert connection.backfill_started_at == prior_time
        assert connection.backfill_completed_at == prior_time
    assert connection.rescan_status == "done"
    assert connection.rescan_completed_at == prior_time


def test_repeated_expiry_does_not_reset_a_queued_recoverys_priority(connection):
    _expired_sync(connection)
    requested = timezone.now()
    connection.backfill_started_at = requested
    connection.save(update_fields=["backfill_started_at"])
    _expired_sync(connection)
    assert connection.backfill_status == "pending"
    assert connection.backfill_started_at == requested


def test_stale_sync_does_not_replace_newer_progress(connection):
    GmailConnection.objects.for_user(connection.user).filter(pk=connection.pk).update(history_id="80")
    _expired_sync(connection)
    assert connection.history_id == "80"
    assert connection.backfill_status == "done"


def test_failure_to_fetch_anchor_changes_neither_cursor_nor_queue(connection):
    client = MagicMock()
    client.users.return_value.getProfile.return_value.execute.side_effect = _http_error(503, "Unavailable")
    with pytest.raises(HttpError):
        _expired_sync(connection, client=client)
    connection.refresh_from_db()
    assert connection.history_id == "40"
    assert connection.backfill_status == "done"


def test_recovery_is_consumed_by_free_backfill_not_paid_rescan(connection):
    _expired_sync(connection)
    with patch.object(gmail_live, "is_configured", return_value=True), \
         patch.object(gmail_live, "backfill_connection", return_value=SyncResult()) as backfill, \
         patch.object(gmail_live, "run_rescan") as rescan, \
         patch.object(gmail_residue, "run_residue_stage") as classify:
        call_command("gmail_backfill", email=connection.user.email)
    backfill.assert_called_once()
    assert backfill.call_args.args[0].pk == connection.pk
    assert backfill.call_args.kwargs == {"dry_run": False, "sweep_sent": True}
    rescan.assert_not_called()
    classify.assert_not_called()
