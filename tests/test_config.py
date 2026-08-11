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
from owr.models import PercentileRounding, PowerRule, WrapConvention


def test_new_fields_have_documented_defaults():
    cfg = Config()
    assert cfg.default_severity_percentile == 0.90
    assert cfg.default_min_stress_window_days == 2
    assert cfg.default_peak_weight == 0.5
    assert cfg.default_smooth_weight == 0.5


def test_config_has_no_energy_budget_fraction():
    assert "energy_budget_fraction" not in asdict(Config())


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


def test_default_efficiency_is_the_team_decision():
    """Week 4B change 10: 0.85 * 0.85 = 0.7225, Report B's 0.85 read as a
    per-leg figure and squared to the round-trip figure Config.default_efficiency
    takes. See config.py's default_efficiency docstring entry."""
    assert Config().default_efficiency == pytest.approx(0.7225)


def test_config_and_api_efficiency_defaults_diverge_on_purpose():
    """Unlike test_config_defaults_match_scenario_create_defaults above, this pair
    is meant to diverge: Config.default_efficiency moved to 0.7225 (Week 4B change
    10) while StorageAsset.efficiency and ScenarioCreate.efficiency stay 1.0, per
    the task scope named in config.py's default_efficiency entry."""
    cfg = Config()
    scenario = _scenario_defaults()
    assert cfg.default_efficiency != scenario.efficiency
    assert scenario.efficiency == 1.0


def test_default_severity_percentile_is_0_90():
    """Pins the 2026-07-28 decision (HANDOFF.md decision 2): stress-event
    identification is settled at daily total demand >= the historical 90th
    percentile. Doc-sourced 2026-08-05 by the Architecture export, Component 3.
    Checked on both surfaces so the two cannot silently drift back apart (same
    three-surface pattern as tests/test_reserve_defaults.py)."""
    assert Config().default_severity_percentile == 0.90
    assert _scenario_defaults().severity_percentile == 0.90


# --------------------------------------------------------------------------- #
# Peak-window config
# --------------------------------------------------------------------------- #


def test_peak_window_defaults():
    cfg = Config()
    assert cfg.default_peak_window_hours == 3
    assert cfg.default_peak_window_wrap == WrapConvention.STOP_AT_MIDNIGHT


@pytest.mark.parametrize("hours", [0, 25])
def test_default_peak_window_hours_must_be_in_range(hours):
    with pytest.raises(ValueError):
        Config(default_peak_window_hours=hours)


def test_config_json_serializes_wrap_convention():
    """Guard against R2: 'config': asdict(cfg) followed by json.dumps in cli.py
    would raise TypeError if WrapConvention were a plain Enum instead of StrEnum."""
    payload = json.dumps(asdict(Config()))
    round_tripped = json.loads(payload)
    assert round_tripped["default_peak_window_wrap"] == "stop_at_midnight"


# --------------------------------------------------------------------------- #
# Ramp hours (event-relative recharge)
# --------------------------------------------------------------------------- #


def test_default_ramp_hours_default():
    cfg = Config()
    assert cfg.default_ramp_hours == 1


@pytest.mark.parametrize("hours", [-1, 25])
def test_default_ramp_hours_must_be_in_range(hours):
    with pytest.raises(ValueError):
        Config(default_ramp_hours=hours)


@pytest.mark.parametrize("hours", [0, 24])
def test_default_ramp_hours_boundary_values_accepted(hours):
    Config(default_ramp_hours=hours)


# --------------------------------------------------------------------------- #
# Phase 5: capital cost constants (parked, unwired)
# --------------------------------------------------------------------------- #


def test_capital_cost_constants_default_to_none():
    cfg = Config()
    assert cfg.est_transmission_cost_per_mile_usd is None
    assert cfg.est_storage_unit_cost_usd is None
    assert cfg.solution_lifetime_years is None


def test_capital_cost_constants_reject_negative_values():
    with pytest.raises(ValueError):
        Config(est_transmission_cost_per_mile_usd=-1.0)
    with pytest.raises(ValueError):
        Config(est_storage_unit_cost_usd=-1.0)
    with pytest.raises(ValueError):
        Config(solution_lifetime_years=-1.0)


def test_capital_cost_constants_still_json_round_trip():
    """Extends test_config_json_serializes_wrap_convention: three new null keys
    join the config block and json.dumps(asdict(Config())) still round-trips."""
    payload = json.dumps(asdict(Config()))
    round_tripped = json.loads(payload)
    assert round_tripped["est_transmission_cost_per_mile_usd"] is None
    assert round_tripped["est_storage_unit_cost_usd"] is None
    assert round_tripped["solution_lifetime_years"] is None


# --------------------------------------------------------------------------- #
# Sweep defaults (docs/archive/plans/PLAN_SCENARIO_SWEEP.md section 4.2)
# --------------------------------------------------------------------------- #


def test_sweep_defaults_match_documented_values():
    cfg = Config()
    assert cfg.default_sweep_sizes_mwh == (
        5000.0, 10000.0, 20000.0, 40000.0, 60000.0, 80000.0, 100000.0,
    )
    assert cfg.default_sweep_power_rule == PowerRule.FIXED


