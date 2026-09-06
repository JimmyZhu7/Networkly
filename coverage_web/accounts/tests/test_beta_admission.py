"""Beta admission exercises actual allauth persistence on Django's test DB.

No live OAuth or mail: provider evidence is an offline Google response.
The concurrent test uses only Django's explicitly selected test connection.
"""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from types import SimpleNamespace

import pytest
from allauth.account.models import EmailAddress
from allauth.core import context
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.models import SocialAccount, SocialLogin
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection, connections
from django.test import RequestFactory
from django.urls import reverse

from accounts import beta
from accounts.adapter import CoverageAccountAdapter, CoverageSocialAccountAdapter
from accounts.models import BetaInvitation, User

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def beta_settings(settings):
    settings.BETA_ENABLED = True
    settings.BETA_MAX_USERS = 3
    settings.ACCOUNT_ADAPTER = "accounts.adapter.CoverageAccountAdapter"
    settings.SOCIALACCOUNT_ADAPTER = "accounts.adapter.CoverageSocialAccountAdapter"


def auth_request():
    request = RequestFactory().get("/accounts/google/login/callback/")
    request.user = AnonymousUser()
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


def google_login(email="invited@example.com", verified=True, provider="google", uid="google-1"):
    return SocialLogin(
        user=User(email=email),
        account=SocialAccount(provider=provider, uid=uid, extra_data={
            "sub": uid, "email": email, "email_verified": verified,
        }),
        email_addresses=[EmailAddress(email=email, verified=verified, primary=True)],
    )


def save_google(login, form=None):
    request = auth_request()
    with context.request_context(request):
        return CoverageSocialAccountAdapter(request).save_user(request, login, form=form)


def test_invitation_batch_normalizes_and_is_idempotent_without_mail(mailoutbox):
    out = StringIO()
    call_command("beta_invite", " Invited@Example.COM ", "invited@example.com", stdout=out)
    call_command("beta_invite", "INVITED@example.com", stdout=out)
    assert BetaInvitation.objects.get().email == "invited@example.com"
    assert User.objects.count() == 0
    assert mailoutbox == []
    assert "already reserved" in out.getvalue()


def test_existing_local_users_count_once_case_insensitively(settings):
    settings.BETA_MAX_USERS = 2
    User.objects.create_user(email="Old@example.com", plan="pro")
    User.objects.create_user(email="old@example.com")
    beta.invite_emails(["new@example.com"])
    assert beta.capacity_status() == {"used": 2, "limit": 2, "remaining": 0, "over_capacity": False}
    assert BetaInvitation.objects.filter(redeemed_at__isnull=False).count() == 1
    with pytest.raises(beta.BetaAdmissionError, match="full"):
        beta.invite_emails(["extra@example.com"])
    assert User.objects.get(email="Old@example.com").plan == "pro"


def test_invitation_batch_rolls_back_when_it_exceeds_capacity(settings):
    settings.BETA_MAX_USERS = 1
    with pytest.raises(beta.BetaAdmissionError):
        beta.invite_emails(["one@example.com", "two@example.com"])
    assert not BetaInvitation.objects.exists()


def test_hard_limit_never_exceeds_one_hundred(settings):
    settings.BETA_MAX_USERS = 1000
    assert beta.beta_limit() == 100


def test_success_saves_verified_google_and_claim_atomically_without_plan_change(mailoutbox):
    beta.invite_emails(["invited@example.com"])
    user = save_google(google_login("Invited@Example.com"))
    seat = BetaInvitation.objects.get()
    assert user.email == "invited@example.com"
    assert user.plan == "free"
    assert not user.has_usable_password()
    assert seat.user == user and seat.redeemed_at is not None
    assert SocialAccount.objects.get().user == user
    assert EmailAddress.objects.get().verified
    assert mailoutbox == []


def test_reserved_invitation_can_be_redeemed_at_exact_capacity(settings):
    settings.BETA_MAX_USERS = 1
    beta.invite_emails(["invited@example.com"])
    assert save_google(google_login()).pk


