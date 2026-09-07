"""A failed heartbeat ping must not write the ping URL into the log stream.

The healthchecks.io ping UUID is the credential (anyone holding it can mark
the job successful). `requests` puts the full URL into its exception message,
and `logger.exception` would have written that traceback to the host's logs
on every DNS blip. Sentry is scrubbed; the log stream is not.
"""
from __future__ import annotations

import logging

import requests

from ops import tracking


def test_a_request_failure_logs_the_job_name_and_not_the_url(settings, monkeypatch, caplog):
    secret = "https://hc-ping.com/0f0f0f0f-1111-2222-3333-444444444444"
    settings.HEALTHCHECK_URLS = {"scrape": secret}

    def boom(url, timeout):
        raise requests.ConnectionError(f"Max retries exceeded with url: {url}")

    monkeypatch.setattr(tracking.requests, "get", boom)
    with caplog.at_level(logging.WARNING, logger="ops.tracking"):
        tracking._ping_healthcheck("scrape")

    text = caplog.text
    assert "scrape" in text
    assert "0f0f0f0f" not in text and "hc-ping.com" not in text
    assert not any(r.exc_info for r in caplog.records), "no traceback (it carries the URL)"
