"""Authenticated request contracts for target removal and mail-fact actions."""
from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from analytics.models import ProductEvent
from capture import mailfacts
from capture.models import MailFact
from crm.models import Contact, UserFirm
from directory.models import Firm


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def owner():
    return get_user_model().objects.create_user(
        email="capture-actions@example.test", password="x",
        timezone="America/Los_Angeles", onboarded_at=timezone.now(),
    )


@pytest.fixture
def other():
    return get_user_model().objects.create_user(email="other-actions@example.test", password="x")


@pytest.fixture
def firm():
    return Firm.objects.create(name="Boundary Partners", slug="boundary-partners")


def test_remove_target_only_unlinks_requesting_owner_and_is_replay_safe(client, owner, other, firm):
    own_target = UserFirm.all_objects.create(user=owner, firm=firm, tier=1)
    other_target = UserFirm.all_objects.create(user=other, firm=firm, tier=2)
    contact = Contact.all_objects.create(user=owner, firm=firm, name="Still Connected", notes="Keep this")
    client.force_login(owner)
    url = reverse("crm:remove_target_firm")

    assert client.post(url, {"firm": firm.pk, "user": other.pk}).status_code == 204
    assert not UserFirm.objects.for_user(owner).filter(pk=own_target.pk).exists()
    assert UserFirm.objects.for_user(other).filter(pk=other_target.pk, tier=2).exists()
    contact.refresh_from_db()
    assert (contact.firm_id, contact.notes, contact.archived) == (firm.pk, "Keep this", False)
    assert Firm.objects.filter(pk=firm.pk).exists()
    assert client.post(url, {"firm": firm.pk}).status_code == 404
    assert ProductEvent.objects.for_user(owner).filter(event="firm_target_removed").count() == 1
    assert not ProductEvent.objects.for_user(other).exists()


@pytest.mark.parametrize("payload,status", [({}, 400), ({"firm": "invalid"}, 400), ({"firm": "-1"}, 404)])
def test_remove_target_rejects_invalid_input_without_changes(client, owner, firm, payload, status):
    target = UserFirm.all_objects.create(user=owner, firm=firm, tier=1)
    client.force_login(owner)
    assert client.post(reverse("crm:remove_target_firm"), payload).status_code == status
    assert UserFirm.objects.for_user(owner).filter(pk=target.pk).exists()
    assert not ProductEvent.objects.for_user(owner).filter(event="firm_target_removed").exists()


def test_remove_target_cannot_remove_a_foreign_only_target_and_requires_post(client, owner, other, firm):
    target = UserFirm.all_objects.create(user=other, firm=firm, tier=1)
    client.force_login(owner)
    url = reverse("crm:remove_target_firm")
    assert client.get(url, {"firm": firm.pk}).status_code == 405
    assert client.post(url, {"firm": firm.pk}).status_code == 404
    assert UserFirm.objects.for_user(other).filter(pk=target.pk).exists()


def _address_fact(owner):
    contact = Contact.all_objects.create(
        user=owner, name="Alex", email="alex@old.example", notes="User note\nAutomatic address note",
    )
    fact = MailFact.all_objects.create(
        user=owner, contact=contact, kind=MailFact.KIND_ADDRESS_CHANGE,
        about_email=contact.email, new_email="alex@new.example",
        quote="My new email is alex@new.example.", note_line="Automatic address note",
        status=MailFact.STATUS_APPLIED,
    )
    return contact, fact


def test_mail_fact_undo_removes_only_its_note_and_replay_has_no_effect(client, owner):
    contact, fact = _address_fact(owner)
    # A manual edit after capture must survive the undo.
    Contact.objects.for_user(owner).filter(pk=contact.pk).update(
        email="chosen@manual.example", notes=contact.notes + "\nLater user note",
    )
    client.force_login(owner)
    url = reverse("crm:mail_fact_act", args=[fact.pk, "undo"])
    response = client.post(url)
    assert response.status_code == 200 and b'cockpit' in response.content
    contact.refresh_from_db()
    fact.refresh_from_db()
    assert contact.notes == "User note\nLater user note"
    assert contact.email == "chosen@manual.example"
    assert fact.status == MailFact.STATUS_UNDONE and fact.resolved_at is not None
    resolved_at = fact.resolved_at
    assert client.post(url).status_code == 404
    fact.refresh_from_db()
    assert fact.resolved_at == resolved_at
    assert ProductEvent.objects.for_user(owner).filter(event="mail_fact_undone").count() == 1


@pytest.mark.parametrize("status", [MailFact.STATUS_PENDING, MailFact.STATUS_APPLIED])
def test_mail_fact_dismiss_preserves_contact_and_cannot_reopen(client, owner, status):
    contact, fact = _address_fact(owner)
    fact.status = status
    fact.save(update_fields=["status"])
    before = (contact.notes, contact.email)
    client.force_login(owner)
    url = reverse("crm:mail_fact_act", args=[fact.pk, "dismiss"])
    assert client.post(url).status_code == 200
    fact.refresh_from_db()
    contact.refresh_from_db()
    assert fact.status == MailFact.STATUS_DISMISSED and fact.resolved_at is not None
    assert (contact.notes, contact.email) == before
    assert client.post(url).status_code == 404
    assert client.post(reverse("crm:mail_fact_act", args=[fact.pk, "undo"])).status_code == 404
    assert ProductEvent.objects.for_user(owner).filter(event="mail_fact_dismissed").count() == 1