def test_invited_free_account_completes_first_application_journey(client):
    """Join admission to the actual wizard and board under beta settings.

    OAuth evidence is synthetic and session creation is explicit; this does
    not claim a browser/provider callback test. Unlike isolated board tests,
    the account here has allauth identity rows, an invitation and no password.
    """
    from accounts.access import has_individual_features
    from analytics.models import UserOpportunity
    from crm.models import UserFirm
    from directory.models import Firm, Opportunity

    beta.invite_emails(["invited@example.com", "second@example.com"])
    user = save_google(google_login())
    firm = Firm.objects.create(name="Journey Firm", slug="journey-firm", regions=["us"], tracks=["ib"])
    role = Opportunity.objects.create(
        firm=firm, title="Journey Summer Analyst", url="https://example.test/journey",
        region="us", bucket="internship", status="open",
    )
    assert user.plan == "free" and has_individual_features(user)
    client.force_login(user)
    wizard = reverse("accounts:onboarding")
    for step, data, next_step in [
        ("profile", {"regions": ["us"], "tracks": ["ib"]}, "work_auth"),
        ("work_auth", {}, "firms"),
        ("firms", {"firms": [str(firm.pk)]}, "import"),
    ]:
        response = client.post(wizard, {"step": step, **data})
        assert response.status_code == 302
        assert f"step={next_step}" in response.url
    assert client.post(wizard, {"step": "import"}).url == "/app/"
    user.refresh_from_db()
    assert user.onboarded_at is not None and user.plan == "free"
    assert UserFirm.objects.for_user(user).filter(firm=firm).exists()

    track = reverse("track_opportunity", args=[role.pk])
    for status in ["saved", "submitted", "submitted"]:
        response = client.post(track, {"status": status, "next": reverse("my_applications")})
        assert response.status_code == 302
    application = UserOpportunity.objects.for_user(user).get(opportunity=role)
    assert application.applied_status == "submitted" and application.applied_at
    response = client.get(reverse("my_applications"))
    assert response.status_code == 200 and response.context["total"] == 1
    assert role.title.encode() in response.content

    second = save_google(google_login("second@example.com", uid="google-2"))
    client.force_login(second)
    response = client.get(reverse("my_applications"))
    assert response.status_code == 200 and response.context["total"] == 0
    assert role.title.encode() not in response.content
    # A second invitee clearing that shared directory role must not remove
    # the first person's application, even before finishing onboarding.
    assert client.post(track, {"status": "clear"}).status_code == 302
    assert UserOpportunity.objects.for_user(user).get(pk=application.pk).applied_at == application.applied_at
    assert not UserOpportunity.objects.for_user(second).exists()
    assert not UserFirm.objects.for_user(second).exists()


@pytest.mark.parametrize("provider,verified", [("google", False), ("microsoft", True), ("google", "false")])
def test_only_verified_google_evidence_can_create_an_account(provider, verified):
    beta.invite_emails(["invited@example.com"])
    with pytest.raises(ImmediateHttpResponse):
        save_google(google_login(provider=provider, verified=verified))
    assert not User.objects.exists()
    assert BetaInvitation.objects.get().redeemed_at is None


def test_invitation_is_required_even_for_verified_google():
    with pytest.raises(ImmediateHttpResponse):
        save_google(google_login())
    assert not User.objects.exists()


def test_social_signup_form_cannot_substitute_another_invited_email():
    beta.invite_emails(["invited@example.com", "other@example.com"])
    with pytest.raises(ImmediateHttpResponse):
        save_google(google_login(), form=SimpleNamespace(cleaned_data={"email": "other@example.com"}))
    assert not User.objects.exists()
    assert not BetaInvitation.objects.filter(redeemed_at__isnull=False).exists()


def test_failure_saving_social_account_rolls_back_user_and_redemption(monkeypatch):
    beta.invite_emails(["invited@example.com"])
    def broken_save(*args, **kwargs):
        raise RuntimeError("simulated social persistence failure")
    monkeypatch.setattr(SocialAccount, "save", broken_save)
    with pytest.raises(RuntimeError):
        save_google(google_login())
    assert not User.objects.exists()
    assert not EmailAddress.objects.exists()
    assert BetaInvitation.objects.get().redeemed_at is None


def test_local_signup_is_closed_but_internal_creation_and_existing_login_work(client):
    before = User.objects.count()
    response = client.post(reverse("account_signup"), {
        "email": "uninvited@example.com", "password1": "A-safe-passphrase-123", "password2": "A-safe-passphrase-123",
    })
    assert response.status_code in (200, 302)
    assert User.objects.count() == before
    user = User.objects.create_user(email="local@example.com", password="A-safe-passphrase-123", plan="pro")
    result = client.post(reverse("account_login"), {"login": user.email, "password": "A-safe-passphrase-123"})
    assert result.status_code == 302
    assert str(client.session["_auth_user_id"]) == str(user.pk)
    assert user.plan == "pro"


def test_account_adapter_rejects_direct_local_save():
    request = auth_request()
    with pytest.raises(ImmediateHttpResponse):
        CoverageAccountAdapter(request).save_user(request, User(email="bad@example.com"), SimpleNamespace(cleaned_data={}))
    assert not User.objects.exists()


def test_existing_social_login_is_allowed_without_invitation():
    user = User.objects.create_user(email="existing@example.com")
    login = google_login(user.email, verified=False)
    login.user = user
    request = auth_request()
    CoverageSocialAccountAdapter(request).pre_social_login(request, login)
    assert not BetaInvitation.objects.exists()


