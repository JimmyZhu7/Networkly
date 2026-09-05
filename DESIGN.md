---
name: Coverage
description: A clear recruiting workspace with restrained color and visible actions.
colors:
  paper: "#f6f8fb"
  surface: "#ffffff"
  ink: "#202939"
  ink-2: "#536174"
  ink-3: "#647185"
  line: "#e1e7ef"
  line-strong: "#a4afbf"
  accent: "#2857c7"
  accent-ink: "#214ba9"
  accent-soft: "#edf2ff"
  accent-line: "#c7d5f7"
  on-accent: "#ffffff"
  on-accent-2: "#e0e9ff"
  dark-paper: "#131923"
  dark-surface: "#1b2432"
  dark-ink: "#edf2fa"
  dark-ink-2: "#b5c1d3"
  dark-ink-3: "#9baac0"
  dark-line: "#303e52"
  dark-line-strong: "#62748e"
  dark-accent: "#9dbaff"
  dark-accent-ink: "#c0d2ff"
  dark-accent-soft: "#263655"
  dark-accent-line: "#435b89"
  dark-on-accent: "#14223f"
  dark-on-accent-2: "#273f6b"
typography:
  headline:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "30px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-.025em"
  title:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "normal"
  body:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
    letterSpacing: "normal"
  description:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "Instrument Sans, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "normal"
rounded:
  r-ctl: "8px"
  r-panel: "12px"
  r-badge: "999px"
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
    typography: "{typography.label}"
    rounded: "{rounded.r-ctl}"
    padding: "8px 14px"
  button-primary-hover:
    backgroundColor: "{colors.accent-ink}"
    textColor: "{colors.on-accent}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.r-ctl}"
    padding: "8px 14px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r-ctl}"
    padding: "9px 14px"
  nav-active:
    backgroundColor: "{colors.accent-soft}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.r-ctl}"
    padding: "11px 12px"
  status-chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.r-badge}"
    padding: "3px 11px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.r-panel}"
---
# Design System: Coverage

## Overview

**Creative North Star: "A Clear Recruiting Workspace"**

Coverage presents a clear recruiting workspace: destinations on the left, the current task in front, supporting context beside it. Cool surfaces, slate text, precise blue selection, and quiet borders make dense recruiting records easy to scan.

This records the implemented September 2026 refurbishment. New shared visual work follows this document and `coverage_web/static/css/workspace.css`, loaded after route styles in `coverage_web/templates/base.html`. Base primitives, semantic status palettes, and self-hosted fonts remain in `coverage_web/static/css/coverage.css`. Route-specific structure still belongs to its templates. Historical visual prescriptions in `docs/design-spec.md` and `design-system/coverage/MASTER.md` are subordinate; their product and functional contracts are not replaced.

**Key Characteristics:**

- Sans-serif page hierarchy and controls.
- Blue selection and actions; separate semantic status colors.
- Flat bordered surfaces with persistent row actions.
- Responsive navigation and both color schemes.

## Colors

### Primary

Precise blue (`accent`) fills primary actions; `accent-ink` supplies their hover state and selected text. `accent-soft` and `accent-line` mark selection without competing with record content. Pair fills with `on-accent`, never a fixed white label.

### Neutral

Cool ground (`paper`), white panels (`surface`), slate text (`ink`, `ink-2`, `ink-3`), and two border strengths (`line`, `line-strong`) establish hierarchy. Frontmatter lists light values and their `dark-` counterparts; runtime CSS retains the same variable names in both themes. System preference applies unless an explicit theme is selected. Semantic status families remain defined in the base stylesheet, including their dark counterparts; they are not additional brand accents.

**The Semantic Color Rule.** Use the accent for navigation, selection, and actions. Preserve the existing warmth, confidence, sponsorship, and outcome tokens for their named states.

## Typography

Instrument Sans is the shared workspace heading, body, and control face, with the fallback stack recorded above. The hierarchy is compact: page headline, section title, body, description, and control label. Page descriptions cap at (65ch). Ordinary workspace headlines reduce to (28px) at the intermediate layout and (27px) on phones; the compact header retains its more specific desktop size until the phone override.

