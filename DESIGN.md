---
name: "Networkly"
description: "A clear daily recruiting workspace with cool surfaces, cobalt actions, and purposeful feedback."
colors:
  paper: "#f4f6fa"
  surface: "#ffffff"
  surface-subtle: "#f8fafc"
  surface-hover: "#eef3fb"
  ink: "#19283f"
  ink-2: "#54647a"
  ink-3: "#607087"
  line: "#e1e7f0"
  control-border: "#7e8da4"
  line-strong: "#7e8da4"
  accent: "#2857c7"
  accent-ink: "#214ba9"
  accent-soft: "#eef2fc"
  accent-line: "#c8d5f4"
  on-accent: "#ffffff"
  on-accent-2: "#e0e9ff"
  dark-paper: "#111827"
  dark-surface: "#1b2536"
  dark-surface-subtle: "#222f43"
  dark-surface-hover: "#293950"
  dark-ink: "#eef3fb"
  dark-ink-2: "#b8c5d8"
  dark-ink-3: "#a7b7ce"
  dark-line: "#334158"
  dark-control-border: "#64748d"
  dark-line-strong: "#64748d"
  dark-accent: "#a4bbff"
  dark-accent-ink: "#c6d5ff"
  dark-accent-soft: "#2b374d"
  dark-accent-line: "#526589"
  dark-on-accent: "#14223f"
  dark-on-accent-2: "#273f6b"
  ok: "#2f6a45"
  ok-soft: "#e6f0e9"
  ok-line: "#cbdfd2"
  danger: "#9d2b23"
  danger-ink: "#841f18"
  danger-soft: "#f7e8e6"
  danger-line: "#e9c8c4"
  w-replied-t: "#7d5410"
  w-replied-s: "#f6ecd6"
  w-replied-l: "#e8d7ad"
  dark-ok: "#74c095"
  dark-ok-soft: "#1c2a22"
  dark-ok-line: "#2f4a3a"
  dark-danger: "#e2867c"
  dark-danger-ink: "#e69890"
  dark-danger-soft: "#2e1e1d"
  dark-danger-line: "#4d302d"
  dark-w-replied-t: "#d8b467"
  dark-w-replied-s: "#2b2519"
  dark-w-replied-l: "#463a22"
typography:
  display:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "clamp(58px, 5.85vw, 84px)"
    fontWeight: 650
    lineHeight: 1.015
    letterSpacing: "-.04em"
  headline:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-.025em"
  support-headline:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 650
    lineHeight: 1.13
    letterSpacing: "-.025em"
  title:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "normal"
  body:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  detail:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  button:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 550
    lineHeight: 1.2
    letterSpacing: "normal"
  field:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
  field-touch:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "normal"
  label:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.45
    letterSpacing: "normal"
  legal-body:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.8
    letterSpacing: "normal"
rounded:
  r-ctl: "9px"
  control-radius: "9px"
  r-panel: "16px"
  r-badge: "999px"
  contact-card: "12px"
  task-card: "14px"
  menu: "10px"
  utility: "6px"
spacing:
  s1: "4px"
  s2: "8px"
  s3: "12px"
  s4: "16px"
  s5: "24px"
  s6: "32px"
  s7: "48px"
  s8: "64px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    typography: "{typography.button}"
    rounded: "{rounded.r-ctl}"
    padding: "9px 16px"
  button-primary-hover:
    backgroundColor: "{colors.accent-ink}"
    textColor: "{colors.on-accent}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.button}"
    rounded: "{rounded.r-ctl}"
    padding: "9px 16px"
  input:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.ink}"
    typography: "{typography.field}"
    rounded: "{rounded.control-radius}"
    padding: "10px 12px"
  input-hover:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
  nav-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.r-ctl}"
    padding: "8px 10px"
  status-chip:
    backgroundColor: "{colors.w-replied-s}"
    textColor: "{colors.w-replied-t}"
    typography: "{typography.label}"
    rounded: "{rounded.r-badge}"
    padding: "4px 9px"
  application-filter-selected:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.r-ctl}"
    padding: "9px 14px"
  contact-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.contact-card}"
    padding: "14px"
  firm-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r-panel}"
    padding: "24px"
  picked-role-card:
    backgroundColor: "{colors.surface-subtle}"
    textColor: "{colors.ink}"
    rounded: "12px"
    padding: "20px"
  today-context-expanded:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r-panel}"
    height: "320px"
  disclosure:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r-panel}"
    padding: "16px 20px"
  marketing-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.r-ctl}"
    padding: "13px 21px"
