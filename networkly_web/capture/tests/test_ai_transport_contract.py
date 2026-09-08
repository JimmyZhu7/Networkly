"""Offline provider boundary contracts: resources, retry budgets and trust."""

import io
import json
from types import SimpleNamespace
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

import pytest

from capture import autopilot, gmail_residue, mailfacts


@pytest.fixture(params=[autopilot, gmail_residue])
def transport_module(request, monkeypatch, settings):
    settings.ANTHROPIC_API_KEY = "local-contract-key"
    module = request.param
    monkeypatch.setattr(module.time, "sleep", Mock())
    return module


def error_type(module):
    return autopilot.AutopilotError if module is autopilot else gmail_residue.ResidueClassifyError


def envelope(text):
    return {"content": [{"type": "text", "text": text}]}


def test_json_transport_preserves_payload_timeout_and_closes_success(transport_module, monkeypatch):
    response = io.BytesIO(json.dumps(envelope("Local answer")).encode())
    send = Mock(return_value=response)
    monkeypatch.setattr(transport_module.urllib.request, "urlopen", send)
    payload = {"messages": [{"role": "user", "content": "Hello 海"}]}
    assert transport_module._post_json(payload, timeout=9, retries=2) == envelope("Local answer")
    request = send.call_args.args[0]
    assert json.loads(request.data) == payload
    assert request.get_method() == "POST"
    assert request.get_header("X-api-key") == "local-contract-key"
    assert send.call_args.kwargs == {"timeout": 9}
    assert response.closed


@pytest.mark.parametrize("failure_kind", ["server", "connection", "invalid_json"])
def test_transient_or_invalid_json_recovers_within_retry_budget(transport_module, monkeypatch, failure_kind):
    body = io.BytesIO(b"temporary problem")
    first = (HTTPError(transport_module.API_URL, 503, "busy", {}, body) if failure_kind == "server"
             else URLError("offline") if failure_kind == "connection" else body)
    success = io.BytesIO(json.dumps(envelope("recovered")).encode())
    send = Mock(side_effect=[first, success])
    monkeypatch.setattr(transport_module.urllib.request, "urlopen", send)
    assert transport_module._post_json({}, timeout=8, retries=1) == envelope("recovered")
    assert send.call_count == 2
    transport_module.time.sleep.assert_called_once()
    assert success.closed
    if failure_kind != "connection":
        assert body.closed


@pytest.mark.parametrize("status", [400, 401, 429])
def test_permanent_http_failures_are_not_retried_and_release_response(transport_module, monkeypatch, status):
    body = io.BytesIO(b"fixture-only-error")
    failure = HTTPError(transport_module.API_URL, status, "rejected", {}, body)
    send = Mock(side_effect=failure)
    monkeypatch.setattr(transport_module.urllib.request, "urlopen", send)
    with pytest.raises(error_type(transport_module)) as error:
        transport_module._post_json({}, timeout=8, retries=2)
    assert error.value.cause is failure
    assert send.call_count == 1
    transport_module.time.sleep.assert_not_called()
    assert body.closed


def test_exhausted_transport_error_is_typed_and_does_not_sleep_again(transport_module, monkeypatch):
    failure = TimeoutError("fixture timeout")
    send = Mock(side_effect=failure)
    monkeypatch.setattr(transport_module.urllib.request, "urlopen", send)
    with pytest.raises(error_type(transport_module)) as error:
        transport_module._post_json({}, timeout=8, retries=2)
    assert error.value.cause is failure
    assert send.call_count == 3 and transport_module.time.sleep.call_count == 2


@pytest.mark.parametrize("response", [None, [], {"content": [None]},
    {"content": [{"type": "text", "text": {"decision": "accept"}}]},
    {"content": [{"type": "tool_use", "input": {"decision": "accept"}}]},
    {"content": "unexpected provider string"}, {"content": []},
    envelope('{"decision":"accept","confidence":0.99,"quote":"Actual source"')])
def test_autopilot_malformed_provider_envelope_never_authorizes_action(monkeypatch, response):
    monkeypatch.setattr(autopilot, "_post_json", Mock(return_value=response))
    decision = autopilot._decide_with_model("Actual source", model="fixture")
    assert decision[0] == "malformed"
    assert autopilot._gate(*decision, "Actual source")[0] == "escalate"


@pytest.mark.parametrize("confidence", [None, "unknown", float("nan"), float("inf"), -float("inf"), True, 10**400])
def test_autopilot_invalid_confidence_cannot_meet_acceptance_floor(monkeypatch, confidence):
    response = envelope(json.dumps({"decision": "accept", "confidence": confidence,
                                   "quote": "Actual source", "reason": "fixture"}))
    monkeypatch.setattr(autopilot, "_post_json", Mock(return_value=response))
    decision = autopilot._decide_with_model("Actual source", model="fixture")
    assert autopilot._gate(*decision, "Actual source")[0] == "escalate"


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), True, 10**400, None, "unknown"])
def test_final_gate_rejects_invalid_confidence_from_any_decider(confidence):
    assert autopilot._gate("accept", confidence, "Actual source", "fixture", "Actual source")[0] == "escalate"


