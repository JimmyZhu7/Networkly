# Capture and Connectors Audit Evidence

Source: codex/deep-capture-audit; commits e561417 (adapter, already integrated separately), 8770757, 4a00baf.

## Scope and coverage

The inventory contains 41 capture modules and 21 connector modules, including package/configuration files, with 522 function/method definitions including nested callbacks. This is an inventory and exercised-line measurement, not a claim of complete branch, provider or scale proof. Migrations and tests are excluded from the table.

| Module | Executable lines hit / total | Coverage | Function bodies entered / inventoried |
| --- | ---: | ---: | ---: |
| `networkly_web/capture/__init__.py` | 0 / 0 | n/a | 0 / 0 |
| `networkly_web/capture/appmail.py` | 261 / 265 | 98.5% | 26 / 26 |
| `networkly_web/capture/apps.py` | 4 / 4 | 100.0% | 0 / 0 |
| `networkly_web/capture/autopilot.py` | 522 / 605 | 86.3% | 29 / 32 |
| `networkly_web/capture/chattime.py` | 219 / 236 | 92.8% | 15 / 15 |
| `networkly_web/capture/discovery.py` | 480 / 493 | 97.4% | 35 / 35 |
| `networkly_web/capture/enrichment.py` | 48 / 55 | 87.3% | 2 / 2 |
| `networkly_web/capture/gcal_live.py` | 273 / 288 | 94.8% | 16 / 18 |
| `networkly_web/capture/gmail.py` | 470 / 481 | 97.7% | 26 / 26 |
| `networkly_web/capture/gmail_live.py` | 730 / 777 | 94.0% | 58 / 60 |
| `networkly_web/capture/gmail_residue.py` | 133 / 157 | 84.7% | 10 / 11 |
| `networkly_web/capture/google_oauth.py` | 23 / 23 | 100.0% | 4 / 4 |
| `networkly_web/capture/google_revoke.py` | 69 / 72 | 95.8% | 5 / 5 |
| `networkly_web/capture/inbound.py` | 91 / 95 | 95.8% | 5 / 5 |
| `networkly_web/capture/locks.py` | 33 / 35 | 94.3% | 4 / 4 |
| `networkly_web/capture/mailfacts.py` | 381 / 481 | 79.2% | 33 / 35 |
| `networkly_web/capture/management/__init__.py` | 0 / 0 | n/a | 0 / 0 |
| `networkly_web/capture/management/commands/__init__.py` | 0 / 0 | n/a | 0 / 0 |
| `networkly_web/capture/management/commands/audit_chat_claims.py` | 58 / 61 | 95.1% | 4 / 4 |
| `networkly_web/capture/management/commands/backfill_touch_subjects.py` | 62 / 64 | 96.9% | 4 / 4 |
| `networkly_web/capture/management/commands/capture_autopilot.py` | 36 / 53 | 67.9% | 2 / 2 |
| `networkly_web/capture/management/commands/capture_autopilot_worker.py` | 31 / 40 | 77.5% | 3 / 3 |
| `networkly_web/capture/management/commands/capture_discover.py` | 77 / 89 | 86.5% | 2 / 2 |
| `networkly_web/capture/management/commands/capture_gmail.py` | 58 / 67 | 86.6% | 5 / 5 |
| `networkly_web/capture/management/commands/capture_openers.py` | 46 / 52 | 88.5% | 2 / 2 |
| `networkly_web/capture/management/commands/capture_worklist.py` | 25 / 27 | 92.6% | 2 / 2 |
| `networkly_web/capture/management/commands/gcal_sync.py` | 60 / 60 | 100.0% | 3 / 3 |
| `networkly_web/capture/management/commands/gmail_backfill.py` | 96 / 119 | 80.7% | 6 / 6 |
| `networkly_web/capture/management/commands/gmail_poll.py` | 208 / 224 | 92.9% | 22 / 22 |
| `networkly_web/capture/management/commands/gmail_pubsub_listen.py` | 47 / 53 | 88.7% | 4 / 4 |
| `networkly_web/capture/management/commands/gmail_watch_renew.py` | 16 / 16 | 100.0% | 1 / 1 |
| `networkly_web/capture/management/commands/opener_worklist.py` | 31 / 33 | 93.9% | 3 / 3 |
| `networkly_web/capture/management/commands/reclassify_inbound_touches.py` | 41 / 50 | 82.0% | 2 / 2 |
| `networkly_web/capture/management/commands/rotate_gmail_tokens.py` | 38 / 44 | 86.4% | 2 / 2 |
| `networkly_web/capture/models.py` | 207 / 211 | 98.1% | 3 / 7 |
| `networkly_web/capture/providers.py` | 42 / 54 | 77.8% | 5 / 8 |
| `networkly_web/capture/reclassify.py` | 113 / 118 | 95.8% | 7 / 7 |
| `networkly_web/capture/subject_backfill.py` | 91 / 92 | 98.9% | 6 / 6 |
| `networkly_web/capture/transactions.py` | 14 / 14 | 100.0% | 1 / 1 |
| `networkly_web/capture/urls.py` | 4 / 4 | 100.0% | 0 / 0 |
| `networkly_web/capture/views.py` | 90 / 130 | 69.2% | 5 / 7 |
| `networkly_connectors/networkly_connectors/__init__.py` | 44 / 46 | 95.7% | 7 / 7 |
| `networkly_connectors/networkly_connectors/avature.py` | 63 / 70 | 90.0% | 5 / 6 |
| `networkly_connectors/networkly_connectors/beisen.py` | 78 / 98 | 79.6% | 9 / 9 |
| `networkly_connectors/networkly_connectors/eightfold.py` | 67 / 69 | 97.1% | 6 / 6 |
| `networkly_connectors/networkly_connectors/goldmansachs.py` | 79 / 91 | 86.8% | 7 / 7 |
| `networkly_connectors/networkly_connectors/greenhouse.py` | 67 / 71 | 94.4% | 4 / 4 |
| `networkly_connectors/networkly_connectors/http.py` | 84 / 91 | 92.3% | 8 / 9 |
| `networkly_connectors/networkly_connectors/icims.py` | 72 / 82 | 87.8% | 5 / 5 |
| `networkly_connectors/networkly_connectors/lever.py` | 46 / 52 | 88.5% | 5 / 5 |
| `networkly_connectors/networkly_connectors/lumesse.py` | 73 / 76 | 96.1% | 8 / 8 |
| `networkly_connectors/networkly_connectors/mckinsey.py` | 76 / 86 | 88.4% | 7 / 7 |
| `networkly_connectors/networkly_connectors/models.py` | 141 / 141 | 100.0% | 0 / 2 |
| `networkly_connectors/networkly_connectors/oracle.py` | 96 / 107 | 89.7% | 6 / 6 |
| `networkly_connectors/networkly_connectors/phenom.py` | 63 / 70 | 90.0% | 4 / 5 |
| `networkly_connectors/networkly_connectors/sitemap.py` | 63 / 68 | 92.6% | 7 / 7 |
| `networkly_connectors/networkly_connectors/socgen.py` | 71 / 77 | 92.2% | 7 / 7 |
| `networkly_connectors/networkly_connectors/successfactors.py` | 96 / 105 | 91.4% | 7 / 7 |
| `networkly_connectors/networkly_connectors/talentgateway.py` | 65 / 72 | 90.3% | 6 / 6 |
| `networkly_connectors/networkly_connectors/talentsoft.py` | 39 / 42 | 92.9% | 4 / 4 |
| `networkly_connectors/networkly_connectors/talnet.py` | 160 / 173 | 92.5% | 11 / 12 |
| `networkly_connectors/networkly_connectors/workday.py` | 143 / 155 | 92.3% | 12 / 12 |