The three vendored families remain available. Fraunces survives on existing non-workspace display surfaces; Spline Sans Mono remains for explicit numeric/data treatments. Neither is the default for a new workspace heading. Summary figures use tabular numerals with the sans-serif face.

**The Readable Label Rule.** Keep source labels readable. Workspace navigation uses normal case; status badges retain their existing CSS uppercase treatment. Names follow the Title Case decision; prose stays sentence case.

## Layout

Above (1100px), a fixed (208px) navigation rail offsets main content. Workspace pages cap at (1600px); ordinary pages excluding wide, full, and assistant layouts cap at (1120px). Base narrow forms retain their own rules outside that workspace override. Default page padding is (36px 32px 48px).

At (1100px) and below, navigation becomes a sticky top bar with an expandable destination grid. Without JavaScript, destinations remain visible. At (820px), Today and settings become single-column layouts and page padding becomes (24px 20px 40px). At (640px), padding is (24px 16px 36px), navigation uses two columns, headers wrap, and record cards stack. Reuse the base spacing steps; recurring panel insets also use (20px) and gaps use (28px).

Firm containers organize role rows; role facts sit above persistent actions. Today pairs an action column with a (280px) supporting rail on wider screens. Respect each route's actual grid rather than imposing one universal card layout.

## Elevation & Depth

The workspace is flat at rest. Surface contrast and fine borders separate content; the raised panel uses the second shadow token for floating content. The sidecar records the light and dark shadow pair. Inputs retain their focus glow. Shared page entrances and decorative title strokes are suppressed; existing interaction feedback and live activity indicators remain, with reduced-motion overrides.

**The Stable Surface Rule.** Shared panels and the refurbished cards do not lift on hover. Use border emphasis for inspection and the raised panel treatment for floating surfaces.

## Shapes

Controls use the control radius and shared panels use the panel radius. Status badges remain fully rounded. Contact cards retain their observed (10px) corners; compact role actions use (6px). These local variants do not replace the shared radii. Use a single-pixel border by default; semantic marks remain where the domain component requires them.

## Components

- **Buttons:** compact, filled primary or bordered secondary, with shared control typography and a (38px) minimum desktop height; the phone default is (42px). Hover changes border or fill without a lift. Focus uses an accent outline (2px) with a (3px) offset. Disabled buttons retain their existing muted state. Destructive actions use the danger family.
- **Inputs:** surface fill, strong border, control corners, and (15px/1.4) text. Hover emphasizes the border; keyboard focus uses a (2px) accent outline at zero offset plus the existing soft glow. Enhanced selects retain their native form behavior and matching visual treatment.
- **Navigation:** normal-case labels with inline SVG icons, a soft blue active fill, and stronger active weight. Mobile Menu exposes its expanded state; Escape closes it and restores focus. Settings uses a separate disclosure on smaller screens.
- **Status chips:** compact uppercase labels with rounded ends, semantic text/surface/border pairings, and visible state wording. Filter selections instead use the control shape and soft accent fill.
- **Panels and cards:** surface fill, fine border, no default shadow. Padding belongs to the content component. Hoverable record cards emphasize borders. Use raised surfaces for overlays rather than lifting the page content.
- **Record actions:** role and contact actions remain visible. Role actions expand to a (44px) minimum height on phones; contact actions expand to (40px). Do not hide facts behind an action overlay.

## Do's and Don'ts

### Do:

- Do use the current CSS variables so explicit and system-selected dark themes stay paired.
- Do keep role and contact actions visible without hover, with the existing larger mobile targets.
- Do preserve keyboard focus, native controls, disclosure state, and reduced-motion behavior.
- Do use the shared panel and button primitives before adding route-specific styling.

### Don't:

- Don't reintroduce the historical masthead rule, serif workspace titles, or page-header eyebrows.
- Don't replace state labels with color alone or restyle unknown facts as confirmed outcomes.
- Don't copy old palette values or hover lifts from historical documentation into new screens.
