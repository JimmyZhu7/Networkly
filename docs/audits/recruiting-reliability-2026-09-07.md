# Recruiting Reliability and Capacity Audit

Date: 7 September 2026. Baseline: `3d2c49d`. Scope: CRM, directory, and the domain rules. All mutations and benchmarks used disposable local test databases. No live provider calls, customer records, hosting plans, or deployment settings changed.

## Changes

1. **Today no longer materializes entire message histories.** A streaming reducer retains the latest relevant evidence per contact and exact lifetime outbound counts. It reads compact touch fields, excludes archived or other-account contacts, and does not fetch private note bodies. The opening-contact bench fetches one latest real interaction per contact. No history cutoff or recommendation cap was introduced.
2. **Role ranking reads only the facts it uses.** Eligible postings still undergo the same qualification, ranking, and duplicate-folding rules, but large provider payloads are excluded from the query. Grouped postings reuse the evaluated candidate objects instead of fetching the full payload again.
3. **Editing a contact cannot rewind background state.** The form saves only its own fields and region provenance. New replies, promotions, archive state, and AI summaries written after the form loaded survive the edit.
4. **Firm merges preserve dependent user records.** Contacts, tasks, proposed contacts, application evidence, dismissal choices, and opportunity-change history move to the surviving firm or posting. The operation locks the firms and runs atomically. Ambiguous application-event collisions stop the merge for explicit review instead of deleting evidence. Derived cycle observations are invalidated for rebuilding from preserved source records.
5. **Relationship summaries have bounded provider work.** The free feature shares an account-level generation lock, permits at most ten attempts per hour, and fails closed when the rate-limit store is unavailable. It reloads current owned records, filters touch ownership, checks account activity again before saving, and cannot resurrect a deleted contact or replace a newer summary. It changes no credit or plan entitlements.
6. **Cadence date ordering handles repeated daylight-saving hours.** Evidence ordering uses UTC instants and ledger IDs. Thank-you delays measure actual elapsed time across the repeated hour rather than wall-clock subtraction.

The CRM view change is limited to surfacing the summary notice. The separately owned paid contact-brief implementation is unchanged by this patch. The account-generation lock comes from the parallel AI-budget workstream.

## Verification

- Full domain suite with a dedicated PostgreSQL database: **625 passed**, including the SQLite/PostgreSQL pipeline variants. No database-dependent skips.
- Focused final suite: **1,095 passed** across cadence, compact history, stale edits, AI-summary failure/concurrency behavior, tenancy guards, firm merges, and personalized/grouped picks.
- Opt-in capacity comparison: **1 passed** with exact action and recommendation parity against the baseline.
- Broad CRM/directory discovery run: **7,207 passed and one structural-guard failure**. The failure was the old count ceiling for deliberate administrative cross-tenant queries. Each added transfer query was reviewed, per-owner work was converted to scoped queries, and the remaining four administrative call sites were documented in the guard. The final focused suite re-ran that guard successfully. This earlier run is supplementary; the parent task's integrated gate is the final release check.
- The remaining warning concerns Django's existing `FORMS_URLFIELD_ASSUME_HTTPS` deprecation.

The complete source inventory contains **102 modules and 848 functions/methods**, excluding tests and migrations. Inventory completeness is not a claim that every branch or external integration has been proven. Deep review focused on history reduction, ranking, state mutation, tenant boundaries, merge recovery, provider-work bounds, and time arithmetic. Existing tests cover the other module families below. The adjacent JSON records intermediate per-module line coverage for triage; it is not final release coverage because the broad run occurred while fixes were being completed.

