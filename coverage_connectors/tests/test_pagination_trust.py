"""A successful HTTP response is not proof that a paginated board was complete."""
import pytest

from coverage_connectors import goldmansachs, lumesse, mckinsey, socgen
from coverage_connectors.models import GoldmanSachsBoard, LumesseBoard, McKinseyBoard, SocGenBoard


def _configure(monkeypatch, provider, batches, total, cap=20):
    pages = iter(batches)
    if provider == 'lumesse':
        monkeypatch.setattr(lumesse, '_PAGE', 1)
        monkeypatch.setattr(lumesse, '_MAX_JOBS', cap)
        def fetch(*a, **k):
            return {'globals': {'jobsCount': total}, 'jobs': [{'jobFields': {'id': i, 'jobTitle': f'Role {i}', 'applicationUrl': f'https://example.com/job/{i}'}} for i in next(pages)]}
        monkeypatch.setattr(lumesse, 'fetch_json', fetch)
        return lambda: lumesse.fetch(LumesseBoard(firm='Review Firm', host='example.com', tech_id='review'))
    if provider == 'socgen':
        monkeypatch.setattr(socgen, '_PAGE', 1)
        monkeypatch.setattr(socgen, '_MAX_JOBS', cap)
        monkeypatch.setattr(socgen, '_token', lambda: 'offline')
        monkeypatch.setattr(socgen, 'post_json', lambda *a, **k: {'TotalCount': total, 'Result': {'Docs': [{'title': f'Role {i}', 'url1': f'https://example.com/job/{i}'} for i in next(pages)]}})
        return lambda: socgen.fetch(SocGenBoard(firm='Review Firm'))
    if provider == 'mckinsey':
        monkeypatch.setattr(mckinsey, '_PAGE_SIZE', 1)
        monkeypatch.setattr(mckinsey, '_MAX_JOBS', cap)
        monkeypatch.setattr(mckinsey, '_page', lambda *a, **k: {'numFound': total, 'docs': [{'jobID': str(i), 'title': f'Role {i}', 'friendlyURL': f'role-{i}'} for i in next(pages)]})
        return lambda: mckinsey.fetch(McKinseyBoard(firm='Review Firm', keywords=('',)))
    monkeypatch.setattr(goldmansachs, '_PAGE_SIZE', 1)
    monkeypatch.setattr(goldmansachs, '_MAX_ROLES', cap)
    monkeypatch.setattr(goldmansachs, '_post', lambda *a, **k: {'totalCount': total, 'items': [{'roleId': str(i), 'jobTitle': f'Role {i}'} for i in next(pages)]})
    return lambda: goldmansachs.fetch(GoldmanSachsBoard())


@pytest.mark.parametrize('provider', ['lumesse', 'socgen', 'mckinsey', 'goldmansachs'])
@pytest.mark.parametrize('batches,total,cap,partial', [
    ([[1]], 3, 1, True),
    ([[1], []], 3, 20, True),
    ([[1], [1]], 2, 20, True),
    ([[1], [2]], 2, 20, False),
])
def test_only_a_complete_unique_board_can_prove_absence(monkeypatch, provider, batches, total, cap, partial):
    result = _configure(monkeypatch, provider, batches, total, cap)()
    assert result.ok, result.error
    assert result.truncated is partial
