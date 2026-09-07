"""Settings editors remain reachable from summaries, anchors and errors."""
import pytest
from django.test import Client
from playwright.sync_api import expect
from .test_journey_browser_matrix import world, _adopt_session, _open, _check

pytestmark = pytest.mark.django_db(transaction=True)


def test_settings_summary_keyboard_and_deep_links(session, live_server, world):
    _adopt_session(session, live_server, world['student'])
    _open(session, live_server, '/welcome/settings/')
    page = session.page
    expect(page.locator('.settings-nav')).to_have_count(0)
    expect(page.locator('#profile-editor')).to_be_hidden()
    toggle = page.locator('#profile .set-disclosure-toggle')
    toggle.focus()
    page.keyboard.press('Enter')
    expect(page.locator('#profile-editor')).to_be_visible()
    expect(toggle).to_have_attribute('aria-label', 'Close Profile')
    page.keyboard.press('Enter')
    expect(page.locator('#profile-editor')).to_be_hidden()
    page.evaluate("location.hash='cadence'")
    expect(page.locator('#cadence-editor')).to_be_visible()
    _check(session, 'settings-summary-links')


def test_invalid_profile_response_reveals_editor(session, live_server, world):
    client = Client()
    client.force_login(world['student'])
    response = client.post('/welcome/settings/', {'section':'profile', 'class_year':'invalid'})
    assert response.status_code == 200
    assert b'errorlist' in response.content
    _adopt_session(session, live_server, world['student'])
    page = session.page
    page.route('**/welcome/settings/', lambda route: route.fulfill(status=200, content_type='text/html', body=response.content.decode()))
    _open(session, live_server, '/welcome/settings/')
    expect(page.locator('#profile-editor')).to_be_visible()
    expect(page.locator('#profile .set-disclosure-toggle')).to_have_attribute('aria-expanded', 'true')
    _check(session, 'settings-validation-visible')
