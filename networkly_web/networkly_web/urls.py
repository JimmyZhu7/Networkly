"""
Root URL configuration for networkly_web.
"""
from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import RedirectView
import re

from analytics import views as analytics_views
from core import views as core_views
from core.media import avatar
from directory import views as directory_views

admin.site.site_header = "Networkly administration"
admin.site.site_title = "Networkly"
admin.site.index_title = "Administration"

urlpatterns = [
    # Not a literal "admin/": settings.ADMIN_URL_PREFIX (default "admin/",
    # production sets an unguessable one) so the staff door that reads every
    # tenant is not sitting on the path every scanner on the internet tries
    # first. django-axes locks the form itself — see the AXES_* block in
    # settings/base.py — and resolves `admin:index` to find it, so moving the
    # prefix does not move the lockout off it.
    path(settings.ADMIN_URL_PREFIX, admin.site.urls),
    # django-allauth: login/logout/signup + Google social-auth callback.
    path("accounts/", include("allauth.urls")),
    # The opportunities feed (insight programmes / internships /
    # entry-level) — the star page: an urgency feed ranked by deadline then
    # freshness, served by the directory app's list view.
    path("opportunities/", directory_views.opportunities, name="opportunities"),
    # The user's saved / applied roles, and the track toggle behind each card.
    path("opportunities/mine/", directory_views.my_applications, name="my_applications"),
    path("opportunities/<int:pk>/track/", directory_views.track_opportunity, name="track_opportunity"),
    # One click saves every open role whose own text names the user's class
    # year — the eligibility lens reaching the pipeline. Gated behind an
    # explicit confirm (see the banner's <details> in _results.html) and
    # reversible immediately after (`track_eligible_undo`, below).
    path("opportunities/track-eligible/", directory_views.track_eligible, name="track_eligible"),
    path("opportunities/track-eligible/undo/", directory_views.track_eligible_undo, name="track_eligible_undo"),
    # Bulk-remove every role still sitting in Saved (never Applied/
    # Interviewing/Offer) — the other side of the one-click bulk save, so 200+
    # rows never again means 200+ individual Remove clicks.
    path("opportunities/saved/clear/", directory_views.clear_saved, name="clear_saved"),
    # The description we already fetched, read inline instead of behind a
    # four-second Workday shell. Public: the posting itself is public.
    path("opportunities/<int:pk>/read/", directory_views.role_description, name="role_description"),
    # Per-firm detail pages linked from the feed.
    path("firms/", include("directory.urls")),
    path("app/", include("crm.urls")),               # authed hub: today, network
    path("welcome/", include("accounts.urls")),      # onboarding, import, settings, delete/export
    # The legal pages live under /welcome/, but /privacy/ and /terms/ are what
    # people type and what link scanners probe. Permanent redirects, not
    # duplicate routes: one canonical URL per document.
    # Browsers fall back to /favicon.ico: Chrome after a pushState history
    # change, Safari as a matter of course. It serves the file DIRECTLY —
    # no redirect. Both earlier attempts at the blank-tab bug left a redirect
    # here, and Safari is unreliable about following one for an icon, so the
    # hop is removed rather than merely repointed.
    path("favicon.ico", core_views.favicon, name="favicon"),
    path("privacy/", RedirectView.as_view(pattern_name="accounts:privacy", permanent=True)),
    path("terms/", RedirectView.as_view(pattern_name="accounts:terms", permanent=True)),
    path("capture/", include("capture.urls")),        # Gmail Live OAuth (connect/callback/disconnect)
    path("billing/", include("billing.urls")),         # Stripe checkout + webhook (billing/stripe_gateway.py)
    # "Talk to Networkly": the advisor page, reasoning over the signed-in
    # student's own CRM through a tool loop (assistant/agent.py).
    path("assistant/", include("assistant.urls")),
    # The founder dashboard: staff-only reader over the ProductEvent rows
    # every action has been writing since the cutover.
    path("instrument/", analytics_views.dashboard, name="instrument"),
    # Staff-only JSON: is every render.yaml cron still actually running,
    # read from the JobRun rows those commands write via ops/tracking.py.
    path("ops/", include("ops.urls")),
    path("", include("core.urls")),
]

# Private uploads use the same authenticated route with local disk or S3.
# No object URL, signature, arbitrary media file, or directory is exposed.
urlpatterns += [
    re_path(
        r"^%s(?P<path>.*)$" % re.escape(settings.MEDIA_URL.lstrip("/")),
        avatar, name="private-media",
    ),
]
