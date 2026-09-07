"""Local-to-private migration is preview-first, non-destructive, and verified."""
from io import BytesIO, StringIO
from unittest.mock import MagicMock, call, patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError

from core.management.commands import migrate_avatar_storage as command
from core.storage import PrivateMediaStorage

pytestmark = pytest.mark.django_db


@pytest.fixture
def local_avatar(tmp_path):
    name = "avatars/legacy.png"
    path = tmp_path / name
    path.parent.mkdir()
    path.write_bytes(b"local avatar bytes")
    user = get_user_model().objects.create_user(email="migrate-avatar@example.test", password="x", avatar=name)
    return user, path, tmp_path


def _run(root, storage, *args):
    out = StringIO()
    with patch.object(command, "default_storage", storage):
        call_command("migrate_avatar_storage", "--source-root", str(root), *args, stdout=out, stderr=StringIO())
    return out.getvalue()


def _storage(objects):
    storage = MagicMock(spec=PrivateMediaStorage)

    def save(name, content, *, sha256):
        if name in objects:
            return False
        objects[name] = content.read()
        return True

    storage.save_if_absent.side_effect = save
    storage.open.side_effect = lambda name, mode: BytesIO(objects[name])
    return storage


def test_default_preview_has_no_remote_calls_or_writes(local_avatar):
    user, path, root = local_avatar
    storage = _storage({})
    out = _run(root, storage)
    assert "Dry run: 1 local avatar(s) ready" in out
    assert not storage.mock_calls
    user.refresh_from_db()
    assert user.avatar.name == "avatars/legacy.png"
    assert path.read_bytes() == b"local avatar bytes"


def test_apply_copies_exact_name_and_bytes_but_retains_local_file_and_db_reference(local_avatar):
    user, path, root = local_avatar
    objects = {}
    storage = _storage(objects)
    out = _run(root, storage, "--apply")
    assert "1 copied and verified" in out
    assert objects == {user.avatar.name: path.read_bytes()}
    user.refresh_from_db()
    assert user.avatar.name == "avatars/legacy.png"
    assert path.exists()
    assert "1 already identical" in _run(root, storage, "--apply")
    storage.delete.assert_not_called()


def test_same_name_different_remote_content_is_never_overwritten(local_avatar):
    user, path, root = local_avatar
    objects = {user.avatar.name: b"different remote photo"}
    storage = _storage(objects)
    with pytest.raises(CommandError, match="incomplete"):
        _run(root, storage, "--apply")
    assert objects[user.avatar.name] == b"different remote photo"
    assert path.read_bytes() == b"local avatar bytes"
    storage.delete.assert_not_called()
    storage.save.assert_not_called()


def test_provider_failure_cannot_trigger_unconditional_fallback_or_leak_error(local_avatar):
    user, path, root = local_avatar
    storage = _storage({})
    storage.save_if_absent.side_effect = RuntimeError("credential-and-provider-details")
    out, err = StringIO(), StringIO()
    with patch.object(command, "default_storage", storage), pytest.raises(CommandError):
        call_command("migrate_avatar_storage", "--source-root", str(root), "--apply", stdout=out, stderr=err)
    assert "credential-and-provider-details" not in out.getvalue() + err.getvalue()
    storage.save.assert_not_called()
    storage.delete.assert_not_called()
    assert path.exists()


@pytest.mark.parametrize("unsafe", ["missing", "symlink", "traversal"])
def test_missing_or_unsafe_local_avatar_is_not_uploaded(local_avatar, unsafe):
    user, path, root = local_avatar
    if unsafe == "missing":
        path.unlink()
    elif unsafe == "symlink":
        outside = root.parent / "external-photo.png"
        outside.write_bytes(b"outside media")
        path.unlink()
        path.symlink_to(outside)
    else:
        user.avatar = "avatars/../external-photo.png"
        user.save(update_fields=["avatar"])
    storage = _storage({})
    with pytest.raises(CommandError, match="incomplete"):
        _run(root, storage, "--apply")
    # Only the local provider prerequisite is allowed; any remote read,
    # existence check, upload, or delete would add a call and fail this guard.
    assert storage.mock_calls == [call.require_conditional_put_support()]


