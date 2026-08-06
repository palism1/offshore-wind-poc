"""Tests for the simulator CLI (src/owr/cli.py) and its supporting modules."""

from __future__ import annotations

import argparse
import io
import json
import re
from datetime import date, timedelta

import pytest

from owr import cli
from owr.config import DEFAULT_CONFIG
from owr.initial_soc import charge_from_wind
from owr.models import StorageAsset
from owr.scenario_input import read_day_profiles
from owr.simulator import simulate
from owr.stress_finder import find_stress_windows
from owr.version import code_version

EXAMPLE = "examples/synthetic_winter_stress.csv"


def test_code_version_returns_a_non_empty_string():
    assert isinstance(code_version(), str)
    assert code_version() != ""


# --------------------------------------------------------------------------- #
# Wiring and defaults
# --------------------------------------------------------------------------- #


def test_build_parser_defaults_match_default_config():
    args = cli.build_parser().parse_args(["--input", EXAMPLE])
    cfg = DEFAULT_CONFIG
    assert args.efficiency == cfg.default_efficiency
    assert args.soc_floor_frac == cfg.default_soc_floor_frac
    assert args.strategic_reserve_frac == cfg.default_strategic_reserve_frac
    assert args.severity_percentile == cfg.default_severity_percentile
    assert args.min_stress_window_days == cfg.default_min_stress_window_days
    assert args.peak_weight == cfg.default_peak_weight
    assert args.smooth_weight == cfg.default_smooth_weight
    assert args.energy_budget_fraction == cfg.energy_budget_fraction
    assert args.priority_demand_weight == cfg.priority_demand_weight
    assert args.priority_wind_weight == cfg.priority_wind_weight


def test_cycles_per_year_default_is_the_module_constant():
    args = cli.build_parser().parse_args(["--input", EXAMPLE])
    assert args.cycles_per_year == cli.DEFAULT_CYCLES_PER_YEAR


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(["--help"])
    assert exc.value.code == 0


def test_missing_input_exits_two():
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args([])
    assert exc.value.code == 2


def test_main_is_importable_at_project_scripts_path():
    from owr.cli import main as entry

    assert callable(entry)


# --------------------------------------------------------------------------- #
# Shipped example
# --------------------------------------------------------------------------- #


