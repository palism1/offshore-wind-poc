"""Tests for `owr.peak_window` — the 3-hour rolling peak-window finder.

Identification only; no peak-shaving or ramp-reduction formula is applied here.
"""

from __future__ import annotations

import pytest

from owr.models import DayProfile, WrapConvention
from owr.peak_window import (
    find_peak_window,
    find_peak_window_for_day,
    find_peak_windows_over_days,
)
from owr.scenario_input import read_day_profiles

EXAMPLE = "examples/synthetic_winter_stress.csv"


def _flat_day(value: float = 100.0, *, date_="2026-01-06"):
    from datetime import date

    y, m, d = (int(x) for x in date_.split("-"))
    return DayProfile(date=date(y, m, d), hourly_load_mw=(value,) * 24)


# --------------------------------------------------------------------------- #
# find_peak_window: locating
# --------------------------------------------------------------------------- #


def test_clear_single_peak():
    loads = [100.0] * 24
    loads[17] = 500.0
    loads[18] = 600.0
    loads[19] = 550.0
    window = find_peak_window(loads, window_hours=3)
    assert window.start_hour == 17
    assert window.clock_hours == (17, 18, 19)
    assert window.load_mwh == pytest.approx(sum(loads[17:20]))
    assert window.wrapped is False


def test_flat_day_ties_to_earliest_start():
    window = find_peak_window([100.0] * 24, window_hours=3)
    assert window.start_hour == 0


def test_two_tied_triplets_earliest_wins():
    loads = [0.0] * 24
    loads[5:8] = [10.0, 10.0, 10.0]
    loads[15:18] = [10.0, 10.0, 10.0]
    window = find_peak_window(loads, window_hours=3)
    assert window.start_hour == 5


# --------------------------------------------------------------------------- #
# find_peak_window: conventions, via next_hours
# --------------------------------------------------------------------------- #


def _hours_22_23_high_next_00_higher():
    loads = [100.0] * 24
    loads[22] = 200.0
    loads[23] = 200.0
    next_hours = [300.0]
    return loads, next_hours


def test_stop_at_midnight_ignores_next_hours():
    loads, _ = _hours_22_23_high_next_00_higher()
    window = find_peak_window(loads, window_hours=3, next_hours=())
    assert window.candidates_considered == 22
    assert window.wrapped is False
    assert window.clock_hours == (21, 22, 23)


def test_wrap_to_next_day_with_next_hours():
    loads, next_hours = _hours_22_23_high_next_00_higher()
    window = find_peak_window(loads, window_hours=3, next_hours=next_hours)
    assert window.candidates_considered == 23
    assert window.wrapped is True
    assert window.start_hour == 22
    assert window.clock_hours == (22, 23, 0)


# --------------------------------------------------------------------------- #
# find_peak_window: window size and validation
# --------------------------------------------------------------------------- #


def test_window_hours_1_returns_single_max_hour():
    loads = [100.0] * 24
    loads[10] = 999.0
    window = find_peak_window(loads, window_hours=1)
    assert window.start_hour == 10
    assert window.clock_hours == (10,)


def test_window_hours_24_returns_whole_day():
    loads = list(range(24))
    window = find_peak_window([float(x) for x in loads], window_hours=24)
    assert window.start_hour == 0
    assert window.candidates_considered == 1


@pytest.mark.parametrize("window_hours", [0, -1, 25])
def test_invalid_window_hours_raises(window_hours):
    with pytest.raises(ValueError):
        find_peak_window([100.0] * 24, window_hours=window_hours)


@pytest.mark.parametrize("n", [23, 25])
def test_invalid_hourly_load_length_raises(n):
    with pytest.raises(ValueError):
        find_peak_window([100.0] * n, window_hours=3)


def test_next_hours_too_long_raises():
    with pytest.raises(ValueError):
        find_peak_window([100.0] * 24, window_hours=3, next_hours=[1.0] * 25)


