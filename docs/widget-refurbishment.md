# Widget refurbishment, September 2026

## Direction contract

THESIS: Each widget makes its object, supporting facts, and available action immediately legible.

OWN-WORLD: Extend the current cool-white/slate/blue workspace, with one sans-serif family, quiet borders, and domain-specific status colors. Shared controls behave consistently while each collection has a format suited to its contents.

STORY: Identify the person or role, understand its state, take one clear action, and receive truthful feedback.

FIRST VIEWPORT: Today pairs a task queue with supporting agenda and actual outreach progress. Network presents an aligned roster. Opportunities presents readable firm collections. Applications starts with count filters over a single authoritative list.

FORM: Code-led extension of the confirmed workspace under the user's explicit request to redesign every widget and make decisive choices. No new branding comp or raster assets are needed. The ten Networkly logo explorations remain separate, pending selection.

FINISH: Complete the bounded desktop/mobile inspection, independent finish review, design documentation, and regression gate.

## Surface inventory

| Surface | Meaningful change |
| --- | --- |
| Today | Identity and evidence above a separate action footer; real weekly progress; quieter supporting agenda and activity. |
| Opportunities | Wider firm collections, readable role facts and persistent actions; explicit expansion for deeper reading. |
| My Applications | Six count filters, including All roles; empty-filter guidance, live status, and preserved filter/focus after server updates. |
| Network | Aligned contact roster, direct profile links, stable recency/action column, and visible selection. |
| Contact and firm records | Labeled interaction capture; readable chronological entries; simpler relationship rows. |
| Calendar | Date-led agenda and an inline creation form; visible event-add controls. |
| Settings | Explanations beside control groups on wide screens, stacked forms on narrower screens. |
| Assistant | A prompt menu, focused composer, and distinct draft subject, body, and action areas. |
| Shared controls and auth | Consistent press, focus, disabled, loading, and error states; shared typography and surfaces. |

## Motion contract

Press responses are brief and local. Disclosures and changed controls use a 200 ms reveal with five pixels of travel. Dialogs use a small opening transition. Only POST requests give the containing widget an in-progress mark and `aria-busy`; search and background reads do not pulse whole panels. Errors keep the authoritative content and show an error state. Success feedback follows the server's response. Existing Today view transitions keep surviving records continuous across a full cockpit update.

Reduced-motion users receive the same functional states without spatial animation. There is no new page-load choreography, ambient motion, or hover lifting of records.

## Verification

Browser evidence is stored locally under `.impeccable/review/widgets/`.

- Thirty-six route/viewport checks at 1440, 1100, 820, and 390 pixels found no horizontal overflow or JavaScript errors. Light and dark captures cover the principal widgets.
- Eleven authenticated demo workflow groups passed, including real save/stage/remove and contact create/edit/touch operations. The application stage filter and keyboard focus survive a full server replacement. Temporary records were removed afterward.
- Five additional interaction groups passed: count-to-row accuracy, zero-result/reset behavior, keyboard expansion on desktop and phone, reduced-motion behavior, and an intercepted failed save. The last preserves content, clears busy state, and reports failure. The zero-result check is an isolated DOM fixture, not a changed server record.
- `scripts/check_widget_interactions.py` preserves the read-only browser checks for reuse with a demo Playwright storage state. Every POST from that script is intercepted.
- A new server-rendered regression guard verifies that every stage filter count matches its authoritative rows, every role appears once, and all rows remain available without JavaScript. Its 44-test module passed; the initial wider 195-test selection also passed.
- The design detector ran once. Its 49 advisories identify token variations requiring documentation; two primary warnings are false positives from Django-dependent image markup. It cannot resolve Django static links, so screenshots and browser measurements remain the visual evidence.
- The weekday Today preview uses existing demo data with the outreach-blackout predicate patched only in a separate rendering process; it does not change the running application's weekend rules. Automatic POSTs from this preview were intercepted.
- The pre-existing demo avatar file is missing and the fallback displays. Paid assistant generation, external OAuth, billing, and live ATS services were not exercised.

The independent reviewer requested two changes: fit the first phone task and its primary action into the initial viewport, and remove the nested calendar form enclosure. The compact phone summary grid now keeps all four factual readouts while exposing the first task's actions. Calendar creation shares one surface with its navigation, separated by a divider. The reviewer scored both fixes resolved and returned `ship`, with no remaining material findings. The full `uv run pytest -n 4 -q` gate passed: **11,237 passed, 13 skipped, 5 existing Django deprecation warnings**, in 381.61 seconds. The skips comprise twelve opt-in live network tests and one unseeded-directory case. Django's system check found no issues.

Eight public route/viewport checks plus the no-JavaScript fallback check passed. The fallback preserves every application row and scrollable firm role while leaving unavailable enhancements hidden or disabled.

The documenter merged the completed widget system into `DESIGN.md` and `.impeccable/design.json`, including nine component previews. Token, schema, reference, palette, motion, and section-order checks passed.
