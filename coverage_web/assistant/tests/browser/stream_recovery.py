"""Real composer checks with intercepted SSE; never sends a model request.

Run with --storage-state /path/to/local-test-user.json and optional --base-url.
The supplied account is read only: stream POSTs are fulfilled in the browser.
"""
import argparse
import json

from playwright.sync_api import sync_playwright

parser = argparse.ArgumentParser()
parser.add_argument("--storage-state", required=True)
parser.add_argument("--base-url", default="http://127.0.0.1:8000")
args = parser.parse_args()

CASES = {
    "partial": 'data: {"type":"delta","text":"Partial answer"}\n\n',
    "empty": "",
    "done": ('data: {"type":"delta","text":"Complete answer"}\n\n'
             'data: {"type":"done"}'),
}
results = []
with sync_playwright() as playwright:
    for engine in ("chromium", "webkit"):
        browser = getattr(playwright, engine).launch()
        for kind, body in CASES.items():
            context = browser.new_context(storage_state=args.storage_state)
            page = context.new_page()
            page.route("**/assistant/stream/", lambda route: route.fulfill(
                status=200, content_type="text/event-stream", body=body,
            ))
            page.goto(args.base_url.rstrip("/") + "/assistant/")
            page.locator("#as-input").fill("Browser readiness check")
            page.locator("#as-input").press("Enter")
            # Readiness follows UI settlement rather than arbitrary provider timing.
            if kind == "done":
                page.locator(".as-body").filter(has_text="Complete answer").wait_for()
            else:
                page.get_by_role("alert").filter(has_text="saved status").wait_for()
            page.wait_for_function(
                "!document.querySelector('#as-input').disabled"
            )
            alert = page.get_by_role("alert").filter(has_text="saved status")
            assert alert.count() == (0 if kind == "done" else 1), (engine, kind)
            assert page.locator(".is-thinking").count() == 0
            if kind == "partial":
                assert page.get_by_text("Partial answer", exact=True).is_visible()
            results.append({"engine": engine, "case": kind, "passed": True})
            context.close()
        browser.close()
print(json.dumps(results, indent=2))
