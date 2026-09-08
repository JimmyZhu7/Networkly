# Networkly Deep Functional Audit

7 September 2026. Baseline: `3d2c49d`. Target: the free individual beta, capped at 100 admitted users. This report continues the [earlier reliability pass](functional-reliability-2026-09-07.md).

## Outcome

Four parallel workstreams reviewed accounts and operations, recruiting and ranking, capture and connectors, and billing and the assistant. Fixes were integrated in a separate checkout with disposable PostgreSQL databases. Customer data, paid hosting, provider credits, and deployment settings were not changed.

This is a broad source and regression audit with measured limits. It does not prove that every branch is correct, every external integration works live, or 100 simultaneous users fit the intended hosting plans. The function inventory records execution evidence and explicitly identifies functions not exercised by the gate.

## What Changed

| Surface | Reliability improvement |
| --- | --- |
| Gmail and Calendar | Current-account and exact-grant checks fence reconnect, disconnect, revocation, sync, backfill and rescan writes. Domain and Django writes share one transaction; a failed checkpoint rolls back the associated contacts, interactions and evidence. Provider requests run outside row-lock transactions. |
| Capture review | Decisions reload current owned rows. Duplicate taps cannot create duplicate contacts or interactions. Each accepted decision commits its effects and undo information together; failed batches resume complete decisions. Stale undo preserves subsequent user changes. Inactive jobs retire without recreating account data. |
| AI budgets | Non-chat jobs reserve before calling a provider, record started/completed units, settle partial results, and refund unused allowance once. Recovery fences abandoned workers. Refunds remain attached to the original spending period. Failed/refunded attempts have separate bounds. |
| Assistant | Mutations share the account/deletion lock and domain transaction. Concurrent draft logging creates one interaction; memories obey their cap; saving a role preserves newer application stages. Internally created HTTP clients close on normal, failed and interrupted requests. |
| Conversation history | Pages load at most 60 stored messages and exclude attachment bodies and tool payloads from display queries. Older history stays accessible with tenant-scoped cursors, keyboard controls, stable scroll position and retry behavior. Stored history is retained. |
| Free summaries | Daily briefs and relationship summaries serialize per account. Actual generation is bounded independently of credits; cached and deterministic results remain available. Automatic mail classification stays free to users, prepares before local writes, and has a separate bounded provider allowance. |
| Today and Network | A streaming reducer preserves all-time counts and latest relevant evidence without loading every interaction and note body. Cadence ordering and delays use actual instants across daylight-saving changes. |
| Opportunities | Ranking projects only the facts it needs and reuses candidate objects. Existing eligibility, scores, explanations and grouping remain intact. |
| Contact edits and firm maintenance | Contact forms update their owned fields without replacing background state. Duplicate-firm maintenance preserves linked contacts, tasks, application evidence and change history; ambiguous conflicting decisions require review. Derived observations are rebuilt rather than double-counted. |
| Contact import | CSV size/row bounds and strict parsing reject malformed files before contact writes. Owned imports and bookkeeping commit together; overlapping imports serialize. Unsafe LinkedIn URL schemes are rejected. |
| Account exports and deletion | ZIP and individual CSV downloads use spooled files and batched queries. Fit-score names resolve per batch. Files and generators close on errors/disconnects. New AI job records are included in export/deletion; deletion serializes with writers. |
| Device notifications | Settings checks the current browser endpoint against that account's subscriptions. Another device cannot make this one appear enabled. Unknown/error states remain retryable; the page does not request permission on load. |
| Provider responses and monitoring | Malformed, partial or inconsistent job-board envelopes fail verification rather than incorrectly declaring roles open or closed. Private calendar/unsubscribe bearer tokens are redacted from monitoring URL paths. Browser tests now flag failed action requests. |

Implementation evidence is detailed in the [recruiting review](recruiting-reliability-2026-09-07.md), [AI review](ai-budget-assistant-deep-review-2026-09-07.md), and [capture review](capture-integrity-2026-09-07.md).

## Final Verification

Final integrated results and function execution inventory are recorded here after the frozen-source gate completes.

## Measured Capacity

The synthetic benchmark contains 100 account rows. One heavy account has 2,000 contacts and 200,000 interactions; the other 99 accounts supply 9,900 additional interactions. The shared board contains 3,000 eligible open roles with substantial provider payloads.

