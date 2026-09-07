"""Renewal must not acknowledge mail that the application has not read."""

from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from google.auth.exceptions import RefreshError
from googleapiclient.errors import HttpError

from capture import gmail_live
from capture.models import GmailConnection
from .test_gmail_connect import _http_error


pytestmark = pytest.mark.django_db


@pytest.fixture
def connection(settings):
    settings.GMAIL_LIVE_CLIENT_ID = "fake-client"
    settings.GMAIL_LIVE_CLIENT_SECRET = "fake-secret"
    settings.GMAIL_LIVE_TOKEN_KEY = gmail_live.Fernet.generate_key().decode()
    settings.GMAIL_LIVE_PUBSUB_TOPIC = "projects/test/topics/gmail"
    user = get_user_model().objects.create_user(email="watch@example.com", password="x")
    return GmailConnection.objects.for_user(user).create(
        user=user, gmail_address=user.email, refresh_token_encrypted="unused", history_id="40",
    )


def _client():
    client = MagicMock()
    client.users.return_value.watch.return_value.execute.return_value = {
        "historyId": "100", "expiration": "1999999999999",
    }
    return client


@pytest.mark.parametrize("history_id,expected", [("40", "40"), ("", "100")])
def test_watch_only_seeds_an_empty_checkpoint(connection, history_id, expected):
    connection.history_id = history_id
    connection.save(update_fields=["history_id"])
    with patch.object(gmail_live, "_gmail_client", return_value=_client()):
        gmail_live.register_watch(connection)
    connection.refresh_from_db()
    assert connection.history_id == expected
    assert connection.watch_expiration is not None


def test_renewal_stale_instance_cannot_overwrite_concurrent_sync(connection):
    connection.history_id = ""
    connection.save(update_fields=["history_id"])
    GmailConnection.objects.for_user(connection.user).filter(pk=connection.pk).update(history_id="80")
    with patch.object(gmail_live, "_gmail_client", return_value=_client()):
        gmail_live.register_watch(connection)
    assert connection.history_id == "80"


def test_expired_grant_is_marked_revoked(connection):
    with patch.object(gmail_live, "_gmail_client", side_effect=RefreshError("invalid_grant")):
        gmail_live.register_watch(connection)
    connection.refresh_from_db()
    assert connection.status == "revoked"
    assert connection.history_id == "40"


def test_pubsub_permission_error_does_not_falsely_revoke_mailbox(connection):
    client = _client()
    client.users.return_value.watch.return_value.execute.side_effect = _http_error(403, "Topic permission denied")
    with patch.object(gmail_live, "_gmail_client", return_value=client), pytest.raises(HttpError):
        gmail_live.register_watch(connection)
    connection.refresh_from_db()
    assert connection.status == "active"
    assert connection.history_id == "40"


def test_temporary_token_service_failure_remains_retryable(connection):
    with patch.object(gmail_live, "_gmail_client", side_effect=RefreshError("temporarily unavailable", retryable=True)), pytest.raises(RefreshError):
        gmail_live.register_watch(connection)
    connection.refresh_from_db()
    assert connection.status == "active"
    assert connection.history_id == "40"
