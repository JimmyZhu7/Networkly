"""Automatic optional AI remains free, bounded and outside write locks."""
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection, transaction

from billing.models import CreditLedger
from capture import enrichment, gmail_live, mailfacts
from capture.models import GmailConnection
from directory import ai_extract

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def grant(settings):
    settings.ANTHROPIC_API_KEY = "fake-key-no-network"
    cache.clear()
    user = get_user_model().objects.create_user(email="enrichment@example.com")
    return GmailConnection.all_objects.create(user=user, gmail_address=user.email, refresh_token_encrypted="snapshot", history_id="1")


def finding():
    return dict(found=True, name="Recruiting", email="noreply@myworkday.com", subject="Your application: next steps", snippet="Our process has moved forward.", bulk=True)


def test_optional_provider_runs_before_grant_transaction_and_never_debits(grant):
    calls = []
    def classify(subject, snippet):
        calls.append(subject)
        assert not connection.in_atomic_block
        return ai_extract.ApplicationEventGuess("interview", snippet, .5)
    with patch.object(ai_extract, "extract_application_event_ai", classify):
        gmail_live.apply_grant_findings(grant, [finding()])
    assert len(calls) == 1
    assert not CreditLedger.all_objects.filter(user=grant.user).exists()


def test_provider_reconnect_cannot_apply_old_prepared_classification(grant):
    def classify(subject, snippet):
        GmailConnection.all_objects.filter(pk=grant.pk).update(refresh_token_encrypted="replacement")
        return ai_extract.ApplicationEventGuess("interview", snippet, .5)
    with patch.object(ai_extract, "extract_application_event_ai", classify):
        with pytest.raises(gmail_live.GmailLiveError, match="changed"):
            gmail_live.apply_grant_findings(grant, [finding()])


def test_hourly_cap_is_shared_across_repeated_preparations(grant, monkeypatch):
    monkeypatch.setattr(enrichment, "MAX_RESIDUE_THREADS", 2)
    with patch.object(ai_extract, "extract_application_event_ai", return_value=None) as provider:
        for _ in range(4):
            enrichment.prepare_findings(grant.user, [finding()])
    assert provider.call_count == 2


@pytest.mark.parametrize("kind", ["dry", "atomic", "busy", "cache"])
def test_optional_failure_modes_keep_deterministic_fallback_without_provider(grant, kind):
    @contextmanager
    def busy(_user_id):
        yield False
    with patch.object(ai_extract, "extract_application_event_ai", side_effect=AssertionError("unexpected provider")) as provider:
        if kind == "dry":
            prepared = enrichment.prepare_findings(grant.user, [finding()], dry_run=True)
        elif kind == "atomic":
            with transaction.atomic():
                prepared = enrichment.prepare_findings(grant.user, [finding()])
        elif kind == "busy":
            with patch.object(enrichment, "enrichment_lock", busy):
                prepared = enrichment.prepare_findings(grant.user, [finding()])
        else:
            with patch.object(enrichment, "window_exceeded", side_effect=RuntimeError("cache down")):
                prepared = enrichment.prepare_findings(grant.user, [finding()])
    assert provider.call_count == 0
    assert len(prepared) == 1


def test_prepared_auto_reply_does_not_call_provider_during_apply(grant):
    row = dict(found=True, name="Alex", email="alex@bank.example", subject="Auto reply", snippet="I am unavailable for a while.", auto_reply=True)
    with patch.object(mailfacts, "_detect_ai", return_value=[]) as classify:
        prepared = enrichment.prepare_findings(grant.user, [row])
    assert classify.call_count == 1
    with transaction.atomic(), patch.object(mailfacts, "_detect_ai", side_effect=AssertionError("provider in write phase")):
        from capture.gmail import apply_findings
        apply_findings(grant.user, [row], prepared=prepared)
