# Networkly Deep Functional Audit

7 September 2026. Baseline: `3d2c49d`. Target: the free individual beta, capped at 100 admitted users. This report continues the [earlier reliability pass](functional-reliability-2026-09-07.md).

## Outcome

Four parallel workstreams reviewed accounts and operations, recruiting and ranking, capture and connectors, and billing and the assistant. Fixes were integrated in a separate checkout with disposable PostgreSQL databases. Existing business records were retained. The local database was backed up and received two additive billing migrations after a successful isolated restore drill. Paid hosting, provider credits, and deployment settings were not changed.

This is a broad source and regression audit with measured limits. It does not prove that every branch is correct, every external integration works live, or 100 simultaneous users fit the intended hosting plans. The function inventory records execution evidence and explicitly identifies functions not exercised by the gate.

## What Changed

| Surface | Reliability improvement |
| --- | --- |
| Gmail and Calendar | Current-account and exact-grant checks fence reconnect, disconnect, revocation, sync, backfill and rescan writes. Domain and Django writes share one transaction; a failed checkpoint rolls back the associated contacts, interactions and evidence. Provider requests run outside row-lock transactions. |
| Capture review | Address-change notes retain the exact supporting phrase, including the full new address, without changing the original contact email. Decisions reload current owned rows. Duplicate taps cannot create duplicate contacts or interactions. Each accepted decision commits its effects and undo information together; failed batches resume complete decisions. Stale undo preserves subsequent user changes. Inactive jobs retire without recreating account data. |
| AI budgets | Non-chat jobs reserve before calling a provider, record started/completed units, settle partial results, and refund unused allowance once. Recovery fences abandoned workers; expired completion cannot renew a lease. Refunds remain attached to the original spending period. Failed/refunded chat and non-chat attempts have separate bounds. |
| Assistant | Mutations share the account/deletion lock and domain transaction. Concurrent draft logging creates one interaction; memories obey their cap; saving a role preserves newer application stages. Message rewind rolls back as a unit and rejects stale targets. Workers that lose ownership return an unsaved notice. Internally created HTTP clients close on normal, failed and interrupted requests. |
| Conversation history | Pages load at most 60 stored messages and exclude attachment bodies and tool payloads from display queries. Older history stays accessible with tenant-scoped cursors, keyboard controls, stable scroll position and retry behavior. Stored history is retained. |
| Free summaries | Daily briefs and relationship summaries serialize per account. Actual generation is bounded independently of credits; cached and deterministic results remain available. Automatic mail classification stays free to users, prepares before local writes, and has a separate bounded provider allowance. |
| Today and Network | A streaming reducer preserves all-time counts and latest relevant evidence without loading every interaction and note body. Cadence ordering and delays use actual instants across daylight-saving changes. |
| Opportunities | Ranking projects only the facts it needs and reuses candidate objects. Existing eligibility, scores, explanations and grouping remain intact. |
| Contact edits and firm maintenance | Contact forms update their owned fields without replacing background state. Duplicate-firm maintenance preserves linked contacts, tasks, application evidence and change history; ambiguous conflicting decisions require review. Derived observations are rebuilt rather than double-counted. |
| Contact import | CSV size/row bounds and strict parsing reject malformed files before contact writes. Owned imports and bookkeeping commit together; overlapping imports serialize. Unsafe LinkedIn URL schemes are rejected. |
| Account exports and deletion | ZIP and individual CSV downloads use spooled files and batched queries. Fit-score names resolve per batch. Files and generators close on errors/disconnects. New AI job records are included in export/deletion; deletion serializes with writers. |
| Device notifications | Settings checks the current browser endpoint against that account's subscriptions. Another device cannot make this one appear enabled. Unknown/error states remain retryable; the page does not request permission on load. |
| Provider responses and monitoring | The retained legacy dismissal route rejects oversized keys without a server error. Board selection preserves provider/firm intersections, order and limits. Malformed, partial or inconsistent job-board envelopes fail verification rather than incorrectly declaring roles open or closed. Private calendar/unsubscribe bearer tokens are redacted from monitoring URL paths. Browser tests now flag failed action requests. |

Implementation evidence is detailed in the [recruiting review](recruiting-reliability-2026-09-07.md), [AI review](ai-budget-assistant-deep-review-2026-09-07.md), and [capture review](capture-integrity-2026-09-07.md).

## Final Verification

The final runtime and deployment configuration are frozen at **`99be0dc`**. Local verification used Python 3.13 and PostgreSQL 18; the GitHub suite uses Linux, Python 3.13 and PostgreSQL 16.

