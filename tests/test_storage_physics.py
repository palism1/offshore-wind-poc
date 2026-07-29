"""Tests for `owr.storage_physics` — geometry, energy, power and the {D, h, E}
inversions, validated against the Fraunhofer full-scale spec and the shallow-water
variant in `docs/DATA_SOURCES.md` [4].

Spec numbers are named module-level constants with a citation, per repo convention.
"""

from __future__ import annotations

import pytest

from owr.storage_physics import (
    flow_for_generating_power_m3_s,
    flow_for_pumping_power_m3_s,
    generating_energy_mwh,
    generating_power_mw,
    head_for_energy_m,
    one_way_from_round_trip,
    pumping_power_mw,
    round_trip_from_one_way,
    sphere_energy_mwh,
    sphere_head_m,
    sphere_internal_diameter_m,
    sphere_internal_volume_m3,
    sphere_outer_diameter_for_volume_m,
    sphere_outer_diameter_m,
    volume_for_energy_m3,
)

# docs/DATA_SOURCES.md [4]: Fraunhofer full-scale design — 30 m OD, 20 MWh, 80%
# round-trip (adopted here as one-way per the module's stated interpretation),
# 600-800 m published depth band.
FRAUNHOFER_OUTER_DIAMETER_M = 30.0
FRAUNHOFER_ENERGY_MWH = 20.0
FRAUNHOFER_EFFICIENCY = 0.80
FRAUNHOFER_DEPTH_BAND_M = (600.0, 800.0)

# docs/DATA_SOURCES.md [4]: theoretical shallow-water variant — 30 m OD, 200 m head,
# 0.70 efficiency, yielding 4.5-5.0 MWh depending on wall thickness.
SHALLOW_HEAD_M = 200.0
SHALLOW_EFFICIENCY = 0.70


# --- geometry ------------------------------------------------------------


def test_sphere_internal_volume():
    assert sphere_internal_volume_m3(30.0, 0.5) == pytest.approx(12770.05, rel=1e-3)
    assert sphere_internal_volume_m3(30.0, 1.0) == pytest.approx(11494.04, rel=1e-3)


def test_sphere_outer_diameter_for_volume_round_trips():
    volume = sphere_internal_volume_m3(30.0, 0.75)
    assert sphere_outer_diameter_for_volume_m(volume, 0.75) == pytest.approx(30.0, rel=1e-3)


# --- Fraunhofer validation (load-bearing) ---------------------------------


def test_sphere_head_matches_fraunhofer_at_wall_0_5():
    head = sphere_head_m(
        outer_diameter_m=FRAUNHOFER_OUTER_DIAMETER_M,
        wall_thickness_m=0.5,
        energy_mwh=FRAUNHOFER_ENERGY_MWH,
        efficiency=FRAUNHOFER_EFFICIENCY,
    )
    assert head == pytest.approx(700.90, rel=1e-3)


def test_sphere_head_matches_fraunhofer_at_wall_1_0():
    head = sphere_head_m(
        outer_diameter_m=FRAUNHOFER_OUTER_DIAMETER_M,
        wall_thickness_m=1.0,
        energy_mwh=FRAUNHOFER_ENERGY_MWH,
        efficiency=FRAUNHOFER_EFFICIENCY,
    )
    assert head == pytest.approx(778.71, rel=1e-3)


@pytest.mark.parametrize("wall", [0.5, 0.75, 1.0])
def test_sphere_head_within_published_depth_band(wall):
    head = sphere_head_m(
        outer_diameter_m=FRAUNHOFER_OUTER_DIAMETER_M,
        wall_thickness_m=wall,
        energy_mwh=FRAUNHOFER_ENERGY_MWH,
        efficiency=FRAUNHOFER_EFFICIENCY,
    )
    low, high = FRAUNHOFER_DEPTH_BAND_M
    assert low <= head <= high


# --- shallow-variant validation --------------------------------------------


def test_shallow_energy_at_wall_0_5():
    energy = sphere_energy_mwh(
        outer_diameter_m=30.0,
        wall_thickness_m=0.5,
        head_m=SHALLOW_HEAD_M,
        efficiency=SHALLOW_EFFICIENCY,
    )
    assert energy == pytest.approx(4.9936, rel=1e-3)


def test_shallow_energy_at_wall_1_0():
    energy = sphere_energy_mwh(
        outer_diameter_m=30.0,
        wall_thickness_m=1.0,
        head_m=SHALLOW_HEAD_M,
        efficiency=SHALLOW_EFFICIENCY,
    )
    assert energy == pytest.approx(4.4946, rel=1e-3)


