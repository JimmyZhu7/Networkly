"""The ORM adapter preserves event order when timestamps are equal."""

from datetime import datetime, timezone

import pytest

from accounts.models import User
from crm.models import Contact, Touch
from crm.utils import _touch_dicts
from networkly_domain.scoring import score_contact


@pytest.mark.django_db
def test_scoring_adapter_keeps_ids_for_a_chat_after_a_same_time_override():
    user = User.objects.create_user(email="score-order@example.com", password="x")
    contact = Contact.all_objects.create(user=user, name="Analyst")
    now = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    Touch.all_objects.create(
        user=user, contact=contact, ts=now, kind="manual_override",
        note="manual override: warmth=cold",
    )
    chat = Touch.all_objects.create(user=user, contact=contact, ts=now, kind="chat")
    rows = Touch.objects.for_user(user).filter(contact=contact).order_by("-ts", "-id")
    history = _touch_dicts(rows)
    assert history[0]["id"] == chat.pk
    score = score_contact({"id": contact.pk}, history, as_of=now)
    assert score["axes"]["depth"]["level"] == 2
