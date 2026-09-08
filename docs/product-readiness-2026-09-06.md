# Networkly: Current Beta Launch Checklist

For the subsequent engineering verification and remaining acceptance checks,
see the [7 September deep audit](audits/deep-functional-audit-2026-09-07.md).
Provider-dashboard observations below retain their stated observation dates.

Updated 6 September 2026. The target is a **free, invitation-only beta with all
individual features and at most 100 people**. Enterprise, Team, paid Pro and
Stripe setup are outside this release. AI credits and daily limits still apply;
free access does not mean unlimited usage.

**Not launched.** The ten existing Render services remain user-suspended. No
hosting costs were resumed and no new deployment was made. Configuration saved
in a dashboard is not evidence of working delivery, sync or scheduled jobs.
Historical findings and implementation evidence belong in the
[functional audit](functional-audit-2026-09-06.md); this document is the current
checklist and supersedes its earlier optional-feature and payment requirements.

## Setup Completed So Far

| Area | Verified State on 6 September | Remaining Work |
|---|---|---|
| Google project | `project-71aa6735-1289-4c5d-a15` is External / In production; the displayed unverified lifetime cap is 100 users, with 4 used. Display name is Networkly; founder two-step verification is complete. Gmail read-only, Calendar read-only and basic identity consent scopes are saved. Calendar API is enabled. | Google verification has **not** been submitted or approved. Complete the applicable review and validate actual consent, tokens and provider behavior. |
| Mailbox and Calendar OAuth | Local mailbox client has localhost, `127.0.0.1` and production Gmail/Calendar callbacks. Production uses its distinct existing mailbox client; its production Calendar callback is also saved. | Verify production web and workers use the matching client and token-encryption key; test both integrations. |
| Google sign-in | Separate existing Render sign-in credentials were copied to `.env` with explicit founder approval. Local localhost / `127.0.0.1` login callbacks and the production login callback are verified. | Test invited sign-in, existing-account linking and cancellation on the deployed app. |
| Render configuration | Verified on web: `BETA_ENABLED=true`, `BETA_MAX_USERS=100`, `GCAL_LIVE_ENABLED=true`, `SITE_URL=https://coverage-web.onrender.com`. All eight existing background services have beta flags and Sentry saved; all seven crons also have `SITE_URL`, and push has all three VAPID values. All ten services remain suspended. | Reconcile new Blueprint services, then deploy and resume required services when authorized. |
| Local setup and push | Beta and Calendar flags enabled; `accounts.0018` and `assistant.0005` migrations applied. Generated VAPID credentials and contact configuration copied to Render web; all three values verified by readback. | Carry required configuration and migrations into production. Saved push credentials do not establish delivery. |
| Redis | Free Upstash `networkly-beta-cache` created in Oregon, with TLS and 256 MB. `.env`, Render web and Gmail worker values verified by exact readback. A unique TTL key passed add/increment/read from a second client and was individually deleted. | Verify deployed shared rate limits. Local settings always use per-process memory so tests cannot flush the production cache. |
| Monitoring | Sentry organization `networkly` and project `networkly-django` created. DSN saved in `.env`, Render web and existing background services. A synthetic `NetworklySetupCheck` event arrived and was confirmed in the Sentry UI. | Test deployed job alerts. Check the plan after the no-card 14-day Business trial; it is expected to revert to free, but ongoing cost is not guaranteed here. |
| Private uploads | Supabase free organization Networkly has healthy project `networkly-media` in Oregon (`us-west-2`). Bucket `networkly-avatars` is private: Public off, JPEG/PNG only, 8 MB limit and zero policies. Founder-approved S3 settings are saved in `.env` and Render web with exact readback. Synthetic raw S3 and app storage probes passed; public read was blocked and both probe objects deleted. | No real avatars migrated. Review the migration constraint below; verify authenticated ownership and persistence after deployment. |
| Domain and email | Resend free account and founder-approved sending-only key are configured in `.env` and Render web with exact readback. SMTP authentication passed and Resend reported a founder-only test email Delivered using its test sender. The founder explicitly has no domain yet. | Configure a verified sender/domain and sending services. `EMAIL_URL` is not activated; beta-user email delivery is not enabled. |

The undeployed Blueprint removes the unused `coverage-kv` service and references
Upstash through web configuration. Workers inherit Sentry and the push job
inherits VAPID settings. Backfill's three Google values and Anthropic key, and
Autopilot's Anthropic key, are now saved in Render with exact readback. Gmail
worker Google values, Redis, Sentry and beta flags exactly match web. The
prepared Blueprint also inherits web credentials for backfill and Autopilot.
Digest and legacy trial email settings inherit web, so the verified sender only
needs configuration once. `RESEND_API_KEY` is stored for setup; the application
does not read it directly. Delivery remains controlled by `EMAIL_URL`.
No new code, jobs or services have been deployed.

The [provider setup report](audits/provider-setup-2026-09-06.json) records the
probes. Local `.env` permissions are `0600`. A synthetic 2-pixel PNG passed raw
S3 upload/readback and actual `PrivateMediaStorage.save/open/url/delete`; the
app URL stayed on the same origin. This does not establish deployed access
control or redeploy persistence.

