"""Journey 3: find a role, save it, apply, move it, drop it.

Nothing is mocked. The feed, the track control and My Applications are the
real views over real rows; the student is synthetic and lives only in the test
database.

`test_my_applications_ui.py` and `test_bulk_save.py` cover the page and the
bulk path. What is new here is the SEQUENCE — feed, save, apply, revisit,
re-stage from the row control, remove — walked as one session, including the
htmx swap the row control actually returns, which is the response a student
sees and which no test asserted the shape of.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from analytics.models import UserOpportunity
from directory.models import Firm, Opportunity

pytestmark = pytest.mark.django_db


@pytest.fixture
def student():
    user = User.objects.create_user(email="applicant@example.com", password="A-safe-passphrase-123")
    user.regions = ["us"]
    user.tracks = ["ib"]
    user.class_year = 2028
    user.onboarded_at = timezone.now()
    user.save()
    return user


@pytest.fixture
def signed_in(client, student):
    client.force_login(student)
    return client


@pytest.fixture
def firm():
    return Firm.objects.create(
        name="Journey Partners", slug="journey-partners", regions=["us"], tracks=["ib"],
    )


@pytest.fixture
def role(firm):
    return Opportunity.objects.create(
        firm=firm,
        title="2028 Summer Analyst, Investment Banking",
        url="https://example.test/journey-summer-analyst",
        region="us",
        bucket="internship",
        status="open",
        deadline=timezone.localdate() + dt.timedelta(days=21),
    )


def _track(client, role, status, **extra):
    return client.post(reverse("track_opportunity", args=[role.pk]),
                       {"status": status, **extra})


def _row(student, role):
    return UserOpportunity.objects.for_user(student).get(opportunity=role)


# ---------------------------------------------------------------------------


def test_an_eligible_role_is_findable_on_the_feed(signed_in, role):
    feed = signed_in.get(reverse("opportunities"))

    assert feed.status_code == 200
    body = feed.content.decode()
    assert role.title in body
    assert role.firm.name in body


def test_the_full_save_apply_revisit_remove_sequence(signed_in, student, role):
    apps = reverse("my_applications")

    # Empty to begin with — the page has to be honest about nothing, too.
    empty = signed_in.get(apps)
    assert empty.status_code == 200 and empty.context["total"] == 0

    assert _track(signed_in, role, "saved").status_code == 302
    saved = _row(student, role)
    assert saved.applied_status == "" and saved.applied_at is None
    assert not saved.dismissed

    page = signed_in.get(apps)
    assert page.context["total"] == 1
    assert role.title in page.content.decode()
    stages = {s["key"]: s["count"] for s in page.context["stages"]}
    assert stages["saved"] == 1 and stages["submitted"] == 0

    assert _track(signed_in, role, "submitted").status_code == 302
    applied = _row(student, role)
    assert applied.applied_status == "submitted"
    assert applied.applied_at is not None
    first_applied_at = applied.applied_at

    page = signed_in.get(apps)
    stages = {s["key"]: s["count"] for s in page.context["stages"]}
    assert stages["saved"] == 0 and stages["submitted"] == 1
    assert page.context["total"] == 1

    # Removing is the same control, and it really removes.
    assert _track(signed_in, role, "clear").status_code == 302
    assert not UserOpportunity.objects.for_user(student).filter(opportunity=role).exists()
    assert signed_in.get(apps).context["total"] == 0
    # The shared directory row is untouched by one student dropping it.
    role.refresh_from_db()
    assert role.status == "open"
    assert first_applied_at is not None


def test_the_row_control_swaps_the_pipeline_body_back_in_place(signed_in, student, role):
    """The control a student actually clicks on My Applications is an htmx
    form: its answer has to be the pipeline partial, because a status change
    MOVES the row between sections rather than editing it in place."""
    _track(signed_in, role, "saved")
    apps = reverse("my_applications")

    response = signed_in.post(
        reverse("track_opportunity", args=[role.pk]),
        {"status": "interview", "next": apps},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 200
    body = response.content.decode()
    assert role.title in body
    # A fragment, not a whole second page swapped inside the first.
    assert "<html" not in body.lower()
    assert _row(student, role).applied_status == "interview"
    stages = {s["key"]: s["count"] for s in response.context["stages"]}
    assert stages["interview"] == 1 and stages["saved"] == 0


def test_moving_forward_and_back_keeps_the_first_applied_stamp(signed_in, student, role):
    """`applied_at` is when the student applied, not when they last touched it."""
    _track(signed_in, role, "submitted")
    stamped = _row(student, role).applied_at
    assert stamped is not None

    _track(signed_in, role, "interview")
    _track(signed_in, role, "offer")
    _track(signed_in, role, "saved")

    row = _row(student, role)
    assert row.applied_status == ""
    assert row.applied_at == stamped


def test_an_unknown_status_is_refused_rather_than_stored(signed_in, student, role):
    response = _track(signed_in, role, "definitely-not-a-stage")

    assert response.status_code == 400
    assert not UserOpportunity.objects.for_user(student).filter(opportunity=role).exists()


def test_not_for_me_hides_a_role_and_is_reversible(signed_in, student, role):
    assert _track(signed_in, role, "dismiss").status_code == 302
    dismissed = UserOpportunity.all_objects.get(user=student, opportunity=role)
    assert dismissed.dismissed and dismissed.applied_status == ""
    assert signed_in.get(reverse("my_applications")).context["total"] == 0

    assert _track(signed_in, role, "undismiss").status_code == 302
    assert not UserOpportunity.all_objects.filter(user=student, opportunity=role).exists()


def test_one_students_pipeline_is_invisible_to_another(signed_in, student, role):
    _track(signed_in, role, "submitted")

    other = User.objects.create_user(email="other@example.com", password="A-safe-passphrase-123")
    signed_in.force_login(other)

    page = signed_in.get(reverse("my_applications"))
    assert page.context["total"] == 0
    assert role.title.encode() not in page.content

    # And the other student clearing the same shared role leaves the first
    # student's application exactly where it was.
    assert _track(signed_in, role, "clear").status_code == 302
    assert _row(student, role).applied_status == "submitted"


def test_the_pipeline_is_private(client, role):
    assert client.get(reverse("my_applications")).status_code == 302
    assert client.post(reverse("track_opportunity", args=[role.pk]),
                       {"status": "saved"}).status_code == 302
    assert not UserOpportunity.all_objects.exists()
