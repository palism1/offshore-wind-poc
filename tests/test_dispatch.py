"""Tests for intra-day discharge allocation. Quotes Architecture Step 5 constraint:
    sum_t Discharge(t) <= Budget(d), plus peak-window and ramp-smoothing split.

D7: the allocation is positional now, over a DispatchWindow's planned slots,
not shaped by the day's load series. Rows F1-F4, G and H2 are the plan's
truncation-invariance cases (Section 13, "no-squeeze guarantee", Section 8c).
"""

import pytest

from owr.dispatch import allocate_discharge
from owr.models import DispatchWindow


def _window(peak_slots: tuple[int, ...], ramp_hours: int) -> DispatchWindow:
    return DispatchWindow(peak_slots=peak_slots, ramp_hours=ramp_hours)


UNTRUNCATED = _window((17, 18, 19), ramp_hours=1)


def test_budget_constraint_never_exceeded():
    total, _, _ = allocate_discharge(dispatch_window=UNTRUNCATED, budget_mwh=120.0, power_mw=1000.0)
    assert sum(total) <= 120.0 + 1e-9


def test_power_limit_never_exceeded():
    total, _, _ = allocate_discharge(dispatch_window=UNTRUNCATED, budget_mwh=500.0, power_mw=50.0)
    assert max(total) <= 50.0 + 1e-9


def test_peak_hours_get_more_than_ramp_hours_when_peak_weighted_more():
    total, d_peak, d_smooth = allocate_discharge(
        dispatch_window=UNTRUNCATED,
        budget_mwh=120.0,
        power_mw=1000.0,
        peak_weight=0.7,
        smooth_weight=0.3,
    )
    assert total[18] > total[16]  # a peak hour beats a ramp hour
    assert d_peak[18] > 0
    assert d_smooth[16] > 0


def test_pure_peak_weight_delivers_nothing_to_ramp_hours():
    total, d_peak, d_smooth = allocate_discharge(
        dispatch_window=UNTRUNCATED,
        budget_mwh=120.0,
        power_mw=1000.0,
        peak_weight=1.0,
        smooth_weight=0.0,
    )
    assert sum(d_smooth) == 0.0
    assert d_peak[18] > 0 and d_peak[0] == 0.0


def test_zero_budget_yields_no_discharge():
    total, d_peak, d_smooth = allocate_discharge(
        dispatch_window=UNTRUNCATED, budget_mwh=0.0, power_mw=100.0
    )
    assert sum(total) == 0.0


def test_none_dispatch_window_yields_no_discharge():
    total, d_peak, d_smooth = allocate_discharge(
        dispatch_window=None, budget_mwh=100.0, power_mw=100.0
    )
    assert sum(total) == 0.0
    assert len(total) == 24


# --------------------------------------------------------------------------- #
# F1 — ends before ramp-down
# --------------------------------------------------------------------------- #


def test_f1_ramp_down_slot_entirely_outside_day():
    truncated = _window((21, 22, 23), ramp_hours=1)
    assert truncated.ramp_down_slots == (24,)
    assert truncated.ramp_down_hours == ()

    total_trunc, _, _ = allocate_discharge(
        dispatch_window=truncated, budget_mwh=120.0, power_mw=1000.0
    )
    total_full, _, _ = allocate_discharge(
        dispatch_window=UNTRUNCATED, budget_mwh=120.0, power_mw=1000.0
    )
    # Every surviving hour gets the same per-slot value as the untruncated block
    # shifted 4 hours later: the divisor is the planned count, not the
    # delivered count, so nothing here changed shape because a slot dropped.
    assert total_trunc[20] == total_full[16]  # ramp-up hour
    assert total_trunc[21] == total_full[17]  # peak hours
    assert total_trunc[22] == total_full[18]
    assert total_trunc[23] == total_full[19]
    assert sum(total_trunc) < sum(total_full)  # the dropped ramp-down slot's energy is lost


# --------------------------------------------------------------------------- #
# F2 — ends during ramp-down
# --------------------------------------------------------------------------- #


