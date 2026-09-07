# Deploying Networkly

Target: **Render** (managed Postgres + built-in cron for the 6-hourly scrape). The
`Dockerfile` is host-agnostic, so Fly.io or any container host works too — only
the platform steps differ. Deployment, migrations and service activation change
production state. The existing services are suspended; use the
[beta release runbook](beta-release-runbook.md) before executing these steps.

Prerequisites you create (Claude can't — they need your accounts/payment):
a Render account and a Google Cloud project (sign-in, and separately, Gmail Live
if you want it). Rough cost at this scale: Render web + Postgres ≈ low-tens of
dollars/month; Google OAuth is free.

---

## 1. First deploy (Render Blueprint)

1. Push this repo to GitHub (it already has a sensible `.gitignore`; the real
   `.env` is ignored — never commit it).
2. Render → **New → Blueprint** → pick the repo. Render reads `render.yaml` and
   proposes a **web service**, a **Postgres database**, and several **cron
   jobs/workers**. The shared cache is the existing Upstash service; this
   Blueprint does not provision another cache. Reconcile existing services
   before applying to avoid creating duplicate paid resources.
3. It will ask you to fill the `sync: false` env vars (they can't live in git).
   Some integrations can remain blank for a boot check, but the full-feature
   beta requires `deploy_preflight --launch` plus provider acceptance.
   A healthy process alone does not establish a launchable product. Set these on the **web service** when you're ready:
   - `DJANGO_ALLOWED_HOSTS` — optional. Blank falls back to
     `RENDER_EXTERNAL_HOSTNAME`, which Render injects into every service, so
     the app boots on `coverage-web.onrender.com` with nothing typed in. Set
     it (comma-separated) when you attach a custom domain.
   - `DJANGO_CSRF_TRUSTED_ORIGINS` — same: blank falls back to
     `https://<render hostname>`. Set it for a custom domain, scheme included.
   - `SITE_URL` — set this explicitly to the public HTTPS origin before
     enabling email. The web service can fall back to its Render hostname;
     cron services have no public hostname. Email jobs inherit the web
     service's explicit value for digest and trial-ended links.
   - `REDIS_URL` — preserve the existing Upstash TLS (`rediss://`) URL
     on the web service; workers that use the cache inherit it. This cache holds the
     failed-login, search and waitlist counters. Before it existed, each of
     the three gunicorn workers kept its own copy, so the "5 failed logins
     per 5 minutes" limit was really 15 and reset on every deploy.
   - `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` (section 3).
   - `GMAIL_LIVE_*` (five keys) — optional; leave blank until you want real-time
     Gmail (section 4, `docs/gmail-live-setup.md`). Blank no longer crash-loops
     the `coverage-gmail-live` worker: it logs one line and idles.
   - `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` — optional (section 8).
   - `APPLE_OAUTH_*`, `MICROSOFT_OAUTH_*`, `LINKEDIN_OAUTH_*` — optional; leave
     blank and those sign-in buttons show "Setup Needed" until you fill them.
   - `SENTRY_DSN` — optional; leave blank to disable.
   - `DJANGO_SECRET_KEY` is `generateValue: true` — Render creates and stores
     it; the cron jobs and workers share the same value.
4. Apply. Render builds the image, runs `collectstatic` at build time, runs
   `migrate` as the **preDeploy** step (once, before traffic — a failed
   migration blocks the release instead of half-applying), then starts gunicorn.
5. Health check: Render polls `/healthz`. When the service is green, open
   `https://<your-host>/` — the home page and `/opportunities/` should load
   (the feed is empty until you seed + scrape, section 2).

### 1b. Preflight

On the web service's **Shell**, before anything else:

```bash
uv run --package networkly-web python networkly_web/manage.py deploy_preflight
```

One line per thing that has broken a deploy of this app, each `PASS`, `WARN`
or `FAIL`. It prints key **names** and verdicts only, never a value, so the
output is safe to paste anywhere. `FAIL` means this deploy will not work and
exits non-zero; `WARN` means a feature is dark and the line says which. A
configuration check that has no `FAIL` is not proof of working integrations.
For this beta, run `deploy_preflight --launch`: required-feature warnings become
failures. Never use `--warn-only` as release acceptance.

A value left as `changeme` is reported as a placeholder, not as configured —
the command never guesses a value and never fills one in.

### 1c. Cron ordering, and the one ordering that matters on a first apply

`render.yaml`'s crons and the worker share the web service's image but have
**no pre-deploy step of their own**. On the very first Blueprint apply they
can therefore start before the web service's `migrate` finishes, and will
traceback on missing tables until it lands. This is self-healing and noisy,
not damaging: the next tick succeeds. If you want silence, suspend the
`*/5` crons in the dashboard until section 2 is done, then resume them.
`deploy_preflight` reports unapplied migrations as a `FAIL` for exactly this
reason.

The daily 05:00 block runs in this order, and the order is load-bearing:

| UTC | Service | Why here |
|---|---|---|
| 04:15 | `coverage-db-backup` | The last quiet moment before the day's plan flips. Inert until a bucket is named — see section 9. |
| 05:00 | `coverage-pro-trial-expire` | Decides who is Pro. Also sends the trial-ended email and unlocks the student's Free "Scan Now". |
| 05:30 | `coverage-gmail-watch-renew` | Acts on who is Pro. Renews only `plan="pro"` watches. |

These used to be the other way round, so a trial that ended overnight got one
last 7-day watch renewal half an hour before the flip that was meant to stop
it. The job that decides has to land before the job that acts.

The two `*/5` jobs are deliberately offset by two minutes
(`coverage-gmail-backfill` on `*/5`, `coverage-autopilot` on `2-59/5`): both
pre-clamp their work against the same student's credit balance, and firing on
the same tick is what let two clamps read one balance. The real fix is at the
debit (`billing.credits._spend_clamped` re-runs the clamp under a row lock);
the offset is belt and braces.

If you mirror these jobs into local launchd plists (`scripts/launchd/`), keep
the same ordering: expire, then renew.

## 2. Create the admin + seed data (Render Shell)

On the web service's **Shell** tab:

```bash
uv run --package networkly-web python networkly_web/manage.py createsuperuser
uv run --package networkly-web python networkly_web/manage.py seed_directory   # 71 firm rows + SA 2028 firm dates
uv run --package networkly-web python networkly_web/manage.py scrape            # first opportunities pull
uv run --package networkly-web python networkly_web/manage.py seed_logo_domains  # firm front doors, for logos
uv run --package networkly-web python networkly_web/manage.py seed_mail_domains  # the domains bankers email FROM
```

Every seed file these commands read is **tracked in git and ships inside the
`directory` app** — `directory/seeds/*.yaml` for the firms and firm dates,
`directory/_logo_domains.py` and `directory/_mail_domains.py` for the two
domain maps. None of them reads `data/`, which is gitignored (it holds the
founder's private research and would not exist on Render anyway). Until
2026-08-25 `seed_directory` read `data/seeds/firms.yaml`, so this section's
first deploy would have printed "firms file not found" and left you with an
empty directory; if you are following an older copy of these instructions,
that is the bug.

Order matters. `seed_mail_domains` runs **after** `scrape` because it appends
to firms the catalog has already created and never invents a connector firm,
whereas `seed_directory` *replaces* each firm's `domains` list from the YAML —
run it last and it would drop everything the connectors and the two domain
commands had added. Without `seed_mail_domains` specifically, `capture.discovery`
matches almost nothing: the domains a board connector stores are career-site
hosts (`careers.bcg.com`, `jobs.rbc.com`), and nobody sends mail from one.

Now `/admin/` accepts your login and `/opportunities/` shows live openings. The
cron service runs the full `refresh` pass every 6 hours (00/06/12/18 UTC;
change `schedule` in `render.yaml`). The command exits non-zero when any stage
fails **or** when a pass ends with zero open roles, so turn on cron-failure
notifications (Render → the cron service → Settings → Notifications) and a
broken scrape emails you instead of silently serving stale deadlines.

## 3. Google sign-in (login-only scopes)

The `coverage-gmail-oauth-setup` skill in this repo walks the Cloud Console
clicks. The one rule that matters: **request only `openid`, `email`, `profile` —
never a `gmail.*` scope.** Login OAuth is unrestricted; adding a Gmail scope
would drag you into Google's restricted-scope verification (the CASA gate).
Gmail Live (section 4) uses a *separate* consent flow for exactly this reason,
so a verification stall on that client can never break sign-in.

1. Cloud Console → APIs & Services → **OAuth consent screen** (External),
   add your email as a test user while unverified.
2. **Credentials → Create OAuth client → Web application.** Authorized redirect
   URI: `https://<your-host>/accounts/google/login/callback/`.
3. Put the client id/secret into `GOOGLE_OAUTH_CLIENT_ID` /
   `GOOGLE_OAUTH_CLIENT_SECRET` on the web service; redeploy.
4. Also add the Google **Social Application** in Django admin
   (`/admin/socialaccount/socialapp/`) if allauth doesn't pick it up from env:
   provider Google, the same client id/secret, and attach it to the site.

## 4. Gmail Live — real-time reply/bounce/invite detection (optional)

This is how Networkly's CRM actually fills itself in: connect a Gmail account
and touches log themselves, no habit change required. Full walkthrough,
including the Google Cloud Console clicks (a SEPARATE OAuth client from
section 3 — never reuse it) and the Pub/Sub setup, lives in
`docs/gmail-live-setup.md`. Skip this section entirely if you're not ready for
it yet — the app runs fine without it; the Settings page simply shows nothing
extra until `GMAIL_LIVE_*` is set.

### 4b. The daily Gmail sync (an older, still-useful path)

A separate, simpler route: for a mailbox already being scanned outside
Networkly by hand (an agent searching Gmail and emitting typed findings), apply
that same batch here — one search serves both systems. This needs no Google
review of its own; it just applies findings someone else already gathered.

```bash
DAYS=$(manage.py capture_gmail --email you@example.com --window)   # size the search
# ...the sync searches `newer_than:${DAYS}d` and writes findings.json...
manage.py capture_gmail --email you@example.com --findings findings.json --dry-run
manage.py capture_gmail --email you@example.com --findings findings.json
```

Always `--dry-run` first when wiring up a new findings source: it runs every
match, ratchet and dedup decision and writes nothing, and a mis-shaped batch
that silently archives contacts as bounced is tedious to unpick.

## 4c. Email (password resets, the weekly digest, the trial-ended notice)

Unset `EMAIL_URL` prints mail to the service logs instead of sending it, so
everything below works on a deploy with nothing bought. Two consequences
worth knowing before real students arrive: nobody can self-serve a password
reset, and the "your Pro trial has ended" mail is not sent at all (the
Settings banner carries that notice on its own — `accounts/trials.py`
deliberately does not count a message printed into a log as delivered).

When you're ready: create an email-provider account, verify a sending
domain, then set `EMAIL_URL` on **coverage-web**, **coverage-weekly-digest**
and **coverage-pro-trial-expire**. Set `DEFAULT_FROM_EMAIL` on the web and
trial-expiry services; the weekly digest inherits the web value. Set the
public `SITE_URL` on the web service; both email jobs inherit it:

- `EMAIL_URL` = `smtp+tls://resend:API_KEY@smtp.resend.com:587`
- `DEFAULT_FROM_EMAIL` = `Networkly <no-reply@yourdomain>`
- `SITE_URL` = `https://<your-public-host>`

**How much mail a day this costs, which is the part that nearly broke.**
Resend's free tier allows **100 emails a day, 3,000 a month, 3 domains, 30
days of retention** (verified 2026-09-06). The digest cron used to run
`0 13 * * 1` and mail every eligible account inside one minute: at the
beta's cap of 100 students, that is the whole day's allowance spent on the
digest, and the mail somebody is actually waiting on — the confirmation, the
reset, the invitation — is refused. Nobody sees an error, because those sends
fail at the provider after the app has already said "check your inbox".

Two mechanisms now stand between the digest and that day:

- `coverage-weekly-digest` runs **daily** and passes `--spread`, which mails
  only the seventh of the roster whose `pk % 7` matches the run's UTC
  weekday. Every student still gets exactly one digest a week, on the same
  weekday every week. A 100-student roster costs about 14 sends a day
  instead of 100 in one.
- `DIGEST_DAILY_SEND_CAP` (default 60, `settings/base.py`) is the hard
  ceiling, and it applies with or without `--spread` — including to a
  founder running the command by hand. Recipients past it are deferred, in a
  stable order, and the count is printed.

Nothing about the email changes: "closing this week" is a rolling window from
the recipient's own today, not a calendar week, so a Thursday student's
digest reads exactly as a Monday student's does.

### 4d. Google Calendar

Google Calendar is optional and separately consented. Add
`https://<your-public-host>/capture/calendar/callback/` to the Gmail/Calendar
OAuth client and enable the Calendar API. Set `GCAL_LIVE_ENABLED=true` on
staging, connect a test user and verify a dry preview before enabling it
on the production web service. The
`coverage-gcal-sync` cron inherits the flag and credentials, and runs
`gcal_sync --apply` every five minutes. Without the flag it stays idle.
Applied runs appear as `gcal-sync` in `/ops/health/cron/`; failures exit
nonzero after continuing through the other connected calendars. The manual
command remains dry by default. Test an event update and cancellation, not
just the initial import.

The Gmail backfill worker also inherits `ANTHROPIC_API_KEY` from the web
service. Without that worker-side key, deterministic scanning works but
ambiguous-thread AI classification is skipped.

## 5. Custom domain (optional, when ready)

Attach your domain to the Render web service, add it to `DJANGO_ALLOWED_HOSTS`
and `DJANGO_CSRF_TRUSTED_ORIGINS`, and update both Google redirect URIs
(sign-in and, if connected, Gmail Live).

### 5b. HSTS preload (a one-way door, so it is off)

`settings/production.py` ships a seven-day HSTS max-age with
`SECURE_HSTS_PRELOAD` off. Both halves are on purpose. A short max-age is
the escape hatch while the domain and its certificates are still moving —
HSTS cannot be un-said any faster than the max-age already handed out — and
the `preload` token is a claim that the origin meets hstspreload.org's bar
(max-age of at least a year, plus subdomains, plus an HTTP redirect). A
seven-day header carrying `preload` advertises a qualification it does not
have, which is what it did until 2026-09-01.

Because preload is off permanently, `production.py` carries
`SILENCED_SYSTEM_CHECKS = ["security.W021"]`. Django raises W021 whenever
`SECURE_HSTS_PRELOAD` is False, so without the silence the runbook's own gate
— `manage.py check --deploy --fail-level WARNING`, which must exit zero —
could never pass on a correctly configured deploy, and the one command meant
to catch a real misconfiguration becomes a line everybody learns to skip. The
silence is scoped to that single check id; every other security warning still
fails the gate. Flipping preload on makes the entry inert rather than wrong.

Turning it on is your call, not a default, because getting off the preload
list takes months and ships with a browser release. When you want it, in
this order:

1. Run one clean cycle on the real domain: HTTPS working, every subdomain
   you use served over HTTPS too.
2. Set `DJANGO_SECURE_HSTS_SECONDS=31536000` and deploy.
3. Set `DJANGO_SECURE_HSTS_PRELOAD=true` and deploy.
4. Submit the domain at https://hstspreload.org.

---

## Fly.io instead of Render

The `Dockerfile` is portable. `fly launch` (don't deploy yet), then: add a
managed Postgres (`fly postgres create` + `fly postgres attach`), set the same
env vars via `fly secrets set`, add a `[deploy] release_command` running
`migrate`, and add a scheduled machine (or an external cron hitting a management
command) for the daily scrape. Render's built-in cron is the only reason it's
the recommended default; everything else is equivalent.

## 8. Stripe (only once Pro has a purchase path)

`billing/` covers exactly one thing today: pay-as-you-go credit packs. There
is no subscription, no customer portal, and no paid-Pro representation at all
(see `docs/plans/b2b2c-sketch.md`). When you do turn it on:

1. Dashboard → Developers → API keys → create a **restricted** key with
   Checkout Sessions *write* and nothing else. `deploy_preflight` warns if
   `STRIPE_SECRET_KEY` is not an `rk_` key.
2. Developers → Webhooks → add `https://<your-host>/billing/webhook/` for
   **`checkout.session.completed` and `checkout.session.async_payment_succeeded`**.
   Both, not just the first: `completed` fires when the customer finishes the
   form, which for a delayed method (bank debit, voucher) is not when the
   money arrives. The handler grants only on `payment_status == "paid"`, so
   without the second event a delayed payment would settle and never be
   credited.
3. Create the endpoint on API version **`2026-07-29.dahlia`**, the version
   `billing/stripe_gateway.STRIPE_API_VERSION` pins outbound calls to. A
   mismatch is logged as a warning on every delivery, not rejected.
4. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` on **coverage-web**.
   Both are already declared in `render.yaml` as `sync: false`, so they
   survive a Blueprint re-apply.

## 9. Database backups (defined, off until you pay for a bucket)

`render.yaml` declares `coverage-db-backup`, a daily 04:15 UTC cron running
`backup_db --require-s3`. It is deliberately inert on a fresh apply, and it
takes two things to arm it. Neither happens by accident:

1. The service is suspended in the dashboard, like every other service in
   this deploy. Render's Blueprint schema has no `suspended:` key, so a cron
   cannot be declared dormant in the file itself.
2. `BACKUP_S3_BUCKET` is blank. With `--require-s3` and no bucket the command
   does nothing at all — no `pg_dump`, no connection to the database, no
   file — prints why, and exits zero. A dump written inside a Render
   container is not a backup: the filesystem goes away with the container.

To turn it on, once object storage is paid for:

- Create a bucket **separate from the avatar bucket**, in the same account.
  One object here is every row in the app; it does not belong in the same
  listing as media a request path can reach.
- Set `BACKUP_S3_BUCKET` on `coverage-db-backup` (and `BACKUP_S3_PREFIX` if
  you want something other than `db/`). The endpoint, region and credentials
  are inherited from the web service's `MEDIA_S3_*` values.
- Resume the service. `--keep 14` holds a fourteen-snapshot ring in the
  bucket, pruned oldest-first by key name.
- Add `"db-backup"` to `ops.tracking.EXPECTED_INTERVALS` and a
  `HEALTHCHECK_URL_DB_BACKUP` slot in the same change, so
  `/ops/health/cron/` starts watching it. It is deliberately untracked while
  dormant: a tracked job that is never meant to run reads as a dead job
  forever.

The image can do this now and could not before: `pg_dump` was not installed
in it at all, so `backup_db` only ever ran from a laptop. The Dockerfile
installs `postgresql-client-18` from the PGDG repository, and CI runs
`pg_dump --version` inside the built image so the binary cannot silently go
missing again. **Major version 18 matters**: `pg_dump` refuses a server newer
than itself, and that is a non-zero exit, not a warning. Read the real
"PostgreSQL version" off the `coverage-db` page in the dashboard — if it is
ever above 18, the Dockerfile has to move with it.

Restore is unchanged and is documented in `backup_db`'s own docstring and in
the [beta release runbook](beta-release-runbook.md). Restore beside the live
database, never over it.

## Dependency scanning

No CVE scan had ever been run against this tree (`audit-security.md §9`), and
"we would have noticed" is not a control. `pip-audit` is a dev dependency; the
command is:

```bash
uv run pip-audit --strict
```

`--strict` fails on a package it cannot resolve rather than skipping it
silently, which is the only version of this worth running: a scanner that
quietly ignores what it does not understand reports clean for the wrong reason.
Add `--requirement uv.lock` to scan the locked resolution rather than whatever
happens to be installed.

Run it before a deploy and after any dependency change. A finding is either
fixed by taking the release that closes it, or written down here with the
reason it is being accepted — never left unread.

`uv run pip-audit --strict` on its own reports an error rather than a finding:
`--strict` refuses to skip a package it cannot resolve, and this workspace's
own three packages (coverage-web, networkly-domain, networkly-connectors) are
editable installs with no PyPI entry to resolve against. Export first, then
audit the export — which is exactly what `.github/workflows/pip-audit.yml`
already does on every push, on every pull request, and every Monday:

```bash
uv export --all-packages --locked --no-emit-workspace \
  --format requirements.txt -o requirements-audit.txt
uv run pip-audit --strict -r requirements-audit.txt
```

**Run 2026-09-06 against the current lockfile: "No known vulnerabilities
found."** 126 packages resolved, nothing outstanding, so no version was moved
in that release pass. The earlier note here listing point releases for
django-allauth, cryptography, google-auth, stripe, psycopg, gunicorn and
playwright as outstanding is settled: the lockfile has since moved past every
one of them, and none of the current pins carries an advisory. Being a point
release behind is not by itself a reason to bump — a bump with no advisory
behind it is churn with a regression risk and no security win.

**The anthropic pin does not move with them.** 0.122.0 against 1.3.0 is a major
version, and `assistant/`'s agent loop depends on the streaming and tool APIs
that a major release is exactly where it would change. Read the migration notes
first; it is its own commit, not a line in a batch. Django stays on 5.2.x, which
is LTS to 2028.

## What still isn't automated (by design)

- The Google OAuth clients (sections 3 and 4) — need your Cloud project.
- The `firm_boards` DB table for ATS tokens (currently in
  `directory/boards.py`) — noted in the build follow-ups, not a blocker.
- Paid Pro. Credit top-ups exist; a Pro *subscription* or a seat-based
  institutional plan does not. `User.plan` is an admin flip with no expiry
  for anything but a trial. `docs/plans/b2b2c-sketch.md` is the shape that
  would fix it, unbuilt.
- Database backups beyond the Render plan's own are *defined* but not *on*.
  `coverage-db-backup` is in `render.yaml` and does nothing until somebody
  names a bucket; see section 9. Check the `coverage-db` plan's own retention
  in the dashboard as well — the two are different guarantees.
