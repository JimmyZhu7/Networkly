"""Malformed or partial provider replies must not falsely verify or close jobs."""
import pytest
from networkly_connectors import greenhouse, lever, workday
from networkly_connectors.models import GreenhouseBoard


@pytest.mark.parametrize("payload", [{}, {"error": "rate limited"}, {"title": "Analyst", "id": 2}, {"title": "Analyst", "id": 1, "updated_at": []}])
def test_greenhouse_unreadable_or_wrong_job_never_verifies(monkeypatch, payload):
    monkeypatch.setattr(greenhouse, "fetch_json", lambda *a, **k: payload)
    result = greenhouse.verify("https://boards.greenhouse.io/bank/jobs/1")
    assert result.result == "needs-verification"


def test_greenhouse_bare_list_is_supported_and_partial_total_is_flagged(monkeypatch):
    job = {"id": 1, "title": "Analyst", "absolute_url": "https://bank.example/jobs/1"}
    board = GreenhouseBoard(firm="Bank", token="bank")
    monkeypatch.setattr(greenhouse, "fetch_json", lambda *a, **k: [job])
    result = greenhouse.fetch(board)
    assert result.ok and result.raw_count == 1 and not result.truncated
    monkeypatch.setattr(greenhouse, "fetch_json", lambda *a, **k: {"jobs": [job], "meta": {"total": 2}})
    result = greenhouse.fetch(board)
    assert result.ok and result.truncated and result.raw_count == 1


@pytest.mark.parametrize("payload", [{}, {"error": "denied"}, [None], [{"text": None}], [{"text": ""}]])
def test_lever_error_envelopes_never_mean_closed_or_open(monkeypatch, payload):
    monkeypatch.setattr(lever, "fetch_json", lambda *a, **k: payload)
    assert lever.verify("https://jobs.lever.co/bank/posting").result == "needs-verification"


@pytest.mark.parametrize("payload", [{}, {"total": 0}, {"total": 1, "jobPostings": []}, {"total": "0", "jobPostings": []}, {"total": 0, "jobPostings": [{"title": "Analyst"}]}])
def test_workday_unreadable_or_inconsistent_search_never_closes(monkeypatch, payload):
    monkeypatch.setattr(workday, "_fetch_all", lambda *a, **k: payload)
    result = workday.verify("https://bank.wd1.myworkdayjobs.com/Careers?q=123")
    assert result.result == "needs-verification"