def test_example_parses_and_main_returns_zero():
    code = cli.main(["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "2000"])
    assert code == 0


def test_example_pins_one_three_day_window():
    with open(EXAMPLE, encoding="utf-8") as f:
        day_set = read_day_profiles(f, origin=EXAMPLE)
    windows = find_stress_windows(
        day_set.days,
        DEFAULT_CONFIG.default_severity_percentile,
        DEFAULT_CONFIG.default_min_stress_window_days,
    )
    assert len(windows) == 1
    assert windows[0].days == 3


# --------------------------------------------------------------------------- #
# Run behavior
# --------------------------------------------------------------------------- #


def test_table_output_contains_summary_labels_and_open_markers(capsys):
    code = cli.main(["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "2000"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Summary" in out
    assert "baseline peak" in out
    assert "reserve peak" in out
    assert "[OPEN: round_trip_efficiency]" in out
    assert "[OPEN: reserve_usage_rules]" in out
    assert "[OPEN: stress_event_definition]" in out
    assert "[OPEN: cycles_per_year]" in out


def test_stress_event_note_names_the_source():
    report = _report([])
    entries = {q["id"]: q for q in report["open_questions"]}
    note = entries["stress_event_definition"]["note"]
    assert "90th historical daily load percentile" in note
    assert "minimum_window" in note
    assert "12+ hours above threshold within a day" not in note


def test_list_windows_text_names_the_source(capsys):
    code = cli.main(["--input", EXAMPLE, "--list-windows"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Architecture 2026-08-05 Component 3" in out
    assert "[OPEN: stress_event_definition]" in out


def test_table_stress_block_names_the_source(capsys):
    code = cli.main(["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "2000"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Architecture 2026-08-05 Component 3" in out


def test_table_states_wind_mw_present_when_the_file_carries_it(capsys):
    code = cli.main(["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "2000"])
    assert code == 0
    out = capsys.readouterr().out
    assert "wind_mw              present" in out


def test_table_states_wind_mw_absent_when_the_file_lacks_it(tmp_path, capsys):
    no_wind = tmp_path / "no_wind.csv"
    lines = ["date,hour,load_mw\n"]
    for hour in range(24):
        lines.append(f"2026-01-01,{hour},1000.0\n")
    no_wind.write_text("".join(lines))

    code = cli.main(["--input", str(no_wind), "--storage-mwh", "20000", "--power-mw", "2000"])
    assert code == 0
    out = capsys.readouterr().out
    assert "wind_mw              absent" in out


def test_daily_table_columns_align_across_magnitudes():
    # Column starts must match the header regardless of how many digits a
    # value has, proving the table is built from one shared column layout
    # rather than hand-counted spaces tuned to one example's magnitudes.
    report = _report([])
    template = report["daily"][0]
    magnitudes = [1, 12, 999, 12_000, 4_500_000]
    report["daily"] = [
        {
            **template,
            "date": f"2026-01-{(i % 28) + 1:02d}",
            "priority": 0.001 * (10**i if i < 4 else 1),
            "budget": float(m),
            "usable_energy": float(m) * 3,
            "discharged_mwh": float(m) / 2 if m > 1 else 0.0,
            "recharge_sufficiency_ratio": None if i % 2 == 0 else float(m) / 1000,
            "gross_peak_mw": float(m) * 1.5,
            "net_peak_mw": float(m),
        }
        for i, m in enumerate(magnitudes)
    ]

    buf = io.StringIO()
    cli._render_table(report, argparse.Namespace(name=None), buf)
    text = buf.getvalue()

    lines = text.splitlines()
    header_line = next(line for line in lines if line.startswith("  date"))

    daily_start = lines.index("Daily results")
    header_index = lines.index(header_line, daily_start)
    row_lines = []
    for line in lines[header_index + 1 :]:
        if not line.strip():
            break
        row_lines.append(line)
    assert len(row_lines) == len(magnitudes)

    # Numeric columns are right-aligned, so the invariant is the right edge: each
    # header ends where its values end, whatever the magnitude of those values.
    numeric_headers = [
        "priority",
        "budget MWh",
        "usable MWh (eod)",
        "discharged MWh",
        "recharge ratio",
        "gross peak MW",
        "net peak MW",
    ]
    header_edges = [header_line.index(name) + len(name) for name in numeric_headers]

    for row in row_lines:
        cells = list(re.finditer(r"\S+", row))
        assert len(cells) == len(numeric_headers) + 1, row
        assert cells[0].start() == 2, row
        assert [c.end() for c in cells[1:]] == header_edges, row


def test_json_output_is_clean_stdout_with_all_top_level_keys(capsys):
    code = cli.main(
        ["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "2000", "--format", "json"]
    )
    assert code == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)  # raises if stdout carries anything else
    expected_keys = [
        "code_version",
        "generated_at",
        "input",
        "asset",
        "config",
        "dispatch",
        "reporting",
        "stress_windows",
        "simulated",
        "daily",
        "summary",
        "open_questions",
    ]
    assert list(report.keys()) == expected_keys


def _report(extra_args: list[str]) -> dict:
    import contextlib

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(
            ["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "2000", "--format", "json"]
            + extra_args
        )
    assert code == 0
    return json.loads(buf.getvalue())


def test_json_summary_matches_direct_simulate_call():
    with open(EXAMPLE, encoding="utf-8") as f:
        day_set = read_day_profiles(f, origin=EXAMPLE)
    asset = StorageAsset(total_mwh=20000.0, power_mw=2000.0)
    result = simulate(asset, day_set.days, starting_soc=asset.total_mwh)

    report = _report([])
    summary = report["summary"]
    assert summary["baseline_peak_mw"] == pytest.approx(result.baseline_peak_mw)
    assert summary["reserve_peak_mw"] == pytest.approx(result.reserve_peak_mw)
    assert summary["final_soc"] == pytest.approx(result.final_soc)


def test_equivalent_full_cycles_is_energy_discharged_over_rated_capacity():
    """Pins the Phase 3 formula change: EFC is discharged / rated capacity, with
    no division by efficiency. Coincides with the old (energy drawn / rated
    capacity) formula at efficiency=1.0, so a second run at --efficiency 0.7 is
    what actually proves the /efficiency term is gone (risk R1)."""
    report = _report([])
    summary = report["summary"]
    assert summary["equivalent_full_cycles"] == pytest.approx(
        summary["energy_discharged_mwh"] / report["asset"]["total_mwh"]
    )


def test_equivalent_full_cycles_at_nondefault_efficiency():
    report = _report(["--efficiency", "0.7"])
    summary = report["summary"]
    assert summary["equivalent_full_cycles"] == pytest.approx(
        summary["energy_discharged_mwh"] / report["asset"]["total_mwh"]
    )


def test_no_hourly_soc_below_min_soc():
    report = _report([])
    min_soc = report["asset"]["min_soc_mwh"]
    for day in report["daily"]:
        for hour in day["hourly"]:
            assert hour["soc"] >= min_soc - 1e-6


def test_reserve_peak_below_baseline_and_positive_severity_reduction():
    report = _report([])
    summary = report["summary"]
    assert summary["reserve_peak_mw"] < summary["baseline_peak_mw"]
    assert summary["severity_reduction"] > 0


def test_window_1_simulates_only_the_window():
    report = _report(["--window", "1"])
    window = report["stress_windows"][0]
    assert len(report["daily"]) == window["days"]


def test_lead_days_correctness_by_equality_against_charge_from_wind():
    report = _report(
        ["--start-soc-mwh", "20000", "--window", "1", "--lead-days", "3", "--storage-mwh", "200000"]
    )
    assert report["simulated"]["lead_days_used"] == 3

    with open(EXAMPLE, encoding="utf-8") as f:
        days = read_day_profiles(f, origin=EXAMPLE).days
    cfg = DEFAULT_CONFIG
    start = find_stress_windows(
        days, cfg.default_severity_percentile, cfg.default_min_stress_window_days
    )[0].start
    expected_lead = [d for d in days if start - timedelta(days=3) <= d.date < start]
    assert [d.date for d in expected_lead] == [start - timedelta(days=k) for k in (3, 2, 1)]

    asset = StorageAsset(total_mwh=200000.0, power_mw=2000.0)
    expected_soc = charge_from_wind(20000.0, expected_lead, asset)
    assert report["simulated"]["soc_at_window_start_mwh"] == pytest.approx(expected_soc)
    assert report["simulated"]["soc_at_window_start_mwh"] < asset.total_mwh


def test_lead_days_strictly_increase_charge_in_order():
    def soc_for(n: int) -> float:
        report = _report(
            [
                "--start-soc-mwh",
                "20000",
                "--window",
                "1",
                "--lead-days",
                str(n),
                "--storage-mwh",
                "200000",
            ]
        )
        return report["simulated"]["soc_at_window_start_mwh"]

    soc1, soc2, soc3 = soc_for(1), soc_for(2), soc_for(3)
    assert soc1 < soc2 < soc3


def test_lead_days_zero_equals_starting_soc():
    report = _report(["--window", "1", "--lead-days", "0"])
    assert report["simulated"]["soc_at_window_start_mwh"] == pytest.approx(
        report["simulated"]["starting_soc_mwh"]
    )
    assert report["simulated"]["lead_days_used"] == 0


def test_lead_days_shortfall_clamps_and_warns(capsys):
    code = cli.main(
        [
            "--input",
            EXAMPLE,
            "--storage-mwh",
            "20000",
            "--power-mw",
            "2000",
            "--window",
            "1",
            "--lead-days",
            "99",
        ]
    )
    assert code == 0
    err = capsys.readouterr().err
    assert "only 3 lead day(s)" in err


def test_window_all_lead_days_positive_path():
    report = _report(
        [
            "--window",
            "all",
            "--lead-days",
            "2",
            "--storage-mwh",
            "200000",
            "--start-soc-mwh",
            "20000",
        ]
    )
    assert report["simulated"]["window"] == "all"

    with open(EXAMPLE, encoding="utf-8") as f:
        days = read_day_profiles(f, origin=EXAMPLE).days
    assert report["simulated"]["date_start"] == days[2].date.isoformat()
    assert report["simulated"]["date_end"] == days[5].date.isoformat()
    assert len(report["daily"]) == 4
    assert report["simulated"]["lead_days_used"] == 2

    expected_lead = [d for d in days if d.date < days[2].date]
    expected_dates = [days[0].date.isoformat(), days[1].date.isoformat()]
    assert [d.date.isoformat() for d in expected_lead] == expected_dates

    asset = StorageAsset(total_mwh=200000.0, power_mw=2000.0)
    expected_soc = charge_from_wind(20000.0, expected_lead, asset)
    assert report["simulated"]["soc_at_window_start_mwh"] == pytest.approx(expected_soc)
    assert report["simulated"]["soc_at_window_start_mwh"] < asset.total_mwh


def test_window_all_lead_days_zero_spans_whole_file():
    report = _report(["--window", "all", "--lead-days", "0"])
    assert report["simulated"]["soc_at_window_start_mwh"] == pytest.approx(
        report["simulated"]["starting_soc_mwh"]
    )
    assert len(report["daily"]) == 6


def test_available_capacity_mw_sets_min_capacity_margin():
    with_cap = _report(["--available-capacity-mw", "13000"])
    assert isinstance(with_cap["summary"]["min_capacity_margin_mw"], int | float)

    without_cap = _report([])
    assert without_cap["summary"]["min_capacity_margin_mw"] is None


def test_cycles_per_year_sets_window_share():
    with_cpy = _report(["--cycles-per-year", "200"])
    assert isinstance(with_cpy["summary"]["window_share_of_annual_cycles"], int | float)
    assert with_cpy["reporting"]["cycles_per_year"] == 200

    without_cpy = _report([])
    assert without_cpy["summary"]["window_share_of_annual_cycles"] is None
    assert without_cpy["reporting"]["cycles_per_year"] is None


def test_list_windows_returns_zero_without_asset_flags(capsys):
    code = cli.main(["--input", EXAMPLE, "--list-windows"])
    assert code == 0
    out = capsys.readouterr().out
    assert "2026-01-09" in out


def test_list_windows_json_carries_the_component3_fields(capsys):
    code = cli.main(["--input", EXAMPLE, "--list-windows", "--format", "json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    w = payload["stress_windows"][0]
    expected_keys = {
        "start",
        "end",
        "days",
        "first_hour_index",
        "last_hour_index",
        "peak_hourly_load_mw",
        "threshold_mwh",
        "severity_percentile",
    }
    assert expected_keys <= w.keys()
    assert w["first_hour_index"] == 0
    assert w["last_hour_index"] == 24 * w["days"] - 1
    assert w["severity_percentile"] == DEFAULT_CONFIG.default_severity_percentile
    assert w["threshold_mwh"] > 0


def test_peak_hourly_load_matches_the_file(capsys):
    with open(EXAMPLE, encoding="utf-8") as f:
        day_set = read_day_profiles(f, origin=EXAMPLE)
    by_date = {d.date: d for d in day_set.days}

    code = cli.main(["--input", EXAMPLE, "--list-windows", "--format", "json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    w = payload["stress_windows"][0]

    start = date.fromisoformat(w["start"])
    end = date.fromisoformat(w["end"])
    expected_peak = 0.0
    day = start
    while day <= end:
        expected_peak = max(expected_peak, max(by_date[day].hourly_load_mw))
        day += timedelta(days=1)

    assert w["peak_hourly_load_mw"] == expected_peak


def test_report_and_list_windows_agree_on_window_fields(capsys):
    report_window = _report([])["stress_windows"][0]

    code = cli.main(["--input", EXAMPLE, "--list-windows", "--format", "json"])
    assert code == 0
    list_window = json.loads(capsys.readouterr().out)["stress_windows"][0]

    assert report_window == list_window


def test_stress_window_output_fields_open_question_is_reported(capsys):
    report = _report([])
    ids = [q["id"] for q in report["open_questions"]]
    assert "stress_window_output_fields" in ids

    code = cli.main(["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "2000"])
    assert code == 0
    out = capsys.readouterr().out
    assert "[OPEN: stress_window_output_fields]" in out


def test_render_table_prints_dash_for_a_missing_peak():
    report = _report([])
    report["stress_windows"][0]["peak_hourly_load_mw"] = None
    buf = io.StringIO()
    cli._render_table(report, argparse.Namespace(name=None), buf)
    assert "peak -" in buf.getvalue()


def test_warnings_on_stderr_results_on_stdout(capsys):
    cli.main(["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "2000"])
    captured = capsys.readouterr()
    assert "warning:" in captured.err
    assert "warning:" not in captured.out


# --------------------------------------------------------------------------- #
# Exit codes
# --------------------------------------------------------------------------- #


def test_missing_storage_flags_without_list_windows_exits_two(capsys):
    code = cli.main(["--input", EXAMPLE])
    assert code == 2
    assert "required" in capsys.readouterr().err


def test_window_out_of_range_exits_two():
    code = cli.main(
        ["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "2000", "--window", "99"]
    )
    assert code == 2


def test_zero_efficiency_exits_two():
    code = cli.main(
        ["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "2000", "--efficiency", "0"]
    )
    assert code == 2


def test_mismatched_priority_weights_exits_two():
    code = cli.main(
        [
            "--input",
            EXAMPLE,
            "--storage-mwh",
            "20000",
            "--power-mw",
            "2000",
            "--priority-demand-weight",
            "0.6",
            "--priority-wind-weight",
            "0.3",
        ]
    )
    assert code == 2


def test_start_soc_above_storage_mwh_exits_two():
    code = cli.main(
        [
            "--input",
            EXAMPLE,
            "--storage-mwh",
            "20000",
            "--power-mw",
            "2000",
            "--start-soc-mwh",
            "30000",
        ]
    )
    assert code == 2


def test_lead_days_at_or_above_day_count_with_window_all_exits_two():
    code = cli.main(
        [
            "--input",
            EXAMPLE,
            "--storage-mwh",
            "20000",
            "--power-mw",
            "2000",
            "--lead-days",
            "6",
        ]
    )
    assert code == 2


def test_cycles_per_year_zero_and_negative_exit_two():
    for value in ("0", "-5"):
        code = cli.main(
            [
                "--input",
                EXAMPLE,
                "--storage-mwh",
                "20000",
                "--power-mw",
                "2000",
                "--cycles-per-year",
                value,
            ]
        )
        assert code == 2


def test_non_finite_storage_flags_exit_two():
    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(
            ["--input", EXAMPLE, "--storage-mwh", "nan", "--power-mw", "2000"]
        )
    assert exc.value.code == 2

    with pytest.raises(SystemExit) as exc:
        cli.build_parser().parse_args(
            ["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "inf"]
        )
    assert exc.value.code == 2


def test_malformed_csv_exits_two(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("date,hour,load_mw\nnot-a-date,0,100\n")
    code = cli.main(["--input", str(bad), "--storage-mwh", "20000", "--power-mw", "2000"])
    assert code == 2


# --------------------------------------------------------------------------- #
# Phase 4: recharge mismatch family wired into the summary
# --------------------------------------------------------------------------- #


def test_json_summary_carries_the_recharge_keys():
    report = _report([])
    summary = report["summary"]
    assert "recharge_opportunity_mwh" in summary
    assert "span_recharge_mismatch_mwh" in summary
    assert "recharge_capacity_mismatch_fraction" in summary
    assert "maximum_available_capacity_mwh" in summary
    # examples/synthetic_winter_stress.csv wind never exceeds its net load
    # (risk R7), so these are correct zeros, not a wiring fault.
    assert summary["recharge_opportunity_mwh"] >= 0.0
    assert summary["span_recharge_mismatch_mwh"] >= 0.0


def test_span_recharge_mismatch_matches_opportunity_minus_charged():
    report = _report([])
    summary = report["summary"]
    assert summary["span_recharge_mismatch_mwh"] == pytest.approx(
        summary["recharge_opportunity_mwh"] - summary["energy_charged_mwh"]
    )


def test_table_output_contains_span_recharge_mismatch_and_open_marker(capsys):
    code = cli.main(["--input", EXAMPLE, "--storage-mwh", "20000", "--power-mw", "2000"])
    assert code == 0
    out = capsys.readouterr().out
    assert "span recharge mismatch" in out
    assert "[OPEN: recharge_opportunity_definition]" in out


def test_maximum_available_capacity_is_seventy_percent_at_default_fractions():
    report = _report([])
    assert report["summary"]["maximum_available_capacity_mwh"] == pytest.approx(0.70 * 20000)


def test_render_table_renders_recharge_capacity_mismatch_as_percent():
    # Doctored-report pattern, matching
    # test_daily_table_columns_align_across_magnitudes.
    report = _report([])
    report["summary"]["recharge_capacity_mismatch_fraction"] = 0.05
    buf = io.StringIO()
    cli._render_table(report, argparse.Namespace(name=None), buf)
    assert "5.0%" in buf.getvalue()
