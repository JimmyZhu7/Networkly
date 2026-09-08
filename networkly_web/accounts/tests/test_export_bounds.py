"""Individual downloads and polymorphic score histories stay bounded and private."""
import csv
import io
import tracemalloc

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts import services
from accounts.models import User
from analytics.models import FitScore
from crm.models import Contact, Touch
from directory.models import Firm


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["contacts", "touches"])
def test_individual_download_preserves_csv_bytes_and_closes_on_disconnect(client, kind, monkeypatch):
    user = User.objects.create_user(email="csv-file@example.test")
    other = User.objects.create_user(email="csv-other@example.test")
    person = Contact.all_objects.create(user=user, name="王 Example", notes="=danger,\"quoted\"\nNext line")
    stranger = Contact.all_objects.create(user=other, name="Foreign Private Person")
    Touch.all_objects.create(user=user, contact=person, ts=timezone.now(), note="\t=SUM(A1)")
    Touch.all_objects.create(user=other, contact=stranger, ts=timezone.now(), note="Foreign Private Note")
    builder = services.contacts_csv if kind == "contacts" else services.touches_csv
    expected = builder(user).encode("utf-8")
    created = []
    build_file = services.export_csv_file

    def tracked_file(*args, **kwargs):
        output = build_file(*args, **kwargs)
        created.append(output)
        return output

    monkeypatch.setattr(services, "export_csv_file", tracked_file)
    client.force_login(user)
    response = client.get(reverse("accounts:export"), {"kind": kind})
    assert response.status_code == 200 and response.streaming
    assert response["Content-Type"].startswith("text/csv")
    assert b"".join(response.streaming_content) == expected
    assert b"Foreign Private" not in expected

    interrupted = client.get(reverse("accounts:export"), {"kind": kind})
    output = created[-1]
    assert not output.closed
    interrupted.close()
    assert output.closed


def test_csv_file_closes_its_temporary_file_when_builder_fails(monkeypatch):
    created = []
    factory = services.SpooledTemporaryFile

    def spool(*args, **kwargs):
        result = factory(*args, **kwargs)
        created.append(result)
        return result

    def broken(user, *, _destination=None):
        _destination.write("partial output")
        raise RuntimeError("builder failed")

    monkeypatch.setattr(services, "SpooledTemporaryFile", spool)
    with pytest.raises(RuntimeError, match="builder failed"):
        services.export_csv_file(None, broken)
    assert len(created) == 1 and created[0].closed


def test_csv_closes_row_generator_after_output_failure():
    released = []

    def rows():
        try:
            yield ["one"]
            yield ["two"]
        finally:
            released.append(True)

    class FailingDestination:
        def write(self, value):
            if "one" in value:
                raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        services._csv(["name"], rows(), _destination=FailingDestination())
    assert released == [True]


@pytest.mark.django_db
def test_large_fit_score_export_preserves_all_scores_with_bounded_memory_and_queries():
    user = User.objects.create_user(email="scores-large@example.test")
    other = User.objects.create_user(email="scores-other@example.test")
    person = Contact.all_objects.create(user=user, name="Owned Person")
    foreign = Contact.all_objects.create(user=other, name="Foreign Private Name")
    firm = Firm.objects.create(name="Shared Bank", slug="scores-shared")
    total = 2200
    # A full list of these reasoning bodies alone exceeds 34 MiB. Batching
    # must still export every body, including subjects on later batches.
    reason = "x" * 16384
    for start in range(0, total, 200):
        FitScore.all_objects.bulk_create([
            FitScore(user=user, subject_type="contact", subject_id=person.pk,
                     reasoning=reason, composite=i) for i in range(start, min(start + 200, total))
        ])
    FitScore.all_objects.bulk_create([
        FitScore(user=user, subject_type="firm", subject_id=firm.pk, reasoning="Shared subject"),
        FitScore(user=user, subject_type="contact", subject_id=foreign.pk, reasoning="Unresolvable subject"),
        FitScore(user=other, subject_type="contact", subject_id=foreign.pk, reasoning="Private score"),
    ])
    tracemalloc.start()
    try:
        with CaptureQueriesContext(connection) as queries:
            output = services.export_csv_file(user, services.fit_scores_csv)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    with output:
        assert output._rolled
        assert peak < 28 * 1024 * 1024
        # At most one scoring query and two subject lookups per batch.
        assert len(queries) <= 1 + 2 * 5
        with io.TextIOWrapper(output, encoding="utf-8", newline="") as text:
            rows = csv.DictReader(text)
            count = 0
            subjects = set()
            for row in rows:
                count += 1
                subjects.add(row["subject"])
                assert row["reasoning"] != "Private score"
                if row["subject"] == "Owned Person":
                    assert row["reasoning"] == reason
            assert count == total + 2
            assert subjects == {"Owned Person", "Shared Bank", str(foreign.pk)}
