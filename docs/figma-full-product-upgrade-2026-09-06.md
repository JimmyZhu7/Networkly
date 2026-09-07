# Networkly Product UI Upgrade — 6 September 2026

This pass expands the earlier component polish into full-screen Figma references and shared implementation changes across the recruiting workspace. It is a broader design and layout pass, not evidence that every conditional state or production integration has been exercised.

## Design Reference

[Figma: Full Product · Journeys and States](https://www.figma.com/design/EOQxIPSHLHpL198bB2tOSU/Networkly?node-id=27-2)

| Reference | Node |
|---|---|
| Today | `28:2` |
| Network | `28:87` |
| Settings | `29:2` |
| Assistant | `29:75` |
| Calendar | `29:134` |
| Opportunities | `29:203` |
| Contact Detail | `29:281` |
| Setup | `29:339` |
| My Applications | `34:2` |
| Firm Detail | `34:74` |
| Light References | `34:196`, `34:281`, `34:354`, `34:432` |
| Mobile and State Boards | `32:2`, `32:15`, `32:26`, `32:40`, `32:51`, `32:65` |

Global navigation prototype links connect the first eight full-screen references.

The design retains Instrument Sans, navy/cobalt themes, compact information density, real firm assets with fallbacks, and restrained interaction feedback. Marketing, pricing, and legal compositions were preserved. Legal operator placeholders remain by explicit user instruction. Figma examples are design references, not live product data or a one-to-one implementation of every frame.

## Implemented Changes

- **Today:** a unified compact summary strip, clearer next-step surface, tighter action spacing, and equal-width supporting feeds. The existing equal-height, internally scrolling feed behavior remains.
- **Network:** a more compact toolbar and cards, consistent card heights and action alignment, clearer selection/focus treatment, and the existing four-contact/three-firm desktop grids.
- **Contact records:** a stronger identity header; relationship status and logging moved ahead of correspondence; score detail progressively disclosed, with a visible prompt when the role is missing.
- **Opportunities and applications:** quieter qualification labels, tighter record spacing, application firm logos with monogram fallbacks, and drawer presentation adjustments.
- **Settings and account forms:** denser preference summaries and target-firm rows, tighter decisions/history rows, balanced cadence controls, and focused import/delete presentation.
- **Assistant:** Saved Context is directly accessible in the history sidebar; message/composer and empty-state spacing were refined while existing handlers remain in place.
- **Calendar and shared shell:** tighter navigation/context controls, responsive spacing, and consistent page typography.

Implementation is concentrated in the three `presentation-*.css` families, `workspace.css`, and selected Django templates. Existing routes, forms, HTMX targets, and action handlers were retained. Application identity adds two presentation fields to the existing view data.

## Networkly Matrix

The source inventory contains **100 non-email templates, including 42 base-page templates**. The inventory is preserved in `docs/networkly-ui-coverage-inventory-2026-09-06.json`; it contains template paths, page flags, extracted headings and state classes. Automated heading extraction can include template/style text, so it is a navigation aid rather than a definitive copy audit. Inventory coverage is not equivalent to browser or functional coverage.

| Family | Source Audit | Implementation in This Pass | Browser Evidence | Remaining Conditional Networkly |
|---|---|---|---|---|
| Today | Page and action/queue/feed states | Summary, plan, action and context layout | Desktop/mobile; light/dark | Active weekday plan, every proposal/undo/error and first-use combination |
| Network and firm network | Toolbar, groups, cards, cleanup states | Toolbar/card density, selection and alignment | Desktop/mobile; light/dark; search, selection and no-results interactions | Every bulk action, drag operation, empty tier and cleanup outcome |
| Opportunities / My Applications | Records, filters, picks, drawers | Record hierarchy, logo fallback, drawer styling | Desktop/mobile; light/dark; filter and Saved-stage interactions; successful/failed role loading | Every stage transition and save/dismiss/undo; drawer load failure is covered below |
| Contact / firm detail | Identity, history, scoring, AI sections | Contact hierarchy and disclosure; shared directory styling | Both details at desktop/mobile | Log submission, AI success/failure, absent data and all relationship states |
| Contact forms and recovery | Form and collection templates | Focused form width and shared presentation | New-contact form and archived collection at desktop/mobile | Submission validation, restoration and other recovery collections |
| Settings | Profile, targets, cadence, integrations, decisions | Shared row/disclosure density and section refinements | Desktop/mobile; light/dark; disclosure and retained selections | Every save/error, merge/restore decision, integration and billing state |
| Assistant | History, memory, composer, stream and attachments | Direct Saved Context access and layout changes | Desktop/mobile; light/dark | Live generation, streaming failure/retry, uploads, dictation and memory mutation |
| Calendar | Month/week/day and event/form states | Compact controls and context | Desktop/mobile; light/dark; week switch and Add disclosure | Event creation/deletion, external sync and every event provenance |
| Account / onboarding | Auth, setup, import/export/delete templates | Shared support-family styling; selected form refinements | Import, export, delete, email, password and connections at desktop/mobile | Full onboarding, email/reset delivery, OAuth, export/download and destructive submissions; logged-out mobile auth rendering is covered below |
| Marketing / legal / utility | Included in source inventory | Compositions preserved | Not included in this pass's page matrix | No claim of fresh end-to-end verification |

## Verification Evidence

- `.impeccable/review/figma-upgrade/browser-results.json`: **28 page/theme/viewport cases**, all HTTP 200, no horizontal overflow, no recorded JavaScript errors. Seven main pages at 1440px and 390px in both themes.
- `.impeccable/review/full-upgrade/secondary.json`: **20 cases** across ten secondary pages at 1440px and 390px, all HTTP 200 with no horizontal overflow. This file does not record a JavaScript-error assertion or a full light/dark matrix.
- `.impeccable/review/figma-upgrade/interactions.json`: Chromium and WebKit passed settings disclosure/selection retention, contact search/selection, opportunity filters, calendar Add disclosure/week view, mobile navigation, and intermediate header widths. No JavaScript errors were recorded in that interaction set.
- `.impeccable/review/full-upgrade/states.json`: successful role loading, a simulated role-load failure with Escape restoring focus, Network no-results filtering, application stage filtering, and logged-out login/signup/reset mobile rendering all passed.
- A review found that the closed mobile Assistant history could retain keyboard-focusable controls off screen. The fix applies `inert` and `aria-hidden`, synchronizes resize state, and restores focus on close; the Chromium reproduction was rechecked. This is a targeted focus check, not a complete accessibility certification.
- The existing CRM `0028` migration was applied locally to resolve Today/Calendar failures caused by the local schema being behind the code. No new migration was authored for this UI pass.
- Automated checks: **261 passed** in 71.85 seconds using an isolated test settings module/database. Networkly includes the visual system, settings page/sections, contact forms/facts, calendar views, and application tracking. One existing Django deprecation warning remains. Earlier database-contention attempts are not counted as passes.

Screenshots and response checks establish rendering of the exercised data states. They do not establish every interaction, accessible name, keyboard sequence, screen-reader behavior, integration, or production deployment.

## Remaining Verification

Follow-up: the local journey, conditional-state, reconciliation and Figma comparison work below has since been extended. See [current implementation status](figma-implementation-status-2026-09-06.md) and [launch acceptance](acceptance-readiness-2026-09-06.md). The list below records the gaps at the end of the original design pass, not a current claim that those checks are all untouched.

1. Exercise a fresh account through onboarding, empty states, contact import and its validation outcomes.
2. Run safe end-to-end workflow tests for application changes, interaction logging, calendar events, and recovery/undo states.
3. Exercise AI streaming/retry/attachments and integration failure states with appropriate test accounts.
4. Complete keyboard and assistive-technology review of drawers, dialogs, dynamic feedback and compact controls; include reduced-motion behavior.
5. Reconfirm against the final release build. Local screenshots do not prove deployment, email delivery, OAuth connectivity or paid service readiness.

Final browser confirmation: Chromium and WebKit both passed mobile Assistant history exclusion from keyboard navigation, opening, Escape focus restoration, and desktop resize behavior (`full-upgrade/final-checks.json`).
