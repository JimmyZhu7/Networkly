"""Journey 9: two accounts on one deployment, and the wall between them.

Nothing is mocked. Two synthetic students are given a full working set each —
contacts, applications, an assistant conversation, an uploaded photo, a
calendar event — and then one of them tries, through real HTTP requests, to
read every one of the other's.

The point is coverage of the SURFACES rather than of the managers. The
per-model tenancy tests (`crm/tests/test_tenant_isolation.py`,
`assistant/tests/test_isolation.py`) prove `for_user` scopes a queryset. This
proves the pages and routes a signed-in stranger can actually reach do not
hand anything over, including the private media route, which is the one that
serves a file off disk rather than a row out of the ORM.
"""

from __future__ import annotations

import datetime as dt
import io
import zipfile

import pytest
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from analytics.models import UserOpportunity
from assistant.models import ChatConversation, ChatMessage
from crm.models import CalendarEvent, Contact, Touch
from directory.models import Firm, Opportunity

pytestmark = pytest.mark.django_db


@pytest.fixture
def firm():
    return Firm.objects.create(name="Journey Partners", slug="journey-partners",
                               regions=["us"], tracks=["ib"])


@pytest.fixture
def role(firm):
    return Opportunity.objects.create(
        firm=firm, title="2028 Summer Analyst", url="https://example.test/journey",
        region="us", bucket="internship", status="open",
    )


def _world(email, *, name, firm, role, tmp_path=None):
    """One student, with one of everything they own."""
    user = User.objects.create_user(
        email=email, password="A-safe-passphrase-123", plan="pro",
        onboarded_at=timezone.now(), timezone="America/Los_Angeles",
    )
    contact = Contact.all_objects.create(user=user, name=name, firm=firm, source="manual")
    Touch.all_objects.create(user=user, contact=contact, kind="outreach",
                             channel="email", ts=timezone.now())
    application = UserOpportunity.all_objects.create(
        user=user, opportunity=role, applied_status="submitted", applied_at=timezone.now())
    conversation = ChatConversation.all_objects.create(user=user, title=f"{name} plan")
    # `text` is a read-only property over the Messages-API block list, so the
    # blocks are what a test writes.
    message = ChatMessage.all_objects.create(
        user=user, conversation=conversation, role=ChatMessage.ROLE_USER,
        content=[{"type": "text", "text": f"secret note about {name}"}])
    event = CalendarEvent.all_objects.create(
        user=user, title=f"{name} superday", source=CalendarEvent.SOURCE_MANUAL,
        starts_at=timezone.now() + dt.timedelta(days=7))
    user.avatar.save(f"{email.split('@')[0]}.png", ContentFile(b"synthetic png bytes"), save=True)
    return {
        "user": user, "contact": contact, "application": application,
        "conversation": conversation, "message": message, "event": event,
        "avatar_url": user.avatar.url, "avatar_name": user.avatar.name,
    }


@pytest.fixture
def owner(settings, tmp_path, firm, role):
    settings.MEDIA_ROOT = tmp_path
    return _world("owner@example.com", name="Dana Owner", firm=firm, role=role)


@pytest.fixture
def stranger(settings, tmp_path, firm, role):
    settings.MEDIA_ROOT = tmp_path
    return _world("stranger@example.com", name="Kim Stranger", firm=firm, role=role)


@pytest.fixture
def as_stranger(client, stranger):
    client.force_login(stranger["user"])
    return client


# ---------------------------------------------------------------------------
# Reading


def test_no_page_a_stranger_can_open_names_the_other_students_people(as_stranger, owner):
    for name in ("crm:week", "crm:contact_list", "crm:calendar",
                 "my_applications", "assistant:chat", "accounts:settings"):
        response = as_stranger.get(reverse(name))
        assert response.status_code == 200, name
        body = response.content.decode()
        assert "Dana Owner" not in body, name
        assert "Dana Owner superday" not in body, name
        assert "Dana Owner plan" not in body, name


def test_a_strangers_direct_link_to_a_contact_is_a_404(as_stranger, owner):
    for route in ("crm:contact_detail", "crm:contact_edit"):
        assert as_stranger.get(reverse(route, args=[owner["contact"].pk])).status_code == 404


def test_a_stranger_cannot_write_to_another_students_contact(as_stranger, owner):
    contact = owner["contact"]

    assert as_stranger.post(reverse("crm:log_touch", args=[contact.pk]),
                            {"kind": "reply_received", "channel": "email"}).status_code == 404
    assert as_stranger.post(reverse("crm:contact_archive", args=[contact.pk])).status_code == 404
    assert as_stranger.post(reverse("crm:contact_edit", args=[contact.pk]),
                            {"name": "Renamed By A Stranger"}).status_code == 404

    contact.refresh_from_db()
    assert contact.name == "Dana Owner"
    assert contact.archived is False
    assert Touch.all_objects.filter(contact=contact).count() == 1


