"""Scoring must agree with the event log and the requested as-of instant."""

from datetime import datetime, timedelta, timezone

import pytest

from coverage_domain import pipeline, scoring

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
