"""Scoring must agree with the event log and the requested as-of instant."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from networkly_domain import pipeline, scoring

NOW = datetime(2026, 9, 6, 12, tzinfo=timezone.utc)


def event(kind, days=0, note=None):
    return {"contact_id": 1, "kind": kind, "ts": NOW + timedelta(days=days), "note": note}


def test_a_recorded_referral_is_advocacy_and_recent_engagement():
    assert pipeline.TOUCH_TRANSITIONS[pipeline.REFERRAL_KIND] == ("advocate", "advocate")
    result = scoring.score_contact({"id": 1}, [event("outreach", -2), event("referral")], as_of=NOW)
    assert result["axes"]["depth"]["level"] == 3
    assert result["axes"]["recency"]["score"] == 100
    assert result["axes"]["responsiveness"]["replies"] == 1
    assert result["reasoning"].startswith("advocate")
    assert "no reply" not in result["reasoning"]


def test_manual_demotion_after_a_referral_still_wins():
    result = scoring.score_contact({"id": 1}, [
        event("referral", -1), event("manual_override", note="manual override: warmth=cold"),
    ], as_of=NOW)
    assert result["axes"]["depth"]["level"] == 0


def test_firm_network_counts_a_real_referrer_as_an_advocate():
    result = scoring.score_firm(
        {"regions": [], "tracks": []}, {"id": 7},
        [{"id": 1, "firm_id": 7}], [event("referral")], [], as_of=NOW,
    )
    assert result["axes"]["network"]["advocates"] == 1


@pytest.mark.parametrize("kind", ["outreach", "follow_up", "reply_received", "chat_scheduled", "chat", "referral", "manual_override"])
def test_future_evidence_cannot_change_any_current_contact_axis(kind):
    history = [event("outreach", -5), event("reply_received", -3)]
    before = scoring.score_contact({"id": 1}, history, as_of=NOW)
    future = event(kind, 1, note="manual override: warmth=advocate")
    after = scoring.score_contact({"id": 1}, [*history, future], as_of=NOW)
    assert after == before


def test_future_chat_becomes_evidence_only_when_its_time_arrives():
    chat = event("chat", 1)
    early = scoring.score_contact({"id": 1}, [chat], as_of=NOW)
    arrived = scoring.score_contact({"id": 1}, [chat], as_of=chat["ts"])
    assert early["axes"]["depth"]["chats"] == 0
    assert early["axes"]["responsiveness"]["replies"] == 0
    assert arrived["axes"]["depth"]["chats"] == 1
    assert arrived["axes"]["recency"]["score"] == 100


@pytest.mark.parametrize("kinds,expected", [
    (["chat", "manual_override"], 0),
    (["manual_override", "chat"], 2),
])
def test_equal_timestamp_events_replay_by_id_in_both_input_orders(kinds, expected):
    history = [
        {**event(kind, note="manual override: warmth=cold"), "id": i + 1}
        for i, kind in enumerate(kinds)
    ]
    forward = scoring.score_contact({"id": 1}, history, as_of=NOW)
    reverse = scoring.score_contact({"id": 1}, reversed(history), as_of=NOW)
    assert forward == reverse
    assert forward["axes"]["depth"]["level"] == expected


def test_equal_timestamp_order_is_part_of_the_score_hash():
    chat = {**event("chat"), "id": 1}
    demotion = {**event("manual_override", note="manual override: warmth=cold"), "id": 2}
    first = scoring.score_contact({"id": 1}, [chat, demotion], as_of=NOW)
    second = scoring.score_contact({"id": 1}, [
        {**chat, "id": 2}, {**demotion, "id": 1},
    ], as_of=NOW)
    assert first["axes"]["depth"]["level"] != second["axes"]["depth"]["level"]
    assert first["inputs_hash"] != second["inputs_hash"]


def test_equal_timestamp_legacy_history_has_a_stable_fallback():
    history = [event("chat"), event("manual_override", note="manual override: warmth=cold")]
    forward = scoring.score_contact({"id": 1}, history, as_of=NOW)
    reverse = scoring.score_contact({"id": 1}, reversed(history), as_of=NOW)
    assert forward == reverse


def test_scoring_uses_elapsed_time_across_daylight_saving_changes():
    zone = ZoneInfo("America/Los_Angeles")
    start = datetime(2026, 3, 7, 12, tzinfo=zone)
    end = datetime(2026, 3, 9, 12, tzinfo=zone)
    history = [{"kind": "outreach", "ts": start}, {"kind": "reply_received", "ts": end}]
    local = scoring.score_contact({"id": 1}, history, as_of=end)
    utc = scoring.score_contact({"id": 1}, [
        {**row, "ts": row["ts"].astimezone(timezone.utc)} for row in history
    ], as_of=end.astimezone(timezone.utc))
    assert scoring._days_between(end, start) == 47 / 24
    assert local == utc


def test_second_occurrence_of_repeated_hour_is_still_future_evidence():
    zone = ZoneInfo("America/Los_Angeles")
    first = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    second = first.replace(fold=1)
    history = [{"kind": "chat", "ts": second}]
    early = scoring.score_contact({"id": 1}, history, as_of=first)
    arrived = scoring.score_contact({"id": 1}, history, as_of=second)
    assert early["axes"]["depth"]["level"] == 0
    assert arrived["axes"]["depth"]["level"] == 2


def test_repeated_hour_replay_uses_instant_before_id():
    zone = ZoneInfo("America/Los_Angeles")
    first = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
    second = first.replace(fold=1)
    history = [
        {"id": 2, "kind": "chat", "ts": first},
        {"id": 1, "kind": "manual_override", "ts": second, "note": "manual override: warmth=cold"},
    ]
    score = scoring.score_contact({"id": 1}, history, as_of=second)
    assert score["axes"]["depth"]["level"] == 0
