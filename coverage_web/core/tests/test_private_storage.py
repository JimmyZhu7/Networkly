"""Private S3 configuration and conditional migration uploads, without network."""
from io import BytesIO
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from botocore.exceptions import ClientError
from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation

from core.storage import PrivateMediaStorage, avatar_content_type, media_storage_config

CONFIG = {
    "MEDIA_S3_BUCKET_NAME": "private-avatars", "MEDIA_S3_ENDPOINT_URL": "https://objects.example.test",
    "MEDIA_S3_REGION_NAME": "auto", "MEDIA_S3_ACCESS_KEY_ID": "access-example",
    "MEDIA_S3_SECRET_ACCESS_KEY": "secret-example",
}


def _config(values):
    return media_storage_config(lambda name, default="": values.get(name, default))


def test_blank_configuration_preserves_filesystem_storage():
    assert _config({}) == {"BACKEND": "django.core.files.storage.FileSystemStorage"}


@pytest.mark.parametrize("missing", list(CONFIG))
def test_partial_configuration_fails_without_echoing_credentials(missing):
    values = {key: value for key, value in CONFIG.items() if key != missing}
    with pytest.raises(ImproperlyConfigured) as error:
        _config(values)
    assert missing in str(error.value)
    assert "secret-example" not in str(error.value)
    assert "access-example" not in str(error.value)


@pytest.mark.parametrize("endpoint", [
    "http://objects.example.test", "https://user:secret@objects.example.test",
    "https://objects.example.test?token=secret", "https://objects.example.test#secret", "file:///tmp/avatars",
])
def test_endpoint_rejects_insecure_or_credential_bearing_urls(endpoint):
    with pytest.raises(ImproperlyConfigured) as error:
        _config({**CONFIG, "MEDIA_S3_ENDPOINT_URL": endpoint})
    assert endpoint not in str(error.value)


def test_remote_config_requires_private_tls_and_keeps_static_files_separate():
    config = _config(CONFIG)
    assert config["BACKEND"] == "core.storage.PrivateMediaStorage"
    options = config["OPTIONS"]
    assert options["default_acl"] is None
    assert "ACL" not in options["object_parameters"]
    assert options["verify"] is True and options["use_ssl"] is True
    assert options["querystring_auth"] is True
    assert options["custom_domain"] is None
    assert options["file_overwrite"] is False


def test_avatar_url_is_same_origin_and_contains_no_storage_credentials():
    storage = PrivateMediaStorage(**_config(CONFIG)["OPTIONS"])
    with patch.object(PrivateMediaStorage, "connection", new_callable=PropertyMock) as client:
        assert storage.url("avatars/profile.png") == "/media/avatars/profile.png"
        client.assert_not_called()


@pytest.mark.parametrize("name", ["../private.png", "avatars/../private.png", "/avatars/x.png", "avatars//x.png", "avatars/x.svg", "avatars/x.html", "avatars\\x.png"])
def test_only_normalized_avatar_image_keys_are_allowed(name):
    with pytest.raises(SuspiciousFileOperation):
        avatar_content_type(name)


def test_migration_put_is_conditional_private_and_does_not_rename_the_key():
    storage = PrivateMediaStorage(**_config(CONFIG)["OPTIONS"])
    connection = MagicMock()
    content = BytesIO(b"photo")
    with patch.object(PrivateMediaStorage, "connection", new_callable=PropertyMock, return_value=connection):
        assert storage.save_if_absent("avatars/profile.png", content, sha256="known-hash")
    call = connection.meta.client.put_object.call_args.kwargs
    assert call["IfNoneMatch"] == "*"
    assert call["Key"] == "avatars/profile.png"
    assert call["Body"] is content
    assert call["Metadata"] == {"sha256": "known-hash"}
    assert "ACL" not in call
    assert call["CacheControl"] == "private, no-store"


@pytest.mark.parametrize("endpoint", [
    "https://project.storage.supabase.co/storage/v1/s3",
    "https://project.supabase.co/storage/v1/s3",
    "https://project.supabase.in/storage/v1/s3",
])
def test_supabase_migration_rejected_before_any_remote_connection(endpoint):
    storage = PrivateMediaStorage(**_config({**CONFIG, "MEDIA_S3_ENDPOINT_URL": endpoint})["OPTIONS"])
    with patch.object(PrivateMediaStorage, "connection", new_callable=PropertyMock) as connection:
        with pytest.raises(ImproperlyConfigured, match="Supabase S3 does not enforce"):
            storage.save_if_absent("avatars/profile.png", BytesIO(b"photo"), sha256="hash")
        connection.assert_not_called()
    # The guard is specific to migration; ordinary authenticated media URLs work.
    assert storage.url("avatars/profile.png") == "/media/avatars/profile.png"


def test_supabase_apply_rejected_before_loading_users_or_copying_any_files():
    from django.core.management.base import CommandError
    from core.management.commands import migrate_avatar_storage as command

    storage = PrivateMediaStorage(**_config({
        **CONFIG, "MEDIA_S3_ENDPOINT_URL": "https://project.storage.supabase.co/storage/v1/s3",
    })["OPTIONS"])
    with patch.object(command, "default_storage", storage), \
            patch.object(command, "get_user_model") as users, \
            patch.object(PrivateMediaStorage, "connection", new_callable=PropertyMock) as connection:
        with pytest.raises(CommandError, match="Avatar migration is blocked"):
            command.Command().handle(apply=True, source_root="/unused")
        users.assert_not_called()
        connection.assert_not_called()


def test_supabase_normal_avatar_upload_does_not_use_migration_guard():
    storage = PrivateMediaStorage(**_config({
        **CONFIG, "MEDIA_S3_ENDPOINT_URL": "https://project.storage.supabase.co/storage/v1/s3",
    })["OPTIONS"])
    name = "avatars/231be859-4900-4a69-804d-4cfd20786a92.png"
    with patch.object(storage, "get_available_name", return_value=name), \
            patch.object(storage, "_save", return_value=name) as upload, \
            patch.object(storage, "require_conditional_put_support") as guard:
        assert storage.save(name, BytesIO(b"photo")) == name
        upload.assert_called_once()
        guard.assert_not_called()


@pytest.mark.parametrize("status", [412, 403, 409, 501])
def test_existing_object_or_unsupported_condition_never_falls_back_to_overwrite(status):
    storage = PrivateMediaStorage(**_config(CONFIG)["OPTIONS"])
    connection = MagicMock()
    connection.meta.client.put_object.side_effect = ClientError(
        {"Error": {"Code": str(status)}, "ResponseMetadata": {"HTTPStatusCode": status}}, "PutObject",
    )
    with patch.object(PrivateMediaStorage, "connection", new_callable=PropertyMock, return_value=connection):
        if status == 412:
            assert storage.save_if_absent("avatars/profile.png", BytesIO(b"photo"), sha256="hash") is False
        else:
            with pytest.raises(ClientError):
                storage.save_if_absent("avatars/profile.png", BytesIO(b"photo"), sha256="hash")
    assert connection.meta.client.put_object.call_count == 1
