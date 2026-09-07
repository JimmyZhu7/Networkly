"""Display folding must not hide materially different eligibility requirements."""
from types import SimpleNamespace

import pytest

from directory.dupes import fold_duplicates, fold_families


def _row(i, **fields):
    return SimpleNamespace(**dict(id=i, firm_id=1, title='Summer Analyst', location='New York',
        deadline=None, cohort='2027', sponsorship='unknown', first_seen=None,
        bucket=fields.pop('bucket', 'internship'), class_year=fields.pop('class_year', ''),
        raw=fields.pop('raw', {}), **fields))


def _fold(rows, mode):
    if mode == 'duplicates':
        return fold_duplicates(rows)[0]
    return fold_families(rows, lambda row: 'same-role-family')[0]


@pytest.mark.parametrize('mode', ['duplicates', 'families'])
@pytest.mark.parametrize('left,right', [
    ({'class_year': '2027'}, {'class_year': '2028'}),
    ({'raw': {'facts': {'grad': {'years': ['2027', '2028']}}}}, {'raw': {'facts': {'grad': {'years': ['2028', '2029']}}}}),
    ({'raw': {'facts': {'grad': {'years': ['2027'], 'open_high': True}}}}, {'class_year': '2027'}),
    ({'bucket': 'internship'}, {'bucket': 'entry_level'}),
])
def test_different_eligibility_evidence_keeps_both_postings(mode, left, right):
    rows = [_row(1, **left), _row(2, **right)]
    assert _fold(rows, mode) == rows


@pytest.mark.parametrize('mode', ['duplicates', 'families'])
def test_equivalent_or_missing_graduation_evidence_still_folds(mode):
    rows = [_row(1, class_year='2027'), _row(2, raw={'facts': {'grad': {'years': ['2027']}}}), _row(3)]
    assert _fold(rows, mode) == [rows[0]]
