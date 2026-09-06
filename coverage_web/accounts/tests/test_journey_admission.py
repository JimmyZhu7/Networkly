"""Journey 1: getting in, and being kept out.

`test_beta_admission.py` already proves the ADAPTER's rules by calling
`CoverageSocialAccountAdapter.save_user` directly. That is the unit. This file
is the JOURNEY: a browser-shaped request walks allauth's real Google callback
view, so the whole chain — `_get_state`, `complete_social_login`,
`pre_social_login`, `is_open_for_signup`, `save_user`, the session cookie the
person is left holding — is exercised as one thing rather than at its seams.

WHAT IS MOCKED: exactly two Google network calls, and nothing else. The token
exchange (`get_access_token_data`) and the identity fetch (`complete_login`)
return canned data; no request leaves the machine and no OAuth secret is read.
Everything downstream of those two — allauth's state check, the adapters, the
invitation registry, the session, the redirect — is the real code path.
"""

from __future__ import annotations

import pytest
from allauth.socialaccount.models import SocialAccount, SocialToken
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from django.urls import reverse

from accounts import beta
from accounts.models import BetaInvitation, User

pytestmark = pytest.mark.django_db

CALLBACK = "/accounts/google/login/callback/"


@pytest.fixture(autouse=True)
def beta_settings(settings):
    settings.BETA_ENABLED = True
    settings.BETA_MAX_USERS = 3
    settings.ACCOUNT_ADAPTER = "accounts.adapter.CoverageAccountAdapter"
    settings.SOCIALACCOUNT_ADAPTER = "accounts.adapter.CoverageSocialAccountAdapter"
    # A provider only has an `app` when a client id is configured; the callback
    # view resolves one before it does anything else. Synthetic value.
    providers = {k: dict(v) for k, v in settings.SOCIALACCOUNT_PROVIDERS.items()}
    providers["google"] = dict(providers["google"])
    providers["google"]["APP"] = {
        "client_id": "journey-client-id", "secret": "journey-secret", "key": "",
    }
    settings.SOCIALACCOUNT_PROVIDERS = providers


@pytest.fixture
def google(monkeypatch):
    """Drive allauth's real callback view with a canned Google identity.

    Returns a callable: `google(client, email=...)` performs the callback GET
    and hands back the response. The `state` allauth stamps into the session on
    the login POST is reused verbatim, so the CSRF-equivalent check in
    `_get_state` is genuinely satisfied rather than bypassed.
    """
    def run(client, email="invited@example.com", *, uid="google-1", verified=True):
        holder = {"email": email, "uid": uid, "verified": verified}

        def fake_token_data(self, request, app, oauth2_client, pkce_code_verifier=None):
            return {"access_token": "synthetic", "id_token": "synthetic", "expires_in": 3600}

        def fake_complete_login(self, request, app, token, **kwargs):
            # Built by the REAL GoogleProvider from a canned id_token payload,
            # not hand-assembled: `extract_uid`, `extract_common_fields` and
            # `extract_email_addresses` are the provider's own, and the
            # SocialLogin comes back bound to the provider the way allauth's
            # own lookup path requires.
            return self.get_provider().sociallogin_from_response(request, {
                "sub": holder["uid"],
                "email": holder["email"],
                "email_verified": holder["verified"],
            })

        monkeypatch.setattr(GoogleOAuth2Adapter, "get_access_token_data", fake_token_data)
        monkeypatch.setattr(GoogleOAuth2Adapter, "complete_login", fake_complete_login)
        monkeypatch.setattr(
            GoogleOAuth2Adapter, "parse_token",
            lambda self, data: SocialToken(token=data["access_token"]),
        )

        # allauth 65 refuses a GET on the provider login view unless
        # SOCIALACCOUNT_LOGIN_ON_GET; POST is what the real sign-in button does.
        start = client.post("/accounts/google/login/")
        assert start.status_code == 302, start.status_code
        state = _state_from_session(client)
        return client.get(CALLBACK, {"code": "synthetic-code", "state": state})

    return run


def _state_from_session(client):
    """The one state key allauth just stored for this pending login."""
    states = client.session.get("socialaccount_states") or {}
    assert states, "allauth stored no OAuth state for the pending login"
    return next(iter(states))


def _signed_in(client) -> bool:
    return "_auth_user_id" in client.session


# ---------------------------------------------------------------------------
# Accepted


def test_invited_google_callback_signs_in_and_lands_in_onboarding(client, google, mailoutbox):
    beta.invite_emails(["invited@example.com"])

    response = google(client)

    assert response.status_code == 302
    user = User.objects.get()
    assert user.email == "invited@example.com"
    assert _signed_in(client) and int(client.session["_auth_user_id"]) == user.pk
    assert BetaInvitation.objects.get().redeemed_at is not None
    assert SocialAccount.objects.get().user == user
    assert mailoutbox == []
    # The wizard is reachable and starts at step one for a brand-new account.
    wizard = client.get(reverse("accounts:onboarding"))
    assert wizard.status_code == 200
    assert wizard.context["step"] == "profile"


