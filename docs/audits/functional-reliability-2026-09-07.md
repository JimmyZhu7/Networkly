# Networkly Reliability Audit

7 September 2026 · Local branch `codex/coverage-ui-refurbishment` · Started from `214678d`

This pass fixes reproducible failures in concurrent writes, recovery, provider
boundaries, and growing data histories. It does not establish that every
function is defect-free or that production capacity has been proven.

## Scope and Method

The accompanying [function inventory](function-inventory-2026-09-07.csv)
enumerates **1,904 functions and methods in 264 first-party Python modules**. It excludes test
code, migrations, dependencies, and generated assets. Inventory entries mean
that a function was identified within a triaged module, not that every branch
received a separate semantic review. Frontend scripts, local job wrappers,
runtime settings, and CI configuration were also reviewed.

| Surface | Inventoried Functions | Deeper Review |
|---|---:|---|
| Accounts, core, billing | 318 | Ownership, inputs, throttling, private storage, deletion/export, beta admission, credit/webhook handling, backup rotation |
| CRM, directory, analytics, domain | 850 | Tracking/undo, calendar writes, merging, cadence, evidence ordering, scoring dates, ranking/read-path growth, analytics queries |
| Capture, assistant, connectors | 695 | Grants/cursors, account closure, replay, provider setup/errors, credit lifecycle, pagination, response bounds |
| Runtime and operations | 41 | Job health, failure propagation, deployment checks; frontend and local scripts reviewed separately |

Four parallel workstreams covered accounts/core/billing, recruiting/domain,
integrations/assistant, and operations/browser recovery. A second reviewer
checked the integration changes and caught a truncated-response regression
before completion. Existing product behavior and tenant boundaries were
preserved; no recommendation weights or eligibility policy were retuned.

## Implemented Fixes

| Area | Failure | Result |
|---|---|---|
| Push subscription ownership | Two accounts could simultaneously claim the same endpoint and replace its owner. | The unique endpoint and a row lock settle ownership before keys are updated. The losing account receives a controlled conflict. |
| Push input | Wrong JSON types, malformed URLs, or oversized keys could raise errors or reach inappropriate endpoints. | Input types and lengths are validated; endpoints require an approved HTTPS relay without embedded credentials or custom ports. |
| Notification controls | A rejected unsubscribe could display Off and lose the endpoint needed to retry. | Server removal is confirmed before browser removal; failures restore a retryable toggle. Sign-in redirects are not accepted as saves. Permission failures recover, and save requests have a timeout. |
| Notification navigation | The click event could finish before the requested page opened. | The worker awaits navigation before focus, recovers when a tab closes, and restricts destinations to the app's origin. |
| Public rate limits | Concurrent requests could all pass a read-before-increment check for the final allowance. | Atomic counter admission assigns each request its actual place in the fixed window. |
| Bulk role saves | Undo could include a row created by another request or a later re-save. | Only rows actually created by the batch enter undo, and undo targets their row identities. Legacy batches without that identity expire safely. |
| Application updates | A stale undismiss could erase a progressed application; overlapping updates could replace the first application time. | Undismiss only removes dismissed records; the database preserves an existing first-application timestamp. |
| Calendar editing | Overlapping edits lost revision increments; stale dialogs could reschedule cancelled meetings. | Current tenant-owned manual events are locked during reschedule/cancel, and cancelled events reject stale reschedules. |
| Contact merge and undo | Cached contact or merge objects could overwrite a separate request's newer edit. | Merge and undo reload and lock current tenant-owned rows in consistent ID order. Undo rechecks the current ledger state. |
| Relationship scoring | Equal timestamps produced order-dependent results; daylight-saving changes distorted elapsed time. | Event IDs provide deterministic ordering and enter the evidence hash. Elapsed-time and future-evidence checks use UTC instants. |
| Cadence | Counting business days iterated over every day in an old relationship. | Whole weeks are counted directly; at most six trailing days are inspected. |
| Analytics | Dashboard summaries materialized full event histories. | Counts and onboarding-step deduplication happen in SQL. Invalid drilldown IDs return safely. |
| Gmail watch/live sync | An old provider response could overwrite a replacement grant or checkpoint. | Updates use the identity of the grant that started the request. A mailbox change resets mailbox-specific scan state. See the remaining application-phase boundary below. |
| Gmail history | Malformed or repeated pages could loop or duplicate processing. | Invalid/repeated pagination is rejected and message IDs are deduplicated. |
| Assistant replay | Every historical message and attachment blob was loaded before slicing recent context. | The replay limit is applied in the database query. |
| Assistant setup errors | SDK construction failures bypassed the normal failure message. | Setup failures return a retry notice and follow credit-refund handling. |
| Account closure during assistant work | An already-running reply could continue model/tool work after deactivation or try to persist after deletion. | Fresh account checks guard model, tool, brief, title, and persistence boundaries. Closure stops work with a notice and refunds pending reservations; hard-deleted accounts are not recreated. An already-started provider request remains a cancellation window. |
| Google authentication transport | Token requests could exceed useful interactive or worker wait times. | Token exchange and refresh use explicit 15-second request timeouts; refresh sessions close after use. |
| Connector fetching | A response could consume unbounded memory; permanent errors were retried; one parser error could abort a batch. | Responses have a 32 MiB cap, permanent HTTP failures stop retrying, and parser failures are isolated to their board. Body completeness remains required. |
| Fetcher identity | Some fetchers still identified the retired project name and an unowned contact domain. | Fetchers identify Networkly and point to its repository while retaining robots checks. |
| Job monitoring | A second database error could replace the original job failure; rejected heartbeat requests looked successful. | The original exception survives failure-recording errors. Rejected pings are logged without exposing the credential URL. |
| Health reporting | A success record without a completion time could break health reporting. | Only completed successes contribute to job freshness. |
| Deployment preflight | A substring check could accept an unrelated health exemption or reject an equivalent regex. | Preflight compiles every pattern and tests the actual health path. Invalid patterns fail the check. |
| Backup retention | Rotation could remove unrelated files/nested remote snapshots or the newly completed dump. | Rotation targets only exact snapshot names directly in its ring and always preserves the current successful backup. |
| Local refresh | The wrapper used a hardcoded database, overwrote same-day backups, and hid failures behind a final success message. | It uses the app's atomic backup command and configured database, retains its local destination, and returns failed backup/refresh exit status. |