**Avatar migration requires explicit review.** Supabase S3 silently overwrote an
object despite `IfNoneMatch`, so default migration now stops before reading rows
or uploading. Explicit `migrate_avatar_storage --rekey` preview/apply uses fresh
UUID keys, verifies hashes, conditionally updates unchanged database references
and preserves local files. Never run migration automatically; review partial
success before any retry. No real avatar migration was performed.

The [confirmed Sentry setup event](https://networkly.sentry.io/issues/7715814098/)
displayed `[Filtered]`. Private request bodies, local variables, free-form error
text, queries and breadcrumbs are removed; tracing and logs are off. No card or
charge was added for the trial, and trial cancellation was unavailable.

Google's lifetime unverified-app cap is **separate from the app's 100-seat
invitation limit**. The displayed four used authorizations leave fewer than 100
unused Google authorizations; deleting local accounts does not reset that cap.
Keep the existing project in production mode. Unapproved sensitive/restricted
scopes can still show Google's warning. Switching to Testing adds test-user
requirements and generally seven-day Gmail/Calendar refresh-token expiration.
[Google audience and user-cap guidance](https://support.google.com/cloud/answer/15549945),
[OAuth token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).

## Required Before Inviting Users

- [ ] **Deploy the complete beta configuration.** Set the canonical HTTPS address,
  allowed hosts and trusted origins. Apply beta settings consistently to web and
  workers, configure new Blueprint services, migrate before traffic/jobs, and
  verify redirects and forms. The saved Render address is the current base URL;
  custom domain setup remains unfinished.
- [ ] **Enforce admission.** `BETA_ENABLED=true` grants effective individual Pro
  access without changing stored billing plans and blocks new checkout.
  `BETA_MAX_USERS` must be 1–100. Use `beta_invite` to reserve Google emails;
  it creates neither accounts nor email messages. Existing, reserved and
  deleted-account seats remain counted. Verify invited admission, rejection of
  uninvited users and the cap. This does not read or enforce Google's quota.
- [ ] **Enable account and digest email.** Configure a verified sender/domain,
  authenticated TLS `EMAIL_URL` and `DEFAULT_FROM_EMAIL` on sending services.
  Receive verification, password-reset and digest messages in Gmail and another
  inbox; verify that links use the deployed HTTPS address. Resend's free allowance
  is 100 emails/day and 3,000/month (re-read from Resend's pricing page on 6
  September). The digest is now spread across the week and capped at 60 sends a
  day, so no single day can consume the allowance and starve verification or
  reset messages; that headroom is by construction, not by hoping the roster
  stays small.
- [ ] **Accept durable private uploads.** Deploy the configured private storage,
  verify authenticated ownership enforcement and an avatar surviving redeploy.
  Review the explicit `--rekey` preview before authorizing any existing-avatar
  copy; preserve local files and review partial results before retrying.
- [ ] **Finish reliability and AI setup.** Confirm AI provider funding,
  models and spending controls. Prove deployed shared rate limits and job alerts,
  push delivery/denial/unsubscribe and small authorized AI runs within budget.
- [ ] **Accept Gmail and Calendar end to end.** Verify Gmail API availability and
  both consent flows. Keep login separate from mailbox access. Match credentials
  and encryption keys across processes. Test replies, bounces, newsletters,
  application confirmations, rescheduled/cancelled/recurring events and replays:
  expected records appear once and unrelated mail stays out. Test disconnects,
  Google revocation and outage recovery without interrupting another user's sync.
  Google project-wide revocation for the same Google account can invalidate both
  Gmail and Calendar grants; verify reconnection for both rather than promising
  independent provider revocation. Polling does not require Pub/Sub. Calendar is
  enabled locally and on Render web, but provider acceptance remains pending.
- [ ] **Run and monitor every required job.** Obtain recent successful production
  JobRun records and confirm that a deliberate staging failure sends an alert.
  Beta suppresses legacy trial-expiry changes and notices.
- [ ] **Establish production recovery.** Schedule backups, choose retention and a
  restore owner, and back up encryption keys securely. Repeat the verified local
  restore procedure against the deployed schema and document recovery time.
- [ ] **Validate feed and recommendations.** Monitor deployed scrape freshness and
  failing sources. Review representative roles and contact histories against
  expected eligibility, next actions and due dates. The historical board counts
  are not a current all-source health check.
- [ ] **Complete the fresh-account acceptance run below**, including Safari and a
  phone-sized screen. Begin with 5–10 invited testers and observe onboarding,
  first saved role/contact, completed next steps, corrections and sync failures.

## Required Job Map

| Job | Blueprint Cadence | Purpose |
|---|---|---|
| `scrape` / `refresh` | Every 6 hours | Opportunities and deadline enrichment |
| `gmail-poll` | Worker, every 120 seconds | Automatic Gmail capture |
| `gmail-backfill` | Every 5 minutes | Initial scans and requested rescans |
| `autopilot` | Every 5 minutes, offset | User-requested review runs |
| `gcal-sync` | Every 5 minutes, offset | Google Calendar mirroring |
| `assistant-reconcile` (`assistant_reconcile --apply`) | Every 10 minutes | Settle/refund interrupted assistant reservations |
| `weekly-digest` (`send_weekly_digest --spread`) | Daily, 13:00 UTC | One seventh of the roster each day under `DIGEST_DAILY_SEND_CAP` (60); each person still gets one digest a week |
| `push-alerts` | Daily, 13:00 UTC | Deadline push |
| `pro-trial-expire` then `clearsessions` | Daily, 05:00 UTC | Legacy trial expiry (suppressed in beta) and purge of expired session rows |
| `db-backup` (`backup_db --require-s3`) | Daily, 04:15 UTC, **defined but suspended** | Off-host snapshot to the private backups bucket; inert while `BACKUP_S3_BUCKET` is blank; resume after payment |

The Blueprint also contains legacy trial expiry and optional Gmail watch renewal;
polling does not depend on watch renewal. No production job execution is claimed.
Assistant reconciliation requires direct or session-preserving PostgreSQL
connections: transaction pooling does not support its conversation-lock ownership
guarantee. Its apply mode considers pending turns older than 30 minutes, up to
100 per run; it must acquire the same conversation lock before recovery.

## Deployment Gate and Acceptance

Run `uv run --package networkly-web python networkly_web/manage.py deploy_preflight --launch`
in the production web environment after migrations. Missing individual-feature
configuration fails this launch gate; Stripe is unnecessary in beta.
`--warn-only` is diagnostic and is not a passed gate. The command checks effective
configuration, database/migrations and local invitation capacity without provider
requests. A PASS does **not** verify provider funding, OAuth approval, Google's
quota, bucket policy, delivery or scheduled execution.

1. Sign up through an invitation, verify email and complete onboarding. Test
   Google login and cancellation; reject an uninvited account.
2. Find and save an eligible role, move it to Applied and revisit My Applications.
3. Add a contact, import a small CSV and resolve unmatched firms without duplicates.
4. Log a reply, chat and referral; verify contact state and Today's next action.
   Pause/resume outreach and check cadence and timezone behavior.
5. Create, reschedule and cancel meetings; verify the calendar subscription and
   connected Google Calendar. Repeat Gmail/Calendar sync and inspect deduplication.
6. Ask the assistant about a record and inspect grounding. Confirm that sensitive
   changes require confirmation. Exercise failed/interrupted turns and verify a
   single correct settlement or refund; test Autopilot and requested rescans.
7. Verify email and push delivery, including denied permission and unsubscribe.
8. Use two test accounts to check isolation of contacts, applications,
   conversations, uploads and exports.
9. Export, sign out other sessions, reset the password and delete a dedicated
   test account. Verify promised results, including connection cleanup and files.
10. Verify job alerts and recovery from provider failure, revocation and interrupted
    assistant work. Calendar recovery must not treat absence alone as cancellation
    or overwrite manual/mail-owned records.

## Second-Pass Results, 6 September

The afternoon pass ran four parallel workstreams on isolated worktrees with
exclusive file ownership, merged each behind its own focused tests, and gates
the whole with one integrated suite (recorded under Test evidence below).

**Release and configuration — done.** The image builds and is gated in CI on
`codex/**` branches and manual dispatch; CI proves `pg_dump`/`pg_restore` at
major version 18 exist inside it. `render.yaml` validates against Render's
published JSON Schema (it did not before: `BETA_ENABLED` was an unquoted YAML
boolean, which the schema types as string-or-number). `check --deploy
--fail-level WARNING` exits zero on placeholder values with only
`security.W021` (HSTS preload, off by recorded decision) silenced.
`pip-audit --strict` on the exported lockfile: no known vulnerabilities across
126 packages, no version moved. The weekly digest is a daily cron sending one
seventh of the roster under a 60-a-day cap. `backup_db` gained an S3
destination behind a separate `BACKUP_S3_BUCKET`; the `coverage-db-backup`
cron is defined and inert. `coverage-assistant-reconcile` needs no `REDIS_URL`
(PostgreSQL advisory locks); `coverage-gcal-sync` inherits everything it reads;
no optional monitoring key became required.

**Completed 7 September:** the Render dashboard confirmed `coverage-db` uses
PostgreSQL **18**. The audit branch pins that existing value and retains the
PostgreSQL 18 backup client. This is not an upgrade or a Blueprint apply.
Reconfirm the target service before activation; never change its immutable major
version based on an assumed default.
Plan names `basic-256mb` and `starter` are current in Render's schema; no tier
changed.

**Security and privacy — no launch blocker in the posture.** Eleven checks
verified with proofs in the [security review](audits/security-review-2026-09-06.md):
every non-public route gated (a resolver-walking test now requires a gate or a
declared reason on every route), all object lookups tenant-scoped with an
unscoped query raising loudly, invitation cap held under a real threaded
last-seat race, uploads re-encoded with EXIF dropped and served only through
the ownership-checked route, exports scoped and in-memory, Sentry scrubbing
verified by executing the production block, production headers read off a
live response, no secret on any ref. Four privacy-page corrections were forced
by call sites, the most important being that **ordinary background Gmail sync
already sends subjects and snippets to the AI provider**, not only Scan Now;
the object store and the shared cache are now named as processors; the advisor
sends subject lines; a contact's address travels to Google as a search term.
All six legal placeholders and the draft banner are intact.

**Fixed in the same pass from the review's findings:** a failed heartbeat ping
no longer writes the ping URL (the credential) into the log stream; the Stripe
webhook no longer echoes provider error text to unauthenticated callers;
account deletion now signs out every device, and expired session rows are
purged by `clearsessions` chained onto the daily trial-expiry cron; region
enrichment logs a contact's domain rather than the address; and `Firm.logo_url`
no longer raises when the private media store refuses a legacy `firm-logos/`
key — **11 of the 139 local firms** carry a stored logo with no generated static
mark and would have returned 400 on the public Opportunities feed in
production. Two preflight tests that silently depended on a developer's `.env`
now pin beta off. Each fix carries a regression test.

**Still open from the review, for the journeys owner:** `university_search`
is anonymous and unthrottled (static data, no leak); the shared per-IP search
throttle should be applied.

**Algorithms and data integrity — four demonstrated defects fixed, thirty
tests added, and two areas probed and found already covered.** (1) The
`backfill_class_year_derived` repair command claimed to reproduce ingest's
rule but read only the title year, so under `--commit` it wrote a heuristic
`2028` over rows whose body stated "graduating in 2026 or 2027"; the column
carries no provenance, so the overwrite was unrecoverable. It now honors the
retained stated window. (2) When a Google Calendar event arrived before the
matching invite email, the mail path matched it by iCalUID with no source
filter, took the row over, and could drag a rescheduled meeting back to its
original time while permanently silencing Google's own mirroring. Mail may now
record the join but never move or re-own a Google-owned meeting. (3) The credit
burst guard computed the student's day inside their zone but built midnight
outside it, which falls back to UTC from a cron tick; for a Los Angeles
account every evening's spend counted against tomorrow, and the fall-back
day's 25th hour was orphaned. (4) Two Today counts accepted future-dated
touches: the pace ring could read 100% on a week with nothing sent (and that
count feeds the daily cap), and the bench rendered "-4 days ago". Reservation
settlement (provider exception, mid-stream disconnect, hard-kill, refund
exactly once, age never refunding a live owner, two recovery workers) and
same-conversation concurrency were probed and found already covered by the
existing durable-turn tests. Rules deliberately left alone: blank-region
deadline bucketing, the recent-activity clamp, and the "already has N today"
copy that counts planned cards. Verified per app from the agent's worktree:
capture 1,187, crm 2,869, assistant/billing/directory 5,469, domain 612 on a
disposable PostgreSQL database.

**Local user journeys — 111 automated journey tests, all green, plus a
browser matrix.** Invitation acceptance, uninvited rejection and the cap
(walking allauth's real Google callback with only the two network calls
mocked); onboarding into Settings; find, save, apply, revisit and remove a
role; add a contact and import a five-row CSV with a duplicate and an
unmatched firm without creating duplicates; reply, chat and referral moving
warmth and Today's next action, with pause and resume, for a Los Angeles user
and a Hong Kong user; calendar create and the ICS subscription; assistant
failure from the outside with the reservation refunded and the conversation
usable afterwards; export scoped to the caller and deletion consuming the
seat; two strangers trying every route against each other. Chromium and
WebKit (the closest available engine to Safari; Safari's own chrome remains a
manual check) at 1280x900 and 375x812: fourteen authenticated surfaces with
zero horizontal overflow, controls reachable and enabled, no console errors,
and the Opportunities save verified by reading the row back from the
database. Mocked and named as such: Google token exchange, the AI client, and
Google revocation. Two defects fixed: the delete confirmation page listed five
categories where deletion removes about thirty tables' worth (it now names the
connected Google account, conversations and memories, the uploaded photo,
calendar events and credit history), and the assistant's scrolling regions
were unreachable from a keyboard on a phone.

**Found by the journeys and still open at this checkpoint:** acceptance step 5
asks the user to reschedule and cancel a meeting, and no user action can do
either. There is no reschedule route (moving a meeting is delete-then-add,
which mints a new ICS UID so subscribers see it vanish rather than move), and
delete is a hard delete, so the feed never emits `STATUS:CANCELLED` for a
self-cancelled meeting. A bounded fix (reschedule keeping the UID with a
SEQUENCE bump; cancel setting `cancelled_at`; ownership rules unchanged for
Google and mail-owned rows) is in progress on its own branch and will be
recorded here when merged. The search throttle from the security review is
applied.

**Calendar reschedule and cancel — merged.** Reschedule moves the same row
(same UID) and bumps an ICS `SEQUENCE`; cancel keeps the row with
`cancelled_at` so the subscription emits `STATUS:CANCELLED`. Both are limited
to hand-added events the caller owns; Google-owned and mail-owned rows answer
404 and show neither control. Delete keeps its previous meaning because six
existing tests pin it. Acceptance step 5 can now be exercised end to end.
Twenty calendar journey tests, 423 across the calendar and route-auth files.

**Gates, and what they showed.** The authoritative local gate runs in a
detached worktree at the merged head, because the main checkout carries
another session's uncommitted interface edits and that session runs pytest
there (two pytest processes in one checkout share a test database; the
result is deadlocks and "database couldn't be flushed", which is a collision
signature, not a code failure). The clean gate on the merged tree: **11,944
passed, 45 skipped, 1 failed**. The one failure,
`test_simultaneous_last_seat_reservations_are_serialized`, passed alone five
times and on CI, and its failing assertion was `['full', 'full']`: both
simultaneous claims saw a full beta, which means a seat-counting row already
existed. Existing users count as seats, and pytest-django runs every
rollback-mode test in the suite before any transactional one, so a row a
side connection committed earlier lands in this test's count. The test now
sets its cap to one above whatever is already counted and checks its own two
reservations, which is the claim it was written to prove. The row's source was
then located and fixed: `core/tests/test_query_budgets.py`'s module fixture
deletes its user outside any test transaction, and with `BETA_ENABLED=true` in
the founder's `.env` the `pre_delete` receiver minted an undeletable beta seat
for that prop user, which survived until the suite's first TRUNCATE. CI has no
`.env`, so it never saw it. The fixture now deletes with the beta off and
sweeps the seat; a full run with the race test restored to its strict form
passed 11,945 with no other leaking test. Two lessons stand: a suite-wide
default set per test does not reach a module fixture's teardown, and a
receiver that runs on delete is part of a test's cleanup surface. CI on the clean runner:
green on `bd127c0` (11,819 tests, audit clean across 122 pins, image
built); on `2862274` the test job died at collection because the browser
matrix's screenshot directory defaulted to one developer's absolute path,
fixed in `c419c11` together with a clean skip when a browser is absent and a
CI step that installs Chromium and WebKit.

**The suite no longer depends on the wall clock at import.** The first CI run
to straddle midnight UTC (collected on Sunday, executed on Monday) failed 39
date-arithmetic tests by exactly one day each: nine test files snapshotted
`TODAY = timezone.localdate()` or `NOW = timezone.now()` at module level, so
fixtures were built on yesterday while the code under test read today. Every
snapshot is now a function evaluated when a test asks for it, and a bench test
whose premise was "two hours ago is today" now builds its touch at one minute
past local midnight. Verified by running all twelve affected files during the
very window that broke them. A suite that takes 25 to 47 minutes on a runner
will cross that line regularly; this was a latent red-on-some-nights.

**A second clock class, caught the same night.** The CI run on the fix
(`ff4df89`) reached its assertions at 00:57 UTC on Monday 7 September and
failed one test of 11,977: the pace ring's mixed-week test dated two touches
"two hours ago" and "one hour ago", which on a Monday before 02:00 is Sunday,
outside the ring's week floor. Not an import-time snapshot, a premise: "a
little earlier is still this week". The past touches are now anchored at no
earlier than local midnight, which is always on or after the floor and never
after now, and a regression test pins the clock to that exact Monday minute
and expects two. The old shape reproduces `assert 0 == 2` under that pin; the
new one passes. The lesson generalises: any test that subtracts hours from
now and asserts a week or day membership has a window each week where it lies.

**Suite hygiene fixed in this pass:** the suite's verdict no longer depends
on the developer's `.env`. `BETA_ENABLED=true` had made every account read as
Pro and failed twenty free-tier tests on the founder's laptop only; the root
conftest now runs every test with the beta off unless the test turns it on,
the same rule it already applied to the AI key. The three Gmail-card tests
now configure the live client themselves, and the two Stripe preflight tests
pin the beta off. The CI test job (a clean runner with no `.env`) is the
independent check that no further machine-dependence remains.

## Unfinished Items by Class

Classified at the end of the second pass. A = needs payment or a service
resumed; B = owner account action or factual decision; C = third-party
approval; D = still doable without payment.

| Item | Class | Exact dependency | Next action | Who |
|---|---|---|---|---|
| Calendar reschedule and cancel as user actions | D | Nothing; in progress on its own branch | Merge, run the integrated suite, record here | Engineering |
| Final integrated suite green locally and on the clean CI runner | Done | `578614e`: CI 11,978 passed, 13 skipped, 0 failed | None; re-run on any new head | Engineering |
| Resume hosting: web, database, worker, crons (12 services in the Blueprint) | A | Render billing | Follow "After Payment" below | Owner resumes; engineering runs the gates |
| Domain, DNS, HTTPS, Google callbacks, Resend sender, `EMAIL_URL` | A | A bought domain | Dossier section "Domain, DNS and console changes" | Owner buys and publishes DNS; engineering sets config |
| AI features live (assistant, Scan Now, Autopilot, region enrichment) | A | Anthropic credit balance (empty as of 4 September) | Top up; keep existing spend limits | Owner |
| Gmail and Calendar end-to-end acceptance, job execution evidence, Healthchecks pings, Sentry job alerts, shared-Redis limits, avatar durability across redeploy | A | Resumed hosting | Acceptance steps 1–10 on the deployed app | Owner with engineering |
| Off-host backup cron running | A | Resumed hosting | Set `BACKUP_S3_BUCKET=networkly-backups` on `coverage-db-backup`, run once by hand, resume the cron, add it to `EXPECTED_INTERVALS` | Owner resumes; engineering verifies |
| Sentry owner notification actually delivered | B | The Sentry account's notification address | Confirm the address in Sentry account settings, re-fire the test, check that inbox | Owner |
| Healthchecks: apply the 11 windows, run the synthetic missed-job test, start checks after resume | B | Dashboard or API key | Monitoring Plan above; keep real checks unstarted until resume | Owner |
| `coverage-db` PostgreSQL major version | Completed 7 September | Dashboard readback: 18 | Audit branch records the matching version; no Blueprint applied | Engineering verified |
| Encryption-key recovery record | B | A password manager or sealed record | Store `GMAIL_LIVE_TOKEN_KEY` (ring, newest first) and `DJANGO_SECRET_KEY` with the date | Owner |
| Legal identity, address, privacy contact, jurisdiction, backup retention | B | Facts only the founder holds; adviser review is his call | Replace the six placeholders on the privacy and terms pages | Owner |
| Calendar scope minimisation | B then D | Founder decision; one live consent pass after | Decide; if yes, engineering switches to the narrower pair and retests connect, sync, disconnect, reconnect | Owner decides |
| "Who to Find" | B | Founder decision | Choose a contextual firm-page entry or retire it; unchanged until then | Owner |
| Push delivery, denial and unsubscribe in a real browser | B | A browser session on the owner's machine | Subscribe in Safari and Chrome on the deployed app, run the daily push job once, deny and unsubscribe | Owner |
| Local poller running pre-fix code | Completed 7 September | Local audited release and migrations | Server and the four existing local jobs restarted after backup and restore checks | Engineering verified |
| Earlier uncommitted UI edits | Superseded 7 September | Current checkout inspected | Tracked checkout is clean after the audited release; private `docs/content/` remains untracked and unpublished | Engineering verified |
| Repository visibility | B | GitHub settings | The repo is public; decide whether it stays so before inviting testers | Owner |
| Google OAuth verification (restricted Gmail scope, assessment) | C after A and B | Deployed origin, domain ownership, legal pages, demo video | Dossier "Submission gates" | Owner submits; Google approves |
| Real avatar migration into the private bucket | A then B | Deployed storage; a `--rekey` preview reviewed by the owner | Preview, review partial results, apply | Owner authorises |

## After Payment: Ordered Execution Checklist

1. Top up the Anthropic balance; leave the existing daily limits and credit plans as they are.
2. Reconfirm the intended Render database and release. Its major version was verified as 18 on 7 September and is pinned to that value on the audit branch. Reconcile dashboard commands with current `networkly_web` paths before applying anything; leave the watched `main` branch untouched until release activation is authorized.
3. Store `GMAIL_LIVE_TOKEN_KEY` and `DJANGO_SECRET_KEY` in a password manager with today's date.
4. Apply the Blueprint (12 services). Confirm every `sync: false` value on `coverage-web` is still present; the new `coverage-gcal-sync`, `coverage-assistant-reconcile` and `coverage-db-backup` inherit from it. Set `BACKUP_S3_BUCKET=networkly-backups` on `coverage-db-backup` only.
5. Resume the database and `coverage-web` only. Migrations run as the pre-deploy step. On the web shell run the three gate commands from the runbook: `check --deploy --fail-level WARNING`, `migrate --check`, `deploy_preflight --launch`. All three must exit zero.
6. Open `/healthz`, then sign in with the founder's Google account and load Today, Opportunities, Network, Calendar, Settings.
7. Run `backup_db --require-s3 --dest /tmp/coverage-backup --keep 14` once by hand from the web shell; confirm one object in `networkly-backups/db/`. Then resume `coverage-db-backup`.
8. Resume the worker and crons in this order: `coverage-gmail-live`, `coverage-gmail-backfill`, `coverage-autopilot`, `coverage-gcal-sync`, `coverage-assistant-reconcile`, `coverage-scrape`, `coverage-push-alerts`, `coverage-weekly-digest`, `coverage-pro-trial-expire`, `coverage-gmail-watch-renew`. Start each Healthchecks check as its service resumes, with the windows from the Monitoring Plan; add `db-backup` to `EXPECTED_INTERVALS` in the same change.
9. Within a day, confirm a success `JobRun` for every required job on `/ops/health/cron/` and a green row for every check.
10. Confirm the Sentry address and inbox; run the Healthchecks synthetic missed-job test and delete it.
11. Buy the domain. Publish the DNS records from the dossier, wait for Render's certificate, set `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` and `SITE_URL`, redeploy. Add the three domain callbacks and the consent-screen links in Google Cloud. Add the domain to Resend, publish its records, then set `EMAIL_URL` and `DEFAULT_FROM_EMAIL` on `coverage-web`. Send a verification, a reset and one digest to the founder's inbox and check every link.
12. Run the ten acceptance steps with two synthetic accounts on the deployed app, including Gmail and Calendar connect on a designated test Google account, and push subscribe, deny and unsubscribe in Safari and Chrome.
13. Fill the six legal placeholders. Record the demo video from the storyboard. Submit Google verification. Reserve a reviewer seat with `beta_invite` when Google supplies the address.
14. Invite 5 to 10 testers with `beta_invite` and watch onboarding, the first saved role and contact, and sync failures for a week before the next batch.

## Founder Decisions and Evidence Limits

- **Who to Find remains a decision gate.** Choose a contextual firm-page entry or
  explicit retirement before restoring or removing the capability.
- **Legal details remain placeholders at the founder's request.** Real operator,
  address, jurisdiction and monitored support details, plus privacy disclosures
  matching actual data processing, remain required before a public launch. No
  legal identity or approval is inferred.
- **Backup evidence:** the [restore report](audits/backup-restore-2026-09-06.json)
  now records the second drill of 6 September, run on the current schema: a
  12.5 MB `backup_db` snapshot restored twice into fresh drill databases, all
  **62 tables** matching the dump in row count and row contents (five tables
  differ only in physical heap order, which a restore does not preserve), id
  sequences ahead of their tables, `migrate --check` and the system check clean
  on the restore, a forced login served Today, Settings and Opportunities, one
  user's contacts stayed invisible to another, and the stored Gmail refresh
  token decrypted under the key ring. Every drill database was dropped. This
  proves the local restore path, not production scheduling or recovery time on
  the hosting provider.

## Backup and Recovery Plan

Prepared 6 September. Everything here is executable without payment except the
step marked as needing the hosting service to be resumed.

| Element | Decision | Status |
|---|---|---|
| Command | `manage.py backup_db --dest <dir> --keep 14` (pg_dump custom format, private 0600 file, partial files never exposed). | Verified locally today. |
| Client tools in the image | The Dockerfile has no Postgres client, so the command cannot run inside the current image; `pg_dump` must be at least the server's major version. Adding the PostgreSQL 18 client from the PGDG repository to the image is in the release workstream. | In progress. |
| Destination | Private Supabase bucket `networkly-backups` in the existing free `networkly-media` project (created today with the saved S3 credentials; anonymous read returns 400; probe object removed; bucket empty). Dumps are about 12.5 MB, so a 14-snapshot ring is under 200 MB, inside the free allowance. | Ready. |
| Schedule | A suspended Blueprint cron `coverage-db-backup` at 04:15 UTC daily, before the 05:00 trial-expiry and 05:30 watch-renewal block and clear of the 6-hourly scrape, uploading to the bucket with the same `--keep` ring applied there. Defining it is preparation; resuming it is a hosting cost. | In progress; resume after payment. |
| Retention | 14 daily snapshots on the ring (a count, not a time guarantee), plus one manual pre-migration snapshot taken by the operator before every release that carries a migration, kept until the release is accepted. Provider-held copies and the hosting database's own point-in-time recovery are separate and must be read from the Render dashboard once resumed. `[BACKUP RETENTION PERIOD]` on the privacy page stays a placeholder until the founder confirms the number. | Decided. |
| Restore drill cadence | Repeat the local drill after any migration and at least monthly: dump, restore into a new `drill_*` database, compare every table against the dump, run `migrate --check`, force a login, check a tenant boundary, decrypt one stored token, drop the drill database. Never restore into the application or maintenance database. | Procedure verified today. |
| Encryption-key recovery | A dump without `GMAIL_LIVE_TOKEN_KEY` (the Fernet ring, newest key first) cannot decrypt any stored Gmail or Calendar refresh token; users would have to reconnect. The ring lives only in Render's environment and the founder's local `.env`. Store the current ring value in a password manager or sealed offline record that does not depend on Render or this laptop, note the date, and add every new key to that record before it is deployed. `DJANGO_SECRET_KEY` is Render-generated; losing it invalidates sessions and password-reset links but no data, so record it too. Never rotate keys as part of a release. | Owner action; procedure written. |
| Avatars | The database dump does not contain avatar bytes. The private `networkly-avatars` bucket is its own durable store; nothing has been migrated into it yet. When avatars exist, add a weekly object listing plus copy to `networkly-backups/avatars/` to the backup cron, or rely on Supabase's project-level backups once their terms are read. | Decided; depends on the first real avatar. |
| Alerting | The backup cron is a tracked job with a Healthchecks check (`db-backup`, cron `15 4 * * *`, grace 30 minutes, success ping only) and Render's own cron-failure notification. A missed or failed backup therefore alerts on two channels once the check is started. Owner must confirm the Healthchecks and Sentry destination inboxes actually receive mail; see the monitoring section. | Prepared; depends on resumed hosting and inbox confirmation. |
| Recovery time | Local restore of 12.5 MB took about two seconds. On Render, a full recovery is: create a new database, restore beside the live one, verify as above, switch `DATABASE_URL` on every service, redeploy. Expect the switch and redeploy, not the restore, to dominate; measure it once on the deployed environment and record it here. | Unmeasured until deployment. |

## Monitoring Plan

Prepared 6 September from `render.yaml`, `ops/tracking.py` and the local job
history. Jobs ping Healthchecks on **success only**: there is no `/start` or
`/fail` signal in the code, so a check's grace window must cover the whole run
plus scheduler jitter, and a failing job is detected by silence rather than by
a failure ping. Local settings ignore every heartbeat URL (verified today by
the two tests in `ops/tests/test_healthcheck_settings.py`), so nothing here can
be triggered from a laptop.

Apply these in Healthchecks (cron mode, timezone UTC, matching the Blueprint):

| Check | Schedule | Grace | Basis |
|---|---|---|---|
| `scrape` | `0 */6 * * *` | 4 h | Measured locally over 23 runs: median 9 min, p95 2.97 h, max 3.37 h. A one-hour grace would page on a normal run. |
| `gmail-poll` (worker) | simple, period 10 min | 5 min | `EXPECTED_INTERVALS` allows five missed 120 s ticks. |
| `gmail-backfill` | `*/5 * * * *` | 6 min | `TICK_BUDGET` is 300 s; max observed 167 s. |
| `autopilot` | `2-59/5 * * * *` | 6 min | Max observed 17 s; runs are budget-bounded. |
| `gcal-sync` | `4-59/5 * * * *` | 5 min | New job; no history. |
| `assistant-reconcile` | `*/10 * * * *` | 10 min | `EXPECTED_INTERVALS` is 20 min. |
| `weekly-digest` | `0 13 * * *` (daily since the spread change) | 30 min | Sends one seventh of the roster per day under `DIGEST_DAILY_SEND_CAP` (60), so no single day can reach Resend's 100. |
| `push-alerts` | `0 13 * * *` | 30 min | |
| `pro-trial-expire` | `0 5 * * *` | 30 min | |
| `gmail-watch-renew` | `30 5 * * *` | 30 min | Optional job; polling does not depend on it. |
| `db-backup` (new) | `15 4 * * *` | 30 min | Dump is seconds; upload is small. |

That is 11 of the free plan's 20 checks. Keep every check paused or unstarted
until its service is resumed; never send a success ping from outside the
deployed job.

**What is verified and what is not.**

- The Sentry alert "Networkly — New Issues and Regressions" reported
  "Notification fired!" in the UI on the earlier pass. A search of the founder's
  Gmail (`zhujimmy123@gmail.com`) over the last ten days, including spam, found
  **no message from sentry.io**. Either the Sentry account's notification
  address is a different mailbox or the notification did not deliver. Owner:
  open Sentry → Settings → Account → Notifications, confirm the address, and
  check that inbox; re-fire the alert test if needed.
- Missed-job alert delivery from Healthchecks is **untested**. The synthetic
  check that would prove it needs the Healthchecks UI or a project API key;
  this session has neither (the browser extension is not connected and no API
  key is stored), so the test is an owner step: create a check "synthetic
  alert test" with period 1 minute and grace 1 minute, ping it once, wait for
  the down alert to arrive, then delete the check. Do not use any of the ten
  real checks for this.
- The ten real checks all show "Never pinged" and must stay that way until
  production runs them.
- **Source follow-up:** Sixth Street's endpoint was corrected and an EY GET
  recovered; Morgan Stanley's bot wall persists. See the historical audit for
  the earlier board snapshot and its limits.
- **Test evidence (final, second pass):** on the finished tree at `a5886cf`,
  the full suite in an isolated clean worktree passed **11,945, 45 skipped, 0
  failed** (15 min 10 s). On the clean CI runner with no `.env`, `c419c11` (the
  same tree minus the race-test hardening and a checklist note) passed
  **11,977, 13 skipped, 0 failed** in 25 min 34 s with the browser matrix
  running on real Chromium and WebKit, the Docker image built, and `pip-audit`
  clean across 122 pins; the CI run on `a5886cf` itself, with the hardened race
  test, then passed **11,977, 13 skipped, 0 failed** (46 min 55 s on a slower
  runner), image built and audit clean. After that, two clock classes surfaced
  on the CI runner and were fixed: `8098645` failed 39 (import-time date
  snapshots, run straddled midnight UTC), `ff4df89` failed 1 with 11,976
  passed and 13 skipped (a "two hours ago is this week" premise on a Monday
  before 02:00). The fix for the second, with a pinned-clock regression test,
  is the final head `578614e`: CI passed **11,978, 13 skipped, 0 failed** in
  32 min 15 s, Docker image built, `pip-audit` clean. The
  two counts differ by the live-network skips (45 locally, 13 on CI) and the
  matrix. Migration drift: no
  changes. These checks do not establish deployed OAuth, push delivery or
  complete production sync acceptance; live connector tests remain opt-in. The
  earlier figure in this document (11,639) is the handoff's count and is
  superseded.

## Latest Launch Preparation

- Resend accepted a single founder-only setup email using its test sender and
  reported **Delivered**. Application email remains disabled until a domain is
  verified; this does not establish delivery to beta users.
- Sentry's saved alert now covers new issues and regressions, notifies the owner,
  and throttles repeats to 30 minutes per issue. Its test reported
  **Notification fired!**; inbox delivery has not been verified.
- Healthchecks is connected: six existing checks reused and four missing jobs
  added. All ten private URLs are saved locally; all eight existing Render jobs
  have exact-value readback verification. Calendar sync and assistant
  reconciliation URLs await their new services at deployment. All ten checks
  still show Never pinged. Actual missed-job alert delivery remains untested.
  Local settings disable external pings even with production URLs in `.env`.
  After the full-suite run, these monitoring changes passed 46 focused tests.
- The [release runbook](beta-release-runbook.md) covers deployment gates,
  service checks, backups and rollback. CI now checks migration drift, and the
  Docker context excludes additional environment, media and backup artifacts.
  Docker is unavailable locally, so an image build is still a release gate.
- The [Google verification preparation](google-verification-preparation-2026-09-06.md)
  contains scope explanations, truthful data disclosures and a demo storyboard.
  It is not a submitted or approved verification request. A commercial beta below
  100 users is not automatically exempt from verification requirements.
