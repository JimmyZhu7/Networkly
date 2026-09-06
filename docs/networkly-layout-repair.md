# Networkly layout repair — September 5, 2026

The founder rejected the previous visual pass because the interface still spilled, overlapped and felt unformatted. This repair audits the actual 693×837 browser layout as well as phone and desktop widths. Whole-document overflow checks are insufficient: the review measures text against its own column, overlapping grid rows, field labels, menu bounds, primary-action placement and expanded states.

## Changes

- Today: the weekly update list becomes a disclosure. Queue rows respond to their container width, with labels above readable role/region fields, wrapping evidence, grouped actions and shorter review notices. Quick add stays within the phone viewport.
- Network: natural grid rows replace conflicting fixed-height rules that compressed tracks below their contents. Long firm names and contact details wrap. Recovery rows keep their actions in the intended column.
- Calendar and capture: forms reflow without implicit columns or overflowing date fields. Debrief questions have one clear divider and consistent spacing.
- Opportunities: filters have readable minimum widths, deadline columns fit their labels, and role/location/evidence text wraps. Menus remain inside the viewport. Firm lists preview three complete rows, followed by a counted expansion control; no record is sliced through its text or actions.
- Applications: stage and removal controls precede optional contact detail. Contact information remains available in an expandable section. Mobile controls retain full touch targets.
- Accounts and public pages: authentication and public compositions stack before their text columns become cramped. Settings fields, firm selections, export filenames, assistant drafts, attachments and memory dialogs handle long content. Selected firm lists have natural height; Add firm shows five complete results with explicit expansion.
- Shared controls: search results show full names and context, with a visible close button and announced keyboard selection. Dialogs fit short screens. Notifications wrap long text and have usable dismiss buttons.

## Validation

Each page-family audit records its routes, widths, themes, conditional fixtures and exclusions in `.impeccable/review/repair/`. Data absent from the demo account is exercised with rendered template or browser-only fixtures; those fixtures do not create product records. Public and authenticated rendering are checked separately. Chromium and WebKit both participate.

The repeatable shared regression check is `scripts/check_shared_layout.py`. It checks header bounds, compact navigation, long search results, keyboard selection, dismissal and confirmation cancellation across ten viewport sizes and both themes. After sign-in it blocks POST requests. Credentials may be supplied through `NETWORKLY_TEST_EMAIL` and `NETWORKLY_TEST_PASSWORD`.

This is a local implementation and review. It does not imply production deployment or live writes through account, email, billing or application actions.

## Final verification record

- Independent Astra review: all reported defects fixed and rechecked in Chromium and WebKit, including the actual 693px pane. Menus close with Escape after pointer opening; drawer action labels remain readable on hover in both themes.
- Shared browser regressions: 148 layout/search/dialog checks, plus24 pointer/keyboard menu and drawer-hover checks, passed. Existing widget checks passed all five groups, including stage filtering, expansion, reduced motion and a simulated failed save.
- Conditional production-template fixtures:42 CRM widget/theme/width checks and six staff-analytics renders passed after fixing long-text overflow. Staff data was synthetic; staff-only live records were not accessed.
- Full regression run:11,253 passed,13 skipped; one wording assertion was updated for the revised review notice. The subsequent affected-family run passed8,094 tests and exposed one obsolete internal-scroll assertion. After updating that assertion for complete-row previews, the final focused run passed147 tests. No identified test failure remains unresolved.
- Django system checks and template compilation pass. This record does not claim live email, billing or destructive business actions were performed.
