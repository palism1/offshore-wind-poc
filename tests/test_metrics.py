"""Tests for outcome metrics (Architecture Step 6 / metrics)."""

import pytest

from owr.metrics import capacity_margin, equivalent_full_cycles, net_load, severity_reduction


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
