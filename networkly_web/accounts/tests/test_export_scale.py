"""Large archives use bounded buffers and new credit records stay portable."""
import csv
import io
import random
import tracemalloc
import zipfile
from datetime import timedelta

import pytest
from django.utils import timezone

from accounts import services
from accounts.models import User
from billing.models import AIJobReservation, CreditLedger


def test_large_archive_spools_without_accumulating_csv_text(monkeypatch):
    def large_csv(user, *, _destination=None):
        rng = random.Random(42)
        return services._csv(["row", "text"],
            ([i, rng.randbytes(128).hex()] for i in range(20000)), _destination=_destination)

    monkeypatch.setattr(services, "EXPORT_FILES", [("large.csv", large_csv, "Fixture")])
    tracemalloc.start()
    try:
        archive = services.export_zip_file(None)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    with archive:
        assert archive._rolled
        assert peak < 8 * 1024 * 1024
        with zipfile.ZipFile(archive) as zf:
            with zf.open("large.csv") as member:
                rows = csv.reader(io.TextIOWrapper(member))
                assert next(rows) == ["row", "text"]
                assert sum(1 for _ in rows) == 20000


@pytest.mark.django_db
def test_new_ai_budgets_are_exported_and_deleted_only_for_their_owner():
    user = User.objects.create_user(email="jobs-owner@example.com")
    other = User.objects.create_user(email="jobs-other@example.com")
    jobs = []
    for owner in (user, other):
        debit = CreditLedger.all_objects.create(user=owner, kind="brief", delta=-1)
        jobs.append(AIJobReservation.all_objects.create(
            user=owner, debit=debit, kind="brief", job_key="attempt", allowed_units=1,
            units_per_credit=1, reserved_credits=1, expires_at=timezone.now()+timedelta(minutes=10),
        ))
    text = services.ai_jobs_csv(user)
    assert str(jobs[0].pk) in text
    assert str(jobs[1].pk) not in text
    counts = services.delete_user_and_data(user)
    assert counts["ai_jobs"] == 1
    assert not AIJobReservation.all_objects.filter(pk=jobs[0].pk).exists()
    assert AIJobReservation.objects.for_user(other).filter(pk=jobs[1].pk).exists()
