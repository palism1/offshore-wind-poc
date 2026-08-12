"""Tests for outcome metrics (Architecture Step 6 / metrics)."""

from datetime import date, timedelta

import pytest

from owr.metrics import (
    average_recharge_mismatch_mwh,
    capacity_margin,
    capacity_margin_deficit_reduction_mw,
    capacity_margin_deficit_reduction_percent,
    capacity_margin_deficit_reduction_series_mw,
    cost_per_equivalent_full_cycle_usd,
    cycle_recharge_mismatch_mwh,
    equivalent_full_cycles,
    estimated_capital_cost_usd,
    fuel_fired_generation_offset_mwh,
    fuel_offset_fraction,
    net_load,
    net_load_change_percent,
    recharge_capacity_mismatch_fraction,
    recharge_opportunity_mw,
    severity_reduction,
    stress_window_effectiveness_fraction,
)
from owr.models import DayMode, DayProfile, DaySchedule, HourState, OperatingSchedule, StorageAsset
from owr.simulator import simulate


def test_net_load_subtracts_discharge_adds_charge():
    assert net_load(1000.0, discharge_mw=200.0) == 800.0
    assert net_load(1000.0, discharge_mw=0.0, charge_mw=50.0) == 1050.0


def test_capacity_margin_sign():
    assert capacity_margin(1200.0, 1000.0) == 200.0
    assert capacity_margin(900.0, 1000.0) == -100.0  # shortfall


def test_severity_reduction_fraction():
    # reserve trims peak from 1000 to 800 -> 20% severity reduction
    assert severity_reduction(1000.0, 800.0) == pytest.approx(0.2)
    assert severity_reduction(1000.0, 1000.0) == 0.0


def test_severity_reduction_requires_positive_baseline():
    with pytest.raises(ValueError):
        severity_reduction(0.0, 0.0)


def test_equivalent_full_cycles_basic():
    assert equivalent_full_cycles(1000.0, rated_energy_mwh=500.0) == 2.0
    assert equivalent_full_cycles(250.0, rated_energy_mwh=1000.0) == pytest.approx(0.25)


def test_equivalent_full_cycles_zero_discharge():
    assert equivalent_full_cycles(0.0, rated_energy_mwh=1000.0) == 0.0


def test_equivalent_full_cycles_requires_positive_rated_energy():
    with pytest.raises(ValueError):
        equivalent_full_cycles(100.0, rated_energy_mwh=0.0)
    with pytest.raises(ValueError):
        equivalent_full_cycles(100.0, rated_energy_mwh=-1.0)


def test_equivalent_full_cycles_rejects_negative_discharge():
    with pytest.raises(ValueError):
        equivalent_full_cycles(-1.0, rated_energy_mwh=1000.0)


def test_equivalent_full_cycles_rated_energy_is_keyword_only():
    # Guards against a silent argument swap: two bare same-unit floats like
    # (1000, 250) would give a plausible but wrong number (4.0 instead of 0.25)
    # if rated_energy_mwh could be passed positionally.
    with pytest.raises(TypeError):
        equivalent_full_cycles(1000.0, 250.0)  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Phase 1: fuel security metrics
# --------------------------------------------------------------------------- #

_OIL = [100.0, 200.0, 300.0]
_GAS = [50.0, 50.0, 50.0]
_WIND = [10.0, 20.0, 30.0]
_DISPATCHED = [5.0, 5.0, 5.0]


def test_fuel_fired_generation_offset_mwh_worked_example():
    assert fuel_fired_generation_offset_mwh(
        oil_generation_mw=_OIL,
        gas_generation_mw=_GAS,
        wind_generation_mw=_WIND,
        capacity_dispatched_mw=_DISPATCHED,
    ) == pytest.approx(675.0)  # 600 + 150 - 60 - 15


