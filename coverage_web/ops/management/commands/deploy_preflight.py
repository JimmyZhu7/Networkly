"""Read-only deployment configuration checks, not an end-to-end service test.

    python manage.py deploy_preflight
    python manage.py deploy_preflight --warn-only   # never exit non-zero
    python manage.py deploy_preflight --launch      # invited free beta gate

`manage.py check --deploy` already tells you whether Django's own security
settings are on. It cannot tell you the six things that actually broke a
first Blueprint apply of THIS app, because every one of them is about
whether a value exists rather than what it is set to: an unset
DJANGO_ALLOWED_HOSTS (the service never boots), a /healthz that 301s under
the SSL redirect (the health check never goes green), a Gmail Live worker
with no credentials (Render restarts it in a loop), crons that start before
the first migrate (tracebacks on missing tables), and SITE_URL/STRIPE_*
absent from render.yaml entirely (digest links pointing at localhost, no way
to pay). This command is that list, as checks.

IT NEVER PRINTS A VALUE. Every line names a KEY and a verdict — set, blank,
placeholder — and nothing else. This is meant to be run in a deploy shell
and pasted into a chat window, and a preflight that leaks the secret it was
checking is worse than no preflight. That rule is tested
(ops/tests/test_deploy_preflight.py).

IT NEVER INVENTS ONE EITHER. A key holding `changeme` is reported as a
placeholder, not quietly treated as configured and not silently replaced
with something plausible. "Not set" and "set to the example value" are
different states and this command says which.

VERDICTS
  PASS  nothing to do.
  WARN  a feature is dark, and that is a choice with a consequence named on
        the line. A deploy full of WARNs is a valid deploy: this project's
        whole posture is that every optional integration no-ops rather than
        crashing (see settings/base.py). Never exits non-zero.
  FAIL  this deploy will not work. Exits non-zero unless --warn-only.
"""

from __future__ import annotations

import os
from ipaddress import ip_address
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor

PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"

#: Substrings that mark a value as an untouched example rather than a real
#: credential. Matched case-insensitively against the value, which is read
#: but never printed. Deliberately conservative — a false "placeholder" on a
#: real key is a confusing line, and a missed one is caught by the feature
#: being dark anyway.
_PLACEHOLDER_MARKERS = (
    "changeme", "change-me", "change_me", "placeholder", "your-", "your_",
    "yourdomain", "example.com", "replace-me", "replaceme", "insecure-dev-only",
    "xxxxx", "todo",
)


def _looks_like_placeholder(value: str) -> bool:
    lowered = (value or "").strip().lower()
    if not lowered:
        return False
    if lowered.startswith("<") and lowered.endswith(">"):
        return True
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def _configured(value) -> bool:
    return bool(str(value or "").strip()) and not _looks_like_placeholder(str(value))


def _https_origin(value) -> bool:
    """Syntactic public HTTPS origin check; no DNS or provider request."""
    try:
        parsed = urlsplit(value)
        host = parsed.hostname or ""
        if (parsed.scheme != "https" or not host or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in {"", "/"}
                or not _configured(host) or host.endswith((".localhost", ".local", ".test"))):
            return False
        # Accessing port also rejects malformed/out-of-range values.
        if parsed.port not in {None, 443}:
            return False
        try:
            return ip_address(host).is_global
        except ValueError:
            return "." in host
    except (TypeError, ValueError):
        return False


class Check:
    """One line of output: a verdict, the key(s) it is about, and what the
    verdict means for the deploy. `keys` is a tuple of NAMES; there is
    nowhere in this class to put a value, on purpose."""

    __slots__ = ("level", "keys", "message")

    def __init__(self, level: str, keys, message: str):
        self.level = level
        self.keys = (keys,) if isinstance(keys, str) else tuple(keys)
        self.message = message

    def render(self) -> str:
        return f"{self.level}  {', '.join(self.keys):<42} {self.message}"


