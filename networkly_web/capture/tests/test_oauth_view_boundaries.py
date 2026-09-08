"""Exercise consent routing and one-use state without contacting Google."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from analytics.models import ProductEvent
from capture import gcal_live, gmail_live, views


pytestmark = pytest.mark.django_db


@pytest.fixture
def signed_in(client, settings, monkeypatch):
    settings.BETA_ENABLED = False
    user = User.objects.create_user(
        email="consent-boundary@example.test", password=None,
        onboarded_at=timezone.now(), timezone="UTC",
    )
    client.force_login(user)
    monkeypatch.setattr(gmail_live, "is_configured", lambda: True)
    monkeypatch.setattr(gcal_live, "is_configured", lambda: True)
    return user


def test_gmail_connect_rotates_state_and_preserves_calendar_flow(client, signed_in, monkeypatch):
    build = Mock(return_value="https://accounts.google.com/o/oauth2/auth?scope=gmail")
    monkeypatch.setattr(gmail_live, "build_auth_url", build)
    session = client.session
    session[views._GCAL_STATE_SESSION_KEY] = "calendar-flow-in-progress"
    session.save()

    first = client.get(reverse("capture:gmail_connect"))
    first_state = client.session[views._STATE_SESSION_KEY]
    assert first.status_code == 302
    assert first.url == build.return_value
    assert len(first_state) >= 24
    build.assert_called_once_with(
        "http://testserver" + reverse("capture:gmail_callback"), first_state,
    )
    assert client.session[views._GCAL_STATE_SESSION_KEY] == "calendar-flow-in-progress"
    assert not ProductEvent.objects.for_user(signed_in).filter(event="gmail_connected").exists()

    client.get(reverse("capture:gmail_connect"))
    assert client.session[views._STATE_SESSION_KEY] != first_state


@pytest.mark.parametrize("route,provider", [
    ("gmail_connect", gmail_live), ("gcal_callback", gcal_live),
])
def test_disabled_consent_routes_fail_closed(client, signed_in, monkeypatch, route, provider):
    monkeypatch.setattr(provider, "is_configured", lambda: False)
    assert client.get(reverse("capture:" + route)).status_code == 404


@pytest.mark.parametrize("kind", ["missing", "mismatch", "denied", "exchange_error", "success"])
def test_calendar_callback_state_is_one_use_and_success_is_owned(
    client, signed_in, monkeypatch, kind,
):
    connect = Mock(return_value=SimpleNamespace(google_email="calendar-owner@example.test"))
    monkeypatch.setattr(gcal_live, "connect_calendar", connect)
    session = client.session
    session[views._STATE_SESSION_KEY] = "independent-gmail-state"
    if kind != "missing":
        session[views._GCAL_STATE_SESSION_KEY] = "calendar-state"
    session.save()
    params = {"state": "wrong" if kind == "mismatch" else "calendar-state", "code": "test-code"}
    if kind == "denied":
        params["error"] = "access_denied"
    if kind == "exchange_error":
        connect.side_effect = gcal_live.GcalError("Calendar could not connect. Try again.")

    response = client.get(reverse("capture:gcal_callback"), params)
    assert response.status_code == 302
    assert response.url == reverse("accounts:settings") + "#google-calendar"
    assert views._GCAL_STATE_SESSION_KEY not in client.session
    assert client.session[views._STATE_SESSION_KEY] == "independent-gmail-state"
    messages = " ".join(str(message) for message in get_messages(response.wsgi_request))
    if kind in ("success", "exchange_error"):
        connect.assert_called_once_with(
            signed_in, "test-code", "http://testserver" + reverse("capture:gcal_callback"),
        )
    else:
        connect.assert_not_called()
    assert ProductEvent.objects.for_user(signed_in).filter(event="gcal_connected").count() == (kind == "success")
    if kind == "success":
        assert "Calendar connected" in messages
        event = ProductEvent.objects.for_user(signed_in).get(event="gcal_connected")
        assert "calendar-owner" not in str(event.props)
    elif kind in ("missing", "mismatch"):
        assert "expired" in messages
    elif kind == "denied":
        assert "cancelled" in messages
    else:
        assert "Try again" in messages

    calls = connect.call_count
    client.get(reverse("capture:gcal_callback"), {"state": "calendar-state", "code": "test-code"})
    assert connect.call_count == calls
    assert ProductEvent.objects.for_user(signed_in).filter(event="gcal_connected").count() == (kind == "success")


def test_calendar_state_from_another_session_cannot_connect(client, signed_in, monkeypatch):
    connect = Mock()
    monkeypatch.setattr(gcal_live, "connect_calendar", connect)
    from django.test import Client
    other = User.objects.create_user(email="other-consent@example.test", password=None,
                                     onboarded_at=timezone.now())
    other_client = Client()
    other_client.force_login(other)
    session = other_client.session
    session[views._GCAL_STATE_SESSION_KEY] = "other-session-state"
    session.save()
    response = client.get(reverse("capture:gcal_callback"), {"state": "other-session-state", "code": "test-code"})
    assert response.status_code == 302
    connect.assert_not_called()
    assert other_client.session[views._GCAL_STATE_SESSION_KEY] == "other-session-state"
    assert not ProductEvent.all_objects.filter(event="gcal_connected").exists()
