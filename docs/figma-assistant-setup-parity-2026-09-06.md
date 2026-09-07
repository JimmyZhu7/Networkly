# Assistant and Setup Figma Parity — 6 September 2026

Read live Figma design context and screenshots for Assistant `29:75`, Account Setup `29:339`, and Assistant conditional states `32:65` in file `EOQxIPSHLHpL198bB2tOSU`.

## Implemented intent and deliberate adaptations

- Assistant has the reference's history/sidebar, direct Saved Context entry, four starter prompts, conversation area and composer. The actual full-height shell keeps conversation scrolling independently and retains attachments, dictation, credits, folders and history. Prompt cards replace the reference's repetitive Start rows, and the actual wordmark/navigation retains product branding and icons. This is an adaptation, not a pixel-identical reproduction.
- The Assistant state board's interruption concept is implemented with an alert that preserves partial output and asks the user to reload and check the saved status. A blind Retry button was intentionally not added: a server may have completed the same turn after the connection broke, so resending could duplicate work. Loading/stream indicators use the existing conversation surface rather than separate demonstration cards.
- Setup retains the established four real stages (profile, work authorization, firms, import), optional fields, progress indicators, and data-driven recruiting preview. The Figma Profile/Preferences/Target Firms/Connect sidebar is a schematic alternative, not the current route model. Replacing the working wizard with those labels would misrepresent its actual stages.

## Fixes

- Removed duplicate import notifications. The shared shell already renders the same success/error feedback with status/alert semantics; the page previously repeated it.
- Named each unmatched-firm dropdown with its displayed firm name, so multiple matching controls can be distinguished using assistive technology.

## Browser evidence

`coverage_web/e2e/test_conditional_ui_refinement.py`: **8 passed** on Chromium and WebKit at 1280×900 and 375×812, using a uniquely named isolated test database. Cases exercise invalid CSV error feedback, the onboarding return link, successful import with a long unmatched firm name and accessible selector, Assistant empty state, and interrupted partial streaming with restored composer access. Model requests are intercepted; this does not establish real model delivery. Checks include horizontal overflow and recorded console/page errors under the existing browser suite's documented exclusions.

The existing fresh-account setup browser journey was also rerun against the current templates: **4 passed** (both engines and viewports), submitting all four stages and reaching Today with persisted completion. One existing Django deprecation warning remains.

Screenshots saved under the system temporary directory's `networkly-journeys` folder; desktop Assistant and narrow WebKit unmatched-firm screenshots were visually inspected. The shared shell's dismissible notification overlays the lower mobile viewport temporarily; no duplicate page notification remains.

This pass does not claim complete screen-reader certification, real OAuth/provider delivery, every attachment/dictation/memory outcome, or production deployment.
