"""Tests for owr.recharge: the shared wind-to-storage rule."""

import inspect
from datetime import date

import pytest

from owr.models import DayMode, DayProfile, DaySchedule, HourState, PeakWindow, StorageAsset
from owr.recharge import charge_forward, charge_request_mw, recharge_opportunity_mwh


@pytest.mark.parametrize(
    ("state", "wind", "expected"),
    [
        (HourState.PRE_CHARGE, 50.0, 50.0),
        (HourState.ACTIVE_OFF_PEAK, 50.0, 50.0),
        (HourState.ACTIVE_RAMP_UP, 50.0, 0.0),
        (HourState.ACTIVE_PEAK, 50.0, 0.0),
        (HourState.ACTIVE_RAMP_DOWN, 50.0, 0.0),
        (HourState.NON_EVENT, 50.0, 0.0),
        (HourState.PRE_CHARGE, -50.0, 0.0),
    ],
)
def test_charge_request_mw(state, wind, expected):
    assert charge_request_mw(wind, state) == expected


def _pre_charge_day(d: date, wind: float = 50.0, load: float = 0.0) -> DayProfile:
    return DayProfile(date=d, hourly_load_mw=(load,) * 24, hourly_wind_mw=(wind,) * 24)


def _pre_charge_schedule_day(d: date) -> DaySchedule:
    return DaySchedule(date=d, mode=DayMode.PRE_CHARGE, peak_window=None, ramp_hours=0)


def test_charge_forward_accumulates_pre_charge_wind():
    asset = StorageAsset(total_mwh=1_000_000, power_mw=100_000)
    d = date(2026, 1, 1)
    forecast = charge_forward(
        starting_soc=0.0,
        days=[_pre_charge_day(d, wind=50.0)],
        day_schedules=[_pre_charge_schedule_day(d)],
        asset=asset,
    )
    assert forecast.charged_mwh == pytest.approx(24 * 50.0 * asset.one_way_efficiency)
    assert forecast.final_soc_mwh == pytest.approx(24 * 50.0 * asset.one_way_efficiency)


def test_charge_forward_stops_at_capacity():
    asset = StorageAsset(total_mwh=100.0, power_mw=1000.0)
    d = date(2026, 1, 1)
    forecast = charge_forward(
        starting_soc=0.0,
        days=[_pre_charge_day(d, wind=1000.0)],
        day_schedules=[_pre_charge_schedule_day(d)],
        asset=asset,
    )
    assert forecast.final_soc_mwh == pytest.approx(asset.total_mwh)


def test_charge_forward_length_mismatch_raises():
    asset = StorageAsset(total_mwh=1000.0, power_mw=100.0)
    d = date(2026, 1, 1)
    with pytest.raises(ValueError):
        charge_forward(
            starting_soc=0.0,
            days=[_pre_charge_day(d)],
            day_schedules=[],
            asset=asset,
        )


def test_charge_forward_date_mismatch_raises():
    asset = StorageAsset(total_mwh=1000.0, power_mw=100.0)
    with pytest.raises(ValueError):
        charge_forward(
            starting_soc=0.0,
            days=[_pre_charge_day(date(2026, 1, 1))],
            day_schedules=[_pre_charge_schedule_day(date(2026, 1, 2))],
            asset=asset,
        )


def test_charge_forward_negative_wind_floors_at_zero():
    asset = StorageAsset(total_mwh=1000.0, power_mw=100.0)
    d = date(2026, 1, 1)
    forecast = charge_forward(
        starting_soc=100.0,
        days=[_pre_charge_day(d, wind=-50.0)],
        day_schedules=[_pre_charge_schedule_day(d)],
        asset=asset,
    )
    assert forecast.final_soc_mwh == pytest.approx(100.0)
    assert forecast.charged_mwh == 0.0


def test_charge_forward_non_event_day_charges_nothing():
    asset = StorageAsset(total_mwh=1000.0, power_mw=100.0)
    d = date(2026, 1, 1)
    non_event = DaySchedule(date=d, mode=DayMode.NON_EVENT, peak_window=None, ramp_hours=0)
    forecast = charge_forward(
        starting_soc=100.0,
        days=[_pre_charge_day(d, wind=500.0)],
        day_schedules=[non_event],
        asset=asset,
    )
    assert forecast.final_soc_mwh == pytest.approx(100.0)
    assert forecast.charged_mwh == 0.0


def test_recharge_opportunity_sums_charge_requests():
    d = date(2026, 1, 1)
    total = recharge_opportunity_mwh(
        days=[_pre_charge_day(d, wind=50.0)],
        day_schedules=[_pre_charge_schedule_day(d)],
    )
    # No efficiency factor: this is routed energy, not stored energy.
    assert total == pytest.approx(24 * 50.0)


def test_recharge_opportunity_skips_dispatch_and_non_event_hours():
    d = date(2026, 1, 1)
    active_day = DaySchedule(
        date=d,
        mode=DayMode.ACTIVE_EVENT,
        peak_window=PeakWindow(
            start_hour=18,
            clock_hours=(18,),
            load_mw=(12000.0,),
            wrapped=False,
            candidates_considered=1,
        ),
        ramp_hours=1,
    )
    off_peak_hours = sum(1 for h in active_day.hours if h.charges_from_wind)
    active_total = recharge_opportunity_mwh(
        days=[_pre_charge_day(d, wind=50.0)],
        day_schedules=[active_day],
    )
    assert active_total == pytest.approx(off_peak_hours * 50.0)

    non_event = DaySchedule(date=d, mode=DayMode.NON_EVENT, peak_window=None, ramp_hours=0)
    non_event_total = recharge_opportunity_mwh(
        days=[_pre_charge_day(d, wind=500.0)],
        day_schedules=[non_event],
    )
    assert non_event_total == 0.0


def test_recharge_opportunity_negative_wind_floors_at_zero():
    # D13 parity with charge_request_mw: a negative wind value contributes
    # nothing, the same floor charge_request_mw applies per hour.
    d = date(2026, 1, 1)
    total = recharge_opportunity_mwh(
        days=[_pre_charge_day(d, wind=-50.0)],
        day_schedules=[_pre_charge_schedule_day(d)],
    )
    assert total == 0.0


def test_recharge_opportunity_length_and_date_mismatch_raise():
    d = date(2026, 1, 1)
    with pytest.raises(ValueError):
        recharge_opportunity_mwh(days=[_pre_charge_day(d)], day_schedules=[])
    with pytest.raises(ValueError):
        recharge_opportunity_mwh(
            days=[_pre_charge_day(date(2026, 1, 1))],
            day_schedules=[_pre_charge_schedule_day(date(2026, 1, 2))],
        )


def test_guard_recharge_opportunity_takes_no_soc_and_no_asset():
    """Signature-only guard: it constrains ``recharge_opportunity_mwh``'s own
    parameters and nothing else. It cannot see the ``simulator.py`` call
    site, so it would not catch a future edit there that goes back to
    ``recharge_mod.charge_forward(...).charged_mwh`` — exactly how the
    defect entered (commit e358231, Phase 9). See
    ``test_simulator.py::test_total_discharge_does_not_fall_as_starting_soc_rises``
    (test 7 of PLAN_BUDGET_FULL_TANK_FIX.md), the behavioral guard that reads
    the simulator's output and would catch that mistake.
    """
    assert set(inspect.signature(recharge_opportunity_mwh).parameters) == {
        "days",
        "day_schedules",
    }
