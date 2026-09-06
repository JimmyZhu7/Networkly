# Networkly: Current Beta Launch Checklist

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
  is 100 emails/day and 3,000/month: 100 digests on one day leave no daily capacity
  for verification or reset messages. Plan delivery within that constraint.
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
| `weekly-digest` | Mondays, 13:00 UTC | Weekly email |
| `push-alerts` | Daily, 13:00 UTC | Deadline push |

The Blueprint also contains legacy trial expiry and optional Gmail watch renewal;
polling does not depend on watch renewal. No production job execution is claimed.
Assistant reconciliation requires direct or session-preserving PostgreSQL
connections: transaction pooling does not support its conversation-lock ownership
guarantee. Its apply mode considers pending turns older than 30 minutes, up to
100 per run; it must acquire the same conversation lock before recovery.

## Deployment Gate and Acceptance

Run `uv run --package coverage-web python coverage_web/manage.py deploy_preflight --launch`
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

## Founder Decisions and Evidence Limits

- **Who to Find remains a decision gate.** Choose a contextual firm-page entry or
  explicit retirement before restoring or removing the capability.
- **Legal details remain placeholders at the founder's request.** Real operator,
  address, jurisdiction and monitored support details, plus privacy disclosures
  matching actual data processing, remain required before a public launch. No
  legal identity or approval is inferred.
- **Backup evidence:** the [restore report](audits/backup-restore-2026-09-06.json)
  records a consistent snapshot of 60 tables with matching row counts and exact
  contents. The temporary restore database was removed. This predates the newest
  migrations and does not establish production backup scheduling.
- **Source follow-up:** Sixth Street's endpoint was corrected and an EY GET
  recovered; Morgan Stanley's bot wall persists. See the historical audit for
  the earlier board snapshot and its limits.
- **Test evidence:** the latest full offline suite passed: **11,639 passed,
  45 skipped, 2 warnings**. Migration drift check reported no changes. The beta
  admission file separately passed 25 tests, including a new invited-user
  onboarding/application journey and cross-account isolation. Authenticated local
  Today, Opportunities, Network, Calendar and Assistant pages loaded without a
  visible error. These checks do not establish deployed OAuth, push delivery or
  complete production sync acceptance; live connector tests remain opt-in.

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
