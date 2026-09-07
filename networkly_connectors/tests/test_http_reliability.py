"""Transport failures are bounded and a malformed board is isolated."""

import io
from http.client import HTTPResponse, IncompleteRead
import urllib.error
from unittest.mock import Mock

import pytest

import networkly_connectors as connectors
from networkly_connectors import http
from networkly_connectors.models import FetchResult, GreenhouseBoard


@pytest.mark.parametrize("status", [400, 401, 403, 422])
def test_permanent_http_error_does_not_retry(monkeypatch, status):
    request = Mock(side_effect=urllib.error.HTTPError("https://example.com", status, "failed", {}, None))
    sleep = Mock()
    monkeypatch.setattr(http, "_do_request", request)
    monkeypatch.setattr(http.time, "sleep", sleep)
    with pytest.raises(http.FetchError) as caught:
        http.fetch_bytes("https://example.com")
    assert caught.value.cause.code == status
    assert request.call_count == 1
    sleep.assert_not_called()


def test_transient_http_failure_retries_then_returns_payload(monkeypatch):
    request = Mock(side_effect=[urllib.error.HTTPError("https://example.com", 503, "failed", {}, None), b"{}"])
    monkeypatch.setattr(http, "_do_request", request)
    monkeypatch.setattr(http.time, "sleep", Mock())
    assert http.fetch_bytes("https://example.com") == b"{}"
    assert request.call_count == 2


def test_oversized_response_is_bounded_and_not_retried(monkeypatch):
    monkeypatch.setattr(http, "MAX_RESPONSE_BYTES", 10)
    payload = io.BytesIO(b"x" * 100)
    opener = Mock(return_value=payload)
    monkeypatch.setattr(http.urllib.request, "urlopen", opener)
    with pytest.raises(http.FetchError, match="response exceeds"):
        http.fetch_bytes("https://example.com")
    assert opener.call_count == 1
    assert payload.closed


def _http_response(body, declared_length):
    class Socket:
        def makefile(self, mode):
            return io.BytesIO(
                f"HTTP/1.1 200 OK\r\nContent-Length: {declared_length}\r\n\r\n".encode() + body
            )

    response = HTTPResponse(Socket())
    response.begin()
    return response


def test_incomplete_content_length_cannot_pass_as_valid_empty_board(monkeypatch):
    body = b'{"jobs": []}'
    opener = Mock(side_effect=lambda *a, **k: _http_response(body, 100))
    monkeypatch.setattr(http.urllib.request, "urlopen", opener)
    monkeypatch.setattr(http.time, "sleep", Mock())
    with pytest.raises(http.FetchError) as caught:
        http.fetch_json("https://example.com")
    assert isinstance(caught.value.cause, IncompleteRead)
    assert caught.value.cause.partial == body
    assert opener.call_count == 3


def test_complete_content_length_is_accepted(monkeypatch):
    body = b'{"jobs": []}'
    monkeypatch.setattr(http.urllib.request, "urlopen", lambda *a, **k: _http_response(body, len(body)))
    assert http.fetch_json("https://example.com") == {"jobs": []}


def test_bad_board_does_not_abort_other_fetches(monkeypatch):
    broken = GreenhouseBoard(firm="Bad", token="bad")
    good = GreenhouseBoard(firm="Good", token="good")

    def fetch(board):
        if board is broken:
            raise TypeError("provider returned an invalid row")
        return FetchResult(board=board, ok=True, opportunities=[], raw_count=0, empty_state=True)

    monkeypatch.setattr(connectors.CONNECTORS["greenhouse"], "fetch", fetch)
    results = connectors.fetch_many([broken, good], max_workers=2)
    assert [result.board.firm for result in results] == ["Bad", "Good"]
    assert not results[0].ok
    assert "TypeError" in results[0].error
    assert results[1].ok