def test_default_sweep_sizes_mwh_rejects_empty_ladder():
    with pytest.raises(ValueError):
        Config(default_sweep_sizes_mwh=())


def test_default_sweep_sizes_mwh_rejects_non_positive_size():
    with pytest.raises(ValueError):
        Config(default_sweep_sizes_mwh=(0.0, 10000.0))
    with pytest.raises(ValueError):
        Config(default_sweep_sizes_mwh=(-5000.0, 10000.0))


def test_default_sweep_sizes_mwh_rejects_non_finite_size():
    with pytest.raises(ValueError):
        Config(default_sweep_sizes_mwh=(5000.0, float("inf")))
    with pytest.raises(ValueError):
        Config(default_sweep_sizes_mwh=(5000.0, float("nan")))


def test_default_sweep_sizes_mwh_must_be_strictly_increasing():
    with pytest.raises(ValueError):
        Config(default_sweep_sizes_mwh=(10000.0, 5000.0))
    with pytest.raises(ValueError):
        Config(default_sweep_sizes_mwh=(5000.0, 5000.0))


def test_sweep_defaults_json_round_trip():
    """Extends the WrapConvention round-trip test: the ladder reads back as a
    list and the rule reads back as its string value."""
    payload = json.dumps(asdict(Config()))
    round_tripped = json.loads(payload)
    assert round_tripped["default_sweep_sizes_mwh"] == [
        5000.0, 10000.0, 20000.0, 40000.0, 60000.0, 80000.0, 100000.0,
    ]
    assert round_tripped["default_sweep_power_rule"] == "fixed"


# --------------------------------------------------------------------------- #
# Week 4B fields (config constants, no wiring): wind multiplier, stress
# percentile bounds, CMDR hourly anchor, zone bands, robustness years.
# --------------------------------------------------------------------------- #


def test_week4b_fields_have_documented_defaults():
    cfg = Config()
    assert cfg.default_wind_generation_multiplier == 1.0
    assert cfg.stress_percentile_floor_percent == 90.0
    assert cfg.stress_percentile_rounding == PercentileRounding.FLOOR
    assert cfg.cmdr_p90_hourly_mwh == 18413.0
    assert cfg.zone_cmdr_acceptable_percent == 20.0
    assert cfg.zone_cmdr_failure_percent == 0.0
    assert cfg.zone_swe_acceptable_percent == 3.0
    assert cfg.zone_swe_failure_percent == 0.5
    assert cfg.zone_fop_acceptable_percent == 5.0
    assert cfg.zone_fop_failure_percent == 2.0
    assert cfg.zone_rcm_acceptable_abs_percent == 5.0
    assert cfg.zone_rcm_failure_abs_percent == 10.0
    assert cfg.robustness_analysis_years == 5


def test_zone_bands_reject_inverted_thresholds():
    with pytest.raises(ValueError):
        Config(zone_cmdr_failure_percent=20.0, zone_cmdr_acceptable_percent=20.0)
    with pytest.raises(ValueError):
        Config(zone_swe_failure_percent=3.0, zone_swe_acceptable_percent=3.0)
    with pytest.raises(ValueError):
        Config(zone_fop_failure_percent=5.0, zone_fop_acceptable_percent=5.0)
    with pytest.raises(ValueError):
        Config(zone_rcm_acceptable_abs_percent=10.0, zone_rcm_failure_abs_percent=5.0)
    with pytest.raises(ValueError):
        Config(zone_rcm_acceptable_abs_percent=0.0, zone_rcm_failure_abs_percent=10.0)


def test_wind_multiplier_rejects_negative():
    with pytest.raises(ValueError):
        Config(default_wind_generation_multiplier=-1.0)


def test_wind_multiplier_rejects_non_finite():
    with pytest.raises(ValueError):
        Config(default_wind_generation_multiplier=float("inf"))
    with pytest.raises(ValueError):
        Config(default_wind_generation_multiplier=float("nan"))


def test_percentile_floor_rejects_out_of_range():
    with pytest.raises(ValueError):
        Config(stress_percentile_floor_percent=-0.1)
    with pytest.raises(ValueError):
        Config(stress_percentile_floor_percent=100.1)


def test_robustness_analysis_years_rejects_non_positive():
    with pytest.raises(ValueError):
        Config(robustness_analysis_years=0)


def test_cmdr_p90_hourly_mwh_rejects_non_positive():
    with pytest.raises(ValueError):
        Config(cmdr_p90_hourly_mwh=0.0)
    with pytest.raises(ValueError):
        Config(cmdr_p90_hourly_mwh=-1.0)


def test_week4b_config_json_round_trip():
    """Extends the earlier round-trip tests: PercentileRounding stays
    serializable and the new scalar fields round-trip unchanged."""
    payload = json.dumps(asdict(Config()))
    round_tripped = json.loads(payload)
    assert round_tripped["stress_percentile_rounding"] == "floor"
    assert round_tripped["default_wind_generation_multiplier"] == 1.0
    assert round_tripped["cmdr_p90_hourly_mwh"] == 18413.0