Source-only aggregate: 6914/7584 executable lines hit (91.2%); 497/522 function bodies entered. This last function metric is intentionally conservative about empty/abstract bodies but does not imply all branches or assertions were exercised.

## Concrete fixes

- The ORM and domain adapter now share explicit Django transaction ownership. The proxy never commits, rolls back, or closes the physical Django connection. Domain failures roll back an inner savepoint, preserving the caller transaction.
- Gmail application locks active owner then exact grant generation (encrypted token, mailbox address, connected timestamp), with optional expected history cursor. Contacts, touches, provenance, calendar effects and final history/backfill/rescan checkpoints commit together. Stale worker failures cannot mark a replacement grant failed.
- Gmail and Calendar connect/disconnect/revocation/final synchronization use the same owner-first lock order as deletion. Prepared stale-grant work cannot enter a replacement connection.
- Gmail backfill validates message-page shape and continuation tokens, detects cycles, de-duplicates IDs and preserves the sent-sweep cap.
- Rescan queuing rechecks status and allowance under the active grant lock. The manual findings command now writes findings and Import checkpoint atomically and rejects non-object input rows.
- Paid residue and autopilot use durable budget reservation before calls, one in-flight unit, explicit successful/failed settlement, finally refunds, caps, duplicate attempt fences and active owner checks. Dry runs call no real paid model.
- Existing automatic application-mail and auto-reply classification remains free. It now prepares only transient typed data before row locks; provider calls are single-flight per account and bounded by the existing 100-thread ceiling per pass and per hour. Cache error, exhausted cap, concurrent pass, unconfigured provider or dry run keeps deterministic/review fallbacks. No mailbox plaintext or provider payload is newly persisted.
- Contact/application review accepts, dismisses, restores and mail-fact undo use fresh locked rows. Each autopilot application decision records CRM effects, touch identity, undo snapshot and applied marker atomically; retries resume only complete decisions. Application undo compares the exact post-apply snapshot before reversing, preserving subsequent user changes. Legacy decisions without that snapshot preserve the application row rather than guessing.
- Autopilot validates supplied run ownership/status, fences decision persistence, tolerates deletion during provider work, and retires inactive claimed jobs via status-only CAS without recreating account data.
- Greenhouse supports documented bare-list responses, flags partial stated totals, and verifies readable matching job identity/date fields. Lever and Workday reject malformed/error/inconsistent search envelopes instead of confidently opening or closing roles.

