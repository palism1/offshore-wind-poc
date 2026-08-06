"""Tests for owr.models. No test module existed for this file before
docs/PLAN_REVIEW_FIXES.md Phase 1; this creates the mirror the conventions ask for.
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
