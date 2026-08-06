"""Tests for src/owr/sweep.py (docs/PLAN_SCENARIO_SWEEP.md section 6.1)."""

from __future__ import annotations

import inspect
from datetime import date, timedelta

import pandas.testing
import pytest

from owr.config import Config
from owr.models import DayProfile, PowerRule, StorageAsset
from owr.simulator import simulate
from owr.sweep import SWEEP_FRAME_COLUMNS, SweepSpec, run_sweep


def _spec(**overrides) -> SweepSpec:
    fields = {
        "sizes_mwh": (5000.0, 10000.0, 20000.0),
        "power_rule": PowerRule.FIXED,
        "efficiency": 1.0,
        "soc_floor_frac": 0.20,
        "strategic_reserve_frac": 0.10,
        "power_mw": 2000.0,
    }
    fields.update(overrides)
    return SweepSpec(**fields)


def _stress_day(i: int) -> DayProfile:
    load = [8000.0] * 24
    load[17] = 10000.0
    load[18] = 12000.0
    load[19] = 10000.0
    wind = [500.0] * 24
    return DayProfile(
        date=date(2026, 1, 10) + timedelta(days=i),
        hourly_load_mw=tuple(load),
        hourly_wind_mw=tuple(wind),
        demand_percentile=0.95,
        wind_forecast_frac=0.1,
    )


def _span(n: int = 3) -> list[DayProfile]:
    return [_stress_day(i) for i in range(n)]


# --------------------------------------------------------------------------- #
# SweepSpec validation
# --------------------------------------------------------------------------- #


def test_spec_rejects_empty_sizes():
    with pytest.raises(ValueError):
        _spec(sizes_mwh=())


def test_spec_rejects_size_at_or_below_zero():
    with pytest.raises(ValueError):
        _spec(sizes_mwh=(0.0, 5000.0))
    with pytest.raises(ValueError):
        _spec(sizes_mwh=(-1.0, 5000.0))


def test_spec_rejects_non_finite_size():
    with pytest.raises(ValueError):
        _spec(sizes_mwh=(5000.0, float("inf")))
    with pytest.raises(ValueError):
        _spec(sizes_mwh=(5000.0, float("nan")))


def test_spec_rejects_sizes_not_strictly_increasing():
    with pytest.raises(ValueError):
        _spec(sizes_mwh=(10000.0, 5000.0))
    with pytest.raises(ValueError):
        _spec(sizes_mwh=(5000.0, 5000.0))


def test_fixed_without_power_mw_raises():
    with pytest.raises(ValueError):
        _spec(power_rule=PowerRule.FIXED, power_mw=None)


def test_fixed_with_duration_hours_raises():
    with pytest.raises(ValueError):
        _spec(power_rule=PowerRule.FIXED, power_mw=2000.0, duration_hours=4.0)


def test_fixed_duration_without_duration_hours_raises():
    with pytest.raises(ValueError):
        _spec(power_rule=PowerRule.FIXED_DURATION, power_mw=None, duration_hours=None)


def test_fixed_duration_with_power_mw_raises():
    with pytest.raises(ValueError):
        _spec(
            power_rule=PowerRule.FIXED_DURATION, power_mw=2000.0, duration_hours=4.0
        )


# --------------------------------------------------------------------------- #
# power_for / duration_for / asset_for
# --------------------------------------------------------------------------- #


def test_power_for_fixed_is_constant_across_sizes():
    spec = _spec(power_rule=PowerRule.FIXED, power_mw=4320.0)
    assert spec.power_for(spec.sizes_mwh[0]) == 4320.0
    assert spec.power_for(spec.sizes_mwh[-1]) == 4320.0


def test_power_for_fixed_duration_is_size_over_duration():
    spec = _spec(power_rule=PowerRule.FIXED_DURATION, power_mw=None, duration_hours=4.0)
    for size in spec.sizes_mwh:
        assert spec.power_for(size) == pytest.approx(size / 4.0)


def test_duration_for_fixed_rises_with_size():
    spec = _spec(power_rule=PowerRule.FIXED, power_mw=2000.0)
    durations = [spec.duration_for(s) for s in spec.sizes_mwh]
    assert durations == sorted(durations)
    assert durations[0] < durations[-1]
    assert spec.duration_for(spec.sizes_mwh[0]) == pytest.approx(
        spec.sizes_mwh[0] / 2000.0
    )


def test_asset_for_carries_fractions_and_scales_min_soc():
    spec = _spec(
        efficiency=0.85, soc_floor_frac=0.20, strategic_reserve_frac=0.10, power_mw=2000.0
    )
    small = spec.asset_for(spec.sizes_mwh[0])
    large = spec.asset_for(spec.sizes_mwh[-1])
    assert small.efficiency == 0.85
    assert small.soc_floor_frac == 0.20
    assert small.strategic_reserve_frac == 0.10
    assert large.min_soc_mwh > small.min_soc_mwh
    assert small.min_soc_mwh == pytest.approx(0.30 * small.total_mwh)


# --------------------------------------------------------------------------- #
# run_sweep
# --------------------------------------------------------------------------- #


