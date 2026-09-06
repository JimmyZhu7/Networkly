"""Invitation admission. All seat mutations share one PostgreSQL transaction lock.

No mail, plan changes, or public registry endpoints live here. Internal user
creation remains available; capacity_status includes those users and reports
overcapacity rather than silently excluding them from the beta ceiling.
"""

from contextlib import contextmanager
import hashlib

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email
from django.db import connection, transaction
from django.utils import timezone

from .models import BetaInvitation

# Stable application namespace/key; shared by registry, admin and admission.
BETA_LOCK_NAMESPACE = 1129272901
BETA_LOCK_KEY = 100


class BetaAdmissionError(ValidationError):
    pass


INVITATION_REQUIRED = "The free beta is invitation-only. Use the Google account that was invited."
BETA_FULL = "The free beta is full. Existing members can still sign in."
EXISTING_ACCOUNT = "Please sign in to your existing account, then connect Google in Settings."


def normalize_email(email):
    email = (email or "").strip().lower()
    validate_email(email)
    return email


def email_fingerprint(email):
    return hashlib.sha256(normalize_email(email).encode("utf-8")).hexdigest()


def beta_limit():
    return max(0, min(100, int(getattr(settings, "BETA_MAX_USERS", 100))))


@contextmanager
def registry_lock():
    if connection.vendor != "postgresql":
        raise ImproperlyConfigured("Beta admission requires PostgreSQL transaction locks.")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(%s, %s)", [BETA_LOCK_NAMESPACE, BETA_LOCK_KEY])
        yield


def _existing_users():
    return get_user_model().objects.exclude(email="").order_by("pk")


def capacity_status():
    """Read-only union: reservations, consumed seats, and existing accounts."""
    keys = set(BetaInvitation.objects.values_list("email_fingerprint", flat=True))
    keys.update(email_fingerprint(email) for email in _existing_users().values_list("email", flat=True))
    used, limit = len(keys), beta_limit()
    return {"used": used, "limit": limit, "remaining": max(0, limit - used), "over_capacity": used > limit}


def _snapshot_existing_users():
    # Persist existing accounts before issuing/claiming seats. SET_NULL on
    # deletion then preserves their occupied seat, including local accounts.
    for user in _existing_users():
        email = normalize_email(user.email)
        seat, _ = BetaInvitation.objects.get_or_create(
            email_fingerprint=email_fingerprint(email),
            defaults={"email": email, "user": user, "redeemed_at": user.date_joined},
        )
        if seat.redeemed_at is None:
            seat.user = user
            seat.redeemed_at = user.date_joined
            seat.save(update_fields=["user", "redeemed_at"])


def validate_invitation(email):
    """Read-only check; callers that will write must hold registry_lock."""
    email = normalize_email(email)
    seat = BetaInvitation.objects.filter(email_fingerprint=email_fingerprint(email)).first()
    if seat:
        return seat
    # Existing users already occupy their seat, even without a registry row.
    if _existing_users().filter(email__iexact=email).exists():
        return None
    if capacity_status()["remaining"] == 0:
        raise BetaAdmissionError(BETA_FULL, code="beta_full")
    return None


def invite_emails(emails):
    """Reserve a batch atomically; case-insensitive and idempotent, no sends."""
    emails = list(dict.fromkeys(normalize_email(email) for email in emails))
    with registry_lock():
        _snapshot_existing_users()
        seats = []
        for email in emails:
            existing = validate_invitation(email)
            if existing is not None:
                seats.append((existing, False))
                continue
            seat = BetaInvitation.objects.create(email=email, email_fingerprint=email_fingerprint(email))
            seats.append((seat, True))
        return seats


def check_admission(email):
    """Check the current registry; the final claim repeats this under lock."""
    from allauth.account.models import EmailAddress

    email = normalize_email(email)
    if (_existing_users().filter(email__iexact=email).exists()
            or EmailAddress.objects.filter(email__iexact=email).exists()):
        raise BetaAdmissionError(EXISTING_ACCOUNT, code="existing_account")
    status = capacity_status()
    if status["over_capacity"]:
        raise BetaAdmissionError(BETA_FULL, code="beta_full")
    seat = BetaInvitation.objects.filter(email_fingerprint=email_fingerprint(email)).first()
    if seat is None:
        message = BETA_FULL if status["remaining"] == 0 else INVITATION_REQUIRED
        raise BetaAdmissionError(message, code="beta_full" if message == BETA_FULL else "invitation_required")
    if seat.redeemed_at is not None or not seat.email:
        raise BetaAdmissionError(INVITATION_REQUIRED, code="invitation_required")
    return seat


def claim_invitation(email, create_user):
    """Allauth's complete user/social/email save and redemption commit together."""
    email = normalize_email(email)
    with registry_lock():
        _snapshot_existing_users()
        seat = check_admission(email)
        user = create_user()
        if not user.pk or normalize_email(user.email) != email:
            raise BetaAdmissionError(INVITATION_REQUIRED, code="invitation_required")
        seat.user = user
        seat.redeemed_at = timezone.now()
        seat.save(update_fields=["user", "redeemed_at"])
        return user


def anonymize_user_seats(user):
    """Call inside account deletion: retain counted fingerprints, remove PII.

    Also snapshots a local account that predates the first invitation. This
    helper never creates a user and must run before its user row is deleted.
    """
    with registry_lock():
        key = email_fingerprint(user.email)
        seat, _ = BetaInvitation.objects.get_or_create(
            email_fingerprint=key,
            defaults={"email": "", "redeemed_at": user.date_joined},
        )
        from django.db.models import Q
        seats = BetaInvitation.objects.filter(Q(user=user) | Q(pk=seat.pk))
        seats.filter(redeemed_at__isnull=True).update(redeemed_at=user.date_joined)
        seats.update(email="", user=None)
