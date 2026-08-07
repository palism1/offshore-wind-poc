"""Tests for priority and daily budget. Quotes Architecture:
    Priority(d) = 0.7*DemandPercentile + 0.3*WindForecast
    plus Component 5's two-term minimum (Week 4B change 7, revised 2026-08-06):
    daily_budget = min(available_charge / remaining_stress_days,
                        energy_recharged_over_N_remaining_cycles / N_remaining_cycles).
"""

import pytest

from owr.budget import daily_budget, priority, recharge_sufficiency_ratio
from owr.config import Config

CFG = Config()


def test_priority_weights_match_doc():
    # 0.7*0.9 + 0.3*0.5 = 0.78
    assert priority(0.9, 0.5, CFG) == pytest.approx(0.78)
    # pure demand
    assert priority(1.0, 0.0, CFG) == pytest.approx(0.7)


def test_daily_budget_takes_the_smaller_term():
    # available_charge term smaller: 1000/2 = 500 < 900/1 = 900
    assert daily_budget(
        available_charge_mwh=1000.0,
        remaining_stress_days=2,
        expected_recharge_mwh=900.0,
        remaining_cycles=1,
    ) == pytest.approx(500.0)
    # expected_recharge term smaller: 1000/1 = 1000 > 300/3 = 100
    assert daily_budget(
        available_charge_mwh=1000.0,
        remaining_stress_days=1,
        expected_recharge_mwh=300.0,
        remaining_cycles=3,
    ) == pytest.approx(100.0)


def test_daily_budget_single_day_single_cycle_is_the_smaller_raw_term():
    # one remaining day, one remaining cycle -> min(available_charge, expected_recharge)
    assert daily_budget(
        available_charge_mwh=1000.0,
        remaining_stress_days=1,
        expected_recharge_mwh=400.0,
        remaining_cycles=1,
    ) == pytest.approx(400.0)


def test_daily_budget_zero_when_no_usable_energy():
    assert daily_budget(
        available_charge_mwh=0.0,
        remaining_stress_days=1,
        expected_recharge_mwh=500.0,
        remaining_cycles=1,
    ) == 0.0


def test_daily_budget_is_zero_when_recharge_is_zero():
    assert daily_budget(
        available_charge_mwh=1000.0,
        remaining_stress_days=1,
        expected_recharge_mwh=0.0,
        remaining_cycles=1,
    ) == 0.0


def test_daily_budget_rejects_zero_or_negative_denominators():
    with pytest.raises(ValueError):
        daily_budget(
            available_charge_mwh=1000.0,
            remaining_stress_days=0,
            expected_recharge_mwh=500.0,
            remaining_cycles=1,
        )
    with pytest.raises(ValueError):
        daily_budget(
            available_charge_mwh=1000.0,
            remaining_stress_days=1,
            expected_recharge_mwh=500.0,
            remaining_cycles=0,
        )
    with pytest.raises(ValueError):
        daily_budget(
            available_charge_mwh=1000.0,
            remaining_stress_days=-1,
            expected_recharge_mwh=500.0,
            remaining_cycles=1,
        )


def test_daily_budget_rejects_negative_energy():
    with pytest.raises(ValueError):
        daily_budget(
            available_charge_mwh=-1.0,
            remaining_stress_days=1,
            expected_recharge_mwh=500.0,
            remaining_cycles=1,
        )
    with pytest.raises(ValueError):
        daily_budget(
            available_charge_mwh=1000.0,
            remaining_stress_days=1,
            expected_recharge_mwh=-1.0,
            remaining_cycles=1,
        )


def test_recharge_sufficiency_ratio():
    assert recharge_sufficiency_ratio(150.0, 100.0) == pytest.approx(1.5)
    assert recharge_sufficiency_ratio(50.0, 100.0) == pytest.approx(0.5)
    assert recharge_sufficiency_ratio(50.0, 0.0) is None


def test_priority_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        Config(priority_demand_weight=0.6, priority_wind_weight=0.3)
