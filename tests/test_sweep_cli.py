"""Tests for src/owr/sweep_cli.py (docs/archive/plans/PLAN_SCENARIO_SWEEP.md section 6.3).

Cases 1 to 13 land in phase 2; cases 14 and 15 land in phase 3.
"""

from __future__ import annotations

import io
import json
import sys

import pytest

from owr import sweep_cli
from owr.config import DEFAULT_CONFIG

REAL_CSV = "examples/real_winter_stress_2026.csv"
SYNTHETIC_CSV = "examples/synthetic_winter_stress.csv"


def _run_cli(argv, monkeypatch):
    out = io.StringIO()
    err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    code = sweep_cli.main(argv)
    return code, out.getvalue(), err.getvalue()


def test_help_exits_0():
    parser = sweep_cli.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--help"])
    assert exc.value.code == 0


def test_parser_defaults_equal_default_config():
    parser = sweep_cli.build_parser()
    args = parser.parse_args(["--input", SYNTHETIC_CSV, "--power-mw", "4320"])
    assert args.sizes_mwh == DEFAULT_CONFIG.default_sweep_sizes_mwh
    assert args.power_rule == DEFAULT_CONFIG.default_sweep_power_rule


def test_sizes_mwh_parses_and_sorts():
    parser = sweep_cli.build_parser()
    args = parser.parse_args(
        ["--input", SYNTHETIC_CSV, "--power-mw", "4320", "--sizes-mwh", "20000,10000"]
    )
    assert args.sizes_mwh == (10000.0, 20000.0)


def test_sizes_mwh_rejects_duplicate():
    parser = sweep_cli.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(
            ["--input", SYNTHETIC_CSV, "--power-mw", "4320", "--sizes-mwh", "10000,10000"]
        )
    assert exc.value.code == 2


def test_sizes_mwh_rejects_empty_string():
    parser = sweep_cli.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--input", SYNTHETIC_CSV, "--power-mw", "4320", "--sizes-mwh", ""])
    assert exc.value.code == 2


def test_sizes_mwh_rejects_non_numeric():
    parser = sweep_cli.build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(
            ["--input", SYNTHETIC_CSV, "--power-mw", "4320", "--sizes-mwh", "abc"]
        )
    assert exc.value.code == 2


def test_missing_power_mw_under_fixed_exits_2(monkeypatch):
    code, out, err = _run_cli(["--input", SYNTHETIC_CSV], monkeypatch)
    assert code == 2
    assert out == ""
    assert "power_mw" in err


def test_fixed_duration_power_mw_equals_size_over_duration(monkeypatch):
    code, out, err = _run_cli(
        [
            "--input", SYNTHETIC_CSV,
            "--power-rule", "fixed_duration",
            "--duration-hours", "4",
            "--format", "json",
        ],
        monkeypatch,
    )
    assert code == 0
    report = json.loads(out)
    for p in report["points"]:
        assert p["power_mw"] == pytest.approx(p["storage_mwh"] / 4.0)


def test_format_json_top_level_keys_in_order(monkeypatch):
    code, out, err = _run_cli(
        ["--input", SYNTHETIC_CSV, "--power-mw", "4320", "--format", "json"], monkeypatch
    )
    assert code == 0
    report = json.loads(out)
    assert list(report.keys()) == [
        "code_version", "generated_at", "input", "spec", "dispatch",
        "points", "chart", "open_questions",
    ]
    assert report["chart"] is None


def test_table_output_has_one_row_per_size_and_code_version(monkeypatch):
    code, out, err = _run_cli(["--input", SYNTHETIC_CSV, "--power-mw", "4320"], monkeypatch)
    assert code == 0
    assert f"engine {sweep_cli.code_version()}" in out
    for size in DEFAULT_CONFIG.default_sweep_sizes_mwh:
        assert f"{size:,.0f}" in out


