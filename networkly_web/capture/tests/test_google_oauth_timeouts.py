"""OAuth calls have a finite socket wait and release their HTTP sessions."""

from unittest.mock import Mock, patch

import pytest
from requests.exceptions import Timeout

from capture import gcal_live, gmail_live, google_oauth


@pytest.mark.parametrize("module,method,error", [
    (gmail_live, "connect_gmail", gmail_live.GmailLiveError),
    (gcal_live, "connect_calendar", gcal_live.GcalError),
])
def test_consent_exchange_is_bounded_and_surfaces_timeout(module, method, error):
    flow = Mock()
    flow.fetch_token.side_effect = Timeout("token endpoint timed out")
    with patch.object(module, "_flow", return_value=flow), pytest.raises(error):
        getattr(module, method)(None, "consent-code", "https://example.com/callback")
    flow.fetch_token.assert_called_once_with(code="consent-code", timeout=15)


@pytest.mark.parametrize("fails", [False, True])
def test_refresh_transport_is_bounded_and_closed(fails):
    transport = Mock()
    if fails:
        transport.side_effect = Timeout("token endpoint timed out")
    creds = Mock()
    creds.refresh.side_effect = lambda request: request(
        "https://oauth2.googleapis.com/token", method="POST", timeout=120,
    )
    with patch.object(google_oauth, "Credentials", return_value=creds), \
         patch.object(google_oauth, "GoogleAuthRequest", return_value=transport):
        kwargs = dict(client_id="fake", client_secret="fake", refresh_token="fake", scopes=[])
        if fails:
            with pytest.raises(Timeout):
                google_oauth.credentials(**kwargs)
        else:
            assert google_oauth.credentials(**kwargs) is creds
    transport.assert_called_once_with("https://oauth2.googleapis.com/token", method="POST", timeout=15)
    transport.session.close.assert_called_once_with()