---
# Design System: Networkly

## Overview

**Creative North Star: "The Daily Recruiting Workspace"**

Networkly is a mature, concise, and harmonious SaaS workspace for recruiting and relationships. Cool white and gray layers, dark navy, cobalt actions, and Instrument Sans give the product a consistent identity. A meaningful task, collection, or form owns a bounded surface; facts and actions inside it stay easy to scan.

The approved public pages use larger type, product examples, and finite kinetic details to explain the product. The application uses restrained feedback tied to an action or state. Legal pages prioritize reading, section navigation, and stable anchors. These surfaces share their palette, type family, control language, and factual standards without sharing one page composition.

This is the implemented direction approved during the September 2026 refurbishment. It supersedes the warm editorial prescriptions previously in this file, `docs/design-spec.md`, and `design-system/coverage/MASTER.md`; their applicable functional contracts remain. Earlier review artifacts remain historical evidence. The direction and its final addendum live in `.impeccable/review/saas/direction.md`.

The runtime source of truth is the cascade in `coverage_web/templates/base.html`: `networkly.css`, route head styles, `workspace.css`, `elements.css`, `presentation-crm.css`, `presentation-directory.css`, `presentation-support.css`, then `controls.css`. Route scopes and selector specificity also matter. `marketing.css`, `pricing.css`, `auth.css`, and `legal.css` own their named surfaces. The base stylesheet retains legacy declarations; the later shared and scoped layers determine the current design. Documentation tokens below record effective values, not a proposal to add another CSS theme.

**Key Characteristics:**

- Instrument Sans throughout the current interface, with Title Case headings and subtitles.
- Cool light surfaces and paired navy dark surfaces, with cobalt interaction and labeled semantic states.
- Bounded widgets, natural record heights, useful icons, and visible actions.
- Stored company logos with an initial fallback, preserving the approved Networkly identity.
- Responsive reading order, keyboard access, and restrained motion with a reduced-motion alternative.

## Colors

### Primary

Cobalt `accent` identifies primary actions, selected controls, useful icons, and links. `accent-ink` supplies stronger interaction text and primary hover; `accent-soft` and `accent-line` provide the corresponding selected surface and boundary. `on-accent` and `on-accent-2` are paired text roles for accent fills. The frontmatter is normative for their exact values.

### Neutral

`paper` is the cool workspace ground; `surface` is the primary white widget surface. `surface-subtle` separates insets and resting fields, while `surface-hover` is available for supporting interaction states. `ink`, `ink-2`, and `ink-3` establish the text hierarchy. `line` divides content. `control-border` is the stronger field boundary; `line-strong` aliases it in runtime CSS and records the resolved value here.

`workspace.css` owns the light and dark pairs. Dark mode uses navy layers with pale blue interaction colors, not inverted white cards. Explicit `data-theme` selection and system preference both set native `color-scheme`; retain the persisted `coverage-theme` contract. Frontmatter prefixes dark counterparts with `dark-` only for documentation; runtime CSS reuses the same property names.

`networkly.css` owns the complete domain families for relationship warmth, score, confidence, sponsorship, freshness, success, and danger. The semantic samples in frontmatter demonstrate the paired treatment and do not replace that inventory. The public closing bands intentionally retain fixed cobalt and white. Pricing's preview plan intentionally uses fixed navy with its own pale text, field, and button colors; keep the scoped pair from `pricing.css` together.

The sidecar's tonal ramps are generated swatch previews only. Its canonical colors match frontmatter; the ramps introduce no runtime tokens.

**The Semantic Color Rule.** Use cobalt for interaction. Keep visible labels beside domain colors, including unknown, unverified, pending, and unavailable states.

## Typography

**Display and Body Font:** Instrument Sans, with the platform sans-serif stack in frontmatter. `workspace.css` resolves `--font-display` to `--font-ui`. Instrument Sans is self-hosted as variable WOFF2 with swap loading. Fraunces and Spline Sans Mono remain declared for compatibility; Fraunces is not the current page-heading direction. Mono remains available for explicit code, while ordinary counts use tabular numerals in Instrument Sans.

