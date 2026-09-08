"""render.yaml — the four facts about the deploy blueprint that code
elsewhere depends on being true.

WHY TESTED AT ALL. Every other file in this repo has a test that fails when
someone undoes its fix. `render.yaml` had none, and three of the defects
this suite now covers were defects IN it: two crons in the wrong order, two
crons on the same tick, and a cache that was never provisioned. Each is a
one-line edit away from coming back, and none of them would fail anything.

PARSED BY HAND, not with PyYAML: this project has no YAML dependency (see
`grep -rn "import yaml"` — zero hits, the firm seeds are read by the
connectors package's own reader) and adding one so a test can read a config
file is a poor trade. The parse below is deliberately dumb — it finds
`name:`/`schedule:`/`key:` lines and nothing else — and it asserts on the
handful of scalars this file cares about. A structural change to the
blueprint that broke this parse would fail loudly, which is the correct
outcome for a file whose shape these tests are about.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# networkly_web/ops/tests/ -> repo root.
RENDER_YAML = Path(__file__).resolve().parents[3] / "render.yaml"


@pytest.fixture(scope="module")
def blueprint() -> str:
    assert RENDER_YAML.exists(), f"render.yaml not found at {RENDER_YAML}"
    return RENDER_YAML.read_text()


def _blocks(text: str) -> dict[str, str]:
    """`name:` -> everything until the next `- type:` line. Good enough to
    ask "does this service mention that key", which is all these tests do."""
    blocks: dict[str, str] = {}
    current = None
    for line in text.splitlines():
        if re.match(r"\s*-\s+type:\s", line):
            current = None
        match = re.match(r"\s*name:\s*(\S+)\s*$", line)
        if match and current is None:
            current = match.group(1)
            blocks[current] = ""
            continue
        if current:
            blocks[current] += line + "\n"
    return blocks


def _schedule(text: str, service: str) -> str:
    block = _blocks(text)[service]
    match = re.search(r'schedule:\s*"([^"]+)"', block)
    assert match, f"{service} has no schedule"
    return match.group(1)


# ---------------------------------------------------------------------------
# T2 — the daily 05:00 block's ordering
# ---------------------------------------------------------------------------
def test_trial_expiry_runs_before_the_watch_renewal(blueprint):
    """These ran the other way round — renew 05:00, expire 05:30 — so a
    trial that ended overnight got one last 7-day watch renewal half an hour
    before the plan flip meant to stop it. `gmail_watch_renew` renews every
    `plan="pro"` connection, so the job that DECIDES who is Pro has to land
    before the job that ACTS on it."""
    expire = _schedule(blueprint, "coverage-pro-trial-expire")
    renew = _schedule(blueprint, "coverage-gmail-watch-renew")

    expire_minute, expire_hour = expire.split()[0], expire.split()[1]
    renew_minute, renew_hour = renew.split()[0], renew.split()[1]

    assert expire_hour == renew_hour == "5"
    assert int(expire_minute) < int(renew_minute), (
        f"trial-expire ({expire}) must run before watch-renew ({renew})"
    )


# ---------------------------------------------------------------------------
# T4 — the two credit-spending crons must not share a tick
# ---------------------------------------------------------------------------
def test_the_two_credit_clamping_crons_are_offset(blueprint):
    """Both pre-clamp their work against the same student's balance
    (billing.credits.affordable_*). The real fix is at the debit
    (`_spend_clamped` re-runs the clamp under a row lock); this offset is
    belt and braces, and it is only belt and braces if it is actually there."""
    backfill = _schedule(blueprint, "coverage-gmail-backfill")
    autopilot = _schedule(blueprint, "coverage-autopilot")

    assert backfill != autopilot, (
        "gmail-backfill and autopilot are back on the same tick"
    )
    # Both must still be every five minutes — a student is watching each of
    # them, and the offset is not licence to slow either down.
    assert backfill.startswith("*/5")
    assert autopilot.split()[0].endswith("/5")


# ---------------------------------------------------------------------------
# The shared cache
# ---------------------------------------------------------------------------
def test_external_tls_cache_is_preserved_without_provisioning_another(blueprint):
    """The approved Upstash URL lives in Render, not in the repository."""
    assert "type: keyvalue" not in blueprint
    assert "name: coverage-kv" not in blueprint
    block = _blocks(blueprint)["coverage-web"]
    assert re.search(r"key: REDIS_URL\s+sync: false", block)
    assert "Upstash" in block
    assert "rediss://" in block


def test_worker_inherits_the_web_services_shared_cache(blueprint):
    block = _blocks(blueprint)["coverage-gmail-live"]
    assert re.search(
        r"key: REDIS_URL\s+fromService:\s+type: web\s+name: coverage-web\s+envVarKey: REDIS_URL",
        block,
    )


def test_all_background_production_services_inherit_error_monitoring(blueprint):
    services = {
        name: block for name, block in _blocks(blueprint).items()
        if "value: networkly_web.settings.production" in block
        and name != "coverage-web"
    }
    assert services
    for name, block in services.items():
        assert re.search(
            r"key: SENTRY_DSN\s+fromService:\s+type: web\s+name: coverage-web\s+envVarKey: SENTRY_DSN",
            block,
        ), f"{name} must report errors to the configured project"


def test_each_tracked_job_has_an_optional_heartbeat_on_its_own_service(blueprint):
    from ops.tracking import EXPECTED_INTERVALS

    blocks = _blocks(blueprint)
    for job in EXPECTED_INTERVALS:
        service = "coverage-" + ("gmail-live" if job == "gmail-poll" else job)
        key = "HEALTHCHECK_URL_" + job.upper().replace("-", "_")
        assert re.search(rf"key: {key}\s+sync: false", blocks[service]), service
        assert blueprint.count(f"key: {key}\n") == 1


@pytest.mark.parametrize("key", ["VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_CLAIM_EMAIL"])
def test_push_cron_inherits_the_web_push_credentials(blueprint, key):
    block = _blocks(blueprint)["coverage-push-alerts"]
    assert re.search(
        rf"key: {key}\s+fromService:\s+type: web\s+name: coverage-web\s+envVarKey: {key}",
        block,
    )


# ---------------------------------------------------------------------------
# T7 — the keys that were read by code and absent from this file
# ---------------------------------------------------------------------------
def test_site_url_is_declared_on_the_web_service(blueprint):
    """Absent entirely, so every weekly-digest link pointed at
    http://localhost:8000 — base.py's dev default."""
    assert "key: SITE_URL" in _blocks(blueprint)["coverage-web"]