def test_fuel_fired_generation_offset_mwh_zero_wind_and_dispatch():
    assert fuel_fired_generation_offset_mwh(
        oil_generation_mw=_OIL,
        gas_generation_mw=_GAS,
        wind_generation_mw=[0.0, 0.0, 0.0],
        capacity_dispatched_mw=[0.0, 0.0, 0.0],
    ) == pytest.approx(750.0)


def test_fuel_fired_generation_offset_mwh_negative_when_clean_supply_exceeds_fossil():
    # Zero oil and gas: wind + storage alone exceed nothing, so the result is
    # negative (risk R5: this reads as "fossil generation remaining", not
    # "displaced" -- implemented as written, sign not flipped).
    assert fuel_fired_generation_offset_mwh(
        oil_generation_mw=[0.0, 0.0, 0.0],
        gas_generation_mw=[0.0, 0.0, 0.0],
        wind_generation_mw=_WIND,
        capacity_dispatched_mw=_DISPATCHED,
    ) == pytest.approx(-75.0)


def test_fuel_fired_generation_offset_mwh_all_empty_returns_zero():
    assert fuel_fired_generation_offset_mwh(
        oil_generation_mw=[], gas_generation_mw=[], wind_generation_mw=[], capacity_dispatched_mw=[]
    ) == 0.0


@pytest.mark.parametrize("bad_index", [0, 1, 2, 3])
def test_fuel_fired_generation_offset_mwh_length_mismatch_raises(bad_index):
    series = [_OIL, _GAS, _WIND, _DISPATCHED]
    series[bad_index] = series[bad_index][:-1]
    with pytest.raises(ValueError):
        fuel_fired_generation_offset_mwh(
            oil_generation_mw=series[0],
            gas_generation_mw=series[1],
            wind_generation_mw=series[2],
            capacity_dispatched_mw=series[3],
        )


@pytest.mark.parametrize("bad_index", [0, 1, 2, 3])
def test_fuel_fired_generation_offset_mwh_negative_element_raises(bad_index):
    series = [list(_OIL), list(_GAS), list(_WIND), list(_DISPATCHED)]
    series[bad_index][0] = -1.0
    with pytest.raises(ValueError):
        fuel_fired_generation_offset_mwh(
            oil_generation_mw=series[0],
            gas_generation_mw=series[1],
            wind_generation_mw=series[2],
            capacity_dispatched_mw=series[3],
        )


def test_fuel_fired_generation_offset_mwh_is_keyword_only():
    with pytest.raises(TypeError):
        fuel_fired_generation_offset_mwh(_OIL, _GAS, _WIND, _DISPATCHED)  # type: ignore[misc]


def test_fuel_offset_fraction_worked_example():
    assert fuel_offset_fraction(675.0, total_generation_mw=[200.0, 300.0, 400.0]) == pytest.approx(
        0.75
    )


def test_fuel_offset_fraction_zero_total_generation_raises():
    with pytest.raises(ValueError):
        fuel_offset_fraction(675.0, total_generation_mw=[0.0, 0.0, 0.0])


def test_fuel_offset_fraction_empty_total_generation_raises():
    with pytest.raises(ValueError):
        fuel_offset_fraction(675.0, total_generation_mw=[])


def test_fuel_offset_fraction_negative_offset_gives_negative_fraction():
    assert fuel_offset_fraction(-75.0, total_generation_mw=[100.0, 100.0]) == pytest.approx(-0.375)


# --------------------------------------------------------------------------- #
# Phase 2: recharge mismatch family
# --------------------------------------------------------------------------- #


def test_recharge_opportunity_mw_basic_on_dispatch_hours():
    # Dispatch hours (ACTIVE_PEAK etc.) keep the old surplus formula.
    assert recharge_opportunity_mw(
        hourly_wind_mw=[100.0, 0.0, 50.0],
        hourly_load_mw=[80.0, 80.0, 10.0],
        hourly_discharge_mw=[0.0, 20.0, 0.0],
        hourly_state=[HourState.ACTIVE_PEAK] * 3,
    ) == [20.0, 0.0, 40.0]