No schema migration is introduced by this pass. Historical snapshot filenames
and external service identifiers remain intact to preserve existing retention
and configuration. `docs/content/` belongs to another workstream and was not
modified.

## Verification

Verification is performed against uniquely named disposable PostgreSQL
databases. Domain PostgreSQL tests run serially in a separate database from
the Django/connector gate. Browser checks exercise Chromium and WebKit at
desktop and narrow widths. Provider responses are mocked in the normal gate;
no account messages or paid provider requests are sent.

| Check | Result |
|---|---|
| Full application and connector suite | **11,539 passed, 13 skipped**, 7 warnings; 8m 23s |
| Domain suite against a separate PostgreSQL database | **621 passed**, 1 warning |
| Simultaneous reservations for the final beta seat | **5 of 5 isolated repeat runs passed** |
| Dependency audit | **120 packages checked, 0 known advisories, 0 audit skips** |
| Django system checks | No issues |
| Pending schema changes | None |
| Patch whitespace checks | Clean |

Together, the two non-overlapping suites passed **12,160 tests**. The five
repeated admission checks are not added to that total. The full suite includes
browser recovery/navigation and the authenticated journey matrix. The 13 skips
are 12 opt-in live connector checks and one directory-seed-dependent account
check. They are not evidence of live integration success.

The final run used a frozen source snapshot: hashes of 1,094 runtime, test,
asset, script, and CI files were unchanged when it finished. Existing warnings
concern a Django transitional setting, a worker-crash test using process fork,
and a settings-isolation test reloading a module. They did not fail this gate;
future runtime upgrades should address the deprecated interfaces.

The lockfile dependency audit inspected 120 packages and reported no known
advisories. This is a scan result, not a claim that the software has no
security defects.

Existing UI assertions had drifted from the owner's approved interface:
the removed Settings rail, the renamed Suggested outreach label, and the
role drawer's temporary loading skeleton. The browser matrix also needed
to open Manage Profile before checking its save control. Tests were updated to preserve the
current contracts; form presence, both time windows, timezone clarity, and
the prohibition on decorative infinite animation remain checked.

## Remaining Engineering Work

These are software follow-ups, not tasks that can be completed simply by
paying for hosting:

1. **Unify Gmail application writes and grant identity.** Capture currently
   uses Django plus a separate domain database connection with independent
   commits. Checks before applying findings and conditional checkpoint
   updates cannot roll back effects if a reconnect/deactivation happens
   during application. Backfill/rescan have additional stale-grant paths.
   Use a grant generation across every write path and a shared transaction
   or durable, resumable application protocol. Test reconnect and process
   termination at each write boundary.
2. **Reserve non-chat AI work before provider calls.** Gmail/rescan/autopilot
   read affordable work and charge later. The final ledger is bounded, but
   simultaneous jobs can exceed the intended provider budget. Add durable
   job reservations with partial settlement, refunds, and abandoned-worker
   recovery. A database lock held across network requests is not a safe fix.
3. **Prove capacity with representative workloads.** Network, Today, and
   ranking still load substantial histories/candidate sets. Some mailbox
   scans accumulate messages or residue across pages. Profile representative
   large accounts, bound the work per tick, add resumable cursors where
   needed, and exercise concurrent users before claiming a capacity figure.
4. **Resolve notification status per device on initial load.** The Settings
   context currently derives its initial toggle from whether the account
   has any saved subscription. Compare the current browser endpoint with
   the account's owned subscription state so another device cannot make
   this device appear enabled. The write-side ownership and retry fixes
   above do not address this initial display state.
5. **Complete staging acceptance.** Exercise real sign-in/reconnect,
   notification delivery, account deletion, restore from an off-host backup,
   monitoring alerts, and provider-outage recovery using dedicated test
   accounts. Local mocks and key presence do not establish live delivery.

The changes are local, reviewable code. This audit does not deploy, resume
suspended services, purchase capacity, or certify production readiness.
