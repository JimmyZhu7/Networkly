"""Launch gate configuration tests. No database or external services used."""
from io import StringIO
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet
from django.core.management import CommandError, call_command

from accounts import beta
from ops.management.commands.deploy_preflight import Check, Command, PASS


@pytest.fixture
def launch_configuration(settings, monkeypatch):
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "networkly_web.settings.production")
    monkeypatch.setenv("SENTRY_DSN", "https://public-key@o1.ingest.sentry.io/123")
    for key in ("GMAIL_LIVE_CLIENT_ID", "GMAIL_LIVE_CLIENT_SECRET", "GMAIL_LIVE_TOKEN_KEY"):
        monkeypatch.delenv(key, raising=False)
    settings.BETA_ENABLED = True
    settings.BETA_MAX_USERS = 100
    settings.DEBUG = False
    settings.SECRET_KEY = "a-valid-secret-never-rendered-in-the-output"
    settings.SITE_URL = "https://coverage-web.onrender.com"
    settings.ALLOWED_HOSTS = ["coverage-web.onrender.com"]
    settings.CSRF_TRUSTED_ORIGINS = [settings.SITE_URL]
    settings.SECURE_SSL_REDIRECT = True
    settings.SECURE_REDIRECT_EXEMPT = [r"^healthz$"]
    settings.SESSION_COOKIE_SECURE = True
    settings.CSRF_COOKIE_SECURE = True
    settings.CACHES = {"default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": "redis://shared-cache:6379/0",
    }}
    settings.EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    settings.EMAIL_HOST = "smtp.mail-provider.net"
    settings.EMAIL_HOST_USER = "relay-user"
    settings.EMAIL_HOST_PASSWORD = "relay-secret"
    settings.EMAIL_USE_TLS = True
    settings.DEFAULT_FROM_EMAIL = "Networkly <support@networkly.app>"
    settings.SOCIALACCOUNT_PROVIDERS = {"google": {
        "SCOPE": ["openid", "email", "profile"],
        "APP": {"client_id": "login-client", "secret": "login-secret"},
    }}
    settings.GMAIL_LIVE_CLIENT_ID = "mail-client"
    settings.GMAIL_LIVE_CLIENT_SECRET = "mail-secret"
    settings.GMAIL_LIVE_TOKEN_KEY = Fernet.generate_key().decode()
    settings.GCAL_LIVE_ENABLED = True
    settings.STORAGES = {"default": {
        "BACKEND": "core.storage.PrivateMediaStorage",
        "OPTIONS": {
            "bucket_name": "private-avatars", "endpoint_url": "https://s3.storage-provider.net",
            "region_name": "us-east-1", "access_key": "storage-access", "secret_key": "storage-secret",
            "default_acl": None, "querystring_auth": True, "custom_domain": None,
            "location": "", "use_ssl": True, "verify": True,
        },
    }}
    settings.VAPID_PUBLIC_KEY = "public-push-key"
    settings.VAPID_PRIVATE_KEY = "private-push-key"
    settings.VAPID_CLAIM_EMAIL = "support@networkly.app"
    settings.SENTRY_DSN = "https://public-key@o1.ingest.sentry.io/123"
    settings.ANTHROPIC_API_KEY = "sk-ant-configured-key"
    settings.STRIPE_SECRET_KEY = ""
    settings.STRIPE_WEBHOOK_SECRET = ""
    monkeypatch.setattr(Command, "_database", lambda self: [Check(PASS, "DATABASE_URL", "mocked read-only database check.")])
    capacity = Mock(return_value={"used": 4, "limit": 100, "remaining": 96, "over_capacity": False})
    monkeypatch.setattr(beta, "capacity_status", capacity)
    import importlib.util
    original_find_spec = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec", lambda name, *args, **kwargs: object() if name == "sentry_sdk" else original_find_spec(name, *args, **kwargs))
    return capacity


def report(*args):
    out = StringIO()
    call_command("deploy_preflight", *args, stdout=out, stderr=out)
    return out.getvalue()


def test_all_individual_configuration_passes_without_stripe(launch_configuration, monkeypatch):
    # Beta must not inspect/require Stripe even if its usual checker breaks.
    monkeypatch.setattr("billing.stripe_gateway.is_configured", Mock(side_effect=AssertionError("Stripe checked")))
    output = report("--launch")
    launch_configuration.assert_called_once_with()
    assert "0 warn · 0 fail" in output
    assert "Configuration check only" in output
    assert "No provider calls" in output
    assert "new checkout is blocked" in output
    assert "Google project audience and lifetime quota require separate verification" in output


