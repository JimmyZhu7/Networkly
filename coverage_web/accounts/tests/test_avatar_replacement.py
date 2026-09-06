"""Profile photo removal/replacement must wait for its DB commit."""
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from PIL import Image

from accounts.forms import ProfileForm
from accounts.tests.test_profile_inputs import _post

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    user = get_user_model().objects.create_user(email="replace-photo@example.test", password="x")
    user.avatar.save("old.png", ContentFile(b"old photo bytes"), save=True)
    return user


def _form(mode):
    if mode == "remove":
        form = ProfileForm(_post(remove_avatar=True))
    else:
        buffer = BytesIO()
        Image.new("RGB", (16, 16), "blue").save(buffer, format="PNG")
        form = ProfileForm(_post(), files={"avatar": SimpleUploadedFile("new.png", buffer.getvalue(), content_type="image/png")})
    assert form.is_valid(), form.errors
    return form


@pytest.mark.parametrize("mode", ["remove", "replace"])
@pytest.mark.parametrize("shared", [False, True])
def test_old_avatar_is_removed_after_commit_only_if_unreferenced(owner, mode, shared, django_capture_on_commit_callbacks):
    name, storage = owner.avatar.name, owner.avatar.storage
    if shared:
        get_user_model().objects.create_user(email="shared-replacement@example.test", password="x", avatar=name)
    with django_capture_on_commit_callbacks(execute=True):
        _form(mode).apply_to(owner)
        assert storage.exists(name)
    owner.refresh_from_db()
    assert storage.exists(name) is shared
    if mode == "replace":
        assert owner.avatar.name != name
        assert storage.exists(owner.avatar.name)
    else:
        assert not owner.avatar


@pytest.mark.parametrize("mode", ["remove", "replace"])
def test_rollback_preserves_the_old_avatar_and_discards_deletion_callback(owner, mode, django_capture_on_commit_callbacks):
    name, storage = owner.avatar.name, owner.avatar.storage
    with django_capture_on_commit_callbacks(execute=True) as callbacks:
        with pytest.raises(RuntimeError), transaction.atomic():
            _form(mode).apply_to(owner)
            raise RuntimeError("roll back profile save")
    assert not callbacks
    owner.refresh_from_db()
    assert owner.avatar.name == name
    assert storage.exists(name)
