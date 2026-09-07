# Invitation beta release runbook

Prepared 2026-09-06. This is an execution checklist, not production evidence.
The current setup record is [product readiness](product-readiness-2026-09-06.md).
The beta is free, invitation-only, capped at 100 users, with all individual
features. Enterprise and paid checkout are outside this release.

## Before activation

Keep services suspended until the founder authorizes deployment and its cost.
Record the reviewed Git revision, previous deployed revision, operator and UTC
time. Do not deploy the current uncommitted workspace as an unidentified release.
Run CI for that revision, including migration drift detection and the full pytest
suite. `.github/workflows/ci.yml` runs on `main`, on `codex/**` branches and on
`workflow_dispatch`, so the release branch is gated without being merged first;
use Actions → CI → Run workflow to run it against a named revision on demand.
That workflow has two jobs and both must be green. `test` is the suite. `docker`
builds the deploy image on a hosted runner and then asserts `pg_dump` and
`pg_restore` exist inside it at major version 18 or above — the release machine
has no Docker, so this is the only place the image is validated before Render
builds it. `.github/workflows/pip-audit.yml` runs the CVE scan on the same
triggers plus a weekly schedule. CI success does not establish provider
acceptance.

Reconcile `render.yaml` against existing services before applying it. Preserve
the existing database, Upstash cache and private media bucket. Review any new
Calendar sync and assistant reconciliation services and their cost. Match beta,
OAuth, encryption and shared-cache settings across the relevant processes.
Keep background jobs suspended until web migrations finish. Do not rotate token
encryption keys during this release. Preserve the ordered key ring securely.

Two Blueprint facts require reading the dashboard rather than this repository.
Record both before applying.

- `coverage-db` has no `postgresMajorVersion` in `render.yaml`, deliberately.
  The key is immutable after creation and the database predates this file, so
  its real version is not knowable here. Read "PostgreSQL version" on the
  `coverage-db` page. Do not add a pin to match it without a separate decision;
  an incorrect pin is the one edit in this file that could turn an apply into a
  data event. The number also bounds the backup client: the image ships
  `pg_dump` 18, which dumps any server at 18 or below and refuses one above.
- Plan names. `plan: basic-256mb` (database) and `plan: starter` (services) are
  current and were verified against Render's own Blueprint JSON Schema at
  `https://render.com/schema/render.yaml.json` on 2026-09-06, where both appear
  in the `postgresPlan` and `serverPlan`/`cronPlan` enumerations alongside the
  newer CPU-and-RAM slugs. Confirm the dashboard reports the same tier for the
  live services; do not change a tier as part of this release.

`coverage-db-backup` is new in this Blueprint and is **not part of this
release**. Suspend it immediately after the apply, along with everything else,
and leave `BACKUP_S3_BUCKET` blank. With that variable blank the command is a
complete no-op even if the service is resumed by accident. See `docs/deploy.md`
section 9 for what arming it requires.

`coverage-weekly-digest` is now a **daily** cron running
`send_weekly_digest --spread`, not a Monday one. Each student still receives one
digest a week on a fixed weekday; the change exists because 100 recipients in a
single tick consumes an entire 100-a-day free mail allowance and starves the
confirmation and reset mail that students are waiting on. Its expected interval
in `/ops/health/cron/` is one day, not seven.

In the production environment, after deployment and migrations:

```bash
uv run --package networkly-web python networkly_web/manage.py check --deploy --fail-level WARNING
uv run --package networkly-web python networkly_web/manage.py migrate --check
uv run --package networkly-web python networkly_web/manage.py deploy_preflight --launch
```

All three must exit zero; investigate warnings rather than suppressing them.
One warning is already suppressed, by a decision recorded in
`settings/production.py` and in `docs/deploy.md` section 5b: `security.W021`,
which Django raises whenever HSTS preload is off. Preload is off permanently and
on purpose, so that warning would otherwise have made this gate impossible to
pass and the gate itself worthless. The suppression is scoped to that one check
id; anything else this command reports is a finding, not a known state. Verified
against placeholder values on 2026-09-06: `System check identified no issues (1
silenced)`.
The preflight checks configuration and database state without provider calls.
Complete the fresh-account acceptance in the readiness document, with authorized
test recipients and AI budget, before inviting the first 5–10 testers.

## Runtime verification

Check the canonical HTTPS origin and its `/healthz` response. `/healthz` does
not query the database. Verify authenticated pages and forms separately.
Resume required jobs only after migrations, then collect successful production
runs for each job in the readiness document's Required Job Map. Running these
jobs manually can send mail/push, invoke AI or modify user data; a command's
existence is not authorization to execute it on real accounts.

Use staff-only `/ops/health/cron/` for freshness and `/ops/health/gmail/` for
connections requiring attention. The cron endpoint includes legacy/optional
jobs, so inspect each required row rather than treating optional watch renewal
as required for polling. It reports last success; review newer failures too.
The following read-only command prints timestamps and status without user data:

