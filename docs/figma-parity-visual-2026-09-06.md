# Figma Visual Parity Review — 6 September 2026

Compared the actual Figma design contexts and screenshots with fresh authenticated local browser captures. These are design-intent references rather than pixel-perfect acceptance frames: the Figma file uses sample records and deliberately simplified navigation. No sample content was copied into the application.

## Frame Comparison

| Frame | Live surface | Implemented design intent and intentional adaptation |
|---|---|---|
| Today `28:2` | `/app/` | Unified four-part summary, prominent next-step surface, paired equal-height feeds, and narrower supporting column are present. Real queue disclosure, market assignment, deadline provenance, and per-stage labels remain; the Figma's static “Review Queue” button is represented by the functioning queue disclosure. |
| Network `28:87` | `/app/contacts/` | Four contact cards per desktop row, compact search/scope toolbar, consistent action footers. Selection, relationship badges, firm marks and group disclosure add real product functionality beyond the simplified reference. |
| Opportunities `29:203` | `/opportunities/` | Title/identity, fit facts, explanatory disclosure and clear save/view actions are present. The live two-column picks layout is retained; the reference's single-column sample and left rail are not copied over the existing Browse/My Applications navigation. This pass tightened repeated vertical spacing and eliminated a redundant internal divider in picked cards. |
| Calendar `29:134` | `/app/calendar/` | Shared type, compact toolbar, date context and event actions are present. The live product retains Month/Week/Day views and external-source handling rather than replacing them with the sample's five-day list or a redundant left rail. The captured default is Month; the Figma reference depicts a week. |
| Contact `29:281` | `/app/contacts/4/` | Strong identity, relationship/log action before supporting content, progressive detail and history remain. Real scoring, source context, archive and draft controls are preserved. The reference's decorative Overview/Interactions rail is not added to a single continuous record. |
| My Applications `34:2` | `/opportunities/mine/` | Six-stage count strip, grouped deadline records, status controls, firm identity and related contacts are implemented. Real closed-posting and empty-group states replace sample roles. The Finished lens and per-row stage select are preserved. |
| Firm Detail `34:74` | `/firms/baird/` | Firm identity, contacts, recruiting dates and roles follow the reference hierarchy. Observed Activity is retained as an additional truthful information section. The inspected firm has no contacts or cycle dates; those empty states remain explicit instead of showing the Figma's sample people. |

## Refinement

Only `networkly_web/static/css/presentation-directory.css` was changed by this visual review. Picked-card stack spacing changed from 12px to 8px, firm-heading spacing from 12px to 8px, and the deadline area's redundant top rule was removed. The first visible card decreased from approximately 351px to 322px at 1440px. All information, disclosures, status controls, footer actions and mobile touch targets remain.

## Evidence and Limits

- `.impeccable/review/parity/results.json`: seven authenticated desktop pages, all HTTP 200 with no horizontal overflow, plus screenshots inspected against seven Figma screenshots.
- `.impeccable/review/parity/responsive.json`: 12 responsive Chromium/WebKit checks for Opportunities and My Applications at 390, 768 and 1440 pixels passed. All returned HTTP 200 without horizontal overflow; picked-role explanations opened and closed in all six Opportunities cases.
- Existing real records were read only. No provider calls, email sends, application changes or contact mutations were made.
- This is a local visual comparison. It does not establish production deployment, every possible data combination, or exact pixel equality with the schematic frames.
