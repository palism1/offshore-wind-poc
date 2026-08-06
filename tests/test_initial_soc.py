"""Tests for owr.initial_soc. No test module existed for this file before
docs/PLAN_REVIEW_FIXES.md Phase 5; this creates the mirror the conventions ask for,
as Phase 1 does for models.py.
"""

from datetime import date

import pytest

from owr.initial_soc import charge_from_wind
from owr.models import DayProfile, StorageAsset


def test_initial_soc_charges_from_wind_before_event():
    asset = StorageAsset(
        total_mwh=1000,
        power_mw=100,
        efficiency=1.0,
        soc_floor_frac=0.33,
        strategic_reserve_frac=0.0,
    )
    lead = [
        DayProfile(
            date=date(2026, 1, 9),
            hourly_load_mw=(0.0,) * 24,
            hourly_wind_mw=(80.0,) * 24,  # 80 MW * 24 h = 1920 MWh available, capacity-capped
        )
    ]
    soc = charge_from_wind(starting_soc=500.0, lead_days=lead, asset=asset)
    assert soc == asset.total_mwh  # fills to capacity


def test_charge_from_wind_ignores_wind_at_or_below_the_lead_day_load():
    # F5: the simulator's own surplus rule (wind above the hour's load), applied
    # to pre-event charging. Wind at or below load leaves no surplus to charge from.
    asset = StorageAsset(total_mwh=1000, power_mw=100)
    lead = [
        DayProfile(
            date=date(2026, 1, 9),
            hourly_load_mw=(1000.0,) * 24,
            hourly_wind_mw=(800.0,) * 24,
        )
    ]
    soc = charge_from_wind(starting_soc=500.0, lead_days=lead, asset=asset)
    assert soc == 500.0


def test_charge_from_wind_takes_only_the_surplus_above_load():
    asset = StorageAsset(total_mwh=1_000_000, power_mw=100_000)
    lead = [
        DayProfile(
            date=date(2026, 1, 9),
            hourly_load_mw=(1000.0,) * 24,
            hourly_wind_mw=(1200.0,) * 24,
        )
    ]
    soc = charge_from_wind(starting_soc=0.0, lead_days=lead, asset=asset)
    assert soc == pytest.approx(24 * 200.0 * asset.one_way_efficiency)