| Module Family | Review and Regression Evidence |
| --- | --- |
| CRM models, forms, services, views and utilities | Tenant-scoped reads, safe contact edits, owned mutations, undo/state preservation, summary boundaries; shared transaction adapter is owned by the capture workstream. |
| CRM Today, coverage, relevance, recruitment and sourcing | Exact action histories, warm-contact clocks, outbound limits, held rows, recruiter handling, candidate ordering, heavy-account allocations. |
| CRM calendar, debrief, merge and campaigns | Existing state/ownership/regression suites; this patch does not alter meeting ownership, campaign decisions or merge policy. |
| CRM regions, inference, enrichment, digest and health | Existing classification, scheduling, retry and health suites; real email delivery remains a staging check. |
| CRM administrative commands | Mutation/tenant-boundary inventory and existing tests; no command was run against application data. |
| Directory views, recommend, facts, classify, dupes and sponsorship | Eligibility and score parity, full eligible candidate set, search/application lens regression, payload projection. |
| Directory applications, dates, deadlines, estimates, timelines, cycle trust and open runs | Existing transition/date/provenance tests; source observations remain distinct from estimates. |
| Directory ingest, boards, AI extraction, logos, parsers and health | Existing parser/failure/provenance suites; external connector work belongs to the parallel connector audit. |
| Directory firm merge and administrative commands | Atomic transfers, all dependent-record preservation, explicit conflicting-event recovery, unchanged posting merge policy. |
| Domain cadence, pipeline and scoring | Complete local suite including PostgreSQL pipeline variants; streaming/full-history parity, DST and deterministic event ordering. |

## Reproducible Capacity Check

Run from a checkout containing the baseline commit. Django must select an isolated `test_*` database; the benchmark asserts that before creating records.

```sh
uv sync --all-packages
NETWORKLY_CAPACITY_BENCH=1 NETWORKLY_CAPACITY_CONTACTS=2000 NETWORKLY_CAPACITY_ROLES=3000 uv run pytest -q -s networkly_web/crm/tests/test_recruiting_capacity.py
```

The benchmark creates 100 tenant rows. One account has 2,000 contacts and 200,000 logged touches. The other 99 accounts contribute 99 contacts and 9,900 touches. The shared board has 3,000 open postings with roughly 26 KB of provider text each. All records are synthetic. An explicit date keeps the comparison reproducible.

Each reducer receives one warm-up, three ordinary timed passes with query counts, and a separate allocation-traced pass. Allocation tracing is excluded from reported latency. Results on this local machine:

| Reducer | Median Before | Median After | Peak Python Before | Peak Python After | Queries Before / After |
| --- | ---: | ---: | ---: | ---: | ---: |
| Today actions | 2.938 s | 1.573 s | 588.37 MiB | 9.65 MiB | 9 / 9 |
| Personalized picks | 0.509 s | 0.228 s | 166.13 MiB | 18.68 MiB | 6 / 5 |

All 2,000 generated actions matched the baseline. All six selected recommendations, scores, explanations, and grouped places matched. The benchmark explicitly rejects zero picks so an ineligible fixture cannot produce a vacuous result. Full metrics are in `recruiting-capacity-2026-09-07.json`.

## Limits and Work Still Requiring Staging

- This is **not** 100 simultaneous users, HTTP throughput, browser rendering, managed-PostgreSQL performance, or a production capacity certification. The user cap does not establish capacity.
- Today still performs work proportional to the account's historical touch count. The memory bound is substantially better, but a 200,000-touch account still took 1.57 seconds for the action reducer alone. A persisted incremental summary would need transactional updates, backfill, repair, and invalidation before it could safely replace exact history scans.
- Ranking still examines all eligible open roles and retains compact candidate objects. Larger catalogs need additional measurements before selecting a materialized/indexed recommendation strategy. Arbitrary truncation would change useful results and was not introduced.
- Before paid hosting is opened to users, run realistic concurrent journeys against the actual web/database plans with background Gmail and connector jobs active. Measure p95/p99 latency, errors, database connections, worker memory, and cache failure behavior. Include a large account, sparse accounts, long provider payloads, and multiple regions.
- Verify the shared cache's real atomic rate limiting, account-generation lock release after worker termination, and provider timeouts in staging. Local concurrency tests establish behavior on local PostgreSQL, not service availability.
- Real AI generation requires funded provider credits. Real digest delivery, Gmail/Calendar activity, scheduled-job completion, backups and restoration require resumed services and test accounts. Those integration checks remain explicitly unproven here.
- Conflicting duplicate-firm application events intentionally require operator review. After a successful merge, rebuild cycle observations through the existing administrative command. No automatic deletion of ambiguous user evidence is authorized by this fix.

No software audit can guarantee the absence of bugs. The evidence here supports the named fixes and measured workload; the integrated release gate and staging checks remain separate requirements.