def test_completing_onboarding_after_an_invited_callback_opens_the_app(client, google):
    beta.invite_emails(["invited@example.com"])
    google(client)

    wizard = reverse("accounts:onboarding")
    assert client.post(wizard, {"step": "profile", "regions": ["us"], "tracks": ["ib"]}).status_code == 302
    assert client.post(wizard, {"step": "work_auth"}).status_code == 302
    assert client.post(wizard, {"step": "firms"}).status_code == 302
    assert client.post(wizard, {"step": "import"}).url == "/app/"

    user = User.objects.get()
    user.refresh_from_db()
    assert user.onboarded_at is not None
    assert user.regions == ["us"] and user.tracks == ["ib"]
    # Bare /welcome/ stops replaying the wizard once it is finished.
    assert client.get(wizard).url == reverse("accounts:settings")


# ---------------------------------------------------------------------------
# Refused


def test_uninvited_google_callback_is_refused_at_the_closed_signup_page(client, google, mailoutbox):
    response = google(client, email="stranger@example.com")

    assert response.status_code == 302
    assert response.url == reverse("account_login")
    assert not User.objects.exists()
    assert not _signed_in(client)
    assert mailoutbox == []
    # The refusal has to SAY so on the page the person is sent to, or the
    # journey ends on a sign-in form that looks like it simply failed.
    page = client.get(response.url)
    assert page.status_code == 200
    assert beta.INVITATION_REQUIRED in page.content.decode()


def test_unverified_google_email_is_refused_even_with_an_invitation(client, google):
    beta.invite_emails(["invited@example.com"])

    response = google(client, verified=False)

    assert response.status_code == 302 and response.url == reverse("account_login")
    assert not User.objects.exists()
    assert BetaInvitation.objects.get().redeemed_at is None


def test_local_password_signup_is_closed_and_says_so(client):
    """The other door. Beta has no email/password signup at all."""
    page = client.get(reverse("account_signup"))
    assert page.status_code == 200
    body = page.content.decode()
    assert "sign" in body.lower()

    response = client.post(reverse("account_signup"), {
        "email": "stranger@example.com",
        "password1": "A-safe-passphrase-123",
        "password2": "A-safe-passphrase-123",
    })
    assert response.status_code in (200, 302)
    assert not User.objects.exists()
    assert not _signed_in(client)


def test_an_existing_password_account_can_still_sign_in_during_beta(client):
    """Closed signup must not lock out the accounts that already exist."""
    user = User.objects.create_user(email="member@example.com", password="A-safe-passphrase-123")

    response = client.post(reverse("account_login"), {
        "login": "member@example.com", "password": "A-safe-passphrase-123",
    })

    assert response.status_code == 302
    assert int(client.session["_auth_user_id"]) == user.pk
    assert client.get("/app/").status_code == 200


# ---------------------------------------------------------------------------
# The cap


def test_the_hundred_and_first_seat_is_refused_through_the_real_callback(client, google, settings):
    """Two seats, two invitees, and a third who is turned away at the door."""
    settings.BETA_MAX_USERS = 2
    beta.invite_emails(["one@example.com", "two@example.com"])

    for index, email in enumerate(["one@example.com", "two@example.com"], start=1):
        assert google(client, email=email, uid=f"google-{index}").status_code == 302
        client.logout()

    assert User.objects.count() == 2
    assert beta.capacity_status() == {
        "used": 2, "limit": 2, "remaining": 0, "over_capacity": False,
    }

    # No seat left to reserve...
    with pytest.raises(beta.BetaAdmissionError, match="full"):
        beta.invite_emails(["three@example.com"])
    # ...and the uninvited third account is refused at the callback itself.
    response = google(client, email="three@example.com", uid="google-3")
    assert response.url == reverse("account_login")
    assert User.objects.count() == 2
    assert not _signed_in(client)
    assert beta.BETA_FULL in client.get(response.url).content.decode()


def test_a_deleted_account_leaves_its_seat_consumed_and_cannot_walk_back_in(client, google, settings):
    settings.BETA_MAX_USERS = 1
    beta.invite_emails(["invited@example.com"])
    assert google(client).status_code == 302
    client.logout()

    User.objects.get().delete()

    assert not User.objects.exists()
    seat = BetaInvitation.objects.get()
    assert seat.email == "" and seat.user_id is None and seat.redeemed_at is not None
    assert beta.capacity_status()["remaining"] == 0

    response = google(client, uid="google-2")
    assert response.url == reverse("account_login")
    assert not User.objects.exists()
    assert not _signed_in(client)


def test_capacity_counts_reserved_redeemed_and_deleted_seats_together(settings):
    """The three kinds of consumed seat, in one arithmetic statement."""
    settings.BETA_MAX_USERS = 3
    reserved, redeemed, deleted = (
        "reserved@example.com", "redeemed@example.com", "deleted@example.com",
    )
    beta.invite_emails([reserved, redeemed, deleted])

    redeemed_user = User.objects.create_user(email=redeemed)
    deleted_user = User.objects.create_user(email=deleted)
    for user in (redeemed_user, deleted_user):
        seat = BetaInvitation.objects.get(email_fingerprint=beta.email_fingerprint(user.email))
        seat.user, seat.redeemed_at = user, user.date_joined
        seat.save(update_fields=["user", "redeemed_at"])
    deleted_user.delete()

    assert beta.capacity_status() == {
        "used": 3, "limit": 3, "remaining": 0, "over_capacity": False,
    }
    with pytest.raises(beta.BetaAdmissionError, match="full"):
        beta.invite_emails(["fourth@example.com"])
