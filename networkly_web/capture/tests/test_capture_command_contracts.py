"""Exercise previously uncovered command entry points without real providers."""
from io import StringIO
import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError

from analytics.models import Import
from capture import autopilot
from capture.models import ContactProposal, AutopilotRun
from crm.models import Contact, Touch

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def user():
    return get_user_model().objects.create_user(email="command-contract@example.com")


def test_gmail_command_import_checkpoint_rolls_back_contact_touch(user, tmp_path):
    contact = Contact.all_objects.create(user=user, name="Alex", email="alex@bank.example")
    file = tmp_path / "findings.json"
    file.write_text(json.dumps([dict(found=True, name="Alex", email=contact.email, replied=True, thread_id="command-atomic")]))
    with patch.object(Import.all_objects, "create", side_effect=RuntimeError("ledger down")):
        with pytest.raises(RuntimeError, match="ledger down"):
            call_command("capture_gmail", email=user.email, findings=str(file), stdout=StringIO())
    assert not Touch.all_objects.filter(user=user).exists()
    call_command("capture_gmail", email=user.email, findings=str(file), stdout=StringIO())
    assert Touch.all_objects.filter(user=user).count() == 1
    assert Import.all_objects.filter(user=user, kind="gmail_findings").count() == 1
    output = StringIO()
    call_command("capture_gmail", email=user.email, window=True, stdout=output)
    assert output.getvalue().strip() == "2"


def test_gmail_command_rejects_nonobject_rows_before_writes(user, tmp_path):
    file = tmp_path / "bad.json"
    file.write_text('[null]')
    with pytest.raises(CommandError, match="array of objects"):
        call_command("capture_gmail", email=user.email, findings=str(file))
    assert not Import.all_objects.filter(user=user).exists()


def test_gmail_command_dry_run_writes_nothing(user, tmp_path):
    Contact.all_objects.create(user=user, name="Alex", email="alex@bank.example")
    file = tmp_path / "findings.json"
    file.write_text(json.dumps([dict(found=True, name="Alex", email="alex@bank.example", replied=True)]))
    out = StringIO()
    call_command("capture_gmail", email=user.email, findings=str(file), dry_run=True, stdout=out)
    assert "[dry-run]" in out.getvalue()
    assert not Touch.all_objects.filter(user=user).exists()
    assert not Import.all_objects.filter(user=user).exists()


def test_autopilot_command_dry_run_does_not_call_provider(user, settings):
    settings.ANTHROPIC_API_KEY = "fake-no-network"
    ContactProposal.all_objects.create(user=user, name="Alex", email="alex@bank.example", evidence_kind="outreach", evidence="Hello Alex")
    with patch.object(autopilot, "_post_json", side_effect=AssertionError("dry-run provider call")):
        call_command("capture_autopilot", email=user.email, dry_run=True, stdout=StringIO())
    assert not AutopilotRun.all_objects.filter(user=user).exists()
