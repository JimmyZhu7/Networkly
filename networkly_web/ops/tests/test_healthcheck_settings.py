"""Every monitored job can load its own optional success heartbeat."""

import runpy
from importlib.util import find_spec

import environ
import pytest

from ops.tracking import EXPECTED_INTERVALS, _ping_healthcheck


@pytest.mark.parametrize("configured", [False, True])
def test_all_tracked_jobs_load_and_ping_only_their_configured_url(
    monkeypatch, settings, configured,
):
    # Evaluate settings without loading local credentials or mutating its module.
    monkeypatch.setattr(environ.Env, "read_env", lambda *args, **kwargs: None)
    expected = {}
    for name in EXPECTED_INTERVALS:
        key = "HEALTHCHECK_URL_" + name.upper().replace("-", "_")
        expected[name] = f"https://hc-ping.com/test-{name}" if configured else ""
        monkeypatch.delenv(key, raising=False)
        if configured:
            monkeypatch.setenv(key, expected[name])
    loaded = runpy.run_path(find_spec("networkly_web.settings.base").origin)
    assert loaded["HEALTHCHECK_URLS"] == expected
    settings.HEALTHCHECK_URLS = loaded["HEALTHCHECK_URLS"]
    calls = []
    monkeypatch.setattr("ops.tracking.requests.get", lambda url, timeout: calls.append((url, timeout)))
    for name in EXPECTED_INTERVALS:
        _ping_healthcheck(name)
    assert calls == ([(url, 5) for url in expected.values()] if configured else [])


def test_local_jobs_cannot_ping_production_and_leave_production_mapping_intact(
    monkeypatch, settings,
):
    from networkly_web.settings import base

    configured = {name: f"https://hc-ping.com/test-{name}" for name in EXPECTED_INTERVALS}
    monkeypatch.setattr(base, "HEALTHCHECK_URLS", configured)
    monkeypatch.setenv("DJANGO_SECRET_KEY", "test-only-not-production")
    monkeypatch.setenv("DJANGO_ALLOWED_HOSTS", "test.example.invalid")
    monkeypatch.setenv("SENTRY_DSN", "")
    local = runpy.run_path(
        find_spec("networkly_web.settings.local").origin,
        run_name="networkly_web.settings._heartbeat_test",
    )
    settings.HEALTHCHECK_URLS = local["HEALTHCHECK_URLS"]
    calls = []
    monkeypatch.setattr("ops.tracking.requests.get", lambda url, timeout: calls.append(url))
    for name in EXPECTED_INTERVALS:
        _ping_healthcheck(name)
    assert calls == []
    assert base.HEALTHCHECK_URLS == configured
    production = runpy.run_path(
        find_spec("networkly_web.settings.production").origin,
        run_name="networkly_web.settings._heartbeat_test",
    )
    assert production["HEALTHCHECK_URLS"] == configured