def test_run_sweep_returns_one_point_per_size_in_ladder_order():
    spec = _spec()
    result = run_sweep(spec, span_days=_span())
    assert [p.storage_mwh for p in result.points] == list(spec.sizes_mwh)


def test_run_sweep_raises_on_empty_span_days():
    with pytest.raises(ValueError):
        run_sweep(_spec(), span_days=[])


def test_run_sweep_matches_direct_simulate_call_anti_fork_guard():
    """Build one StorageAsset by hand, call simulate() directly, and assert a
    one-size run_sweep returns the same core outputs. Exact float equality: any
    divergence means the sweep forked the engine call path."""
    span = _span()
    config = Config()
    asset = StorageAsset(
        total_mwh=20000.0,
        power_mw=2000.0,
        efficiency=1.0,
        soc_floor_frac=0.20,
        strategic_reserve_frac=0.10,
    )
    direct = simulate(
        asset,
        span,
        starting_soc=asset.total_mwh,
        config=config,
        peak_weight=config.default_peak_weight,
        smooth_weight=config.default_smooth_weight,
    )
    direct_discharged = sum(h.discharge for d in direct.daily for h in d.hourly)

    spec = _spec(sizes_mwh=(20000.0,), power_mw=2000.0)
    result = run_sweep(spec, span_days=span, config=config)
    point = result.points[0]

    assert point.severity_reduction == pytest.approx(
        (direct.baseline_peak_mw - direct.reserve_peak_mw) / direct.baseline_peak_mw
    )
    assert point.baseline_peak_mw == direct.baseline_peak_mw
    assert point.reserve_peak_mw == direct.reserve_peak_mw
    assert point.energy_discharged_mwh == direct_discharged
    assert point.final_soc_mwh == direct.final_soc


def test_run_sweep_is_deterministic():
    spec = _spec()
    span = _span()
    a = run_sweep(spec, span_days=span).frame()
    b = run_sweep(spec, span_days=span).frame()
    pandas.testing.assert_frame_equal(a, b)


def test_frame_column_order_and_dtypes():
    result = run_sweep(_spec(), span_days=_span())
    frame = result.frame()
    assert list(frame.columns) == list(SWEEP_FRAME_COLUMNS)
    for col in frame.columns:
        assert frame[col].dtype == "float64"


def test_run_sweep_passes_config_weights_through(monkeypatch):
    """Config pass-through spy. Measured at 219a55a: the weight extremes 1.0/0.0
    and 0.0/1.0 return the same reserve_peak_mw and discharged energy on
    examples/synthetic_winter_stress.csv, so this asserts the call arguments
    rather than an output difference."""
    import owr.sweep as sweep_mod

    real_simulate = sweep_mod.simulate
    calls: list[dict] = []

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real_simulate(*args, **kwargs)

    monkeypatch.setattr(sweep_mod, "simulate", spy)

    config = Config(default_peak_weight=0.9, default_smooth_weight=0.1)
    spec = _spec()
    run_sweep(spec, span_days=_span(), config=config)

    assert len(calls) == len(spec.sizes_mwh)
    for call in calls:
        assert call["peak_weight"] == 0.9
        assert call["smooth_weight"] == 0.1


def test_purity_guard_no_matplotlib_or_cli_in_engine_core():
    """Engine-core modules must not *import* matplotlib,
    sweep_chart or owr.cli. Listed explicitly so a new core module has to be
    added on purpose. Checked against the parsed import statements, not a raw
    substring search: owr/version.py's docstring names ``owr.cli`` in prose
    without importing it."""
    import ast

    import owr.budget
    import owr.config
    import owr.dispatch
    import owr.initial_soc
    import owr.metrics
    import owr.models
    import owr.peak_window
    import owr.scenario_input
    import owr.simulator
    import owr.soc_engine
    import owr.storage_physics
    import owr.stress_finder
    import owr.sweep
    import owr.version

    core_modules = [
        owr.models,
        owr.config,
        owr.stress_finder,
        owr.initial_soc,
        owr.budget,
        owr.dispatch,
        owr.soc_engine,
        owr.metrics,
        owr.simulator,
        owr.peak_window,
        owr.storage_physics,
        owr.scenario_input,
        owr.version,
        owr.sweep,
    ]
    forbidden = ("matplotlib", "sweep_chart", "owr.cli")
    for module in core_modules:
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                names = [module_name] + [f"{module_name}.{a.name}" for a in node.names]
            else:
                continue
            for name in names:
                for bad in forbidden:
                    assert bad not in name, f"{module.__name__} imports {name!r}"


def test_run_sweep_raises_when_baseline_peak_is_zero():
    """Documented D6 divergence: metrics.severity_reduction raises ValueError
    when baseline_peak_mw <= 0, where cli._severity_reduction returns 0.0."""
    zero_load_day = DayProfile(
        date=date(2026, 1, 10),
        hourly_load_mw=(0.0,) * 24,
        hourly_wind_mw=(0.0,) * 24,
        demand_percentile=0.5,
        wind_forecast_frac=0.0,
    )
    with pytest.raises(ValueError):
        run_sweep(_spec(sizes_mwh=(5000.0,)), span_days=[zero_load_day])
