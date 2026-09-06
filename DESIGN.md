---
name: "Networkly"
description: "A personal recruiting index with editorial headings, open records, and clear actions."
colors:
  paper: "#f7f7f2"
  surface: "#ffffff"
  ink: "#252b2e"
  ink-2: "#596365"
  ink-3: "#697371"
  line: "#dedfd8"
  line-strong: "#a6afaa"
  accent: "#2857c7"
  accent-ink: "#214ba9"
  accent-soft: "#eef2fc"
  accent-line: "#c8d5f4"
  on-accent: "#ffffff"
  on-accent-2: "#e0e9ff"
  dark-paper: "#191e20"
  dark-surface: "#22282b"
  dark-ink: "#edf0ec"
  dark-ink-2: "#b6c0bf"
  dark-ink-3: "#a6b1ae"
  dark-line: "#3b4446"
  dark-line-strong: "#6e7c78"
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
typography:
  headline:
    fontFamily: "Fraunces, Georgia, Times New Roman, serif"
    fontSize: "38px"
    fontWeight: 400
    lineHeight: 1.15
    letterSpacing: "-.025em"
  headline-phone:
    fontFamily: "Fraunces, Georgia, Times New Roman, serif"
    fontSize: "34px"
    fontWeight: 400
    lineHeight: 1.15
    letterSpacing: "-.025em"
  title:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "18px"
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
  label:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.45
    letterSpacing: "normal"
rounded:
  r-ctl: "8px"
  r-panel: "12px"
  r-badge: "999px"
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
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r-ctl}"
    padding: "9px 14px"
  nav-active:
    backgroundColor: "transparent"
    textColor: "{colors.accent-ink}"
    rounded: "0"
    padding: "0"
  status-chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.r-badge}"
    padding: "4px 9px"
  application-filter-selected:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.r-ctl}"
    padding: "9px 14px"
  record-row:
    backgroundColor: "transparent"
    textColor: "{colors.ink}"
    rounded: "0"
    padding: "22px 0"
  capture-surface:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r-panel}"
    padding: "20px"
---
# Design System: Networkly

## Overview

**Creative North Star: "The Personal Recruiting Index"**

Networkly uses the order and reading comfort of a contemporary university library catalogue. Warm neutral ground, editorial page titles, cobalt actions, and open ruled records give recruiting information a clear place. The material is digital: flat fills, real evidence, and familiar controls.

The built system gives records more space than their containers. Identity, context, timing, and actions form readable groups; supporting information sits beside the work on wide screens and follows it on phones. Forms and floating menus retain useful boundaries. Clear status wording carries meaning alongside color.

This document records the implemented September 2026 redesign. The visual cascade in `coverage_web/templates/base.html` is `networkly.css`, route styles, `workspace.css`, `elements.css`, then `presentation-crm.css`, `presentation-directory.css`, and `presentation-support.css`. Base styles own self-hosted fonts, semantic palettes, and control behavior; the later layers own the shell and page compositions. Read specificity as well as load order. This file supersedes historical visual prescriptions in `docs/design-spec.md` and `design-system/coverage/MASTER.md`; their functional contracts still apply. The build is code-led; no external comp is a pixel authority.

The approved Networkly lockup is binding. `_wordmark.html` preserves the original raster silhouette through a luminance mask with unique IDs per placement; theme-aware blue and ink fill its original color regions. Preserve the connected two-person N symbol, custom lettering, source asset, and full-lockup proportions. Header and footer links expose the accessible name Networkly home. Compact marks and email raster exports remain the same identity.

**Key Characteristics:**

- Normal-weight serif page titles with a quiet sans-serif working hierarchy.
- Warm neutral surfaces, cobalt interaction, and distinct semantic states.
- Open ruled records with visible actions and restrained form enclosures.
- Horizontal navigation, responsive reading order, and paired light and dark themes.

## Colors

### Primary

Cobalt (`accent`) identifies primary actions and active navigation. `accent-ink` supplies selected text and primary hover; `accent-soft` and `accent-line` identify selected filters and choices. Text on accent fills uses `on-accent`, which changes with the theme. Secondary text on the same fill uses `on-accent-2`.

### Neutral

Warm paper (`paper`) grounds the page; `surface` provides white form and overlay areas. Ink, secondary ink, and quiet ink establish three text roles. Fine lines divide records; strong lines define controls or section boundaries. Frontmatter records light tokens and their `dark-` counterparts. Runtime CSS reuses the same variable names for both themes.

Explicit theme selection and system preference both set native `color-scheme`, so date/time picker affordances match the page. The persisted `coverage-theme` key and `data-theme` contract remain compatible. The base stylesheet owns the full light/dark semantic families for warmth, score, confidence, sponsorship, freshness, success, and danger; the frontmatter's semantic samples do not replace those families.

