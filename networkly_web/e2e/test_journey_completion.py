"""Real browser submissions complement the HTTP journey regression suites."""
import pytest
from django.utils import timezone
from crm.models import Contact, CalendarEvent
from .test_journey_browser_matrix import world, _adopt_session, _open, _check

pytestmark = pytest.mark.django_db(transaction=True)


def test_contact_creation_and_duplicate_csv_import(session, live_server, world):
    page = session.page
    _adopt_session(session, live_server, world['student'])
    _open(session, live_server, '/app/contacts/new/')
    page.fill('[name=name]', 'Browser Added')
    page.fill('[name=email]', 'added@example.test')
    page.select_option('select[name=firm]', str(world['firm'].pk))
    page.get_by_role('button', name='Add contact', exact=True).click()
    page.wait_for_load_state('networkidle')
    assert Contact.objects.for_user(world['student']).filter(name='Browser Added').exists()
    _check(session, 'contact-created')
    _open(session, live_server, '/welcome/import/')
    page.set_input_files('[name=file]', {
        'name': 'contacts.csv', 'mimeType': 'text/csv',
        'buffer': b'name,email,firm\nBrowser Added,added@example.test,Journey Partners\nImported Person,imported@example.test,Journey Partners\n',
    })
    page.get_by_role('button', name='Import contacts', exact=True).click()
    page.wait_for_load_state('networkidle')
    assert Contact.objects.for_user(world['student']).filter(email='added@example.test').count() == 1
    assert Contact.objects.for_user(world['student']).filter(name='Imported Person').exists()
    assert 'Import Summary' in page.content()
    _check(session, 'csv-import-summary')


def test_calendar_event_submission(session, live_server, world):
    page = session.page
    _adopt_session(session, live_server, world['student'])
    _open(session, live_server, '/app/calendar/')
    page.locator('.cal-add > summary').click()
    page.fill('[name=title]', 'Browser Coffee Chat')
    page.fill('[name=day]', timezone.localdate().isoformat())
    page.fill('[name=at]', '14:30')
    page.get_by_role('button', name='Add to calendar', exact=True).click()
    page.wait_for_load_state('networkidle')
    assert CalendarEvent.objects.for_user(world['student']).filter(title='Browser Coffee Chat').exists()
    assert 'Browser Coffee Chat' in page.content()
    _check(session, 'calendar-event-created')


def test_fresh_account_can_finish_setup_and_reach_today(session, live_server, world):
    student = world['student']
    student.onboarded_at = None
    student.name = ''
    student.save(update_fields=['onboarded_at', 'name'])
    _adopt_session(session, live_server, student)
    _open(session, live_server, '/welcome/')
    page = session.page
    page.fill('[name=name]', 'New Browser Student')
    for step in ('profile', 'work_auth', 'firms'):
        assert page.locator(f'input[name=step][value={step}]').count() == 1
        page.get_by_role('button', name='Continue', exact=True).click()
        page.wait_for_load_state('networkidle')
        _check(session, f'onboarding-after-{step}')
    page.get_by_role('button', name='Finish setup', exact=True).click()
    page.wait_for_load_state('networkidle')
    assert page.url.endswith('/app/')
    student.refresh_from_db()
    assert student.onboarded_at is not None
    assert student.name == 'New Browser Student'
    _check(session, 'onboarding-complete')


def test_application_stage_changes_persist_from_browser(session, live_server, world):
    from analytics.models import UserOpportunity
    from playwright.sync_api import expect
    student, role = world['student'], world['role']
    tracked = UserOpportunity.objects.for_user(student).create(user=student, opportunity=role)
    _adopt_session(session, live_server, student)
    _open(session, live_server, '/opportunities/mine/')
    page = session.page
    for stage in ('submitted', 'interview', 'offer'):
        with page.expect_response(lambda response: response.request.method == 'POST' and f'/opportunities/{role.pk}/track/' in response.url) as saved:
            page.locator('select[data-stage-select]').select_option(stage)
        assert saved.value.status == 200
        page.wait_for_function("!document.querySelector('.htmx-request')")
        page.wait_for_load_state('networkidle')
        expect(page.locator('select[data-stage-select]')).to_have_value(stage)
        # Revisit guarantees this is server-persisted rather than a local select value.
        _open(session, live_server, '/opportunities/mine/')
        tracked.refresh_from_db()
        assert tracked.applied_status == stage
        expect(page.locator('select[data-stage-select]')).to_have_value(stage)
    _check(session, 'application-offer')
