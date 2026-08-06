"""Tests for the real-data bridge (docs/archive/plans/PLAN_REAL_DEMO_BRIDGE.md Phase 1)."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from owr import scenario_input
from owr.etl.daily import IntervalReading
from owr.etl.demo_profile import (
    HourlyLoad,
    hourly_loads_from_readings,
    percentile_ranks,
    render_day_profile_csv,
)


def _hourly_readings_for_day(
    date_str: str, mw: float, *, offset: str = "-05:00"
) -> list[IntervalReading]:
    """24 one-hour readings for one local calendar day, fixed winter (EST) offset."""
    return [
        IntervalReading(
            ts=datetime.fromisoformat(f"{date_str}T{hour:02d}:00:00{offset}"),
            load_mw=mw,
            interval_hours=1.0,
        )
        for hour in range(24)
    ]


def _full_day_hourly(d: date, mw: float) -> list[HourlyLoad]:
    return [
        HourlyLoad(date=d, hour=hour, load_mwh=mw, hours_covered=1.0, intervals=12)
        for hour in range(24)
    ]


# --------------------------------------------------------------------------- #
# hourly_loads_from_readings                                                  #
# --------------------------------------------------------------------------- #


def test_twelve_five_minute_readings_integrate_to_one_hour():
    mws = [100.0, 105.0, 98.0, 110.0, 102.0, 99.0, 101.0, 103.0, 97.0, 104.0, 100.0, 106.0]
    readings = [
        IntervalReading(
            ts=datetime.fromisoformat(f"2026-01-24T00:{minute:02d}:00-05:00"),
            load_mw=mw,
            interval_hours=5.0 / 60.0,
        )
        for minute, mw in zip(range(0, 60, 5), mws, strict=True)
    ]

    result = hourly_loads_from_readings(readings)

    assert len(result) == 1
    hourly = result[0]
    assert hourly.load_mwh == pytest.approx(sum(mws) / 12.0)
    assert hourly.hours_covered == pytest.approx(1.0)
    assert hourly.intervals == 12


def test_mixed_widths_integrate_not_average():
    # One 30-minute reading plus six 5-minute readings = 60 minutes covered.
    readings = [
        IntervalReading(
            ts=datetime.fromisoformat("2026-01-24T00:00:00-05:00"),
            load_mw=200.0,
            interval_hours=0.5,
        )
    ] + [
        IntervalReading(
            ts=datetime.fromisoformat(f"2026-01-24T00:{minute:02d}:00-05:00"),
            load_mw=100.0,
            interval_hours=5.0 / 60.0,
        )
        for minute in range(30, 60, 5)
    ]
    expected_integral = 200.0 * 0.5 + 100.0 * (5.0 / 60.0) * 6
    expected_mean = (200.0 + 100.0 * 6) / 7.0

    result = hourly_loads_from_readings(readings)

    assert len(result) == 1
    assert result[0].load_mwh == pytest.approx(expected_integral)
    assert result[0].load_mwh != pytest.approx(expected_mean)


def test_utc_reading_lands_on_local_date_and_hour():
    readings = [
        IntervalReading(
            ts=datetime.fromisoformat("2026-01-24T05:00:00+00:00"),
            load_mw=100.0,
            interval_hours=1.0,
        )
    ]

    result = hourly_loads_from_readings(readings)

    assert len(result) == 1
    assert result[0].date == date(2026, 1, 24)
    assert result[0].hour == 0


def test_naive_timestamp_rejected():
    readings = [
        IntervalReading(
            ts=datetime.fromisoformat("2026-01-24T00:00:00"), load_mw=100.0, interval_hours=1.0
        )
    ]

    with pytest.raises(ValueError, match="2026-01-24T00:00:00"):
        hourly_loads_from_readings(readings)


def test_duplicate_instant_rejected():
    ts = "2026-01-24T00:00:00-05:00"
    readings = [
        IntervalReading(ts=datetime.fromisoformat(ts), load_mw=100.0, interval_hours=1.0),
        IntervalReading(ts=datetime.fromisoformat(ts), load_mw=105.0, interval_hours=1.0),
    ]

    with pytest.raises(ValueError, match=ts):
        hourly_loads_from_readings(readings)


def test_empty_input_returns_empty_list():
    assert hourly_loads_from_readings([]) == []


# --------------------------------------------------------------------------- #
# percentile_ranks                                                             #
# --------------------------------------------------------------------------- #


def test_percentile_ranks_basic():
    population = [1.0, 2.0, 3.0, 4.0]
    day_totals = {date(2026, 1, 1): 3.0, date(2026, 1, 2): 4.0}

    ranks = percentile_ranks(population, day_totals)

    assert ranks[date(2026, 1, 1)] == pytest.approx(0.75)
    assert ranks[date(2026, 1, 2)] == pytest.approx(1.0)


def test_percentile_ranks_population_maximum_ranks_exactly_one():
    population = [10.0, 20.0, 30.0]
    day_totals = {date(2026, 1, 1): 30.0}

    ranks = percentile_ranks(population, day_totals)

    assert ranks[date(2026, 1, 1)] == 1.0


def test_percentile_ranks_empty_population_raises():
    with pytest.raises(ValueError):
        percentile_ranks([], {date(2026, 1, 1): 1.0})


# --------------------------------------------------------------------------- #
# render_day_profile_csv                                                      #
# --------------------------------------------------------------------------- #


def test_render_two_full_days():
    d1, d2 = date(2026, 1, 24), date(2026, 1, 25)
    hourly = _full_day_hourly(d1, 100.0) + _full_day_hourly(d2, 200.0)
    demand_percentile = {d1: 0.5, d2: 1.0}

    text = render_day_profile_csv(
        hourly, demand_percentile=demand_percentile, banner=["one", "two"]
    )

    lines = text.splitlines()
    assert lines[0] == "# one"
    assert lines[1] == "# two"
    assert lines[2] == "date,hour,load_mw,demand_percentile"
    data_lines = lines[3:]
    assert len(data_lines) == 48


def test_render_round_trip_through_scenario_input():
    d1, d2 = date(2026, 1, 24), date(2026, 1, 25)
    hourly = _full_day_hourly(d1, 100.0) + _full_day_hourly(d2, 200.0)
    demand_percentile = {d1: 0.5, d2: 1.0}

    text = render_day_profile_csv(hourly, demand_percentile=demand_percentile, banner=["banner"])
    result = scenario_input.read_day_profiles(iter(text.splitlines(keepends=True)), origin="<test>")

    assert result.demand_percentile_source == "file"
    assert result.has_wind is False
    assert len(result.days) == 2


def test_render_round_trip_load_mwh_matches_daily_integral():
    d1, d2 = date(2026, 1, 24), date(2026, 1, 25)
    hourly = _full_day_hourly(d1, 100.0) + _full_day_hourly(d2, 200.0)
    demand_percentile = {d1: 0.5, d2: 1.0}

    text = render_day_profile_csv(hourly, demand_percentile=demand_percentile, banner=["banner"])
    result = scenario_input.read_day_profiles(iter(text.splitlines(keepends=True)), origin="<test>")

    by_date = {day.date: day for day in result.days}
    assert by_date[d1].load_mwh == pytest.approx(24 * 100.0, abs=0.02)
    assert by_date[d2].load_mwh == pytest.approx(24 * 200.0, abs=0.02)


def test_render_23_hour_date_raises_and_names_dst():
    d = date(2026, 3, 8)  # a spring-forward Sunday
    hourly = [
        HourlyLoad(date=d, hour=hour, load_mwh=100.0, hours_covered=1.0, intervals=12)
        for hour in range(24)
        if hour != 2
    ]

    with pytest.raises(ValueError, match="daylight saving time") as exc_info:
        render_day_profile_csv(hourly, demand_percentile={d: 0.5}, banner=[])
    assert d.isoformat() in str(exc_info.value)


def test_render_fallback_two_hour_bucket_raises_and_names_dst():
    d = date(2026, 11, 1)  # a fall-back Sunday
    hourly = [
        HourlyLoad(date=d, hour=hour, load_mwh=100.0, hours_covered=1.0, intervals=12)
        for hour in range(24)
        if hour != 1
    ]
    hourly.append(HourlyLoad(date=d, hour=1, load_mwh=200.0, hours_covered=2.0, intervals=24))

    with pytest.raises(ValueError, match="daylight saving time"):
        render_day_profile_csv(hourly, demand_percentile={d: 0.5}, banner=[])


def test_render_ordinary_coverage_gap_does_not_mention_dst():
    d = date(2026, 1, 24)
    hourly = [
        HourlyLoad(date=d, hour=hour, load_mwh=100.0, hours_covered=1.0, intervals=12)
        for hour in range(24)
        if hour != 4
    ]
    hourly.append(HourlyLoad(date=d, hour=4, load_mwh=91.67, hours_covered=0.9167, intervals=11))

    with pytest.raises(ValueError) as exc_info:
        render_day_profile_csv(hourly, demand_percentile={d: 0.5}, banner=[])
    message = str(exc_info.value)
    assert "daylight saving time" not in message
    assert d.isoformat() in message
    assert "4" in message
    assert "0.9167" in message


def test_render_non_consecutive_dates_raises_and_names_both():
    d1, d2 = date(2026, 1, 24), date(2026, 1, 26)
    hourly = _full_day_hourly(d1, 100.0) + _full_day_hourly(d2, 100.0)

    with pytest.raises(ValueError) as exc_info:
        render_day_profile_csv(
            hourly, demand_percentile={d1: 0.5, d2: 0.5}, banner=[]
        )
    message = str(exc_info.value)
    assert d1.isoformat() in message
    assert d2.isoformat() in message


def test_render_output_contains_no_wind_column():
    d = date(2026, 1, 24)
    hourly = _full_day_hourly(d, 100.0)

    text = render_day_profile_csv(hourly, demand_percentile={d: 0.5}, banner=["no wind here"])

    assert "wind_mw" not in text


def test_render_one_day_with_wind():
    d = date(2026, 1, 24)
    hourly = _full_day_hourly(d, 100.0)
    wind = _full_day_hourly(d, 50.0)

    text = render_day_profile_csv(
        hourly, demand_percentile={d: 0.5}, banner=["banner"], wind=wind
    )

    lines = text.splitlines()
    assert lines[1] == "date,hour,load_mw,wind_mw,demand_percentile"
    data_lines = lines[2:]
    assert len(data_lines) == 24
    assert data_lines[0] == "2026-01-24,0,100.000,50.000,0.500000"


def test_render_with_wind_round_trips_through_scenario_input():
    d = date(2026, 1, 24)
    hourly = _full_day_hourly(d, 100.0)
    wind = _full_day_hourly(d, 50.0)

    text = render_day_profile_csv(
        hourly, demand_percentile={d: 0.5}, banner=["banner"], wind=wind
    )
    result = scenario_input.read_day_profiles(iter(text.splitlines(keepends=True)), origin="<test>")

    assert result.has_wind is True
    assert result.wind_forecast_frac_source == "default-zero"
    day = result.days[0]
    for hourly_wind in day.hourly_wind_mw:
        assert hourly_wind == pytest.approx(50.0)


def test_render_wind_missing_hour_raises_and_names_it():
    d = date(2026, 1, 24)
    hourly = _full_day_hourly(d, 100.0)
    wind = [h for h in _full_day_hourly(d, 50.0) if h.hour != 5]

    with pytest.raises(ValueError) as exc_info:
        render_day_profile_csv(hourly, demand_percentile={d: 0.5}, banner=[], wind=wind)
    message = str(exc_info.value)
    assert d.isoformat() in message
    assert "hour 5" in message


def test_render_wind_bad_coverage_raises_and_names_wind():
    d = date(2026, 1, 24)
    hourly = _full_day_hourly(d, 100.0)
    wind = [h for h in _full_day_hourly(d, 50.0) if h.hour != 5]
    wind.append(HourlyLoad(date=d, hour=5, load_mwh=100.0, hours_covered=2.0, intervals=24))

    with pytest.raises(ValueError) as exc_info:
        render_day_profile_csv(hourly, demand_percentile={d: 0.5}, banner=[], wind=wind)
    message = str(exc_info.value)
    assert "wind_mw" in message
    assert d.isoformat() in message
    assert "5" in message


def test_render_shared_dst_coverage_fault_names_dst_not_wind():
    d = date(2026, 11, 1)  # a fall-back Sunday
    hourly = [
        HourlyLoad(date=d, hour=hour, load_mwh=100.0, hours_covered=1.0, intervals=12)
        for hour in range(24)
        if hour != 1
    ]
    hourly.append(HourlyLoad(date=d, hour=1, load_mwh=200.0, hours_covered=2.0, intervals=24))
    wind = [
        HourlyLoad(date=d, hour=hour, load_mwh=50.0, hours_covered=1.0, intervals=12)
        for hour in range(24)
        if hour != 1
    ]
    wind.append(HourlyLoad(date=d, hour=1, load_mwh=100.0, hours_covered=2.0, intervals=24))

    with pytest.raises(ValueError) as exc_info:
        render_day_profile_csv(hourly, demand_percentile={d: 0.5}, banner=[], wind=wind)
    message = str(exc_info.value)
    assert "daylight saving time" in message
    assert "wind_mw" not in message


def test_render_wind_date_outside_load_dates_is_ignored():
    d1 = date(2026, 1, 24)
    d_outside = date(2026, 1, 25)
    hourly = _full_day_hourly(d1, 100.0)
    wind = _full_day_hourly(d1, 50.0) + _full_day_hourly(d_outside, 60.0)

    text = render_day_profile_csv(
        hourly, demand_percentile={d1: 0.5}, banner=[], wind=wind
    )

    assert d_outside.isoformat() not in text


def test_render_wind_value_formats_to_three_decimals():
    d = date(2026, 1, 24)
    hourly = _full_day_hourly(d, 100.0)
    wind = [
        HourlyLoad(date=d, hour=hour, load_mwh=1186.0, hours_covered=1.0, intervals=1)
        for hour in range(24)
    ]

    text = render_day_profile_csv(hourly, demand_percentile={d: 0.5}, banner=[], wind=wind)

    assert "1186.000" in text