class Command(BaseCommand):
    help = "Check this environment for the things that break a first deploy."
    launch = False

    def add_arguments(self, parser):
        parser.add_argument(
            "--launch", action="store_true",
            help="Require configured individual features for the invited free beta (no provider calls).",
        )
        parser.add_argument(
            "--warn-only", action="store_true",
            help="Print the report and exit 0 even when a check FAILs.",
        )

    def handle(self, *args, **opts):
        self.launch = opts["launch"]
        checks: list[Check] = []
        checks.append(self._settings_module())
        checks.append(self._secret_key())
        checks.append(self._allowed_hosts())
        checks.append(self._csrf_origins())
        checks.append(self._healthz_exempt())
        checks.extend(self._database())
        checks.append(self._redis())
        checks.append(self._site_url())
        checks.append(self._email())
        checks.append(self._google_login())
        checks.append(self._gmail_live())
        checks.append(self._google_calendar())
        checks.append(self._media_storage())
        checks.append(self._vapid())
        checks.append(self._sentry())
        checks.append(self._anthropic())
        from accounts.access import beta_enabled
        if self.launch or beta_enabled():
            checks.extend(self._beta_capacity())
        if self.launch:
            checks.append(self._launch_security())
            # These integrations are optional in a regular deployment, but
            # required for the founder's all-individual-features beta.
            for check in checks:
                if check.level == WARN:
                    check.level = FAIL
        checks.extend(self._stripe())

        self.stdout.write(
            "Configuration check only. No provider calls or delivery tests; "
            "a PASS does not verify OAuth consent, Google quota, funding, "
            "storage permissions, scheduled jobs or end-to-end operation.\n"
        )

        for check in checks:
            style = {
                PASS: self.style.SUCCESS,
                WARN: self.style.WARNING,
                FAIL: self.style.ERROR,
            }[check.level]
            self.stdout.write(style(check.render()))

        failed = [c for c in checks if c.level == FAIL]
        warned = [c for c in checks if c.level == WARN]
        self.stdout.write(
            f"\n{len(checks) - len(failed) - len(warned)} pass · "
            f"{len(warned)} warn · {len(failed)} fail"
        )
        if failed and not opts["warn_only"]:
            raise CommandError(
                f"{len(failed)} check(s) would break this deploy: "
                + ", ".join(k for c in failed for k in c.keys)
            )

    # -- individual checks -------------------------------------------------

    def _settings_module(self) -> Check:
        module = os.environ.get("DJANGO_SETTINGS_MODULE", "") or settings.SETTINGS_MODULE
        if module.endswith(".production"):
            return Check(PASS, "DJANGO_SETTINGS_MODULE", "production settings.")
        return Check(
            WARN, "DJANGO_SETTINGS_MODULE",
            "not production — this report describes the current environment, "
            "not the deployed one.",
        )

    def _secret_key(self) -> Check:
        key = getattr(settings, "SECRET_KEY", "") or ""
        if not key:
            return Check(FAIL, "DJANGO_SECRET_KEY", "blank — the app will not boot.")
        if _looks_like_placeholder(key):
            return Check(
                FAIL, "DJANGO_SECRET_KEY",
                "still the insecure dev key from settings/base.py. Render "
                "generates a real one (generateValue: true in render.yaml).",
            )
        return Check(PASS, "DJANGO_SECRET_KEY", "set.")

    def _allowed_hosts(self) -> Check:
        hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
        if not hosts:
            return Check(
                FAIL, "DJANGO_ALLOWED_HOSTS",
                "empty — every request 400s and production settings refuse to "
                "import. Set it, or run on a host that provides "
                "RENDER_EXTERNAL_HOSTNAME.",
            )
        if os.environ.get("DJANGO_ALLOWED_HOSTS", "").strip():
            source = "from DJANGO_ALLOWED_HOSTS"
        elif os.environ.get("RENDER_EXTERNAL_HOSTNAME", "").strip():
            source = "from the platform's RENDER_EXTERNAL_HOSTNAME"
        else:
            source = "from this settings module"
        return Check(PASS, "DJANGO_ALLOWED_HOSTS", f"{len(hosts)} host(s), {source}.")

    def _csrf_origins(self) -> Check:
        origins = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])
        if origins:
            return Check(PASS, "DJANGO_CSRF_TRUSTED_ORIGINS", f"{len(origins)} origin(s).")
        return Check(
            WARN, "DJANGO_CSRF_TRUSTED_ORIGINS",
            "empty — same-origin POSTs still pass behind the proxy header, "
            "but a custom domain will need this before its forms work.",
        )

    def _healthz_exempt(self) -> Check:
        """Render marks the service live on a 200 from /healthz. Behind
        SECURE_SSL_REDIRECT, a probe that does not send
        X-Forwarded-Proto: https gets a 301 instead and the deploy never
        goes green — the second thing on the audit's first-deploy list."""
        keys = ("SECURE_SSL_REDIRECT", "SECURE_REDIRECT_EXEMPT")
        if not getattr(settings, "SECURE_SSL_REDIRECT", False):
            return Check(PASS, keys, "SSL redirect off; /healthz cannot 301.")
        exempt = [str(p) for p in getattr(settings, "SECURE_REDIRECT_EXEMPT", []) or []]
        if any("healthz" in pattern for pattern in exempt):
            return Check(PASS, keys, "/healthz is exempt from the SSL redirect.")
        return Check(
            FAIL, keys,
            "/healthz is NOT exempt from the SSL redirect — the health check "
            "may 301 and the service may never go green.",
        )

    def _database(self) -> list[Check]:
        """Reachability first, then "has migrate run" — the two crons and
        the worker share this image with no pre-deploy step of their own, so
        a first apply can start them before the web service's
        preDeployCommand lands (docs/deploy.md §1)."""
        keys = ("DATABASE_URL",)
        connection = connections[DEFAULT_DB_ALIAS]
        try:
            connection.ensure_connection()
        except Exception as exc:  # noqa: BLE001 — the message is the check.
            return [Check(FAIL, keys, f"unreachable: {type(exc).__name__}.")]

        reachable = Check(PASS, keys, "reachable.")
        try:
            executor = MigrationExecutor(connection)
            targets = executor.loader.graph.leaf_nodes()
            plan = executor.migration_plan(targets)
        except Exception as exc:  # noqa: BLE001
            return [reachable, Check(FAIL, "migrations", f"could not be read: {type(exc).__name__}.")]

        if plan:
            return [reachable, Check(
                FAIL, "migrations",
                f"{len(plan)} unapplied — run `manage.py migrate` BEFORE any "
                "cron or worker starts, or they traceback on missing tables.",
            )]
        return [reachable, Check(PASS, "migrations", "all applied.")]

    def _redis(self) -> Check:
        if self.launch:
            cache = getattr(settings, "CACHES", {}).get("default", {})
            location = cache.get("LOCATION", "")
            locations = location if isinstance(location, (list, tuple)) else [location]
            if (cache.get("BACKEND") != "django.core.cache.backends.redis.RedisCache"
                    or not locations or not all(_configured(item) and str(item).startswith(("redis://", "rediss://")) for item in locations)):
                return Check(WARN, "REDIS_URL", "shared Redis cache backend and location must be configured; availability has not been tested.")
            return Check(PASS, "REDIS_URL", "shared Redis backend configured; connection and rate-limit behavior have not been tested.")
        if (os.environ.get("REDIS_URL", "") or "").strip():
            return Check(PASS, "REDIS_URL", "set; connection and shared rate-limit behavior have not been tested.")
        return Check(
            WARN, "REDIS_URL",
            "blank — the cache falls back to per-process memory, so allauth's "
            "login limits count once PER gunicorn worker and reset on every "
            "deploy. Configure the existing shared Upstash Redis URL on web and workers.",
        )

    def _site_url(self) -> Check:
        url = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
        if self.launch and not _https_origin(url):
            return Check(WARN, "SITE_URL", "a public HTTPS origin without credentials, path or query is required.")
        if not url:
            return Check(WARN, "SITE_URL", "blank — links built outside a request have no host.")
        if "localhost" in url or "127.0.0.1" in url:
            return Check(
                WARN, "SITE_URL",
                "still the local default — every digest and trial-ended email "
                "link would point at the reader's own machine.",
            )
        return Check(PASS, "SITE_URL", "origin configured; DNS, TLS and public reachability have not been tested.")

    def _email(self) -> Check:
        from accounts import trials as pro_trials

        if self.launch:
            backend = getattr(settings, "EMAIL_BACKEND", "")
            if backend in {"django.core.mail.backends.locmem.EmailBackend", "django.core.mail.backends.filebased.EmailBackend"}:
                return Check(WARN, ("EMAIL_URL", "DEFAULT_FROM_EMAIL"), "local-only email backend; configure an outbound relay and verified sender.")
            if backend == "django.core.mail.backends.smtp.EmailBackend":
                host = getattr(settings, "EMAIL_HOST", "")
                if (not _configured(host) or host in {"localhost", "127.0.0.1", "::1"}
                        or not (getattr(settings, "EMAIL_USE_TLS", False) or getattr(settings, "EMAIL_USE_SSL", False))
                        or not all(_configured(getattr(settings, key, "")) for key in ("EMAIL_HOST_USER", "EMAIL_HOST_PASSWORD"))):
                    return Check(WARN, ("EMAIL_URL", "DEFAULT_FROM_EMAIL"), "configure an authenticated TLS email relay; delivery has not been tested.")
        if pro_trials.email_is_configured():
            from email.utils import parseaddr

            sender = parseaddr(getattr(settings, "DEFAULT_FROM_EMAIL", ""))[1]
            if "@" not in sender or sender.rsplit("@", 1)[-1].lower() == "localhost" or _looks_like_placeholder(sender):
                return Check(WARN, ("EMAIL_URL", "DEFAULT_FROM_EMAIL"), "relay configured, but the sender is missing or a placeholder. Verify a sending domain and set its address.")
            return Check(PASS, ("EMAIL_URL", "DEFAULT_FROM_EMAIL"), "relay and sender configured; actual delivery has not been tested.")
        return Check(
            WARN, ("EMAIL_URL", "DEFAULT_FROM_EMAIL"),
            "blank — password resets and the weekly digest print to the "
            "service logs, nobody can self-serve a reset, and the trial-ended "
            "notice is the Settings banner alone.",
        )

    def _google_login(self) -> Check:
        keys = ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET")
        if self.launch:
            google = getattr(settings, "SOCIALACCOUNT_PROVIDERS", {}).get("google", {})
            app = google.get("APP", {})
            scopes = set(google.get("SCOPE", []))
            if not all(_configured(app.get(key)) for key in ("client_id", "secret")):
                return Check(WARN, keys, "login OAuth credentials are missing or placeholders in effective settings.")
            if (not {"openid", "email"}.issubset(scopes)
                    or not scopes.issubset({"openid", "email", "profile"})
                    or app["client_id"] == getattr(settings, "GMAIL_LIVE_CLIENT_ID", "")):
                return Check(WARN, keys, "use a separate login-only OAuth client with identity scopes; keep Gmail/Calendar consent separate.")
            return Check(PASS, keys, "separate login-only client configured; callback, consent and sign-in have not been tested.")
        values = [os.environ.get(k, "") for k in keys]
        if any(_looks_like_placeholder(v) for v in values):
            return Check(
                WARN, keys,
                "placeholder value(s) — treated as unset, so no Google button "
                "renders. Email/password sign-in still works.",
            )
        if all(v.strip() for v in values):
            return Check(PASS, keys, "set; callback, consent and sign-in have not been tested.")
        return Check(
            WARN, keys,
            "blank — the Google sign-in button is not rendered at all; "
            "email/password only.",
        )

    def _gmail_live(self) -> Check:
        from capture import gmail_live

        keys = ("GMAIL_LIVE_CLIENT_ID", "GMAIL_LIVE_CLIENT_SECRET", "GMAIL_LIVE_TOKEN_KEY")
        if self.launch:
            if not all(_configured(getattr(settings, key, "")) for key in keys):
                return Check(WARN, keys, "OAuth credentials or encryption key missing/placeholder in effective settings.")
            from cryptography.fernet import Fernet
            try:
                for key in settings.GMAIL_LIVE_TOKEN_KEY.split(","):
                    Fernet(key.strip().encode())
            except (TypeError, ValueError):
                return Check(WARN, keys, "token encryption key is malformed; existing token decryptability has not been tested.")
        if not self.launch and any(_looks_like_placeholder(os.environ.get(k, "")) for k in keys):
            return Check(WARN, keys, "placeholder value(s) — treated as unset.")
        if gmail_live.is_configured():
            return Check(
                PASS, keys,
                "configured; match credentials across Gmail/Calendar workers. "
                "API access, consent, callbacks and sync have not been tested.",
            )
        return Check(
            WARN, keys,
            "blank — no Connect button, and the gmail-live worker idles "
            "instead of polling (it will not crash-loop).",
        )

    def _stripe(self) -> list[Check]:
        from accounts.access import beta_enabled
        if beta_enabled():
            return [Check(PASS, ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"),
                          "not required for the free beta; new checkout is blocked by beta mode.")]
        from billing import stripe_gateway

        keys = ("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET")
        if not stripe_gateway.is_configured():
            return [Check(
                WARN, keys,
                "blank — credit top-ups are off and the webhook 400s cleanly. "
                "There is no way to pay for anything on this deploy.",
            )]
        out = [Check(PASS, keys, "set; checkout and webhook delivery still need a real test.")]
        secret = (getattr(settings, "STRIPE_SECRET_KEY", "") or "").strip()
        if not secret.startswith("rk_"):
            out.append(Check(
                WARN, "STRIPE_SECRET_KEY",
                "not a restricted key (rk_). Use one scoped to Checkout "
                "Sessions write and nothing else.",
            ))
        return out

    def _vapid(self) -> Check:
        from accounts import push

        keys = ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_CLAIM_EMAIL")
        if self.launch:
            from django.core.exceptions import ValidationError
            from django.core.validators import validate_email
            try:
                if not all(_configured(getattr(settings, key, "")) for key in keys):
                    raise ValueError
                validate_email(settings.VAPID_CLAIM_EMAIL)
            except (ValidationError, ValueError):
                return Check(WARN, keys, "configure a non-placeholder keypair and contact email; browser subscription and delivery have not been tested.")
        if push.is_configured():
            return Check(PASS, keys, "configured; browser subscription and actual push delivery have not been tested.")
        return Check(
            WARN, keys,
            "blank — the Settings push toggle is unavailable and the "
            "push-alerts cron no-ops. `manage.py generate_vapid_keys` prints "
            "a pair; no third-party service and no cost.",
        )

    def _sentry(self) -> Check:
        dsn = getattr(settings, "SENTRY_DSN", "")
        if not self.launch:
            dsn = dsn or os.environ.get("SENTRY_DSN", "")
        if self.launch and _configured(dsn):
            try:
                parsed = urlsplit(dsn)
                valid = parsed.scheme == "https" and parsed.hostname and parsed.username and parsed.path.strip("/")
            except ValueError:
                valid = False
            if not valid:
                return Check(WARN, "SENTRY_DSN", "configure a valid HTTPS project DSN; receipt of errors has not been tested.")
        if _configured(dsn):
            from importlib.util import find_spec

            if find_spec("sentry_sdk") is None:
                return Check(WARN, "SENTRY_DSN", "set, but sentry-sdk is not installed; errors are not reported.")
            return Check(PASS, "SENTRY_DSN", "DSN and SDK present; verify receipt of a test event in production.")
        return Check(
            WARN, "SENTRY_DSN",
            "blank — no error monitoring. Tracebacks still reach stderr "
            "(settings/base.py's LOGGING block).",
        )

    def _anthropic(self) -> Check:
        if _configured(getattr(settings, "ANTHROPIC_API_KEY", "")):
            return Check(PASS, "ANTHROPIC_API_KEY", "set; model access, balance and responses have not been tested.")
        return Check(
            WARN, "ANTHROPIC_API_KEY",
            "blank — the advisor, autopilot and AI extraction all no-op.",
        )

    def _google_calendar(self) -> Check:
        from capture import gcal_live

        if not getattr(settings, "GCAL_LIVE_ENABLED", False):
            return Check(WARN, "GCAL_LIVE_ENABLED", "off — Google Calendar connection is unavailable; manual events and calendar export still work.")
        if not gcal_live.is_configured():
            return Check(WARN, "GCAL_LIVE_ENABLED", "enabled but OAuth credentials are incomplete; configure the separate calendar consent and gcal_sync job.")
        return Check(PASS, "GCAL_LIVE_ENABLED", "connection configured; consent, callback and scheduled gcal_sync still need verification.")

    def _media_storage(self) -> Check:
        config = getattr(settings, "STORAGES", {}).get("default", {})
        backend = config.get("BACKEND", "")
        if self.launch:
            options = config.get("OPTIONS", {})
            required = ("bucket_name", "endpoint_url", "region_name", "access_key", "secret_key")
            if (backend != "core.storage.PrivateMediaStorage"
                    or not all(_configured(options.get(key)) for key in required)
                    or not _https_origin(options.get("endpoint_url", ""))
                    or options.get("default_acl") is not None
                    or options.get("querystring_auth") is not True
                    or options.get("custom_domain") or options.get("location")
                    or options.get("use_ssl") is not True or options.get("verify") is not True):
                return Check(WARN, ("STORAGES", "MEDIA_ROOT", "MEDIA_S3_*"), "configure the shipped private HTTPS object storage backend; local disk or an arbitrary backend does not establish private durable uploads.")
            return Check(PASS, ("STORAGES", "MEDIA_ROOT", "MEDIA_S3_*"), "private object storage configured; bucket policy, credentials, upload access and persistence have not been tested.")
        if backend == "django.core.files.storage.FileSystemStorage":
            return Check(WARN, "STORAGES, MEDIA_ROOT", "uploads use the local filesystem. On ephemeral hosts, configure durable storage before accepting avatars or uploads.")
        return Check(PASS, "STORAGES, MEDIA_ROOT", "custom storage configured; persistence and private access still need verification.")

    def _beta_capacity(self) -> list[Check]:
        from accounts.access import beta_enabled
        from accounts.beta import capacity_status

        if not beta_enabled():
            return [Check(FAIL, "BETA_ENABLED", "launch requires the free, invitation-only beta with all individual features; enterprise is outside this release.")]
        keys = ("BETA_ENABLED", "BETA_MAX_USERS", "BetaInvitation")
        try:
            configured_limit = int(getattr(settings, "BETA_MAX_USERS", 100))
            status = capacity_status()
        except Exception as exc:  # Database/configuration errors never expose values.
            return [Check(FAIL, keys, f"invitation capacity could not be checked: {type(exc).__name__}.")]
        if not 1 <= configured_limit <= 100 or not 1 <= status["limit"] <= 100 or status["over_capacity"] or status["used"] > status["limit"]:
            return [Check(FAIL, keys, "invitation capacity must be 1–100 and current reserved/consumed seats must fit within it.")]
        return [Check(PASS, keys, "free invited beta enabled; local reserved/consumed seats fit the configured ceiling of at most 100. Google project audience and lifetime quota require separate verification.")]

    def _launch_security(self) -> Check:
        from django.http.request import validate_host

        keys = ("DEBUG", "SECURE_SSL_REDIRECT", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE", "DJANGO_ALLOWED_HOSTS", "DJANGO_CSRF_TRUSTED_ORIGINS")
        origin = (getattr(settings, "SITE_URL", "") or "").rstrip("/")
        hosts = list(getattr(settings, "ALLOWED_HOSTS", []) or [])
        origins = list(getattr(settings, "CSRF_TRUSTED_ORIGINS", []) or [])
        secure = all(getattr(settings, key, False) for key in ("SECURE_SSL_REDIRECT", "SESSION_COOKIE_SECURE", "CSRF_COOKIE_SECURE"))
        if (getattr(settings, "DEBUG", False) or not secure or not _https_origin(origin)
                or "*" in hosts or not validate_host(urlsplit(origin).hostname or "", hosts)
                or origin not in origins or not all(_https_origin(item) for item in origins)):
            return Check(FAIL, keys, "require DEBUG off, HTTPS redirects and secure cookies, with the canonical HTTPS origin covered by explicit allowed hosts and trusted origins.")
        return Check(PASS, keys, "production HTTPS and host settings configured; deployed redirects, TLS and authenticated forms have not been tested.")
