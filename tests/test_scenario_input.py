"""Tests for the day-profile CSV reader (src/owr/scenario_input.py)."""

from __future__ import annotations

import io
import sys
from datetime import date

import pytest

from owr.scenario_input import ScenarioInputError, read_day_profiles

HOURS = range(24)


def _rows(date_str: str, load_values: list[float], extra: dict[str, list] | None = None) -> str:
    """Build CSV row lines for one date, 24 hours, given per-hour load values and
    optional extra per-hour columns (dict of column name -> 24 values)."""
    extra = extra or {}
    lines = []
    for h in HOURS:
        cells = [date_str, str(h), str(load_values[h])]
        for _col, values in extra.items():
            cells.append(str(values[h]))
        lines.append(",".join(cells))
    return lines


def _flat_load(value: float = 8000.0) -> list[float]:
    return [value] * 24


def _csv(header: str, *day_lines: list[str]) -> str:
    rows: list[str] = [header]
    for lines in day_lines:
        rows.extend(lines)
    return "\n".join(rows) + "\n"


# --------------------------------------------------------------------------- #
# Basic shape
# --------------------------------------------------------------------------- #


def test_minimal_csv_one_day_profile_no_wind():
    content = _csv("date,hour,load_mw", _rows("2026-01-10", _flat_load()))
    result = read_day_profiles(io.StringIO(content), origin="test")
    assert len(result.days) == 1
    assert result.days[0].hourly_wind_mw == ()
    assert result.has_wind is False


def test_wind_mw_column_present_gives_24_wind_values():
    content = _csv(
        "date,hour,load_mw,wind_mw",
        _rows("2026-01-10", _flat_load(), {"wind_mw": [500.0] * 24}),
    )
    result = read_day_profiles(io.StringIO(content), origin="test")
    assert result.has_wind is True
    assert len(result.days[0].hourly_wind_mw) == 24
    assert result.days[0].hourly_wind_mw[0] == 500.0


def test_rows_shuffled_gives_same_result_as_sorted():
    day1 = _rows("2026-01-10", _flat_load(7000.0))
    day2 = _rows("2026-01-11", _flat_load(8000.0))
    ordered = _csv("date,hour,load_mw", day1, day2)
    shuffled = _csv("date,hour,load_mw", day2, day1)
    r1 = read_day_profiles(io.StringIO(ordered), origin="test")
    r2 = read_day_profiles(io.StringIO(shuffled), origin="test")
    assert [d.date for d in r1.days] == [d.date for d in r2.days] == [
        date(2026, 1, 10),
        date(2026, 1, 11),
    ]
    assert r1.days == r2.days


def test_blank_lines_and_comments_are_skipped():
    content = (
        "# synthetic test file\n"
        "\n"
        "date,hour,load_mw\n"
        "\n"
        "# start of day\n"
        + "\n".join(_rows("2026-01-10", _flat_load()))
        + "\n"
    )
    result = read_day_profiles(io.StringIO(content), origin="test")
    assert len(result.days) == 1


# --------------------------------------------------------------------------- #
# Per-day scalar columns
# --------------------------------------------------------------------------- #


def test_per_day_scalars_read_from_file():
    content = _csv(
        "date,hour,load_mw,demand_percentile,wind_forecast_frac",
        _rows(
            "2026-01-10",
            _flat_load(),
            {"demand_percentile": [0.5] * 24, "wind_forecast_frac": [0.3] * 24},
        ),
    )
    result = read_day_profiles(io.StringIO(content), origin="test")
    assert result.demand_percentile_source == "file"
    assert result.wind_forecast_frac_source == "file"
    assert result.days[0].demand_percentile == 0.5
    assert result.days[0].wind_forecast_frac == 0.3


def test_demand_percentile_absent_is_derived_via_ecdf():
    # 3 days with distinct daily totals -> exact expected ranks.
    days = [
        _rows("2026-01-10", _flat_load(1000.0)),  # smallest total
        _rows("2026-01-11", _flat_load(2000.0)),  # middle total
        _rows("2026-01-12", _flat_load(3000.0)),  # largest total
    ]
    content = _csv("date,hour,load_mw", *days)
    result = read_day_profiles(io.StringIO(content), origin="test")
    assert result.demand_percentile_source == "derived-rank"
    assert any("demand_percentile" in w for w in result.warnings)
    got = {d.date: d.demand_percentile for d in result.days}
    assert got[date(2026, 1, 10)] == pytest.approx(1 / 3)
    assert got[date(2026, 1, 11)] == pytest.approx(2 / 3)
    assert got[date(2026, 1, 12)] == pytest.approx(3 / 3)


