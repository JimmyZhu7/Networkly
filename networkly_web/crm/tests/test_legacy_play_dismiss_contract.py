"""The registered legacy dismissal route remains scoped and repeat-safe."""
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from analytics.models import ProductEvent
from crm.models import PlayDismissal
from directory.models import Firm


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def owner():
    return get_user_model().objects.create_user(
        email="legacy-play@example.test", password="x", onboarded_at=timezone.now(),
        timezone="America/Los_Angeles",
    )


@pytest.fixture
def firm():
    return Firm.objects.create(name="Legacy Firm", slug="legacy-firm")


def payload(firm_obj, **updates):
    return {"firm": firm_obj.pk, "date": "2026-11-10", "event_kind": "applications_close", **updates}


def test_anonymous_or_non_post_requests_cannot_write(client, owner, firm):
    url = reverse("crm:play_dismiss")
    assert client.post(url, payload(firm)).status_code == 302
    assert not PlayDismissal.objects.for_user(owner).exists()
    client.force_login(owner)
    assert client.get(url, payload(firm)).status_code == 405
    assert not PlayDismissal.objects.for_user(owner).exists()


def test_dismissal_is_owned_and_repeating_the_same_fact_keeps_one_record(client, owner, firm):
    other = get_user_model().objects.create_user(email="other-legacy-play@example.test", password="x")
    foreign = PlayDismissal.all_objects.create(
        user=other, firm=firm, event_kind="applications_close", date=date(2026, 11, 10),
    )
    foreign_time = foreign.dismissed_at
    client.force_login(owner)
    url = reverse("crm:play_dismiss")
    assert client.post(url, payload(firm, user=other.pk)).status_code == 200
    own = PlayDismissal.objects.for_user(owner).get()
    assert own.pk != foreign.pk
    assert (own.firm_id, own.event_kind, own.date) == (firm.pk, "applications_close", date(2026, 11, 10))
    own_time = own.dismissed_at
    assert client.post(url, payload(firm)).status_code == 200
    own.refresh_from_db()
    foreign.refresh_from_db()
    assert PlayDismissal.objects.for_user(owner).count() == 1 and own.dismissed_at == own_time
    assert foreign.dismissed_at == foreign_time and PlayDismissal.objects.for_user(other).count() == 1
    assert not ProductEvent.objects.for_user(other).filter(event="play_dismissed").exists()


def test_changed_fact_date_is_a_new_dismissal_not_an_overwrite(client, owner, firm):
    client.force_login(owner)
    url = reverse("crm:play_dismiss")
    assert client.post(url, payload(firm)).status_code == 200
    assert client.post(url, payload(firm, date="2026-11-11")).status_code == 200
    assert set(PlayDismissal.objects.for_user(owner).values_list("date", flat=True)) == {
        date(2026, 11, 10), date(2026, 11, 11),
    }


@pytest.mark.parametrize("updates,expected", [
    ({"firm": "not-an-id"}, 400),
    ({"firm": ""}, 400),
    ({"firm": -1}, 404),
    ({"date": "2026-02-30"}, 400),
    ({"date": "not-a-date"}, 400),
    ({"date": ""}, 400),
    ({"event_kind": "   "}, 400),
    ({"event_kind": "x" * 65}, 400),
    ({"event_kind": "界" * 65}, 400),
])
def test_invalid_fact_input_has_a_controlled_response_and_no_writes(client, owner, firm, updates, expected):
    client.force_login(owner)
    assert client.post(reverse("crm:play_dismiss"), payload(firm, **updates)).status_code == expected
    assert not PlayDismissal.objects.for_user(owner).exists()
    assert not ProductEvent.objects.for_user(owner).filter(event="play_dismissed").exists()


def test_event_kind_whitespace_is_normalized_without_losing_the_key(client, owner, firm):
    client.force_login(owner)
    url = reverse("crm:play_dismiss")
    assert client.post(url, payload(firm, event_kind=" applications_close ")).status_code == 200
    assert client.post(url, payload(firm)).status_code == 200
    assert PlayDismissal.objects.for_user(owner).get().event_kind == "applications_close"


@pytest.mark.parametrize("event_kind", ["x" * 64, "界" * 64])
def test_event_kind_accepts_the_full_character_limit_after_trimming(client, owner, firm, event_kind):
    client.force_login(owner)
    url = reverse("crm:play_dismiss")
    assert client.post(url, payload(firm, event_kind=" " + event_kind + " ")).status_code == 200
    assert client.post(url, payload(firm, event_kind=event_kind)).status_code == 200
    assert PlayDismissal.objects.for_user(owner).get().event_kind == event_kind