```bash
uv run --package networkly-web python networkly_web/manage.py shell <<'PY'
from ops.models import JobRun
from ops.tracking import EXPECTED_INTERVALS
for name in sorted(EXPECTED_INTERVALS):
    rows = JobRun.objects.filter(name=name).order_by('-finished_at', '-started_at')
    latest = rows.values('status', 'started_at', 'finished_at').first()
    success = rows.filter(status='success').values('finished_at').first()
    print(name, {'latest': latest, 'last_success': success})
PY
```

Confirm an authorized synthetic staging error reaches Sentry and its selected
recipient. Prove missed-job alerts reach an operator; success rows and a saved
Sentry DSN do not prove missed executions will alert. Record recipient, test time,
and response owner without exposing DSNs or heartbeat URLs.

Each background service has an optional `HEALTHCHECK_URL_<JOB>` environment
slot in the Blueprint, using uppercase job names with underscores. The Gmail
poll worker uses `HEALTHCHECK_URL_GMAIL_POLL` on `coverage-gmail-live`;
Calendar, autopilot and assistant recovery use `HEALTHCHECK_URL_GCAL_SYNC`,
`HEALTHCHECK_URL_AUTOPILOT` and `HEALTHCHECK_URL_ASSISTANT_RECONCILE` on their
respective services. Empty values disable pings and are not launch-preflight
requirements. Store URLs only in local/provider environment settings. Configure
the monitor's cadence, grace window and notification destination separately;
keep checks paused/unstarted until the corresponding hosting service resumes.
Local development/test settings ignore all external heartbeat URLs, including
ones saved in `.env`, so local jobs cannot report production success.

## Backup and recovery

Before migrations, take a production snapshot to private durable storage outside
the web container. The application image now installs the PostgreSQL 18 client
(`pg_dump`, `pg_restore`) from the PGDG repository, and CI asserts they are
present in the built image, so this no longer requires a separate operator host
with client tools — but it still requires that the client's major version be at
least the server's, which is why the dashboard reading above matters. Load
connection settings securely; do not paste database URLs into logs or command
arguments. Confirm that the selected settings target the intended production
database before proceeding.

```bash
uv run --package networkly-web python networkly_web/manage.py backup_db --dest "${COVERAGE_BACKUP_DIR:?Set a private durable backup directory}" --keep 14
```

Set `COVERAGE_BACKUP_DIR` to a private durable directory before running. A
container filesystem is not one: on Render it is discarded with the container,
so a snapshot taken there and left there is not a backup. Fourteen is a snapshot
count, not a time-based retention guarantee.

The Blueprint now *defines* a scheduled backup (`coverage-db-backup`, 04:15 UTC,
`backup_db --require-s3`) but does not activate one. It stays suspended and its
`BACKUP_S3_BUCKET` stays blank for this release; with the bucket blank it takes
no snapshot at all rather than taking one it would throw away. Assign a backup
owner, schedule, retention policy and failure alert as a separate, funded
decision, and add the job to `ops.tracking.EXPECTED_INTERVALS` in the same change
that resumes it. Back up private avatars and the encryption key ring separately.
A database dump alone cannot restore missing avatars or decrypt lost keys.

Restore only into a newly created, empty drill database on an approved recovery
host. Set `COVERAGE_RESTORE_DB` to that database's name and
`COVERAGE_BACKUP_FILE` to the selected dump. Supply host/user/password using a
private libpq service or environment, never a password-bearing command argument.

```bash
createdb "${COVERAGE_RESTORE_DB:?Set a new drill database name}" &&
pg_restore --exit-on-error --no-owner --no-privileges --dbname "$COVERAGE_RESTORE_DB" "${COVERAGE_BACKUP_FILE:?Select the dump to restore}"
```

If `createdb` fails, stop: do not restore into a pre-existing database. Record
dump checksum, server/client versions, start/end time and migration state.
Compare every table's row counts and contents with the same source snapshot;
changing live counts are not a reliable comparator. Verify sequence-backed
inserts, login, ownership boundaries and encrypted-token decryptability in the
isolated environment without running outbound jobs. The September 6 local
restore report predates newer migrations and must be repeated for production.

## Rollback

Stop new invitations and pause background writes if a release damages data or
critical flows. Record the failure and preserve logs with private payloads
redacted. Redeploy the recorded previous revision only after confirming it is
compatible with the migrated schema. Reverting code does not revert migrations.
For incompatible schema or data damage, restore beside the live database,
verify the recovery, then perform an explicitly approved connection switch.
Never merge a dump into the live database or improvise reverse migrations.

Keep the release pending until production acceptance, job execution, alert
delivery and recovery evidence are attached to the readiness checklist.
