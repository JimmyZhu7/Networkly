"""Deleting an account also removes its uploaded photo, only after commit."""

import pytest
from django.core.files.base import ContentFile
from django.db import transaction

from accounts.models import User
from accounts.services import delete_user_and_data

pytestmark = pytest.mark.django_db


@pytest.fixture
def account(settings, tmp_path, monkeypatch):
    settings.MEDIA_ROOT = tmp_path
    monkeypatch.setattr("capture.google_revoke.revoke_all_for_user", lambda user: None)
    user = User.objects.create_user(email="photo-delete@example.test", password="x")
    user.avatar.save("photo.png", ContentFile(b"uploaded photo bytes"), save=True)
    return user


@pytest.mark.parametrize("shared_reference", [False, True])
def test_deletion_cleans_only_unreferenced_photo(account, shared_reference, django_capture_on_commit_callbacks):
    other = User.objects.create_user(email="other-photo@example.test", password="x")
    if shared_reference:
        other.avatar = account.avatar.name
        other.save(update_fields=["avatar"])
    else:
        other.avatar.save("other.png", ContentFile(b"other account photo"), save=True)
    name, storage, pk = account.avatar.name, account.avatar.storage, account.pk

    with django_capture_on_commit_callbacks(execute=True):
        delete_user_and_data(account)
        assert storage.exists(name), "file removal must wait for commit"

    assert not User.objects.filter(pk=pk).exists()
    assert storage.exists(name) is shared_reference
    other.refresh_from_db()
    assert other.avatar.storage.exists(other.avatar.name)


def test_rollback_keeps_account_and_photo(account, django_capture_on_commit_callbacks):
    name, storage, pk = account.avatar.name, account.avatar.storage, account.pk
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(RuntimeError), transaction.atomic():
            delete_user_and_data(account)
            raise RuntimeError("outer transaction rejected")
    assert not callbacks
    assert User.objects.filter(pk=pk).exists()
    assert storage.exists(name)
