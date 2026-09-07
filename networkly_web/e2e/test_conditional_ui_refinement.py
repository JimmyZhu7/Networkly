"""Conditional UI states on isolated accounts; model requests are intercepted."""
import pytest
from playwright.sync_api import expect
from .test_journey_browser_matrix import world, _adopt_session, _open, _check

pytestmark = pytest.mark.django_db(transaction=True)


def test_import_invalid_and_unmatched_firm_states(session, live_server, world):
    page = session.page
    _adopt_session(session, live_server, world['student'])
    _open(session, live_server, '/welcome/import/?from=welcome')
    page.set_input_files('[name=file]', {'name': 'invalid.csv', 'mimeType': 'text/csv', 'buffer': b'irrelevant,columns\na,b\n'})
    page.get_by_role('button', name='Import contacts', exact=True).click()
    expect(page.get_by_role('alert')).to_be_visible()
    expect(page.get_by_role('link', name='Continue setup')).to_have_attribute('href', '/welcome/?step=import')
    _check(session, 'import-invalid')
    firm = 'Unmatched Independent Advisory Partnership With A Long Name'
    page.set_input_files('[name=file]', {'name': 'contacts.csv', 'mimeType': 'text/csv', 'buffer': f'name,email,firm\nNew Import,new@example.test,{firm}\n'.encode()})
    page.get_by_role('button', name='Import contacts', exact=True).click()
    expect(page.get_by_role('status')).to_be_visible()
    expect(page.get_by_role('combobox', name=firm, exact=True)).to_be_visible()
    _check(session, 'import-unmatched-long-firm')


def test_assistant_empty_and_interrupted_stream(session, live_server, world, monkeypatch):
    monkeypatch.setattr("assistant.views.is_configured", lambda: True)
    page = session.page
    _adopt_session(session, live_server, world['student'])
    _open(session, live_server, '/assistant/')
    expect(page.get_by_role('region', name='Ways to start')).to_have_attribute('tabindex', '0')
    expect(page.get_by_role('heading', name='What Would You Like to Work On?')).to_be_visible()
    _check(session, 'assistant-empty')
    page.route('**/assistant/stream/', lambda route: route.fulfill(status=200, content_type='text/event-stream', body='data: {"type":"delta","text":"Partial answer"}\n\n'))
    page.locator('#as-input').fill('Help plan my week')
    page.locator('#as-input').press('Enter')
    expect(page.get_by_role('alert').filter(has_text='saved status')).to_be_visible()
    expect(page.get_by_text('Partial answer', exact=True)).to_be_visible()
    expect(page.get_by_role('region', name='Conversation')).to_have_attribute('tabindex', '0')
    expect(page.locator('#as-input')).to_be_enabled()
    assert page.locator('.is-thinking').count() == 0
    _check(session, 'assistant-stream-interrupted')