The primary CRM and directory heading is `headline`; supporting account and assistant headings use `support-headline`. Common section headings use `title`; working copy uses `body`, secondary explanations `detail`, and semantic chips `label`. Shared field text is `field`, changing to `field-touch` at 640px or on coarse pointers. These roles come from `workspace.css`, the three presentation stylesheets, `elements.css`, and `controls.css`.

Public typography has deliberate route variants. The marketing hero uses `display`, with explicit 1100px, 820px, 420px, and 350px adjustments in `marketing.css`; its desktop clamp is not a universal scale. Pricing uses a `clamp(42px,5.5vw,76px)` headline and a 72px price figure. Legal titles use `clamp(30px,4vw,44px)` and legal prose uses `legal-body`. Authentication's orientation title is 36px on desktop. Preserve these local scales rather than forcing all headings to one size.

Working descriptions usually cap at 65–72ch; legal paragraphs wrap within the reading column. Long names, timing, role facts, and URLs wrap where needed. Body and control text is not artificially tracked or uppercased. The approved wordmark is an asset rather than an editable text heading.

**The Case Rule.** Use Title Case for headings and short subtitles; use sentence case for controls, body copy, and explanatory sentences. Preserve acronyms, brand names, and the meaning of stored facts through the existing text-formatting helpers.

## Layout

The shared horizontal header is sticky, with an 80px desktop minimum and a 1440px inner maximum. Destinations use soft selected tabs. At 1050px the app has a 72px compact header, Menu control, and a three-column destination grid; at 640px that grid has two columns. The compact navigation remains available without JavaScript. Public navigation becomes a scrollable destination row below the brand and account actions. `workspace.css` owns this shell.

Page padding starts at `40px 40px 64px`, changes to `24px 20px 40px` at 820px, and to `28px 20px 44px` at 640px. Ordinary app pages cap at 1200px and wide app pages at 1440px above 1100px, with route-specific widths for focused forms and public surfaces. The base spacing scale is 4/8/12/16/24/32/48/64px; repeated 20px, 28px, and 40px values are deliberate local composition values.

| Surface | Implemented Composition |
| --- | --- |
| Today | Four summary shortcuts above the main plan and supporting rail. Market assignment and the Firm Updates / Recent Activity pair sit beneath the plan. Both context panels have 320px outer heights, matched 72px headers, and independently scrollable, keyboard-accessible lists; they stack below a 650px queue width. Firm updates separate company marks, role titles, and compact location or deadline metadata. Activity rows pair contact initials with a name, action/firm line, and timestamp; the whole row opens the contact. Firm Updates starts open and becomes naturally shorter when collapsed. The right rail holds Weekly Outreach, Outreach Schedule, Upcoming Deadlines, and setup, preserving market and timezone context. |
| Network Contacts | Four columns at 1280px and above, two at 1100–1279px, and one below. Cards are naturally sized with 12px gaps; a tall record does not stretch its neighbors. Relationship groups use full-row summary controls and complete-row scroll previews. |
| Network Firms | Three columns at 1200px and above, two at intermediate widths, and one on phones. `grid-auto-rows: max-content`, `align-items: start`, and `align-content: start` preserve natural rows in capped collections. |
| Opportunities | Ordinary firm surfaces preview three complete lead rows with grouped locations. Picked roles use individual cards in two columns above 1000px and one at or below it, with 16px gaps and four complete cards in the initial preview. Both variants have a counted expansion footer; without enhancement, the full list remains visible. |
| Applications | Wrapping labeled count filters above bounded application records. Role identity, stage editing, timing, and contact disclosure remain separate. The records stack at 820px; actions wrap without covering facts. |
| Contact, Calendar, and Assistant | Contact history and capture have distinct surfaces; capture fields stack on phones. Calendar preserves its time grids and agenda geometry. Assistant has a bounded history area, optional starters, and a clear composer with reachable actions. |
| Settings and Onboarding | A 200px settings index sits beside 24px-inset sections with a 32px gap. At 820px the index becomes a disclosure and the content stacks. Firm choosers reveal complete matches and preserve selected values during search. Cadence pairs fields in a shared row grid, aligns control centers and dividers, and reserves 68px number / 82px unwrapped unit tracks; phones use one column with compact descriptions. |
| Marketing and Pricing | Marketing uses a 1280px wrap, large split hero, explicit example panels, open sections, and a cobalt close; major sections stack at 820px. Pricing caps at 1120px, pairs plan cards, and stacks them at 760px. The comparison table keeps horizontal scrolling inside its own boundary. |
| Authentication and Legal | Authentication pairs orientation with a 400px form column and stacks before clipping. Legal uses a 200px section index and document column with a 40px gap; at 860px the index wraps above the document. The legal page caps at 1180px, with 32px/40px document insets and smaller phone insets. |

