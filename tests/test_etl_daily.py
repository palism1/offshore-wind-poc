"""Tests for interval-to-daily energy integration (docs/PLAN_EIA_EXTRACTOR.md Phase B2)."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta

import pytest

from owr.etl.daily import (
    DAILY_CORE_COLUMNS,
    EASTERN,
    IntervalReading,
    daily_frame,
    daily_loads_from_readings,
    local_day_hours,
)


def _local_midnight_utc(day: date) -> datetime:
    """UTC instant of local Eastern midnight on ``day`` (unambiguous at 00:00)."""
    return datetime.combine(day, time(0), tzinfo=EASTERN).astimezone(UTC)


def _five_minute_readings_for_local_day(
    day: date, load_mw: float = 1000.0
) -> list[IntervalReading]:
    """Synthetic 5-minute readings spanning exactly local calendar day ``day``,
    built from UTC absolute instants so DST transitions are handled correctly by
    construction (rather than relying on wall-clock arithmetic across a fold)."""
    start = _local_midnight_utc(day)
    end = _local_midnight_utc(day + timedelta(days=1))
    readings = []
    ts = start
    step = timedelta(minutes=5)
    while ts < end:
        readings.append(IntervalReading(ts=ts, load_mw=load_mw, interval_hours=5 / 60))
        ts += step
    return readings


def test_twelve_readings_of_1000mw_at_5min_grain_over_one_hour():
    start = datetime(2025, 6, 10, 12, tzinfo=UTC)
    readings = [
        IntervalReading(ts=start + timedelta(minutes=5 * i), load_mw=1000.0, interval_hours=5 / 60)
        for i in range(12)
    ]
    days = daily_loads_from_readings(readings)
    assert len(days) == 1
    assert days[0].load_mwh == pytest.approx(1000.0)


def test_mixed_grains_integrate_correctly():
    start = datetime(2025, 6, 10, 12, tzinfo=UTC)
    readings = [
        IntervalReading(ts=start, load_mw=1000.0, interval_hours=5 / 60),
        IntervalReading(ts=start + timedelta(minutes=5), load_mw=1000.0, interval_hours=55 / 60),
    ]
    days = daily_loads_from_readings(readings)
    assert len(days) == 1
    # 1000*5/60 + 1000*55/60 = 1000.0 MWh total, over a 1-hour span
    assert days[0].load_mwh == pytest.approx(1000.0)
    assert days[0].hours_covered == pytest.approx(1.0)


def test_spring_forward_2025_03_09_is_23_hours_and_complete():
    day = date(2025, 3, 9)
    readings = _five_minute_readings_for_local_day(day, load_mw=1200.0)
    assert len(readings) == 276
    days = daily_loads_from_readings(readings)
    assert len(days) == 1
    result = days[0]
    assert result.date == day
    assert result.hours_covered == pytest.approx(23.0)
    assert result.expected_hours == pytest.approx(23.0)
    assert result.complete is True
    assert result.load_mwh == pytest.approx(sum(1200.0 for _ in readings) / 12)


def test_fall_back_2025_11_02_is_25_hours_and_complete():
    day = date(2025, 11, 2)
    readings = _five_minute_readings_for_local_day(day, load_mw=900.0)
    assert len(readings) == 300
    days = daily_loads_from_readings(readings)
    assert len(days) == 1
    result = days[0]
    assert result.hours_covered == pytest.approx(25.0)
    assert result.expected_hours == pytest.approx(25.0)
    assert result.complete is True


def test_ordinary_day_2025_06_10_is_24_hours():
    day = date(2025, 6, 10)
    readings = _five_minute_readings_for_local_day(day)
    assert len(readings) == 288
    days = daily_loads_from_readings(readings)
    assert days[0].hours_covered == pytest.approx(24.0)
    assert days[0].expected_hours == pytest.approx(24.0)


def test_local_day_hours_around_dst():
    assert local_day_hours(date(2025, 3, 9)) == pytest.approx(23.0)
    assert local_day_hours(date(2025, 6, 10)) == pytest.approx(24.0)
    assert local_day_hours(date(2025, 11, 2)) == pytest.approx(25.0)


def test_local_date_grouping_across_utc_midnight():
    # 2025-01-01T02:30Z is 2024-12-31 21:30 Eastern (winter, UTC-5).
    reading = IntervalReading(
        ts=datetime(2025, 1, 1, 2, 30, tzinfo=UTC), load_mw=100.0, interval_hours=5 / 60
    )
    days = daily_loads_from_readings([reading])
    assert days[0].date == date(2024, 12, 31)


def test_naive_timestamp_raises_naming_the_ts():
    reading = IntervalReading(ts=datetime(2025, 1, 1, 0, 0), load_mw=1.0, interval_hours=1.0)
    with pytest.raises(ValueError, match="2025-01-01"):
        daily_loads_from_readings([reading])


def test_duplicate_absolute_instant_raises_naming_the_ts():
    ts = datetime(2025, 1, 1, 0, 0, tzinfo=UTC)
    readings = [
        IntervalReading(ts=ts, load_mw=1.0, interval_hours=1.0),
        IntervalReading(ts=ts, load_mw=2.0, interval_hours=1.0),
    ]
    with pytest.raises(ValueError, match=re.escape(ts.isoformat())):
        daily_loads_from_readings(readings)


def test_unsorted_input_matches_sorted_result():
    start = datetime(2025, 6, 10, 0, tzinfo=UTC)
    ordered = [
        IntervalReading(ts=start + timedelta(hours=i), load_mw=float(i), interval_hours=1.0)
        for i in range(24)
    ]
    shuffled = list(reversed(ordered))
    assert daily_loads_from_readings(shuffled) == daily_loads_from_readings(ordered)


def test_day_missing_two_hours_is_incomplete():
    day = date(2025, 6, 10)
    readings = _five_minute_readings_for_local_day(day)
    # drop the last 24 5-minute readings (2 hours)
    trimmed = readings[:-24]
    days = daily_loads_from_readings(trimmed)
    assert days[0].complete is False
    assert days[0].hours_covered == pytest.approx(22.0)


def test_daily_frame_columns_dtypes_and_row_order():
    start = datetime(2025, 6, 10, 0, tzinfo=UTC)
    readings = [
        IntervalReading(ts=start + timedelta(days=d, hours=h), load_mw=100.0, interval_hours=1.0)
        for d in range(3)
        for h in range(24)
    ]
    days = daily_loads_from_readings(readings)
    frame = daily_frame(days)
    assert tuple(frame.columns) == DAILY_CORE_COLUMNS
    assert frame["date"].dtype == object
    assert frame["load_mwh"].dtype == "float64"
    assert frame["hours_covered"].dtype == "float64"
    assert frame["expected_hours"].dtype == "float64"
    assert frame["intervals"].dtype == "int64"
    assert frame["complete"].dtype == "bool"
    assert list(frame["date"]) == [d.date for d in days]


def test_daily_frame_date_column_holds_date_objects():
    readings = [
        IntervalReading(ts=datetime(2025, 6, 10, tzinfo=UTC), load_mw=1.0, interval_hours=1.0)
    ]
    days = daily_loads_from_readings(readings)
    frame = daily_frame(days)
    assert isinstance(frame["date"].iloc[0], date)
    assert not isinstance(frame["date"].iloc[0], datetime)


def test_daily_frame_empty_input_has_declared_columns():
    frame = daily_frame([])
    assert len(frame.index) == 0
    assert tuple(frame.columns) == DAILY_CORE_COLUMNS
    assert frame["load_mwh"].dtype == "float64"
    assert frame["intervals"].dtype == "int64"
    assert frame["complete"].dtype == "bool"
