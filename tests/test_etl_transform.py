"""Tests for threshold/window orchestration (docs/archive/plans/PLAN_EIA_EXTRACTOR.md Phase B3)."""

from __future__ import annotations

from datetime import date

import pytest

from owr.etl.daily import DailyLoad, daily_frame
from owr.etl.seasons import Season
from owr.etl.transform import (
    EVENT_FRAME_COLUMNS,
    add_season_columns,
    compute_threshold,
    find_windows_per_winter,
    winter_labels,
)
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


def _frame(days: list[DailyLoad]):
    return add_season_columns(daily_frame(days))


def test_compute_threshold_matches_hand_computed_p90():
    values = [100_000.0 + i * 1000 for i in range(20)]
    days = [_day(date(2021, 12, 1 + i), v) for i, v in enumerate(values)]
    result = compute_threshold(_frame(days), percentile=0.9, season=Season.WINTER)
    expected = percentile_threshold(values, 0.9)
    assert result.threshold_mwh == pytest.approx(expected)
    assert result.population_days == 20


def test_summer_and_shoulder_days_excluded_from_winter_population():
    winter_days = [_day(date(2021, 12, 1 + i), 100_000.0 + i * 1000) for i in range(20)]
    summer_days = [_day(date(2022, 7, 1 + i), 999_999.0) for i in range(5)]
    shoulder_days = [_day(date(2022, 4, 1 + i), 999_999.0) for i in range(5)]
    result = compute_threshold(
        _frame(winter_days + summer_days + shoulder_days), percentile=0.9, season=Season.WINTER
    )
    assert result.population_days == 20
    assert result.max_mwh < 999_999.0


def test_incomplete_days_excluded_from_population_and_listed():
    days = [_day(date(2021, 12, 1 + i), 100_000.0 + i * 1000) for i in range(20)]
    days[5] = _day(date(2021, 12, 6), 999_999.0, complete=False)
    result = compute_threshold(_frame(days), percentile=0.9, season=Season.WINTER)
    assert result.population_days == 19
    assert date(2021, 12, 6) in result.excluded_incomplete


def test_blocking_case_excluded_day_splits_run_not_merges():
    # A five-day stressed run Dec 10-14; day 3 (Dec 12) excluded as incomplete.
    days = [_day(date(2021, 12, 1 + i), 10_000.0) for i in range(30)]
    for i, d in enumerate([date(2021, 12, 10 + k) for k in range(5)]):
        days[9 + i] = _day(d, 500_000.0, complete=(d != date(2021, 12, 12)))
    threshold = 400_000.0
    events = find_windows_per_winter(_frame(days), threshold_mwh=threshold, min_window_days=2)
    winter_events = events[events["winter_label"] == "2021/22"]
    assert len(winter_events.index) == 2
    assert all(winter_events["event_duration_days"] == 2)


def test_naive_concatenation_direct_produces_two_runs():
    winter_a_end = _day(date(2022, 2, 28), 500_000.0)
    winter_b_start = _day(date(2022, 12, 1), 500_000.0)
    days = [winter_a_end, winter_b_start]
    windows = find_stress_windows_at_threshold(days, threshold=400_000.0, min_window_days=1)
    assert len(windows) == 2


def test_grouping_in_practice_separates_winters():
    winter_a = [_day(date(2022, 2, 25 + i), 500_000.0) for i in range(4)]  # 25,26,27,28
    winter_b = [_day(date(2022, 12, 1 + i), 500_000.0) for i in range(4)]
    events = find_windows_per_winter(
        _frame(winter_a + winter_b), threshold_mwh=400_000.0, min_window_days=2
    )
    assert set(events["winter_label"]) == {"2021/22", "2022/23"}
    a_events = events[events["winter_label"] == "2021/22"]
    b_events = events[events["winter_label"] == "2022/23"]
    assert len(a_events.index) == 1
    assert a_events["event_duration_days"].iloc[0] == 4
    assert len(b_events.index) == 1
    assert b_events["event_duration_days"].iloc[0] == 4


def test_pooled_threshold_not_per_group():
    low_winter = [_day(date(2021, 12, 1 + i), 50_000.0 + i) for i in range(30)]
    high_winter = [_day(date(2022, 12, 1 + i), 500_000.0 + i) for i in range(30)]
    pooled = compute_threshold(
        _frame(low_winter + high_winter), percentile=0.9, season=Season.WINTER
    )
    low_events = find_windows_per_winter(
        _frame(low_winter), threshold_mwh=pooled.threshold_mwh, min_window_days=2
    )
    assert low_events[low_events["winter_label"] == "2021/22"].empty


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


def test_etl_path_leaves_severity_percentile_none():
    # Pins the split between the StressWindow object and the ETL event frame
    # (docs/archive/plans/PLAN_ARCH_0805_SYNC.md decision D9): find_windows_per_winter calls
    # find_stress_windows_at_threshold exactly as below, with no percentile named,
    # so severity_percentile stays None on the object even though threshold_mwh is
    # set. peak_hourly_load_mw is never enriched on the ETL path either.
    days = [_day(date(2021, 12, 1 + i), 500_000.0) for i in range(3)]
    windows = find_stress_windows_at_threshold(days, threshold=400_000.0, min_window_days=2)
    assert windows[0].severity_percentile is None
    assert windows[0].threshold_mwh == 400_000.0
    assert windows[0].peak_hourly_load_mw is None


def test_event_frame_columns_and_dtypes():
    days = [_day(date(2021, 12, 1 + i), 500_000.0) for i in range(3)]
    events = find_windows_per_winter(_frame(days), threshold_mwh=400_000.0, min_window_days=2)
    assert tuple(events.columns) == EVENT_FRAME_COLUMNS
    assert events["winter_label"].dtype == object
    assert events["event_duration_days"].dtype == "int64"
    assert isinstance(events["event_start_date"].iloc[0], date)
    assert isinstance(events["event_end_date"].iloc[0], date)


def test_event_frame_is_empty_with_declared_columns_when_no_run_qualifies():
    days = [_day(date(2021, 12, 1 + i), 10_000.0) for i in range(3)]
    events = find_windows_per_winter(_frame(days), threshold_mwh=400_000.0, min_window_days=2)
    assert len(events.index) == 0
    assert tuple(events.columns) == EVENT_FRAME_COLUMNS
    assert events["event_duration_days"].dtype == "int64"


def test_threshold_result_fields_are_builtin_floats():
    days = [_day(date(2021, 12, 1 + i), 100_000.0 + i * 1000) for i in range(20)]
    result = compute_threshold(_frame(days), percentile=0.9, season=Season.WINTER)
    assert type(result.threshold_mwh) is float
    assert type(result.population_days) is int


def test_add_season_columns_does_not_mutate_the_input():
    days = [_day(date(2021, 12, 1 + i), 100_000.0) for i in range(3)]
    base = daily_frame(days)
    before = tuple(base.columns)
    add_season_columns(base)
    assert tuple(base.columns) == before


def test_winter_labels_includes_a_winter_with_no_complete_day():
    complete_winter = [_day(date(2021, 12, 1 + i), 100_000.0) for i in range(5)]
    all_incomplete_winter = [
        _day(date(2022, 12, 1 + i), 100_000.0, complete=False) for i in range(5)
    ]
    labels = winter_labels(_frame(complete_winter + all_incomplete_winter))
    assert "2021/22" in labels
    assert "2022/23" in labels
