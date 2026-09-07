"""Offline expired-cursor recovery: absence is a lookup, never a tombstone.

The main task runs these DB-backed tests serially. Every provider request is
mocked; none of these tests needs credentials or access to Google.
"""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from django.db import transaction

from capture import gcal_live
from capture.models import GoogleCalendarConnection
from capture.tests.test_gcal_sync import _event, _fake_client, _http_error, _page, _sync
from crm.models import CalendarEvent

pytestmark = pytest.mark.django_db(transaction=True)
NOW = datetime(2026, 9, 6, 12, tzinfo=dt_timezone.utc)


@pytest.fixture
def connection(settings):
    settings.GCAL_SYNC_PAST_DAYS = 30
    settings.GCAL_SYNC_FUTURE_DAYS = 180
    user = get_user_model().objects.create_user(email="reconcile@example.test", password="x")
    return GoogleCalendarConnection.all_objects.create(
        user=user, google_email=user.email, refresh_token_encrypted="not-used",
        sync_token="expired", last_synced_at=NOW - timedelta(days=1),
        last_sync_stats={"previous": True},
    )


@pytest.fixture(autouse=True)
def fixed_clock():
    with patch.object(gcal_live.timezone, "now", return_value=NOW):
        yield


def _stored(connection, event_id="missing", **overrides):
    fields = dict(
        user=connection.user, external_id=event_id, title="Original meeting",
        starts_at=NOW + timedelta(days=2), ends_at=NOW + timedelta(days=2, hours=1),
        source=CalendarEvent.SOURCE_GCAL, description="Original notes",
    )
    fields.update(overrides)
    return CalendarEvent.all_objects.create(**fields)


def _client(connection, resources, *, items=(), initial=False):
    pages = [_page(list(items), next_sync_token="recovered")]
    if not initial:
        pages.insert(0, _http_error(410))
    client = _fake_client(pages)

    def get(**kwargs):
        assert kwargs["calendarId"] == (connection.calendar_id or "primary")
        resource = resources[kwargs["eventId"]]
        request = MagicMock()
        if isinstance(resource, Exception):
            request.execute.side_effect = resource
        else:
            request.execute.return_value = resource
        return request

    client.events.return_value.get.side_effect = get
    client.calendars.return_value.get.return_value.execute.return_value = {"id": connection.google_email}
    return client


def _assert_checkpoint_unchanged(connection):
    connection.refresh_from_db()
    assert connection.sync_token == "expired"
    assert connection.last_synced_at == NOW - timedelta(days=1)
    assert connection.last_sync_stats == {"previous": True}


@pytest.mark.parametrize("initial", [False, True])
@pytest.mark.parametrize("proof", ["tombstone", "404"])
def test_missing_mirror_is_retired_only_after_individual_confirmation(connection, initial, proof):
    event = _stored(connection)
    if initial:
        connection.sync_token = ""
        connection.save(update_fields=["sync_token"])
    resource = {"id": "missing", "status": "cancelled"} if proof == "tombstone" else _http_error(404)
    client = _client(connection, {"missing": resource}, initial=initial)

    result = _sync(connection, client)

    event.refresh_from_db()
    connection.refresh_from_db()
    assert event.cancelled_at == NOW
    assert event.description == "Original notes"
    assert result.cancelled == 1
    assert result.resynced is (not initial)
    assert connection.sync_token == "recovered"
    client.events.return_value.get.assert_called_once_with(calendarId="primary", eventId="missing")
    assert client.calendars.return_value.get.call_count == (1 if proof == "404" else 0)


@pytest.mark.parametrize("days", [5, 400])
def test_missing_event_that_moved_is_updated_even_beyond_the_list_window(connection, days):
    event = _stored(connection)
    moved_at = NOW + timedelta(days=days)
    resource = _event(
        event_id="missing", summary="Moved meeting",
        start={"dateTime": moved_at.isoformat()},
        end={"dateTime": (moved_at + timedelta(hours=1)).isoformat()},
    )

    result = _sync(connection, _client(connection, {"missing": resource}))

    event.refresh_from_db()
    assert event.starts_at == moved_at
    assert event.title == "Moved meeting"
    assert event.cancelled_at is None
    assert result.updated == 1 and result.cancelled == 0
    assert CalendarEvent.all_objects.filter(user=connection.user).count() == 1