@pytest.mark.parametrize("verb", ["undo", "dismiss"])
def test_mail_fact_actions_refuse_foreign_missing_and_get_requests(client, owner, other, verb):
    contact, foreign = _address_fact(other)
    client.force_login(owner)
    url = reverse("crm:mail_fact_act", args=[foreign.pk, verb])
    assert client.post(url).status_code == 404
    assert client.get(url).status_code == 405
    assert client.post(reverse("crm:mail_fact_act", args=[foreign.pk + 10000, verb])).status_code == 404
    contact.refresh_from_db()
    foreign.refresh_from_db()
    assert foreign.status == MailFact.STATUS_APPLIED and foreign.resolved_at is None
    assert contact.notes == "User note\nAutomatic address note"
    assert not ProductEvent.objects.for_user(owner).exists()


def test_invalid_mail_fact_action_has_no_effect(client, owner):
    contact, fact = _address_fact(owner)
    client.force_login(owner)
    assert client.post(reverse("crm:mail_fact_act", args=[fact.pk, "delete"])).status_code == 400
    fact.refresh_from_db()
    contact.refresh_from_db()
    assert fact.status == MailFact.STATUS_APPLIED and fact.resolved_at is None
    assert contact.notes == "User note\nAutomatic address note"
    assert not ProductEvent.objects.for_user(owner).exists()


def test_pending_mail_fact_cannot_undo_an_unapplied_action(client, owner):
    contact, fact = _address_fact(owner)
    fact.status = MailFact.STATUS_PENDING
    fact.save(update_fields=["status"])
    client.force_login(owner)
    assert client.post(reverse("crm:mail_fact_act", args=[fact.pk, "undo"])).status_code == 200
    fact.refresh_from_db()
    contact.refresh_from_db()
    assert fact.status == MailFact.STATUS_PENDING and fact.resolved_at is None
    assert contact.notes == "User note\nAutomatic address note"


def test_mail_fact_ooo_undo_keeps_a_later_manual_snooze(client, owner):
    old_snooze = timezone.now() + timedelta(days=2)
    applied_snooze = old_snooze + timedelta(days=3)
    manual_snooze = applied_snooze + timedelta(days=10)
    contact = Contact.all_objects.create(user=owner, name="Away", snoozed_until=manual_snooze)
    fact = MailFact.all_objects.create(
        user=owner, contact=contact, kind=MailFact.KIND_OOO, about_email="away@example.test",
        status=MailFact.STATUS_APPLIED, prior_snoozed_until=old_snooze, snoozed_to=applied_snooze,
    )
    client.force_login(owner)
    assert client.post(reverse("crm:mail_fact_act", args=[fact.pk, "undo"])).status_code == 200
    contact.refresh_from_db()
    fact.refresh_from_db()
    assert contact.snoozed_until == manual_snooze and fact.status == MailFact.STATUS_UNDONE


@pytest.mark.parametrize("verb", ["undo", "dismiss"])
def test_mail_fact_action_rereads_a_resolution_after_request_lookup(client, owner, monkeypatch, verb):
    contact, fact = _address_fact(owner)
    resolved_at = timezone.now()
    real_action = getattr(mailfacts, verb)
    def resolve_before_lock(stale):
        assert stale.status == MailFact.STATUS_APPLIED
        MailFact.objects.for_user(owner).filter(pk=fact.pk).update(
            status=MailFact.STATUS_UNDONE, resolved_at=resolved_at,
        )
        Contact.objects.for_user(owner).filter(pk=contact.pk).update(notes="Later corrected note")
        real_action(stale)
    monkeypatch.setattr(mailfacts, verb, resolve_before_lock)
    client.force_login(owner)
    assert client.post(reverse("crm:mail_fact_act", args=[fact.pk, verb])).status_code == 200
    contact.refresh_from_db()
    fact.refresh_from_db()
    assert fact.status == MailFact.STATUS_UNDONE and fact.resolved_at == resolved_at
    assert contact.notes == "Later corrected note"


def test_mail_fact_undo_marker_failure_rolls_back_the_contact_edit(client, owner, monkeypatch):
    contact, fact = _address_fact(owner)
    original = MailFact.save
    def fail_resolution(row, *args, **kwargs):
        if row.pk == fact.pk and kwargs.get("update_fields") == ["status", "resolved_at"]:
            raise RuntimeError("resolution marker failed")
        return original(row, *args, **kwargs)
    monkeypatch.setattr(MailFact, "save", fail_resolution)
    client.force_login(owner)
    with pytest.raises(RuntimeError, match="resolution marker failed"):
        client.post(reverse("crm:mail_fact_act", args=[fact.pk, "undo"]))
    contact.refresh_from_db()
    fact.refresh_from_db()
    assert contact.notes == "User note\nAutomatic address note"
    assert fact.status == MailFact.STATUS_APPLIED and fact.resolved_at is None
