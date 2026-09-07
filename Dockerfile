# Portable image for Networkly's web service — works on Render (Docker env),
# Fly.io, or any container host. Uses uv for fast, locked installs.
FROM python:3.13-slim

# uv from the official distroless image (pinned minor).
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /uvx /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DJANGO_SETTINGS_MODULE=networkly_web.settings.production

WORKDIR /app

# 0) Postgres client tools, so `manage.py backup_db` can run INSIDE this
#    image instead of only on a laptop that happens to have Homebrew's
#    Postgres. That command shells out to `pg_dump`, and this image had no
#    Postgres client at all — which made the one scheduled backup the deploy
#    could plausibly own impossible to schedule, and left the runbook telling
#    an operator to dump production by hand from a trusted host.
#
#    MAJOR VERSION 18, FROM PGDG, NOT DEBIAN'S DEFAULT. `pg_dump` refuses a
#    server newer than itself ("server version 18.x; pg_dump version 17.x")
#    — it is not a warning, it is a non-zero exit and no dump. Debian slim's
#    own `postgresql-client` tracks the distribution's release, which is
#    behind 18, so the distribution package would install cleanly and then
#    fail against the real database. apt.postgresql.org publishes a
#    versioned package per major, which is the only way to pin the client to
#    the server.
#
#    The repository codename is read from the base image's own
#    /etc/os-release rather than hardcoded, so a future `python:3.13-slim`
#    rebased onto the next Debian keeps working instead of pointing at a
#    suite that no longer matches the userland.
#
#    Kept as ONE layer with its own `apt-get purge` and list cleanup: curl
#    exists only to fetch the signing key and must not survive into the
#    running image. Costs roughly 30MB installed (libpq5 +
#    postgresql-client-common + the client binaries) against an image whose
#    Playwright tier alone is ten times that.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    install -d -m 0755 /usr/share/postgresql-common/pgdg; \
    curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc; \
    codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${codename}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-client-18; \
    apt-get purge -y --auto-remove curl; \
    rm -rf /var/lib/apt/lists/*; \
    pg_dump --version; \
    pg_restore --version

# 1) Dependency layer — copy only what uv needs to resolve, so app-code edits
#    don't bust the cached install.
COPY pyproject.toml uv.lock ./
COPY networkly_web/pyproject.toml networkly_web/
COPY networkly_domain/pyproject.toml networkly_domain/
COPY networkly_connectors/pyproject.toml networkly_connectors/
COPY networkly_domain/ networkly_domain/
COPY networkly_connectors/ networkly_connectors/
RUN uv sync --frozen --no-dev --package networkly-web

# 1b) Browser tier: the Beisen connector (CICC) drives headless Chromium via
#     Playwright during scrapes/refreshes. Install the browser + its system
#     libs so the scrape cron can run it. (~300MB; the web service itself
#     never launches a browser, but one image serves both roles on Render.)
RUN uv run --package networkly-web playwright install --with-deps chromium

# 2) App code.
COPY . .

# 3) Collect static into STATIC_ROOT for WhiteNoise. Dummy values for the two
#    settings production.py requires with no fallback (SECRET_KEY,
#    ALLOWED_HOSTS) let the management command run at build time without real
#    secrets. Neither is used for anything at build time; ALLOWED_HOSTS is
#    unused by collectstatic. Nothing here reaches a request path.
RUN DJANGO_SECRET_KEY=build-only DJANGO_ALLOWED_HOSTS=localhost \
    uv run --package networkly-web python networkly_web/manage.py collectstatic --noinput

EXPOSE 8000

# $PORT is provided by the host (Render/Fly). Migrations run as a separate
# release step (see render.yaml / the deploy checklist), NOT here, so a
# rollback never half-applies a migration.
CMD ["sh", "-c", "uv run --package networkly-web gunicorn networkly_web.wsgi:application --chdir networkly_web --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 60 --access-logfile - --error-logfile -"]