def test_duplicate_email_is_blocked_before_allauth_fallback_or_mail(mailoutbox):
    User.objects.create_user(email="Invited@example.com")
    request = auth_request()
    request.session["socialaccount_sociallogin"] = {"stale": True}
    with pytest.raises(ImmediateHttpResponse) as exc:
        CoverageSocialAccountAdapter(request).pre_social_login(request, google_login())
    assert exc.value.response.url == reverse("account_login")
    assert "socialaccount_sociallogin" not in request.session
    assert mailoutbox == []
    assert User.objects.count() == 1


def test_existing_secondary_email_also_blocks_fallback():
    user = User.objects.create_user(email="other@example.com")
    EmailAddress.objects.create(user=user, email="invited@example.com", verified=True)
    beta.invite_emails(["invited@example.com"])
    with pytest.raises(ImmediateHttpResponse):
        save_google(google_login())
    assert User.objects.count() == 1


def test_deleted_accounts_keep_consumed_seats_and_cannot_rejoin(settings):
    settings.BETA_MAX_USERS = 1
    beta.invite_emails(["invited@example.com"])
    user = save_google(google_login())
    user.delete()
    seat = BetaInvitation.objects.get()
    assert seat.email == "" and seat.user_id is None and seat.redeemed_at
    assert beta.capacity_status()["remaining"] == 0
    beta.invite_emails(["invited@example.com"])
    assert seat.email == ""
    with pytest.raises(ImmediateHttpResponse):
        save_google(google_login(uid="google-2"))
    with pytest.raises(ValidationError):
        seat.delete()
    with pytest.raises(ValidationError):
        BetaInvitation.objects.all().delete()


def test_queryset_deletion_counts_and_anonymizes_an_unsnapshotted_local_account():
    user = User.objects.create_user(email="legacy@example.com")
    assert not BetaInvitation.objects.exists()
    User.objects.filter(pk=user.pk).delete()
    seat = BetaInvitation.objects.get()
    assert seat.email == "" and seat.user_id is None and seat.redeemed_at
    assert seat.email_fingerprint == beta.email_fingerprint("legacy@example.com")


def test_internal_overcapacity_is_reported_and_blocks_admission(settings):
    settings.BETA_MAX_USERS = 1
    beta.invite_emails(["invited@example.com"])
    User.objects.create_user(email="admin-created@example.com")
    assert beta.capacity_status()["over_capacity"]
    with pytest.raises(ImmediateHttpResponse):
        save_google(google_login())


def test_beta_off_restores_local_signup(settings):
    settings.BETA_ENABLED = False
    assert CoverageAccountAdapter(auth_request()).is_open_for_signup(auth_request())


def test_anonymous_cannot_view_invitation_registry(client):
    response = client.get(reverse("admin:accounts_betainvitation_changelist"))
    assert response.status_code == 302
    assert "/admin/login/" in response.url


def test_admin_add_is_idempotent_and_capacity_error_is_a_form_error(client, settings, mailoutbox):
    settings.BETA_MAX_USERS = 2
    admin = User.objects.create_superuser(email="admin@example.com", password="pw")
    client.force_login(admin)
    url = reverse("admin:accounts_betainvitation_add")
    assert client.post(url, {"email": "Invited@Example.com", "_save": "Save"}).status_code == 302
    assert client.post(url, {"email": "invited@example.com", "_save": "Save"}).status_code == 302
    response = client.post(url, {"email": "overflow@example.com", "_save": "Save"})
    assert response.status_code == 200
    assert "free beta is full" in response.content.decode()
    assert BetaInvitation.objects.count() == 2
    assert mailoutbox == []


@pytest.mark.django_db(transaction=True)
def test_simultaneous_last_seat_reservations_are_serialized(settings):
    # The claim under test is "exactly one of two simultaneous reservations
    # for the LAST seat wins", not "the table is empty". Existing users count
    # as seats, and a transactional test runs after every rollback-mode test
    # in the suite, so any row a side connection committed earlier would
    # make both claims see a full beta and fail this test for the wrong
    # reason (it did, twice, in loaded full-suite runs while passing alone).
    # Set the cap one above whatever is already counted.
    used = beta.capacity_status()["used"]
    if used >= 100:
        pytest.skip("the beta cap is at its ceiling; no last seat to race for")
    settings.BETA_MAX_USERS = used + 1
    barrier = Barrier(2)
    test_name = connection.settings_dict["NAME"]

    def reserve(email):
        try:
            # Thread-local Django connection inherits the active test DB;
            # no DSN fallback or independently configured SQL connection.
            assert connections["default"].settings_dict["NAME"] == test_name
            barrier.wait(timeout=5)
            beta.invite_emails([email])
            return "reserved"
        except beta.BetaAdmissionError:
            return "full"
        finally:
            connections["default"].close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(reserve, email) for email in ("one@example.com", "two@example.com")]
        assert sorted(future.result(timeout=10) for future in futures) == ["full", "reserved"]
    assert BetaInvitation.objects.filter(email__in=["one@example.com", "two@example.com"]).count() == 1