def test_recharge_opportunity_mw_discharge_above_load_clamps_net_not_wind():
    assert recharge_opportunity_mw(
        hourly_wind_mw=[30.0],
        hourly_load_mw=[10.0],
        hourly_discharge_mw=[20.0],
        hourly_state=[HourState.ACTIVE_PEAK],
    ) == [30.0]


def test_recharge_opportunity_mw_charges_from_wind_hours_ignore_load_and_discharge():
    # D4: PRE_CHARGE and ACTIVE_OFF_PEAK hours report the full wind value,
    # whatever load and discharge say.
    assert recharge_opportunity_mw(
        hourly_wind_mw=[100.0, 50.0],
        hourly_load_mw=[80.0, 80.0],
        hourly_discharge_mw=[0.0, 0.0],
        hourly_state=[HourState.PRE_CHARGE, HourState.ACTIVE_OFF_PEAK],
    ) == [100.0, 50.0]


def test_recharge_opportunity_mw_non_event_hour_is_zero():
    # D4: NON_EVENT hours report zero opportunity: all their wind goes to the
    # grid by design, so there is no missed opportunity to report.
    assert recharge_opportunity_mw(
        hourly_wind_mw=[100.0],
        hourly_load_mw=[10.0],
        hourly_discharge_mw=[0.0],
        hourly_state=[HourState.NON_EVENT],
    ) == [0.0]


@pytest.mark.parametrize("bad_index", [0, 1, 2])
def test_recharge_opportunity_mw_length_mismatch_raises(bad_index):
    series = [[100.0, 0.0], [80.0, 80.0], [0.0, 20.0]]
    series[bad_index] = series[bad_index][:-1]
    with pytest.raises(ValueError):
        recharge_opportunity_mw(
            hourly_wind_mw=series[0],
            hourly_load_mw=series[1],
            hourly_discharge_mw=series[2],
            hourly_state=[HourState.ACTIVE_PEAK, HourState.ACTIVE_PEAK],
        )


@pytest.mark.parametrize("bad_index", [0, 1, 2])
def test_recharge_opportunity_mw_negative_element_raises(bad_index):
    series = [[100.0, 0.0], [80.0, 80.0], [0.0, 20.0]]
    series[bad_index] = list(series[bad_index])
    series[bad_index][0] = -1.0
    with pytest.raises(ValueError):
        recharge_opportunity_mw(
            hourly_wind_mw=series[0],
            hourly_load_mw=series[1],
            hourly_discharge_mw=series[2],
            hourly_state=[HourState.ACTIVE_PEAK, HourState.ACTIVE_PEAK],
        )


def test_cycle_recharge_mismatch_mwh_basic():
    assert cycle_recharge_mismatch_mwh(
        recharge_opportunity_mw=[10.0, 20.0, 30.0], actual_recharged_mw=[10.0, 15.0, 20.0]
    ) == pytest.approx(15.0)


def test_cycle_recharge_mismatch_mwh_equal_series_gives_zero():
    assert cycle_recharge_mismatch_mwh(
        recharge_opportunity_mw=[10.0, 20.0], actual_recharged_mw=[10.0, 20.0]
    ) == 0.0


def test_cycle_recharge_mismatch_mwh_actual_above_opportunity_is_negative():
    assert cycle_recharge_mismatch_mwh(
        recharge_opportunity_mw=[10.0], actual_recharged_mw=[20.0]
    ) == pytest.approx(-10.0)


def test_cycle_recharge_mismatch_mwh_length_mismatch_raises():
    with pytest.raises(ValueError):
        cycle_recharge_mismatch_mwh(
            recharge_opportunity_mw=[10.0, 20.0], actual_recharged_mw=[10.0]
        )


