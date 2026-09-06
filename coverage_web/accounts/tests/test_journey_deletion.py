"""Journey 8: taking your data with you, and taking your account away.

The one mock is named here: `capture.google_revoke.revoke_all_for_user`, which
account deletion calls before anything else and which really does reach out to
Google. Everything else runs — the ZIP is built for real, the rows are really
deleted, the avatar file is really removed on commit, and the seat is really
left consumed.

`test_export.py` and `test_delete_receipt.py` cover the export's contents and
the receipt's wording. What is new here is the WALK: sign in, download all
three shapes, confirm the download holds nobody else's rows, then delete and
check the four things the delete page promises actually happened — the rows,
the uploaded file, the connected mailbox and calendar, and the sessions.
"""

from __future__ import annotations

import csv
import io
import zipfile

import pytest
from django.contrib.sessions.models import Session
from django.test import Client
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from accounts import beta
from accounts.models import BetaInvitation, User
from crm.models import Contact, Touch
from directory.models import Firm

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_google_calls(monkeypatch):
    """Deletion revokes the account's Google grants. Not from a test."""
    calls = []
    monkeypatch.setattr("capture.google_revoke.revoke_all_for_user", calls.append)
    return calls


@pytest.fixture
def firm():
    return Firm.objects.create(name="Journey Partners", slug="journey-partners")


def _student(email, firm, name):
    user = User.objects.create_user(email=email, password="A-safe-passphrase-123")
    contact = Contact.all_objects.create(user=user, name=name, firm=firm, source="manual")
    Touch.all_objects.create(user=user, contact=contact, kind="outreach",
                             channel="email", ts=timezone.now())
    return user, contact


@pytest.fixture
def student(firm):
    return _student("leaver@example.com", firm, "Dana Banker")


@pytest.fixture
def stranger(firm):
    return _student("stayer@example.com", firm, "Kim Stranger")


@pytest.fixture
def signed_in(client, student):
    client.force_login(student[0])
    return client


def _rows(archive, name):
    with archive.open(name) as handle:
        return list(csv.DictReader(io.TextIOWrapper(handle, "utf-8")))


# ---------------------------------------------------------------------------
# Export


def test_the_export_page_offers_all_three_downloads_and_they_all_work(signed_in, student):
    page = signed_in.get(reverse("accounts:export"))
    assert page.status_code == 200
    assert page.context["contact_count"] == 1

    zip_response = signed_in.get(reverse("accounts:export"), {"kind": "all"})
    assert zip_response.status_code == 200
    assert zip_response["Content-Type"] == "application/zip"
    assert "networkly-data.zip" in zip_response["Content-Disposition"]
    archive = zipfile.ZipFile(io.BytesIO(zip_response.content))
    assert archive.testzip() is None
    assert "README.txt" in archive.namelist()

    for kind, filename in [("contacts", "networkly-contacts.csv"),
                           ("touches", "networkly-touches.csv")]:
        response = signed_in.get(reverse("accounts:export"), {"kind": kind})
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/csv")
        assert filename in response["Content-Disposition"]


def test_the_export_carries_this_account_and_nobody_else(signed_in, student, stranger):
    zip_response = signed_in.get(reverse("accounts:export"), {"kind": "all"})
    archive = zipfile.ZipFile(io.BytesIO(zip_response.content))

    names = {row["name"] for row in _rows(archive, "contacts.csv")}
    assert names == {"Dana Banker"}
    assert "Kim Stranger" not in zip_response.content.decode("utf-8", "replace")

    contacts_csv = signed_in.get(reverse("accounts:export"), {"kind": "contacts"}).content.decode()
    assert "Dana Banker" in contacts_csv and "Kim Stranger" not in contacts_csv


def test_the_export_is_private(client):
    for kind in (None, "all", "contacts", "touches"):
        response = client.get(reverse("accounts:export"), {"kind": kind} if kind else {})
        assert response.status_code == 302


# ---------------------------------------------------------------------------
# Deletion


def test_the_confirm_page_names_every_kind_of_thing_deletion_removes(signed_in):
    """A confirm page for an irreversible action has one job: say what goes.

    It named five categories while `_DELETE_ORDER` swept thirty-odd tables,
    and the omissions were the ones a reader would most want confirmed — the
    connected Google account, the assistant conversations, the uploaded photo.
    """
    body = signed_in.get(reverse("accounts:delete")).content.decode().lower()

    for promised in ["photo", "contacts", "target firms", "calendar events",
                     "fit scores", "imports", "assistant conversations",
                     "credit history", "google", "notification"]:
        assert promised in body, f"the delete page never mentions {promised}"
    assert "no undo" in body
    assert "exporting your data" in body


