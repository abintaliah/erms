from datetime import date

import pytest

from frontend.webui.retention_timeline import disposition_dates


@pytest.mark.parametrize('closed,current,intermediate,expected', [
    ('2026-09-30T00:00:00Z', 2, 3, date(2031, 9, 30)),
    ('2024-02-29T00:00:00Z', 1, 0, date(2025, 2, 28)),
    ('2024-02-29T00:00:00Z', 1, 3, date(2028, 2, 29)),
    ('2026-09-30T22:00:00Z', 0, 0, date(2026, 10, 1)),
])
def test_calendar_years_in_working_timezone(closed, current, intermediate, expected):
    rule = dict(current_period_years=current, intermediate_period_years=intermediate)
    dates = disposition_dates(rule, {'date_closed': closed}, 'Asia/Dubai')
    assert dates[1] == expected


@pytest.mark.parametrize('root', [None, {}, {'date_closed': None}])
def test_no_date_for_open_or_unavailable_root(root):
    assert disposition_dates(dict(current_period_years=2, intermediate_period_years=3), root, 'UTC') is None


@pytest.mark.parametrize('period', [None, -1, '2', True])
def test_no_fabricated_date_for_invalid_period(period):
    assert disposition_dates(dict(current_period_years=period, intermediate_period_years=3),
                             {'date_closed': '2026-09-30T00:00:00Z'}, 'UTC') is None