@pytest.mark.parametrize("wall", [0.5, 0.75, 1.0])
def test_shallow_energy_within_band(wall):
    # Assert 4.49, not 4.5: the 1.0 m wall case is 4.4946 MWh and `>= 4.5` fails.
    energy = sphere_energy_mwh(
        outer_diameter_m=30.0,
        wall_thickness_m=wall,
        head_m=SHALLOW_HEAD_M,
        efficiency=SHALLOW_EFFICIENCY,
    )
    assert 4.49 <= energy <= 5.00


# --- power -------------------------------------------------------------


def test_generating_power_at_mitchells_stated_flow():
    # Mitchell's stated flow (~1.02 m3/s) does not give his stated 1.67 MW.
    power = generating_power_mw(
        flow_m3_s=1.02, head_m=SHALLOW_HEAD_M, efficiency=SHALLOW_EFFICIENCY
    )
    assert power == pytest.approx(1.4359, rel=1e-3)


def test_flow_for_1_67_mw():
    flow = flow_for_generating_power_m3_s(
        power_mw=1.67, head_m=SHALLOW_HEAD_M, efficiency=SHALLOW_EFFICIENCY
    )
    assert flow == pytest.approx(1.1863, rel=1e-3)


def test_generating_power_at_corrected_flow():
    power = generating_power_mw(
        flow_m3_s=1.186, head_m=SHALLOW_HEAD_M, efficiency=SHALLOW_EFFICIENCY
    )
    assert power == pytest.approx(1.6696, rel=1e-3)


def test_pump_to_turbine_ratio():
    kwargs = {"flow_m3_s": 1.0, "head_m": SHALLOW_HEAD_M, "efficiency": SHALLOW_EFFICIENCY}
    ratio = pumping_power_mw(**kwargs) / generating_power_mw(**kwargs)
    assert ratio == pytest.approx(2.0408, rel=1e-3)
    assert ratio == pytest.approx(1.0 / SHALLOW_EFFICIENCY**2, rel=1e-6)


def test_flow_for_pumping_power_round_trips():
    flow = flow_for_pumping_power_m3_s(
        power_mw=1.4359, head_m=SHALLOW_HEAD_M, efficiency=SHALLOW_EFFICIENCY
    )
    power = pumping_power_mw(flow_m3_s=flow, head_m=SHALLOW_HEAD_M, efficiency=SHALLOW_EFFICIENCY)
    assert power == pytest.approx(1.4359, rel=1e-3)


# --- efficiency helpers --------------------------------------------------


def test_one_way_from_round_trip():
    assert one_way_from_round_trip(0.70) == pytest.approx(0.836660, rel=1e-4)


def test_round_trip_from_one_way():
    assert round_trip_from_one_way(0.70) == pytest.approx(0.49, rel=1e-6)


@pytest.mark.parametrize("x", [0.35, 0.5, 0.7, 0.8, 1.0])
def test_efficiency_conversions_round_trip(x):
    assert round_trip_from_one_way(one_way_from_round_trip(x)) == pytest.approx(x, rel=1e-9)


def test_efficiency_helpers_reject_out_of_range():
    with pytest.raises(ValueError):
        one_way_from_round_trip(0.0)
    with pytest.raises(ValueError):
        one_way_from_round_trip(1.1)
    with pytest.raises(ValueError):
        round_trip_from_one_way(0.0)
    with pytest.raises(ValueError):
        round_trip_from_one_way(1.1)


# --- inversion round-trips -------------------------------------------------


@pytest.mark.parametrize(
    "outer_diameter_m,wall_thickness_m,head_m,efficiency",
    [
        (30.0, 0.5, 200.0, 0.70),
        (30.0, 1.0, 700.0, 0.80),
        (46.0, 0.75, 150.0, 0.60),
    ],
)
def test_sphere_head_inverts_sphere_energy(outer_diameter_m, wall_thickness_m, head_m, efficiency):
    energy = sphere_energy_mwh(
        outer_diameter_m=outer_diameter_m,
        wall_thickness_m=wall_thickness_m,
        head_m=head_m,
        efficiency=efficiency,
    )
    recovered_head = sphere_head_m(
        outer_diameter_m=outer_diameter_m,
        wall_thickness_m=wall_thickness_m,
        energy_mwh=energy,
        efficiency=efficiency,
    )
    assert recovered_head == pytest.approx(head_m, rel=1e-3)


