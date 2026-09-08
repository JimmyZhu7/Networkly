"""Real Google credentials/discovery construction with fake token HTTP only."""

import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.parse import parse_qs

from cryptography.fernet import Fernet
from google.auth.exceptions import RefreshError, TransportError
import pytest

from capture import gcal_live, gmail_live, google_oauth


@pytest.fixture
def refresh_transport(monkeypatch, settings):
    settings.GMAIL_LIVE_CLIENT_ID = "fixture-client"
    settings.GMAIL_LIVE_CLIENT_SECRET = "fixture-client-secret"
    settings.GMAIL_LIVE_TOKEN_KEY = Fernet.generate_key().decode()
    session = Mock()
    request = Mock(session=session, return_value=SimpleNamespace(status=200, data=json.dumps({
        "access_token": "fixture-access-token", "expires_in": 3600, "token_type": "Bearer",
    }).encode()))
    monkeypatch.setattr(google_oauth, "GoogleAuthRequest", Mock(return_value=request))
    return request


@pytest.mark.parametrize("module,scope,api", [
    (gmail_live, "https://www.googleapis.com/auth/gmail.readonly", "gmail"),
    (gcal_live, "https://www.googleapis.com/auth/calendar.readonly", "calendar"),
])
def test_clients_refresh_their_own_readonly_grant_and_build_offline(refresh_transport, module, scope, api, monkeypatch):
    # Bundled discovery documents must suffice; no surprise discovery HTTP.
    monkeypatch.setattr("httplib2.Http.request", Mock(side_effect=AssertionError("Unexpected live discovery HTTP")))
    connection = SimpleNamespace(refresh_token_encrypted=gmail_live.encrypt_token("fixture-refresh-token"))
    factory = module._gmail_client if api == "gmail" else module._calendar_client
    service = factory(connection)
    try:
        credentials = service._http.credentials
        assert credentials.token == "fixture-access-token"
        assert credentials.valid and list(credentials.scopes) == [scope]
        assert credentials.refresh_token == "fixture-refresh-token"
        assert refresh_transport.call_count == 1
        kwargs = refresh_transport.call_args.kwargs
        assert kwargs["url"] == google_oauth.TOKEN_URI
        assert kwargs["timeout"] == google_oauth.REQUEST_TIMEOUT_SECONDS
        form = parse_qs(kwargs["body"].decode())
        assert form["scope"] == [scope]
        assert form["refresh_token"] == ["fixture-refresh-token"]
        # Build, but do not execute, an actual API method using that grant.
        resource = (service.users().getProfile(userId="me") if api == "gmail"
                    else service.events().list(calendarId="primary"))
        assert resource.method == "GET"
    finally:
        service.close()
    refresh_transport.session.close.assert_called_once_with()


@pytest.mark.parametrize("module", [gmail_live, gcal_live])
@pytest.mark.parametrize("failure", ["revoked", "missing_access_token", "transport"])
def test_unusable_token_response_closes_session_and_never_builds_api(refresh_transport, module, failure, monkeypatch):
    if failure == "transport":
        refresh_transport.side_effect = TransportError("local network unavailable")
        expected = TransportError
    else:
        refresh_transport.return_value = SimpleNamespace(status=400 if failure == "revoked" else 200,
            data=json.dumps({"error": "invalid_grant"} if failure == "revoked" else {"expires_in": 3600}).encode())
        expected = RefreshError
    build = Mock(side_effect=AssertionError("Must not build an API without a valid grant"))
    monkeypatch.setattr(module, "build", build)
    factory = module._gmail_client if module is gmail_live else module._calendar_client
    with pytest.raises(expected):
        factory(SimpleNamespace(refresh_token_encrypted=gmail_live.encrypt_token("fixture-refresh-token")))
    assert not build.called
    refresh_transport.session.close.assert_called_once_with()


@pytest.mark.parametrize("module", [gmail_live, gcal_live])
def test_corrupt_encrypted_grant_fails_before_any_token_http(refresh_transport, module):
    with pytest.raises(gmail_live.GmailLiveError):
        module._credentials(SimpleNamespace(refresh_token_encrypted="not-a-fernet-token"))
    refresh_transport.assert_not_called()
