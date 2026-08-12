"""Tests for owr.models. No test module existed for this file before
docs/archive/plans/PLAN_REVIEW_FIXES.md Phase 1; this creates the mirror the conventions ask for.
"""

import dataclasses
import math
from datetime import date

import pytest

from owr import storage_physics
from owr.models import (
    DayMode,
    DaySchedule,
    DispatchWindow,
    HourState,
    OperatingSchedule,
    PeakWindow,
    StorageAsset,
)


def test_one_way_efficiency_is_the_square_root_of_round_trip():
    for eff in (0.72, 0.5):
        asset = StorageAsset(total_mwh=1000, power_mw=100, efficiency=eff)
        assert asset.one_way_efficiency == pytest.approx(math.sqrt(eff))


def test_one_way_efficiency_matches_storage_physics_converter():
    for eff in (0.72, 0.5):
        asset = StorageAsset(total_mwh=1000, power_mw=100, efficiency=eff)
        assert asset.one_way_efficiency == pytest.approx(
            storage_physics.one_way_from_round_trip(eff)
        )


def test_one_way_efficiency_is_one_at_the_lossless_default():
    asset = StorageAsset(total_mwh=1000, power_mw=100)
    assert asset.one_way_efficiency == 1.0


def test_negative_soc_floor_frac_rejected():
    with pytest.raises(ValueError):
        StorageAsset(total_mwh=1000, power_mw=100, soc_floor_frac=-0.1)


def test_negative_strategic_reserve_frac_rejected():
    with pytest.raises(ValueError):
        StorageAsset(total_mwh=1000, power_mw=100, strategic_reserve_frac=-0.1)


@pytest.mark.parametrize(("floor", "reserve"), [(0.9, 0.9), (0.5, 0.5)])
def test_fraction_sum_at_or_above_one_rejected(floor, reserve):
    with pytest.raises(ValueError):
        StorageAsset(
            total_mwh=1000, power_mw=100, soc_floor_frac=floor, strategic_reserve_frac=reserve
        )


def test_fraction_sum_just_below_one_accepted():
    asset = StorageAsset(
        total_mwh=1000, power_mw=100, soc_floor_frac=0.6, strategic_reserve_frac=0.39
    )
    assert asset.min_soc_mwh == pytest.approx(990.0)


def test_default_fractions_still_build():
    asset = StorageAsset(total_mwh=1000, power_mw=100)
    assert asset.soc_floor_frac == 0.20
    assert asset.strategic_reserve_frac == 0.10


# --- HourState -----------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "day_mode"),
    [
        (HourState.NON_EVENT, DayMode.NON_EVENT),
        (HourState.PRE_CHARGE, DayMode.PRE_CHARGE),
        (HourState.ACTIVE_OFF_PEAK, DayMode.ACTIVE_EVENT),
        (HourState.ACTIVE_RAMP_UP, DayMode.ACTIVE_EVENT),
        (HourState.ACTIVE_PEAK, DayMode.ACTIVE_EVENT),
        (HourState.ACTIVE_RAMP_DOWN, DayMode.ACTIVE_EVENT),
    ],
)
def test_hour_state_day_mode(state, day_mode):
    assert state.day_mode is day_mode


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (HourState.NON_EVENT, False),
        (HourState.PRE_CHARGE, True),
        (HourState.ACTIVE_OFF_PEAK, True),
        (HourState.ACTIVE_RAMP_UP, False),
        (HourState.ACTIVE_PEAK, False),
        (HourState.ACTIVE_RAMP_DOWN, False),
    ],
)
def test_hour_state_charges_from_wind(state, expected):
    assert state.charges_from_wind is expected


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        (HourState.NON_EVENT, False),
        (HourState.PRE_CHARGE, False),
        (HourState.ACTIVE_OFF_PEAK, False),
        (HourState.ACTIVE_RAMP_UP, True),
        (HourState.ACTIVE_PEAK, True),
        (HourState.ACTIVE_RAMP_DOWN, True),
    ],
)
def test_hour_state_is_dispatch_hour(state, expected):
    assert state.is_dispatch_hour is expected


# --- DispatchWindow --------------------------------------------------------


def _peak_window(start_hour: int, width: int = 3) -> PeakWindow:
    return PeakWindow(
        start_hour=start_hour,
        clock_hours=tuple((start_hour + k) % 24 for k in range(width)),
        load_mw=tuple(float(k) for k in range(width)),
        wrapped=start_hour + width > 24,
        candidates_considered=22,
    )


def test_dispatch_window_around_builds_consecutive_peak_slots():
    window = DispatchWindow.around(_peak_window(17), ramp_hours=1)
    assert window.peak_slots == (17, 18, 19)
    assert window.ramp_up_slots == (16,)
    assert window.ramp_down_slots == (20,)
    assert window.peak_hours == (17, 18, 19)
    assert window.ramp_up_hours == (16,)
    assert window.ramp_down_hours == (20,)
    assert window.dispatch_hours == (16, 17, 18, 19, 20)
    assert window.planned_slot_count == 5


def test_dispatch_window_truncates_ramp_down_at_day_end():
    window = DispatchWindow(peak_slots=(21, 22, 23), ramp_hours=1)
    assert window.ramp_down_slots == (24,)
    assert window.ramp_down_hours == ()
    assert window.planned_slot_count == 5


def test_dispatch_window_truncates_ramp_up_before_day_start():
    window = DispatchWindow(peak_slots=(0, 1, 2), ramp_hours=1)
    assert window.ramp_up_slots == (-1,)
    assert window.ramp_up_hours == ()


def test_dispatch_window_rejects_empty_peak_slots():
    with pytest.raises(ValueError):
        DispatchWindow(peak_slots=(), ramp_hours=1)


