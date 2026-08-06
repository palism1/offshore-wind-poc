"""Integration test of the rolling-window loop on a small synthetic stress event.

Verifies the end-to-end invariants the Architecture doc requires:
  * SoC never drops below the reserve floor,
  * discharge reduces the peak net load vs the direct-to-grid baseline,
  * state carries forward across days (MPC receding horizon).
"""

import datetime
import math
from datetime import date, timedelta

import pytest

from owr.initial_soc import charge_from_wind
from owr.models import DayProfile, StorageAsset
from owr.simulator import DAILY_FRAME_COLUMNS, HOURLY_FRAME_COLUMNS, simulate


def _stress_day(i: int) -> DayProfile:
    # Evening-peak day: flat 8000 MW base, peak 12000 MW at hour 18, low wind (stress).
    load = [8000.0] * 24
    load[17] = 10000.0
    load[18] = 12000.0
    load[19] = 10000.0
    wind = [500.0] * 24  # low wind during the event
    return DayProfile(
        date=date(2026, 1, 10) + timedelta(days=i),
        hourly_load_mw=tuple(load),
        hourly_wind_mw=tuple(wind),
        demand_percentile=0.95,
        wind_forecast_frac=0.1,
    )


def test_rolling_window_shaves_peak_and_respects_reserve():
    asset = StorageAsset(
        total_mwh=20000,
        power_mw=2000,
        efficiency=1.0,
        soc_floor_frac=0.33,
        strategic_reserve_frac=0.0,
    )
    window = [_stress_day(i) for i in range(3)]

    result = simulate(
        asset,
        window,
        starting_soc=asset.total_mwh,  # fully charged pre-event
        available_capacity_mw=13000.0,
    )

    assert len(result.daily) == 3
    # reserve floor (33% of 20000 = 6600 MWh) is never breached
    for day in result.daily:
        for hour in day.hourly:
            assert hour.soc >= asset.min_soc_mwh - 1e-6
    # the reserve reduces the worst net-load hour below the gross peak
    assert result.reserve_peak_mw < result.baseline_peak_mw
    # SoC was actually drawn down (energy was delivered)
    assert result.final_soc < asset.total_mwh


@pytest.mark.parametrize("efficiency", [0.5, 0.72])
def test_soc_never_crosses_the_floor_at_lossy_efficiency(efficiency):
    # F1's own repro at engine scale: before the fix, --efficiency 0.72 on the
    # shipped demo scenario drove SoC below the protected floor.
    asset = StorageAsset(
        total_mwh=20000,
        power_mw=2000,
        efficiency=efficiency,
        soc_floor_frac=0.33,
        strategic_reserve_frac=0.0,
    )
    window = [_stress_day(i) for i in range(3)]

    result = simulate(
        asset,
        window,
        starting_soc=asset.total_mwh,  # fully charged pre-event
        available_capacity_mw=13000.0,
    )

    for day in result.daily:
        for hour in day.hourly:
            assert hour.soc >= asset.min_soc_mwh - 1e-6
    assert result.final_soc >= asset.min_soc_mwh - 1e-6


def _surplus_wind_day() -> DayProfile:
    # Flat 100 MW load, one hour bumped to 300 MW so a real discharge leg exists
    # (a flat day dispatches nothing, the known flat-day edge). Wind is 0 except
    # 500 MW at hour 12, well above that hour's load, so it is surplus.
    load = [100.0] * 24
    load[18] = 300.0
    wind = [0.0] * 24
    wind[12] = 500.0
    return DayProfile(
        date=date(2026, 1, 10),
        hourly_load_mw=tuple(load),
        hourly_wind_mw=tuple(wind),
        demand_percentile=0.95,
        wind_forecast_frac=0.5,
    )


def _surplus_wind_asset() -> StorageAsset:
    return StorageAsset(
        total_mwh=10000,
        power_mw=500,
        efficiency=1.0,
        soc_floor_frac=0.20,
        strategic_reserve_frac=0.10,
    )


def test_surplus_wind_charging_does_not_raise_the_reserve_peak():
    # F3/F7b, the reviewer's own repro (with a load bump added so a discharge leg
    # is real). Before D2, hour 12's net load included the charging draw and
    # reported near 500 MW against a 300 MW baseline peak: a negative severity
    # reduction despite storage strictly helping.
    asset = _surplus_wind_asset()
    result = simulate(
        asset,
        [_surplus_wind_day()],
        starting_soc=5000.0,  # above the floor (3000) and below total_mwh
    )
    hourly_by_hour = {h.ts_hour: h for h in result.daily[0].hourly}

    assert hourly_by_hour[12].charge > 0
    assert hourly_by_hour[18].discharge > 0
    assert result.baseline_peak_mw == 300.0
    assert result.reserve_peak_mw <= result.baseline_peak_mw
    assert hourly_by_hour[12].net_load == pytest.approx(
        hourly_by_hour[12].gross_load - hourly_by_hour[12].discharge
    )


