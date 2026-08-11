"""Tests for owr.initial_soc.

Event-relative recharge: pre-event charging now routes ALL wind on a
PRE_CHARGE day to storage, not just the surplus above load (D4). The two
former "surplus above load" tests below become pre-charge tests: wind charges
regardless of load, and capacity still stops it.
"""

from datetime import date

import pytest

from owr.initial_soc import charge_from_wind
from owr.models import DayMode, DayProfile, DaySchedule, OperatingSchedule, StorageAsset


def _pre_charge_schedule(d: date) -> OperatingSchedule:
    return OperatingSchedule(
        days=(DaySchedule(date=d, mode=DayMode.PRE_CHARGE, peak_window=None, ramp_hours=0),)
    )


def test_initial_soc_charges_from_wind_before_event():
    asset = StorageAsset(
        total_mwh=1000,
        power_mw=100,
        efficiency=1.0,
        soc_floor_frac=0.33,
        strategic_reserve_frac=0.0,
    )
    lead = [
        DayProfile(
            date=date(2026, 1, 9),
            hourly_load_mw=(0.0,) * 24,
            hourly_wind_mw=(80.0,) * 24,  # 80 MW * 24 h = 1920 MWh available, capacity-capped
        )
    ]
    schedule = _pre_charge_schedule(date(2026, 1, 9))
    soc = charge_from_wind(starting_soc=500.0, lead_days=lead, asset=asset, schedule=schedule)
    assert soc == asset.total_mwh  # fills to capacity


def test_pre_charge_day_charges_all_wind_regardless_of_load():
    """On a PRE_CHARGE day, every hour's wind routes to storage whatever the
    load is (D4): the surplus-above-load rule no longer applies here."""
    asset = StorageAsset(total_mwh=1_000_000, power_mw=100_000)
    lead = [
        DayProfile(
            date=date(2026, 1, 9),
            hourly_load_mw=(1000.0,) * 24,
            hourly_wind_mw=(800.0,) * 24,
        )
    ]
    schedule = _pre_charge_schedule(date(2026, 1, 9))
    soc = charge_from_wind(starting_soc=0.0, lead_days=lead, asset=asset, schedule=schedule)
    assert soc == pytest.approx(24 * 800.0 * asset.one_way_efficiency)


def test_pre_charge_day_charges_wind_above_load_too():
    asset = StorageAsset(total_mwh=1_000_000, power_mw=100_000)
    lead = [
        DayProfile(
            date=date(2026, 1, 9),
            hourly_load_mw=(1000.0,) * 24,
            hourly_wind_mw=(1200.0,) * 24,
        )
    ]
    schedule = _pre_charge_schedule(date(2026, 1, 9))
    soc = charge_from_wind(starting_soc=0.0, lead_days=lead, asset=asset, schedule=schedule)
    assert soc == pytest.approx(24 * 1200.0 * asset.one_way_efficiency)


def test_charge_from_wind_negative_wind_floors_at_zero():
    """D13: negative wind floors at 0.0, matching the retired surplus rules;
    the function never raises on it."""
    asset = StorageAsset(total_mwh=1_000_000, power_mw=100_000)
    lead = [
        DayProfile(
            date=date(2026, 1, 9),
            hourly_load_mw=(1000.0,) * 24,
            hourly_wind_mw=(-50.0,) * 24,
        )
    ]
    schedule = _pre_charge_schedule(date(2026, 1, 9))
    soc = charge_from_wind(starting_soc=100.0, lead_days=lead, asset=asset, schedule=schedule)
    assert soc == 100.0


def test_charge_from_wind_on_active_event_day_charges_off_peak_only():
    """A lead day that is itself ACTIVE_EVENT (e.g. inside an earlier window)
    charges only its off-peak hours, following the one shared rule rather than
    a second policy."""
    from owr.models import HourState, PeakWindow

    asset = StorageAsset(total_mwh=1_000_000, power_mw=100_000)
    d = date(2026, 1, 9)
    lead = [DayProfile(date=d, hourly_load_mw=(0.0,) * 24, hourly_wind_mw=(100.0,) * 24)]
    peak = PeakWindow(
        start_hour=12,
        clock_hours=(12, 13, 14),
        load_mw=(1.0, 1.0, 1.0),
        wrapped=False,
        candidates_considered=22,
    )
    day_schedule = DaySchedule(date=d, mode=DayMode.ACTIVE_EVENT, peak_window=peak, ramp_hours=1)
    schedule = OperatingSchedule(days=(day_schedule,))
    dispatch_hours = set(day_schedule.dispatch_window.dispatch_hours)
    off_peak_hours = [h for h in range(24) if h not in dispatch_hours]
    assert day_schedule.hours[off_peak_hours[0]] is HourState.ACTIVE_OFF_PEAK
    soc = charge_from_wind(starting_soc=0.0, lead_days=lead, asset=asset, schedule=schedule)
    expected_hours = len(off_peak_hours)
    assert soc == pytest.approx(expected_hours * 100.0 * asset.one_way_efficiency)
