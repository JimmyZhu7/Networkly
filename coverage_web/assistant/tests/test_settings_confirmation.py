"""The server, not a model argument, authorizes important settings writes."""

import json

import pytest
from django.contrib.auth import get_user_model

from assistant import agent, tools
from assistant.confirmation import approved_settings
from assistant.models import ChatConversation, ChatMessage
from .test_agent import FakeClient, FakeStreamingClient, _response, _text, _tool_use


pytestmark = pytest.mark.django_db


@pytest.fixture
def student():
    return get_user_model().objects.create_user(email="approval@example.com", password="x")


@pytest.fixture
def conversation(student):
    row = ChatConversation(user=student, title="Settings")
    row.save()
    return row


def _turn(student, conversation, text, calls, *, streaming=False):
    responses = [
        _response([_tool_use("update_settings", args, f"toolu_{index}")], "tool_use")
        for index, args in enumerate(calls)
    ] + [_response([_text("Change your timezone to Europe/London. Please confirm.")], "end_turn")]
    if streaming:
        client = FakeStreamingClient([([], response) for response in responses])
        assert list(agent.stream_turn(student, conversation, text, client=client))[-1]["type"] == "done"
    else:
        assert agent.run_turn(student, conversation, text, client=FakeClient(responses)).ok
    student.refresh_from_db()


def _setting(value="Europe/London", confirmed=False):
    return {"field": "timezone", "value": value, "confirmed": confirmed}


@pytest.mark.parametrize("streaming", [False, True])
def test_model_cannot_skip_or_self_complete_confirmation(student, conversation, streaming):
    _turn(student, conversation, "Change my timezone", [
        _setting(confirmed=True), _setting(confirmed=True),
    ], streaming=streaming)
    assert student.timezone == ""


@pytest.mark.parametrize("streaming", [False, True])
def test_next_explicit_human_reply_approves_exact_proposal(student, conversation, streaming):
    _turn(student, conversation, "Change my timezone", [_setting()], streaming=streaming)
    _turn(student, conversation, "Yes, please".replace(",", ""), [_setting(confirmed=True)], streaming=streaming)
    assert student.timezone == "Europe/London"


@pytest.mark.parametrize("reply", ["yes but keep my current timezone", "What does that mean?", "no"])
def test_qualified_or_unrelated_reply_does_not_authorize(student, conversation, reply):
    _turn(student, conversation, "Change my timezone", [_setting()])
    _turn(student, conversation, reply, [_setting(confirmed=True)])
    assert student.timezone == ""


def test_confirmation_cannot_change_the_value(student, conversation):
    _turn(student, conversation, "Change my timezone", [_setting()])
    _turn(student, conversation, "yes", [_setting("Asia/Hong_Kong", confirmed=True)])
    assert student.timezone == ""


def test_changed_setting_requires_a_fresh_proposal(student, conversation):
    _turn(student, conversation, "Change my timezone", [_setting()])
    student.timezone = "Asia/Hong_Kong"
    student.timezone_auto = False
    student.save(update_fields=["timezone", "timezone_auto"])
    _turn(student, conversation, "yes", [_setting(confirmed=True)])
    assert student.timezone == "Asia/Hong_Kong"


def test_confirmation_does_not_survive_an_intervening_turn(student, conversation):
    _turn(student, conversation, "Change my timezone", [_setting()])
    _turn(student, conversation, "Tell me about my queue", [])
    _turn(student, conversation, "yes", [_setting(confirmed=True)])
    assert student.timezone == ""


def test_failed_proposal_reply_cannot_be_confirmed(student, conversation):
    _turn(student, conversation, "Change my timezone", [_setting()])
    notice = ChatMessage(user=student, conversation=conversation, role="assistant",
                         content=[{"type": "text", "text": "Failed"}], notice=ChatMessage.NOTICE_FAILED)
    notice.save()
    _turn(student, conversation, "yes", [_setting(confirmed=True)])
    assert student.timezone == ""


def test_approval_cannot_be_read_by_another_tenant(student, conversation):
    _turn(student, conversation, "Change my timezone", [_setting()])
    message = ChatMessage(user=student, conversation=conversation, role="user",
                          content=[{"type": "text", "text": "yes"}])
    message.save()
    assert approved_settings(student, conversation)
    other = get_user_model().objects.create_user(email="other-approval@example.com", password="x")
    assert approved_settings(other, conversation) == ()


def test_model_input_cannot_smuggle_server_context(student):
    args = _setting(confirmed=True)
    args["approved_settings"] = [{"field": "timezone", "value": "Europe/London", "before": ""}]
    payload, error = tools.execute(student, "update_settings", args)
    assert error and "settings_proposal" in json.loads(payload)
    student.refresh_from_db()
    assert student.timezone == ""
