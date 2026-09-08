# Billing and Assistant Reliability Review

Review date: September 7, 2026. Scope: the free, individual 100-user beta.
All verification used an isolated worktree and test database. No real AI,
Stripe, email, or other paid requests were made. This is regression evidence,
not a guarantee against all future provider failures or arbitrary load.

## Implemented Fixes

- Reserve non-chat credits before a provider request. A durable, tenant-owned
  `AIJobReservation` records each started and completed unit, partial outcomes,
  settlement, and abandoned-worker recovery. Repeated job keys cannot execute
  twice. Short transactions lock the active user before reservation/ledger
  rows; provider requests run outside those transactions.
- Refund unused units once. An interrupted in-flight unit remains chargeable
  because the provider may have processed it; recovery releases unstarted
  work and prevents the old worker from continuing. The existing
  `assistant_reconcile` command handles both chat and non-chat recovery.
- Attribute linked refunds to the original debit's day and month, so a late
  refund cannot expand today's budget or cancel unrelated usage. Refunds
  cannot exceed the source debit or target another user's spending.
- Bound non-chat attempts independently of refunds: 60 admitted reservations
  per account per hour, and 600 started provider units per account per hour,
  shared across job kinds. The unit window is conservative: units in a batch
  active within the last hour also count. These safeguards do not change
  credit prices. Failure/empty-answer loops cannot renew unlimited attempts.
  Chat additionally admits at most 60 attempts per hour per account; refunded
  debit records still count and both sync/stream responses explain the limit.
- Serialize free daily-brief and contact-summary generation per account with
  a dedicated PostgreSQL advisory-lock session. Cached briefs remain free;
  actual daily-brief generation is limited to 10 attempts per hour and fails
  safely if the shared cache is unavailable. The recruiting workstream owns
  contact-summary integration with the same lock.
- Close internally created AI HTTP clients on success, provider failure, and
  interrupted streams. Injected clients remain owned by their callers.
- Make assistant mutations and domain writes one transaction using the capture
  workstream's shared transaction adapter. Recheck the active account under its
  row lock. Concurrent draft-log clicks create one touch; concurrent memory
  writes cannot exceed the cap; Save cannot erase a newer application stage.
- Admit coffee-chat brief generation before calling its provider and release
  unused credits on failure or unavailability.
- Commit rewind deletion and the edited message together under the active
  account lock. A failure rolls back original text, attachments and later
  replies. If an earlier edit removed the target, return a controlled stale
  message response instead of deleting more history or raising a server error.
- Treat loss of the original conversation-lock session as terminal for that
  worker. Show an ephemeral notice without persisting a stale failure reply
  or title. Expired non-chat completion cannot renew the lease before
  reconciliation or revive the old worker's allowance.
- Load conversation history in pages of at most 60 stored messages, with a
  stable, tenant-scoped `(created, id)` cursor. New replies do not shift older
  pages. Display reads strip stored file payloads and tool inputs/results in
  PostgreSQL while preserving filenames, prose, draft controls, and tool names.
  Older pages remain available through keyboard-accessible links, including
  without JavaScript. Enhanced loading preserves the visible message position
  and offers a retry after a failed fetch.

## Module Review and Regression Map

