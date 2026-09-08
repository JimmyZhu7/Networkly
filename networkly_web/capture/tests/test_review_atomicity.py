"""Fault injection and stale-card regression tests for local review writes."""
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection

from capture import autopilot, discovery
from capture.models import ContactProposal, AutopilotRun, AutopilotDecision
from crm.models import Contact, Touch

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def proposal():
    user = get_user_model().objects.create_user(email="atomic-review@example.com")
    return ContactProposal.all_objects.create(
        user=user, name="Alex", email="alex@bank.example", evidence_kind="outreach",
        evidence="Subject: coffee chat", thread_id="atomic-review", thread_subject="Coffee chat",
    )


def test_accept_failure_after_touch_rolls_back_contact_and_provenance(proposal):
    stale = ContactProposal.all_objects.get(pk=proposal.pk)
    with patch.object(discovery, "_resolve", side_effect=RuntimeError("resolution failed")):
        with pytest.raises(RuntimeError, match="resolution failed"):
            discovery.accept(proposal)
    assert not Contact.all_objects.filter(user=proposal.user).exists()
    assert not Touch.all_objects.filter(user=proposal.user).exists()
    assert ContactProposal.all_objects.get(pk=proposal.pk).status == "pending"
    first = discovery.accept(stale)
    second = discovery.accept(proposal)
    assert first.pk == second.pk
    assert Touch.all_objects.filter(user=proposal.user).count() == 1


def test_concurrent_accepts_produce_one_contact_and_one_touch(proposal):
    def accept():
        close_old_connections()
        try:
            row = ContactProposal.all_objects.get(pk=proposal.pk)
            return discovery.accept(row).pk
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: accept(), range(2)))
    assert results[0] == results[1]
    assert Contact.all_objects.filter(user=proposal.user).count() == 1
    assert Touch.all_objects.filter(user=proposal.user).count() == 1


def test_stale_dismiss_does_not_overwrite_accept(proposal):
    stale = ContactProposal.all_objects.get(pk=proposal.pk)
    discovery.accept(proposal)
    discovery.dismiss(stale)
    assert ContactProposal.all_objects.get(pk=proposal.pk).status == "accepted"


def test_inactive_owner_cannot_accept_cached_card(proposal):
    get_user_model().objects.filter(pk=proposal.user_id).update(is_active=False)
    assert discovery.accept(proposal) is None
    assert not Contact.all_objects.filter(user_id=proposal.user_id).exists()


def test_decision_marker_failure_rolls_back_complete_accept(proposal):
    run = AutopilotRun.all_objects.create(user=proposal.user, status="reviewed")
    decision = AutopilotDecision.all_objects.create(user=proposal.user, run=run, proposal=proposal, decision="accept")
    original = AutopilotDecision.save
    def fail_marker(self, *args, **kwargs):
        if self.status == "applied":
            raise RuntimeError("marker failed")
        return original(self, *args, **kwargs)
    with patch.object(AutopilotDecision, "save", fail_marker):
        with pytest.raises(RuntimeError, match="marker failed"):
            autopilot.apply_run(run)
    assert not Contact.all_objects.filter(user=proposal.user).exists()
    assert not Touch.all_objects.filter(user=proposal.user).exists()
    proposal.refresh_from_db()
    decision.refresh_from_db()
    assert proposal.status == "pending" and decision.status == "proposed"
    assert autopilot.apply_run(run) == (autopilot.APPLIED, 1)


def test_foreign_or_finished_run_cannot_make_provider_calls(proposal):
    other = get_user_model().objects.create_user(email="other-review@example.com")
    run = AutopilotRun.all_objects.create(user=other, status="running")
    decide = lambda *_args, **_kwargs: pytest.fail("provider must not be called")
    result = autopilot.run_autopilot(proposal.user, run=run, decide=decide)
    assert not result.ok and result.reason == "invalid_run"


def test_run_deleted_during_provider_does_not_recreate_rows_or_crash(proposal):
    run = AutopilotRun.all_objects.create(user=proposal.user, status="running")
    def decide(text, **kwargs):
        assert not connection.in_atomic_block
        AutopilotRun.all_objects.filter(pk=run.pk).delete()
        return "accept", .95, text.splitlines()[0], "evidence"
    result = autopilot.execute_run(run, decide=decide)
    assert not result.ok
    assert not AutopilotRun.all_objects.filter(pk=run.pk).exists()
    assert not AutopilotDecision.all_objects.filter(user=proposal.user).exists()


def test_undo_application_does_not_erase_later_manual_progress(proposal):
    from analytics.models import UserOpportunity
    from capture.models import ApplicationEvent
    from directory.models import Firm, Opportunity
    firm = Firm.objects.create(name="Atomic Bank", slug="atomic-bank")
    opportunity = Opportunity.objects.create(firm=firm, title="Analyst", url="https://bank.example/analyst", source="manual")
    event = ApplicationEvent.all_objects.create(user=proposal.user, firm=firm, opportunity=opportunity, event_type="applied", target_status="applied")
    run = AutopilotRun.all_objects.create(user=proposal.user, status="reviewed")
    decision = AutopilotDecision.all_objects.create(user=proposal.user, run=run, app_event=event, decision="accept")
    autopilot.apply_run(run)
    row = UserOpportunity.all_objects.get(user=proposal.user, opportunity=opportunity)
    row.applied_status = "interviewing"
    row.save(update_fields=["applied_status"])
    decision.refresh_from_db()
    assert autopilot.undo_decision(decision) == autopilot.UNDONE
    row.refresh_from_db()
    assert row.applied_status == "interviewing"