def test_cycle_recharge_mismatch_mwh_negative_element_raises():
    with pytest.raises(ValueError):
        cycle_recharge_mismatch_mwh(
            recharge_opportunity_mw=[-1.0], actual_recharged_mw=[1.0]
        )


def test_average_recharge_mismatch_mwh_basic():
    assert average_recharge_mismatch_mwh([10.0, 20.0, 30.0]) == pytest.approx(20.0)


def test_average_recharge_mismatch_mwh_empty_is_none():
    assert average_recharge_mismatch_mwh([]) is None


def test_average_recharge_mismatch_mwh_mixed_sign():
    assert average_recharge_mismatch_mwh([-10.0, 10.0]) == 0.0


def test_recharge_capacity_mismatch_fraction_worked_example():
    # 700 / 14000 = 5%, sits inside the Overview RCM score table.
    assert recharge_capacity_mismatch_fraction(
        700.0, maximum_available_capacity_mwh=14000.0
    ) == pytest.approx(0.05)


def test_recharge_capacity_mismatch_fraction_zero_denominator_raises():
    with pytest.raises(ValueError):
        recharge_capacity_mismatch_fraction(700.0, maximum_available_capacity_mwh=0.0)


def test_recharge_capacity_mismatch_fraction_negative_denominator_raises():
    with pytest.raises(ValueError):
        recharge_capacity_mismatch_fraction(700.0, maximum_available_capacity_mwh=-1.0)


def test_recharge_capacity_mismatch_fraction_negative_average_gives_negative_fraction():
    assert recharge_capacity_mismatch_fraction(
        -700.0, maximum_available_capacity_mwh=14000.0
    ) == pytest.approx(-0.05)


def _wind_and_load_day(i: int, wind_mw: float, load_mw: float) -> DayProfile:
    return DayProfile(
        date=date(2026, 2, 1) + timedelta(days=i),
        hourly_load_mw=tuple([load_mw] * 24),
        hourly_wind_mw=tuple([wind_mw] * 24),
        demand_percentile=0.95,
        wind_forecast_frac=0.9,
    )


def _pre_charge_schedule(days: list[DayProfile]) -> OperatingSchedule:
    return OperatingSchedule(
        days=tuple(
            DaySchedule(date=d.date, mode=DayMode.PRE_CHARGE, peak_window=None, ramp_hours=0)
            for d in days
        )
    )


def test_recharge_opportunity_drift_guard_sanity_assertion_a():
    # Assertion A: sum(opportunity) >= sum(charge) always holds by construction,
    # because soc_engine.clamp_charge only ever reduces the requested charge.
    # Sanity check only; catches a sign error or a swapped argument, nothing more.
    asset = StorageAsset(total_mwh=20000.0, power_mw=2000.0)
    days = [_wind_and_load_day(0, wind_mw=1500.0, load_mw=8000.0)]
    schedule = _pre_charge_schedule(days)
    result = simulate(asset, days, starting_soc=asset.total_mwh, schedule=schedule)
    opportunity: list[float] = []
    for day, day_schedule, day_result in zip(days, schedule.days, result.daily, strict=True):
        opportunity.extend(
            recharge_opportunity_mw(
                hourly_wind_mw=list(day.hourly_wind_mw),
                hourly_load_mw=[h.gross_load for h in day_result.hourly],
                hourly_discharge_mw=[h.discharge for h in day_result.hourly],
                hourly_state=list(day_schedule.hours),
            )
        )
    charge = [h.charge for d in result.daily for h in d.hourly]
    assert sum(opportunity) >= sum(charge)


