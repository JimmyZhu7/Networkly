from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from capture.models import ApplicationEvent, ContactProposal
from crm.models import Contact, PlayDismissal, Task
from directory.firm_merge import merge_firms
from directory.models import Firm, FirmCycleObservation, Opportunity, OpportunityChange

pytestmark = pytest.mark.django_db


def _world():
    user = get_user_model().objects.create_user(email="merge-integrity@example.test")
    keep = Firm.objects.create(name="Bank", slug="bank")
    lose = Firm.objects.create(name="Bank", slug="bank-copy")
    return user, keep, lose


def _role(firm):
    return Opportunity.objects.create(firm=firm, title="Analyst", url="https://example.test/analyst")


def test_merge_keeps_person_links_mail_evidence_and_change_ledger():
    user, keep, lose = _world()
    role, duplicate_role = _role(keep), _role(lose)
    contact = Contact.all_objects.create(user=user, name="Ada", firm=lose, region="hk")
    task = Task.all_objects.create(user=user, firm=lose, title="Apply")
    proposal = ContactProposal.all_objects.create(user=user, firm=lose, name="New person")
    event = ApplicationEvent.all_objects.create(
        user=user, opportunity=duplicate_role, firm=lose, event_type="applied", target_status="submitted",
        evidence="Original application evidence", firm_text="Bank original mail name",
    )
    change = OpportunityChange.objects.create(opportunity=duplicate_role, field="status", old_value="open", new_value="closed", stage="repair", observed_at=timezone.now())
    dismissal = PlayDismissal.all_objects.create(user=user, firm=lose, event_kind="app_close", date=date(2026, 9, 30))
    FirmCycleObservation.objects.create(firm=keep, region="us", opened_count=5)
    FirmCycleObservation.objects.create(firm=lose, region="us", opened_count=5)
    merge_firms(keep, lose)
    for row in (contact, task, proposal, event, dismissal):
        row.refresh_from_db()
        assert row.firm_id == keep.pk
    assert contact.region == "hk"
    assert event.opportunity_id == role.pk and event.evidence == "Original application evidence"
    assert event.firm_text == "Bank original mail name"
    change.refresh_from_db()
    assert change.opportunity_id == role.pk
    assert not FirmCycleObservation.objects.filter(firm=keep).exists()


def test_conflicting_mail_records_abort_the_entire_merge_without_data_loss():
    user, keep, lose = _world()
    role, duplicate_role = _role(keep), _role(lose)
    person = Contact.all_objects.create(user=user, name="Ada", firm=lose)
    for opp, state in ((role, "dismissed"), (duplicate_role, "accepted")):
        ApplicationEvent.all_objects.create(user=user, opportunity=opp, firm=opp.firm,
                                           event_type="applied", target_status="submitted", status=state)
    with pytest.raises(ValueError, match="need review"):
        merge_firms(keep, lose)
    assert Firm.objects.filter(pk=lose.pk).exists()
    assert Opportunity.objects.filter(pk=duplicate_role.pk).exists()
    assert ApplicationEvent.all_objects.filter(user=user).count() == 2
    person.refresh_from_db()
    assert person.firm_id == lose.pk


def test_merging_a_firm_with_itself_is_rejected_before_writes():
    _, firm, _ = _world()
    with pytest.raises(ValueError, match="different"):
        merge_firms(firm, firm)
    assert Firm.objects.filter(pk=firm.pk).exists()
