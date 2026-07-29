"""Tests for the Phase 1 CLI-support additions to Config: the stress-detection and
dispatch-weight defaults the simulator CLI reads at parser-build time. These pin the
defaults and their validation, plus a drift guard against the API's own defaults
(the same three-surface pattern as tests/test_reserve_defaults.py).
"""

import json
from dataclasses import asdict

import pytest

from owr.api.schemas import ScenarioCreate
from owr.config import Config
from owr.models import WrapConvention


def test_new_fields_have_documented_defaults():
    cfg = Config()
    assert cfg.default_severity_percentile == 0.90
    assert cfg.default_min_stress_window_days == 2
    assert cfg.default_peak_weight == 0.5
    assert cfg.default_smooth_weight == 0.5


def test_default_severity_percentile_must_be_in_range():
    with pytest.raises(ValueError):
        Config(default_severity_percentile=-0.1)
    with pytest.raises(ValueError):
        Config(default_severity_percentile=1.1)


def test_default_min_stress_window_days_must_be_positive():
    with pytest.raises(ValueError):
        Config(default_min_stress_window_days=0)


def test_default_peak_and_smooth_weights_must_be_non_negative():
    with pytest.raises(ValueError):
        Config(default_peak_weight=-0.1)
    with pytest.raises(ValueError):
        Config(default_smooth_weight=-0.1)


def test_default_peak_and_smooth_weights_sum_must_be_positive():
    with pytest.raises(ValueError):
        Config(default_peak_weight=0.0, default_smooth_weight=0.0)


def _scenario_defaults() -> ScenarioCreate:
    from datetime import date

    return ScenarioCreate(
        storage_total_mwh=20000,
        storage_start_mwh=20000,
        power_output_mw=2000,
        date_start=date(2026, 1, 10),
        date_end=date(2026, 1, 12),
    )


def test_config_defaults_match_scenario_create_defaults():
    """Drift guard: Config()'s new fields must equal the corresponding defaults
    already shipping in api/schemas.ScenarioCreate, so the CLI's parser-build-time
    defaults and the API's request-validation defaults never silently diverge."""
    cfg = Config()
    scenario = _scenario_defaults()
    assert cfg.default_severity_percentile == scenario.severity_percentile
    assert cfg.default_min_stress_window_days == scenario.min_stress_window_days
    assert cfg.default_peak_weight == scenario.peak_weight
    assert cfg.default_smooth_weight == scenario.smooth_weight


def test_default_severity_percentile_is_0_90():
    """Pins the 2026-07-28 decision (HANDOFF.md decision 2): stress-event
    identification is settled at daily total demand >= the historical 90th
    percentile. Checked on both surfaces so the two cannot silently drift back
    apart (same three-surface pattern as tests/test_reserve_defaults.py)."""
    assert Config().default_severity_percentile == 0.90
    assert _scenario_defaults().severity_percentile == 0.90


# --------------------------------------------------------------------------- #
# Peak-window config
# --------------------------------------------------------------------------- #


def test_peak_window_defaults():
    cfg = Config()
    assert cfg.default_peak_window_hours == 3
    assert cfg.default_peak_window_wrap == WrapConvention.WRAP_TO_NEXT_DAY


@pytest.mark.parametrize("hours", [0, 25])
def test_default_peak_window_hours_must_be_in_range(hours):
    with pytest.raises(ValueError):
        Config(default_peak_window_hours=hours)


def test_config_json_serializes_wrap_convention():
    """Guard against R2: 'config': asdict(cfg) followed by json.dumps in cli.py
    would raise TypeError if WrapConvention were a plain Enum instead of StrEnum."""
    payload = json.dumps(asdict(Config()))
    round_tripped = json.loads(payload)
    assert round_tripped["default_peak_window_wrap"] == "wrap_to_next_day"
