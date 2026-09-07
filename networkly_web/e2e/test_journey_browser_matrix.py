"""Journey 10: the highest-value flows, in two engines at two widths.

Sign in, Today, save a role on Opportunities, and Settings — each rendered by a
real browser against a real server on the test database, at a laptop width and
at 375x812.

Three assertions on every page, and they are the ones a student would make:
the page does not scroll sideways, the control they came for can actually be
clicked, and the console is quiet.

WebKit stands in for Safari. It is the same engine Safari ships and it is what
`playwright install webkit` provides; it is not Safari itself, so a
Safari-specific chrome bug (its own toolbars, its own PDF viewer) is out of
scope here and stays a manual check.

Screenshots land outside the repository, under the path `conftest.SHOTS` names.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.utils import timezone

from accounts.models import User
from analytics.models import UserOpportunity
from crm.models import Contact, Touch, UserFirm
from directory.models import Firm, Opportunity

# `live_server` runs in its own thread against a committed database, so these
# have to be transactional.
pytestmark = pytest.mark.django_db(transaction=True)

PASSWORD = "A-safe-passphrase-123"


@pytest.fixture
def world():
    """One student with enough on their account for every page to have content."""
    student = User.objects.create_user(
        email="browser@example.com", password=PASSWORD, name="Browser Student",
        regions=["us"], tracks=["ib"], class_year=2028,
        onboarded_at=timezone.now(), timezone="America/Los_Angeles",
        timezone_auto=False,
    )
    firm = Firm.objects.create(name="Journey Partners", slug="journey-partners",
                               regions=["us"], tracks=["ib"])
    UserFirm.all_objects.create(user=student, firm=firm, tier=1)
    contact = Contact.all_objects.create(
        user=student, name="Dana Banker", firm=firm, role="Analyst",
        email="dana@journeypartners.test", region="us", source="manual",
    )
    Touch.all_objects.create(user=student, contact=contact, kind="outreach",
                             channel="email", ts=timezone.now() - dt.timedelta(days=21))
    role = Opportunity.objects.create(
        firm=firm, title="2028 Summer Analyst, Investment Banking",
        url="https://example.test/journey", region="us", bucket="internship",
        status="open", deadline=timezone.localdate() + dt.timedelta(days=21),
    )
    return {"student": student, "firm": firm, "contact": contact, "role": role}


def _adopt_session(session, live_server, user):
    """Sign in without replaying Google's OAuth in a browser.

    The beta's only front door is Google, and driving a real consent screen
    would mean a network call to a provider — which this workstream does not
    make. So the session is minted server-side (Django's own SessionStore, the
    same rows `client.force_login` writes) and handed to the browser as its
    cookie. Everything AFTER the cookie is genuinely the browser's: the
    middleware, the templates, the CSS, htmx.

    `test_journey_admission.py` covers the sign-in chain itself end to end.
    """
    from django.conf import settings

    store = SessionStore()
    store["_auth_user_id"] = str(user.pk)
    store["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
    store["_auth_user_hash"] = user.get_session_auth_hash()
    store.create()
    session.page.context.add_cookies([{
        "name": settings.SESSION_COOKIE_NAME,
        "value": store.session_key,
        "url": live_server.url,
    }])


def _open(session, live_server, path):
    session.page.goto(f"{live_server.url}{path}")
    session.page.wait_for_load_state("networkidle")


def _check(session, name):
    """The three questions, asked the same way on every page."""
    overflow = session.horizontal_overflow()
    shot = session.shoot(name)
    errors = session.real_console_errors()
    assert overflow == 0, (
        f"{session.label(name)} scrolls {overflow}px sideways (screenshot: {shot})"
    )
    assert not errors, f"{session.label(name)} console errors: {errors}"
    return shot


# ---------------------------------------------------------------------------


def test_signing_in_with_a_password_works_in_a_real_browser(session, live_server, world):
    """The sign-in page itself, driven by hand.

    Google is the beta's front door and cannot be replayed here without a
    provider call, so this exercises the form that exists for accounts that
    already have a password — which is the other real path through this page,
    and the one that proves the form, the CSRF token and the redirect work in
    both engines.
    """
    page = session.page
    _open(session, live_server, "/accounts/login/")
    _check(session, "01-signin")

    page.fill("input[name='login']", "browser@example.com")
    page.fill("input[name='password']", PASSWORD)
    page.click("button[type='submit'], input[type='submit']")
    page.wait_for_load_state("networkidle")

    assert "/accounts/login" not in page.url, f"still on the sign-in page: {page.url}"
    assert not session.real_console_errors()
    session.shoot("02-signed-in")


def test_today_renders_its_queue_without_sideways_scroll(session, live_server, world):
    _adopt_session(session, live_server, world["student"])
    _open(session, live_server, "/app/")

    body = session.page.content()
    assert "Dana Banker" in body, "the queue card the fixture set up is not on the page"
    _check(session, "03-today")

    # The card's own controls are reachable, which at 375px is the real risk.
    buttons = session.page.locator("form button:visible, a.btn:visible")
    assert buttons.count() > 0
    assert buttons.first.is_enabled()


def test_saving_a_role_from_the_feed_works_in_a_real_browser(session, live_server, world):
    student, role = world["student"], world["role"]
    _adopt_session(session, live_server, student)
    _open(session, live_server, "/opportunities/")

    assert role.title in session.page.content()
    _check(session, "04-opportunities")

    # The Save control is an htmx button, not a form submit: `hx-post` is the
    # attribute that carries the URL, so that is what identifies it.
    save = session.page.locator(
        f"button[hx-post='/opportunities/{role.pk}/track/']:visible"
    ).first
    save.scroll_into_view_if_needed()
    assert save.is_enabled()
    box = save.bounding_box()
    assert box and box["width"] > 0 and box["height"] > 0, "the Save control has no box"
    save.click()
    session.page.wait_for_timeout(700)

    assert UserOpportunity.objects.for_user(student).filter(opportunity=role).exists(), (
        "clicking Save in the browser did not save the role"
    )
    assert not session.real_console_errors()
    session.shoot("05-opportunity-saved")


def test_settings_renders_every_card_at_both_widths(session, live_server, world):
    _adopt_session(session, live_server, world["student"])
    _open(session, live_server, "/welcome/settings/")

    body = session.page.content()
    assert "Browser Student" in body
    assert "Journey Partners" in body
    _check(session, "06-settings")

    # The profile save is the control this page exists for.
    save = session.page.locator("form button[type='submit']:visible").first
    save.scroll_into_view_if_needed()
    assert save.is_enabled()


def test_every_scrolling_region_can_be_reached_from_a_keyboard(session, live_server, world):
    """A region that scrolls and cannot take focus hides its own content.

    The assistant's empty state is the case that found this: at 375x812 its box
    is 250px over 419px of content, so three of the four starter prompts are
    below the fold with no way to reach them except a pointer. Asserted on
    every authenticated surface, not just that one, because any of them can
    grow a scrolling panel.
    """
    _adopt_session(session, live_server, world["student"])

    for path in ("/app/", "/assistant/", "/app/contacts/", "/opportunities/mine/"):
        _open(session, live_server, path)
        unreachable = session.page.evaluate("""() => {
          const focusable = 'a[href],button,input,select,textarea,[tabindex]';
          return [...document.querySelectorAll('*')].filter(el => {
            const style = getComputedStyle(el);
            const scrolls = /(auto|scroll)/.test(style.overflowY)
              && el.scrollHeight - el.clientHeight > 1;
            if (!scrolls) return false;
            if (el.tabIndex >= 0) return false;
            return !el.querySelector(focusable);
          }).map(el => el.className || el.tagName);
        }""")
        assert unreachable == [], (
            f"{path} at {session.viewport['name']}: scrolling regions with no "
            f"keyboard route in: {unreachable}"
        )


def test_no_page_needs_a_horizontal_swipe_on_a_phone(session, live_server, world):
    """Every authenticated surface, in one sweep, at whatever width is under
    test. This is the assertion the narrow viewport exists for."""
    _adopt_session(session, live_server, world["student"])

    for name, path in [
        ("07-today", "/app/"),
        ("08-opportunities", "/opportunities/"),
        ("09-applications", "/opportunities/mine/"),
        ("10-network", "/app/contacts/"),
        ("11-calendar", "/app/calendar/"),
        ("12-assistant", "/assistant/"),
        ("13-settings", "/welcome/settings/"),
        ("14-export", "/welcome/export/"),
    ]:
        _open(session, live_server, path)
        assert session.page.title(), f"{path} rendered with no title"
        _check(session, name)
