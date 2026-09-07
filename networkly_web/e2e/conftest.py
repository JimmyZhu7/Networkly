"""Playwright against a real server, on the test database only.

`live_server` is pytest-django's own fixture: it boots Django in a thread bound
to the SAME test database the rest of the suite uses, and tears it down after.
Nothing here can reach the development database, and no fixture in this package
reads a `DATABASE_URL` of its own.

Two engines, because the deployment target is a browser and not a test client:
Chromium, and WebKit as the closest freely-installable stand-in for Safari,
which the readiness checklist names by hand. Two viewports, because a phone is
where a student will actually open this.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

# Screenshots go to the system temp directory unless JOURNEY_SHOTS says
# otherwise. This used to default to one developer's session scratchpad, an
# absolute path that exists on exactly one machine; on CI the mkdir in
# pytest_configure raised and took the entire collection down with it (exit 2,
# zero tests run). A default must be creatable anywhere, and creating it must
# never be able to fail collection.
SHOTS = Path(os.environ.get("JOURNEY_SHOTS", str(Path(tempfile.gettempdir()) / "networkly-journeys")))

# Name, width, height. 375x812 is the iPhone X class, which is the narrowest
# screen the checklist asks about; 1280x900 is an ordinary laptop.
VIEWPORTS = [("desktop", 1280, 900), ("narrow", 375, 812)]
ENGINES = ["chromium", "webkit"]

# Console noise that is not the application's fault and would otherwise make
# every page "fail" the no-errors assertion. Kept deliberately short: anything
# not on this list is a real error the page emitted.
IGNORED_CONSOLE = (
    "favicon",
    "manifest",
    "net::ERR_ABORTED",
    "Failed to load resource: the server responded with a status of 404",
)


def pytest_configure(config):
    try:
        SHOTS.mkdir(parents=True, exist_ok=True)
    except OSError:
        # An unwritable location must not stop the suite; the screenshot
        # helper creates the directory again lazily and reports if it cannot.
        pass


@pytest.fixture(scope="session")
def playwright_instance(django_db_setup):
    """Started AFTER the test database exists, and owning the async-unsafe flag.

    TWO ORDERING FACTS, both learned the hard way.

    Creating the test database opens a connection with no database selected,
    which Django guards as async-unsafe. Playwright's sync API leaves a running
    asyncio loop on this thread, so if it starts first that guard trips and the
    database is never created at all. Depending on `django_db_setup` puts the
    loop after the last thing that has to run without one.

    And `DJANGO_ALLOW_ASYNC_UNSAFE` is set HERE rather than per test, because
    per-test teardown is too narrow a window: pytest-django truncates tables
    after each transactional test, and that truncation is an ORM call made
    while the loop is still running. Setting the flag for exactly the lifetime
    of the loop covers setup, the test, and teardown, and restores whatever was
    there before as soon as the browser process is gone. Nothing outside a
    browser test is affected: without a running loop the guard never fires, so
    the flag has nothing to relax.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:  # pragma: no cover - depends on the environment
        pytest.skip("playwright is not installed; the browser matrix needs it")

    key = "DJANGO_ALLOW_ASYNC_UNSAFE"
    previous = os.environ.get(key)
    os.environ[key] = "true"
    try:
        with sync_playwright() as playwright:
            yield playwright
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous


@pytest.fixture(params=ENGINES)
def engine(request):
    return request.param


@pytest.fixture(params=VIEWPORTS, ids=[name for name, _, _ in VIEWPORTS])
def viewport(request):
    name, width, height = request.param
    return {"name": name, "width": width, "height": height}


@pytest.fixture
def browser(playwright_instance, engine):
    launcher = getattr(playwright_instance, engine)
    try:
        browser = launcher.launch(headless=True)
    except Exception as exc:  # Playwright raises its own Error when the binary is absent
        if "Executable doesn't exist" in str(exc) or "playwright install" in str(exc):
            pytest.skip(f"{engine} is not installed; run `playwright install --with-deps {engine}`")
        raise
    yield browser
    browser.close()


class Session:
    """One page, with everything the console said while it was open."""

    def __init__(self, page, errors, engine, viewport):
        self.page = page
        self.errors = errors
        self.engine = engine
        self.viewport = viewport

    def label(self, name):
        return f"{name}-{self.engine}-{self.viewport['name']}"

    def shoot(self, name):
        path = SHOTS / f"{self.label(name)}.png"
        self.page.screenshot(path=str(path), full_page=True)
        return path

    def horizontal_overflow(self):
        """How many pixels the document scrolls sideways. Must be zero.

        `documentElement.scrollWidth` against the viewport width is the
        measurement a reader would make by trying to swipe the page sideways,
        which is the actual complaint a narrow-screen overflow produces.
        """
        return self.page.evaluate(
            "() => Math.max(0, document.documentElement.scrollWidth - window.innerWidth)"
        )

    def real_console_errors(self):
        return [
            message for message in self.errors
            if not any(noise in message for noise in IGNORED_CONSOLE)
        ]


@pytest.fixture
def session(browser, engine, viewport):
    context = browser.new_context(
        viewport={"width": viewport["width"], "height": viewport["height"]},
        # Restrained motion is the house style, and a reveal animation frozen
        # on its 0% keyframe is indistinguishable from a missing element in a
        # screenshot. This removes that whole class of false negative.
        reduced_motion="reduce",
    )
    page = context.new_page()
    errors: list[str] = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    yield Session(page, errors, engine, viewport)
    context.close()