def test_reserve_peak_never_exceeds_baseline_peak():
    # D2's provable floor: discharge >= 0, so reserve_peak_mw <= baseline_peak_mw
    # always, on a surplus-wind profile and on the existing three-day stress window.
    surplus_result = simulate(_surplus_wind_asset(), [_surplus_wind_day()], starting_soc=5000.0)
    assert surplus_result.reserve_peak_mw <= surplus_result.baseline_peak_mw

    stress_asset = StorageAsset(
        total_mwh=20000, power_mw=2000, efficiency=1.0,
        soc_floor_frac=0.33, strategic_reserve_frac=0.0,
    )
    stress_window = [_stress_day(i) for i in range(3)]
    stress_result = simulate(
        stress_asset, stress_window, starting_soc=stress_asset.total_mwh,
        available_capacity_mw=13000.0,
    )
    assert stress_result.reserve_peak_mw <= stress_result.baseline_peak_mw


def test_capacity_margin_follows_the_net_load_definition():
    asset = _surplus_wind_asset()
    result = simulate(
        asset, [_surplus_wind_day()], starting_soc=5000.0, available_capacity_mw=1000.0
    )
    hour12 = next(h for h in result.daily[0].hourly if h.ts_hour == 12)
    assert hour12.charge > 0
    assert hour12.capacity_margin == pytest.approx(1000.0 - hour12.net_load)


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
    soc = charge_from_wind(starting_soc=500.0, lead_days=lead, asset=asset)
    assert soc == asset.total_mwh  # fills to capacity


def test_starting_soc_out_of_bounds_rejected():
    asset = StorageAsset(total_mwh=1000, power_mw=100)
    try:
        simulate(asset, [_stress_day(0)], starting_soc=2000.0)
        raised = False
    except ValueError:
        raised = True
    assert raised


def _two_day_asset_and_window():
    asset = StorageAsset(
        total_mwh=20000,
        power_mw=2000,
        efficiency=1.0,
        soc_floor_frac=0.33,
        strategic_reserve_frac=0.0,
    )
    window = [_stress_day(i) for i in range(2)]
    return asset, window


def test_hourly_frame_shape_and_columns():
    asset, window = _two_day_asset_and_window()
    result = simulate(asset, window, starting_soc=asset.total_mwh, available_capacity_mw=13000.0)
    frame = result.hourly_frame()
    assert tuple(frame.columns) == HOURLY_FRAME_COLUMNS
    assert len(frame.index) == 48


def test_hourly_frame_values_match_the_dataclasses():
    asset, window = _two_day_asset_and_window()
    result = simulate(asset, window, starting_soc=asset.total_mwh, available_capacity_mw=13000.0)
    frame = result.hourly_frame()
    rows = [hr for day in result.daily for hr in day.hourly]
    dates = [day.date for day in result.daily for _ in day.hourly]
    for i, (row, day_date) in enumerate(zip(rows, dates, strict=True)):
        r = frame.iloc[i]
        assert r["date"] == day_date
        assert r["ts_hour"] == row.ts_hour
        assert r["soc"] == row.soc
        assert r["charge"] == row.charge
        assert r["discharge"] == row.discharge
        assert r["discharge_peak"] == row.discharge_peak
        assert r["discharge_smooth"] == row.discharge_smooth
        assert r["gross_load"] == row.gross_load
        assert r["net_load"] == row.net_load
        assert r["capacity_margin"] == row.capacity_margin


def test_hourly_frame_date_column_holds_date_objects():
    asset, window = _two_day_asset_and_window()
    result = simulate(asset, window, starting_soc=asset.total_mwh, available_capacity_mw=13000.0)
    frame = result.hourly_frame()
    assert isinstance(frame["date"].iloc[0], datetime.date)
    assert not isinstance(frame["date"].iloc[0], datetime.datetime)
    assert frame["date"].dtype == object


def test_capacity_margin_is_nan_and_float64_when_unset():
    asset, window = _two_day_asset_and_window()
    result = simulate(asset, window, starting_soc=asset.total_mwh, available_capacity_mw=None)
    frame = result.hourly_frame()
    assert frame["capacity_margin"].dtype == "float64"
    assert frame["capacity_margin"].isna().all()


def test_daily_frame_columns_and_nan_ratio():
    asset, window = _two_day_asset_and_window()
    result = simulate(asset, window, starting_soc=asset.total_mwh, available_capacity_mw=13000.0)
    frame = result.daily_frame()
    assert frame["recharge_sufficiency_ratio"].dtype == "float64"
    assert math.isnan(frame["recharge_sufficiency_ratio"].iloc[-1])


def test_frames_are_empty_with_declared_columns():
    asset = StorageAsset(total_mwh=1000, power_mw=100)
    result = simulate(asset, [], starting_soc=0.0)
    hourly = result.hourly_frame()
    daily = result.daily_frame()
    assert len(hourly.index) == 0
    assert len(daily.index) == 0
    assert tuple(hourly.columns) == HOURLY_FRAME_COLUMNS
    assert tuple(daily.columns) == DAILY_FRAME_COLUMNS
    assert hourly["capacity_margin"].dtype == "float64"
    assert daily["recharge_sufficiency_ratio"].dtype == "float64"