def test_reference_point_real_and_synthetic(monkeypatch):
    # --efficiency 1.0: Week 4B change 10 moved the CLI's own --efficiency
    # default to Config.default_efficiency (0.7225). Pinning 1.0 explicitly here
    # keeps this test documenting the original reference-point arithmetic
    # instead of silently tracking whatever the config default becomes.
    #
    # --wind-multiplier 15 (real) / 25 (synthetic): Week 4B change 7's revised
    # daily_budget takes surplus wind above load as its recharge term, and
    # neither shipped file's wind ever clears its load (R7), which leaves
    # severity_reduction at 0.0 at the identity multiplier (see the companion
    # zero-case assertions right below). These multipliers restore surplus so
    # the pins keep documenting real dispatch, not the no-recharge floor.
    code, out, err = _run_cli(
        [
            "--input", REAL_CSV,
            "--sizes-mwh", "60000",
            "--power-mw", "4320",
            "--efficiency", "1.0",
            "--wind-multiplier", "15",
            "--format", "json",
        ],
        monkeypatch,
    )
    assert code == 0
    report = json.loads(out)
    assert report["points"][0]["severity_reduction"] == pytest.approx(0.012936, abs=1e-6)

    code, out, err = _run_cli(
        [
            "--input", REAL_CSV,
            "--sizes-mwh", "60000",
            "--power-mw", "4320",
            "--efficiency", "1.0",
            "--format", "json",
        ],
        monkeypatch,
    )
    assert code == 0
    report = json.loads(out)
    assert report["points"][0]["severity_reduction"] == pytest.approx(0.0, abs=1e-9)

    code, out, err = _run_cli(
        [
            "--input", SYNTHETIC_CSV,
            "--sizes-mwh", "60000",
            "--power-mw", "4320",
            "--efficiency", "1.0",
            "--wind-multiplier", "25",
            "--format", "json",
        ],
        monkeypatch,
    )
    assert code == 0
    report = json.loads(out)
    assert report["points"][0]["severity_reduction"] == pytest.approx(0.25, abs=1e-9)

    code, out, err = _run_cli(
        [
            "--input", SYNTHETIC_CSV,
            "--sizes-mwh", "60000",
            "--power-mw", "4320",
            "--efficiency", "1.0",
            "--format", "json",
        ],
        monkeypatch,
    )
    assert code == 0
    report = json.loads(out)
    assert report["points"][0]["severity_reduction"] == pytest.approx(0.0, abs=1e-9)


def test_wind_multiplier_flag_changes_the_sweep(monkeypatch):
    code, out, err = _run_cli(
        [
            "--input", REAL_CSV,
            "--sizes-mwh", "60000",
            "--power-mw", "4320",
            "--format", "json",
        ],
        monkeypatch,
    )
    assert code == 0
    default_report = json.loads(out)
    assert default_report["input"]["wind_multiplier"] == 1.0

    code, out, err = _run_cli(
        [
            "--input", REAL_CSV,
            "--sizes-mwh", "60000",
            "--power-mw", "4320",
            "--wind-multiplier", "10.0",
            "--format", "json",
        ],
        monkeypatch,
    )
    assert code == 0
    scaled_report = json.loads(out)
    assert scaled_report["input"]["wind_multiplier"] == 10.0


def test_data_out_writes_bannered_csv(monkeypatch, tmp_path):
    out_path = tmp_path / "sweep.csv"
    code, out, err = _run_cli(
        [
            "--input", SYNTHETIC_CSV,
            "--power-mw", "4320",
            "--sizes-mwh", "10000,20000",
            "--data-out", str(out_path),
        ],
        monkeypatch,
    )
    assert code == 0
    lines = out_path.read_text().splitlines()
    banner = [line for line in lines if line.startswith("#")]
    assert len(banner) > 0
    non_banner = [line for line in lines if not line.startswith("#")]
    header = non_banner[0].split(",")
    from owr.sweep import SWEEP_FRAME_COLUMNS

    assert header == list(SWEEP_FRAME_COLUMNS)
    data_rows = [line for line in non_banner[1:] if line.strip()]
    assert len(data_rows) == 2


def test_reader_warnings_reach_stderr_not_stdout(monkeypatch):
    code, out, err = _run_cli(
        ["--input", REAL_CSV, "--power-mw", "4320", "--sizes-mwh", "10000", "--format", "json"],
        monkeypatch,
    )
    assert code == 0
    assert "wind_forecast_frac" in err
    # stdout must stay parseable JSON, uncontaminated by the warning
    json.loads(out)


def test_chart_writes_file_and_names_path(monkeypatch, tmp_path):
    pytest.importorskip("matplotlib")
    chart_path = tmp_path / "chart.png"
    code, out, err = _run_cli(
        [
            "--input", SYNTHETIC_CSV,
            "--power-mw", "4320",
            "--sizes-mwh", "10000,20000",
            "--chart", str(chart_path),
        ],
        monkeypatch,
    )
    assert code == 0
    assert chart_path.exists()
    assert str(chart_path) in out


def test_chart_dependency_error_exits_2_writes_nothing_to_stdout(monkeypatch):
    """Pins the step order in section 4.5: the chart renders before anything
    reaches stdout, so a ChartDependencyError produces no report at all."""
    from owr.sweep_chart import ChartDependencyError

    def _raise(*args, **kwargs):
        raise ChartDependencyError("chart output needs matplotlib, an optional dependency.")

    monkeypatch.setattr(sweep_cli, "render_sweep_chart", _raise)

    code, out, err = _run_cli(
        [
            "--input", SYNTHETIC_CSV,
            "--power-mw", "4320",
            "--sizes-mwh", "10000",
            "--chart", "/tmp/unused_sweep_chart.png",
        ],
        monkeypatch,
    )
    assert code == 2
    assert out == ""
    assert "matplotlib" in err
