"""Tests for the day-profile CSV reader (src/owr/scenario_input.py)."""

from __future__ import annotations

import io
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
    lines = _rows("2026-01-10", _flat_load())
    parts = lines[0].split(",")
    parts[1] = "24"
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
