"""Real transaction, reconnect and process-death tests; no live providers."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path
from unittest.mock import MagicMock, patch
import os
import subprocess
import sys

import pytest
from django.contrib.auth import get_user_model
from django.db import connection as db, connections, transaction
from django.utils import timezone

from capture import gmail, gmail_live
from capture.models import GmailConnection
from crm import services
from crm.models import Contact, Touch

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def mailbox():
    user = get_user_model().objects.create_user(email="atomic-mail@example.test", password=None)
    grant = GmailConnection.all_objects.create(
        user=user, gmail_address=user.email, refresh_token_encrypted="original",
        history_id="100", backfill_status="pending", rescan_status="pending",
    )
    contact = Contact.all_objects.create(user=user, name="Jane Banker", email="jane@bank.test")
    return grant, contact


def finding():
    return {"found": True, "name": "Jane Banker", "email": "jane@bank.test",
            "replied": True, "thread_id": "atomic-thread", "evidence": "A reply"}


def assert_unapplied(grant, contact):
    grant.refresh_from_db()
    contact.refresh_from_db()
    assert grant.history_id == "100"
    assert contact.warmth == "cold"
    assert not Touch.all_objects.filter(user=grant.user).exists()


@pytest.mark.parametrize("boundary", ["_stamp_subject", "_record"])
def test_failed_post_touch_write_rolls_back_everything(mailbox, boundary):
    grant, contact = mailbox
    with patch.object(gmail, boundary, side_effect=RuntimeError("fault after domain write")):
        with pytest.raises(RuntimeError, match="fault after"):
            gmail_live.apply_grant_findings(grant, [finding()])
    assert_unapplied(grant, contact)
    gmail_live.apply_grant_findings(grant, [finding()])
    gmail_live.apply_grant_findings(grant, [finding()])
    assert Touch.all_objects.filter(user=grant.user).count() == 1


def test_failed_live_checkpoint_rolls_back_touch_and_contact(mailbox):
    grant, contact = mailbox
    from django.db.models.query import QuerySet
    original_update = QuerySet.update

    def update(query, **fields):
        if query.model is GmailConnection and "last_notification_at" in fields:
            raise RuntimeError("checkpoint fault")
        return original_update(query, **fields)

    with patch.object(gmail_live, "_gmail_client", return_value=MagicMock()), \
            patch.object(gmail_live, "_list_new_messages", return_value=(["m"], "200")), \
            patch.object(gmail_live, "_fetch_message", return_value={}), \
            patch.object(gmail_live, "classify_message_findings", return_value=[finding()]), \
            patch.object(QuerySet, "update", update):
        with pytest.raises(RuntimeError, match="checkpoint fault"):
            gmail_live.sync_connection(grant)
    assert_unapplied(grant, contact)


def test_failed_enrichment_savepoint_does_not_poison_primary_sync(mailbox):
    grant, contact = mailbox

    def bad_hook(*args, **kwargs):
        Contact.all_objects.filter(pk=contact.pk).update(notes="partial hook")
        # A real DB error, rather than only a Python exception.
        with db.cursor() as cursor:
            cursor.execute("SELECT 1 / 0")

    with patch.object(gmail.mailfacts, "consider_finding", bad_hook):
        result = gmail_live.apply_grant_findings(grant, [finding()])
    contact.refresh_from_db()
    assert result.mail_facts_errors == 1
    assert result.touches_logged == 1
    assert contact.notes == ""


def test_domain_savepoint_failure_leaves_outer_transaction_usable(mailbox):
    grant, contact = mailbox
    with services.atomic_pipeline():
        Contact.all_objects.filter(pk=contact.pk).update(notes="before")
        with pytest.raises(Exception):
            services.log_touch(grant.user_id, -1, "reply_received", "email")
        Contact.all_objects.filter(pk=contact.pk).update(notes="after")
    contact.refresh_from_db()
    assert contact.notes == "after"


def test_replaced_grant_cannot_apply_or_mark_backfill_done(mailbox):
    grant, contact = mailbox
    provider = MagicMock()

    def fetched(*args):
        GmailConnection.all_objects.filter(pk=grant.pk).update(refresh_token_encrypted="replacement")
        return {}

    provider.users.return_value.messages.return_value.list.return_value.execute.return_value = {"messages": [{"id": "m"}]}
    with patch.object(gmail_live, "_gmail_client", return_value=provider), \
            patch.object(gmail_live, "_fetch_message", fetched):
        with pytest.raises(gmail_live.GmailLiveError, match="changed during sync"):
            gmail_live.backfill_connection(grant)
    assert_unapplied(grant, contact)
    assert grant.refresh_token_encrypted == "replacement"
    assert grant.backfill_status == "pending"


@pytest.mark.parametrize("action", ["reconnect", "deactivate"])
def test_other_writer_serializes_after_complete_application(mailbox, action):
    grant, contact = mailbox
    attempted = Event()
    committed = Event()

    def other_writer():
        connections.close_all()
        try:
            attempted.set()
            if action == "reconnect":
                GmailConnection.all_objects.filter(pk=grant.pk).update(refresh_token_encrypted="replacement")
            else:
                get_user_model().objects.filter(pk=grant.user_id).update(is_active=False)
            committed.set()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with gmail_live.application_transaction(grant):
            pending = pool.submit(other_writer)
            assert attempted.wait(5)
            assert not committed.wait(0.15)
            gmail.apply_findings(grant.user, [finding()])
        pending.result(timeout=5)
    assert committed.is_set()
    assert Touch.all_objects.filter(user_id=grant.user_id).count() == 1
    with pytest.raises(gmail_live.GmailLiveError):
        gmail_live.apply_grant_findings(grant, [finding()])


@pytest.mark.parametrize("boundary", ["_stamp_subject", "_record"])
def test_worker_exit_after_domain_write_rolls_back_uncommitted_batch(mailbox, boundary):
    grant, contact = mailbox
    params = db.settings_dict
    assert params["NAME"].startswith("test_")
    from urllib.parse import quote
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    env["DJANGO_SETTINGS_MODULE"] = "networkly_web.settings.local"
    env["DATABASE_URL"] = (
        f"postgresql://{quote(params['USER'])}:{quote(params['PASSWORD'])}@"
        f"{params['HOST'] or 'localhost'}:{params['PORT'] or 5432}/{params['NAME']}"
    )
    script = """
import django, os, sys
django.setup()
from capture import gmail, gmail_live
from capture.models import GmailConnection
grant = GmailConnection.all_objects.select_related('user').get(pk=int(sys.argv[1]))
setattr(gmail, sys.argv[2], lambda *a, **k: os._exit(73))
gmail_live.apply_grant_findings(grant, [{'found': True, 'name': 'Jane Banker', 'email': 'jane@bank.test', 'replied': True, 'thread_id': 'atomic-thread'}])
"""
    result = subprocess.run([sys.executable, "-c", script, str(grant.pk), boundary], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
    assert result.returncode == 73, result.stderr.decode()[-1000:]
    assert_unapplied(grant, contact)
