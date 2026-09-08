"""Address-change evidence, tenant ownership and exact reversible notes."""
import pytest
from django.contrib.auth import get_user_model

from capture import mailfacts
from capture.models import MailFact
from crm.models import Contact


pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def owner():
    return get_user_model().objects.create_user(email="address-facts@example.test", password="x")


def _finding(**updates):
    finding = {
        "found": True, "email": "alex@old.example", "name": "Alex",
        "replied": True, "subject": "Contact details",
        "snippet": "My new email address is alex@new.example.", "thread_id": "address-1",
    }
    finding.update(updates)
    return finding


@pytest.mark.parametrize("auto_reply", [False, True])
def test_grounded_address_change_keeps_primary_and_preserves_later_manual_edits(owner, auto_reply):
    contact = Contact.all_objects.create(user=owner, name="Alex", email="alex@old.example", notes="Prior note")
    finding = _finding(auto_reply=auto_reply, bulk=auto_reply)
    result = mailfacts.consider_finding(owner, finding, allow_ai=False)
    contact.refresh_from_db()
    fact = MailFact.objects.for_user(owner).get(kind=MailFact.KIND_ADDRESS_CHANGE)
    assert result.applied == 1 and result.surfaced == 0
    assert contact.email == "alex@old.example" and fact.new_email == "alex@new.example"
    assert fact.status == MailFact.STATUS_APPLIED and fact.contact_id == contact.pk
    assert fact.quote in mailfacts._finding_text(finding) and fact.new_email in fact.quote
    assert fact.note_line in contact.notes and contact.notes.startswith("Prior note\n")
    notes_once = contact.notes
    assert mailfacts.consider_finding(owner, finding, allow_ai=False).applied == 0
    contact.refresh_from_db()
    assert contact.notes == notes_once and MailFact.objects.for_user(owner).count() == 1

    Contact.objects.for_user(owner).filter(pk=contact.pk).update(
        email="chosen@manual.example", notes=notes_once + "\nLater manual note",
    )
    mailfacts.undo(fact)
    contact.refresh_from_db()
    fact.refresh_from_db()
    assert contact.notes == "Prior note\nLater manual note" and contact.email == "chosen@manual.example"
    assert fact.status == MailFact.STATUS_UNDONE
    resolved_at = fact.resolved_at
    mailfacts.undo(fact)
    mailfacts.consider_finding(owner, finding, allow_ai=False)
    fact.refresh_from_db()
    contact.refresh_from_db()
    assert fact.resolved_at == resolved_at and fact.status == MailFact.STATUS_UNDONE
    assert contact.notes == "Prior note\nLater manual note"


def test_address_change_for_unknown_sender_never_updates_another_tenant(owner):
    other = get_user_model().objects.create_user(email="foreign-address@example.test", password="x")
    contact = Contact.all_objects.create(user=other, name="Alex", email="alex@old.example", notes="Private note")
    result = mailfacts.consider_finding(owner, _finding(), allow_ai=False)
    contact.refresh_from_db()
    fact = MailFact.objects.for_user(owner).get(kind=MailFact.KIND_ADDRESS_CHANGE)
    assert result.surfaced == 1 and result.applied == 0
    assert fact.status == MailFact.STATUS_PENDING and fact.contact_id is None
    assert not Contact.objects.for_user(owner).exists()
    assert contact.email == "alex@old.example" and contact.notes == "Private note"
    assert not MailFact.objects.for_user(other).exists()


@pytest.mark.parametrize("updates", [
    {"snippet": "Her new email address is alex@new.example."},
    {"snippet": "My new email address is alex@old.example."},
    {"bulk": True},
    {"outreach_sent": True},
    {"found": False},
    {"replied": False},
])
def test_non_address_or_untrusted_human_findings_do_not_write_notes(owner, updates):
    contact = Contact.all_objects.create(user=owner, name="Alex", email="alex@old.example", notes="Keep")
    result = mailfacts.consider_finding(owner, _finding(**updates), allow_ai=False)
    contact.refresh_from_db()
    assert result.applied == 0 and result.surfaced == 0
    assert contact.email == "alex@old.example" and contact.notes == "Keep"
    assert not MailFact.objects.for_user(owner).exists()


@pytest.mark.parametrize("known", [False, True])
def test_address_change_dry_run_describes_without_mutating(owner, known):
    if known:
        Contact.all_objects.create(user=owner, name="Alex", email="alex@old.example", notes="Keep")
    result = mailfacts.consider_finding(owner, _finding(), dry_run=True, allow_ai=False)
    assert (result.applied, result.surfaced) == ((1, 0) if known else (0, 1))
    assert not MailFact.objects.for_user(owner).exists()
    assert list(Contact.objects.for_user(owner).values_list("notes", flat=True)) == (["Keep"] if known else [])


@pytest.mark.parametrize("auto_reply", [False, True])
def test_long_address_statement_keeps_the_address_in_its_visible_evidence(owner, auto_reply):
    contact = Contact.all_objects.create(user=owner, name="Alex", email="alex@old.example")
    finding = _finding(auto_reply=auto_reply, bulk=auto_reply,
                       snippet="For your records " * 40 + "my new email address is alex@new.example.")
    mailfacts.consider_finding(owner, finding, allow_ai=False)
    fact = MailFact.objects.for_user(owner).get(kind=MailFact.KIND_ADDRESS_CHANGE)
    assert len(fact.quote) <= 500 and fact.quote in mailfacts._finding_text(finding)
    assert fact.new_email in fact.quote
    assert fact.quote == "my new email address is alex@new.example"
    assert fact.quote in finding["snippet"]
    contact.refresh_from_db()
    assert contact.email == "alex@old.example"


@pytest.mark.parametrize("auto_reply", [False, True])
def test_address_quote_preserves_source_case_while_email_is_normalized(owner, auto_reply):
    Contact.all_objects.create(user=owner, name="Alex", email="alex@old.example")
    finding = _finding(auto_reply=auto_reply, bulk=auto_reply,
                       snippet="My new email address is Alex@NEW.example.")
    mailfacts.consider_finding(owner, finding, allow_ai=False)
    fact = MailFact.objects.for_user(owner).get(kind=MailFact.KIND_ADDRESS_CHANGE)
    assert fact.new_email == "alex@new.example"
    assert fact.quote == "My new email address is Alex@NEW.example"
    assert fact.quote in finding["snippet"]