def test_recharge_opportunity_matches_simulator_at_scale_where_no_clamp_binds():
    # Assertion B, the real drift guard: at a scale where no clamp binds,
    # opportunity[h] must equal charge[h] for every hour, on the hours that
    # charge from wind (PRE_CHARGE / ACTIVE_OFF_PEAK). This fails the moment
    # recharge.charge_request_mw's rule changes shape. Restricted to the
    # charges-from-wind hours: opportunity and charge differ by design on
    # dispatch hours, where opportunity keeps the old surplus formula and
    # charge is always 0.0 (D4, D8).
    asset = StorageAsset(
        total_mwh=1_000_000.0,
        power_mw=1_000_000.0,
        soc_floor_frac=0.20,
        strategic_reserve_frac=0.10,
    )
    days = [_wind_and_load_day(i, wind_mw=2000.0, load_mw=1000.0) for i in range(2)]
    schedule = _pre_charge_schedule(days)
    result = simulate(asset, days, starting_soc=asset.min_soc_mwh, schedule=schedule)
    for day, day_schedule, day_result in zip(days, schedule.days, result.daily, strict=True):
        opportunity = recharge_opportunity_mw(
            hourly_wind_mw=list(day.hourly_wind_mw),
            hourly_load_mw=[h.gross_load for h in day_result.hourly],
            hourly_discharge_mw=[h.discharge for h in day_result.hourly],
            hourly_state=list(day_schedule.hours),
        )
        for opp, hr, state in zip(opportunity, day_result.hourly, day_schedule.hours, strict=True):
            if state.charges_from_wind:
                assert opp == pytest.approx(hr.charge)


# --------------------------------------------------------------------------- #
# Phase 3: capacity margin, both formulas
# --------------------------------------------------------------------------- #


def test_capacity_margin_deficit_reduction_mw_basic():
    assert capacity_margin_deficit_reduction_mw(
        capacity_margin_with_storage_mw=500.0, capacity_margin_without_storage_mw=300.0
    ) == 200.0


def test_capacity_margin_deficit_reduction_mw_floors_at_zero():
    assert capacity_margin_deficit_reduction_mw(
        capacity_margin_with_storage_mw=300.0, capacity_margin_without_storage_mw=500.0
    ) == 0.0


def test_capacity_margin_deficit_reduction_mw_both_negative():
    assert capacity_margin_deficit_reduction_mw(
        capacity_margin_with_storage_mw=-100.0, capacity_margin_without_storage_mw=-300.0
    ) == pytest.approx(200.0)


@pytest.mark.parametrize("available", [10_000.0, 50_000.0])
def test_capacity_margin_deficit_reduction_mw_cancellation_property(available):
    with_storage = capacity_margin(available, 9_000.0)
    without_storage = capacity_margin(available, 9_500.0)
    assert capacity_margin_deficit_reduction_mw(
        capacity_margin_with_storage_mw=with_storage,
        capacity_margin_without_storage_mw=without_storage,
    ) == pytest.approx(500.0)


def test_capacity_margin_deficit_reduction_series_mw_basic():
    assert capacity_margin_deficit_reduction_series_mw(
        capacity_margin_with_storage_mw=[500.0, 300.0],
        capacity_margin_without_storage_mw=[300.0, 500.0],
    ) == [200.0, 0.0]


def test_capacity_margin_deficit_reduction_series_mw_length_mismatch_raises():
    with pytest.raises(ValueError):
        capacity_margin_deficit_reduction_series_mw(
            capacity_margin_with_storage_mw=[500.0],
            capacity_margin_without_storage_mw=[300.0, 500.0],
        )


def test_capacity_margin_deficit_reduction_series_mw_accepts_negative_margins():
    assert capacity_margin_deficit_reduction_series_mw(
        capacity_margin_with_storage_mw=[-100.0],
        capacity_margin_without_storage_mw=[-300.0],
    ) == [pytest.approx(200.0)]


def test_net_load_change_percent_basic():
    assert net_load_change_percent(
        net_load_dispatch_mw=[90.0, 90.0], net_load_observed_mw=[100.0, 100.0]
    ) == pytest.approx(-10.0)  # source formula's own sign; see findings section 3


