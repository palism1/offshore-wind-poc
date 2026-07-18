"""The protected-reserve default split is a team design decision (2026-07-17):
20% floor + 10% reserve = 30% of total storage protected, leaving 70% for regular
operations. The engine already models the floor and the reserve as two separate
fractions; these tests pin the default values across the three code surfaces that
carry them so the decision cannot silently drift back to the old 33% placeholder.

The *usage rules* (when the 10% reserve and 20% floor may each be drawn down) are
still an open team decision; until then both are treated as one protected floor.
"""

from datetime import date

import pytest

from owr.api.schemas import ScenarioCreate
from owr.config import Config
from owr.models import StorageAsset


def test_storage_asset_default_reserve_split():
    asset = StorageAsset(total_mwh=1000, power_mw=100)
    assert asset.soc_floor_frac == 0.20
    assert asset.strategic_reserve_frac == 0.10
    # combined protected floor is 30% of total; 70% usable in regular operations
    assert asset.min_soc_mwh == pytest.approx(300.0)


def test_config_default_reserve_split():
    cfg = Config()
    assert cfg.default_soc_floor_frac == 0.20
    assert cfg.default_strategic_reserve_frac == 0.10


def test_scenario_default_reserve_split():
    scenario = ScenarioCreate(
        storage_total_mwh=20000,
        storage_start_mwh=20000,
        power_output_mw=2000,
        date_start=date(2026, 1, 10),
        date_end=date(2026, 1, 12),
    )
    assert scenario.soc_floor_frac == 0.20
    assert scenario.strategic_reserve_frac == 0.10
