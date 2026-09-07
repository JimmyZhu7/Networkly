"""Deleting an account signs out every device, not only the one that asked.

Session rows have no foreign key to the user, so nothing cascades. The view
flushes the caller's own session; the other devices' rows stayed valid until
their natural expiry.
"""
from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session

from accounts.services import delete_user_and_data


def _session_for(user) -> str:
    store = SessionStore()
    store["_auth_user_id"] = str(user.pk)
    store["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
    store.create()
    return store.session_key


@pytest.mark.django_db
def test_every_session_of_the_deleted_user_is_gone_and_others_survive():
    User = get_user_model()
    doomed = User.objects.create_user(email="doomed@example.com", password="x" * 12)
    bystander = User.objects.create_user(email="bystander@example.com", password="x" * 12)
    phone, laptop = _session_for(doomed), _session_for(doomed)
    other = _session_for(bystander)

    delete_user_and_data(doomed)

    assert not Session.objects.filter(session_key__in=[phone, laptop]).exists()
    assert Session.objects.filter(session_key=other).exists()