def test_net_load_change_percent_negative_element_accepted():
    # sums are 150 and 100, so the change is +50%; proves no element-level sign
    # check applies to the net-load series (they legitimately go negative).
    assert net_load_change_percent(
        net_load_dispatch_mw=[-50.0, 200.0], net_load_observed_mw=[-100.0, 200.0]
    ) == pytest.approx(50.0)


def test_net_load_change_percent_zero_observed_sum_raises():
    with pytest.raises(ValueError):
        net_load_change_percent(
            net_load_dispatch_mw=[100.0, -100.0], net_load_observed_mw=[50.0, -50.0]
        )


def test_net_load_change_percent_negative_observed_sum_raises():
    with pytest.raises(ValueError):
        net_load_change_percent(net_load_dispatch_mw=[10.0], net_load_observed_mw=[-10.0])


def test_net_load_change_percent_length_mismatch_raises():
    with pytest.raises(ValueError):
        net_load_change_percent(net_load_dispatch_mw=[10.0, 20.0], net_load_observed_mw=[10.0])


def test_net_load_change_percent_is_keyword_only():
    with pytest.raises(TypeError):
        net_load_change_percent([90.0], [100.0])  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Phase 5: capital costs
# --------------------------------------------------------------------------- #


def test_estimated_capital_cost_usd_worked_example():
    assert estimated_capital_cost_usd(
        transmission_cost_per_mile_usd=1_000_000.0,
        miles=10.0,
        storage_unit_cost_usd=5_000_000.0,
        total_unit_count=3.0,
    ) == pytest.approx(25_000_000.0)


@pytest.mark.parametrize(
    "field",
    ["transmission_cost_per_mile_usd", "miles", "storage_unit_cost_usd", "total_unit_count"],
)
def test_estimated_capital_cost_usd_negative_input_raises(field):
    kwargs = {
        "transmission_cost_per_mile_usd": 1.0,
        "miles": 1.0,
        "storage_unit_cost_usd": 1.0,
        "total_unit_count": 1.0,
    }
    kwargs[field] = -1.0
    with pytest.raises(ValueError):
        estimated_capital_cost_usd(**kwargs)


def test_cost_per_equivalent_full_cycle_usd_worked_example():
    assert cost_per_equivalent_full_cycle_usd(
        25_000_000.0, annual_equivalent_full_cycles=50.0, solution_lifetime_years=20.0
    ) == pytest.approx(25_000.0)


def test_cost_per_equivalent_full_cycle_usd_negative_capital_cost_raises():
    with pytest.raises(ValueError):
        cost_per_equivalent_full_cycle_usd(
            -1.0, annual_equivalent_full_cycles=50.0, solution_lifetime_years=20.0
        )


def test_cost_per_equivalent_full_cycle_usd_zero_annual_efc_raises():
    with pytest.raises(ValueError):
        cost_per_equivalent_full_cycle_usd(
            25_000_000.0, annual_equivalent_full_cycles=0.0, solution_lifetime_years=20.0
        )


def test_cost_per_equivalent_full_cycle_usd_zero_lifetime_raises():
    with pytest.raises(ValueError):
        cost_per_equivalent_full_cycle_usd(
            25_000_000.0, annual_equivalent_full_cycles=50.0, solution_lifetime_years=0.0
        )


# --- Metric Thresholds v1.1: SWE and CMDR --------------------------------------


def test_swe_matches_the_thresholds_pdf_derivation():
    dispatch = [200.0] * 54
    oil = [4000.0] * 54
    gas = [7920.0] * 54
    result = stress_window_effectiveness_fraction(
        capacity_dispatched_mw=dispatch, oil_generation_mw=oil, gas_generation_mw=gas
    )
    assert result == pytest.approx(0.0168, abs=1e-4)


def test_swe_rejects_length_mismatch():
    with pytest.raises(ValueError):
        stress_window_effectiveness_fraction(
            capacity_dispatched_mw=[1.0, 2.0],
            oil_generation_mw=[1.0],
            gas_generation_mw=[1.0, 2.0],
        )
    with pytest.raises(ValueError):
        stress_window_effectiveness_fraction(
            capacity_dispatched_mw=[1.0, 2.0],
            oil_generation_mw=[1.0, 2.0],
            gas_generation_mw=[1.0],
        )


