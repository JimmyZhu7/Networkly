# Directory Functionality Audit — 6 September 2026

**Disposition:** concrete fixes are complete. Offline connector, pure dedupe and directory integration checks pass. The main task's full run had 11,377 passing cases and one unrelated new assistant-test assertion failure, recorded in the parent audit. A controlled live refresh is still required before claiming upstream availability. No live directory records were changed, no provider requests or paid calls were made, and no commit was created by this audit.

## Fixes

| Area | Concrete defect and resulting behavior | Source |
| --- | --- | --- |
| Ingest eligibility | A repeat listing could derive a graduation year before consulting preserved stated graduation facts. The merge now happens first, so a surviving stated window prevents a contradictory heuristic year. A material content change can still invalidate old extracted facts and permit fresh derivation. | `coverage_web/directory/ingest.py` |
| Ingest location | Whitespace location now counts as silence and preserves the stored place. A newly stated, different location that cannot be mapped retracts the old market, preventing recommendations from continuing to use a contradicted region. | `coverage_web/directory/ingest.py` |
| Connector completeness | Phenom, Eightfold, Lumesse, Société Générale, McKinsey, and Goldman Sachs now report incomplete known-count results when a cap, early empty page, or repeated page leaves jobs unseen. Short-page offset providers advance by the actual returned batch length. Existing ingest guards then preserve unseen jobs instead of treating the partial listing as proof of closure. | Six connector files listed below |
| Phenom response validity | Malformed/error-shaped HTTP 200 envelopes return a failed fetch instead of appearing to be a successful empty board or escaping as an unhandled parsing error. | `coverage_connectors/coverage_connectors/phenom.py` |
| Dedupe eligibility | Both duplicate folding and role-family folding retain separate roles when stated graduation windows or nonblank entry routes conflict. Equivalent class-year/raw-fact representations and missing facts can still fold. Existing requisition, location, deadline, cohort, and sponsorship safeguards remain. | `coverage_web/directory/dupes.py` |

## Exact Changed Source and Test Coverage

| Changed source | Changed or added tests | Verification |
| --- | --- | --- |
| `coverage_connectors/coverage_connectors/phenom.py` | New `coverage_connectors/tests/test_phenom.py`: 7 cases | Cap, early empty page, actual offset, repeated page, three unreadable envelopes |
| `coverage_connectors/coverage_connectors/eightfold.py` | `coverage_connectors/tests/test_eightfold.py`: 3 added cases | Early empty page, repeated page, growing stated count |
| `coverage_connectors/coverage_connectors/lumesse.py` | New `coverage_connectors/tests/test_pagination_trust.py` | Four providers × cap, early empty page, repeated page, complete traversal = 16 cases |
| `coverage_connectors/coverage_connectors/socgen.py` | Same matrix | Same |
| `coverage_connectors/coverage_connectors/mckinsey.py` | Same matrix | Same; preserves per-keyword completeness despite global dedupe |
| `coverage_connectors/coverage_connectors/goldmansachs.py` | Same matrix | Same |
| `coverage_web/directory/ingest.py` | `coverage_web/directory/tests/test_ingest.py`: 4 added cases | Preserved stated graduation; changed-content invalidation; unknown replacement market; whitespace location |
| `coverage_web/directory/dupes.py` | New `coverage_web/directory/tests/test_dedupe_eligibility.py`: 10 cases | Both folding modes retain four kinds of competing eligibility claims; equivalent/missing facts still fold |

Total scope: **8 source files and 5 test files**. Unrelated concurrent changes, including firm-logo work in directory models/views/tests, were preserved.

Validated locally without a database:

- Entire offline connector suite: **296 passed, 12 live tests deselected**. Log: `/tmp/directory-connectors-all.log`.
- New pure dedupe regressions: **10 passed**. Log: `/tmp/directory-dedupe-green.log`.
- Regression sensitivity before fixes: initial Phenom/Eightfold run **8 failed, 9 passed**; additional Eightfold run **2 failed**; four-provider matrix **11 failed, 5 passed**; dedupe **8 failed, 2 passed**.
- Main task ran the four new ingest cases before the fix: **3 failed, 1 passed, 41 deselected**. Log: `/tmp/networkly-functional-ingest-before.log`. Post-fix ingest passed in the 113-case combined ops/directory batch. The final broad run also passed the directory integration, recommendation and eligibility cases; its only failure was an unrelated new assistant-test assertion. Logs: `/tmp/networkly-functional-ops-directory.log`, `/tmp/networkly-functional-full-suite.log`.
- Scoped `git diff --check` passed. No additional database test process was started by this audit.

Reproduction commands from repository root:

```sh
.venv/bin/python -m pytest -c coverage_connectors/pyproject.toml --confcutdir=coverage_connectors coverage_connectors/tests -q -m 'not live'
PYTHONPATH=coverage_web .venv/bin/python -m pytest -c coverage_connectors/pyproject.toml --confcutdir=coverage_web/directory/tests coverage_web/directory/tests/test_dedupe_eligibility.py -q
```