# --------------------------------------------------------------------------- #
# find_peak_window_for_day
# --------------------------------------------------------------------------- #


def test_find_peak_window_for_day_stop_at_midnight():
    day = _flat_day()
    window = find_peak_window_for_day(
        day, None, window_hours=3, wrap=WrapConvention.STOP_AT_MIDNIGHT
    )
    assert window.candidates_considered == 22
    assert window.wrapped is False


def test_find_peak_window_for_day_wrap_with_no_next_day():
    day = _flat_day()
    window = find_peak_window_for_day(
        day, None, window_hours=3, wrap=WrapConvention.WRAP_TO_NEXT_DAY
    )
    assert window.candidates_considered == 22
    assert window.wrapped is False


def test_find_peak_window_for_day_wrap_with_non_adjacent_next_day():
    from datetime import date

    day = _flat_day(date_="2026-01-06")
    non_adjacent = DayProfile(date=date(2026, 1, 8), hourly_load_mw=(999.0,) * 24)
    window = find_peak_window_for_day(
        day, non_adjacent, window_hours=3, wrap=WrapConvention.WRAP_TO_NEXT_DAY
    )
    assert window.candidates_considered == 22
    assert window.wrapped is False


def test_find_peak_window_for_day_wrap_with_adjacent_next_day():
    from datetime import date

    loads, _ = _hours_22_23_high_next_00_higher()
    day = DayProfile(date=date(2026, 1, 6), hourly_load_mw=tuple(loads))
    next_day = DayProfile(date=date(2026, 1, 7), hourly_load_mw=(300.0,) + (100.0,) * 23)
    window = find_peak_window_for_day(
        day, next_day, window_hours=3, wrap=WrapConvention.WRAP_TO_NEXT_DAY
    )
    assert window.candidates_considered == 23
    assert window.wrapped is True
    assert window.start_hour == 22
    assert window.clock_hours == (22, 23, 0)


# --------------------------------------------------------------------------- #
# Against the shipped example
# --------------------------------------------------------------------------- #


def _example_days():
    with open(EXAMPLE) as f:
        return read_day_profiles(f, origin=EXAMPLE).days


EXPECTED_STOP_AT_MIDNIGHT_START_HOURS = [0, 0, 0, 16, 17, 16]
EXPECTED_WRAP_START_HOURS = [22, 22, 22, 16, 17, 16]


def test_example_stop_at_midnight_start_hours():
    days = _example_days()
    results = find_peak_windows_over_days(
        days, window_hours=3, wrap=WrapConvention.STOP_AT_MIDNIGHT
    )
    assert [w.start_hour for _, w in results] == EXPECTED_STOP_AT_MIDNIGHT_START_HOURS
    for _, w in results:
        assert w.wrapped is False


def test_example_wrap_to_next_day_start_hours():
    days = _example_days()
    results = find_peak_windows_over_days(
        days, window_hours=3, wrap=WrapConvention.WRAP_TO_NEXT_DAY
    )
    assert [w.start_hour for _, w in results] == EXPECTED_WRAP_START_HOURS
    # mild days (0-2) wrap into the next day; cold days (3-4) don't need to; the
    # last day (5) has no successor so it cannot wrap even though the convention allows it.
    assert [w.wrapped for _, w in results] == [True, True, True, False, False, False]
    assert results[5][1].candidates_considered == 22


def test_example_returns_six_entries_in_input_order():
    days = _example_days()
    results = find_peak_windows_over_days(
        days, window_hours=3, wrap=WrapConvention.WRAP_TO_NEXT_DAY
    )
    assert len(results) == 6
    assert [d for d, _ in results] == [day.date for day in days]


# --------------------------------------------------------------------------- #
# find_peak_windows_over_days: window size 1 edge case
# --------------------------------------------------------------------------- #


def test_find_peak_windows_over_days_empty_list():
    assert (
        find_peak_windows_over_days([], window_hours=3, wrap=WrapConvention.WRAP_TO_NEXT_DAY) == []
    )
