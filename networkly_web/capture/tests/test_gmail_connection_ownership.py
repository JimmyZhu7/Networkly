"""An old Google response cannot modify a replacement connection."""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from google.auth.exceptions import RefreshError

from capture import gmail_live
from capture.models import GmailConnection
from crm.models import Contact


pytestmark = pytest.mark.django_db


@pytest.fixture
def connection(settings):
    settings.GMAIL_LIVE_CLIENT_ID = "fake-client"
    settings.GMAIL_LIVE_CLIENT_SECRET = "fake-secret"
    settings.GMAIL_LIVE_TOKEN_KEY = gmail_live.Fernet.generate_key().decode()
    settings.GMAIL_LIVE_PUBSUB_TOPIC = "projects/test/topics/gmail"
    user = get_user_model().objects.create_user(email="ownership@example.com", password="x")
    return GmailConnection.all_objects.create(
        user=user, gmail_address=user.email, refresh_token_encrypted="old-token", history_id="40",
    )


def _replace(connection, **fields):
    GmailConnection.all_objects.filter(pk=connection.pk).update(**fields)


@pytest.mark.parametrize("failure", [False, True])
def test_watch_response_cannot_change_reconnected_grant(connection, failure):
    def provider(old):
        _replace(connection, refresh_token_encrypted="replacement", history_id="90",
                 status="active" if failure else "revoked")
        if failure:
            raise RefreshError("invalid_grant")
        client = MagicMock()
        client.users.return_value.watch.return_value.execute.return_value = {
            "historyId": "100", "expiration": "1999999999999",
        }
        return client

    with patch.object(gmail_live, "_gmail_client", side_effect=provider):
        gmail_live.register_watch(connection)
    connection.refresh_from_db()
    assert connection.status == ("active" if failure else "revoked")
    assert connection.history_id == "90"
    assert connection.watch_expiration is None
    assert connection.refresh_token_encrypted == "replacement"


@pytest.mark.parametrize("change", ["reconnect", "disconnect", "concurrent_sync"])
def test_live_sync_discards_results_when_connection_changed(connection, change):
    client = MagicMock()
    client.users.return_value.history.return_value.list.return_value.execute.return_value = {
        "historyId": "50", "history": [{"messagesAdded": [{"message": {"id": "m1"}}]}],
    }

    def classify(*args, **kwargs):
        if change == "disconnect":
            GmailConnection.all_objects.filter(pk=connection.pk).delete()
        elif change == "reconnect":
            _replace(connection, refresh_token_encrypted="replacement", history_id="40")
        else:
            _replace(connection, history_id="90")
        return [{"email": "person@example.com", "type": "outreach"}]

    with patch.object(gmail_live, "_gmail_client", return_value=client), \
         patch.object(gmail_live, "_fetch_message", return_value={"id": "m1"}), \
         patch.object(gmail_live, "classify_message_findings", side_effect=classify), \
         patch.object(gmail_live, "apply_findings") as applied:
        gmail_live.sync_connection(connection)
    applied.assert_not_called()
    if change == "disconnect":
        assert not GmailConnection.all_objects.filter(pk=connection.pk).exists()
    else:
        connection.refresh_from_db()
        assert connection.history_id == ("90" if change == "concurrent_sync" else "40")
        assert connection.last_notification_at is None


def test_live_sync_does_not_checkpoint_if_apply_fails(connection):
    client = MagicMock()
    client.users.return_value.history.return_value.list.return_value.execute.return_value = {
        "historyId": "50", "history": [{"messagesAdded": [{"message": {"id": "m1"}}]}],
    }

    def partial_apply(user, findings):
        Contact.objects.for_user(user).create(user=user, name="Partial result")
        raise RuntimeError("apply failed")

    with patch.object(gmail_live, "_gmail_client", return_value=client), \
         patch.object(gmail_live, "_fetch_message", return_value={"id": "m1"}), \
         patch.object(gmail_live, "classify_message_findings", return_value=[{"type": "outreach"}]), \
         patch.object(gmail_live, "apply_findings", side_effect=partial_apply), \
         pytest.raises(RuntimeError, match="apply failed"):
        gmail_live.sync_connection(connection)
    connection.refresh_from_db()
    assert connection.history_id == "40"


def test_connecting_different_mailbox_resets_its_scan_state(connection):
    now = timezone.now()
    _replace(connection, backfill_status="done", backfill_completed_at=now,
             backfill_stats={"old": True}, rescan_status="running", rescan_started_at=now,
             rescan_requested_at=now, rescan_completed_at=now, rescan_stats={"old": True},
             watch_expiration=now, last_notification_at=now)
    flow = MagicMock()
    flow.credentials.refresh_token = "new-token"
    client = MagicMock()
    client.users.return_value.getProfile.return_value.execute.return_value = {
        "emailAddress": "different@example.com", "historyId": "100",
    }
    with patch.object(gmail_live, "_flow", return_value=flow), \
         patch.object(gmail_live, "build", return_value=client), \
         patch.object(gmail_live, "register_watch"):
        changed = gmail_live.connect_gmail(connection.user, "code", "https://example.com/callback")
    assert changed.gmail_address == "different@example.com"
    assert changed.backfill_status == "pending"
    assert changed.backfill_completed_at is None
    assert changed.backfill_stats == {}
    assert changed.rescan_status == "none"
    assert changed.rescan_started_at is None
    assert changed.rescan_requested_at is None
    assert changed.rescan_completed_at is None
    assert changed.rescan_stats == {}
    assert changed.watch_expiration is None
    assert changed.last_notification_at is None


@pytest.mark.parametrize("pages", [
    [{"historyId": "50", "nextPageToken": "again"}] * 2,
    [{"historyId": "50", "history": None}],
    [{"history": [], "historyId": None}],
])
def test_incomplete_history_does_not_acknowledge_messages(connection, pages):
    client = MagicMock()
    client.users.return_value.history.return_value.list.return_value.execute.side_effect = pages
    with patch.object(gmail_live, "_gmail_client", return_value=client), \
         pytest.raises(gmail_live.GmailLiveError):
        gmail_live.sync_connection(connection)
    connection.refresh_from_db()
    assert connection.history_id == "40"
    assert connection.last_notification_at is None
