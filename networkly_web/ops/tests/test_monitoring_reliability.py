import logging
from unittest.mock import Mock

import pytest
import requests
from django.db import DatabaseError
from django.utils import timezone

from ops.models import JobRun
from ops.tracking import track_job_run

pytestmark = pytest.mark.django_db


def test_failure_recording_preserves_original_error(monkeypatch, caplog):
    original = ValueError("original job failure")
    with caplog.at_level(logging.ERROR):
        with pytest.raises(ValueError) as caught:
            with track_job_run("scrape") as run:
                monkeypatch.setattr(run, "save", Mock(side_effect=DatabaseError("private database detail")))
                raise original
    assert caught.value is original
    assert "could not record failure" in caplog.text
    assert "private database detail" not in caplog.text


def test_rejected_ping_is_visible_without_marking_successful_job_failed(settings, monkeypatch, caplog):
    secret_url = "https://hc-ping.com/private-credential"
    settings.HEALTHCHECK_URLS = {"scrape": secret_url}
    response = Mock()
    response.raise_for_status.side_effect = requests.HTTPError(secret_url)
    monkeypatch.setattr("ops.tracking.requests.get", Mock(return_value=response))
    with caplog.at_level(logging.WARNING):
        with track_job_run("scrape") as run:
            pass
    run.refresh_from_db()
    assert run.status == JobRun.STATUS_SUCCESS
    assert "healthcheck ping failed" in caplog.text
    assert secret_url not in caplog.text


def test_health_ignores_incomplete_success_records(client, django_user_model):
    staff = django_user_model.objects.create_user(email="monitor@example.com", password="x", is_staff=True)
    client.force_login(staff)
    now = timezone.now()
    valid = JobRun.objects.create(name="scrape", status="success", started_at=now, finished_at=now)
    JobRun.objects.create(name="scrape", status="success", started_at=now)
    response = client.get("/ops/health/cron/")
    assert response.status_code == 200
    scrape = next(row for row in response.json()["jobs"] if row["name"] == "scrape")
    assert scrape["status"] == "ok"
    assert scrape["last_success"] == valid.finished_at.isoformat()


@pytest.mark.parametrize(("patterns", "status"), [
    (["^not-healthz$"], "FAIL"),
    (["^health[z]$"], "PASS"),
    (["["], "FAIL"),
    (["^healthz$", "["], "FAIL"),
])
def test_preflight_matches_actual_health_path(settings, patterns, status):
    from ops.management.commands.deploy_preflight import Command
    settings.SECURE_SSL_REDIRECT = True
    settings.SECURE_REDIRECT_EXEMPT = patterns
    assert Command()._healthz_exempt().level == status