@pytest.mark.parametrize("quote", [123, True, ["Actual source"], {"source": "Actual source"}])
def test_autopilot_does_not_coerce_structured_values_into_verbatim_evidence(monkeypatch, quote):
    response = envelope(json.dumps({"decision": "accept", "confidence": .99, "quote": quote}))
    monkeypatch.setattr(autopilot, "_post_json", Mock(return_value=response))
    source = str(quote)
    decision = autopilot._decide_with_model(source, model="fixture")
    assert autopilot._gate(*decision, source)[0] == "escalate"


@pytest.mark.parametrize("quote", [" ", "\n\t"])
def test_whitespace_is_not_grounded_evidence_for_either_classifier(monkeypatch, quote):
    monkeypatch.setattr(autopilot, "_post_json", Mock(return_value=envelope(json.dumps({
        "decision": "accept", "confidence": .99, "quote": quote}))))
    decision = autopilot._decide_with_model("Actual source", model="fixture")
    assert autopilot._gate(*decision, "Actual source")[0] == "escalate"
    monkeypatch.setattr(gmail_residue, "_post_json", Mock(return_value=envelope(json.dumps({
        "outcome": "genuine_reply", "quote": quote}))))
    assert gmail_residue._classify_one({"snippet": "Actual source"}, model="fixture", timeout=8, retries=0) == ("ambiguous", None)


@pytest.mark.parametrize("confidence,expected", [(.99, "accept"), ("0.99", "accept"), (.1, "escalate"), (0, "escalate")])
def test_valid_confidence_and_grounding_keep_existing_decision_policy(monkeypatch, confidence, expected):
    response = envelope(json.dumps({"decision": "accept", "confidence": confidence,
                                   "quote": "Actual source", "reason": "fixture"}))
    monkeypatch.setattr(autopilot, "_post_json", Mock(return_value=response))
    decision = autopilot._decide_with_model("Actual source", model="fixture")
    assert autopilot._gate(*decision, "Actual source")[0] == expected


def test_autopilot_reads_split_text_but_still_rejects_a_fabricated_quote(monkeypatch):
    raw = json.dumps({"decision": "accept", "confidence": .99, "quote": "Invented evidence", "reason": "fixture"})
    response = {"content": [{"type": "thinking", "thinking": "not evidence"},
                            {"type": "text", "text": raw[:24]}, {"type": "text", "text": raw[24:]}]}
    monkeypatch.setattr(autopilot, "_post_json", Mock(return_value=response))
    decision = autopilot._decide_with_model("Actual source", model="fixture")
    assert decision[0] == "accept"
    assert autopilot._gate(*decision, "Actual source")[0] == "escalate"


@pytest.mark.parametrize("response", [None, [], {"content": [None]}, envelope("[]"),
    envelope("null"), envelope('{"outcome":"genuine_reply","quote":42}'),
    envelope('{"outcome":"genuine_reply","quote":{"invented":"source"}}'),
    envelope('{"outcome":["genuine_reply"],"quote":"Actual source"}'),
    {"content": "unexpected provider string"}, {"content": [{"type": "text", "text": 42}]}])
def test_residue_partial_response_is_ambiguous_not_a_sync_failure(monkeypatch, response):
    monkeypatch.setattr(gmail_residue, "_post_json", Mock(return_value=response))
    assert gmail_residue._classify_one({"snippet": "Actual source"}, model="fixture", timeout=8, retries=0) == ("ambiguous", None)


def test_residue_split_response_requires_grounded_quote(monkeypatch):
    raw = json.dumps({"outcome": "genuine_reply", "quote": "Happy to chat on Tuesday."})
    response = {"content": [{"type": "text", "text": raw[:22]},
                            {"type": "thinking", "thinking": "not evidence"},
                            {"type": "text", "text": raw[22:]}]}
    monkeypatch.setattr(gmail_residue, "_post_json", Mock(return_value=response))
    result = gmail_residue._classify_one({"snippet": "Happy to chat on Tuesday."}, model="fixture", timeout=8, retries=0)
    assert result == ("genuine_reply", "Happy to chat on Tuesday.")
    result = gmail_residue._classify_one({"snippet": "A completely different message."}, model="fixture", timeout=8, retries=0)
    assert result == ("ambiguous", None)


def test_mailfact_model_sees_only_preview_and_cannot_supply_referral_data(monkeypatch):
    text = "Alex has moved on. Please contact Casey Jones at casey@example.test."
    classifier = Mock(return_value=SimpleNamespace(value="departed", phrase="Alex has moved on.",
        new_email="invented@elsewhere.test", new_name="Invented Person"))
    # Drive the real default-classifier seam rather than bypassing the wrapper.
    monkeypatch.setattr(mailfacts.ai_extract, "extract_mail_fact_ai", classifier)
    result = mailfacts._detect_ai(text, {"subject": " Away ", "snippet": " A &amp; B ",
        "body": "Private full body must not reach the model", "refresh_token": "not input"})
    classifier.assert_called_once_with("Away", "A & B")
    assert [item.kind for item in result] == ["departed", "referral"]
    assert result[1].new_email == "casey@example.test"
    assert result[1].new_name == "Casey Jones"
    assert all(item.detected_by == "ai" and item.quote in text for item in result)


@pytest.mark.parametrize("guess", [None, SimpleNamespace(value="departed", phrase="Invented quote"),
                                   SimpleNamespace(value="departed", phrase="")])
def test_mailfact_ungrounded_or_absent_guess_produces_no_fact(guess):
    assert mailfacts._detect_ai("Original message", {}, ai_classifier=Mock(return_value=guess)) == []
