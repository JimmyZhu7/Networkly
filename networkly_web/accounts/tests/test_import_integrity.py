"""Uploads must fail atomically and repeated requests must not duplicate people."""
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from django.db import connections

from accounts import services
from accounts.models import User
from analytics.models import Import
from crm.models import Contact


@pytest.mark.django_db
@pytest.mark.parametrize("text", [
    'name,email\nValid,valid@example.com\n"unfinished',
    'name,notes\nValid,ok\nInvalid,"' + ('x' * 140000) + '"',
    'name,notes\nValid,ok\nInvalid,bad\x00text',
    'name,linkedin\nValid,https://linkedin.com/in/valid\nUnsafe,javascript:alert(1)',
])
def test_invalid_file_is_a_useful_error_without_partial_contacts(text):
    user = User.objects.create_user(email="csv@example.com")
    result = services.parse_contacts_csv(user, text)
    assert result.errors and result.created == 0
    assert not Contact.objects.for_user(user).exists()


@pytest.mark.django_db
def test_import_bookkeeping_failure_rolls_back_contacts():
    user = User.objects.create_user(email="csv@example.com")
    with patch.object(Import.all_objects, "create", side_effect=RuntimeError("write failed")):
        with pytest.raises(RuntimeError):
            services.import_contacts(user, file_bytes=b"name,email\nValid,valid@example.com", filename="contacts.csv")
    assert not Contact.objects.for_user(user).exists()


@pytest.mark.django_db
def test_row_limit_does_not_silently_import_a_partial_file(monkeypatch):
    user = User.objects.create_user(email="csv@example.com")
    monkeypatch.setattr(services, "MAX_CONTACT_IMPORT_ROWS", 1)
    result = services.parse_contacts_csv(user, "name,email\nFirst,a@example.com\nSecond,b@example.com")
    assert result.errors and not Contact.objects.for_user(user).exists()


@pytest.mark.django_db(transaction=True)
def test_simultaneous_imports_create_one_contact_per_person():
    user = User.objects.create_user(email="csv-race@example.com")
    barrier = threading.Barrier(2)

    def run_import():
        try:
            barrier.wait(timeout=10)
            return services.parse_contacts_csv(user, "name,email\nSame Person,same@example.com").created
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run_import) for _ in range(2)]
        counts = [future.result(timeout=15) for future in futures]
    assert sorted(counts) == [0, 1]
    assert Contact.objects.for_user(user).count() == 1
