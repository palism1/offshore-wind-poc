"""Tests for owr.models. No test module existed for this file before
docs/archive/plans/PLAN_REVIEW_FIXES.md Phase 1; this creates the mirror the conventions ask for.
"""

import math

import pytest

from owr import storage_physics
from owr.models import StorageAsset


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
