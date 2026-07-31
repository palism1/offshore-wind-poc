"""Tests for threshold/window orchestration (docs/PLAN_EIA_EXTRACTOR.md Phase B3)."""

from __future__ import annotations

from datetime import date

import pytest

from owr.etl.daily import DailyLoad
from owr.etl.seasons import Season
from owr.etl.transform import compute_threshold, find_windows_per_winter
from owr.stress_finder import find_stress_windows_at_threshold, percentile_threshold


def _day(d: date, load_mwh: float, *, complete: bool = True) -> DailyLoad:
    return DailyLoad(
        date=d,
        load_mwh=load_mwh,
        hours_covered=24.0 if complete else 22.0,
        expected_hours=24.0,
        intervals=288,
        complete=complete,
    )


def _winter_2021_22() -> list[DailyLoad]:
    """20 winter days, Dec 2021 -> Jan 2022, ascending load."""
    days = []
    d = date(2021, 12, 12)
    for i in range(20):
        days.append(_day(d, load_mwh=100_000.0 + i * 1000))
        d = date(2021, 12, 12) if i == 19 else d
        # advance date by one day each iteration
    # rebuild with proper sequential dates
    days = [
        _day(date(2021, 12, 12) if i < 19 else date(2022, 1, 1), 100_000.0 + i * 1000)
        for i in range(20)
    ]
    return days


def test_compute_threshold_matches_hand_computed_p90():
    values = [100_000.0 + i * 1000 for i in range(20)]
    days = [_day(date(2021, 12, 1), v) for v in values]
    # give each a distinct date
    days = [
        _day(date(2021, 12, 1).replace(day=min(1 + i, 31)) if i < 20 else None, v)
        for i, v in enumerate(values)
    ]
    # simpler: sequential December dates
    days = [_day(date(2021, 12, 1 + i), v) for i, v in enumerate(values)]
    result = compute_threshold(days, percentile=0.9, season=Season.WINTER)
    expected = percentile_threshold(values, 0.9)
    assert result.threshold_mwh == pytest.approx(expected)
    assert result.population_days == 20


def test_summer_and_shoulder_days_excluded_from_winter_population():
    winter_days = [_day(date(2021, 12, 1 + i), 100_000.0 + i * 1000) for i in range(20)]
    summer_days = [_day(date(2022, 7, 1 + i), 999_999.0) for i in range(5)]
    shoulder_days = [_day(date(2022, 4, 1 + i), 999_999.0) for i in range(5)]
    result = compute_threshold(
        winter_days + summer_days + shoulder_days, percentile=0.9, season=Season.WINTER
    )
    assert result.population_days == 20
    assert result.max_mwh < 999_999.0


def test_incomplete_days_excluded_from_population_and_listed():
    days = [_day(date(2021, 12, 1 + i), 100_000.0 + i * 1000) for i in range(20)]
    days[5] = _day(date(2021, 12, 6), 999_999.0, complete=False)
    result = compute_threshold(days, percentile=0.9, season=Season.WINTER)
    assert result.population_days == 19
    assert date(2021, 12, 6) in result.excluded_incomplete


def test_blocking_case_excluded_day_splits_run_not_merges():
    # A five-day stressed run Dec 10-14; day 3 (Dec 12) excluded as incomplete.
    days = [_day(date(2021, 12, 1 + i), 10_000.0) for i in range(30)]
    for i, d in enumerate([date(2021, 12, 10 + k) for k in range(5)]):
        days[9 + i] = _day(d, 500_000.0, complete=(d != date(2021, 12, 12)))
    threshold = 400_000.0
    windows = find_windows_per_winter(days, threshold_mwh=threshold, min_window_days=2)
    assert "2021/22" in windows
    winter_windows = windows["2021/22"]
    assert len(winter_windows) == 2
    assert all(w.days == 2 for w in winter_windows)


def test_naive_concatenation_direct_produces_two_runs():
    winter_a_end = _day(date(2022, 2, 28), 500_000.0)
    winter_b_start = _day(date(2022, 12, 1), 500_000.0)
    days = [winter_a_end, winter_b_start]
    windows = find_stress_windows_at_threshold(days, threshold=400_000.0, min_window_days=1)
    assert len(windows) == 2


def test_grouping_in_practice_separates_winters():
    winter_a = [_day(date(2022, 2, 25 + i), 500_000.0) for i in range(4)]  # 25,26,27,28
    winter_b = [_day(date(2022, 12, 1 + i), 500_000.0) for i in range(4)]
    windows = find_windows_per_winter(
        winter_a + winter_b, threshold_mwh=400_000.0, min_window_days=2
    )
    assert set(windows) == {"2021/22", "2022/23"}
    assert len(windows["2021/22"]) == 1
    assert windows["2021/22"][0].days == 4
    assert len(windows["2022/23"]) == 1
    assert windows["2022/23"][0].days == 4


def test_pooled_threshold_not_per_group():
    low_winter = [_day(date(2021, 12, 1 + i), 50_000.0 + i) for i in range(30)]
    high_winter = [_day(date(2022, 12, 1 + i), 500_000.0 + i) for i in range(30)]
    pooled = compute_threshold(low_winter + high_winter, percentile=0.9, season=Season.WINTER)
    low_windows = find_windows_per_winter(
        low_winter, threshold_mwh=pooled.threshold_mwh, min_window_days=2
    )
    assert low_windows.get("2021/22", []) == []


def test_min_window_days_excludes_or_includes_isolated_days():
    days = [_day(date(2021, 12, 1 + i), 10_000.0) for i in range(10)]
    days[5] = _day(date(2021, 12, 6), 500_000.0)
    windows_2 = find_stress_windows_at_threshold(days, threshold=400_000.0, min_window_days=2)
    windows_1 = find_stress_windows_at_threshold(days, threshold=400_000.0, min_window_days=1)
    assert windows_2 == []
    assert len(windows_1) == 1


def test_dailyload_accepted_by_find_stress_windows_at_threshold():
    days = [_day(date(2021, 12, 1 + i), 500_000.0) for i in range(3)]
    windows = find_stress_windows_at_threshold(days, threshold=400_000.0, min_window_days=2)
    assert len(windows) == 1
    assert windows[0].days == 3
