"""Exercise production's Sentry setup without Django, a database, or delivery."""

import ast
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest


def test_sentry_does_not_capture_private_request_or_frame_data(monkeypatch):
    source = (
        Path(__file__).resolve().parents[2]
        / "networkly_web/settings/production.py"
    )
    module = ast.parse(source.read_text())
    # Execute the actual optional integration block in isolation. Importing
    # all production settings would mutate process-wide Django configuration.
    setup = next(
        node for node in module.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "SENTRY_DSN"
    )
    initialize = Mock()
    monkeypatch.setitem(
        sys.modules, "sentry_sdk", SimpleNamespace(init=initialize)
    )
    dsn = "https://public-test-key@example.invalid/1"
    exec(compile(ast.Module(body=[setup], type_ignores=[]), str(source), "exec"),
         {"SENTRY_DSN": dsn})

    initialize.assert_called_once()
    options = initialize.call_args.kwargs
    assert options["dsn"] == dsn
    assert options["send_default_pii"] is False
    assert options["include_local_variables"] is False
    assert options["max_request_body_size"] == "never"
    assert options["traces_sample_rate"] == 0.0
    assert options["enable_logs"] is False
    from core.monitoring import scrub_sentry_event
    assert options["before_send"] is scrub_sentry_event


def test_event_scrubber_removes_mail_credentials_and_messages_but_keeps_frames():
    import json
    from core.monitoring import scrub_sentry_event

    private = "alice@example.com mailbox-body oauth-secret provider-private-message"
    frames = [{
        "filename": "capture/gmail.py",
        "function": "sync",
        "lineno": 42,
        "context_line": "response = client.execute()",
        "pre_context": ["client = build_client()"],
    }]
    event = {
        "level": "error", "logger": "capture.gmail",
        "contexts": {"runtime": {"name": "CPython", "version": "3.13"}},
        "request": {
            "url": "https://oauth-secret:password@coverage.example.com:8443/capture/gmail/callback/?code=oauth-secret#mailbox-body",
            "method": "GET", "query_string": "code=oauth-secret",
            "headers": {"Authorization": private}, "cookies": private,
            "data": private, "env": {"PRIVATE": private},
        },
        "breadcrumbs": {"values": [{"message": private}]},
        "user": {"email": private}, "extra": {"response": private},
        "message": private, "logentry": {"formatted": private},
        "exception": {"values": [{
            "type": "HttpError", "value": private,
            "stacktrace": {"frames": frames},
        }]},
    }

    result = scrub_sentry_event(event, {})
    serialized = json.dumps(result)
    for secret in private.split():
        assert secret not in serialized
    assert result["request"] == {
        "url": "https://coverage.example.com:8443/capture/gmail/callback/",
        "method": "GET",
    }
    error = result["exception"]["values"][0]
    assert error["type"] == "HttpError"
    assert error["stacktrace"]["frames"] == frames
    assert result["contexts"]["runtime"]["name"] == "CPython"
    assert result["logger"] == "capture.gmail"
    assert result["level"] == "error"
    for key in ("breadcrumbs", "user", "extra", "message", "logentry"):
        assert key not in result


def test_event_scrubber_drops_invalid_url_and_accepts_sparse_events():
    from core.monitoring import scrub_sentry_event

    assert scrub_sentry_event({}, {}) == {}
    assert scrub_sentry_event({"request": {"url": "https://host:invalid/"}}, {}) == {
        "request": {}
    }
@pytest.mark.parametrize("path", [
    "/welcome/unsubscribe/private-signed-token/",
    "/app/calendar/feed/private-calendar-token.ics",
])
def test_monitoring_does_not_publish_bearer_tokens_inside_url_paths(path):
    from core.monitoring import scrub_sentry_event
    import json
    result = scrub_sentry_event({"request": {"url": "https://networkly.test" + path}}, {})
    assert "private-" not in json.dumps(result)
    assert "[Filtered]" in result["request"]["url"]