def test_shared_references_copy_once_and_unreferenced_files_stay_local(local_avatar):
    user, path, root = local_avatar
    get_user_model().objects.create_user(email="shared-photo@example.test", password="x", avatar=user.avatar.name)
    (root / "avatars/unreferenced.png").write_bytes(b"not referenced")
    storage = _storage({})
    assert "1 copied and verified" in _run(root, storage, "--apply")
    assert storage.save_if_absent.call_count == 1
    assert (root / "avatars/unreferenced.png").exists()


def _rekey_storage(objects):
    storage = _storage(objects)

    def save(name, content):
        assert name not in objects
        objects[name] = content.read()
        return name

    storage.save.side_effect = save
    storage.delete.side_effect = lambda name: objects.pop(name)
    return storage


def test_rekey_preview_does_not_touch_storage_or_db_reference(local_avatar):
    user, path, root = local_avatar
    storage = _rekey_storage({})
    assert "No remote calls or writes" in _run(root, storage, "--rekey")
    assert not storage.mock_calls
    user.refresh_from_db()
    assert user.avatar.name == "avatars/legacy.png"


def test_rekey_preserves_old_remote_and_local_file_and_verifies_new_reference(local_avatar):
    user, path, root = local_avatar
    objects = {user.avatar.name: b"different existing remote object"}
    storage = _rekey_storage(objects)
    assert "1 rekeyed and verified" in _run(root, storage, "--rekey", "--apply")
    user.refresh_from_db()
    assert user.avatar.name != "avatars/legacy.png"
    assert objects[user.avatar.name] == path.read_bytes()
    assert objects["avatars/legacy.png"] == b"different existing remote object"
    assert path.exists()
    storage.require_conditional_put_support.assert_not_called()
    storage.save_if_absent.assert_not_called()
    storage.delete.assert_not_called()


def test_rekey_concurrent_avatar_change_kept_and_only_attempt_upload_removed(local_avatar):
    user, path, root = local_avatar
    objects = {user.avatar.name: b"old remote", "avatars/newer.png": b"new avatar"}
    storage = _rekey_storage(objects)

    def readback(name, mode):
        get_user_model().objects.filter(pk=user.pk).update(avatar="avatars/newer.png")
        return BytesIO(objects[name])

    storage.open.side_effect = readback
    with pytest.raises(CommandError, match="incomplete"):
        _run(root, storage, "--rekey", "--apply")
    user.refresh_from_db()
    assert user.avatar.name == "avatars/newer.png"
    assert objects == {"avatars/legacy.png": b"old remote", "avatars/newer.png": b"new avatar"}
    assert path.exists()
    storage.delete.assert_called_once_with(storage.save.call_args.args[0])


@pytest.mark.parametrize("failure", ["upload", "readback", "database"])
def test_rekey_failure_retains_original_reference_and_cleans_only_confirmed_upload(local_avatar, failure):
    from django.db.models.query import QuerySet

    user, path, root = local_avatar
    objects = {user.avatar.name: b"old remote"}
    storage = _rekey_storage(objects)
    real_update = QuerySet.update

    def update_then_fail(queryset, **kwargs):
        real_update(queryset, **kwargs)
        raise RuntimeError("database failure after update")

    if failure == "upload":
        storage.save.side_effect = RuntimeError("provider credentials must stay private")
    elif failure == "readback":
        storage.open.side_effect = lambda name, mode: BytesIO(b"corrupt")
    with patch.object(QuerySet, "update", update_then_fail if failure == "database" else real_update):
        with pytest.raises(CommandError, match="incomplete"):
            _run(root, storage, "--rekey", "--apply")
    user.refresh_from_db()
    assert user.avatar.name == "avatars/legacy.png"
    assert objects == {"avatars/legacy.png": b"old remote"}
    assert path.exists()
    if failure == "upload":
        storage.delete.assert_not_called()
    else:
        storage.delete.assert_called_once_with(storage.save.call_args.args[0])