def test_reconciliation_excludes_mail_manual_other_tenants_and_out_of_window_rows(connection):
    other = get_user_model().objects.create_user(email="other-cal@example.test", password="x")
    untouched = [
        _stored(connection, "mail", source=CalendarEvent.SOURCE_CAPTURE, thread_id="mail-thread"),
        _stored(connection, "manual", source=CalendarEvent.SOURCE_MANUAL),
        _stored(connection, "", title="No provider identity"),
        _stored(connection, "past", starts_at=NOW-timedelta(days=40), ends_at=NOW-timedelta(days=39)),
        _stored(connection, "lower-end", starts_at=NOW-timedelta(days=31), ends_at=NOW-timedelta(days=30)),
        _stored(connection, "upper-start", starts_at=NOW+timedelta(days=180), ends_at=None),
        _stored(connection, "far-future", starts_at=NOW+timedelta(days=400), ends_at=None),
        _stored(connection, "retired", cancelled_at=NOW-timedelta(days=1)),
        _stored(connection, "missing", user=other),
    ]
    snapshots = {row.pk: CalendarEvent.all_objects.filter(pk=row.pk).values().get() for row in untouched}
    missing = _stored(connection)
    overlapping = _stored(connection, "overlapping", starts_at=NOW-timedelta(days=31), ends_at=NOW-timedelta(days=29))
    seen = _stored(connection, "listed")
    client = _client(connection, {
        "missing": _http_error(404), "overlapping": {"id": "overlapping", "status": "cancelled"},
    }, items=[_event(event_id="listed")])

    _sync(connection, client)

    queried = {call.kwargs["eventId"] for call in client.events.return_value.get.call_args_list}
    assert queried == {"missing", "overlapping"}
    for row in untouched:
        assert CalendarEvent.all_objects.filter(pk=row.pk).values().get() == snapshots[row.pk]
    for row in (missing, overlapping):
        row.refresh_from_db()
        assert row.cancelled_at == NOW
    seen.refresh_from_db()
    assert seen.cancelled_at is None


@pytest.mark.parametrize("failure", [_http_error(code) for code in (401, 403, 410, 429, 500)] + [OSError("offline")])
def test_failure_after_one_confirmed_gap_applies_nothing_and_keeps_the_cursor(connection, failure):
    first = _stored(connection, "first")
    second = _stored(connection, "second")
    client = _client(connection, {"first": _http_error(404), "second": failure}, items=[_event(event_id="new")])

    with pytest.raises((gcal_live.GcalError, OSError)):
        _sync(connection, client)

    for row in (first, second):
        row.refresh_from_db()
        assert row.cancelled_at is None
    assert not CalendarEvent.all_objects.filter(external_id="new").exists()
    _assert_checkpoint_unchanged(connection)


@pytest.mark.parametrize("resource", [
    {}, {"id": "someone-else", "status": "cancelled"},
    {"id": "missing", "status": "confirmed"},
    {"id": "missing", "status": "confirmed", "start": {"dateTime": "nonsense"}},
    {"id": "missing", "status": "unknown", "start": {"dateTime": NOW.isoformat()}},
])
def test_unresolved_event_resource_preserves_the_row_and_checkpoint(connection, resource):
    event = _stored(connection)
    with pytest.raises(gcal_live.GcalError):
        _sync(connection, _client(connection, {"missing": resource}))
    event.refresh_from_db()
    assert event.cancelled_at is None
    _assert_checkpoint_unchanged(connection)


