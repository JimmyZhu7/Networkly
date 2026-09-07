# Networkly Acceptance Checks — 6 September 2026

## Completed in This Pass

- Journey lane: 134 Django regression tests and 20 Chromium/WebKit desktop/mobile browser cases passed. Covers onboarding, contact creation, duplicate-safe CSV import, calendar creation, opportunity saving, application-stage persistence, interaction lifecycle and undo. Synthetic sessions and isolated test data were used.
- Integration lane: 242 tests passed covering Gmail/Calendar connection and recovery contracts, push, beta admission, email change, private media, production settings, backup safety and deployment preflight. External-provider behavior was mocked.
- Assistant lane: 1,116 tests and six Chromium/WebKit streaming cases passed. Fixed silent premature stream completion and final-frame parsing. Partial replies now retain their text with an accessible recovery notice; no automatic retry is issued.
- Accessibility lane: 28 page/viewport checks passed, plus keyboard/focus/retry checks in Chromium and WebKit. Contact searches now announce result counts after typing pauses. See accessibility-readiness-2026-09-06.md for evidence and limits.
- Live Redis temporary-key write/read/expiry/delete probe passed. Live private-media bucket access probe passed; no media was written or modified.

Total automated functional checks across the first three lanes: 1,538 passed. Accessibility coverage is additional. An existing Django deprecation warning remains.

## Freshly Verified Launch Gates

- Render dashboard: zero active services, ten services suspended by the owner. No paid service was resumed and no deployment was performed.
- Local launch preflight: 12 passes, eight failures expected from local development settings (production module, HTTPS/site/CSRF/security settings, production cache/storage/monitoring, and sending email). This is not a production preflight result; local development settings were not converted into production settings.
- Sending email configuration still lacks EMAIL_URL and DEFAULT_FROM_EMAIL. A verified sending domain is still required for launch email.

## Remaining Acceptance Work

1. Activate the intended hosting/database/job services, deploy the release, apply migrations, and run the production launch preflight against the deployed configuration.
2. Purchase/configure the domain and verify sending-email DNS; replace legal operator placeholders before public launch.
3. Complete real deployed Google sign-in, Gmail and Calendar consent/synchronization with a beta account.
4. Run controlled production email, push, avatar upload/read, and AI-response smoke checks; verify delivery and persisted results rather than configuration alone.
5. Confirm scheduled jobs actually run, monitoring receives their signals, and a production backup can be restored into an isolated database.
6. Perform hands-on VoiceOver or NVDA checks. Automated accessibility checks are not full screen-reader acceptance or WCAG certification.

The local fixes are implemented. Suspended production hosting and absent launch-domain/email configuration prevent claiming production readiness. No real messages were sent and no real user records were changed during this pass.
