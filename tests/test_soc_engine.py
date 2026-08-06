"""Tests for the state equation. Quotes Architecture doc:
    soc(t+1) = soc(t) + charge(t)*eff - discharge(t)/eff
"""

import pytest

from owr.models import StorageAsset
from owr.soc_engine import clamp_charge, clamp_discharge, next_soc, usable_energy


def test_state_equation_lossless():
    # one-way eff = 1.0 -> soc just adds charge and subtracts discharge (Overview
    # "100% efficient")
    assert next_soc(100.0, charge=10.0, discharge=0.0, one_way_efficiency=1.0) == 110.0
    assert next_soc(100.0, charge=0.0, discharge=10.0, one_way_efficiency=1.0) == 90.0


def test_state_equation_lossy():
    # one-way eff = 0.9 -> charge deposits 0.9*10=9; discharge withdraws 10/0.9 from
    # the tank
    assert next_soc(
        100.0, charge=10.0, discharge=0.0, one_way_efficiency=0.9
    ) == pytest.approx(109.0)
    assert next_soc(
        100.0, charge=0.0, discharge=10.0, one_way_efficiency=0.9
    ) == pytest.approx(100.0 - 10.0 / 0.9)


def test_negative_flows_rejected():
    with pytest.raises(ValueError):
        next_soc(100.0, charge=-1.0, discharge=0.0, one_way_efficiency=1.0)


def test_usable_energy_respects_reserve_floor():
    # 33% of 1000 MWh = 330 MWh protected reserve (floor only, no strategic reserve)
    asset = StorageAsset(
        total_mwh=1000, power_mw=100, soc_floor_frac=0.33, strategic_reserve_frac=0.0
    )
    assert asset.min_soc_mwh == pytest.approx(330.0)
    assert usable_energy(500.0, asset) == pytest.approx(170.0)
    assert usable_energy(330.0, asset) == 0.0
    assert usable_energy(200.0, asset) == 0.0  # below floor -> nothing usable


def test_clamp_discharge_by_floor_and_power():
    asset = StorageAsset(
        total_mwh=1000, power_mw=50, soc_floor_frac=0.33, strategic_reserve_frac=0.0
    )
    # want 200 but only 170 usable and power caps at 50
    assert clamp_discharge(500.0, 200.0, asset) == 50.0
    # power not binding: usable (170) is the limit... but power (50) is smaller, so 50
    assert clamp_discharge(500.0, 100.0, asset) == 50.0


def test_clamp_charge_by_headroom_and_power():
    asset = StorageAsset(total_mwh=1000, power_mw=50, efficiency=1.0)
    assert clamp_charge(980.0, 40.0, asset) == pytest.approx(20.0)  # headroom binds
    assert clamp_charge(500.0, 999.0, asset) == 50.0  # power binds


def test_round_trip_efficiency_is_realized_across_a_full_cycle():
    # D1: efficiency is round trip, and the engine splits it per leg. Charging 100
    # MWh at the terminals and then discharging the tank back down to empty must
    # deliver 0.72 * 100 = 72 MWh at the terminals, not 0.72**2 * 100 = 51.84.
    asset = StorageAsset(
        total_mwh=1000,
        power_mw=1000,
        efficiency=0.72,
        soc_floor_frac=0.0,
        strategic_reserve_frac=0.0,
    )
    soc = 0.0
    charge = clamp_charge(soc, 100.0, asset)
    soc = next_soc(soc, charge=charge, discharge=0.0, one_way_efficiency=asset.one_way_efficiency)
    assert soc == pytest.approx(100.0 * asset.one_way_efficiency)

    # Discharge leg through next_soc alone (not clamp_discharge, which still
    # returns tank energy until Phase 3 and would drive soc below zero here).
    delivered = soc * asset.one_way_efficiency
    soc = next_soc(
        soc, charge=0.0, discharge=delivered, one_way_efficiency=asset.one_way_efficiency
    )
    assert delivered == pytest.approx(72.0)
    assert soc == pytest.approx(0.0)


def test_clamp_discharge_caps_at_deliverable_energy_above_the_floor():
    # F1's own repro: at eff=0.64 the leg is exactly 0.8 (sqrt(0.64)). Tank energy
    # above the floor is 40 - 30 = 10 MWh; deliverable at the terminals is
    # 10 * 0.8 = 8 MWh, not the 10 MWh tank figure the pre-fix code returned.
    asset = StorageAsset(
        total_mwh=100, power_mw=100, efficiency=0.64, soc_floor_frac=0.30,
        strategic_reserve_frac=0.0,
    )
    assert clamp_discharge(40.0, 50.0, asset) == pytest.approx(8.0)
    assert next_soc(
        40.0, charge=0.0, discharge=8.0, one_way_efficiency=asset.one_way_efficiency
    ) == pytest.approx(30.0)


@pytest.mark.parametrize("efficiency", [0.5, 0.72])
def test_floor_invariant_holds_at_lossy_efficiency(efficiency):
    # F7a: the engine must never discharge below the protected reserve floor,
    # source rule docs/source/2026-08-05_Metric_Thresholds_v1.1.pdf, RCM winter
    # derivation ("Protected reserve floor = 20% of Total Capacity"). Tolerance
    # because the round trip through a multiply and a divide is not exact in
    # IEEE 754; no epsilon is added to production code.
    asset = StorageAsset(total_mwh=1000, power_mw=1000, efficiency=efficiency)
    min_soc = asset.min_soc_mwh
    socs = (min_soc, min_soc + 1, asset.total_mwh / 2, asset.total_mwh)
    requests = (0.0, 1.0, asset.total_mwh, 10 * asset.total_mwh)
    for soc in socs:
        for requested in requests:
            discharge = clamp_discharge(soc, requested, asset)
            new_soc = next_soc(
                soc, charge=0.0, discharge=discharge, one_way_efficiency=asset.one_way_efficiency
            )
            assert new_soc >= min_soc - 1e-9


def test_usable_energy_is_terminal_basis_and_matches_tank_basis_when_lossless():
    lossy = StorageAsset(total_mwh=1000, power_mw=100, efficiency=0.5)
    lossless = StorageAsset(total_mwh=1000, power_mw=100, efficiency=1.0)
    soc = 700.0
    tank_above_floor = soc - lossy.min_soc_mwh
    assert usable_energy(soc, lossy) == pytest.approx(
        tank_above_floor * lossy.one_way_efficiency
    )
    assert usable_energy(soc, lossless) == pytest.approx(soc - lossless.min_soc_mwh)
