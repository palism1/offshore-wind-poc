"""Tests for priority and daily budget. Quotes Architecture:
    Priority(d) = 0.7*DemandPercentile + 0.3*WindForecast
    plus the "80% energy budget rule".
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


def test_daily_budget_single_day_is_80pct_cap():
    # one remaining day -> full 80% of usable energy
    budget = daily_budget(1000.0, day_priority=0.5, remaining_priority_sum=0.5, config=CFG)
    assert budget == pytest.approx(800.0)


def test_daily_budget_splits_by_priority_share():
    # two days, this one carries 1/4 of remaining priority -> 800 * 0.25 = 200
    budget = daily_budget(1000.0, day_priority=0.5, remaining_priority_sum=2.0, config=CFG)
    assert budget == pytest.approx(200.0)


def test_daily_budget_zero_when_no_usable_energy():
    assert daily_budget(0.0, 0.5, 0.5, CFG) == 0.0


def test_recharge_sufficiency_ratio():
    assert recharge_sufficiency_ratio(150.0, 100.0) == pytest.approx(1.5)
    assert recharge_sufficiency_ratio(50.0, 100.0) == pytest.approx(0.5)
    assert recharge_sufficiency_ratio(50.0, 0.0) is None


def test_priority_weights_must_sum_to_one():
    with pytest.raises(ValueError):
        Config(priority_demand_weight=0.6, priority_wind_weight=0.3)
