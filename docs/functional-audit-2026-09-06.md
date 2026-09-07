# Networkly Functional Audit

6 September 2026 · Local checkout on `codex/coverage-ui-refurbishment`

The original audit and test counts below are historical. The
[invited-beta follow-up](#invited-beta-launch-follow-up) records subsequent
implementation and verification, including the now-implemented assistant
recovery/conversation guards and completed local backup restoration.

## Outcome

The workspace has substantial account, CRM, application, calendar, capture,
assistant and billing infrastructure. The audit found and fixed defects in
data completeness, eligibility preservation, scoring, event ordering,
payment idempotency, assistant authorization and credit accounting. It also
filled deployment configuration gaps.

The recommended next release is a **free private beta**, followed by real
integration acceptance testing. Paid Pro and Team remain separate product
work. Their marketing waitlists do not represent implemented paid access.

Use the [founder checklist](product-readiness-2026-09-06.md) for actions on
your side. This report explains the implementation and its limits.

## Implemented Changes

| Area | Defect | Resulting Behavior |
|---|---|---|
| Feed completeness | Six connectors could treat capped, repeated or prematurely empty pagination as a complete board. Downstream logic could infer that unseen jobs had disappeared. | Phenom, Eightfold, Goldman Sachs, Lumesse, McKinsey and Société Générale report incomplete results. Existing ingestion guards preserve unseen jobs when the board response is incomplete. Malformed Phenom envelopes become fetch failures. |
| Eligibility preservation | A repeat listing could derive a graduation year before consulting retained stated facts. | Fact merging precedes derivation; preserved stated graduation windows take precedence. Material changes can still invalidate cached extracted facts. |
| Location truth | A new unmapped location could retain an obsolete market; whitespace could erase the old location. | Silence preserves the stored place. A genuinely changed, unmapped place clears a contradicted region. |
| Duplicate roles | Similar titles could fold together roles with conflicting stated graduation windows or entry routes. | Both duplicate and family folding retain materially different eligibility routes. Existing requisition, location, deadline and sponsorship checks remain. |
| Relationship scoring | Actual referral events did not count as advocate depth or meaningful recency. Future events could affect some score components. | Referrals contribute actual advocacy evidence. Every score component uses evidence available at the requested as-of time. Later explicit demotions still apply. |
| Contact state | Concurrent imports could pass the stale-event check before another writer committed, then overwrite newer state. | Contact-row locking happens before the event-order check. A PostgreSQL lock regression exercises the serialization boundary. |
| Calendar subscription | A cancelled event retained its UID but lacked cancellation/free-time semantics. | Export emits `STATUS:CANCELLED` and `TRANSP:TRANSPARENT` with the existing event identity. |
| Calendar details and authentication | Cleared Google-owned details remained stale; later syncs overwrote mail-derived titles/notes; transient refresh failures revoked grants. | Google-owned rows mirror empty details, mail-derived context survives repeated syncs, and retryable authentication failures keep the grant active for retry. |
| Checkout fulfillment | Different webhook events for the same paid session could grant credits twice. | A unique Checkout Session ID prevents duplicate grants across distinct or concurrent deliveries. The historical event-ID guard remains. |
| Checkout failure | A provider error could produce a server error. | Checkout returns a concise retry message and logs the failure category without exposing provider details. |
| Assistant authorization | A model-supplied `confirmed=true` could authorize sensitive settings changes. | Approval comes from a saved proposal followed by the user's next explicit confirmation. It binds the field, new value and prior value; a model flag alone cannot authorize the write. |
| Assistant credits | Concurrent turns could both start on the same remaining credit; an interrupted stream could strand a charge. | Credits are reserved atomically before provider work. Failed and interrupted turns refund; successful turns retain one charge. The existing deliberate one-action overdraw policy is preserved. |
| Gmail watches | Renewing a watch could overwrite the processed history cursor and skip unprocessed mail. | Watch renewal preserves an existing cursor and conditionally initializes only an empty one. Concurrent poll progress is retained. Invalid grants are recorded as revoked; retryable authentication and topic errors remain retryable. |
| Gmail outage recovery | Expired history re-anchored to the present without scheduling recovery of the gap. | Re-anchoring atomically queues the existing free deterministic backfill, preserves active queue work and rejects stale/revoked callers. It does not initiate a paid rescan. Recovery is bounded by the existing backfill scope. The OAuth callback also reports a revoked grant honestly. |
| Rescan billing | Failed classification requests were counted as processed and charged. | Only returned classifications are billable. Failed requests are counted separately, and provider outages are distinguished from credit limits. |
| Calendar operations | Calendar sync lacked a scheduled production job and job-health recording. | The Blueprint includes an optional five-minute job. Applied sync records health and exits unsuccessfully when any connection fails, after processing the remaining connections. Dry-run behavior remains the default. |
| Worker configuration | Email jobs could use the wrong public origin/sender; the backfill worker lacked the web service's AI key. | Explicit service inheritance supplies the origin, sender and AI key where needed. No external service was provisioned or enabled by this edit. |
| Deployment checks | Preflight omitted Calendar readiness, upload persistence and several incomplete integrations. | Checks expose those gaps and avoid treating key presence as proof of live delivery or approval. Secret values are never printed. |
| Dependencies | The installed dependency audit reported known advisories. | Django was updated to 5.2.17, cryptography to 50.0.1 and sqlparse to 0.6.0, with the lockfile refreshed. The subsequent installed-package scan reported no known vulnerabilities. |
| Test isolation | Two domain-test entry points defaulted to the PostgreSQL maintenance database. | An explicit test DSN is required and the connected database name must begin with `test_`. Both entry points refuse app/maintenance databases before executing SQL. CI creates a dedicated domain-test database. |

The unique paid-session field is introduced by
`networkly_web/billing/migrations/0010_processedstripeevent_stripe_checkout_id.py`.
Production deployment must run migrations before accepting webhook traffic.
Historical rows do not have a stored session ID; if an existing deployment
already processed payments, reconcile old paid sessions before replaying
distinct historical events. Stripe is unconfigured in the inspected local
environment.

Dependency update references: [Django release notes](https://docs.djangoproject.com/en/5.2/releases/5.2.17/),
[cryptography changelog](https://cryptography.io/en/latest/changelog/),
[sqlparse changelog](https://sqlparse.readthedocs.io/en/latest/changes.html).
An advisory scan is not proof that the application has no security defects.

## Networkly and Product Decisions

| Product Surface | Review / Validation Scope | Remaining Boundary |
|---|---|---|
| Onboarding, Settings and authentication | Existing account, profile, trial, export/deletion, security and isolation regressions are included in the main suite. Deployment checks inspect configuration without printing secrets. | Public signup, account email, Google login and deletion must be exercised with a dedicated staging account and real provider configuration. |
| Today and contact workflows | Cadence, scoring, event ordering, pause/resume, interaction state and tenant-scoped service tests. | Priorities are heuristics, not measured reply or offer probabilities. Validate representative histories with beta users before tuning weights. |
| Opportunities and applications | Eligibility gates, diversification, deadline windows, stored facts, ingest safeguards, duplicate folding and save-time rechecks. | This is not a newly labeled relevance study or a live availability audit of all providers. |
| Gmail capture | Cursor handling, mailbox locks, attribution, chronological processing, replay boundaries, deterministic capture and paid residue classification. | Real OAuth permission, mailbox examples and provider accuracy were not tested through live accounts. |
| Calendar | Separate grant, event identity, cancellation, recurrence, optional-field clearing, provenance and command health. | Reconciling missing events after cursor expiry needs additional work; see below. |
| Assistant | Tenant-scoped tools, important-setting approvals, provider failure behavior, credit concurrency and stream cancellation. | No paid model evaluations were run. Concurrent conversation turns and hard-process-kill reconciliation remain concerns. |
| Billing | Credit packs, ledger behavior, webhook races and provider errors. | Paid Pro entitlement lifecycle, Team workspaces, automated refund/dispute handling and customer portal are not implemented. |
| Operations | Blueprint wiring, job tracking, preflight, migration consistency, dependency scan and test isolation. | No deployment, external alerts, live emails, backup restoration or scheduler provisioning was performed. |

No recommendation weights were changed just to produce a different ranking.
The algorithm edits correct evidence handling and consistency. The founder
checklist includes a small labeled role/contact evaluation so future ranking
changes can be assessed against user outcomes.

The existing “Who to Find” capability has no active user-facing caller. It
was left intact because a prior founder decision gate requires choosing its
entry point or retirement before changing that behavior.

Detailed source evidence and connector tests are in the
[directory audit](audits/directory-functional-2026-09-06.md). Its
[140-board snapshot](audits/directory-source-status-2026-09-06.json) records
stored status, not a new live scrape. The `wiped` classification is an alert
from firm/provider aggregate counters, not proof that an individual board
lost data.

## Verification

| Check | Result |
|---|---|
| Full workspace suite | **11,377 passed, 13 skipped, 1 failed** in 762.63 seconds. The failure was a new test incorrectly expecting the public credit balance to display a negative number. The concurrency outcome was correct. The test now checks the zero display, negative ledger total and single charge separately. |
| Capture, assistant and billing follow-up | **2,288 passed, 1 failed** in 366.42 seconds. The new provider-outage test lacked the contact required to start its scan. The fixture was corrected and the test now asserts that all three mocked provider attempts ran. No product change was needed for this failure. |
| Final targeted regression pass | **164 passed** in 30.98 seconds. Covers both corrected tests, Gmail watch/recovery/rescan, Calendar synchronization and consent, assistant approval/reservation, and Stripe fulfillment. No known test failures remain from the audit. |
| Domain suite with explicit disposable PostgreSQL database | **612 passed**. Includes both SQL backends and real PostgreSQL concurrency. |
| Earlier combined account, CRM, billing and core regression batch | **1,585 passed, 1 skipped**. |
| Calendar command and operations checks | **93 passed**. |
| Post-fix ingest and operations batch | **113 passed**. |
| Installed dependency advisory scan | **No known vulnerabilities found** after the dependency updates. The preceding scan found seven advisories across three installed packages. |
| Django checks / migration consistency | System check clean; `makemigrations --check --dry-run` reports no changes. |
| Local schema | Billing migration `0010` applied successfully to `coverage`. All local migrations applied; no production migration executed. |
| Local deployment preflight | **7 pass, 11 warnings, 0 failures**. Warnings correspond to local configuration and launch setup; this is not a production readiness certificate. |
| Diff whitespace | `git diff --check` clean. |

The full workspace suite was not repeated after the final targeted pass;
the later runs cover the changed capture, assistant and billing paths. The
full-run skips comprise 12 explicitly opt-in live ATS checks and one
unseeded-directory account case. Its warning is Django's deprecated
`FORMS_URLFIELD_ASSUME_HTTPS` transitional setting. Test counts include
parameterized cases, not that many independent end-user journeys. Earlier
batches overlap with the full run and must not be added together.

Logs are local under `/tmp/networkly-functional-*.log`. Meaningful regressions
failed before the corresponding billing, ingest, connector and dedupe fixes.

Tests use mocked provider responses and isolated PostgreSQL databases. They
do not establish live Gmail, Calendar, AI, email or Stripe operation. The
main suite runs serially to avoid shared-database interference.

## Second Pass, 6 September Afternoon

The handoff above was committed as revision `38b38c6` and taken over by a
release-owner pass that ran four parallel workstreams (release and
configuration, local user journeys, algorithms and data integrity, security
and privacy) on isolated worktrees with exclusive file ownership, merged each
behind focused tests, and closed the review findings in files nobody owned.
The current checklist, [product readiness](product-readiness-2026-09-06.md),
carries the results, the evidence, the classified unfinished items and the
after-payment order of operations; this section records only what changes
the statements made earlier in this document.

- **Follow-up 1 (Calendar reconciliation)** shipped in the handoff and was
  probed again: absence after cursor expiry does not imply cancellation, and
  mail can no longer take over or move a Google-owned meeting when the
  calendar side arrives first.
- **Follow-up 2 (AI crash accounting)**: `assistant_reconcile --apply` exists
  and is scheduled; hard-kill, mid-stream disconnect, refund-exactly-once and
  two-worker cases are covered by the durable-turn tests and were re-probed
  without finding a gap.
- **Follow-up 3 (conversation concurrency)**: a second turn in the same
  conversation is rejected before provider, history or credit work; covered.
- **New defects fixed in the second pass**: a repair command that wrote a
  heuristic graduation year over a stated window; the credit burst guard's
  day boundary belonging to UTC from a cron tick; two Today counts that
  accepted future-dated touches; `Firm.logo_url` raising on the public feed
  for 11 firms; a heartbeat failure logging the ping credential; the Stripe
  webhook echoing provider text; deletion leaving other devices signed in;
  the delete page understating what deletion removes; keyboard-unreachable
  assistant regions on a phone; the public university search unthrottled;
  and the privacy page's claim that AI classification happens only on Scan
  Now, when ordinary sync already sends subjects and snippets.
- **The suite's verdict no longer depends on the machine.** Beta flag, VAPID
  keys and the Gmail live client are now defaults set by the root conftest
  and the tests that need them; the CI test job on a runner with no `.env`
  is the independent check.
- **The Verification table above is historical.** The integrated suite on the
  final tree is recorded in the readiness checklist's test evidence with its
  exact count, together with the clean-runner CI result on the pushed head.
- **Still open**: reschedule and cancel as user actions on the calendar (in
  progress), and everything the readiness checklist classifies as needing
  payment, an owner decision or Google's approval.

## Remaining Engineering Follow-Ups

1. **Calendar reconciliation:** handle missing events after an expired sync
   cursor. Do this before promising full Calendar mirror fidelity.
2. **AI crash accounting:** normal failures and browser cancellation refund,
   but a hard process termination cannot run cleanup. Reservation IDs permit
   investigation; automatic stale-reservation reconciliation is not shipped.
3. **Conversation concurrency:** evaluate overlapping turns in one assistant
   conversation, including ordering, tool context and user-visible recovery.
4. **Paid product lifecycle:** define Pro duration/expiry/refunds and Team
   membership/permissions before building paid entitlements. Credit-pack
   checkout does not unlock Pro.
5. **Source operations:** verify degraded boards from the deployment host and
   agree an authorized coverage process for blocked sources. Do not infer
   zero hiring from a bot wall.
6. **Outcome evaluation:** maintain representative, labeled role and contact
   histories. Mocked rule tests cannot establish model accuracy or usefulness
   across the launch cohort.

## Test-Database Incident

During this audit, a domain-test agent ran an existing standalone test whose
fallback DSN was `postgresql:///postgres`. The test committed drops and
recreation of `contacts` and `touches` in the **`postgres` maintenance
database**, then inserted one synthetic row into each table.

This was an unintended database modification by the audit. The unsafe
fallback was pre-existing, but executing it was our error. The main Django
application is configured for a different database, **`coverage`**. A
read-only check found 4 users, 384 contacts and 659 touches there; the
mistaken test targeted `postgres`, not that application database. The prior
contents of the two maintenance-database tables are unknown, so data loss
cannot be ruled out.

No cleanup or speculative restoration was attempted. The two affected tables
were left intact for investigation. The local backup folder contained an
application backup from 17 August 2026; that is not evidence of a backup of
the maintenance database or its previous table contents.

Both dangerous defaults have been removed. Regression tests verify refusal
of app/maintenance database names before SQL executes. Subsequent domain
tests use an explicitly created disposable database and CI now provisions
its own. The audit's disposable database was removed after validation. If
those maintenance-database tables contained anything important,
identify the relevant backup or recovery source before making further
changes there.

The separate read-only application fixture audit also flagged one reserved-
domain debug account created on 2 September, before this task. It was left
untouched for review; this audit did not delete user or fixture records.

## Change Boundaries

Unrelated firm-logo and UI edits already present in the checkout were
preserved. This task did not send email, make purchases, call paid models,
change external credentials, deploy, or intentionally create fixtures in
the user's application records. The accidental maintenance-database write
is disclosed above. The final local migration status is recorded with the
verification results.


## Invited-Beta Launch Follow-Up

The founder chose **free invitation-only access to all individual features,
up to 100 people, with no enterprise or paid launch**. A centralized effective
plan grants individual Pro capabilities without changing stored billing
plans. AI credits/daily limits remain bounded. Invitation admission counts
existing users and reservations, preserves consumed seats after deletion
and serializes claims. New Stripe checkout is blocked while beta is enabled;
Stripe configuration and paid entitlement development are not launch gates.

Subsequent source changes supersede the corresponding earlier follow-ups:

- Assistant turns now have durable `assistant_turn_reservations` records, atomic debit/settlement/refund and a dedicated PostgreSQL session lock per conversation. Overlapping turns fail usefully before provider work or history changes; no ordinary transaction spans a provider call. `assistant_reconcile` defaults to preview, and `--apply` considers pending turns older than 30 minutes while requiring the same ownership lock. Age alone cannot refund an active long turn. The Blueprint schedules recovery every ten minutes. Prior-turn server-owned settings confirmation remains intact. Deployment requires direct/session-preserving PostgreSQL connections.
- Calendar cursor recovery verifies missing Google-owned events individually after a full windowed read. Absence alone does not imply cancellation; manual/mail-owned records are preserved. Incomplete/failed verification must not advance the cursor. Real provider acceptance remains outstanding.
- Private S3-compatible avatar storage and an authenticated ownership-checked media route are implemented. The migration command previews before copying existing local avatars. Provider credentials, bucket privacy, persistence and actual migration are separate deployment work.
- `deploy_preflight --launch` requires beta mode/capacity, production HTTPS/login, Gmail/Calendar, shared Redis, email, private durable storage, VAPID, Sentry and Anthropic configuration. It performs no provider calls; missing required configuration fails, while Stripe is unnecessary in beta. Default nonlaunch optional-feature warnings remain. `--warn-only` bypasses the failing exit and is not a successful launch gate. New isolated configuration regressions cover missing/unsafe settings, capacity errors, secret redaction and beta Stripe exemption.
- Sixth Street's source endpoint was corrected and a follow-up EY GET recovered. Morgan Stanley still presents a bot wall. These do not constitute a fresh successful scrape of every board.

**Verified local restore:** [the report](audits/backup-restore-2026-09-06.json)
records exact-content and row-count agreement for all **60 tables** from one
shared exported snapshot. The temporary database was removed. The private
`0600` dump is `/Users/zhujimmy/Backups/coverage/launch-readiness-2026-09-06/coverage_consistent_41a593dcd55b.dump`.
This validates the application snapshot, not the previously modified
maintenance-database tables, production backup scheduling or recovery of the
later invitation/reservation schema.

**Live Google observation, 6 September:** the existing project
`project-71aa6735-1289-4c5d-a15` is External / In production, displaying **4/100**
on its unverified lifetime user cap. Production mode is retained. The founder
completed two-step verification and the display name was saved as Networkly.
At this checkpoint, saved scopes were blank and client/API/permission changes
had not been made; Render awaited founder login. These are setup observations,
not a verified complete OAuth flow. Testing's named-user and seven-day
Gmail/Calendar authorization limits are conditional on entering Testing;
they are not instructions to change this project's existing production state.
The app invitation count does not measure Google's lifetime usage.
[Google's audience and user-cap guidance](https://support.google.com/cloud/answer/15549945).

**New test evidence:** the parent-run follow-up batch reported **281 passed**
for beta admission/entitlements, export, billing, Gmail gates/polling, trials
and Render wiring. This does not validate the subsequent assistant durability,
Calendar recovery, storage and launch-gate changes; updated serial validation
for those is pending at this checkpoint. Earlier audit counts remain scoped
to their recorded runs and must not be added together or presented as a
current full-suite pass.

The remaining founder work is provider accounts/credentials/funding, domain,
production deployment and genuine integration acceptance. Real legal operator
placeholders remain unchanged at the founder's explicit request. The
[updated checklist](product-readiness-2026-09-06.md#current-launch-follow-up)
keeps those requirements distinct from completed source work.
