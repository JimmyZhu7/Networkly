"""Bounded conversation reads preserve chronology, files and tenant fences."""

from datetime import timedelta
import re

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from assistant.models import ChatConversation, ChatMessage
from assistant.views import MESSAGE_PAGE_SIZE, _display_messages, _message_page

pytestmark = pytest.mark.django_db


@pytest.fixture
def history(client):
    user = get_user_model().objects.create_user(email="history-pages@example.test", password="x")
    conversation = ChatConversation.objects.for_user(user).create(user=user, title="Long conversation")
    rows = [ChatMessage(user=user, conversation=conversation,
                        role="user" if i % 2 == 0 else "assistant",
                        content=[{"type": "text", "text": f"Message {i:03d}"}])
            for i in range(MESSAGE_PAGE_SIZE * 2 + 7)]
    ChatMessage.objects.for_user(user).bulk_create(rows)
    # Every timestamp ties: IDs must provide the stable second ordering key.
    ChatMessage.objects.for_user(user).update(created=timezone.now() - timedelta(days=1))
    client.force_login(user)
    return user, conversation, rows


def test_pages_are_bounded_and_cover_full_history_without_duplicates(history, client):
    user, conversation, rows = history
    seen, before = [], None
    with CaptureQueriesContext(connection) as queries:
        page = _message_page(user, conversation)
    assert len(page["rows"]) <= MESSAGE_PAGE_SIZE
    assert any("LIMIT 61" in query["sql"] for query in queries)
    while True:
        batch = [row["message_id"] for row in page["rows"]]
        assert batch == sorted(batch)
        seen = batch + seen
        before = page["before_cursor"]
        if before is None:
            break
        page = _message_page(user, conversation, before)
    assert seen == [row.pk for row in rows]
    response = client.get(reverse("assistant:chat_conversation", args=[conversation.pk]))
    assert response.status_code == 200
    assert "Load Older Messages" in response.content.decode()
    assert response.content.count(b'data-message-id=') <= MESSAGE_PAGE_SIZE


def test_newer_insert_does_not_shift_older_page_cursor(history):
    user, conversation, _ = history
    page = _message_page(user, conversation)
    older = _message_page(user, conversation, page["before_cursor"])
    ChatMessage.objects.for_user(user).create(user=user, conversation=conversation, role="assistant",
                                   content=[{"type": "text", "text": "New reply"}])
    assert _message_page(user, conversation, page["before_cursor"]) == older


def test_attachment_names_and_tool_evidence_survive_without_loading_payloads(history):
    user, conversation, rows = history
    attachment = rows[0]
    ChatMessage.objects.for_user(user).filter(pk=attachment.pk).update(content=[
        {"type": "text", "text": "Review my CV"},
        {"type": "document", "_filename": "resume.pdf", "source": {"data": "large-private-file"}},
    ])
    messages, _ = _display_messages(user, conversation, rows[5].pk)
    assert messages[0].attachment_names == ["resume.pdf"]
    assert "source" not in messages[0].content[1]
    assert "large-private-file" not in repr(messages)
    page = _message_page(user, conversation, rows[5].pk)
    assert page["rows"][0]["attachments"] == ["resume.pdf"]
    assert page["rows"][1]["retry_message_id"] == attachment.pk


def test_full_page_and_fragment_render_older_messages(history, client):
    user, conversation, _ = history
    page = _message_page(user, conversation)
    cursor = page["before_cursor"]
    expected = _message_page(user, conversation, cursor)
    fragment = client.get(reverse("assistant:history"), {"conversation": conversation.pk, "before": cursor})
    full = client.get(reverse("assistant:chat_conversation", args=[conversation.pk]), {"before": cursor})
    ids = lambda response: list(map(int, re.findall(r'data-message-id="(\d+)"', response.content.decode())))
    assert fragment.status_code == full.status_code == 200
    assert ids(fragment) == ids(full) == [row["message_id"] for row in expected["rows"]]
    assert "Latest Messages" in full.content.decode()
    assert 'aria-controls="as-log"' in fragment.content.decode()
    assert 'role="region" aria-label="Conversation"' in full.content.decode()


@pytest.mark.parametrize("cursor", ["invalid", "-1", "0", "99999999999999999999999999"])
def test_invalid_message_cursor_is_not_a_server_error(history, client, cursor):
    _, conversation, _ = history
    assert client.get(reverse("assistant:history"), {"conversation": conversation.pk, "before": cursor}).status_code == 404


def test_cross_tenant_or_other_conversation_cursor_never_exposes_messages(history, client):
    user, conversation, rows = history
    other = get_user_model().objects.create_user(email="foreign-history@example.test", password="x")
    foreign = ChatConversation.objects.for_user(other).create(user=other)
    foreign_message = ChatMessage.objects.for_user(other).create(user=other, conversation=foreign, content=[{"type": "text", "text": "Secret"}])
    own_other = ChatConversation.objects.for_user(user).create(user=user)
    own_message = ChatMessage.objects.for_user(user).create(user=user, conversation=own_other)
    endpoint = reverse("assistant:history")
    for conv, cursor in [(conversation.pk, foreign_message.pk), (foreign.pk, rows[0].pk), (conversation.pk, own_message.pk)]:
        response = client.get(endpoint, {"conversation": conv, "before": cursor})
        assert response.status_code == 404
        assert "Secret" not in response.content.decode()
    assert client.get(endpoint, {"before": rows[0].pk}).status_code == 404
    assert client.post(endpoint, {"conversation": conversation.pk, "before": rows[0].pk}).status_code == 405
    client.logout()
    assert client.get(endpoint, {"conversation": conversation.pk, "before": rows[0].pk}).status_code == 302