def test_f2_ramp_down_partially_truncated():
    truncated = _window((20, 21, 22), ramp_hours=2)
    assert truncated.ramp_down_slots == (23, 24)
    assert truncated.ramp_down_hours == (23,)

    full = _window((10, 11, 12), ramp_hours=2)
    assert full.ramp_down_slots == (13, 14)
    assert full.ramp_down_hours == (13, 14)

    total_trunc, _, _ = allocate_discharge(
        dispatch_window=truncated, budget_mwh=140.0, power_mw=1000.0
    )
    total_full, _, _ = allocate_discharge(dispatch_window=full, budget_mwh=140.0, power_mw=1000.0)

    assert total_trunc[18] == total_full[8]  # ramp-up hours unchanged
    assert total_trunc[19] == total_full[9]
    assert total_trunc[23] == total_full[13]  # first ramp-down hour: same per-slot value
    assert total_trunc[23] > 0
    # The second ramp-down slot (hour 24) does not exist in the truncated day;
    # its energy is dropped, not moved onto hour 23 or the peak hours.
    assert sum(total_trunc) < sum(total_full)


# --------------------------------------------------------------------------- #
# G — ends immediately after the peak window
# --------------------------------------------------------------------------- #


def test_g_pure_peak_weight_delivers_whole_budget_to_peak_hours():
    window = _window((21, 22, 23), ramp_hours=1)
    total, d_peak, d_smooth = allocate_discharge(
        dispatch_window=window, budget_mwh=90.0, power_mw=1000.0, peak_weight=1.0, smooth_weight=0.0
    )
    assert sum(total) == 90.0
    assert sum(d_smooth) == 0.0
    assert total[20] == 0.0  # the ramp-up hour gets nothing: the smooth pool is empty
    for h in (21, 22, 23):
        assert total[h] == 30.0


# --------------------------------------------------------------------------- #
# H2 — wrapped peak window truncated (peak-side proof of Section 8c)
# --------------------------------------------------------------------------- #


def test_h2_wrapped_peak_window_loses_a_peak_slot():
    wrapped = _window((22, 23, 24), ramp_hours=1)
    assert wrapped.peak_hours == (22, 23)
    assert wrapped.planned_slot_count == 5

    total_wrapped, d_peak_wrapped, _ = allocate_discharge(
        dispatch_window=wrapped, budget_mwh=150.0, power_mw=1000.0
    )
    total_full, d_peak_full, _ = allocate_discharge(
        dispatch_window=UNTRUNCATED, budget_mwh=150.0, power_mw=1000.0
    )

    assert d_peak_wrapped[22] == d_peak_full[17]
    assert d_peak_wrapped[23] == d_peak_full[18]
    assert total_wrapped[21] == total_full[16]  # ramp-up hour unaffected
    assert sum(total_wrapped) < sum(total_full)  # one third of the peak pool is lost


# --------------------------------------------------------------------------- #
# F3 — ramp planned but wholly outside the day
# --------------------------------------------------------------------------- #


def test_f3_ramp_slots_wholly_outside_day_smooth_pool_dropped_not_folded():
    window = _window(tuple(range(24)), ramp_hours=1)
    assert window.ramp_up_slots == (-1,)
    assert window.ramp_down_slots == (24,)
    assert window.ramp_up_hours == ()
    assert window.ramp_down_hours == ()

    total, d_peak, d_smooth = allocate_discharge(
        dispatch_window=window, budget_mwh=240.0, power_mw=1000.0
    )
    assert sum(d_smooth) == 0.0
    # The smooth pool (half the budget by default weights) is dropped entirely,
    # not folded into the peak hours: each peak hour gets peak_pool / 24, the
    # SAME value it would get if both ramp slots existed.
    assert d_peak[0] == 240.0 * 0.5 / 24
    assert sum(total) == pytest.approx(240.0 * 0.5)


# --------------------------------------------------------------------------- #
# F4 — no ramp configured
# --------------------------------------------------------------------------- #


def test_f4_no_ramp_configured_smooth_pool_folds_into_peak():
    window = _window(tuple(range(24)), ramp_hours=0)
    total, d_peak, d_smooth = allocate_discharge(
        dispatch_window=window, budget_mwh=240.0, power_mw=1000.0
    )
    assert sum(d_smooth) == 0.0
    assert d_peak[0] == 240.0 / 24
    assert sum(total) == pytest.approx(240.0)
