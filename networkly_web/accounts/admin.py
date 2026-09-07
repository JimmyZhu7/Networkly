from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django import forms

from .models import BetaInvitation, User
from . import beta


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Founder-facing CRUD for the one model that isn't itself
    tenant-scoped (it *is* the tenant) — see docs/build-plan.md §2.
    Subclasses Django's own `UserAdmin` for the well-tested
    password-change / permissions widgets, replacing every fieldset
    reference to the now-gone `username` field.
    """

    ordering = ("email",)
    list_display = (
        "email",
        "name",
        "school",
        "class_year",
        "target_cycles",
        "plan",
        "is_staff",
        "is_active",
        "onboarded_at",
        "created",
    )
    # `target_cycles` (an ArrayField, like regions/tracks below) dropped from
    # list_filter: Django's stock filter needs discrete Field choices, not a
    # Postgres array — the same reason regions/tracks were never in here.
    list_filter = ("plan", "is_staff", "is_active", "is_superuser", "school")
    search_fields = ("email", "name", "school")
    readonly_fields = ("created", "last_login", "date_joined")

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Profile",
            {
                "fields": (
                    "name",
                    "first_name",
                    "last_name",
                    "school",
                    "school_emails",
                    "class_year",
                    "target_cycles",
                    "regions",
                    "tracks",
                    "assets",
                )
            },
        ),
        (
            # These three feed the domain engines directly (fit-score
            # sponsorship, cadence windows, the Today pace ring) and have no
            # settings-page UI yet, so admin is the only place to set them.
            "Recruiting preferences",
            {
                "fields": (
                    "work_authorization",
                    "cadence_params",
                    "weekly_touch_goal",
                ),
                "description": (
                    "work_authorization is keyed by region, e.g. "
                    '{"us": "citizen", "hk": "sponsorship"}. cadence_params '
                    "only honors the keys in crm.views.TUNABLE_CADENCE_PARAMS; "
                    "anything else is ignored at read time."
                ),
            },
        ),
        (
            # No billing writes this yet (no payment processor in the
            # codebase) — admin IS the billing system for now. The advisor
            # page (assistant/plans.py) and the credit ledger
            # (billing/credits.py, billing/admin.py — grant or adjust a
            # student's balance there) both read it.
            "Plan",
            {
                "fields": ("plan",),
                "description": (
                    "Free: Haiku, 60 credits/month (60 messages, or mix with rescans). "
                    "Pro: Sonnet, 180 credits/month (60 messages at 3 credits each). "
                    "Set by hand until Stripe exists — see the Credit Ledger admin to "
                    "grant or adjust a student's balance directly."
                ),
            },
        ),
        ("Account", {"fields": ("google_sub", "onboarded_at")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Dates", {"fields": ("last_login", "date_joined", "created", "deleted_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


class BetaInvitationForm(forms.ModelForm):
    class Meta:
        model = BetaInvitation
        fields = ("email",)

    def clean_email(self):
        email = beta.normalize_email(self.cleaned_data["email"])
        beta.validate_invitation(email)
        return email


@admin.register(BetaInvitation)
class BetaInvitationAdmin(admin.ModelAdmin):
    form = BetaInvitationForm
    list_display = ("email", "created_at", "redeemed_at", "user")
    search_fields = ("email",)
    actions = None

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_fields(self, request, obj=None):
        return ("email", "created_at", "redeemed_at", "user") if obj else ("email",)

    def get_readonly_fields(self, request, obj=None):
        return self.get_fields(request, obj) if obj else ()

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        if request.method == "POST" and object_id is None:
            # Form validation and persistence see one serialized capacity.
            with beta.registry_lock():
                return super().changeform_view(request, object_id, form_url, extra_context)
        return super().changeform_view(request, object_id, form_url, extra_context)

    def save_model(self, request, obj, form, change):
        seat, _ = beta.invite_emails([form.cleaned_data["email"]])[0]
        # Django's admin logs/redirects using the instance returned by save_form.
        obj.__dict__.update(seat.__dict__)