**The Semantic Color Rule.** Use cobalt for interaction. Preserve the existing domain colors and visible labels for their named states, including unknown and unverified facts.

## Typography

**Display Font:** Fraunces, with Georgia and Times New Roman fallbacks.
**Body Font:** Instrument Sans, with the platform sans-serif stack.
**Data Font:** Spline Sans Mono remains available for explicit code and numeric treatments.

All three families are self-hosted variable WOFF2 fonts declared in the base stylesheet with swap loading. Serif titles establish page identity; sans-serif labels, facts, and actions support scanning. The approved logo is an asset, not a typeset approximation.

The primary CRM and directory title role uses the frontmatter headline. CRM titles reduce to the phone headline at (600px); directory titles do so at (720px). Supporting page titles use (38px/1.13) and usually reduce to (32px) at (680px). Authentication retains its local (38px) phone title. Public hero headings have their own larger responsive scale. These are route variants, not a universal display-size clamp.

Section titles generally use (17–18px), weight (600); settings section titles use (22px). Working body text follows the frontmatter body role. Secondary explanations use the detail role; chips use the label role. Native field text starts at (15px/1.4), with directory filter fields at (14px/1.4). Phone field rules raise common inputs to (16px), with some route-specific composer styles retained. Descriptions typically constrain reading width to (65–72ch). Counts use tabular numerals; they do not require a monospace face.

**The Readable Label Rule.** Navigation, labels, chips, and actions use normal or sentence case without forced uppercase or tracking. Proper names, stored values, and quoted evidence preserve their original meaning.

## Layout

The sticky horizontal masthead has an (80px) desktop height, a bottom divider, and a (1440px) maximum inner width. The logo, six destinations, search, and account controls share one line. At (1050px), the workspace uses a compact (72px) header with a Menu control and three-column destination grid; at (640px), destinations use two columns. Without JavaScript the grid stays visible. Public navigation instead becomes a horizontal scrollable destination row below the logo and account actions.

Default page padding is (40px 40px 64px), with ordinary workspace pages capped at (1200px) and wide pages at (1440px) above (1100px). Shared padding becomes (24px 20px 40px) at (820px) and (28px 20px 44px) at (640px), with deliberate page-local exceptions. Spacing uses the base scale and recurring (20px), (28px), and (40px) gaps.

Today has a ruled factual summary, a collapsed weekly-updates disclosure, open action records, and a (290px) supporting column separated by a vertical rule. At (900px), that support moves below the main work. The action queue uses its own container width: below (680px), records stack identity, evidence, and actions; the final phone spacing uses compact section gaps while retaining (44px) primary targets. This places the first action group in the reviewed phone arrival view; arbitrary content length can extend it.

Opportunities groups each firm in one horizontal band: a (250px) identity column and a broad role column with a (36px) gap. Each role list previews three complete lead rows with their grouped-location disclosures. A counted footer reveals the remaining rows; lists have natural height and show every rendered row when JavaScript is unavailable. At (720px), firm identity sits above roles. Applications uses wrapping labeled count filters above ruled rows, not boxed metric tiles. Network is a roster whose firm context and actions reflow beneath identity as space narrows. Its firm grid uses natural content-sized rows; a collapsed viewport never compresses cards into shorter tracks. Application stage controls precede a disclosure containing contacts at that firm. Contact records use open journal sections, a separate capture form, and supporting facts beside them.

Settings has a (200px) section index beside open ruled sections, with a (64px) gap at wide sizes. The index becomes an inset disclosure and the layout becomes one column at (820px). Selected firm lists use natural height. Add-firm search previews five complete matching rows with a result count and an explicit control to show all matches; the no-JavaScript fallback shows all rows. Assistant keeps an open reading area with divided starters and an enclosed composer. Calendar uses time-based grids and agenda rows; responsive forms and day views retain their own geometry. Legal reading content caps at (760px). Public examples and authentication layouts stack at (820px) so their narrower columns cannot clip headings or content.

## Elevation & Depth

Page content is flat at rest. Warm ground, white working surfaces, spacing, and single-pixel rules establish depth. Menus, dialogs, drawers, and the raised panel use the second shadow token; the sidecar records both theme pairs. Inputs retain their soft accent focus glow. Selected theme and segmented choices have a small local shadow.

Shared page entrances are disabled. Feedback is local: press (120ms), color/border state (180ms), and overlay reveal (240ms), with shorter menu reveals. A pending mutation uses a slim progress mark; failure uses a danger outline. Reduced motion removes spatial transitions and leaves a static pending mark. This feedback describes actual activity, not decoration.

**The Stable Surface Rule.** Record collections and page sections stay still on hover. Use color or border emphasis for interaction and reserve substantial shadow for floating content.

## Shapes