The exact breakpoints and narrow-phone exceptions remain in the source styles. Today context is composed in `crm/_today_context.html`; cadence fields are in `accounts/settings.html` and `presentation-support.css`. The explicitly requested 320px Today context panels are a deliberate exception to natural outer height. Contact and firm record cards remain content-sized; picked-role cards share their content-defined grid row height. Do not add fixed record heights or pixel-cropped role previews. Content, errors, and controls must retain usable space.

## Elevation & Depth

White widgets sit on cool ground with single-pixel borders; inset surfaces group related work. Most app cards are shadowless at rest. `shadow-1` is a low interaction shadow, `shadow-widget` is available for small bounded widgets, and `shadow-2` separates floating menus, dialogs, and drawers. Their exact light/dark values are recorded in the sidecar from `workspace.css`. Legal documents remain quiet and flat. The marketing product illustration and journal use scoped diffuse shadows; pricing uses a restrained card hover.

Application feedback uses `--motion-press: 120ms`, `--motion-state: 180ms`, `--motion-reveal: 240ms`, and `--ease-widget: cubic-bezier(.16, 1, .3, 1)`. Buttons have local press and subtle hover feedback; ordinary contact and task cards do not lift. User-opened disclosures and updated filter results receive a short 200ms reveal in `widgets.js`. A 900ms alternating pending mark exists only during actual POST work; it is not a decorative idle animation. Errors use a visible danger outline.

Public motion is finite and scoped: the marketing connection draws once over 1.8s, observed sections reveal over 800ms, and demo tabs switch over 400ms. Pricing has short arrival, panel-switch, and pointer-hover feedback. `marketing.js` controls the public reveals without requiring motion to read the content. The app has no shared page-arrival choreography. Legal has no decorative motion. All surfaces honor `prefers-reduced-motion`; the app's pending mark becomes static and spatial effects are removed.

**The Stable Layout Rule.** Keep record geometry stable on hover, focus, and loading. Let contact and firm records size to content, retain the explicitly sized Today context panels, and reveal complete role previews. Reserve logo dimensions. Finite transforms may provide local feedback without changing document flow.

## Shapes

Shared controls use `r-ctl` and `control-radius`; major groups use `r-panel`. Task and firm cards use the 14px local radius, compact contact and picked-role cards 12px, menus 10px, and small utilities 6px. These documented local names describe existing CSS values, not new runtime custom properties. Semantic status chips retain `r-badge`. Inner records usually use dividers rather than another enclosing card. Reserved, contained logo boxes keep the row stable as images load or fail.

## Components

### Buttons and Fields

Primary buttons pair accent fill with on-accent text; secondary buttons use surface, ink, and a strong border. The shared `.btn` baseline is 40px high with `9px 16px` padding and 14px/550 text; local controls deliberately vary. Common text fields, search fields, native selects, and enhanced select buttons use the final `controls.css` baseline: 42px minimum, 9px corners, `10px 12px` padding, 14px text, and `surface-subtle`. On phones at 640px or coarse pointers, fields become 44px with 16px text. Shared phone buttons are 44px; authentication's password input and wrapper are 46px, marketing CTAs are 52px, and pricing CTAs are 48px. Do not claim every desktop control is one height.

Common fields have visible labels, a persistent strong border, accent focus, a visible invalid state, and separate help/error copy. Select carets reserve 36px of right padding and switch color with the theme. `controls.css` is loaded last so the same resting field shape is used across route families. Search has one frame around its icon and input. Native textareas remain vertically resizable; embedded composers own their enclosure.

### Selects, Navigation, and Dialogs

The enhanced select keeps the original native value and form contract. A browser top-layer popover escapes clipped cards where supported; the menu remains next to the control in the DOM, wraps long choices, and preserves selected/disabled state, keyboard handling, and focus. See `base.html` and `controls.css`. Keep per-region work-authorization selectors individually labeled and retain accessible alternatives for firm tier changes.