| Check | Result | Scope |
| --- | --- | --- |
| Final application and connector gate | **11,888 passed; 14 gated skips** | 13m39s; all **1,133 source/test/asset/configuration files** matched before and after. |
| Domain gate | **625 passed** | Exact domain source is unchanged in the final runtime; separate disposable database. |
| Final integrated focused gate | **188 passed** | New provider, consent, capture-action, evidence, board-selection and legacy-route cases plus Blueprint checks. |
| Full follow-up capture gate | **1,340 passed** | Final provider parsing, grounding, confidence and cleanup changes. |
| Full follow-up CRM gate | **2,998 passed; one opt-in benchmark skipped** | Final legacy-route validation and board selection. |
| GitHub final gate | **12,513 passed; 14 gated skips** | 29m49s on the frozen revision; [full suite and image/backup-client checks](https://github.com/JimmyZhu7/Networkly/actions/runs/34186987321) and [dependency audit](https://github.com/JimmyZhu7/Networkly/actions/runs/34186987393) passed. |
| Configuration | System check and migration checks passed; official Render schema accepted the Blueprint | Existing database version 18 is pinned; no service was activated. |

The first two rows cover **12,513 distinct ordinary-suite cases**. Focused and repeated gates overlap and must not be added as separate product coverage.

The 14 ordinary-gate skips are one seed-dependent invariant, one opt-in capacity benchmark and 12 live connector tests. Each was exercised separately: the local directory invariant below, the synthetic benchmark below, and **12 read-only public ATS smoke tests**. No user mailbox, Calendar account or paid provider was used for those public-feed checks.

The remaining warnings are Django's existing URL-field transition deprecation and a settings-module reload warning in the cache-isolation test. Neither was suppressed.

The [function inventory](function-inventory-deep-2026-09-07.csv) maps **1,960 runtime Python functions across 211 modules**. Final-source coverage records **25,391 of 26,907 executable lines (94.37%)** across 267 measured Python files. Function-body evidence: **1,426 fully exercised, 477 partly exercised, 52 not exercised, one with no executable body lines and four indeterminate stubs**. Coverage comes from the frozen final application gate plus the unchanged domain source; old versions' line numbers were not reused.

The 52 unentered functions include 33 model display methods, abstract/compatibility helpers, bootstrap code and maintenance/provider fallbacks. This means their bodies were not recorded in the coverage gates, not that they are all unused or require payment to test. Bootstrap is also exercised by the actual local server and command checks. Any future change to these paths needs the relevant contract tests.

This is Python execution evidence, not complete branch coverage or proof of behavioral correctness. Browser interaction tests separately exercise Chromium and WebKit at desktop and narrow widths, including failed-request detection, pagination, keyboard access, retries and scroll preservation. [Machine-readable verification](deep-verification-2026-09-07.json).

The seed-dependent firm-name invariant was also run against the actual local directory in a read-only transaction: **139 firms, zero normalization collisions**. This supplements the skipped isolated test without seeding or mutating application data.

The final-seat reservation race passed **five consecutive isolated repetitions**. This checks concurrent admission at the 100-person cap; it does not measure throughput for 100 active users.

The first combined gate found seven failures: two older tests expected in-memory CSV responses; an import query check did not account for the new single account lock; three browser cases started with an unset timezone and hit the application's automatic timezone reload; and the source guard flagged newly added ownership predicates. These failures were investigated individually. The final gate includes the corrected response/query assertions, initialized browser fixture and reviewed tenant scopes; the browser network guard remains strict.

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

## Local Release and Recovery Check

A fresh private local backup was restored into a new disposable PostgreSQL 18 database. The temporary restore database was removed after verification; the private backup and aggregate results were retained. All **62 original table counts** matched; billing migrations `0011` and `0012` then applied successfully. The live local database received the same two migrations and matched all **63 resulting table counts**, including the expected new empty reservation table and Django bookkeeping. This verifies restoration, counts and migration applicability; it does not claim a full row-content comparison or off-host recovery.

The local checkout was fast-forwarded to the audited runtime, dependencies synchronized from the lockfile, and Django reported no pending migrations or system-check issues. The local server and its four previously configured jobs were restarted. Five public endpoints returned successful responses and the Assistant and Settings endpoints required sign-in. These HTTP checks do not replace the authenticated journeys in the isolated browser suite. The private `docs/content/` directory remains untracked and unpublished.

No paid service was resumed and no deployment was triggered by this audit. GitHub publication is source publication only.

### Hosting Readback

On 7 September, Render showed **zero active and ten user-suspended services**, PostgreSQL **18**, and a paused Blueprint sync. The web service still tracks `main` with Auto-Deploy set to **On Commit** and a legacy `coverage_web` pre-deploy command. The audit branch records `postgresMajorVersion: "18"` and checks compatibility with the image's backup client; Render's [official Blueprint schema](https://render.com/schema/render.yaml.json) accepted the configuration; its [database version reference](https://render.com/docs/blueprint-spec#postgresmajorversion) describes the immutable field. This audit is published to `codex/deep-core-audit`; it does not update the watched remote branch or apply the Blueprint. Before activating the release, reconcile the dashboard commands with the current `networkly_web` paths and the reviewed Blueprint. No secrets were revealed or changed during this readback.