| Operation | Median before | Median after | Peak Python allocations before | After |
| --- | ---: | ---: | ---: | ---: |
| Today action reducer | 2.938 s | 1.573 s | 588.37 MiB | 9.65 MiB |
| Personalized ranking | 0.509 s | 0.228 s | 166.13 MiB | 18.68 MiB |

All 2,000 actions and six selected recommendations matched the baseline, including scores, explanations and grouped places. Timing used ordinary passes; allocation tracing ran separately. These are local reducer measurements, not HTTP latency, process RSS, production throughput or 100 concurrent users. [Reproduction and complete metrics](recruiting-reliability-2026-09-07.md#reproducible-capacity-check).

## Remaining Checklist

Payment alone does not complete these checks. Items marked as needing active services remain unproven until exercised against the actual deployment.

| Item | Dependency | Completion evidence |
| --- | --- | --- |
| Activate the approved web, database, worker and required scheduled jobs | Paid Render activation; currently not authorized | Matching release SHA, successful migrations and launch preflight, healthy web/worker, completed scheduled jobs. Apply new billing migrations `0011` and `0012` before dependent workers start. |
| Exercise real AI calls and abandoned-job recovery | Funded provider credits and active runtime | Controlled requests, streaming disconnect/timeouts, correct usage/refunds, and a synthetic abandoned reservation settled by `assistant_reconcile --apply`. |
| Finish domain and sending-email setup | Domain purchase and DNS access | Verified sending domain, correct web/TLS routes, signup and digest emails received in dedicated test inboxes. |
| Run authenticated Google acceptance | Dedicated test accounts and active services; account access is also required | Signup, invite/admission, Gmail and Calendar consent, refresh/reconnect/revoke, sync and account deletion, with expected records and no cross-account effects. Confirm the chosen Google test-user/scopes configuration. |
| Verify actual notification and upload delivery | Active deployment and test devices | Browser-specific subscription state, delivered/clickable push, signed private avatar access, expired/foreign URL denial, and native Safari testing. Chromium/WebKit tests do not replace native Safari delivery. |
| Verify monitoring and backups | Active jobs, off-host storage and owner-controlled inboxes | Received Sentry alert, synthetic missed-job alert, successful scheduled backup, restore into a separate database and content comparison. Keep real suspended job checks quiet until services resume. |
| Complete owner/security setup | Owner action; generally not a software purchase | Store recovery keys off this laptop and outside Render; confirm monitoring notification address; replace legal operator/contact placeholders before public launch; decide domain/repository visibility and pilot claims. No invented legal or traction facts. |
| Measure actual concurrent usage | Running staging services on the intended plans | Concurrent core journeys plus background jobs, p95/p99 latency, error rate, worker memory, database connection usage, cache/provider failure and recovery. Admission cap alone is not capacity proof. |
| Run payment acceptance only if paid top-ups are enabled later | Stripe sandbox/account setup; not required for the free beta | Signed webhook delivery/replay and checkout/grant reconciliation. No enterprise version is required. |

## Engineering Limits to Keep Visible

- Today still scans historical interaction evidence. Memory is much lower, but the heavy-account action reducer still took 1.57 seconds. An incremental stored summary needs transactional updates, repair/backfill and parity evidence before replacing exact scans.
- Ranking still evaluates the eligible catalog. Larger catalogs need measurement before adding materialization; truncating candidates would change useful results.
- Contact mailbox backfills can still walk large histories and accumulate message IDs/findings. Existing page validation, sent-sweep and AI caps are safeguards, not a measured queue-lag or maximum-mailbox guarantee. Measure this on controlled large mailboxes before broad activation.
- Session advisory locks require a session-affine PostgreSQL connection. Do not switch these paths to transaction pooling without revisiting lock ownership. Cache-based free-feature limits depend on the shared cache; cache resets can reopen a window.
- Individual provider calls already sent cannot be reliably cancelled by deleting an account or losing a worker. Local writes are fenced afterward, and uncertain started work is conservatively accounted for.
- The test inventory contains unexecuted administrative/provider/error branches. Coverage is a map for follow-up, not proof that every function is bug-free. Real-service acceptance and ongoing dependency/provider monitoring remain necessary.

No paid service was resumed and no deployment was triggered by this audit. GitHub publication, if performed, is source publication only.