@pytest.mark.parametrize("setting,value,key", [
    ("BETA_ENABLED", False, "BETA_ENABLED"),
    ("BETA_MAX_USERS", 101, "BETA_MAX_USERS"),
    ("BETA_MAX_USERS", 0, "BETA_MAX_USERS"),
    ("DEBUG", True, "DEBUG"),
    ("SITE_URL", "http://coverage-web.onrender.com", "SITE_URL"),
    ("SITE_URL", "https://localhost", "SITE_URL"),
    ("SITE_URL", "https://coverage-web.onrender.com/private", "SITE_URL"),
    ("ALLOWED_HOSTS", ["*"], "DJANGO_ALLOWED_HOSTS"),
    ("CSRF_TRUSTED_ORIGINS", ["https://wrong-origin.net"], "DJANGO_CSRF_TRUSTED_ORIGINS"),
    ("SESSION_COOKIE_SECURE", False, "SESSION_COOKIE_SECURE"),
    ("SECURE_SSL_REDIRECT", False, "SECURE_SSL_REDIRECT"),
    ("CACHES", {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}, "REDIS_URL"),
    ("EMAIL_BACKEND", "django.core.mail.backends.locmem.EmailBackend", "EMAIL_URL"),
    ("EMAIL_HOST_PASSWORD", "", "EMAIL_URL"),
    ("DEFAULT_FROM_EMAIL", "no-reply@localhost", "DEFAULT_FROM_EMAIL"),
    ("SOCIALACCOUNT_PROVIDERS", {}, "GOOGLE_OAUTH_CLIENT_ID"),
    ("GMAIL_LIVE_CLIENT_SECRET", "changeme", "GMAIL_LIVE_CLIENT_SECRET"),
    ("GMAIL_LIVE_TOKEN_KEY", "malformed-key", "GMAIL_LIVE_TOKEN_KEY"),
    ("GCAL_LIVE_ENABLED", False, "GCAL_LIVE_ENABLED"),
    ("STORAGES", {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}}, "MEDIA_S3_*"),
    ("VAPID_CLAIM_EMAIL", "not-an-email", "VAPID_CLAIM_EMAIL"),
    ("SENTRY_DSN", "invalid-dsn", "SENTRY_DSN"),
    ("ANTHROPIC_API_KEY", "changeme", "ANTHROPIC_API_KEY"),
])
def test_launch_rejects_missing_or_unsafe_configuration(launch_configuration, settings, setting, value, key):
    setattr(settings, setting, value)
    with pytest.raises(CommandError, match=key.replace("*", r"\*")):
        report("--launch")


def test_google_mail_scope_cannot_leak_into_login(launch_configuration, settings):
    settings.SOCIALACCOUNT_PROVIDERS["google"]["SCOPE"].append("https://www.googleapis.com/auth/gmail.readonly")
    with pytest.raises(CommandError, match="GOOGLE_OAUTH_CLIENT_ID"):
        report("--launch")


def test_google_login_client_stays_separate(launch_configuration, settings):
    settings.SOCIALACCOUNT_PROVIDERS["google"]["APP"]["client_id"] = settings.GMAIL_LIVE_CLIENT_ID
    with pytest.raises(CommandError, match="GOOGLE_OAUTH_CLIENT_ID"):
        report("--launch")


@pytest.mark.parametrize("options", [
    {"default_acl": "public-read"}, {"querystring_auth": False},
    {"custom_domain": "cdn.networkly.app"}, {"secret_key": "changeme"},
    {"endpoint_url": "http://s3.storage-provider.net"}, {"verify": False},
])
def test_storage_cannot_claim_private_configuration_with_public_or_insecure_options(launch_configuration, settings, options):
    settings.STORAGES["default"]["OPTIONS"].update(options)
    with pytest.raises(CommandError, match="MEDIA_S3"):
        report("--launch")


def test_arbitrary_remote_backend_does_not_establish_private_storage(launch_configuration, settings):
    settings.STORAGES["default"]["BACKEND"] = "storages.backends.s3.S3Storage"
    with pytest.raises(CommandError, match="MEDIA_S3"):
        report("--launch")


def test_capacity_includes_reserved_and_existing_accounts_and_can_be_full(launch_configuration):
    launch_configuration.return_value = {"used": 100, "limit": 100, "remaining": 0, "over_capacity": False}
    assert "0 warn · 0 fail" in report("--launch")
    launch_configuration.return_value = {"used": 101, "limit": 100, "remaining": 0, "over_capacity": True}
    with pytest.raises(CommandError, match="BetaInvitation"):
        report("--launch")


def test_capacity_read_error_fails_closed_without_leaking_details(launch_configuration):
    launch_configuration.side_effect = RuntimeError("postgres://user:secret@private-host/db")
    output = report("--launch", "--warn-only")
    assert "FAIL" in output and "RuntimeError" in output
    assert "postgres://" not in output and "private-host" not in output


def test_beta_default_report_skips_paid_setup_warnings(launch_configuration, settings):
    settings.STRIPE_SECRET_KEY = "sk_live_unused-in-beta"
    output = report("--warn-only")
    assert "not required for the free beta" in output
    assert "restricted key" not in output
    assert "no way to pay" not in output


def test_nonlaunch_keeps_optional_feature_warnings(launch_configuration, settings, monkeypatch):
    settings.BETA_ENABLED = False
    settings.GCAL_LIVE_ENABLED = False
    settings.ANTHROPIC_API_KEY = ""
    settings.STORAGES = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"}}
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "networkly_web.settings.development")
    output = report()
    assert "WARN  GCAL_LIVE_ENABLED" in output
    assert "0 fail" in output
    launch_configuration.assert_not_called()


def test_launch_output_never_prints_credentials(launch_configuration, settings):
    output = report("--launch")
    values = [settings.SECRET_KEY, settings.GMAIL_LIVE_CLIENT_ID, settings.GMAIL_LIVE_CLIENT_SECRET,
              settings.GMAIL_LIVE_TOKEN_KEY, settings.EMAIL_HOST_PASSWORD, settings.VAPID_PRIVATE_KEY,
              settings.ANTHROPIC_API_KEY, settings.SENTRY_DSN,
              settings.STORAGES["default"]["OPTIONS"]["secret_key"]]
    assert all(value not in output for value in values)
