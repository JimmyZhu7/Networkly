"""Offline pagination trust checks: a partial board cannot prove a role closed."""
import pytest

from coverage_connectors import phenom
from coverage_connectors.models import PhenomBoard

BOARD = PhenomBoard(firm="BCG", host="careers.bcg.com", keywords="intern")


def _job(i):
    return {"jobId": str(i), "title": f"Intern {i}",
            "applyUrl": f"https://careers.bcg.com/job/{i}", "city": "Boston"}


def _page(jobs, total):
    return {"refineSearch": {"totalHits": total, "data": {"jobs": jobs}}}


def test_cap_marks_a_successful_fetch_incomplete(monkeypatch):
    monkeypatch.setattr(phenom, "_MAX_JOBS", 2)
    monkeypatch.setattr(phenom, "_PAGE_SIZE", 2)
    monkeypatch.setattr(phenom, "post_json", lambda *a, **k: _page([_job(1), _job(2)], 5))
    result = phenom.fetch(BOARD)
    assert result.ok and result.raw_count == 2
    assert result.truncated, "omitted roles are not evidence of closure"


def test_empty_later_page_does_not_claim_a_complete_board(monkeypatch):
    pages = iter([_page([_job(1)], 3), _page([], 3)])
    monkeypatch.setattr(phenom, "post_json", lambda *a, **k: next(pages))
    result = phenom.fetch(BOARD)
    assert result.ok and result.raw_count == 1
    assert result.truncated


def test_page_offset_uses_the_count_actually_returned(monkeypatch):
    jobs = [_job(i) for i in range(5)]
    starts = []
    def fetch(url, payload):
        starts.append(payload["from"])
        return _page(jobs[payload["from"]:payload["from"]+2], 5)
    monkeypatch.setattr(phenom, "post_json", fetch)
    result = phenom.fetch(BOARD)
    assert result.ok and not result.truncated
    assert starts == [0, 2, 4]
    assert [o.title for o in result.opportunities] == [f"Intern {i}" for i in range(5)]


def test_repeated_page_cannot_satisfy_the_reported_total(monkeypatch):
    monkeypatch.setattr(phenom, "_PAGE_SIZE", 2)
    monkeypatch.setattr(phenom, "post_json", lambda *a, **k: _page([_job(1), _job(2)], 4))
    result = phenom.fetch(BOARD)
    assert result.ok and len(result.opportunities) == 2
    assert result.truncated


@pytest.mark.parametrize("body", [[], {"refineSearch": []}, {"refineSearch": {"totalHits": 0, "data": {}}}])
def test_unreadable_envelope_is_reported_without_raising(monkeypatch, body):
    monkeypatch.setattr(phenom, "post_json", lambda *a, **k: body)
    result = phenom.fetch(BOARD)
    assert not result.ok and result.error
    assert not result.empty_state
