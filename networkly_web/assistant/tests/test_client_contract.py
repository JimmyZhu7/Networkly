"""Exercise the real Anthropic SDK through an entirely local mock transport."""

import json
from unittest.mock import Mock

import anthropic
import httpx
import pytest

from assistant import client as module


@pytest.fixture(autouse=True)
def clean_proxy_environment(monkeypatch, settings):
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(name, raising=False)
    settings.ANTHROPIC_API_KEY = "local-provider-contract-key"


def sdk_client(monkeypatch, responses):
    requests, transports, options = [], [], []
    original = httpx.Client

    def respond(request):
        requests.append(request)
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        status, payload = response
        return httpx.Response(status, json=payload)

    class LocalClient(original):
        def __init__(self, **kwargs):
            options.append(kwargs)
            super().__init__(transport=httpx.MockTransport(respond), trust_env=False)
            transports.append(self)

    monkeypatch.setattr(httpx, "Client", LocalClient)
    monkeypatch.setattr("anthropic._base_client.time.sleep", lambda seconds: None)
    return module.get_client(), requests, transports, options


def answer():
    return {"id": "msg_local", "type": "message", "role": "assistant", "model": "local-model",
            "content": [{"type": "text", "text": "Ready"}], "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 2, "output_tokens": 1}}


def ask(client):
    return client.messages.create(model="local-model", max_tokens=10,
                                  messages=[{"role": "user", "content": "Check the plan"}])


def test_sdk_request_has_bounded_timeout_and_releases_owned_transport(monkeypatch):
    client, requests, transports, options = sdk_client(monkeypatch, iter([(200, answer())]))
    try:
        assert ask(client).content[0].text == "Ready"
        request = requests[0]
        assert request.url == "https://api.anthropic.com/v1/messages"
        assert request.headers["x-api-key"] == "local-provider-contract-key"
        assert json.loads(request.content)["messages"] == [{"role": "user", "content": "Check the plan"}]
        assert set(request.extensions["timeout"].values()) == {module.REQUEST_TIMEOUT_SECONDS}
        assert options[0]["trust_env"] is False
    finally:
        module.close_client(client)
    assert transports[0].is_closed


@pytest.mark.parametrize("status,attempts,error", [(401, 1, anthropic.AuthenticationError),
                                                   (503, 2, anthropic.InternalServerError)])
def test_sdk_failure_retries_are_bounded_and_typed(monkeypatch, status, attempts, error):
    payload = {"type": "error", "error": {"type": "api_error", "message": "Local fixture"}}
    client, requests, transports, _ = sdk_client(monkeypatch, iter([(status, payload)] * 3))
    try:
        with pytest.raises(error):
            ask(client)
        assert len(requests) == attempts
    finally:
        module.close_client(client)
    assert transports[0].is_closed


def test_sdk_recovers_from_one_transient_failure(monkeypatch):
    client, requests, _, _ = sdk_client(monkeypatch, iter([(503, {"error": "busy"}), (200, answer())]))
    try:
        assert ask(client).content[0].text == "Ready"
        assert len(requests) == 2
    finally:
        module.close_client(client)


def test_sdk_timeout_exhausts_one_retry_without_hanging(monkeypatch):
    client, requests, _, _ = sdk_client(monkeypatch, iter([httpx.ReadTimeout("local timeout")] * 3))
    try:
        with pytest.raises(anthropic.APITimeoutError):
            ask(client)
        assert len(requests) == 2
    finally:
        module.close_client(client)


@pytest.mark.parametrize("proxy_vars,expected", [
    ({"ALL_PROXY": "socks5://unavailable.local:1080"}, None),
    ({"https_proxy": "http://local-proxy:8080", "HTTP_PROXY": "http://other:8080"}, "http://local-proxy:8080"),
])
def test_explicit_https_proxy_selection_never_falls_back_to_socks(monkeypatch, proxy_vars, expected):
    for key, value in proxy_vars.items():
        monkeypatch.setenv(key, value)
    client, _, _, options = sdk_client(monkeypatch, iter([(200, answer())]))
    try:
        assert ask(client).content[0].text == "Ready"
        assert options[0]["proxy"] == expected
    finally:
        module.close_client(client)


@pytest.mark.parametrize("failure", [ValueError("invalid config"), KeyboardInterrupt()])
def test_failed_sdk_construction_closes_the_new_http_client(monkeypatch, failure):
    owned = Mock()
    monkeypatch.setattr(httpx, "Client", Mock(return_value=owned))
    monkeypatch.setattr(anthropic, "Anthropic", Mock(side_effect=failure))
    with pytest.raises(type(failure)):
        module.get_client()
    owned.close.assert_called_once_with()


def test_cleanup_failure_does_not_replace_a_completed_answer(caplog):
    module.close_client(Mock(close=Mock(side_effect=RuntimeError("private transport diagnostic"))))
    assert "Could not close assistant transport" in caplog.text
    assert "private transport diagnostic" not in caplog.text
