"""Custom allauth account adapter — trims allauth's own flash messages.

allauth's `DefaultAccountAdapter.add_message` renders a message on every
login and logout ("Successfully signed in as x@y.com.", "You have signed
out."). Those fire on every session, stack up during normal use, and add
nothing a signed-in user doesn't already know from being on the page — pure
noise, unlike a one-time confirmation such as onboarding's "You're all set."
(accounts/views.py), which stays.

Only the two auth-flow templates are swallowed; everything else (password
changed, email confirmed, etc.) still flows through the base adapter
unchanged.
"""

from __future__ import annotations

from copy import copy

from allauth.account.adapter import DefaultAccountAdapter
from allauth.core.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponseRedirect
from django.urls import reverse

from .access import beta_enabled
from . import beta

_SUPPRESSED_TEMPLATES = {
    "account/messages/logged_in.txt",
    "account/messages/logged_out.txt",
}


class CoverageAccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # Social signup has its own verified-provider gate below. Closing the
        # local form avoids reserving somebody else's email without proof.
        return not beta_enabled() and super().is_open_for_signup(request)

    def save_user(self, request, user, form, commit=True):
        if beta_enabled() and not getattr(request, "_beta_google_signup", False):
            _deny_signup(request, beta.INVITATION_REQUIRED)
        return super().save_user(request, user, form, commit=commit)

    def render_mail(self, template_prefix, email, context, headers=None):
        # Preserve hosts and confirmation links without mutating cached Site data.
        context = dict(context)
        if context.get("current_site") is not None:
            site = copy(context["current_site"])
            site.name = "Networkly"
            context["current_site"] = site
        return super().render_mail(template_prefix, email, context, headers=headers)

    def add_message(self, request, level, message_template=None, message_context=None,
                     extra_tags="", message=None):
        if message_template in _SUPPRESSED_TEMPLATES:
            return
        super().add_message(
            request, level,
            message_template=message_template, message_context=message_context,
            extra_tags=extra_tags, message=message,
        )


def _deny_signup(request, message):
    # Do not leave a pending allauth form that could substitute another email.
    request.session.pop("socialaccount_sociallogin", None)
    messages.error(request, message)
    raise ImmediateHttpResponse(HttpResponseRedirect(reverse("account_login")))


def _verified_google_email(sociallogin, form=None):
    data = sociallogin.account.extra_data or {}
    if (sociallogin.account.provider != "google"
            or not (data.get("email_verified") is True or data.get("verified_email") is True)):
        raise beta.BetaAdmissionError(beta.INVITATION_REQUIRED, code="invitation_required")
    email = beta.normalize_email(data.get("email"))
    supplied = {beta.normalize_email(address.email) for address in sociallogin.email_addresses
                if address.verified}
    if email not in supplied or beta.normalize_email(sociallogin.user.email) != email:
        raise beta.BetaAdmissionError(beta.INVITATION_REQUIRED, code="invitation_required")
    if form is not None and beta.normalize_email(form.cleaned_data.get("email")) != email:
        raise beta.BetaAdmissionError(beta.INVITATION_REQUIRED, code="invitation_required")
    return email


class CoverageSocialAccountAdapter(DefaultSocialAccountAdapter):
    """Existing sign-ins stay available; new beta users need verified Google."""

    def _admission_email(self, request, sociallogin, form=None):
        try:
            email = _verified_google_email(sociallogin, form)
            beta.check_admission(email)
            return email
        except ValidationError as exc:
            message = " ".join(exc.messages) if isinstance(exc, beta.BetaAdmissionError) else beta.INVITATION_REQUIRED
            _deny_signup(request, message)

    def pre_social_login(self, request, sociallogin):
        super().pre_social_login(request, sociallogin)
        if not beta_enabled() or sociallogin.is_existing:
            return
        if sociallogin.state.get("process") == "connect" and request.user.is_authenticated:
            return
        # Before allauth can redirect a duplicate address to a signup form
        # or its enumeration-prevention email path.
        self._admission_email(request, sociallogin)

    def is_open_for_signup(self, request, sociallogin):
        if not beta_enabled():
            return super().is_open_for_signup(request, sociallogin)
        self._admission_email(request, sociallogin)
        return True

    def save_user(self, request, sociallogin, form=None):
        if not beta_enabled():
            return super().save_user(request, sociallogin, form=form)
        email = self._admission_email(request, sociallogin, form)

        def create_user():
            sociallogin.user.email = email
            if form is not None:
                form.cleaned_data["email"] = email
            previous = getattr(request, "_beta_google_signup", False)
            request._beta_google_signup = True
            try:
                # Installed allauth saves User, SocialAccount and EmailAddress
                # here. The caller's transaction encloses every one of them.
                return super(CoverageSocialAccountAdapter, self).save_user(request, sociallogin, form=form)
            finally:
                request._beta_google_signup = previous

        try:
            return beta.claim_invitation(email, create_user)
        except beta.BetaAdmissionError as exc:
            _deny_signup(request, " ".join(exc.messages))
