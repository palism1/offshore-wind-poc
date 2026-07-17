"""Tests for intra-day discharge allocation. Quotes Architecture Step 5 constraint:
    sum_t Discharge(t) <= Budget(d), plus peak-reduction and ramp-smoothing split.
"""

from owr.dispatch import allocate_discharge

# A day with one clear peak at hour 18.
LOAD = [100.0] * 24
LOAD[18] = 300.0
LOAD[17] = 200.0


def test_budget_constraint_never_exceeded():
    total, _, _ = allocate_discharge(LOAD, budget_mwh=120.0, power_mw=1000.0)
    assert sum(total) <= 120.0 + 1e-9


def test_power_limit_never_exceeded():
    total, _, _ = allocate_discharge(LOAD, budget_mwh=500.0, power_mw=50.0)
    assert max(total) <= 50.0 + 1e-9


def test_peak_hour_gets_the_most_discharge():
    total, _, _ = allocate_discharge(LOAD, budget_mwh=120.0, power_mw=1000.0)
    assert total.index(max(total)) == 18  # the peak hour is shaved hardest


def test_pure_peak_weight_ignores_flat_ramp_regions():
    # peak_weight only: discharge concentrates on above-mean hours (17, 18)
    total, d_peak, d_smooth = allocate_discharge(
        LOAD, budget_mwh=120.0, power_mw=1000.0, peak_weight=1.0, smooth_weight=0.0
    )
    assert sum(d_smooth) == 0.0
    assert d_peak[18] > 0 and d_peak[0] == 0.0


def test_zero_budget_yields_no_discharge():
    total, d_peak, d_smooth = allocate_discharge(LOAD, budget_mwh=0.0, power_mw=100.0)
    assert sum(total) == 0.0
