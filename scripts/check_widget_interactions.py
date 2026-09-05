"""Read-only browser checks against a signed-in demo session.

Run: uv run python scripts/check_widget_interactions.py --storage-state /path/to/session.json
Create the Playwright storage state using a demo account. POSTs are intercepted;
no server data is changed. Real save/stage/remove flows are checked separately.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage-state", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--report")
    args = parser.parse_args()
    checks, errors = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(storage_state=args.storage_state, viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        # Never send a POST from this read-only check, including automatic requests.
        page.route("**/*", lambda route: route.fulfill(status=204, body="") if route.request.method == "POST" else route.continue_())
        page.goto(args.base_url + "/opportunities/mine/", wait_until="networkidle")
        total = page.locator("[data-app-stage]").count()
        assert total > 0, "This check requires a populated demo pipeline"
        for button in page.locator(".apps-funnel [data-stage-filter]").all():
            button.click()
            expected = int(button.locator(".apps-fseg-n").inner_text())
            expect(page.locator("[data-app-stage]:visible")).to_have_count(expected)
            expect(button).to_have_attribute("aria-pressed", "true")
            assert page.locator('.apps-funnel [aria-pressed="true"]').count() == 1
        page.locator('.apps-funnel [data-stage-filter="all"]').click()
        expect(page.locator("[data-app-stage]:visible")).to_have_count(total)
        checks.append("Each stage count filters exactly its rows; All roles restores every row")

        # Isolated DOM fixture for a zero-result stage, without touching server records.
        page.locator('[data-app-stage="offer"]').evaluate_all("rows => rows.forEach(row => row.remove())")
        page.locator('.apps-funnel [data-stage-filter="offer"]').click()
        expect(page.locator("[data-apps-filter-empty]")).to_be_visible()
        expect(page.locator("[data-apps-filter-status]")).to_contain_text("Showing 0")
        page.locator('[data-apps-filter-empty] button').click()
        expect(page.locator("[data-apps-filter-empty]")).not_to_be_visible()
        checks.append("Zero-result fixture announces an empty state and offers a working reset")

        for width in (1440, 390):
            page.set_viewport_size({"width": width, "height": 1000 if width > 640 else 844})
            page.goto(args.base_url + "/opportunities/", wait_until="networkidle")
            expand = page.locator("[data-widget-expand]").first
            panel = expand.locator("xpath=ancestor::article[1]")
            before = panel.bounding_box()["height"]
            expand.focus()
            page.keyboard.press("Enter")
            expect(expand).to_have_attribute("aria-expanded", "true")
            assert panel.bounding_box()["height"] > before
            scroll = panel.locator(".firmcol-scroll")
            assert scroll.evaluate("e => e.scrollHeight <= e.clientHeight + 1")
            page.keyboard.press("Enter")
            expect(expand).to_have_attribute("aria-expanded", "false")
            assert abs(panel.bounding_box()["height"] - before) < 2
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        checks.append("Firm panels expand and collapse with Enter on desktop and phone")

        page.emulate_media(reduced_motion="reduce")
        page.wait_for_timeout(300)  # Let an already-running prior interaction finish.
        page.locator("[data-widget-expand]").first.click()
        animations = page.evaluate("document.getAnimations().filter(a => a.effect.getTiming().duration > 1).map(a => ({name:a.animationName, frames:a.effect.getKeyframes()}))")
        assert animations == [], animations
        checks.append("Reduced-motion expansion keeps its state without animation")

        button = page.locator('.firmcol:not(.firmcol--picked) .track-btn:not(.is-saved)').first
        endpoint = args.base_url + button.get_attribute("hx-post")
        row = button.locator("xpath=ancestor::div[contains(@class, 'rolerow')][1]")
        if not row.count():
            row = button.locator("xpath=ancestor::*[contains(concat(' ',normalize-space(@class),' '), ' rolerow ')][1]")
        initial = row.inner_text()
        busy = []

        def reject(route):
            busy.append(row.get_attribute("aria-busy") == "true")
            assert row.evaluate("e => getComputedStyle(e, '::after').animationName") == "none"
            route.fulfill(status=503, content_type="text/plain", body="Simulated unavailable response")

        page.route(endpoint, reject)
        button.click()
        expect(row).to_have_class(re.compile("widget-request-error"))
        assert busy == [True]
        assert row.get_attribute("aria-busy") is None
        assert row.inner_text() == initial
        expect(page.locator("#hx-toast")).to_contain_text("didn't go through")
        checks.append("An intercepted failed save clears busy state, preserves content, and reports failure")
        assert not errors, errors
        browser.close()
    result = {"passed": checks, "javascript_errors": errors}
    if args.report:
        Path(args.report).write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