Controls have gently curved corners through `r-ctl`; grouped form surfaces use `r-panel`. Status badges keep rounded ends through `r-badge`. Menus use their smaller local radius and utility choices use the utility radius. Most recurring records have square corners with a bottom rule and transparent fill. These open records are the default reading structure; capture forms, composers, and overlays have their own bounded shape. Calendar event labels retain compact local corners.

## Components

### Buttons

Primary buttons pair accent fill with on-accent text; secondary buttons use surface fill, ink text, and a strong border. Shared buttons have a (40px) desktop minimum and (44px) phone minimum. Page-local compact controls retain their explicit variants. Hover changes fill or border without lift. Keyboard focus uses a (2px) accent outline with a (3px) offset; press feedback scales widget buttons to (.975) unless reduced motion is enabled. Disabled state remains visible and noninteractive. Destructive actions retain the danger palette.

### Inputs / Fields

Fields use surface fill, strong borders, control corners, visible labels, and separate explanatory or error text. Focus uses an accent outline at zero offset and a soft (3px) accent glow. Native and enhanced selects retain form submission and keyboard contracts. Checkbox and radio indicators remain visible; invalid fields use danger. Date and time affordances follow the root color scheme. Native textareas remain vertically resizable.

### Navigation

Desktop destinations are plain text with an accent bottom rule and stronger weight on the active page. Navigation icons appear in the compact menu. Menu exposes expanded state; Escape closes it and restores focus. Directory scope tabs use soft selected fills, while shared scope tabs use an underline. Preserve the actual route variant and its accessible current-page state. Search and account affordances remain separate from destinations.

### Chips and choices

Status chips use normal-case wording, semantic text/surface/border pairings, and rounded ends. Selected filters use control corners, accent tint, and explicit pressed or checked state. Relationship stages are wrapping categorical labels with the current category highlighted; the contact record does not render them as a numerical progress bar. Work-authorization choices retain native radio indicators and equal-height labeled targets.

### Records and grouped surfaces

Today tasks, firm bands, application rows, roster entries, and settings sections use open dividers. Identity and evidence remain separate from actions, and actions wrap without overlaying facts. Role and contact actions are persistently visible. Forms, composers, dialogs, and selected supporting widgets use bounded surfaces where they help users act. Avoid carrying obsolete card padding or hover lifts into open page sections.

### Collection controls

Application stage filters expose `aria-pressed` and operate on the authoritative rows. Preserve the live visible-count announcement, empty-filter guidance, focus restoration after replacement, and disabled enhancement when JavaScript is unavailable. Firm expansion uses a real button with Expand/Collapse wording and `aria-expanded`; it reveals complete hidden records while keeping the header reachable on collapse. Preserve the natural-height full list when the enhancement is unavailable.

### Calendar and capture

Calendar categories retain their colors and text. Month-cell add controls appear on hover or focus and remain available for coarse pointers. Agenda events and form actions use larger targets. Contact capture has a white, rounded form surface with visible labels and optional wording; its history remains a separate open section. Outreach schedules state timing in text, and native progress represents actual completed/goal values only.

### Assistant and overlays

Assistant starters form an open divided list. The bordered composer marks the editing area; draft subject, body, and actions remain distinct. Dialogs and drawers use the raised shadow, clear headings, constrained scrolling, and grouped wrapping actions. Dialogs have (24px) padding and a maximum height of (100dvh - 32px). Command search uses vertically grouped, fully wrapping result names and context, a visible close button, and keyboard selection announced through the search field. Its result list scrolls inside a dialog bounded by the viewport, including short landscape windows.

### Identity and compatibility

Preserve the approved lockup and mark, asset paths, per-placement mask IDs, accessible link names, and theme-aware fills. Styling changes keep existing URLs, field names, named IDs, data attributes, htmx targets, stored categories, and browser persistence keys. Product facts and uncertainty remain literal; examples on public pages stay labeled. These contracts allow the recorded visual system to evolve without changing user data or behavior.

## Do's and Don'ts

### Do:

- Do use runtime CSS variables so explicit and system-selected dark themes remain paired.
- Do use Fraunces for page identity and Instrument Sans for working information and controls.
- Do organize records with spacing and dividers, retaining useful boundaries around forms and overlays.
- Do keep role and contact actions visible, with their larger phone targets.
- Do preserve native controls, keyboard focus, disclosure state, reduced motion, and persistence compatibility.
- Do preserve the approved Networkly logo and explicit wording for categorical or uncertain facts.

### Don't:

- Don't reintroduce the discarded vertical navigation rail, cool blue page ground, boxed summary tiles, or page-header eyebrows.
- Don't replace semantic labels with color alone or style unknown facts as confirmed outcomes.
- Don't revive uppercase small labels, hover lifts, decorative page entrances, or literal paper textures.
- Don't copy historical CSS fragments without checking the final page-family cascade.
- Don't turn relationship categories into a numerical meter or use decorative progress to imply activity.
