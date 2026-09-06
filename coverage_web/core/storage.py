"""Private avatar storage with stable, authenticated same-origin URLs."""
from pathlib import PurePosixPath
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured, SuspiciousFileOperation
from django.urls import reverse
from storages.backends.s3 import S3Storage
from botocore.exceptions import ClientError


def avatar_content_type(name):
    """Only the re-encoded avatar formats belong on the media route."""
    if not isinstance(name, str) or "\\" in name or "\x00" in name:
        raise SuspiciousFileOperation("Invalid avatar path.")
    path = PurePosixPath(name)
    if (not name.startswith("avatars/") or str(path) != name
            or any(part in {".", ".."} for part in path.parts)):
        raise SuspiciousFileOperation("Invalid avatar path.")
    content_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}.get(path.suffix.lower())
    if not content_type:
        raise SuspiciousFileOperation("Unsupported avatar format.")
    return content_type


def media_storage_config(env):
    """Explicit opt-in; a partial remote configuration fails at boot."""
    names = {
        "bucket_name": "MEDIA_S3_BUCKET_NAME", "endpoint_url": "MEDIA_S3_ENDPOINT_URL",
        "region_name": "MEDIA_S3_REGION_NAME", "access_key": "MEDIA_S3_ACCESS_KEY_ID",
        "secret_key": "MEDIA_S3_SECRET_ACCESS_KEY", "security_token": "MEDIA_S3_SESSION_TOKEN",
    }
    values = {key: env(name, default="").strip() for key, name in names.items()}
    if not any(values.values()):
        return {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    for key, name in names.items():
        if key != "security_token" and not values[key]:
            raise ImproperlyConfigured(f"{name} is required when private media storage is configured.")
    endpoint = urlsplit(values["endpoint_url"])
    if (endpoint.scheme != "https" or not endpoint.hostname or endpoint.username
            or endpoint.password or endpoint.query or endpoint.fragment):
        raise ImproperlyConfigured("MEDIA_S3_ENDPOINT_URL must be an HTTPS endpoint without credentials or query parameters.")
    return {
        "BACKEND": "core.storage.PrivateMediaStorage",
        "OPTIONS": {
            **values, "default_acl": None, "querystring_auth": True,
            "file_overwrite": False, "custom_domain": None, "location": "",
            "use_ssl": True, "verify": True, "signature_version": "s3v4",
            "addressing_style": "path", "max_memory_size": 1024 * 1024,
            "object_parameters": {"CacheControl": "private, no-store"},
        },
    }


class PrivateMediaStorage(S3Storage):
    def url(self, name, parameters=None, expire=None, http_method=None):
        avatar_content_type(name)
        return reverse("private-media", kwargs={"path": name})

    def require_conditional_put_support(self):
        """Reject providers known to ignore the migration's no-overwrite guard."""
        host = (urlsplit(self.endpoint_url or "").hostname or "").lower().rstrip(".")
        # Covers both project.storage.supabase.co and the legacy project
        # hostname. Supabase accepts IfNoneMatch but can still replace bytes.
        if any(host == domain or host.endswith("." + domain)
               for domain in ("supabase.co", "supabase.in")):
            raise ImproperlyConfigured(
                "Avatar migration is blocked: Supabase S3 does not enforce "
                "the required conditional writes. Use a storage backend with "
                "verified atomic create-if-absent support before applying this migration. "
                "Normal avatar uploads are unaffected."
            )

    def save_if_absent(self, name, content, *, sha256):
        """Request atomic create without renaming on a compatible provider.

        Known Supabase endpoints are blocked because they ignore the condition.
        Other providers must enforce IfNoneMatch; this guard does not certify
        their behavior. Provider errors never trigger an unconditional retry.
        """
        self.require_conditional_put_support()
        content_type = avatar_content_type(name)
        try:
            self.connection.meta.client.put_object(
                Bucket=self.bucket_name, Key=self._normalize_name(name), Body=content,
                IfNoneMatch="*", ContentType=content_type,
                CacheControl="private, no-store", Metadata={"sha256": sha256},
            )
        except ClientError as exc:
            if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 412:
                return False
            raise
        return True
