from unittest.mock import patch

import pytest
from django.core.cache import cache

from assistant.locks import AccountGenerationLock
from crm import ai_summary
from crm.models import Contact, Touch
from crm.tests.test_ai_summary import _history, contact, firm, user, REAL_SUMMARY

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def configured():
    cache.clear()
    with patch.object(ai_summary, "is_configured", return_value=True):
        yield
    cache.clear()


def test_another_generation_in_same_account_prevents_parallel_provider_spend(user, contact):
    _history(user, contact)
    with AccountGenerationLock(user.pk) as owner, patch.object(ai_summary, "complete_text") as provider:
        assert owner.acquired
        assert ai_summary.regenerate(contact) is None
        provider.assert_not_called()
    with patch.object(ai_summary, "complete_text", return_value=REAL_SUMMARY):
        assert ai_summary.regenerate(contact) == REAL_SUMMARY


def test_free_summary_attempts_are_bounded_per_account(user, contact):
    _history(user, contact)
    with patch.object(ai_summary, "complete_text", return_value=REAL_SUMMARY) as provider:
        for _ in range(ai_summary.MAX_GENERATIONS_PER_HOUR):
            assert ai_summary.regenerate(contact) == REAL_SUMMARY
        assert ai_summary.regenerate(contact) is None
        assert provider.call_count == ai_summary.MAX_GENERATIONS_PER_HOUR


def test_account_deactivation_during_generation_leaves_existing_summary(user, contact):
    _history(user, contact)
    Contact.all_objects.filter(pk=contact.pk).update(ai_summary="Keep me")
    def complete(*args, **kwargs):
        type(user).objects.filter(pk=user.pk).update(is_active=False)
        return REAL_SUMMARY
    with patch.object(ai_summary, "complete_text", side_effect=complete):
        assert ai_summary.regenerate(contact) is None
    contact.refresh_from_db()
    assert contact.ai_summary == "Keep me"


def test_contact_deletion_during_generation_is_a_safe_no_op(user, contact):
    _history(user, contact)
    pk = contact.pk
    def complete(*args, **kwargs):
        Contact.all_objects.filter(pk=pk).delete()
        return REAL_SUMMARY
    with patch.object(ai_summary, "complete_text", side_effect=complete):
        assert ai_summary.regenerate(contact) is None
    assert not Contact.all_objects.filter(pk=pk).exists()


def test_newer_summary_from_another_writer_cannot_be_replaced(user, contact):
    from django.utils import timezone
    _history(user, contact)
    def complete(*args, **kwargs):
        Contact.all_objects.filter(pk=contact.pk).update(ai_summary="Newer", ai_summary_generated_at=timezone.now())
        return REAL_SUMMARY
    with patch.object(ai_summary, "complete_text", side_effect=complete):
        assert ai_summary.regenerate(contact) is None
    contact.refresh_from_db()
    assert contact.ai_summary == "Newer"


def test_inconsistent_foreign_touch_cannot_enter_summary_prompt(user, contact):
    from django.utils import timezone

    _history(user, contact)
    other = type(user).objects.create_user(email="summary-foreign@example.test")
    Touch.all_objects.create(user=other, contact=contact, kind="reply_received",
                             ts=timezone.now(), note="Other account private text")
    with patch.object(ai_summary, "complete_text", return_value=REAL_SUMMARY) as provider:
        assert ai_summary.regenerate(contact) == REAL_SUMMARY
    assert "Other account private text" not in provider.call_args.args[0]
