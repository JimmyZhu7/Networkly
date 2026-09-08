"""Streaming histories preserve decisions and compare repeated hours as instants."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from networkly_domain.cadence import TouchHistory, due_actions


def test_full_outbound_count_survives_a_long_stream():
    now = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    history = TouchHistory.from_touches(
        {"id": i, "contact_id": 1, "kind": "outreach", "ts": now - timedelta(days=60)}
        for i in range(100_000)
    )
    contact = {"id": 1, "warmth": "cold", "thread_state": "no_reply"}
    action = due_actions([contact], history, as_of=now)[0]
    assert action["action"] == "park"
    assert action["ctx"]["outbound"] == 100_000
    assert len(history.contacts) == 1
    assert history.contacts[1].last_real["id"] == 99_999


def test_thank_you_from_before_the_latest_chat_does_not_hide_a_new_one():
    now = datetime(2026, 9, 7, 12, tzinfo=timezone.utc)
    touches = [
        {"id": 1, "contact_id": 1, "kind": "chat", "ts": now - timedelta(days=30)},
        {"id": 2, "contact_id": 1, "kind": "thank_you", "ts": now - timedelta(days=29)},
        {"id": 3, "contact_id": 1, "kind": "chat", "ts": now - timedelta(hours=2)},
    ]
    action = due_actions([{"id": 1, "warmth": "chatted", "thread_state": "chat_done"}],
                         iter(reversed(touches)), as_of=now)[0]
    assert action["action"] == "thank_you"
    assert action["ctx"]["hours"] == 2


def test_repeated_dst_hour_uses_elapsed_time_and_event_order():
    zone = ZoneInfo("America/New_York")
    chat = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    now = datetime(2026, 11, 1, 2, 0, tzinfo=zone)
    contact = {"id": 1, "warmth": "chatted", "thread_state": "chat_done"}
    touches = [{"id": 1, "contact_id": 1, "kind": "chat", "ts": chat}]
    action = due_actions([contact], touches, as_of=now)[0]
    assert action["ctx"]["hours"] == 1.5
    # 01:15 on the second clock is later than 01:30 on the first clock.
    touches.append({"id": 2, "contact_id": 1, "kind": "thank_you",
                    "ts": datetime(2026, 11, 1, 1, 15, tzinfo=zone, fold=1)})
    assert due_actions([contact], touches, as_of=now) == []


def test_equal_time_real_evidence_uses_ledger_identity_not_query_order():
    now = datetime(2026, 9, 7, tzinfo=timezone.utc)
    rows = [
        {"id": 1, "contact_id": 1, "kind": "outreach", "ts": now},
        {"id": 2, "contact_id": 1, "kind": "reply_received", "ts": now},
        {"id": 3, "contact_id": 1, "kind": "bulk_received", "ts": now},
    ]
    for source in (rows, reversed(rows)):
        assert TouchHistory.from_touches(source).contacts[1].last_real["kind"] == "reply_received"
