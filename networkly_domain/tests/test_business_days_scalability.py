"""Cadence weekday counts retain exact boundaries across long histories."""

from datetime import date, timedelta

from networkly_domain.cadence import business_days_since


def test_weekday_arithmetic_matches_day_by_day_reference():
    monday = date(2026, 9, 7)
    for weekday in range(7):
        start = monday + timedelta(days=weekday)
        expected = 0
        for elapsed in range(401):
            end = start + timedelta(days=elapsed)
            if elapsed and end.weekday() < 5:
                expected += 1
            assert business_days_since(start, end) == expected
        assert business_days_since(start, start - timedelta(days=1)) == 0


def test_full_supported_date_span_is_counted_without_day_iteration():
    # date.min is Monday; the span has 521722 full weeks and four weekdays.
    assert business_days_since(date.min, date.max) == 2_608_614