Requested main-task integration coverage includes `coverage_web/directory/tests/test_ingest.py`, `coverage_web/directory/tests/test_dupes.py`, the new dedupe file, and the existing recommendation/eligibility/feed coverage in the full suite. Follow the main task's dedicated database configuration rather than starting another shared test run.

## Algorithm Review Boundaries

Source inspection covered recommendation gates and scoring/diversification in `directory/recommend.py`; profile eligibility and pick/bulk-save rechecks in `directory/views.py`; deadline windows in `directory/deadlines.py`; freshness and open-run baselines in `directory/open_runs.py`; sponsorship precedence in `directory/sponsorship.py`; identity/conflict handling in `directory/dupes.py`; and ingestion merge, history, per-row isolation, and board-level close guards in `directory/ingest.py`.

The inspected contracts retain hard stated graduation/study-level mismatches, posting-specific no-sponsorship restrictions for users who need sponsorship, past-deadline exclusion, diversity limits, and a final eligibility check before bulk saving. Failed verification does not become fresh confirmation. No recommendation weights, factual extraction rules, or eligibility policy were recalibrated. These are source-review findings, not a new live profile-cohort accuracy study.

Connector review used stored envelopes and mocked requests. Existing guard paths in Workday, Oracle, Talnet, iCIMS, Avature, and SuccessFactors were also inspected, but their current upstream availability was not tested. The passing offline suite does not establish complete live coverage, all possible malformed provider shapes, or every content-change/fact-cache edge.

## Stored Source Status and Launch Work

A read-only database transaction captured **140 catalog boards** at **2026-09-06 07:38:02 UTC**. The latest stored full scrape ran **2026-09-05 15:30:06–15:32:59 UTC** and ended **partial**. This is stored run evidence, not a fresh upstream health check. The full map is in `directory-source-status-2026-09-06.json` beside this report.

| Stored classification | Boards | Meaning and action |
| --- | ---: | --- |
| `ok` | 128 | Returned rows; this alone does not prove complete results or present-day freshness. |
| `failed` | 2 | EY: DNS lookup failure. Sixth Street: Greenhouse HTTP 404. Verify from the deployment environment and confirm the official board before changing configuration. |
| `walled` | 2 | Morgan Stanley jobs and events: Oleeo Protect blocked access. Choose an authorized source or manual coverage process, or disclose the coverage limit. |
| `wiped` | 4 | Zero-row alerts for Solomon Partners students/graduates, Jefferies jobs, Houlihan Lokey Events, and Guggenheim Undergraduate Programs. Verify empty state and board configuration before any repair. |
| `empty` | 3 | HPS Investment Partners, Permira, and U.S. Bank internship board have no banked rows. Confirm whether genuinely empty or misconfigured. |
| `silent` | 1 | Marshall Wace has historical data but no current rows. Verify the official source. |

The health helper's `open_rows` and `ever` counters are aggregated by **firm/provider pair**, not individual board. In particular, an empty events board may share banked jobs with a sibling board. The `wiped` label is therefore an alert, not proof that four boards lost their records; counts for two Morgan Stanley boards must not be summed as separate job populations. The helper also omits the stored per-board `truncated` marker, so the summary cannot substitute for reviewing scrape-run detail.

Founder/operator decisions and setup, in priority order:

1. **Deployment gate:** confirm the main task's full suite, then deploy these fixes and run one controlled refresh. Check per-board completeness markers and the aggregate partial result. Do not reopen or close historical jobs merely from this audit.
2. **Coverage ownership:** assign an owner for EY, Sixth Street, Morgan Stanley, and zero-row-board verification. Decide which limited providers are launch-critical and which require an explicit coverage limitation. Bot protection must not be treated as an empty hiring market.
3. **Refresh operations:** confirm the deployed scheduler, logs, failure alerts, and freshness target. The repository contains a local macOS refresh wrapper; launch operations need a confirmed deployment schedule and recipient rather than an assumption that a laptop job is sufficient. The main task owns deployment setup.
4. **Verification capacity:** inspect real backlog against refresh defaults of 400 enrichment candidates and 200 reverifications per run. Adjust only after observing throughput and source limits; establish a freshness service target first.
5. **Optional AI spend:** deterministic ingestion and guards do not require enabling a new paid deadline pipeline. Any recurring AI enrichment remains a separate cost/benefit decision; none was enabled or called here.
6. **Recommendation calibration:** review representative launch cohorts, regions, and visa requirements against real known-positive/known-negative roles. The current audit establishes regression protection and inspected rule precedence, not a measured relevance or eligibility accuracy rate.

No live data repair, external-provider configuration change, scheduler execution, or recommendation-policy change was performed.