def test_the_wrong_confirmation_deletes_nothing(signed_in, student, no_google_calls):
    user, _ = student

    response = signed_in.post(reverse("accounts:delete"), {"confirm": "delete my account"})

    assert response.status_code == 200
    assert "didn&#x27;t match" in response.content.decode()
    assert User.objects.filter(pk=user.pk).exists()
    assert Contact.objects.for_user(user).exists()
    assert no_google_calls == []


def test_deleting_removes_the_account_its_rows_its_upload_and_its_sessions(
    client, settings, tmp_path, django_capture_on_commit_callbacks,
    student, stranger, no_google_calls,
):
    settings.MEDIA_ROOT = tmp_path
    user, _ = student
    other, _ = stranger
    user.avatar.save("leaver.png", ContentFile(b"synthetic png bytes"), save=True)
    avatar_name = user.avatar.name

    # Three separate browsers, because one test client only ever holds one
    # session: a phone and a laptop signed in as this account, and somebody
    # else's browser, so "its sessions" can be told apart from "all sessions".
    phone = Client()
    phone.force_login(user)
    elsewhere = Client()
    elsewhere.force_login(other)
    client.force_login(user)
    keys = [phone.session.session_key, elsewhere.session.session_key,
            client.session.session_key]
    assert Session.objects.filter(session_key__in=keys).count() == 3
    phone_key, other_key, laptop_key = keys

    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(reverse("accounts:delete"), {"confirm": "LEAVER@example.com"},
                               follow=True)

    assert response.status_code == 200
    assert not User.objects.filter(pk=user.pk).exists()
    assert not Contact.all_objects.filter(user_id=user.pk).exists()
    assert not Touch.all_objects.filter(user_id=user.pk).exists()
    assert not (tmp_path / avatar_name).exists(), "the uploaded file went with the account"
    # By email, not pk: `user.delete()` nulls the pk on the very instance the
    # request was carrying, which is the object the spy recorded.
    assert [u.email for u in no_google_calls] == ["leaver@example.com"], (
        "the Google grants were revoked, once"
    )
    # The receipt says what was removed rather than a bare success.
    assert "Deleted" in response.content.decode()

    # The other browser signed in as the deleted account cannot get back in,
    # and the stranger's session is untouched.
    assert phone.get(reverse("accounts:settings")).status_code == 302
    assert not Session.objects.filter(session_key=laptop_key).exists(), (
        "the session that asked was flushed"
    )
    assert elsewhere.get(reverse("accounts:settings")).status_code == 200
    assert Session.objects.filter(session_key=other_key).exists()
    assert User.objects.filter(pk=other.pk).exists()
    assert Contact.objects.for_user(other).count() == 1


def test_a_deleted_account_keeps_its_beta_seat_consumed(client, settings, student, stranger):
    settings.BETA_ENABLED = True
    settings.BETA_MAX_USERS = 2
    user, _ = student
    beta.invite_emails([user.email])
    before = beta.capacity_status()
    assert before["used"] == 2 and before["remaining"] == 0

    client.force_login(user)
    assert client.post(reverse("accounts:delete"), {"confirm": user.email}).status_code == 302

    assert not User.objects.filter(pk=user.pk).exists()
    seat = BetaInvitation.objects.get(email_fingerprint=beta.email_fingerprint("leaver@example.com"))
    assert seat.email == "" and seat.user_id is None and seat.redeemed_at is not None
    assert beta.capacity_status()["remaining"] == 0, "the seat is not handed back"


def test_signing_out_other_devices_spares_the_one_asking(client, student, stranger):
    user, _ = student
    other, _ = stranger
    phone = Client()
    phone.force_login(user)
    elsewhere = Client()
    elsewhere.force_login(other)
    client.force_login(user)
    phone_key = phone.session.session_key
    current_key = client.session.session_key

    confirm = client.get(reverse("accounts:signout_all"))
    assert confirm.status_code == 200
    assert Session.objects.filter(session_key=phone_key).exists(), "the GET changes nothing"

    response = client.post(reverse("accounts:signout_all"))

    assert response.status_code == 302
    assert not Session.objects.filter(session_key=phone_key).exists()
    assert Session.objects.filter(session_key=current_key).exists()
    assert phone.get(reverse("accounts:settings")).status_code == 302
    # The stranger stays signed in, and so does the device that asked.
    assert elsewhere.get(reverse("accounts:settings")).status_code == 200
    assert client.get(reverse("accounts:settings")).status_code == 200


def test_the_deletion_routes_are_private(client, student):
    user, _ = student
    assert client.get(reverse("accounts:delete")).status_code == 302
    assert client.post(reverse("accounts:delete"), {"confirm": user.email}).status_code == 302
    assert client.post(reverse("accounts:signout_all")).status_code == 302
    assert User.objects.filter(pk=user.pk).exists()
