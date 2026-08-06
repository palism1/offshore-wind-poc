"""Tests for `etl demo-profile` CLI wiring (docs/archive/plans/PLAN_REAL_DEMO_BRIDGE.md Phase 2).

The computation modules (owr.etl.daily, owr.etl.demo_profile) are tested elsewhere;
this module only exercises the CLI's argument parsing, file handling, and error
surfacing. Fixture rows CSVs are built with `write_rows_csv`, exactly as
tests/test_etl_cli_transform.py does.
"""

from __future__ import annotations

from datetime import UTC, datetime

from owr import scenario_input
from owr.etl import cli
from owr.etl.extract import DATASETS
from owr.etl.provenance import Provenance
from owr.etl.rows_csv import write_rows_csv

HOURLY_LOAD = DATASETS["load"]
HOURLY_WIND = DATASETS["wind"]


def _prov(retrieved_at: datetime | None = None) -> Provenance:
    return Provenance.stamp(
        source="gridstatus.isone.load",
        source_query="test fixture",
        dataset_version="gridstatus==0.0.0",
        retrieved_at=retrieved_at or datetime(2026, 1, 1, tzinfo=UTC),
    )


def _hourly_rows_for_days(dates: list[str], *, mw_by_date: dict[str, float]) -> list[tuple]:
    rows = []
    for d in dates:
        mw = mw_by_date[d]
        for hour in range(24):
            ts = f"{d}T{hour:02d}:00:00-05:00"
            rows.append((ts, "ISONE", mw, 60.0))
    return rows


def _write_fixture(path, dates: list[str], mw_by_date: dict[str, float], *, prov=None) -> None:
    rows = _hourly_rows_for_days(dates, mw_by_date=mw_by_date)
    write_rows_csv(str(path), HOURLY_LOAD, rows, prov or _prov())


def _header_only(path) -> None:
    write_rows_csv(str(path), HOURLY_LOAD, [], _prov())


def _run(argv: list[str]) -> int:
    args = cli.build_parser().parse_args(argv)
    return args.func(args)


def _wind_prov(retrieved_at: datetime | None = None) -> Provenance:
    return Provenance.stamp(
        source="eia930.isne.wind",
        source_query="test wind fixture",
        dataset_version="gridstatus==0.36.0",
        retrieved_at=retrieved_at or datetime(2026, 1, 1, tzinfo=UTC),
    )


def _wind_rows_for_days(
    dates: list[str], *, mw_by_date: dict[str, float], horizon_days: int = 0
) -> list[tuple]:
    rows = []
    for d in dates:
        mw = mw_by_date[d]
        for hour in range(24):
            ts = f"{d}T{hour:02d}:00:00-05:00"
            rows.append((ts, mw, "", horizon_days))
    return rows


def _write_wind_fixture(
    path, dates: list[str], mw_by_date: dict[str, float], *, prov=None, horizon_days: int = 0
) -> None:
    rows = _wind_rows_for_days(dates, mw_by_date=mw_by_date, horizon_days=horizon_days)
    write_rows_csv(str(path), HOURLY_WIND, rows, prov or _wind_prov())


_WINTER_DATES = [f"2023-01-{d:02d}" for d in range(1, 11)]  # ten winter days


def _ten_day_fixture(path, mw_by_date: dict[str, float] | None = None) -> dict[str, float]:
    mw = mw_by_date or {d: 1000.0 + i * 10 for i, d in enumerate(_WINTER_DATES)}
    _write_fixture(path, _WINTER_DATES, mw)
    return mw


# --------------------------------------------------------------------------- #
# End to end                                                                   #
# --------------------------------------------------------------------------- #


def test_demo_profile_end_to_end(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    capsys.readouterr()

    assert code == 0
    with open(out_path, encoding="utf-8") as f:
        result = scenario_input.read_day_profiles(f, origin=str(out_path))
    assert len(result.days) == 4
    assert result.demand_percentile_source == "file"
    assert result.has_wind is False


def test_demo_profile_known_totals_match_hand_computed_rank(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "profile.csv"
    mw_by_date = {d: 1000.0 + i * 10 for i, d in enumerate(_WINTER_DATES)}
    _write_fixture(in_path, _WINTER_DATES, mw_by_date)
    day_totals_mwh = {d: mw * 24 for d, mw in mw_by_date.items()}

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--start",
            "2023-01-01",
            "--end",
            "2023-01-10",
            "--out",
            str(out_path),
        ]
    )
    capsys.readouterr()
    assert code == 0

    population = sorted(day_totals_mwh.values())
    n = len(population)
    with open(out_path, encoding="utf-8") as f:
        result = scenario_input.read_day_profiles(f, origin=str(out_path))
    for day in result.days:
        v = day_totals_mwh[day.date.isoformat()]
        expected = sum(1 for p in population if p <= v) / n
        assert day.demand_percentile == expected


