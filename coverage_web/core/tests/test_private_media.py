"""Owner-only media works through storage.open, including a remote backend."""
from io import BytesIO
from unittest.mock import patch

import pytest
from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    user = get_user_model().objects.create_user(email="private-photo@example.test", password="x")
    user.avatar.save("private.png", ContentFile(b"stored photo bytes"), save=True)
    return user


def test_owner_gets_local_avatar_with_private_cache_policy(client, owner):
    client.force_login(owner)
    response = client.get(owner.avatar.url)
    assert response.status_code == 200
    assert b"".join(response.streaming_content) == b"stored photo bytes"
    assert response["Content-Type"] == "image/png"
    assert response["Cache-Control"] == "private, no-store"
    assert response["X-Content-Type-Options"] == "nosniff"


@pytest.mark.parametrize("who", ["anonymous", "other", "staff"])
def test_nonowners_cannot_fetch_known_avatar_urls_or_open_storage(client, owner, who):
    if who != "anonymous":
        visitor = get_user_model().objects.create_user(email=f"{who}@example.test", password="x", is_staff=who == "staff")
        client.force_login(visitor)
    with patch.object(default_storage, "open") as opened:
        response = client.get(owner.avatar.url)
    assert response.status_code == 404
    opened.assert_not_called()


def test_remote_avatar_bytes_are_proxied_without_redirect_or_signed_url(client, owner):
    client.force_login(owner)
    with patch.object(default_storage, "open", return_value=BytesIO(b"remote photo")) as opened:
        response = client.get(owner.avatar.url)
        assert b"".join(response.streaming_content) == b"remote photo"
    opened.assert_called_once_with(owner.avatar.name, "rb")
    assert response.status_code == 200
    assert "Location" not in response


def test_arbitrary_files_and_directory_paths_are_not_a_public_media_server(client, owner):
    client.force_login(owner)
    for url in ("/media/", "/media/avatars/", "/media/private.txt", "/media/avatars/other.png"):
        assert client.get(url).status_code == 404


def test_removed_avatar_url_stops_working_even_if_bytes_remain(client, owner):
    url = owner.avatar.url
    owner.avatar = None
    owner.save(update_fields=["avatar"])
    client.force_login(owner)
    assert client.get(url).status_code == 404


@pytest.mark.parametrize("status, expected", [(404, 404), (403, 404), (500, 503)])
def test_remote_failure_does_not_expose_provider_errors(client, owner, status, expected):
    client.force_login(owner)
    failure = ClientError({"Error": {"Code": str(status), "Message": "sensitive-provider-detail"},
                           "ResponseMetadata": {"HTTPStatusCode": status}}, "GetObject")
    with patch.object(default_storage, "open", side_effect=failure):
        response = client.get(owner.avatar.url)
    assert response.status_code == expected
    assert b"sensitive-provider-detail" not in response.content