@pytest.mark.parametrize(
    "outer_diameter_m,wall_thickness_m,head_m,efficiency",
    [
        (30.0, 0.5, 200.0, 0.70),
        (30.0, 1.0, 700.0, 0.80),
        (46.0, 0.75, 150.0, 0.60),
    ],
)
def test_sphere_outer_diameter_inverts_sphere_energy(
    outer_diameter_m, wall_thickness_m, head_m, efficiency
):
    energy = sphere_energy_mwh(
        outer_diameter_m=outer_diameter_m,
        wall_thickness_m=wall_thickness_m,
        head_m=head_m,
        efficiency=efficiency,
    )
    recovered_diameter = sphere_outer_diameter_m(
        head_m=head_m, energy_mwh=energy, efficiency=efficiency, wall_thickness_m=wall_thickness_m
    )
    assert recovered_diameter == pytest.approx(outer_diameter_m, rel=1e-3)


def test_spec_inconsistency_is_pinned():
    # DATA_SOURCES.md [4]'s "~46 m" for 20 MWh at 200 m / 0.70 is the *internal*
    # diameter, not the outer one — the outer diameter at a 0.5 m wall is ~47.05 m.
    # 30 m (what the team actually specified) and ~46-47 m cannot both hold.
    outer = sphere_outer_diameter_m(
        head_m=200.0, energy_mwh=20.0, efficiency=0.70, wall_thickness_m=0.5
    )
    assert outer == pytest.approx(47.05, rel=1e-3)
    internal = sphere_internal_diameter_m(outer, 0.5)
    assert internal == pytest.approx(46.05, rel=1e-3)


# --- validation ------------------------------------------------------------


def test_sphere_internal_diameter_rejects_non_positive_outer_diameter():
    with pytest.raises(ValueError):
        sphere_internal_diameter_m(0.0, 0.5)


def test_sphere_internal_diameter_rejects_negative_wall_thickness():
    with pytest.raises(ValueError):
        sphere_internal_diameter_m(30.0, -0.1)


def test_sphere_internal_diameter_rejects_wall_thickness_too_large():
    with pytest.raises(ValueError):
        sphere_internal_diameter_m(30.0, 15.0)


def test_sphere_outer_diameter_for_volume_rejects_non_positive_volume():
    with pytest.raises(ValueError):
        sphere_outer_diameter_for_volume_m(0.0, 0.5)


def test_generating_energy_rejects_non_positive_volume():
    with pytest.raises(ValueError):
        generating_energy_mwh(volume_m3=0.0, head_m=200.0, efficiency=0.70)


def test_generating_energy_rejects_non_positive_head():
    with pytest.raises(ValueError):
        generating_energy_mwh(volume_m3=1000.0, head_m=0.0, efficiency=0.70)


def test_generating_energy_rejects_bad_efficiency():
    with pytest.raises(ValueError):
        generating_energy_mwh(volume_m3=1000.0, head_m=200.0, efficiency=0.0)
    with pytest.raises(ValueError):
        generating_energy_mwh(volume_m3=1000.0, head_m=200.0, efficiency=1.1)


def test_volume_for_energy_rejects_non_positive_energy():
    with pytest.raises(ValueError):
        volume_for_energy_m3(energy_mwh=0.0, head_m=200.0, efficiency=0.70)


def test_head_for_energy_rejects_non_positive_volume():
    with pytest.raises(ValueError):
        head_for_energy_m(energy_mwh=20.0, volume_m3=0.0, efficiency=0.70)


def test_generating_power_rejects_non_positive_flow():
    with pytest.raises(ValueError):
        generating_power_mw(flow_m3_s=0.0, head_m=200.0, efficiency=0.70)


def test_generating_power_rejects_non_positive_head():
    with pytest.raises(ValueError):
        generating_power_mw(flow_m3_s=1.0, head_m=0.0, efficiency=0.70)


def test_pumping_power_rejects_non_positive_flow():
    with pytest.raises(ValueError):
        pumping_power_mw(flow_m3_s=-1.0, head_m=200.0, efficiency=0.70)


def test_flow_for_generating_power_rejects_non_positive_power():
    with pytest.raises(ValueError):
        flow_for_generating_power_m3_s(power_mw=0.0, head_m=200.0, efficiency=0.70)


def test_flow_for_pumping_power_rejects_non_positive_power():
    with pytest.raises(ValueError):
        flow_for_pumping_power_m3_s(power_mw=-1.0, head_m=200.0, efficiency=0.70)
