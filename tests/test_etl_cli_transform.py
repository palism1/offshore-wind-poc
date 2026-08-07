"""Tests for `etl transform` CLI wiring (docs/PLAN.md Phase 2 step 2).

The computation modules (owr.etl.daily, owr.etl.transform, owr.stress_finder) are
already tested elsewhere; this module only exercises the CLI's argument parsing,
file handling, and error surfacing. Fixture rows CSVs are built with
`write_rows_csv` so they match exactly what `etl extract --out` produces.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from owr.etl import cli
from owr.etl.extract import DATASETS
from owr.etl.provenance import Provenance
from owr.etl.rows_csv import write_rows_csv

HOURLY_LOAD = DATASETS["load"]


def _prov() -> Provenance:
    return Provenance.stamp(
        source="gridstatus.isone.load",
        source_query="test fixture",
        dataset_version="gridstatus==0.0.0",
        retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _hourly_rows_for_days(dates: list[str], *, mw_by_date: dict[str, float]) -> list[tuple]:
    """24 hourly readings per date at a fixed load, tz-aware Eastern offsets ignored
    (fixture uses a fixed -05:00 offset year-round for simplicity, which is fine:
    the daily rollup only cares about `interval_hours`, and expected_hours is
    derived independently from the calendar date, not from the offset in `ts`)."""
    rows = []
    for d in dates:
        mw = mw_by_date[d]
        for hour in range(24):
            ts = f"{d}T{hour:02d}:00:00-05:00"
            rows.append((ts, "ISONE", mw, 60.0))
    return rows


def _write_fixture(path, dates: list[str], mw_by_date: dict[str, float]) -> None:
    rows = _hourly_rows_for_days(dates, mw_by_date=mw_by_date)
    write_rows_csv(str(path), HOURLY_LOAD, rows, _prov())


def _header_only(path) -> None:
    write_rows_csv(str(path), HOURLY_LOAD, [], _prov())


def _run(argv: list[str]) -> tuple[int, str]:
    """Parse argv through the real parser and run the dispatched command,
    capturing stdout via a monkeypatched print is avoided; callers use capsys."""
    args = cli.build_parser().parse_args(argv)
    code = args.func(args)
    return code, ""


# --------------------------------------------------------------------------- #
# End-to-end                                                                   #
# --------------------------------------------------------------------------- #


def test_transform_end_to_end(tmp_path, capsys):
    path = tmp_path / "load.csv"
    winter_dates = [f"2023-01-{d:02d}" for d in range(1, 11)]
    mw_by_date = {d: 1000.0 for d in winter_dates}
    # push the last two days above the rest so a 2-day stress window is detected
    mw_by_date[winter_dates[-1]] = 5000.0
    mw_by_date[winter_dates[-2]] = 5000.0
    _write_fixture(path, winter_dates, mw_by_date)

    code, _ = _run(["transform", "--input", str(path), "--min-window-days", "2"])
    out = capsys.readouterr().out

    assert code == 0
    assert "threshold_mwh" in out
    assert "2022/23" in out


def test_transform_no_longer_not_implemented(tmp_path, capsys):
    path = tmp_path / "load.csv"
    winter_dates = [f"2023-01-{d:02d}" for d in range(1, 4)]
    _write_fixture(path, winter_dates, {d: 1000.0 for d in winter_dates})

    code, _ = _run(["transform", "--input", str(path)])
    out = capsys.readouterr().out

    assert "not implemented yet" not in out
    assert code == 0


def test_transform_reports_population_pending_below_five_winters(tmp_path, capsys):
    path = tmp_path / "load.csv"
    winter_dates = [f"2023-01-{d:02d}" for d in range(1, 4)]
    _write_fixture(path, winter_dates, {d: 1000.0 for d in winter_dates})

    code, _ = _run(["transform", "--input", str(path)])
    out = capsys.readouterr().out
    assert code == 0
    assert "population covers 1 winter(s); the 5-winter pooled value is pending data" in out

    code, _ = _run(["transform", "--input", str(path), "--format", "json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["population_winters"] == 1
    assert payload["population_pending"] is True


def test_transform_csv_carries_load_percentile(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "daily.csv"
    winter_dates = [f"2023-01-{d:02d}" for d in range(1, 4)]
    _write_fixture(in_path, winter_dates, {d: 1000.0 for d in winter_dates})

    code, _ = _run(["transform", "--input", str(in_path), "--out", str(out_path)])
    capsys.readouterr()
    assert code == 0

    header = out_path.read_text().splitlines()[0]
    assert header.endswith("load_percentile")


# --------------------------------------------------------------------------- #
# Multiple inputs pooled                                                       #
# --------------------------------------------------------------------------- #


def test_transform_pools_multiple_inputs(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_b = tmp_path / "b.csv"
    dates_a = [f"2023-01-{d:02d}" for d in range(1, 6)]
    dates_b = [f"2023-02-{d:02d}" for d in range(1, 6)]
    _write_fixture(path_a, dates_a, {d: 1000.0 for d in dates_a})
    _write_fixture(path_b, dates_b, {d: 1000.0 for d in dates_b})

    code, _ = _run(
        ["transform", "--input", str(path_a), "--input", str(path_b), "--min-window-days", "2"]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "population_days = 10" in out


# --------------------------------------------------------------------------- #
# Header-only file skipped                                                     #
# --------------------------------------------------------------------------- #


def test_transform_skips_header_only_file(tmp_path, capsys):
    empty_path = tmp_path / "empty.csv"
    data_path = tmp_path / "data.csv"
    _header_only(empty_path)
    dates = [f"2023-01-{d:02d}" for d in range(1, 4)]
    _write_fixture(data_path, dates, {d: 1000.0 for d in dates})

    code, _ = _run(["transform", "--input", str(empty_path), "--input", str(data_path)])
    captured = capsys.readouterr()

    assert code == 0
    assert "0 data rows, skipping" not in captured.out
    assert "0 data rows, skipping" in captured.err
    assert str(empty_path) in captured.err


# --------------------------------------------------------------------------- #
# Skip diagnostic goes to stderr, not stdout, in both formats                  #
# --------------------------------------------------------------------------- #


def test_transform_skip_diagnostic_on_stderr_text_format(tmp_path, capsys):
    empty_path = tmp_path / "empty.csv"
    data_path = tmp_path / "data.csv"
    _header_only(empty_path)
    dates = [f"2023-01-{d:02d}" for d in range(1, 4)]
    _write_fixture(data_path, dates, {d: 1000.0 for d in dates})

    code, _ = _run(
        ["transform", "--input", str(empty_path), "--input", str(data_path), "--format", "text"]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "0 data rows, skipping" not in captured.out
    assert "0 data rows, skipping" in captured.err


def test_transform_json_stays_parseable_with_header_only_input(tmp_path, capsys):
    empty_path = tmp_path / "empty.csv"
    data_path = tmp_path / "data.csv"
    _header_only(empty_path)
    dates = [f"2023-01-{d:02d}" for d in range(1, 4)]
    _write_fixture(data_path, dates, {d: 1000.0 for d in dates})

    code, _ = _run(
        ["transform", "--input", str(empty_path), "--input", str(data_path), "--format", "json"]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "0 data rows, skipping" not in captured.out
    assert "0 data rows, skipping" in captured.err
    payload = json.loads(captured.out)  # must succeed on stdout alone
    assert payload["season"] == "winter"


# --------------------------------------------------------------------------- #
# --season other than winter: threshold only, no windows                      #
# --------------------------------------------------------------------------- #


def test_transform_season_summer_does_not_emit_winter_windows_text(tmp_path, capsys):
    path = tmp_path / "load.csv"
    winter_dates = [f"2023-01-{d:02d}" for d in range(1, 11)]
    summer_dates = [f"2023-07-{d:02d}" for d in range(1, 11)]
    mw_by_date = {d: 1000.0 for d in winter_dates + summer_dates}
    # push winter days above the rest so a winter stress window would be
    # detected if window detection incorrectly ran against this season
    mw_by_date[winter_dates[-1]] = 5000.0
    mw_by_date[winter_dates[-2]] = 5000.0
    _write_fixture(path, winter_dates + summer_dates, mw_by_date)

    code, _ = _run(
        ["transform", "--input", str(path), "--season", "summer", "--min-window-days", "2"]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "season          = summer" in out
    assert "2022/23" not in out  # no winter_label windows leaked through
    assert "stress windows: not computed (window detection is winter-only)" in out


def test_transform_season_summer_does_not_emit_winter_windows_json(tmp_path, capsys):
    path = tmp_path / "load.csv"
    winter_dates = [f"2023-01-{d:02d}" for d in range(1, 11)]
    summer_dates = [f"2023-07-{d:02d}" for d in range(1, 11)]
    mw_by_date = {d: 1000.0 for d in winter_dates + summer_dates}
    mw_by_date[winter_dates[-1]] = 5000.0
    mw_by_date[winter_dates[-2]] = 5000.0
    _write_fixture(path, winter_dates + summer_dates, mw_by_date)

    code, _ = _run(
        [
            "transform",
            "--input",
            str(path),
            "--season",
            "summer",
            "--min-window-days",
            "2",
            "--format",
            "json",
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    payload = json.loads(out)
    assert payload["season"] == "summer"
    assert payload["windows"] is None
    assert "winter-only" in payload["stress_windows_note"]


def test_transform_season_winter_unchanged(tmp_path, capsys):
    path = tmp_path / "load.csv"
    winter_dates = [f"2023-01-{d:02d}" for d in range(1, 11)]
    mw_by_date = {d: 1000.0 for d in winter_dates}
    mw_by_date[winter_dates[-1]] = 5000.0
    mw_by_date[winter_dates[-2]] = 5000.0
    _write_fixture(path, winter_dates, mw_by_date)

    code, _ = _run(
        [
            "transform",
            "--input",
            str(path),
            "--season",
            "winter",
            "--min-window-days",
            "2",
            "--format",
            "json",
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    payload = json.loads(out)
    assert payload["season"] == "winter"
    assert payload["windows"] is not None
    assert "2022/23" in payload["windows"]
    assert len(payload["windows"]["2022/23"]) == 1


# --------------------------------------------------------------------------- #
# Cross-file duplicate-instant overlap                                        #
# --------------------------------------------------------------------------- #


def test_transform_cross_file_duplicate_instant_rejected(tmp_path, capsys):
    # Year-boundary overlap: file A covers late Dec 2022, file B covers early
    # Jan 2023, but they share one identical `ts` (e.g. an off-by-one export
    # window). Duplicate-instant detection is global across pooled inputs
    # (`_run_transform` flattens all --input readings before the single
    # `daily_loads_from_readings` call), so this must surface here too, not
    # just within a single file.
    path_a = tmp_path / "a.csv"
    path_b = tmp_path / "b.csv"
    shared_ts = "2022-12-31T23:00:00-05:00"

    rows_a = [(shared_ts, "ISONE", 1000.0, 60.0)]
    for hour in range(23):
        rows_a.append((f"2022-12-31T{hour:02d}:00:00-05:00", "ISONE", 1000.0, 60.0))
    write_rows_csv(str(path_a), HOURLY_LOAD, rows_a, _prov())

    rows_b = [(shared_ts, "ISONE", 1000.0, 60.0)]  # duplicate of the last row in A
    for hour in range(1, 24):
        rows_b.append((f"2023-01-01T{hour:02d}:00:00-05:00", "ISONE", 1000.0, 60.0))
    write_rows_csv(str(path_b), HOURLY_LOAD, rows_b, _prov())

    code, _ = _run(["transform", "--input", str(path_a), "--input", str(path_b)])
    out = capsys.readouterr().out

    assert code == 2
    assert "error:" in out
    assert shared_ts in out


# --------------------------------------------------------------------------- #
# Errors -> exit 2, not tracebacks                                             #
# --------------------------------------------------------------------------- #


def test_transform_naive_timestamp_rejected(tmp_path, capsys):
    path = tmp_path / "load.csv"
    rows = [("2023-01-01T00:00:00", "ISONE", 1000.0, 60.0)]  # naive, no offset
    write_rows_csv(str(path), HOURLY_LOAD, rows, _prov())

    code, _ = _run(["transform", "--input", str(path)])
    out = capsys.readouterr().out

    assert code == 2
    assert "naive timestamp" in out
    assert str(path) in out


def test_transform_bad_header_rejected(tmp_path, capsys):
    path = tmp_path / "bad.csv"
    path.write_text("not,the,right,header\n1,2,3,4\n")

    code, _ = _run(["transform", "--input", str(path)])
    out = capsys.readouterr().out

    assert code == 2
    assert "error:" in out


def test_row_missing_a_trailing_cell_exits_two_not_traceback(tmp_path, capsys):
    path = tmp_path / "short_row.csv"
    header = "ts,zone,load_mw,interval_minutes,source,retrieved_at,source_query,dataset_version"
    short_row = "2023-01-01T00:00:00-05:00,ISONE,1000.0,60.0,src,2026-01-01T00:00:00+00:00,q"
    path.write_text(f"{header}\n{short_row}\n")

    code, _ = _run(["transform", "--input", str(path)])
    out = capsys.readouterr().out

    assert code == 2
    assert out.startswith("error:")


def test_transform_missing_file_rejected(tmp_path, capsys):
    missing = tmp_path / "does_not_exist.csv"

    code, _ = _run(["transform", "--input", str(missing)])
    out = capsys.readouterr().out

    assert code == 2
    assert "error:" in out


def test_transform_no_complete_days_in_season_exits_2(tmp_path, capsys):
    path = tmp_path / "summer.csv"
    dates = [f"2023-07-{d:02d}" for d in range(1, 4)]  # summer, no winter days at all
    _write_fixture(path, dates, {d: 1000.0 for d in dates})

    code, _ = _run(["transform", "--input", str(path), "--season", "winter"])
    out = capsys.readouterr().out

    assert code == 2
    assert "error:" in out


# --------------------------------------------------------------------------- #
# --format json                                                                #
# --------------------------------------------------------------------------- #


def test_transform_json_format_parses(tmp_path, capsys):
    path = tmp_path / "load.csv"
    dates = [f"2023-01-{d:02d}" for d in range(1, 4)]
    _write_fixture(path, dates, {d: 1000.0 for d in dates})

    code, _ = _run(["transform", "--input", str(path), "--format", "json"])
    out = capsys.readouterr().out

    assert code == 0
    payload = json.loads(out)
    assert payload["season"] == "winter"
    assert "threshold_mwh" in payload
    assert "windows" in payload


# --------------------------------------------------------------------------- #
# --out writes the daily CSV                                                   #
# --------------------------------------------------------------------------- #


def test_transform_out_writes_daily_csv(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "daily.csv"
    dates = [f"2023-01-{d:02d}" for d in range(1, 4)]
    _write_fixture(in_path, dates, {d: 1000.0 for d in dates})

    code, _ = _run(["transform", "--input", str(in_path), "--out", str(out_path)])
    capsys.readouterr()

    assert code == 0
    assert out_path.exists()
    header = out_path.read_text().splitlines()[0]
    assert header == (
        "date,load_mwh,hours_covered,expected_hours,intervals,complete,season,"
        "winter_label,load_percentile"
    )
    lines = out_path.read_text().splitlines()
    assert len(lines) == 1 + len(dates)


# --------------------------------------------------------------------------- #
# Parser wiring                                                                #
# --------------------------------------------------------------------------- #


def test_transform_out_daily_csv_is_byte_identical_to_the_expected_text(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "daily.csv"
    dates = [f"2023-01-{d:02d}" for d in range(1, 4)]
    _write_fixture(in_path, dates, {d: 1000.0 for d in dates})

    code, _ = _run(["transform", "--input", str(in_path), "--out", str(out_path)])
    capsys.readouterr()

    assert code == 0
    expected = (
        b"date,load_mwh,hours_covered,expected_hours,intervals,complete,season,"
        b"winter_label,load_percentile\r\n"
        b"2023-01-01,24000.0,24.0,24.0,24,True,winter,2022/23,100.0\r\n"
        b"2023-01-02,24000.0,24.0,24.0,24,True,winter,2022/23,100.0\r\n"
        b"2023-01-03,24000.0,24.0,24.0,24,True,winter,2022/23,100.0\r\n"
    )
    assert out_path.read_bytes() == expected


def test_transform_json_keeps_a_winter_with_no_window(tmp_path, capsys):
    path = tmp_path / "load.csv"
    winter_a_dates = [f"2023-01-{d:02d}" for d in range(1, 11)]
    winter_b_dates = [f"2024-01-{d:02d}" for d in range(1, 11)]
    mw_by_date = {d: 1000.0 for d in winter_a_dates + winter_b_dates}
    # push winter A's last two days above the rest so a 2-day stress window is
    # detected there; winter B stays flat and qualifies for no window.
    mw_by_date[winter_a_dates[-1]] = 5000.0
    mw_by_date[winter_a_dates[-2]] = 5000.0
    _write_fixture(path, winter_a_dates + winter_b_dates, mw_by_date)

    code, _ = _run(
        ["transform", "--input", str(path), "--min-window-days", "2", "--format", "json"]
    )
    out = capsys.readouterr().out

    assert code == 0
    payload = json.loads(out)
    assert set(payload["windows"]) == {"2022/23", "2023/24"}
    assert payload["windows"]["2023/24"] == []
    assert len(payload["windows"]["2022/23"]) == 1


def test_transform_json_days_field_is_a_plain_int(tmp_path, capsys):
    path = tmp_path / "load.csv"
    winter_dates = [f"2023-01-{d:02d}" for d in range(1, 11)]
    mw_by_date = {d: 1000.0 for d in winter_dates}
    mw_by_date[winter_dates[-1]] = 5000.0
    mw_by_date[winter_dates[-2]] = 5000.0
    _write_fixture(path, winter_dates, mw_by_date)

    code, _ = _run(
        ["transform", "--input", str(path), "--min-window-days", "2", "--format", "json"]
    )
    out = capsys.readouterr().out

    assert code == 0
    payload = json.loads(out)
    assert type(payload["windows"]["2022/23"][0]["days"]) is int


def test_cli_parser_dispatches_transform():
    args = cli.build_parser().parse_args(
        ["transform", "--input", "a.csv", "--input", "b.csv"]
    )
    assert args.func is cli.cmd_transform
    assert args.inputs == ["a.csv", "b.csv"]
    assert args.season == "winter"
    assert args.format == "text"


def test_cli_parser_transform_defaults_match_config():
    from owr.config import DEFAULT_CONFIG

    args = cli.build_parser().parse_args(["transform", "--input", "a.csv"])
    assert args.percentile == DEFAULT_CONFIG.default_severity_percentile
    assert args.min_window_days == DEFAULT_CONFIG.default_min_stress_window_days


def test_cli_transform_requires_at_least_one_input():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["transform"])