def test_wind_forecast_frac_absent_defaults_to_zero():
    content = _csv("date,hour,load_mw", _rows("2026-01-10", _flat_load()))
    result = read_day_profiles(io.StringIO(content), origin="test")
    assert result.wind_forecast_frac_source == "default-zero"
    assert result.days[0].wind_forecast_frac == 0.0
    assert any("wind_forecast_frac" in w for w in result.warnings)


# --------------------------------------------------------------------------- #
# Non-finite rejection
# --------------------------------------------------------------------------- #


NON_FINITE_TOKENS = ["nan", "NaN", "inf", "-inf", "+inf", "Infinity"]


@pytest.mark.parametrize("token", NON_FINITE_TOKENS)
def test_non_finite_load_mw_rejected(token):
    lines = _rows("2026-01-10", _flat_load())
    # replace only the load_mw field (third column) on the first row
    parts = lines[0].split(",")
    parts[2] = token
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="test:2"):
        read_day_profiles(io.StringIO(content), origin="test")


@pytest.mark.parametrize("token", NON_FINITE_TOKENS)
def test_non_finite_wind_mw_rejected(token):
    lines = _rows("2026-01-10", _flat_load(), {"wind_mw": [500.0] * 24})
    parts = lines[0].split(",")
    parts[3] = token
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw,wind_mw", lines)
    with pytest.raises(ScenarioInputError, match="test:2"):
        read_day_profiles(io.StringIO(content), origin="test")


@pytest.mark.parametrize("token", NON_FINITE_TOKENS)
def test_non_finite_demand_percentile_rejected(token):
    lines = _rows("2026-01-10", _flat_load(), {"demand_percentile": [0.5] * 24})
    parts = lines[0].split(",")
    parts[3] = token
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw,demand_percentile", lines)
    with pytest.raises(ScenarioInputError, match="test:2"):
        read_day_profiles(io.StringIO(content), origin="test")


@pytest.mark.parametrize("token", NON_FINITE_TOKENS)
def test_non_finite_wind_forecast_frac_rejected(token):
    lines = _rows("2026-01-10", _flat_load(), {"wind_forecast_frac": [0.3] * 24})
    parts = lines[0].split(",")
    parts[3] = token
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw,wind_forecast_frac", lines)
    with pytest.raises(ScenarioInputError, match="test:2"):
        read_day_profiles(io.StringIO(content), origin="test")


# --------------------------------------------------------------------------- #
# Blank-cell handling
# --------------------------------------------------------------------------- #


def test_blank_wind_mw_cell_defaults_to_zero():
    lines = _rows("2026-01-10", _flat_load(), {"wind_mw": [500.0] * 24})
    parts = lines[0].split(",")
    parts[3] = ""
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw,wind_mw", lines)
    result = read_day_profiles(io.StringIO(content), origin="test")
    assert result.days[0].hourly_wind_mw[0] == 0.0


