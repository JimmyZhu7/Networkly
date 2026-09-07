"""The founder dashboard: staff-only, and reads rows the app already writes."""

from __future__ import annotations

import pytest
from django.utils import timezone

from analytics.events import record_event
from analytics.models import ProductEvent
from analytics.views import _pilot_drilldown, _pilot_rows

pytestmark = pytest.mark.django_db


def test_the_instrument_is_staff_only(client, django_user_model):
    assert client.get("/instrument/").status_code == 302, "anonymous is turned away"

    plain = django_user_model.objects.create_user(email="plain@x.com", password="x")
    client.force_login(plain)
    assert client.get("/instrument/").status_code == 302, "a signed-in user is not staff"

    staff = django_user_model.objects.create_user(email="staff@x.com", password="x")
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    client.force_login(staff)
    assert client.get("/instrument/").status_code == 200


def test_it_reports_what_the_product_recorded(client, django_user_model):
    staff = django_user_model.objects.create_user(email="staff2@x.com", password="x")
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    for _ in range(3):
        record_event("touch_logged", user=staff, source="today")
    record_event("opportunity_tracked", user=staff, status="saved")

    client.force_login(staff)
    response = client.get("/instrument/")
    body = response.content.decode()
    assert "touch_logged" in body and "opportunity_tracked" in body
    assert "Product Events" in body
    assert dict(response.context["top_events"])["touch_logged"] == 3
    assert dict(response.context["top_events"])["opportunity_tracked"] == 1


@pytest.mark.parametrize("user_id", ["²", "9" * 5000, str(2**63), "-1", "1.0"])
def test_malformed_drilldown_ids_do_not_query_or_raise(user_id, django_assert_num_queries):
    with django_assert_num_queries(0):
        assert _pilot_drilldown(user_id, timezone.now()) is None


def test_pilot_step_deduplication_preserves_furthest_known_step(django_user_model):
    from accounts.views import ONBOARDING_STEPS

    user = django_user_model.objects.create_user(email="steps@example.com", password="x")
    ProductEvent.all_objects.bulk_create([
        ProductEvent(user=user, event="onboarding_step_viewed", props={"step": step})
        for step in [ONBOARDING_STEPS[0], ONBOARDING_STEPS[-1], ONBOARDING_STEPS[0]] * 20
    ] + [
        ProductEvent(user=user, event="onboarding_step_viewed", props={"step": "unknown"}),
        ProductEvent(user=user, event="onboarding_step_viewed", props=["malformed"]),
    ])
    row = next(row for row in _pilot_rows(timezone.now()) if row["user"].pk == user.pk)
    assert row["step"] == ONBOARDING_STEPS[-1]
    assert row["step_number"] == len(ONBOARDING_STEPS)


def test_a_pipeline_stage_that_never_ran_says_so(client, django_user_model):
    """The honest answer to "is the automation still running" — a page that
    showed a blank where a stage should be would read as a rendering bug."""
    staff = django_user_model.objects.create_user(email="staff3@x.com", password="x")
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])
    client.force_login(staff)
    body = client.get("/instrument/").content.decode()
    assert "never run" in body
