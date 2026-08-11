"""Integration test of the rolling-window loop on a small synthetic stress event.

Verifies the end-to-end invariants the Architecture doc requires:
  * SoC never drops below the reserve floor,
  * discharge reduces the peak net load vs the direct-to-grid baseline,
  * state carries forward across days (MPC receding horizon).

Event-relative recharge: every ``simulate()`` call now takes a required
``schedule=`` (an ``OperatingSchedule``). ``_active_event_schedule`` builds one
that marks every day of a window ``ACTIVE_EVENT``, with a peak window found by
the same search the engine uses, so the dispatch block lands on each
fixture's real load peak.
"""

import datetime
import math
from datetime import date, timedelta

import pytest

from owr import budget as budget_mod
from owr import recharge as recharge_mod
from owr.config import Config
from owr.models import DayMode, DayProfile, OperatingSchedule, StorageAsset, StressWindow
from owr.schedule import build_schedule
from owr.simulator import DAILY_FRAME_COLUMNS, HOURLY_FRAME_COLUMNS, simulate
from owr.soc_engine import usable_energy

# default_min_stress_window_days=1 so a single-day fixture still qualifies as
# an event; the rest of the schedule-building config stays default.
_SCHEDULE_CONFIG = Config(default_min_stress_window_days=1)


def _active_event_schedule(days: list[DayProfile]) -> OperatingSchedule:
    window = StressWindow(start=days[0].date, end=days[-1].date, days=len(days))
    return build_schedule(days, stress_windows=[window], config=_SCHEDULE_CONFIG)


def _non_event_schedule(days: list[DayProfile]) -> OperatingSchedule:
    return build_schedule(days, stress_windows=[], config=_SCHEDULE_CONFIG)


def _stress_day(i: int, wind_mw: float = 150.0) -> DayProfile:
    # Evening-peak day: flat 8000 MW base, peak 12000 MW at hour 18. Wind is
    # moderate (150 MW), not huge, simply to keep the fixture's numbers
    # readable. PLAN_BUDGET_FULL_TANK_FIX.md moved the budget's recharge
    # term to recharge.recharge_opportunity_mwh, which carries no SoC, so a
    # full tank no longer floors the budget at 0.0 here; a fully-charged
    # start is now a fixture this file uses on purpose (see
    # test_full_tank_start_discharges_on_an_active_event, below).
    load = [8000.0] * 24
    load[17] = 10000.0
    load[18] = 12000.0
    load[19] = 10000.0
    wind = [wind_mw] * 24
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
    schedule = _active_event_schedule(window)

    result = simulate(
        asset,
        window,
        starting_soc=8000.0,  # above the floor, with headroom across the window
        schedule=schedule,
        available_capacity_mw=13000.0,
    )

    assert len(result.daily) == 3
    # reserve floor (33% of 20000 = 6600 MWh) is never breached
    for day in result.daily:
        for hour in day.hourly:
            assert hour.soc >= asset.min_soc_mwh - 1e-6
    # the reserve reduces the worst net-load hour below the gross peak
    assert result.reserve_peak_mw < result.baseline_peak_mw
    total_discharged = sum(h.discharge for day in result.daily for h in day.hourly)
    assert total_discharged > 0


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
    schedule = _active_event_schedule(window)

    result = simulate(
        asset,
        window,
        starting_soc=asset.total_mwh,  # fully charged pre-event
        schedule=schedule,
        available_capacity_mw=13000.0,
    )

    for day in result.daily:
        for hour in day.hourly:
            assert hour.soc >= asset.min_soc_mwh - 1e-6
    assert result.final_soc >= asset.min_soc_mwh - 1e-6


