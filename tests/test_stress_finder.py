"""Tests for stress-window detection. Quotes Architecture Step 2:
    "find X or more consecutive days above the severity percentile".
"""

from dataclasses import dataclass
from datetime import date, timedelta

from owr.models import HOURS_PER_DAY, DayProfile
from owr.stress_finder import (
    find_stress_windows,
    find_stress_windows_at_threshold,
    percentile_threshold,
)


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


@dataclass(frozen=True)
class _Reading:
    """A minimal DailyLoadLike stand-in, for direct date-list tests."""

    date: date
    load_mwh: float


def test_date_aware_adjacency_splits_a_gap_into_two_windows():
    # dates 1, 2, 4, 5 (day-index) all stressed; day 3 absent from the list.
    days = [
        _Reading(date(2026, 1, 1), 100.0),
        _Reading(date(2026, 1, 2), 100.0),
        _Reading(date(2026, 1, 4), 100.0),
        _Reading(date(2026, 1, 5), 100.0),
    ]
    windows = find_stress_windows_at_threshold(days, threshold=100.0, min_window_days=2)
    assert len(windows) == 2
    assert windows[0].start == date(2026, 1, 1)
    assert windows[0].end == date(2026, 1, 2)
    assert windows[1].start == date(2026, 1, 4)
    assert windows[1].end == date(2026, 1, 5)


def test_isolated_day_after_a_gap_is_dropped():
    days = [
        _Reading(date(2026, 1, 1), 100.0),
        _Reading(date(2026, 1, 2), 100.0),
        _Reading(date(2026, 1, 4), 100.0),
    ]
    windows = find_stress_windows_at_threshold(days, threshold=100.0, min_window_days=2)
    assert len(windows) == 1
    assert windows[0].start == date(2026, 1, 1)
    assert windows[0].end == date(2026, 1, 2)


def test_out_of_order_input_is_not_silently_merged():
    # dates 3, 1, 2 in that order; positional adjacency (3->1) is not date-adjacent.
    days = [
        _Reading(date(2026, 1, 3), 100.0),
        _Reading(date(2026, 1, 1), 100.0),
        _Reading(date(2026, 1, 2), 100.0),
    ]
    windows = find_stress_windows_at_threshold(days, threshold=100.0, min_window_days=2)
    # documented behaviour: NOT sorted, so date(1)->date(2) is the only adjacent
    # pair (positions 1,2); date(3) at position 0 stands alone and is dropped.
    assert len(windows) == 1
    assert windows[0].start == date(2026, 1, 1)
    assert windows[0].end == date(2026, 1, 2)


def test_threshold_split_reproduces_find_stress_windows():
    loads = [10, 100, 100, 100, 10]
    days = [_day(i, v) for i, v in enumerate(loads)]
    threshold = percentile_threshold([d.load_mwh for d in days], 0.9)
    assert find_stress_windows_at_threshold(days, threshold, 2) == find_stress_windows(
        days, severity_percentile=0.9, min_window_days=2
    )