def test_dispatch_window_rejects_non_consecutive_peak_slots():
    with pytest.raises(ValueError):
        DispatchWindow(peak_slots=(1, 3), ramp_hours=1)


def test_dispatch_window_rejects_non_ascending_peak_slots():
    with pytest.raises(ValueError):
        DispatchWindow(peak_slots=(3, 2, 1), ramp_hours=1)


def test_dispatch_window_rejects_no_slot_in_day():
    with pytest.raises(ValueError):
        DispatchWindow(peak_slots=(24, 25, 26), ramp_hours=1)


def test_dispatch_window_rejects_negative_ramp_hours():
    with pytest.raises(ValueError):
        DispatchWindow(peak_slots=(1, 2, 3), ramp_hours=-1)


# --- DaySchedule ------------------------------------------------------------


def test_day_schedule_non_event_day_is_non_event_all_hours():
    ds = DaySchedule(date=date(2026, 1, 1), mode=DayMode.NON_EVENT, peak_window=None, ramp_hours=0)
    assert ds.hours == (HourState.NON_EVENT,) * 24
    assert ds.dispatch_window is None


def test_day_schedule_pre_charge_day_is_pre_charge_all_hours():
    ds = DaySchedule(date=date(2026, 1, 1), mode=DayMode.PRE_CHARGE, peak_window=None, ramp_hours=0)
    assert ds.hours == (HourState.PRE_CHARGE,) * 24


def test_day_schedule_active_event_day_hours_match_dispatch_window():
    ds = DaySchedule(
        date=date(2026, 1, 1),
        mode=DayMode.ACTIVE_EVENT,
        peak_window=_peak_window(17),
        ramp_hours=1,
    )
    assert ds.hours[16] is HourState.ACTIVE_RAMP_UP
    assert ds.hours[17] is HourState.ACTIVE_PEAK
    assert ds.hours[18] is HourState.ACTIVE_PEAK
    assert ds.hours[19] is HourState.ACTIVE_PEAK
    assert ds.hours[20] is HourState.ACTIVE_RAMP_DOWN
    for h in range(24):
        if h not in (16, 17, 18, 19, 20):
            assert ds.hours[h] is HourState.ACTIVE_OFF_PEAK
    assert ds.charges_from_wind(0) is True
    assert ds.is_dispatch_hour(17) is True


def test_day_schedule_rejects_active_event_without_peak_window():
    with pytest.raises(ValueError):
        DaySchedule(
            date=date(2026, 1, 1), mode=DayMode.ACTIVE_EVENT, peak_window=None, ramp_hours=0
        )


def test_day_schedule_rejects_peak_window_on_non_active_day():
    with pytest.raises(ValueError):
        DaySchedule(
            date=date(2026, 1, 1),
            mode=DayMode.NON_EVENT,
            peak_window=_peak_window(17),
            ramp_hours=0,
        )


def test_day_schedule_rejects_negative_ramp_hours():
    with pytest.raises(ValueError):
        DaySchedule(
            date=date(2026, 1, 1),
            mode=DayMode.ACTIVE_EVENT,
            peak_window=_peak_window(17),
            ramp_hours=-1,
        )


def test_day_schedule_rejects_ramp_hours_without_peak_window():
    with pytest.raises(ValueError):
        DaySchedule(date=date(2026, 1, 1), mode=DayMode.NON_EVENT, peak_window=None, ramp_hours=1)


def test_day_schedule_structural_guard_hours_and_dispatch_window_not_stored():
    """Protects Section 4.3's central decision: hours and dispatch_window must be
    derived cached_property values, never constructor fields, so no later change
    can store the two facts twice and let them disagree."""
    field_names = {f.name for f in dataclasses.fields(DaySchedule)}
    assert "hours" not in field_names
    assert "dispatch_window" not in field_names


def test_dispatch_window_structural_guard_ramp_slots_not_stored():
    field_names = {f.name for f in dataclasses.fields(DispatchWindow)}
    assert "ramp_up_slots" not in field_names
    assert "ramp_down_slots" not in field_names


# --- OperatingSchedule -------------------------------------------------------


def _day_schedule(d: date, mode: DayMode = DayMode.NON_EVENT) -> DaySchedule:
    return DaySchedule(date=d, mode=mode, peak_window=None, ramp_hours=0)


def test_operating_schedule_for_date_and_slice_for():
    days = (_day_schedule(date(2026, 1, 1)), _day_schedule(date(2026, 1, 2)))
    schedule = OperatingSchedule(days=days)
    assert schedule.for_date(date(2026, 1, 2)) is days[1]
    assert schedule.slice_for([date(2026, 1, 1), date(2026, 1, 2)]) == days


def test_operating_schedule_for_date_raises_on_missing_date():
    schedule = OperatingSchedule(days=(_day_schedule(date(2026, 1, 1)),))
    with pytest.raises(ValueError):
        schedule.for_date(date(2026, 1, 5))


def test_operating_schedule_slice_for_raises_on_missing_date():
    schedule = OperatingSchedule(days=(_day_schedule(date(2026, 1, 1)),))
    with pytest.raises(ValueError):
        schedule.slice_for([date(2026, 1, 1), date(2026, 1, 5)])


def test_operating_schedule_rejects_non_ascending_dates():
    with pytest.raises(ValueError):
        OperatingSchedule(days=(_day_schedule(date(2026, 1, 2)), _day_schedule(date(2026, 1, 1))))


def test_operating_schedule_rejects_duplicate_dates():
    with pytest.raises(ValueError):
        OperatingSchedule(days=(_day_schedule(date(2026, 1, 1)), _day_schedule(date(2026, 1, 1))))
