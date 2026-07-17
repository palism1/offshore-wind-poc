"""Tests for outcome metrics (Architecture Step 6 / metrics)."""

import pytest

from owr.metrics import capacity_margin, net_load, severity_reduction


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
