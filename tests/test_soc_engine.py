"""Tests for the state equation. Quotes Architecture doc:
    soc(t+1) = soc(t) + charge(t)*eff - discharge(t)/eff
"""

import pytest

from owr.models import StorageAsset
from owr.soc_engine import clamp_charge, clamp_discharge, next_soc, usable_energy


def test_state_equation_lossless():
    # eff = 1.0 -> soc just adds charge and subtracts discharge (Overview "100% efficient")
    assert next_soc(100.0, charge=10.0, discharge=0.0, efficiency=1.0) == 110.0
    assert next_soc(100.0, charge=0.0, discharge=10.0, efficiency=1.0) == 90.0


def test_state_equation_lossy():
    # eff = 0.9 -> charge deposits 0.9*10=9; discharge withdraws 10/0.9 from the tank
    assert next_soc(100.0, charge=10.0, discharge=0.0, efficiency=0.9) == pytest.approx(109.0)
    assert next_soc(100.0, charge=0.0, discharge=10.0, efficiency=0.9) == pytest.approx(
        100.0 - 10.0 / 0.9
    )


def test_negative_flows_rejected():
    with pytest.raises(ValueError):
        next_soc(100.0, charge=-1.0, discharge=0.0, efficiency=1.0)


def test_usable_energy_respects_reserve_floor():
    # 33% of 1000 MWh = 330 MWh protected reserve
    asset = StorageAsset(total_mwh=1000, power_mw=100, soc_floor_frac=0.33)
    assert asset.min_soc_mwh == pytest.approx(330.0)
    assert usable_energy(500.0, asset) == pytest.approx(170.0)
    assert usable_energy(330.0, asset) == 0.0
    assert usable_energy(200.0, asset) == 0.0  # below floor -> nothing usable


def test_clamp_discharge_by_floor_and_power():
    asset = StorageAsset(total_mwh=1000, power_mw=50, soc_floor_frac=0.33)
    # want 200 but only 170 usable and power caps at 50
    assert clamp_discharge(500.0, 200.0, asset) == 50.0
    # power not binding: usable (170) is the limit... but power (50) is smaller, so 50
    assert clamp_discharge(500.0, 100.0, asset) == 50.0


def test_clamp_charge_by_headroom_and_power():
    asset = StorageAsset(total_mwh=1000, power_mw=50, efficiency=1.0)
    assert clamp_charge(980.0, 40.0, asset) == pytest.approx(20.0)  # headroom binds
    assert clamp_charge(500.0, 999.0, asset) == 50.0  # power binds