def test_site_url_and_email_are_declared_on_the_trial_expiry_cron(blueprint):
    """That cron now sends the trial-ended email, so it needs a relay and a
    host for the link in it."""
    block = _blocks(blueprint)["coverage-pro-trial-expire"]

    assert "key: EMAIL_URL" in block
    assert "key: SITE_URL" in block


@pytest.mark.parametrize("service", ["coverage-weekly-digest", "coverage-pro-trial-expire"])
def test_email_jobs_have_a_sender_and_the_public_web_origin(blueprint, service):
    block = _blocks(blueprint)[service]
    for key in ("EMAIL_URL", "DEFAULT_FROM_EMAIL"):
        assert re.search(
            rf"key: {key}\s+fromService:\s+type: web\s+name: coverage-web\s+envVarKey: {key}",
            block,
        )
    assert re.search(
        r"key: SITE_URL\s+fromService:\s+type: web\s+name: coverage-web\s+envVarKey: SITE_URL",
        block,
    ), "A cron has no public hostname to use for links in email."


def test_reserved_resend_key_does_not_configure_delivery(blueprint):
    block = _blocks(blueprint)["coverage-web"]
    assert re.search(r"key: RESEND_API_KEY\s+sync: false", block)
    assert re.search(r"key: EMAIL_URL\s+sync: false", block)


def test_gmail_rescan_worker_has_model_credentials(blueprint):
    block = _blocks(blueprint)["coverage-gmail-backfill"]
    assert re.search(
        r"key: ANTHROPIC_API_KEY\s+fromService:\s+type: web\s+name: coverage-web\s+envVarKey: ANTHROPIC_API_KEY",
        block,
    ), "Rescan residue classification runs in this worker, not the web process."


@pytest.mark.parametrize("service", [
    "coverage-gmail-live", "coverage-gmail-backfill", "coverage-gmail-watch-renew",
])
def test_gmail_workers_share_oauth_and_token_encryption_with_web(blueprint, service):
    block = _blocks(blueprint)[service]
    for key in ("GMAIL_LIVE_CLIENT_ID", "GMAIL_LIVE_CLIENT_SECRET", "GMAIL_LIVE_TOKEN_KEY"):
        assert re.search(
            rf"key: {key}\s+fromService:\s+type: web\s+name: coverage-web\s+envVarKey: {key}",
            block,
        ), f"{service} must use web's {key} to read stored mailbox connections"


def test_autopilot_inherits_model_credentials(blueprint):
    block = _blocks(blueprint)["coverage-autopilot"]
    assert re.search(
        r"key: ANTHROPIC_API_KEY\s+fromService:\s+type: web\s+name: coverage-web\s+envVarKey: ANTHROPIC_API_KEY",
        block,
    )


def test_calendar_sync_is_scheduled_and_shares_the_explicit_feature_gate(blueprint):
    block = _blocks(blueprint)["coverage-gcal-sync"]
    assert "gcal_sync --apply" in block
    assert _schedule(blueprint, "coverage-gcal-sync").split()[0].endswith("/5")
    for key in ("GCAL_LIVE_ENABLED", "GMAIL_LIVE_CLIENT_ID", "GMAIL_LIVE_CLIENT_SECRET", "GMAIL_LIVE_TOKEN_KEY"):
        assert f"envVarKey: {key}" in block


