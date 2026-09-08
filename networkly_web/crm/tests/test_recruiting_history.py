from datetime import datetime, timedelta, timezone as utc

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from crm.forms import ContactForm
from crm.models import Contact, Touch
from crm.today import _action_history
from networkly_domain.cadence import due_actions

pytestmark = pytest.mark.django_db


def test_history_reads_only_live_owned_evidence_without_note_bodies():
    user = get_user_model().objects.create_user(email="history@example.test")
    other = get_user_model().objects.create_user(email="other@example.test")
    contact = Contact.all_objects.create(user=user, name="One")
    archived = Contact.all_objects.create(user=user, name="Archived", archived=True)
    foreign = Contact.all_objects.create(user=other, name="Foreign")
    now = datetime(2026, 9, 7, 10, tzinfo=utc.utc)
    old = now - timedelta(days=60)
    Touch.all_objects.bulk_create([
        Touch(user=user, contact=contact, kind="outreach", ts=old, note="private body" * 1000),
        Touch(user=user, contact=contact, kind="follow_up", ts=now),
        Touch(user=user, contact=contact, kind="bulk_received", ts=now + timedelta(hours=1)),
        Touch(user=user, contact=archived, kind="outreach", ts=now),
        Touch(user=other, contact=foreign, kind="outreach", ts=now),
        # Deliberately inconsistent imported row: ownership must also match.
        Touch(user=other, contact=contact, kind="reply_received", ts=now),
    ])
    with timezone.override("UTC"), CaptureQueriesContext(connection) as queries:
        history, last, chased, sent = _action_history(user, [contact], today=now.date())
    assert set(history.contacts) == {contact.pk}
    assert history.contacts[contact.pk].outbound == 2
    assert last[contact.pk].kind == "follow_up"
    assert chased == {contact.pk: now}
    assert sent == {contact.pk: 1}
    assert all('"note"' not in q["sql"] and '"subject"' not in q["sql"] for q in queries)
    assert len(queries) == 1


def test_edit_form_cannot_rewind_newer_relationship_or_archive_state():
    user = get_user_model().objects.create_user(email="form@example.test")
    contact = Contact.all_objects.create(user=user, name="Old name", region="us")
    form = ContactForm({"name": "New name", "region": "hk"}, instance=contact)
    assert form.is_valid(), form.errors
    Contact.all_objects.filter(pk=contact.pk).update(
        warmth="advocate", thread_state="chat_done", archived=True, ai_summary="New summary",
    )
    form.save()
    contact.refresh_from_db()
    assert contact.name == "New name"
    assert contact.region == "hk" and contact.region_source == "user"
    assert contact.warmth == "advocate" and contact.thread_state == "chat_done"
    assert contact.archived and contact.ai_summary == "New summary"
