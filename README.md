# Networkly

A recruiting workspace for students: find opportunities, keep track of applications,
and follow up with the people you meet.

Networkly connects a shared opportunities directory with a private contact CRM.
The Today page brings deadlines, outreach tasks, firm updates, and recent activity
together so students can decide what to do next.

## What You Can Do

- **Find roles:** search by firm, role, and city; filter opportunities and review personalized picks.
- **Track applications:** save roles, update application stages, and keep deadlines beside your contacts.
- **Build your network:** organize contacts and target firms, log conversations, and plan follow-ups.
- **Plan your week:** view recruiting dates and personal events in the calendar.
- **Connect your tools:** use Google sign-in, optional Gmail activity logging, and Calendar integration.
- **Get assistance:** use the contextual AI assistant, email digests, and device notifications.

The interface includes light and dark themes, responsive layouts, keyboard-accessible
controls, and reviewed company logos with initials as a fallback.

## Beta Scope and Status

The planned release is a **free, invitation-only beta for up to 100 users**, with
all individual features. Enterprise features and paid checkout are outside this release.

The application is implemented and undergoing release verification. It is **not yet
verified for public production use**. Hosting activation, domain and sending-email
configuration, legal operator details, and real production integration checks remain
launch gates. Automated tests do not prove email delivery or successful provider consent.

See the [release runbook](docs/beta-release-runbook.md) and
[deployment guide](docs/deploy.md) for configuration and acceptance steps.

## Architecture

Networkly uses Django, PostgreSQL, server-rendered templates, and htmx.
Python dependencies are managed with a uv workspace.

| Package | Responsibility |
| --- | --- |
| `networkly_web/` | Web application, authentication, private user data, integrations, and background commands |
| `networkly_domain/` | Shared recruiting and relationship logic |
| `networkly_connectors/` | Recruiting-source connectors and ingestion support |

The application packages and repository use the Networkly name.
Gmail access is read-only: it reads mail to log activity and cannot send, reply, or delete.
Provider credentials and local environment files must stay outside Git.

## Local setup

Prerequisites: [uv](https://docs.astral.sh/uv/) (manages Python 3.13 for you
— no separate Python install needed) and a local Postgres server. There is no
SQLite fallback anywhere in this project, by design (see
`docs/build-plan.md`, "1. Stack": concurrent writers — web + scrape worker +
inbound-mail webhook — is precisely SQLite's weak spot, and testing against a
different engine than production would defeat the point of choosing
Postgres).

```bash
# 1. Install all workspace packages' dependencies (Django, psycopg, allauth,
#    django-environ, htmx is vendored as a static file so nothing to install
#    there, plus pytest/pytest-django/pytest-cov). Plain `uv sync` alone only
#    installs the workspace root's own deps — `--all-packages` is required to
#    pull in networkly_web's (and later networkly_domain's/networkly_connectors')
#    dependencies too.
uv sync --all-packages

# 2. Create the local Postgres role + database matching the default
#    DATABASE_URL (postgres://coverage:coverage@localhost:5432/coverage).
#    Adjust if your local Postgres uses different admin access.
psql postgres -c "CREATE USER coverage WITH PASSWORD 'coverage' CREATEDB;"
createdb -O coverage coverage

# 3. Copy the env template and adjust anything that doesn't match your setup
#    (the DATABASE_URL default above matches step 2 as-is).
cp .env.example .env

# 4. Apply migrations.
cd networkly_web
uv run python manage.py migrate

# 5. Run the dev server.
uv run python manage.py runserver
# -> http://127.0.0.1:8000/         marketing home page
# -> http://127.0.0.1:8000/healthz  {"status": "ok"}

# 6. Run the test suite (from the repo root).
cd ..
uv run pytest
```

## Running the suite

**`uv run pytest` is the full test gate.** Runtime varies by machine and database load.
Do not run independent suites against the same test database. Use a unique test
database for each concurrent run; a separate worktree alone does not isolate it. Nothing below changes what a bare `pytest` runs — a default that
quietly skipped tests would mean "pytest passed" no longer means what every
commit in this repo has meant by it.

Two ways to make the inner loop shorter while you work. Both are opt-out, and
neither is a substitute for a full run before you commit:

```bash
# Same tests, four processes. xdist gives each worker its own database
# (test_coverage_gw0..gw3), so this does NOT reintroduce the two-runs-on-one-
# database contention that has caused mass failures here before.
uv run pytest -n 4

# The fast subset: everything except page renders and generated matrices.
uv run pytest -m "not slow and not stress"
```

The two markers are applied by SHAPE in the repo-root `conftest.py`, so
nothing has to be remembered when a test is added:

| marker | what carries it | why it is skippable |
|---|---|---|
| `stress` | any `test_stress_*.py` module | 4,006 of the 9,296 cases, 54 s — a generated matrix over one pure function; it inflates the count far more than the clock |
| `slow` | any test taking the `client` fixture | 1,369 tests, 251 s — full page renders with a fixture world built per test, which is where the suite's time actually goes |
| `live` | hand-written, `networkly_connectors` only | hits a real ATS over the network; deselected by its own conftest unless a network run is asked for |

`networkly_web/core/tests/test_suite_hygiene.py` pins all three: an
unregistered marker is a warning rather than an error, so it is the kind of
thing that decays silently.

## Verifying a change by hand — use the demo account, not the shared tables

The `coverage` database above is a **shared, standing dev database** — every
worktree on a given machine points at the same one by default (only the
pytest database name is per-worktree, see `settings/base.py`'s Database
section), and it is also where the founder's own account lives. `uv run
pytest` / `pytest networkly_web/<app> -q` never touch it — they run against a
throwaway `test_coverage_*` database instead. Anything driven through a
running `manage.py runserver` or typed into `manage.py shell`, though, lands
in the real one.

That distinction has produced real leakage more than once: a `Firm` row with
a blank slug from a stray `manage.py shell` insert (see `Firm.slug`'s
docstring), four "ZZZ Smoke Test..." contacts left in the founder's own CRM
by smoke runs (`crm/management/commands/purge_test_contacts.py`), and a fake
"Verify J.P. Morgan" firm that rendered as a real card on the founder's own
Today page.

So: to click through a CRM feature by hand, sign in as
**`demo@coverage.local`** (password `demo1234`) — run **`manage.py
seed_demo`** first if it doesn't exist yet (idempotent, safe to run
anytime). It is tenant-isolated like every other account, so nothing you do
to its contacts/touches/firms can affect anyone else's data. Only reach for
`directory.Firm`/`FirmDate` directly when the thing under test IS the shared
directory itself, and prefer doing that against pytest's database over the
live one. Either way, run **`manage.py audit_fixtures`** before you finish —
it reports (never deletes) anything that still looks synthetic, so a session
ends with a check rather than a guess.

Google sign-in (`/accounts/google/login/`) is wired up via django-allauth but
needs a real OAuth client from Google Cloud Console
(`GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` in `.env`) to
complete a login — that's the founder's to create. **That client must request
only `openid email profile` scopes and never anything under `gmail.*`**; see
`docs/build-plan.md` §3 and the `coverage-gmail-oauth-setup` skill for why
this boundary matters. The app boots and the test suite passes with no
Google credentials configured at all.
