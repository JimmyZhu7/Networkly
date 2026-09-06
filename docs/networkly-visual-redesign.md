# Networkly visual redesign — September 2026

The founder explicitly requests a total visual replacement, concise harmonious presentation, and parallel Astra high work. Visual choices are delegated; the approved Networkly logo and all product behavior remain binding. Build code-led, directly in the app; no further concept approval is required by the user.

## Direction

THESIS: Recruiting records should read like a clear personal index: find the next useful item, understand its evidence, act without searching for controls.
OWN-WORLD: A contemporary university library catalogue and reading room. Editorial typography, open ruled lists, warm neutral ground, cobalt navigation, calm selection. This is a digital product, with no literal paper textures, index-card costumes, or invented content.
STORY: Today directs action; Opportunities supports finding and comparing; Network makes relationships legible; Calendar explains time; Assistant helps with one question; Settings groups decisions. Public pages demonstrate these functions with clearly labeled examples.
FIRST VIEWPORT: Slim horizontal navigation, generous heading, concise explanation, then actual work. Today uses a factual inline summary and an action-led agenda. Opportunities uses a coherent search/filter area and firm-grouped lists. Main working content begins within the first viewport on desktop and phone.
FORM: Direction seed b7a912e1, corroborated by the printed concept roll. Warm white #f7f7f2 / white #ffffff / ink #252b2e / secondary #596365 / line #dedfd8 / cobalt #2857c7. Dark: #191e20 / #22282b / #edf0ec / #b6c0bf / #3b4446 / #a4bbff. Existing semantic status colors remain distinct. Instrument Sans for body/controls; existing Fraunces for primary page titles and select public headings only, normal weight. No uppercase labels. Controls 40px minimum, primary phone targets44px. Corner language 8px controls,12px grouped surfaces. Use spacing and dividers before card enclosures.
FINISH: Aligned field labels, persistent actions, honest states, real accessible controls. Understated selection/expansion feedback, never perpetual motion. No gradients, decorative eyebrows, floating blobs, fake progress, tiny lettering, or data masked as decoration. Reduced-motion, keyboard and both themes remain supported.

## Invention record

Seven grounded candidates: university bulletin (screen), professional address-book application (screen), transit wayfinding (environment), photographic contact sheet (print), contemporary library catalogue (screen), investment-research report (print), conference wayfinding (environment). Direction seed b7a912e1 assigns candidate5; acknowledged and selected under the founder's delegated decision authority.

Catalog challengers were fused with recruiting tasks and declined on audience identification and product clarity: camcorder HUD (raises clear focused selection), Japanese high-density web (raises information efficiency), deep-dive profile (raises location/orientation clarity), origami sequence (raises progressive steps), one-bit desktop (raises control/state consistency). Those disciplines improve the selected catalogue; their visual costumes do not transfer. Category-standard dashboard was considered but does not meet the requested total visual replacement. No external comp is a pixel authority; this contract and the approved logo are the review references.

## Parallel implementation boundaries

Root owns base.html, shared navigation, networkly.css, workspace.css, elements.css, global JS, integration and final checks. Three final page-family stylesheets are loaded after shared controls; scope every rule to owned page roots, never change global tokens or generic controls in them.

1. Core-workflows agent: templates/crm and static/css/presentation-crm.css. Today, network/contact/recovery collections, calendar and debrief. Preserve all routes, request payloads, data attributes, named IDs and categorical meaning.
2. Opportunities agent: templates/directory and static/css/presentation-directory.css. Feed, applications, firm pages, drawers and nested people/role widgets. Preserve firm grouping and exact factual distinctions.
3. Supporting-pages agent: templates/accounts, account, core, assistant, legal, socialaccount, analytics, 404/500 and static/css/presentation-support.css. Settings, public/auth/onboarding, Assistant and secondary pages. Preserve Networkly identity and access/plan/legal truths.

No agent edits another agent's files, shared styles/base, backend behavior, tests, brand assets, or output/. Do not run DB test suites in parallel. Agents can inspect source/browser read-only and compile templates. Root integrates and runs tests, then independent finish review and final design documentation.

## Implementation and verification

The shared masthead, typography, themes, and controls are implemented in `workspace.css` and `elements.css`; three final page-family stylesheets own CRM, directory, and supporting layouts. The approved identity is unchanged. Native browser controls follow the selected theme, and the first populated phone agenda action group fits within 390×844 with 44px targets.

Verification on September 5, 2026: 97 templates compile and Django's system check passes. The final full regression run passed 11,252 tests with 13 optional tests skipped and two failures in old filter-label markup assertions. Those two assertions were corrected to preserve live-count ownership across layout wrappers; all 190 affected directory tests then passed. A separate 301-test account/core/CRM/Assistant run passed. No product code changed after the full run.

Browser verification covered 91 route/theme/viewport and widget captures, with no horizontal overflow or JavaScript errors. Eleven demo interaction flows and five read-only widget checks passed. Temporary test records were removed. The independent finish review's three required corrections were scored resolved: phone agenda actions, dark native picker icons, and design-system persistence. Capture and review files remain local under the ignored `.impeccable/review/visual-redesign/` directory.