def test_demo_profile_highest_day_ranks_exactly_one(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "profile.csv"
    mw_by_date = {d: 1000.0 + i * 10 for i, d in enumerate(_WINTER_DATES)}
    _write_fixture(in_path, _WINTER_DATES, mw_by_date)

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--start",
            "2023-01-01",
            "--end",
            "2023-01-10",
            "--out",
            str(out_path),
        ]
    )
    capsys.readouterr()
    assert code == 0

    with open(out_path, encoding="utf-8") as f:
        result = scenario_input.read_day_profiles(f, origin=str(out_path))
    highest = max(result.days, key=lambda d: d.date)
    assert highest.demand_percentile == 1.0


# --------------------------------------------------------------------------- #
# Errors -> exit 2, not tracebacks                                            #
# --------------------------------------------------------------------------- #


def test_demo_profile_missing_input_file_exits_2(tmp_path, capsys):
    missing = tmp_path / "does_not_exist.csv"
    out_path = tmp_path / "profile.csv"

    code = _run(
        [
            "demo-profile",
            "--input",
            str(missing),
            "--start",
            "2023-01-01",
            "--end",
            "2023-01-02",
            "--out",
            str(out_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert out.startswith("error:")
    assert "Traceback" not in out


def test_demo_profile_start_after_end_exits_2(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--start",
            "2023-01-06",
            "--end",
            "2023-01-03",
            "--out",
            str(out_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert out.startswith("error:")


def test_demo_profile_23_hour_date_exits_2_and_names_date(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "profile.csv"
    dates = [f"2023-01-{d:02d}" for d in range(1, 11)]
    rows = _hourly_rows_for_days(dates, mw_by_date={d: 1000.0 for d in dates})
    # Drop one hourly reading on 2023-01-05 so that date has only 23 hours.
    rows = [r for r in rows if not (r[0].startswith("2023-01-05T04:00:00"))]
    write_rows_csv(str(in_path), HOURLY_LOAD, rows, _prov())

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--start",
            "2023-01-01",
            "--end",
            "2023-01-10",
            "--out",
            str(out_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert out.startswith("error:")
    assert "2023-01-05" in out


def test_demo_profile_selected_date_outside_population_exits_2_and_names_date(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)  # only covers 2023-01-01..10

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--start",
            "2023-01-01",
            "--end",
            "2023-01-12",  # 11th/12th are outside the fixture
            "--out",
            str(out_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert out.startswith("error:")
    assert "2023-01-11" in out


# --------------------------------------------------------------------------- #
# Header-only input skipped                                                   #
# --------------------------------------------------------------------------- #


def test_demo_profile_skips_header_only_file(tmp_path, capsys):
    empty_path = tmp_path / "empty.csv"
    data_path = tmp_path / "data.csv"
    out_path = tmp_path / "profile.csv"
    _header_only(empty_path)
    _ten_day_fixture(data_path)

    code = _run(
        [
            "demo-profile",
            "--input",
            str(empty_path),
            "--input",
            str(data_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-05",
            "--out",
            str(out_path),
        ]
    )
    captured = capsys.readouterr()

    assert code == 0
    assert "0 data rows, skipping" not in captured.out
    assert "0 data rows, skipping" in captured.err
    assert str(empty_path) in captured.err


# --------------------------------------------------------------------------- #
# Banner carries sorted, distinct provenance pairs                            #
# --------------------------------------------------------------------------- #


def test_demo_profile_banner_carries_both_provenance_pairs_sorted(tmp_path, capsys):
    path_a = tmp_path / "a.csv"
    path_b = tmp_path / "b.csv"
    out_path = tmp_path / "profile.csv"
    dates_a = [f"2023-01-{d:02d}" for d in range(1, 6)]
    dates_b = [f"2023-01-{d:02d}" for d in range(6, 11)]
    _write_fixture(
        path_a, dates_a, {d: 1000.0 for d in dates_a}, prov=_prov(datetime(2026, 1, 1, tzinfo=UTC))
    )
    _write_fixture(
        path_b, dates_b, {d: 1000.0 for d in dates_b}, prov=_prov(datetime(2026, 2, 1, tzinfo=UTC))
    )

    code = _run(
        [
            "demo-profile",
            "--input",
            str(path_a),
            "--input",
            str(path_b),
            "--start",
            "2023-01-01",
            "--end",
            "2023-01-10",
            "--out",
            str(out_path),
        ]
    )
    capsys.readouterr()
    assert code == 0

    text = out_path.read_text()
    assert text.count("retrieved_at = 2026-01-01") == 1
    assert text.count("retrieved_at = 2026-02-01") == 1
    first = text.index("retrieved_at = 2026-01-01")
    second = text.index("retrieved_at = 2026-02-01")
    assert first < second


# --------------------------------------------------------------------------- #
# Byte-identical across runs                                                  #
# --------------------------------------------------------------------------- #


def test_demo_profile_byte_identical_across_runs(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)

    argv = [
        "demo-profile",
        "--input",
        str(in_path),
        "--start",
        "2023-01-03",
        "--end",
        "2023-01-06",
        "--out",
        str(out_path),
    ]

    code = _run(argv)
    capsys.readouterr()
    assert code == 0
    first = out_path.read_bytes()

    code = _run(argv)
    capsys.readouterr()
    assert code == 0
    second = out_path.read_bytes()

    assert first == second


# --------------------------------------------------------------------------- #
# Parser wiring                                                               #
# --------------------------------------------------------------------------- #


def test_cli_parser_dispatches_demo_profile():
    args = cli.build_parser().parse_args(
        [
            "demo-profile",
            "--input",
            "a.csv",
            "--start",
            "2023-01-01",
            "--end",
            "2023-01-02",
            "--out",
            "out.csv",
        ]
    )
    assert args.func is cli.cmd_demo_profile
    assert args.inputs == ["a.csv"]
    assert args.season == "winter"


def test_cli_demo_profile_requires_all_flags():
    import pytest

    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["demo-profile", "--input", "a.csv"])


# --------------------------------------------------------------------------- #
# --wind-input                                                                 #
# --------------------------------------------------------------------------- #


def test_demo_profile_end_to_end_with_wind(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    wind_path = tmp_path / "wind.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)
    wind_mw = {d: 50.0 + i for i, d in enumerate(_WINTER_DATES)}
    _write_wind_fixture(wind_path, _WINTER_DATES, wind_mw)

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--wind-input",
            str(wind_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    capsys.readouterr()
    assert code == 0

    with open(out_path, encoding="utf-8") as f:
        result = scenario_input.read_day_profiles(f, origin=str(out_path))
    assert result.has_wind is True
    for day in result.days:
        expected = wind_mw[day.date.isoformat()]
        for hourly_wind in day.hourly_wind_mw:
            assert hourly_wind == expected


def test_demo_profile_no_wind_input_has_wind_false(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    capsys.readouterr()
    assert code == 0

    text = out_path.read_text()
    with open(out_path, encoding="utf-8") as f:
        result = scenario_input.read_day_profiles(f, origin=str(out_path))
    assert result.has_wind is False
    header = next(line for line in text.splitlines() if line.startswith("date,hour"))
    assert "wind_mw" not in header


def test_demo_profile_wind_banner(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    wind_path = tmp_path / "wind.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)
    _write_wind_fixture(wind_path, _WINTER_DATES, {d: 50.0 for d in _WINTER_DATES})

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--wind-input",
            str(wind_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    capsys.readouterr()
    assert code == 0

    text = out_path.read_text()
    assert "source = eia930.isne.wind" in text
    assert "REAL  wind_mw" in text


def test_demo_profile_wind_missing_hour_exits_2_and_names_it(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    wind_path = tmp_path / "wind.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)
    rows = _wind_rows_for_days(_WINTER_DATES, mw_by_date={d: 50.0 for d in _WINTER_DATES})
    rows = [r for r in rows if not r[0].startswith("2023-01-04T05:00:00")]
    write_rows_csv(str(wind_path), HOURLY_WIND, rows, _wind_prov())

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--wind-input",
            str(wind_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert out.startswith("error:")
    assert "2023-01-04" in out
    assert "5" in out


def test_demo_profile_wind_realized_row_wins_over_forecast(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    wind_path = tmp_path / "wind.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)
    realized = _wind_rows_for_days(
        _WINTER_DATES, mw_by_date={d: 50.0 for d in _WINTER_DATES}, horizon_days=0
    )
    forecast = _wind_rows_for_days(
        _WINTER_DATES, mw_by_date={d: 999.0 for d in _WINTER_DATES}, horizon_days=1
    )
    write_rows_csv(str(wind_path), HOURLY_WIND, realized + forecast, _wind_prov())

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--wind-input",
            str(wind_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    capsys.readouterr()
    assert code == 0

    with open(out_path, encoding="utf-8") as f:
        result = scenario_input.read_day_profiles(f, origin=str(out_path))
    for day in result.days:
        for hourly_wind in day.hourly_wind_mw:
            assert hourly_wind == 50.0


def test_demo_profile_wind_only_forecast_rows_exits_2(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    wind_path = tmp_path / "wind.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)
    _write_wind_fixture(
        wind_path, _WINTER_DATES, {d: 50.0 for d in _WINTER_DATES}, horizon_days=1
    )

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--wind-input",
            str(wind_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert "no realized (horizon_days = 0) wind rows" in out


def test_demo_profile_wind_bad_horizon_days_exits_2_and_names_it(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    wind_path = tmp_path / "wind.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)
    rows = _wind_rows_for_days(_WINTER_DATES, mw_by_date={d: 50.0 for d in _WINTER_DATES})
    ts0 = rows[0][0]
    rows[0] = (rows[0][0], rows[0][1], rows[0][2], "x")
    write_rows_csv(str(wind_path), HOURLY_WIND, rows, _wind_prov())

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--wind-input",
            str(wind_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert out.startswith("error:")
    assert str(wind_path) in out
    assert ts0 in out


def test_demo_profile_load_file_as_wind_input_exits_2(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--wind-input",
            str(in_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert "does not match" in out


def test_demo_profile_wind_blank_gen_mw_exits_2_and_names_timestamp(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    wind_path = tmp_path / "wind.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)
    rows = _wind_rows_for_days(_WINTER_DATES, mw_by_date={d: 50.0 for d in _WINTER_DATES})
    ts0 = rows[0][0]
    rows[0] = (rows[0][0], "", rows[0][2], rows[0][3])
    write_rows_csv(str(wind_path), HOURLY_WIND, rows, _wind_prov())

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--wind-input",
            str(wind_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    out = capsys.readouterr().out

    assert code == 2
    assert out.startswith("error:")
    assert ts0 in out


def test_demo_profile_wind_zero_data_rows_skip_then_exits_2(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    wind_path = tmp_path / "wind.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)
    write_rows_csv(str(wind_path), HOURLY_WIND, [], _wind_prov())

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--wind-input",
            str(wind_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    captured = capsys.readouterr()

    assert code == 2
    assert "0 data rows, skipping" in captured.err
    assert str(wind_path) in captured.err


def test_demo_profile_generated_by_line_carries_wind_input_after_input(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    wind_path = tmp_path / "wind.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)
    _write_wind_fixture(wind_path, _WINTER_DATES, {d: 50.0 for d in _WINTER_DATES})

    code = _run(
        [
            "demo-profile",
            "--input",
            str(in_path),
            "--wind-input",
            str(wind_path),
            "--start",
            "2023-01-03",
            "--end",
            "2023-01-06",
            "--out",
            str(out_path),
        ]
    )
    capsys.readouterr()
    assert code == 0

    text = out_path.read_text()
    line = next(line for line in text.splitlines() if line.startswith("# Generated by:"))
    assert line.index(f"--input {in_path}") < line.index(f"--wind-input {wind_path}")


def test_demo_profile_wind_runs_are_byte_identical(tmp_path, capsys):
    in_path = tmp_path / "load.csv"
    wind_path = tmp_path / "wind.csv"
    out_path = tmp_path / "profile.csv"
    _ten_day_fixture(in_path)
    _write_wind_fixture(wind_path, _WINTER_DATES, {d: 50.0 for d in _WINTER_DATES})

    argv = [
        "demo-profile",
        "--input",
        str(in_path),
        "--wind-input",
        str(wind_path),
        "--start",
        "2023-01-03",
        "--end",
        "2023-01-06",
        "--out",
        str(out_path),
    ]

    code = _run(argv)
    capsys.readouterr()
    assert code == 0
    first = out_path.read_bytes()

    code = _run(argv)
    capsys.readouterr()
    assert code == 0
    second = out_path.read_bytes()

    assert first == second


def test_cli_parser_wind_input_wiring():
    args = cli.build_parser().parse_args(
        [
            "demo-profile",
            "--input",
            "a.csv",
            "--wind-input",
            "a.csv",
            "--wind-input",
            "b.csv",
            "--start",
            "2023-01-01",
            "--end",
            "2023-01-02",
            "--out",
            "out.csv",
        ]
    )
    assert args.wind_inputs == ["a.csv", "b.csv"]

    args_no_wind = cli.build_parser().parse_args(
        [
            "demo-profile",
            "--input",
            "a.csv",
            "--start",
            "2023-01-01",
            "--end",
            "2023-01-02",
            "--out",
            "out.csv",
        ]
    )
    assert args_no_wind.wind_inputs is None
