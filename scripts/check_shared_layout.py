#!/usr/bin/env python3
"""Read-only browser regression check for shared responsive UI.

Run with the app available locally and Playwright's Chromium and WebKit installed.
Uses the demo account by default; credentials can be supplied through the
NETWORKLY_TEST_EMAIL and NETWORKLY_TEST_PASSWORD environment variables.
Long-content search results are browser fixtures, never database records.
"""

from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import argparse
import json
import os

parser = argparse.ArgumentParser(
    description="Check shared Networkly chrome, search wrapping, and dialogs in Chromium and WebKit."
)
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
parser.add_argument("--output", default=".impeccable/review/repair")
parser.add_argument(
    "--email", default=os.environ.get("NETWORKLY_TEST_EMAIL", "demo@coverage.local")
)
parser.add_argument(
    "--password", default=os.environ.get("NETWORKLY_TEST_PASSWORD", "demo1234")
)
parser.add_argument(
    "--only-menus",
    action="store_true",
    help="Run the pointer-to-keyboard dropdown and drawer regressions only",
)
args = parser.parse_args()
OUT = Path(args.output)
OUT.mkdir(exist_ok=True, parents=True)
B = args.base_url.rstrip("/")
checks = []
with sync_playwright() as p:
    for engine in ("chromium", "webkit"):
        browser = getattr(p, engine).launch()
        ctx = browser.new_context(
            reduced_motion="reduce", viewport={"width": 693, "height": 837}
        )
        page = ctx.new_page()
        page.goto(B + "/accounts/login/")
        page.locator("[name=login]").fill(args.email)
        page.locator("[name=password]").fill(args.password)
        page.get_by_role("button", name="Sign in", exact=True).click()
        page.wait_for_url("**/app/")
        # Block mutations after sign-in; fixtures below exist only in this browser.
        page.route(
            "**/*",
            lambda r: (
                r.fulfill(status=204, body="")
                if r.request.method == "POST"
                else r.continue_()
            ),
        )
        page.route(
            "**/search/**",
            lambda r: r.fulfill(
                json={
                    "contacts": [
                        {
                            "name": "Alexandra Catherine Montgomery-Wellington",
                            "firm": "International Investment Management and Capital Advisory Partners",
                            "warmth": "Had a conversation",
                            "url": "/app/contacts/",
                        }
                    ],
                    "firms": [],
                    "roles": [
                        {
                            "title": "2027 Global Investment Banking Summer Analyst Development Programme – Hong Kong and Singapore",
                            "firm": "International Investment Management and Capital Advisory Partners",
                            "url": "/opportunities/",
                            "external": False,
                        }
                    ],
                }
            ),
        )
        for width, height in [
            (320, 568),
            (390, 844),
            (600, 800),
            (693, 837),
            (820, 900),
            (1050, 900),
            (1051, 900),
            (1100, 900),
            (1440, 960),
            (693, 390),
        ]:
            if args.only_menus:
                break
            page.set_viewport_size({"width": width, "height": height})
            page.goto(B + "/app/", wait_until="networkidle")
            page.evaluate("document.fonts.ready")
            for theme in ("light", "dark"):
                page.evaluate(
                    '(t)=>document.documentElement.setAttribute("data-theme",t)', theme
                )
                page.wait_for_timeout(250)
                # Shared header: every visible action fits, including immediately above collapse threshold.
                header = page.locator(".site-header")
                hs = header.evaluate(
                    'el=>{const box=el.getBoundingClientRect();return [...el.querySelectorAll("a,button")].filter(x=>x.getClientRects().length).filter(x=>{const r=x.getBoundingClientRect();return r.left<box.left-1||r.right>box.right+1}).map(x=>x.textContent.trim()||x.ariaLabel)}'
                )
                checks.append(
                    {
                        "engine": engine,
                        "width": width,
                        "height": height,
                        "theme": theme,
                        "state": "header",
                        "overflow": hs,
                    }
                )
                if width <= 1050:
                    page.locator("[data-workspace-menu]").click()
                    expect(page.locator("#workspace-primary")).to_be_visible()
                    page.get_by_role(
                        "link", name="Settings", exact=True
                    ).scroll_into_view_if_needed()
                    mb = page.locator(".site-header").bounding_box()
                    checks.append(
                        {
                            "engine": engine,
                            "width": width,
                            "height": height,
                            "theme": theme,
                            "state": "navigation",
                            "height": mb["height"],
                            "viewport_height": height,
                        }
                    )
                    page.keyboard.press("Escape")
                page.locator("[data-open-search]").click()
                page.locator("#cmdk-q").fill("Alexandra")
                expect(page.locator("#cmdk-results")).to_contain_text("Montgomery")
                geometry = page.locator("#cmdk").evaluate(
                    'el=>{const box=el.getBoundingClientRect();return {left:box.left,right:box.right,bottom:box.bottom,scrollHeight:el.scrollHeight,clientHeight:el.clientHeight,spilled:[...el.querySelectorAll("input,button,.palette-item b,.palette-item span")].filter(x=>{let r=x.getBoundingClientRect();return r.left<box.left-1||r.right>box.right+1||x.scrollWidth>x.clientWidth+1}).map(x=>x.className||x.tagName)}}'
                )
                checks.append(
                    {
                        "engine": engine,
                        "width": width,
                        "height": height,
                        "theme": theme,
                        "state": "search",
                        **geometry,
                    }
                )
                expect(page.locator("#cmdk-q")).to_have_attribute(
                    "aria-activedescendant", "cmdk-option-0"
                )
                page.keyboard.press("ArrowDown")
                expect(page.locator("#cmdk-q")).to_have_attribute(
                    "aria-activedescendant", "cmdk-option-1"
                )
                if width in (320, 693, 1051) and height > 500:
                    page.screenshot(
                        path=str(OUT / f"search-{engine}-{theme}-{width}.png")
                    )
                page.get_by_role("button", name="Close search", exact=True).click()
                expect(page.locator("#cmdk")).not_to_be_visible()
                page.evaluate(
                    "() => { window.confirmResult=null; window.covConfirm('Remove Alexandra Catherine Montgomery-Wellington from this list?', {ok:'Remove contact'}).then(v=>window.confirmResult=v); }"
                )
                dialog = page.locator("#cov-confirm")
                expect(dialog).to_be_visible()
                cb = dialog.bounding_box()
                checks.append(
                    {
                        "engine": engine,
                        "width": width,
                        "height": height,
                        "theme": theme,
                        "state": "confirmation",
                        "left": cb["x"],
                        "right": cb["x"] + cb["width"],
                        "bottom": cb["y"] + cb["height"],
                    }
                )
                page.get_by_role("button", name="Cancel", exact=True).click()
                expect(dialog).not_to_be_visible()
                page.wait_for_function("() => window.confirmResult === false")
        for width in (320, 693, 1051):
            page.set_viewport_size({"width": width, "height": 900})
            page.goto(B + "/opportunities/", wait_until="networkidle")
            filters = page.locator("[data-filters-more]")
            if filters.get_attribute("open") is None:
                page.locator("[data-filters-toggle]").click()
            for theme in ("light", "dark"):
                page.evaluate(
                    "t => document.documentElement.setAttribute('data-theme',t)", theme
                )
                page.wait_for_timeout(300)
                region = page.locator("#f-region").locator("..").locator(".csel-btn")
                firms = page.locator(".cmulti-btn")
                for trigger in (region, firms):
                    trigger.click()
                    expect(trigger).to_have_attribute("aria-expanded", "true")
                    expect(trigger).to_be_focused()
                    page.keyboard.press("Escape")
                    expect(trigger).to_have_attribute("aria-expanded", "false")
                    expect(trigger).to_be_focused()
                checks.append(
                    {
                        "engine": engine,
                        "width": width,
                        "height": 900,
                        "theme": theme,
                        "state": "pointer-keyboard menus",
                    }
                )
                page.locator("[data-role-read]:visible").first.click()
                action = page.locator(".directory-drawer .drawer-apply:not(.is-closed)")
                expect(action).to_be_visible()
                action.hover()
                page.wait_for_timeout(300)
                colors = action.evaluate(
                    "el => {const probe=document.createElement('span');probe.style.color='var(--on-accent)';el.appendChild(probe);const expected=getComputedStyle(probe).color;probe.remove();return {actual:getComputedStyle(el).color,expected};}"
                )
                assert colors["actual"] == colors["expected"], colors
                checks.append(
                    {
                        "engine": engine,
                        "width": width,
                        "height": 900,
                        "theme": theme,
                        "state": "drawer hover contrast",
                    }
                )
                page.keyboard.press("Escape")
        browser.close()
OUT.joinpath(
    "menu-checks.json" if args.only_menus else "shared-checks.json"
).write_text(json.dumps(checks, indent=2))
failures = [
    x
    for x in checks
    if x.get("overflow")
    or x.get("spilled")
    or x.get("left", 0) < -1
    or x.get("right", 0) > x["width"] + 1
    or x.get("bottom", 0) > x["height"] + 1
    or (x["state"] == "navigation" and x["height"] > x["viewport_height"])
]
print(json.dumps({"checks": len(checks), "failures": failures}, indent=2))
raise SystemExit(bool(failures))