def test_swe_rejects_negative_series():
    with pytest.raises(ValueError):
        stress_window_effectiveness_fraction(
            capacity_dispatched_mw=[-1.0], oil_generation_mw=[1.0], gas_generation_mw=[1.0]
        )
    with pytest.raises(ValueError):
        stress_window_effectiveness_fraction(
            capacity_dispatched_mw=[1.0], oil_generation_mw=[-1.0], gas_generation_mw=[1.0]
        )
    with pytest.raises(ValueError):
        stress_window_effectiveness_fraction(
            capacity_dispatched_mw=[1.0], oil_generation_mw=[1.0], gas_generation_mw=[-1.0]
        )


def test_swe_raises_when_fossil_sum_is_zero():
    with pytest.raises(ValueError):
        stress_window_effectiveness_fraction(
            capacity_dispatched_mw=[1.0], oil_generation_mw=[0.0], gas_generation_mw=[0.0]
        )


def test_cmdr_percent_matches_the_thresholds_pdf_derivation():
    load = [19213.0] * 54  # p90 18413 + 800 deficit
    result = capacity_margin_deficit_reduction_percent(
        capacity_dispatched_mw=[75.0] * 54, hourly_load_mw=load, p90_threshold_mwh=18413.0
    )
    assert result == pytest.approx(9.375, abs=0.05)

    result_200 = capacity_margin_deficit_reduction_percent(
        capacity_dispatched_mw=[200.0] * 54, hourly_load_mw=load, p90_threshold_mwh=18413.0
    )
    assert result_200 == pytest.approx(25.0)


def test_cmdr_percent_can_exceed_one_hundred():
    load = [19213.0] * 54
    result = capacity_margin_deficit_reduction_percent(
        capacity_dispatched_mw=[921.0] * 54, hourly_load_mw=load, p90_threshold_mwh=18413.0
    )
    assert result == pytest.approx(115.1, abs=0.1)
    assert result > 100.0


def test_cmdr_percent_returns_none_when_no_hour_is_stressed():
    result = capacity_margin_deficit_reduction_percent(
        capacity_dispatched_mw=[75.0] * 24,
        hourly_load_mw=[18000.0] * 24,
        p90_threshold_mwh=18413.0,
    )
    assert result is None


def test_unstressed_hours_are_excluded_from_both_sums():
    single = capacity_margin_deficit_reduction_percent(
        capacity_dispatched_mw=[75.0],
        hourly_load_mw=[18413.0 + 800.0],
        p90_threshold_mwh=18413.0,
    )
    mixed = capacity_margin_deficit_reduction_percent(
        capacity_dispatched_mw=[75.0, 1000.0],
        hourly_load_mw=[18413.0 + 800.0, 18413.0 - 800.0],
        p90_threshold_mwh=18413.0,
    )
    assert mixed == pytest.approx(single)


def test_cmdr_percent_hour_exactly_at_the_threshold_is_not_stressed():
    result = capacity_margin_deficit_reduction_percent(
        capacity_dispatched_mw=[1000.0],
        hourly_load_mw=[18413.0],
        p90_threshold_mwh=18413.0,
    )
    assert result is None


def test_cmdr_percent_rejects_non_positive_threshold():
    with pytest.raises(ValueError):
        capacity_margin_deficit_reduction_percent(
            capacity_dispatched_mw=[1.0], hourly_load_mw=[1.0], p90_threshold_mwh=0.0
        )
    with pytest.raises(ValueError):
        capacity_margin_deficit_reduction_percent(
            capacity_dispatched_mw=[1.0], hourly_load_mw=[1.0], p90_threshold_mwh=-1.0
        )