def test_a_stranger_cannot_open_or_delete_another_students_conversation(as_stranger, owner):
    conversation = owner["conversation"]

    opened = as_stranger.get(reverse("assistant:chat_conversation", args=[conversation.pk]))
    assert "secret note about Dana Owner" not in opened.content.decode()

    as_stranger.post(reverse("assistant:delete"), {"conversation": str(conversation.pk)})
    as_stranger.post(reverse("assistant:rename"),
                     {"conversation": str(conversation.pk), "title": "Taken"})

    conversation.refresh_from_db()
    assert conversation.title == "Dana Owner plan"
    assert ChatMessage.all_objects.filter(conversation=conversation).count() == 1


def test_a_stranger_cannot_touch_another_students_application(as_stranger, owner, role):
    assert as_stranger.post(reverse("track_opportunity", args=[role.pk]),
                            {"status": "clear"}).status_code == 302

    owner["application"].refresh_from_db()
    assert owner["application"].applied_status == "submitted"
    assert UserOpportunity.all_objects.filter(user=owner["user"]).count() == 1


def test_a_stranger_cannot_remove_another_students_calendar_event(as_stranger, owner):
    event = owner["event"]

    assert as_stranger.post(reverse("crm:calendar_delete", args=[event.pk])).status_code == 302

    assert CalendarEvent.all_objects.filter(pk=event.pk).exists()


def test_the_ics_feed_carries_only_the_account_whose_token_it_is(client, owner, stranger):
    owner["user"].refresh_from_db()
    stranger["user"].refresh_from_db()

    theirs = client.get(reverse("crm:calendar_ics", args=[stranger["user"].calendar_token]))

    assert theirs.status_code == 200
    body = theirs.content.decode()
    assert "Kim Stranger superday" in body
    assert "Dana Owner superday" not in body
    assert f"coverage-ev-{owner['event'].pk}@" not in body


def test_the_export_is_one_accounts_data_and_only_that(as_stranger, owner):
    archive = zipfile.ZipFile(io.BytesIO(
        b"".join(as_stranger.get(reverse("accounts:export"), {"kind": "all"}).streaming_content)))

    everything = b"".join(archive.read(name) for name in archive.namelist())

    assert b"Kim Stranger" in everything
    assert b"Dana Owner" not in everything
    assert b"secret note about Dana Owner" not in everything


# ---------------------------------------------------------------------------
# The private media route


def test_an_avatar_url_is_ownership_checked_not_merely_unguessable(
    client, owner, stranger,
):
    """The one route that serves a FILE rather than a row.

    The owner's URL is not a secret in any useful sense — it is printed in the
    owner's own HTML — so the check has to be on who is asking, not on whether
    the path could be guessed. It answers 404 rather than 403 to everyone
    else, so the route never confirms that the file exists.
    """
    url = owner["avatar_url"]
    assert url.endswith(".png")

    # Nobody at all.
    assert client.get(url).status_code == 404

    # Another signed-in student.
    client.force_login(stranger["user"])
    assert client.get(url).status_code == 404
    # Their own still works, so the 404 above is the ownership check and not
    # a broken route.
    own = client.get(stranger["avatar_url"])
    assert own.status_code == 200
    assert own["Cache-Control"] == "private, no-store"
    assert own["X-Content-Type-Options"] == "nosniff"

    # Staff are not exempt.
    admin = User.objects.create_superuser(email="admin@example.com", password="pw")
    client.force_login(admin)
    assert client.get(url).status_code == 404

    # And the owner.
    client.force_login(owner["user"])
    assert client.get(url).status_code == 200


def test_a_deactivated_account_stops_serving_its_own_avatar(client, owner):
    client.force_login(owner["user"])
    assert client.get(owner["avatar_url"]).status_code == 200

    owner["user"].is_active = False
    owner["user"].save(update_fields=["is_active"])

    assert client.get(owner["avatar_url"]).status_code == 404


def test_clearing_an_avatar_makes_its_old_url_a_404_for_the_owner_too(client, owner):
    client.force_login(owner["user"])
    url = owner["avatar_url"]
    assert client.get(url).status_code == 200

    owner["user"].avatar = None
    owner["user"].save(update_fields=["avatar"])

    assert client.get(url).status_code == 404