def _surplus_wind_day() -> DayProfile:
    # Flat 100 MW load, one hour bumped to 300 MW so a real discharge leg
    # exists (a flat day dispatches nothing, the known flat-day edge). Wind is
    # 0 except 500 MW at hour 12, an off-peak hour under the peak search below.
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
    # reduction despite storage strictly helping. Hour 12 is off-peak under the
    # peak search on this fixture (the peak triplet lands on 16,17,18), so it
    # still charges the full 500 MW wind under the new event-relative rule.
    asset = _surplus_wind_asset()
    day = _surplus_wind_day()
    schedule = _active_event_schedule([day])
    result = simulate(
        asset,
        [day],
        starting_soc=5000.0,  # above the floor (3000) and below total_mwh
        schedule=schedule,
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
    day = _surplus_wind_day()
    surplus_result = simulate(
        _surplus_wind_asset(), [day], starting_soc=5000.0, schedule=_active_event_schedule([day])
    )
    assert surplus_result.reserve_peak_mw <= surplus_result.baseline_peak_mw

    stress_asset = StorageAsset(
        total_mwh=20000, power_mw=2000, efficiency=1.0,
        soc_floor_frac=0.33, strategic_reserve_frac=0.0,
    )
    stress_window = [_stress_day(i) for i in range(3)]
    stress_result = simulate(
        stress_asset, stress_window, starting_soc=stress_asset.total_mwh,
        schedule=_active_event_schedule(stress_window),
        available_capacity_mw=13000.0,
    )
    assert stress_result.reserve_peak_mw <= stress_result.baseline_peak_mw


def _stress_day_with_wind(i: int, wind_mw: float) -> DayProfile:
    load = [8000.0] * 24
    load[17] = 10000.0
    load[18] = 12000.0
    load[19] = 10000.0
    return DayProfile(
        date=date(2026, 1, 10) + timedelta(days=i),
        hourly_load_mw=tuple(load),
        hourly_wind_mw=tuple([wind_mw] * 24),
        demand_percentile=0.95,
        wind_forecast_frac=0.1,
    )


def test_budget_is_zero_on_non_event_days():
    # Structural: a day the schedule marks anything other than ACTIVE_EVENT
    # never gets a discharge budget, whatever the wind carries (D8, Phase 6).
    asset = StorageAsset(
        total_mwh=20000, power_mw=2000, efficiency=1.0,
        soc_floor_frac=0.33, strategic_reserve_frac=0.0,
    )
    window = [_stress_day_with_wind(i, 9000.0) for i in range(3)]
    result = simulate(
        asset, window, starting_soc=asset.total_mwh, schedule=_non_event_schedule(window)
    )
    for day in result.daily:
        assert day.budget == pytest.approx(0.0)
        for hour in day.hourly:
            assert hour.discharge == pytest.approx(0.0)


def test_budget_rises_with_more_wind_on_active_event_days():
    # Event-relative recharge: expected_recharge_mwh now comes from
    # recharge.recharge_opportunity_mwh over the off-peak hours, so more wind
    # on those hours raises the opportunity sum and, whenever that term
    # binds, the budget. Start with headroom (not fully charged) simply to
    # keep the fixture's numbers modest and readable; since
    # PLAN_BUDGET_FULL_TANK_FIX.md, the opportunity term carries no SoC, so a
    # fully-charged start would no longer invert this result the way it once
    # did.
    asset = StorageAsset(
        total_mwh=20000, power_mw=2000, efficiency=1.0,
        soc_floor_frac=0.33, strategic_reserve_frac=0.0,
    )
    starting_soc = asset.total_mwh * 0.5
    low_window = [_stress_day_with_wind(i, 50.0) for i in range(3)]
    high_window = [_stress_day_with_wind(i, 150.0) for i in range(3)]
    low_wind = simulate(
        asset, low_window, starting_soc=starting_soc, schedule=_active_event_schedule(low_window)
    )
    high_wind = simulate(
        asset, high_window, starting_soc=starting_soc, schedule=_active_event_schedule(high_window)
    )
    low_discharged = sum(h.discharge for day in low_wind.daily for h in day.hourly)
    high_discharged = sum(h.discharge for day in high_wind.daily for h in day.hourly)
    assert high_discharged > low_discharged


def test_capacity_margin_follows_the_net_load_definition():
    asset = _surplus_wind_asset()
    day = _surplus_wind_day()
    result = simulate(
        asset,
        [day],
        starting_soc=5000.0,
        schedule=_active_event_schedule([day]),
        available_capacity_mw=1000.0,
    )
    hour12 = next(h for h in result.daily[0].hourly if h.ts_hour == 12)
    assert hour12.charge > 0
    assert hour12.capacity_margin == pytest.approx(1000.0 - hour12.net_load)


def _fixture_asset() -> StorageAsset:
    return StorageAsset(
        total_mwh=20000, power_mw=2000, efficiency=1.0,
        soc_floor_frac=0.33, strategic_reserve_frac=0.0,
    )


def test_full_tank_start_discharges_on_an_active_event():
    # PLAN_BUDGET_FULL_TANK_FIX.md test 6. Before the fix, budget.daily_budget's
    # recharge term came from recharge.charge_forward's SoC-clamped forecast,
    # so a fully-charged start forecast zero further recharge and floored the
    # whole span's budget at 0.0: a full reserve discharged nothing. The fix
    # (recharge.recharge_opportunity_mwh, which carries no SoC) restores
    # discharge at a full start. Measured: 8,550.0 MWh discharged, reserve
    # peak 11,525.0 against baseline 12,000.0.
    asset = _fixture_asset()
    window = [_stress_day(i) for i in range(3)]
    result = simulate(
        asset, window, starting_soc=asset.total_mwh, schedule=_active_event_schedule(window)
    )
    total_discharged = sum(h.discharge for day in result.daily for h in day.hourly)
    assert total_discharged > 0
    assert result.reserve_peak_mw < result.baseline_peak_mw
    assert total_discharged == pytest.approx(8550.0, abs=1.0)
    assert result.reserve_peak_mw == pytest.approx(11525.0, abs=1.0)
    assert result.baseline_peak_mw == pytest.approx(12000.0, abs=1.0)


def test_total_discharge_does_not_fall_as_starting_soc_rises():
    """PLAN_BUDGET_FULL_TANK_FIX.md test 7, the regression guard for the whole
    defect class this plan fixes, and the only test in this file that watches
    the ``simulator.py`` call site directly (test
    ``test_recharge.py::test_guard_recharge_opportunity_takes_no_soc_and_no_asset``
    is the signature-only guard; it cannot see this call site, so this test
    is the pair that would catch a regression back to
    ``recharge_mod.charge_forward(...).charged_mwh``).

    Total discharge falling as starting SoC rises is a physical
    impossibility: more banked energy can never leave an asset worse able to
    discharge. Under the pre-fix code this sequence fell; under the fix it is
    non-decreasing. Measured: 0.0, 2975.0, 4275.0, 5208.3, 6541.7, 7500.0,
    8500.0, 8550.0, 8550.0.
    """
    asset = _fixture_asset()
    window = [_stress_day(i) for i in range(3)]
    schedule = _active_event_schedule(window)
    fractions = (0.0, 0.2, 0.33, 0.4, 0.5, 0.6, 0.75, 0.9, 1.0)
    totals = []
    for frac in fractions:
        result = simulate(
            asset, window, starting_soc=asset.total_mwh * frac, schedule=schedule
        )
        totals.append(sum(h.discharge for day in result.daily for h in day.hourly))
    for earlier, later in zip(totals, totals[1:], strict=False):
        assert later >= earlier - 1e-6
    assert totals == pytest.approx(
        [0.0, 2975.0, 4275.0, 5208.3, 6541.7, 7500.0, 8500.0, 8550.0, 8550.0], abs=1.0
    )


def test_two_window_span_pins_the_d15_day_set_mismatch():
    """PLAN_BUDGET_FULL_TANK_FIX.md test 8 (M1), specified in
    PLAN_EVENT_RELATIVE_RECHARGE.md's Section 13.2 and never delivered there.
    Written now, because this fix changes the exact expression it asserts.

    Two 2-day windows, a 2-day gap, a 2-day tail: modes are
    [active, active, pre_charge, pre_charge, active, active, non_event, non_event].
    D15's day-set mismatch was invisible before this fix, because a
    multi-event span that started full produced all-zero budgets. It is
    visible now: on day 5 the numerator credits only that day's off-peak
    hours (2,850 MWh) and nothing from the two trailing non-event days,
    while the divisor still counts all three remaining days, costing a
    factor of three that day.
    """
    asset = _fixture_asset()
    span = [_stress_day(i, wind_mw=150.0) for i in range(8)]
    windows = [
        StressWindow(start=span[0].date, end=span[1].date, days=2),
        StressWindow(start=span[4].date, end=span[5].date, days=2),
    ]
    schedule = build_schedule(span, stress_windows=windows, config=_SCHEDULE_CONFIG)
    day_schedules = schedule.slice_for([d.date for d in span])

    starting_soc = asset.total_mwh
    result = simulate(asset, span, starting_soc=starting_soc, schedule=schedule)

    modes = [ds.mode for ds in day_schedules]
    assert modes == [
        DayMode.ACTIVE_EVENT,
        DayMode.ACTIVE_EVENT,
        DayMode.PRE_CHARGE,
        DayMode.PRE_CHARGE,
        DayMode.ACTIVE_EVENT,
        DayMode.ACTIVE_EVENT,
        DayMode.NON_EVENT,
        DayMode.NON_EVENT,
    ]

    def soc_at_start_of(i: int) -> float:
        return starting_soc if i == 0 else result.daily[i - 1].hourly[-1].soc

    for i, day_result in enumerate(result.daily):
        if day_schedules[i].mode is not DayMode.ACTIVE_EVENT:
            assert day_result.budget == 0.0
            continue
        soc = soc_at_start_of(i)
        remaining = len(span) - i  # D15: counts gap days and the second event's days
        expected = budget_mod.daily_budget(
            available_charge_mwh=usable_energy(soc, asset),
            remaining_stress_days=remaining,
            expected_recharge_mwh=recharge_mod.recharge_opportunity_mwh(
                span[i:], day_schedules[i:]
            ),
            remaining_cycles=remaining,
        )
        assert day_result.budget == pytest.approx(expected)


def test_starting_soc_out_of_bounds_rejected():
    asset = StorageAsset(total_mwh=1000, power_mw=100)
    day = _stress_day(0)
    schedule = _active_event_schedule([day])
    try:
        simulate(asset, [day], starting_soc=2000.0, schedule=schedule)
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
    result = simulate(
        asset,
        window,
        starting_soc=asset.total_mwh,
        schedule=_active_event_schedule(window),
        available_capacity_mw=13000.0,
    )
    frame = result.hourly_frame()
    assert tuple(frame.columns) == HOURLY_FRAME_COLUMNS
    assert len(frame.index) == 48


def test_hourly_frame_values_match_the_dataclasses():
    asset, window = _two_day_asset_and_window()
    result = simulate(
        asset,
        window,
        starting_soc=asset.total_mwh,
        schedule=_active_event_schedule(window),
        available_capacity_mw=13000.0,
    )
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
    result = simulate(
        asset,
        window,
        starting_soc=asset.total_mwh,
        schedule=_active_event_schedule(window),
        available_capacity_mw=13000.0,
    )
    frame = result.hourly_frame()
    assert isinstance(frame["date"].iloc[0], datetime.date)
    assert not isinstance(frame["date"].iloc[0], datetime.datetime)
    assert frame["date"].dtype == object


def test_capacity_margin_is_nan_and_float64_when_unset():
    asset, window = _two_day_asset_and_window()
    result = simulate(
        asset,
        window,
        starting_soc=asset.total_mwh,
        schedule=_active_event_schedule(window),
        available_capacity_mw=None,
    )
    frame = result.hourly_frame()
    assert frame["capacity_margin"].dtype == "float64"
    assert frame["capacity_margin"].isna().all()


def test_hourly_frame_dtypes_match_the_declared_schema():
    asset, window = _two_day_asset_and_window()
    result = simulate(
        asset,
        window,
        starting_soc=asset.total_mwh,
        schedule=_active_event_schedule(window),
        available_capacity_mw=13000.0,
    )
    frame = result.hourly_frame()
    assert frame["date"].dtype == object
    assert frame["ts_hour"].dtype == "int64"
    for column in HOURLY_FRAME_COLUMNS[2:]:
        assert frame[column].dtype == "float64", column


def test_daily_frame_columns_and_nan_ratio():
    asset, window = _two_day_asset_and_window()
    result = simulate(
        asset,
        window,
        starting_soc=asset.total_mwh,
        schedule=_active_event_schedule(window),
        available_capacity_mw=13000.0,
    )
    frame = result.daily_frame()
    assert frame["recharge_sufficiency_ratio"].dtype == "float64"
    assert math.isnan(frame["recharge_sufficiency_ratio"].iloc[-1])


def test_recharge_sufficiency_ratio_divides_by_full_usable_energy():
    # next_need is 100% of usable energy at day close: the protected reserve
    # floor inside usable_energy is the only constraint left.
    asset, window = _two_day_asset_and_window()
    result = simulate(
        asset,
        window,
        starting_soc=asset.total_mwh,
        schedule=_active_event_schedule(window),
    )
    first = result.daily[0]
    recharge_available = sum(h.charge for h in first.hourly)
    assert recharge_available > 0          # the fixture must discriminate
    assert first.usable_energy > 0
    assert first.recharge_sufficiency_ratio == pytest.approx(
        recharge_available / first.usable_energy
    )
    assert result.daily[-1].recharge_sufficiency_ratio is None


def test_frames_are_empty_with_declared_columns():
    asset = StorageAsset(total_mwh=1000, power_mw=100)
    result = simulate(asset, [], starting_soc=0.0, schedule=OperatingSchedule(days=()))
    hourly = result.hourly_frame()
    daily = result.daily_frame()
    assert len(hourly.index) == 0
    assert len(daily.index) == 0
    assert tuple(hourly.columns) == HOURLY_FRAME_COLUMNS
    assert tuple(daily.columns) == DAILY_FRAME_COLUMNS
    assert hourly["capacity_margin"].dtype == "float64"
    assert daily["recharge_sufficiency_ratio"].dtype == "float64"


def test_simulate_requires_schedule_dates_to_cover_window_days():
    asset = StorageAsset(total_mwh=1000, power_mw=100)
    day = _stress_day(0)
    mismatched = _active_event_schedule([_stress_day(5)])
    with pytest.raises(ValueError):
        simulate(asset, [day], starting_soc=0.0, schedule=mismatched)
