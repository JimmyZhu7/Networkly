# UI refurbishment, September 2026

## Direction contract
THESIS: A clear recruiting workspace: destinations on the left, the current task in front, supporting context beside it.

OWN-WORLD: Cool white surfaces, slate text, a precise blue selection, quiet borders, consistent sans-serif controls, and restrained status colors.

STORY: Orient, inspect, act. Preserve firms as the organizing object and make the relationship loop visible.

FIRST VIEWPORT: A 208px desktop rail; compact title and useful description; an explicit primary action; task content immediately beneath. Mobile uses an expandable navigation menu and a single content column.

FORM: Direct implementation selected under the founder's explicit delegation. Clear workbench, rather than editorial ledger. No generated visual assets are needed.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance.

## Implementation

`workspace.css` owns the shared visual layer and loads after route styles. The existing Django templates, htmx actions, semantic status colors, and URLs remain the functional foundation. `workspace.js` controls the responsive menu and the settings-section disclosure. `DESIGN.md` is the current visual reference; historical aesthetic specifications now point to it.

The navigation rail gives each destination a persistent position and a visible selected state. Network puts contacts before firm coverage, with direct section links. Opportunity facts sit above visible Save and Read actions. The Today queue, application stages, calendar, contact forms, settings, and assistant share the same typography and surface hierarchy. On phones, navigation expands from the header and content becomes a single column.

The browser pass also corrected three interaction defects: native search-input Escape behavior in the command palette, an existing contact-search CSS specificity conflict, and header-height assumptions that no longer applied to the desktop rail or breakpoint transitions.

## Verification evidence

- Authenticated demo checks covered eleven flow groups: sign-in, global search, role search and details, save/stage/remove, contact creation/editing/touch logging, contact filtering and selection, calendar views, settings and theme persistence, phone navigation, and responsive filters.
- Twenty-nine authenticated route/viewport/theme checks and six public route/viewport checks reported no horizontal overflow or JavaScript errors.
- Browser-created contact and application records were removed after verification. No founder data was used for writes.
- An independent Astra finish reviewer returned `ship`, with no material fixes. It inspected the required desktop/mobile captures and eight additional route/theme captures, plus sampled source. Review notes and screenshots stay local under the ignored `.impeccable/review/` directory.
- The design detector ran once. It reported legacy-template warnings and could not resolve Django static stylesheet links; it was not treated as proof of a clean render. The authored workspace stylesheet had no detector findings.
- External Gmail OAuth, paid assistant generation, billing, and live ATS network calls were not exercised. The existing demo avatar resource is missing; the fallback rendered. The fixture audit separately identified a pre-existing debug account from September 2, which this UI work did not alter.

The completed full regression gate, `uv run pytest -n 4 -q`, passed with **11,236 passed, 13 skipped, 5 existing Django deprecation warnings** in 370.30 seconds. The skips comprise twelve opt-in live network checks and one unseeded-directory case. Django's system check reported no issues. Browser evidence is in `.impeccable/review/functional-checks.json`, `final-pass.json`, and `public-pass.json`.