@pytest.mark.parametrize("calendar_reply", [_http_error(404), _http_error(403), {}, {"id": "different@example.test"}])
def test_an_event_404_with_unverified_calendar_access_is_not_a_cancellation(connection, calendar_reply):
    event = _stored(connection)
    client = _client(connection, {"missing": _http_error(404)})
    execute = client.calendars.return_value.get.return_value.execute
    if isinstance(calendar_reply, Exception):
        execute.side_effect = calendar_reply
    else:
        execute.return_value = calendar_reply
    with pytest.raises(gcal_live.GcalError):
        _sync(connection, client)
    event.refresh_from_db()
    assert event.cancelled_at is None
    _assert_checkpoint_unchanged(connection)


def test_dry_recovery_reports_confirmed_cancellation_without_any_write(connection):
    event = _stored(connection)
    result = _sync(connection, _client(connection, {"missing": _http_error(404)}), dry_run=True)
    assert result.cancelled == 1 and result.resynced
    event.refresh_from_db()
    assert event.cancelled_at is None
    _assert_checkpoint_unchanged(connection)


@pytest.mark.parametrize("pages", [
    [{"items": []}],
    [{"items": "unreadable", "nextSyncToken": "bad"}],
    [_page([], next_page_token="repeat"), _page([], next_page_token="repeat")],
    [_page([_event(event_id="new")], next_page_token="next"), _http_error(500)],
])
def test_incomplete_full_listing_cannot_start_reconciliation_or_advance(connection, pages):
    event = _stored(connection)
    client = _fake_client([_http_error(410), *pages])
    with pytest.raises((gcal_live.GcalError, type(_http_error(500)))):
        _sync(connection, client)
    client.events.return_value.get.assert_not_called()
    event.refresh_from_db()
    assert event.cancelled_at is None
    assert not CalendarEvent.all_objects.filter(external_id="new").exists()
    _assert_checkpoint_unchanged(connection)


@pytest.mark.parametrize("change", ["reconnect", "disconnect", "another_sync"])
def test_stale_provider_read_cannot_commit_over_changed_connection(connection, change):
    event = _stored(connection)
    client = _client(connection, {"missing": {"id": "missing", "status": "cancelled"}})
    original_get = client.events.return_value.get.side_effect

    def get(**kwargs):
        request = original_get(**kwargs)
        if change == "disconnect":
            GoogleCalendarConnection.all_objects.filter(pk=connection.pk).delete()
        elif change == "reconnect":
            GoogleCalendarConnection.all_objects.filter(pk=connection.pk).update(refresh_token_encrypted="replacement")
        else:
            GoogleCalendarConnection.all_objects.filter(pk=connection.pk).update(sync_token="other-run")
        return request

    client.events.return_value.get.side_effect = get
    with pytest.raises(gcal_live.GcalError, match="changed during sync"):
        _sync(connection, client)
    event.refresh_from_db()
    assert event.cancelled_at is None
    if change == "disconnect":
        assert not GoogleCalendarConnection.all_objects.filter(pk=connection.pk).exists()
    else:
        connection.refresh_from_db()
        assert connection.sync_token == ("other-run" if change == "another_sync" else "expired")
        if change == "reconnect":
            assert connection.refresh_token_encrypted == "replacement"


def test_event_write_failure_rolls_back_all_rows_and_cursor(connection):
    first = _event(event_id="first")
    second = _event(event_id="second")
    client = _client(connection, {}, items=[first, second])
    original = gcal_live._upsert_event

    def upsert(user, current, event, result, *, dry_run):
        assert transaction.get_connection().in_atomic_block
        if event["id"] == "second":
            raise RuntimeError("write interrupted")
        return original(user, current, event, result, dry_run=dry_run)

    with patch.object(gcal_live, "_upsert_event", side_effect=upsert):
        with pytest.raises(RuntimeError, match="write interrupted"):
            _sync(connection, client)
    assert not CalendarEvent.all_objects.filter(user=connection.user).exists()
    _assert_checkpoint_unchanged(connection)


def test_incremental_empty_result_does_not_reconcile_unchanged_events(connection):
    event = _stored(connection)
    client = _fake_client([_page([], next_sync_token="incremental")])
    _sync(connection, client)
    client.events.return_value.get.assert_not_called()
    event.refresh_from_db()
    assert event.cancelled_at is None
    connection.refresh_from_db()
    assert connection.sync_token == "incremental"