| Modules | Boundaries reviewed and exercised |
| --- | --- |
| `billing/credits.py`, `models.py`, `job_budget.py` | Monthly grants, plan reconciliation, concurrent final credit, daily/timezone limits, partial settlement, linked refunds, duplicate attempt keys, recovery, closure, tenant scoping, attempt caps and final-slot races. |
| `billing/stripe_gateway.py`, `views.py`, `urls.py` | Configuration/beta guards, checkout metadata, paid-only grants, signed webhook failures, event/session deduplication, private settings, waitlist validation and rate limits. Provider calls were mocked. |
| `billing/admin.py`, `apps.py` | Staff credit adjustments, audit fields, registered configuration. |
| `assistant/agent.py`, `client.py`, `metering.py` | Sync/stream replies, input and tool-loop bounds, credits, provider failures, interrupted streams, resource ownership, durable settlement and account lifecycle. |
| `assistant/locks.py`, `lifecycle.py`, `recovery.py`, `management/commands/assistant_reconcile.py` | Dedicated-session ownership, lock namespaces, process/connection-loss behavior, active-user checks, dry-run versus applied recovery, bounded batches. |
| `assistant/tools.py`, `confirmation.py` | Tool allowlists, tenant reads, write confirmation, user/contact mutations, application-stage preservation, atomic domain writes, settings and memory limits. |
| `assistant/views.py`, `urls.py`, history/message templates | Authentication, ownership, conversations/folders, draft logging, edit/retry actions, credits/history fragments, bounded history, attachments, keyboard loading and scroll behavior. |
| `assistant/attachments.py`, `drafts.py`, `mismatch.py`, `templatetags/assistant_extras.py` | Attachment types/count/size, payload extraction, escaped rendering, draft parsing, mismatches, safe draft actions and formatting. |
| `assistant/brief.py`, `situation.py`, `plans.py`, `models.py` | Daily cache/staleness, quiet-day behavior, source-bound summaries, prioritization, plan/model limits, account generation ownership and stored relationships. |
| `crm/views.py::contact_ai_brief` | Configuration and tenant checks, last-credit race, admission before provider work, refund/no-answer behavior and response rendering. |
| `capture/autopilot.py` | Reservation integration and pipeline safety are owned and documented by the capture-integrity workstream; this review supplies and tests the shared budget API. |

## Validation

- Before the final pagination/attempt changes: 1,287 billing, assistant and
  coffee-brief tests passed.
- Pagination, draft rendering and durable job-budget focused suite: 66 passed.
- Final focused pagination, tenant-isolation, ownership/lifecycle and job-budget
  suite: 70 passed. The whole-package isolation guard also covers test fixtures.
- Actual Chromium and WebKit, at desktop and narrow mobile widths: four
  history-pagination tests passed. These exercise keyboard activation,
  temporary HTTP failure/retry, scroll preservation, full older-message access,
  attachment filenames and absence of horizontal overflow.
- Combined assistant/billing/coffee-brief scope plus the four browser cases:
  1,307 passed. The integrated cross-workstream gate is recorded separately.
- Final independent-review fixes: 211 focused tests passed across durable
  turns, new fault boundaries, credit reservations, account lifecycle, views,
  non-chat budgets and coffee briefs. Cases include actual ownership-session
  closure, sync/stream rewind rollback, stale edit targets, expired completion
  and refunded chat-attempt limits. The sole warning is Django's existing
  `FORMS_URLFIELD_ASSUME_HTTPS` deprecation.

The source/module map describes the reviewed contracts, not numerical line
coverage. Existing regression matrices plus new concurrency, lifecycle and
browser tests provide the evidence; real-provider behavior remains separate.

## Integration and Deferred Live Checks

1. Apply billing migrations `0011` and `0012` when services resume. Include
   `AIJobReservation` in account export/deletion policy; the integration owner
   implements and tests those cross-cutting lists.
2. Run the integrated suite after all workstream commits land; concurrent
   test runners must use distinct worktrees and test databases.
3. On paid hosting, verify the real AI credentials/model permissions, timeout
   behavior, stream disconnects through the production proxy, and recorded
   usage with a bounded smoke test. This was not done locally.
4. Verify `assistant_reconcile --apply` is scheduled and its job monitoring
   is live; test a synthetic abandoned job after hosting is activated. No real
   reservation or production job was started in this audit.
5. Load-test the deployed PostgreSQL/shared-cache connection budget and
   provider latency at the planned beta concurrency. Local final-slot races
   and process-death tests are not a production capacity measurement.
6. Stripe checkout/webhook delivery needs a sandbox integration check only if
   paid top-ups are later enabled. The current free beta does not require
   checkout or an enterprise tier.
