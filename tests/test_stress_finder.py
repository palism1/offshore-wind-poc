"""Tests for stress-window detection. Quotes Architecture Step 2:
    "find X or more consecutive days above the severity percentile".
"""

from datetime import date, timedelta

from owr.models import HOURS_PER_DAY, DayProfile
from owr.stress_finder import find_stress_windows, percentile_threshold


def _day(day_index: int, flat_load_mw: float) -> DayProfile:
    return DayProfile(
        date=date(2026, 1, 1) + timedelta(days=day_index),
        hourly_load_mw=(flat_load_mw,) * HOURS_PER_DAY,
    )


def test_percentile_linear_interpolation():
    # matches numpy default 'linear': p50 of [1,2,3,4] = 2.5
    assert percentile_threshold([1, 2, 3, 4], 0.5) == 2.5
    assert percentile_threshold([10], 0.9) == 10


def test_finds_a_single_multi_day_window():
    # loads: low, HIGH, HIGH, HIGH, low  -> one 3-day window at 90th percentile
    loads = [10, 100, 100, 100, 10]
    days = [_day(i, v) for i, v in enumerate(loads)]
    windows = find_stress_windows(days, severity_percentile=0.9, min_window_days=2)
    assert len(windows) == 1
    assert windows[0].days == 3
    assert windows[0].start == date(2026, 1, 2)
    assert windows[0].end == date(2026, 1, 4)


def test_short_runs_below_min_window_are_ignored():
    # single spiked day cannot satisfy min_window_days=2
    loads = [10, 100, 10, 10, 10]
    days = [_day(i, v) for i, v in enumerate(loads)]
    assert find_stress_windows(days, severity_percentile=0.9, min_window_days=2) == []


def test_trailing_window_at_series_end_is_captured():
    loads = [10, 10, 100, 100]
    days = [_day(i, v) for i, v in enumerate(loads)]
    windows = find_stress_windows(days, severity_percentile=0.75, min_window_days=2)
    assert len(windows) == 1
    assert windows[0].end == date(2026, 1, 4)