def test_blank_demand_percentile_cell_rejected():
    lines = _rows("2026-01-10", _flat_load(), {"demand_percentile": [0.5] * 24})
    parts = lines[0].split(",")
    parts[3] = ""
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw,demand_percentile", lines)
    with pytest.raises(ScenarioInputError, match=r"test:2.*demand_percentile"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_blank_wind_forecast_frac_cell_rejected():
    lines = _rows("2026-01-10", _flat_load(), {"wind_forecast_frac": [0.3] * 24})
    parts = lines[0].split(",")
    parts[3] = ""
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw,wind_forecast_frac", lines)
    with pytest.raises(ScenarioInputError, match=r"test:2.*wind_forecast_frac"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_blank_load_mw_cell_rejected():
    lines = _rows("2026-01-10", _flat_load())
    parts = lines[0].split(",")
    parts[2] = ""
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="test:2"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_blank_date_cell_rejected():
    lines = _rows("2026-01-10", _flat_load())
    parts = lines[0].split(",")
    parts[0] = ""
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="test:2"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_blank_hour_cell_rejected():
    lines = _rows("2026-01-10", _flat_load())
    parts = lines[0].split(",")
    parts[1] = ""
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="test:2"):
        read_day_profiles(io.StringIO(content), origin="test")


# --------------------------------------------------------------------------- #
# Other validation rules
# --------------------------------------------------------------------------- #


def test_missing_required_header_column_rejected():
    content = "date,hour\n2026-01-10,0\n"
    with pytest.raises(ScenarioInputError, match="load_mw"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_zero_data_rows_rejected():
    content = "date,hour,load_mw\n"
    with pytest.raises(ScenarioInputError):
        read_day_profiles(io.StringIO(content), origin="test")


def test_unparseable_date_rejected():
    lines = _rows("2026-01-10", _flat_load())
    parts = lines[0].split(",")
    parts[0] = "not-a-date"
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="test:2"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_hour_out_of_range_rejected():
    # 24 is now a valid hour-ending value (change 9); the out-of-range bound is 25.
    lines = _rows("2026-01-10", _flat_load())
    parts = lines[0].split(",")
    parts[1] = "25"
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="test:2"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_duplicate_date_hour_pair_rejected():
    lines = _rows("2026-01-10", _flat_load())
    lines.append(lines[0])  # duplicate hour 0
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="duplicate"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_date_with_wrong_row_count_rejected():
    lines = _rows("2026-01-10", _flat_load())[:23]  # only 23 rows
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="24"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_demand_percentile_varying_within_date_rejected():
    values = [0.5] * 24
    values[1] = 0.6
    lines = _rows("2026-01-10", _flat_load(), {"demand_percentile": values})
    content = _csv("date,hour,load_mw,demand_percentile", lines)
    with pytest.raises(ScenarioInputError, match="varies within date"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_wind_forecast_frac_varying_within_date_rejected():
    values = [0.3] * 24
    values[1] = 0.4
    lines = _rows("2026-01-10", _flat_load(), {"wind_forecast_frac": values})
    content = _csv("date,hour,load_mw,wind_forecast_frac", lines)
    with pytest.raises(ScenarioInputError, match="varies within date"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_non_consecutive_dates_rejected():
    day1 = _rows("2026-01-10", _flat_load())
    day2 = _rows("2026-01-12", _flat_load())  # gap of 2 days
    content = _csv("date,hour,load_mw", day1, day2)
    with pytest.raises(ScenarioInputError, match="not consecutive"):
        read_day_profiles(io.StringIO(content), origin="test")


# --------------------------------------------------------------------------- #
# Phase 6 — pandas.read_csv migration, admitted behavior changes A1, A2, A4
# --------------------------------------------------------------------------- #


def test_duplicate_header_column_first_wins():
    lines = [f"2026-01-10,{h},8000.0,1.0" for h in HOURS]
    content = _csv("date,hour,load_mw,load_mw", lines)
    result = read_day_profiles(io.StringIO(content), origin="test")
    assert result.days[0].hourly_load_mw[0] == 8000.0


@pytest.mark.parametrize("bad_row_position", ["first", "second"])
def test_over_long_data_row_is_rejected_at_any_position(bad_row_position):
    good_lines = _rows("2026-01-10", _flat_load())
    long_row = good_lines[0] + ",extra"
    if bad_row_position == "first":
        lines = [long_row] + good_lines[1:]
    else:
        lines = [good_lines[0], long_row] + good_lines[2:]
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="cannot parse as CSV"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_unclosed_quote_is_rejected():
    good_lines = _rows("2026-01-10", _flat_load())
    good_lines[0] = good_lines[0] + ',"1'
    content = _csv("date,hour,load_mw,note", good_lines)
    with pytest.raises(ScenarioInputError):
        read_day_profiles(io.StringIO(content), origin="test")


def test_blank_header_cell_still_reports_the_missing_column():
    lines = _rows("2026-01-10", _flat_load())
    content = _csv("date,,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="hour"):
        read_day_profiles(io.StringIO(content), origin="test")


# --------------------------------------------------------------------------- #
# Hour convention: hour-ending 1-24 vs. hour-beginning 0-23 (change 9)
# --------------------------------------------------------------------------- #


def _rows_ending(date_str: str, load_values: list[float]) -> list[str]:
    """Build CSV row lines for one date, hour-ending 1 to 24, given 24 load
    values indexed 0..23 (load_values[0] is hour 1, load_values[23] is hour 24)."""
    lines = []
    for h in range(1, 25):
        lines.append(f"{date_str},{h},{load_values[h - 1]}")
    return lines


def test_hour_ending_file_is_accepted_and_maps_to_zero_based():
    loads = [100.0 + h for h in range(1, 25)]  # hour 1 -> 101, hour 24 -> 124
    content = _csv("date,hour,load_mw", _rows_ending("2026-01-10", loads))
    result = read_day_profiles(io.StringIO(content), origin="test")
    assert result.hour_convention == "hour-ending-1-24"
    assert result.days[0].hourly_load_mw[0] == 101.0
    assert result.days[0].hourly_load_mw[23] == 124.0


def test_hour_beginning_file_still_works():
    content = _csv("date,hour,load_mw", _rows("2026-01-10", _flat_load()))
    result = read_day_profiles(io.StringIO(content), origin="test")
    assert result.hour_convention == "hour-beginning-0-23"


def test_mixed_conventions_rejected():
    day_one = _rows("2026-01-10", _flat_load())
    day_two = _rows_ending("2026-01-11", _flat_load())
    content = _csv("date,hour,load_mw", day_one, day_two)
    with pytest.raises(ScenarioInputError, match="mixed hour conventions"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_hour_25_rejected():
    lines = _rows("2026-01-10", _flat_load())
    parts = lines[0].split(",")
    parts[1] = "25"
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="0..24"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_hour_negative_rejected():
    lines = _rows("2026-01-10", _flat_load())
    parts = lines[0].split(",")
    parts[1] = "-1"
    lines[0] = ",".join(parts)
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="0..24"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_duplicate_hour_still_rejected_under_hour_ending():
    lines = _rows_ending("2026-01-10", _flat_load())
    lines.append(lines[0])  # duplicate hour 1
    content = _csv("date,hour,load_mw", lines)
    with pytest.raises(ScenarioInputError, match="duplicate"):
        read_day_profiles(io.StringIO(content), origin="test")


def test_hour_convention_reported_on_the_day_profile_set():
    beginning = read_day_profiles(
        io.StringIO(_csv("date,hour,load_mw", _rows("2026-01-10", _flat_load()))),
        origin="test",
    )
    ending = read_day_profiles(
        io.StringIO(_csv("date,hour,load_mw", _rows_ending("2026-01-10", _flat_load()))),
        origin="test",
    )
    assert beginning.hour_convention == "hour-beginning-0-23"
    assert ending.hour_convention == "hour-ending-1-24"


def test_committed_examples_are_hour_beginning():
    for path in ("examples/real_winter_stress_2026.csv", "examples/synthetic_winter_stress.csv"):
        with open(path, encoding="utf-8") as f:
            result = read_day_profiles(f, origin=path)
        assert result.hour_convention == "hour-beginning-0-23"


# --------------------------------------------------------------------------- #
# Wind multiplier (change 8, D11, D12)
# --------------------------------------------------------------------------- #


def test_wind_multiplier_scales_every_hour():
    content = _csv(
        "date,hour,load_mw,wind_mw",
        _rows("2026-01-10", _flat_load(), {"wind_mw": [100.0] * 24}),
    )
    result = read_day_profiles(io.StringIO(content), origin="test", wind_multiplier=2.5)
    assert all(w == 250.0 for w in result.days[0].hourly_wind_mw)
    assert result.wind_multiplier == 2.5


def test_wind_multiplier_default_is_identity():
    content = _csv(
        "date,hour,load_mw,wind_mw",
        _rows("2026-01-10", _flat_load(), {"wind_mw": [100.0, 200.0] + [50.0] * 22}),
    )
    default = read_day_profiles(io.StringIO(content), origin="test")
    explicit = read_day_profiles(io.StringIO(content), origin="test", wind_multiplier=1.0)
    assert default.days == explicit.days


@pytest.mark.parametrize("bad", [-1.0, float("nan"), float("inf"), float("-inf")])
def test_wind_multiplier_rejects_negative_and_non_finite(bad):
    content = _csv(
        "date,hour,load_mw,wind_mw", _rows("2026-01-10", _flat_load(), {"wind_mw": [100.0] * 24})
    )
    with pytest.raises(ScenarioInputError):
        read_day_profiles(io.StringIO(content), origin="test", wind_multiplier=bad)


def test_wind_multiplier_overflow_to_inf_is_rejected():
    content = _csv(
        "date,hour,load_mw,wind_mw",
        _rows("2026-01-10", _flat_load(), {"wind_mw": [sys.float_info.max] * 24}),
    )
    with pytest.raises(ScenarioInputError, match="non-finite"):
        read_day_profiles(io.StringIO(content), origin="test", wind_multiplier=2.0)


def test_wind_multiplier_without_wind_column_is_a_no_op():
    content = _csv("date,hour,load_mw", _rows("2026-01-10", _flat_load()))
    result = read_day_profiles(io.StringIO(content), origin="test", wind_multiplier=5.0)
    assert result.has_wind is False
    assert result.days[0].hourly_wind_mw == ()
