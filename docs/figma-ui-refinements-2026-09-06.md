# Networkly Figma and Application Refinements — 2026-09-06

[Editable Figma file](https://www.figma.com/design/EOQxIPSHLHpL198bB2tOSU/Networkly-Product-UI-Refinements)

The Professional Full seat was verified after owner payment. This continuation adds editable reference components in Figma and a focused visual update to the local application. It is not a complete page-prototype set or a complete production design system. Sample feed names and entries in Figma are illustrative; no user contact records were imported.

## Figma Inventory

The Product Upgrade page `20:2` contains navigation `20:3`, contact card `20:85`, Settings `20:95`, Calendar `20:107`, Assistant composer `20:112`, and implementation rules `23:7`. Light counterparts are `25:16`, `25:30`, and `25:42`. These are component references, not full-page prototypes. The temporary reference capture `21:2` was removed.

The existing semantic collection `3:5` now has Light mode `25:1` alongside Dark mode `3:1`. The two collections still contain 26 variables in total: 10 primitive colors, 10 aliased semantic colors, and 6 spacing/radius values. Four Instrument Sans text styles remain available.

Useful earlier objects remain:

- Foundations page `0:1` and read-me frame `4:2`.
- Controls page `3:2`: Action component set `4:18`, with Primary `4:10`, Secondary `4:12`, Saved `4:14`, and Disabled `4:16`. The configured 160ms Save-to-Saved transition has not had interactive prototype acceptance.
- Widgets page `3:3`: Opportunity Card `4:20`, Firm Updates panel `5:4`, Recent Activity panel `5:8`, Firm Update Entry `5:12`, and Activity Entry `5:16`.
- The earlier feed references are 560 × 420, with clipped vertical-overflow content containers `5:7` and `5:11`. Those reference dimensions are not the application's 320px Today context-panel rule.
- Cadence component `17:2`, five desktop examples `17:10`, mobile cadence `17:51`, mobile opportunity card `17:97`, and 343 × 420 mobile feed references `19:83` and `19:119`. Mobile feed entries and opportunity actions use editable local frames after instance-rendering defects; desktop components remain reusable.

## Implemented Local Changes

Four shared/presentation stylesheets contain the application changes:

- Shared navigation now shows desktop icons and gives the active destination an inset accent border. Intermediate desktop widths hide icons and tighten spacing before the mobile menu breakpoint.
- Network contact cards retain the four/two/one-column breakpoints, but now align their action footers within content-defined rows. Insets increase to 16px; hover/focus and selected states have clearer accents. Record text can still wrap.
- Settings preference disclosures become flat rows with dividers, larger titles, visible selected values, and clear chevrons.
- Opportunity titles and qualification chips have a clearer hierarchy; picked cards use the main surface with a subtle edge. Application rows use an accent border on hover/focus.
- Calendar's current day gains an accent top inset. Assistant gains a composer focus ring and tighter phone starter spacing. Today shortcuts, secondary controls, and the Assistant sidebar use a restrained inset surface edge.

The phone Assistant initially clipped the fourth starter button. The final correction uses `4px 0` starter-area padding and an 8px gap; the refreshed 390px capture shows all four actions above the composer. These are visual changes, not new product workflows.

## Verification and Evidence

Evidence lives under `.impeccable/review/figma-upgrade/`:

- 28 route/theme/size checks cover Today, Network, Opportunities, Applications, Calendar, Assistant, and Settings at 1440px and 390px in light and dark themes. The corrected harness reports HTTP 200, zero horizontal overflow, and no JavaScript errors for those checks (`browser-results.json`).
- Chromium and WebKit interaction checks pass for Settings disclosures and retained selections, contact selection/search, opportunity filters, Calendar add disclosure/week view, mobile navigation, and headers at 1100/1200/1280px (`interactions.json`).
- The implementation run reports 17 visual tests plus 219 Settings/contact/calendar tests passing: 236 total. An existing Django warning remains.
- Before/after captures and the refreshed phone Assistant capture support visual review. The final review addressed the clipped fourth Assistant starter.

The checks cover the named local routes and interactions. No production deployment was performed. AI sending, OAuth authorization, and checkout were not tested. Figma prototype scrolling, input behavior, and the Save-to-Saved transition still need interactive acceptance; component presence and configured overflow do not prove those interactions work.
