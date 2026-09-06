"""Individual feature access, independent of the stored billing plan."""

from django.conf import settings
from django.db.models import Q


def beta_enabled():
    return bool(getattr(settings, "BETA_ENABLED", False))


def effective_plan(user):
    if beta_enabled():
        return "pro"
    plan = (getattr(user, "plan", "") or "").strip().lower()
    return plan if plan in {"free", "pro"} else "free"


def has_individual_features(user):
    return getattr(user, "is_active", True) and effective_plan(user) == "pro"


def sync_user_filter():
    """The same entitlement for workers; inactive accounts never sync."""
    query = Q(user__is_active=True)
    return query if beta_enabled() else query & Q(user__plan="pro")


def plan_label(user):
    return "Free Beta" if beta_enabled() else effective_plan(user).capitalize()