## Test evidence

- Initial full capture/connector gate: 1,515 passed, 12 live skipped; one old fixture returned a William Blair job ID for a Jane Street request and was corrected after exact identity validation.
- New targeted fault/budget/enrichment/command/connector suites: 49 passed on the final feature state.
- Full frozen gate: 1,549 passed, 12 live skipped, two failures; corrected an obsolete fault-injection mock signature and inactive job metadata retirement. After those two narrow changes, all 68 affected ownership/inactive/autopilot/review tests passed. Root integrated gate is the authoritative final combined result.
- Actual child-process os._exit(73) after domain touch and after provenance boundaries leaves no partially committed contact/touch batch. Separate database connections prove reconnect/deactivation writers serialize behind the owner/grant application transaction. Faulted final cursor write, SQL-error savepoints and marker failure all roll back the intended unit.
- Concurrent double acceptance creates exactly one contact and one touch. Stale dismiss cannot overwrite an accepted proposal. Deletion during model work does not recreate runs/decisions. Optional AI tests assert no row transaction at provider boundary, no user ledger debit, shared hourly cap, deterministic fallback and stale-grant refusal.

## Remaining proof and operational limits

- Actual Gmail/Calendar OAuth, refresh, revocation semantics, push/watch renewal, background schedules and end-to-end account deletion during real provider traffic require controlled staging accounts and active hosting. No live mailbox data or account credentials were accessed.
- Paid model quality, provider outage behavior under actual quota/rate limits and billed cost reconciliation remain unproven until credits/services are activated. One budget unit is a logical classification, not each bounded HTTP retry.
- Automatic optional classification is intentionally a service-paid feature, not user-credit debit. The shared-cache hourly limit requires the production shared cache; development local-memory cache only limits each process. Cache loss/reset can reopen a window. Postgres session advisory locks require session-affinity (not transaction-pooling without a dedicated session).
- The 100-user beta is not a large-tenant load test. Provider page walks, per-account contact backfills, retention volume and queue lag still need staging measurements. Unknown external provider changes can degrade to needs-verification/unreachable; the local suite cannot prove future API availability.
- Lever verify remains a documented board-level availability check, not proof that a specific requisition remains open. This inherited behavior was not silently changed in this reliability pass.
- Some provider/error/command branches remain unexecuted, as the per-module table shows. No assertion that every function is bug-free or that 100% branch coverage was achieved.

Public ATS smoke results are appended after the separate authorized read-only run.

## Live public ATS checks

`RUN_LIVE=1 uv run pytest -q networkly_connectors/tests/test_live_smoke.py -m live`: **12 passed in 53.37 seconds**. Read-only public board/API checks, no accounts, no emails, no model calls and no database imports.

- Greenhouse: William Blair fetch and custom-domain job verification; TPG job verification.
- Lever: Palantir board fetch.
- Workday: Citi fetch and job verification; Haitong readable board; Accenture keyword-scoped board below the 2,000-row cap.
- Avature: Deloitte entry-level facet feed.
- SuccessFactors: EY fetch and job verification; Janus Henderson keyword fetch; GIC multi-page walk beyond 20 rows.

These prove those public endpoints responded to those checks during this run. They do not establish continuous availability or certify every configured firm/provider.