Navigation uses a rounded accent-tinted current destination, with useful icons in the compact app menu. Preserve active-page, expanded, pressed, selected, and disabled semantics. Menu closes on Escape and returns focus. Dialogs and drawers have defined headings, wrapping actions, controlled scrolling, and `shadow-2`; shared dialogs use 24px padding and a `calc(100dvh - 32px)` height bound. Command search keeps its close control visible and its result list scrollable within the viewport.

### Widgets, Status, and Disclosures

A task or collection owns its surface. Contact and firm identity, contextual facts, time, and actions form distinct groups with visible controls. Status wording carries meaning alongside its semantic palette. Relationship stages remain named categories, not a numerical progress meter. Application filters expose `aria-pressed` and announce the current visible count; preserve the authoritative server rows and no-JavaScript behavior.

Use a full-width summary target for a group disclosure, with a clear indicator and complete revealed content. Opportunities previews and Network collection caps reveal complete records. Today context is different: fixed headers stay visible above independently scrolling lists with accessible names, tab stops, focus outlines, and stable scrollbar gutters. Its expanded 320px panels retain their outer height as lists scroll; collapsing Firm Updates intentionally reduces its height. Hover, loading, or entrance effects must not cause incidental layout shifts.

Picked-role cards use the company logo or monogram, the full wrapping title, grouped requirements and fit facts, a divided deadline/provenance strip, a native Why Picked disclosure, and bottom-aligned actions. Their inset is 20px, reducing to 16px at 640px; action targets are 42px on desktop and 44px at 640px. At 480px, Save and View share two equal columns while Not for me spans the row. Hover changes the border and subtle fill without lifting the card. Preserve existing date uncertainty, underlying role links, and form actions. See `directory/_rolecard.html`, `presentation-directory.css`, and the four-versus-three preview rule in `widgets.js`.

### Logos and Icons

Preserve the approved Networkly connected two-person N, custom lettering, full-lockup proportions, source raster silhouette, theme-aware mask, and unique per-placement IDs in `_wordmark.html`. Header and footer links keep the accessible name “Networkly home.” Favicon and compact exports use the same supplied identity.

Company marks come from stored `Firm.logo` assets. `crm/_firm_mark.html`, directory firm templates, and account firm lists use a contained image on white with an initial fallback if absent or failed. CRM's standard mark is 28px, with 21px contact context and 32px firm-card variants; directory list marks are 38px and the firm detail mark is 60px, reducing to 48px on small phones. Keep explicit dimensions, `object-fit: contain`, decorative empty alt text beside the visible firm name, and the shared failure handler. Do not invent or retrieve substitute external logos for presentation.

Use the existing inline SVG icon vocabulary in `_nav_icon.html`, `_icon.html`, and `directory/_section_icon.html` when it identifies an action, category, or firm context. Most icons are 16–20px, with larger page-heading variants. Text labels remain where an icon alone would be ambiguous. Decorative icons must not duplicate the accessible label.

### Surface Variants and Truthfulness

Public examples are labeled as examples; source inventory, prices, availability, account state, and legal copy come from the current templates and data. The design system does not authorize new claims. Marketing can explain a workflow with finite motion. App feedback must describe a real interaction or pending state. Legal content preserves its section anchors, readable text, and print treatment. Shared styling must retain route, form, HTMX, theme, and data contracts.

## Do's and Don'ts

### Do

- Do reuse the final runtime tokens and scoped page styles, including explicit and system-selected dark themes.
- Do use Instrument Sans and the approved case hierarchy across public and private surfaces.
- Do give a task, form, or collection a clear surface; separate its internal facts with spacing and dividers.
- Do keep full labels, useful icons, stored firm logos, native form values, keyboard focus, and visible actions.
- Do size contact and firm records naturally, preserve the explicitly sized Today context panels, and keep role previews complete.
- Do tie application motion to user input or actual pending state, and honor reduced motion.
- Do preserve product truth, uncertainty, example labels, supported routes, and theme compatibility.

### Don't

- Don't revive the superseded warm paper, serif page titles, transparent newspaper-style widgets, or vertical navigation rail.
- Don't replace company logos with invented brands, fetch new external logos for decoration, or recreate the Networkly lockup in type.
- Don't hide required actions on hover, clip labels to force alignment, compress card rows, or animate layout dimensions.
- Don't add endless decorative motion, fabricated counters, activity pulses, or numerical progress for categorical relationship stages.
- Don't apply a public hero's type scale or entrance choreography to working app pages or legal documents.
- Don't treat historical CSS comments or review artifacts as authority over the current cascade and approved direction.
