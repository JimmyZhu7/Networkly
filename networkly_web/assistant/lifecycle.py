"""Account authority must be current at every external-call/write boundary."""

from django.contrib.auth import get_user_model


INACTIVE_TEXT = "This reply stopped because your account is no longer active."


class InactiveAccountError(Exception):
    pass


def require_active_user(user):
    if not get_user_model().objects.filter(
        pk=user.pk, is_active=True, deleted_at__isnull=True,
    ).exists():
        raise InactiveAccountError(INACTIVE_TEXT)