# ---------------------------------------------------------------------------
# The Blueprint's own shape
# ---------------------------------------------------------------------------
def test_no_env_var_value_is_a_bare_yaml_boolean(blueprint):
    """`value: true` is a BOOLEAN to a YAML parser, and Render's Blueprint
    schema (envVarFromKeyValue) types `value` as string-or-number and nothing
    else — so the file was invalid, at `BETA_ENABLED` of all keys: the one
    that decides whether the invited beta's admission gate is on at all. The
    quoted form reads identically to `env.bool`. Checked as a line pattern
    because this suite parses the blueprint by hand and has no YAML
    dependency; see this module's docstring."""
    offenders = [
        line.strip() for line in blueprint.splitlines()
        if re.match(r"\s*value:\s*(true|false|yes|no|on|off|True|False|~|null)\s*(#.*)?$", line)
    ]
    assert not offenders, f"quote these values: {offenders}"


# ---------------------------------------------------------------------------
# The daily mail budget
# ---------------------------------------------------------------------------
def test_the_digest_cron_spreads_the_roster_across_the_week(blueprint):
    """`0 13 * * 1` mailed every eligible account inside one minute. At the
    beta's cap of 100 students that is the whole of a 100-a-day free mail
    allowance spent on the digest, leaving nothing for the confirmation or
    reset somebody is waiting on — sends that fail at the provider, after the
    app has told the student to check their inbox."""
    schedule = _schedule(blueprint, "coverage-weekly-digest")
    assert schedule.split()[-1] == "*", (
        f"the digest is back on a single weekday ({schedule})"
    )
    assert "send_weekly_digest --spread" in _blocks(blueprint)["coverage-weekly-digest"], (
        "a daily cron without --spread mails the whole roster every day"
    )


# ---------------------------------------------------------------------------
# The backup cron — defined now, resumed only after payment
# ---------------------------------------------------------------------------
def test_backup_client_supports_the_pinned_database_major(blueprint):
    """A future server pin must not outrun pg_dump inside the deploy image."""
    database_section = blueprint.split("\nservices:", 1)[0]
    databases = re.split(r"(?m)^  - name: ", database_section)[1:]
    database = next(block for block in databases if block.splitlines()[0] == "coverage-db")
    pin = re.search(r'(?m)^    postgresMajorVersion: "(\d+)"\s*(?:#.*)?$', database)
    assert pin, "coverage-db needs an explicit, quoted major matching the verified instance"

    dockerfile = (RENDER_YAML.parent / "Dockerfile").read_text()
    clients = re.findall(
        r"(?m)^\s*apt-get install\b[^\n]*\bpostgresql-client-(\d+)\b", dockerfile,
    )
    assert len(clients) == 1, "The image must install one explicit PostgreSQL client major"
    assert int(clients[0]) >= int(pin.group(1)), (
        f"pg_dump {clients[0]} cannot back up PostgreSQL {pin.group(1)}"
    )


def test_the_backup_cron_cannot_run_without_a_bucket(blueprint):
    """Two locks, because Render's Blueprint schema has no `suspended:` key
    and a cron therefore cannot be declared dormant in this file. The service
    is suspended in the dashboard, AND `--require-s3` with a blank
    BACKUP_S3_BUCKET makes the command a complete no-op. The second lock is
    the one this file can hold."""
    block = _blocks(blueprint)["coverage-db-backup"]
    assert "backup_db --require-s3" in block
    assert re.search(r"key: BACKUP_S3_BUCKET\s+sync: false", block), (
        "the bucket is the off switch; a value here would arm the cron"
    )


def test_the_backup_cron_runs_before_the_daily_plan_flips(blueprint):
    backup = _schedule(blueprint, "coverage-db-backup")
    expire = _schedule(blueprint, "coverage-pro-trial-expire")
    minute, hour = backup.split()[0], backup.split()[1]
    assert int(hour) < int(expire.split()[1]), (
        f"the snapshot ({backup}) must land before the 05:00 block"
    )
    assert (int(hour), int(minute)) not in {(0, 0), (6, 0), (12, 0), (18, 0)}, (
        "clear of the scrape's marks"
    )


def test_the_backup_cron_borrows_storage_credentials_but_not_the_avatar_bucket(blueprint):
    """One object here is every row in the app. It does not belong in the
    same listing as media a request path can reach, so the bucket NAME is its
    own key while the endpoint and credentials are shared."""
    block = _blocks(blueprint)["coverage-db-backup"]
    for key in ("MEDIA_S3_ENDPOINT_URL", "MEDIA_S3_REGION_NAME",
                "MEDIA_S3_ACCESS_KEY_ID", "MEDIA_S3_SECRET_ACCESS_KEY"):
        assert re.search(
            rf"key: {key}\s+fromService:\s+type: web\s+name: coverage-web\s+envVarKey: {key}",
            block,
        ), f"the backup cron needs web's {key} to reach the object store"
    assert not re.search(r"key: BACKUP_S3_BUCKET\s+fromService", block), (
        "the backup bucket must not be inherited from the avatar bucket"
    )


@pytest.mark.parametrize("key", ["STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET"])
def test_stripe_keys_are_declared_even_though_they_are_blank(blueprint, key):
    """Declared while blank on purpose: a key typed into the dashboard but
    absent from this file is a key the next Blueprint apply can drop."""
    assert f"key: {key}" in _blocks(blueprint)["coverage-web"]
