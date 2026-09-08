"""Older chat messages remain reachable by keyboard without a scroll jump."""

import pytest
from django.utils import timezone

from accounts.models import User
from assistant.models import ChatConversation, ChatMessage
from assistant.views import MESSAGE_PAGE_SIZE
from .test_journey_browser_matrix import _adopt_session

pytestmark = pytest.mark.django_db(transaction=True)


def test_older_history_preserves_position_and_retries_failed_load(session, live_server):
    user = User.objects.create_user(email="history-browser@example.test", password="x",
                                    onboarded_at=timezone.now())
    conversation = ChatConversation.all_objects.create(user=user, title="History pagination")
    rows = [ChatMessage(user=user, conversation=conversation,
                        role="user" if i % 2 == 0 else "assistant",
                        content=[{"type": "text", "text": f"Question or answer {i}. Enough detail to read."}])
            for i in range(MESSAGE_PAGE_SIZE + 30)]
    rows[0].content.append({"type": "document", "_filename": "historical-resume.pdf",
                           "source": {"type": "base64", "media_type": "application/pdf", "data": "private-payload"}})
    ChatMessage.all_objects.bulk_create(rows)
    _adopt_session(session, live_server, user)
    page = session.page
    page.goto(f"{live_server.url}/assistant/{conversation.pk}/")
    page.wait_for_load_state("networkidle")
    assert not session.real_console_errors()
    log = page.locator("#as-log")
    assert log.locator(".as-msg").count() == MESSAGE_PAGE_SIZE
    assert log.get_attribute("tabindex") == "0"
    link = page.get_by_role("link", name="Load Older Messages")
    link.scroll_into_view_if_needed()
    anchor = log.locator(".as-msg").first
    anchor_id = anchor.get_attribute("data-message-id")
    page.route("**/assistant/history/**", lambda route: route.fulfill(status=503, body="Unavailable"))
    link.focus()
    page.keyboard.press("Enter")
    page.get_by_role("status").filter(has_text="Could not load messages").wait_for()
    expected_failure = "HTTP 503: /assistant/history/"
    assert expected_failure in session.errors
    assert not [error for error in session.real_console_errors()
                if error != expected_failure and "status of 503" not in error]
    session.errors.clear()
    assert log.locator(".as-msg").count() == MESSAGE_PAGE_SIZE
    assert link.get_attribute("aria-disabled") is None
    page.unroute("**/assistant/history/**")
    link.focus()
    before = anchor.bounding_box()["y"]
    page.keyboard.press("Enter")
    page.locator(f'[data-message-id="{rows[0].pk}"]').wait_for(state="attached")
    assert log.locator(".as-msg").count() == len(rows)
    after = page.locator(f'[data-message-id="{anchor_id}"]').bounding_box()["y"]
    assert abs(before - after) <= 2
    assert page.locator(":focus").get_attribute("data-message-id") == anchor_id
    assert not page.get_by_role("link", name="Load Older Messages").count()
    assert "historical-resume.pdf" in log.text_content()
    assert "private-payload" not in page.content()
    assert session.horizontal_overflow() == 0
    assert not session.real_console_errors()
    session.shoot("assistant-history-loaded")
