"""Day-profile CSV reader for the simulator CLI.

**Provisional format, not a stable interface.** Nothing in ``db/migrations/001_init.sql``
carries these columns: ``features.daily_load`` is daily-grain with different names
(``load_mwh``, ``season``, ``demand_percentile``), the hourly tables are
``raw.hourly_load`` / ``raw.hourly_wind`` keyed on ``(source, zone, ts)``, and
``docs/PLAN.md`` Phase 2 defines no CSV export step at all. This is what the
simulator CLI reads today, not a contract with ETL. When Phase 2 lands, either this
reader gains a second layout or ETL grows an export that matches this one; whoever
does that work owns reconciling the two.

Format: one row per hour, header required, column order irrelevant, names
case-insensitive. Blank lines and lines starting with ``#`` are skipped, so a file
can carry its own provenance banner.

Columns: ``date`` (YYYY-MM-DD, required), ``hour`` (1-24 hour-ending, or 0-23
hour-beginning; required), ``load_mw`` (required), ``wind_mw`` (optional),
``demand_percentile`` (optional, constant per date), ``wind_forecast_frac``
(optional, constant per date).

``hour`` accepts either convention (change 9, 2026-08-05 to 08-06 Discord). The
convention is decided once per file, from the set of raw hour values the whole
file carries: a file that contains ``0`` (and never ``24``) is hour-beginning,
and the internal 0-based index equals the raw hour. A file that contains ``24``
(and never ``0``) is hour-ending, and the internal index is ``hour - 1``; hour
24 maps to internal index 23 and stays on the same calendar date, never rolling
over. A file that carries both 0 and 24 is rejected: the two conventions cannot
coexist in one file. ``DayProfileSet.hour_convention`` reports which one a
parsed file used.

``demand_percentile`` absent is derived as the empirical CDF of the day's energy
within the supplied series: ``count(load_mwh <= load_mwh(d)) / n_days``. Defaulting
to 0.0 would make ``priority()`` zero for every day, which hands every day the full
80% energy-budget cap (see ``owr.budget.daily_budget``); the seasonal-denominator
definition in the ``DayProfile`` docstring is not usable, since ``docs/HANDOFF.md``
records the seasonal denominators as underivable and forbids hard-coding them.
``wind_forecast_frac`` absent defaults to 0.0 (the ``DayProfile`` default): it
cannot be derived without a wind nameplate capacity, which is not an input.

Parsed by ``pandas.read_csv`` with ``dtype=str`` and ``na_filter=False``, so every
cell reaches the validation below as the token the file carried. Three behaviors
differ from the retired ``csv.DictReader``:

* A data row with more fields than the header is rejected, at any row position.
  ``csv.DictReader`` accepted it and stored the extra field under the ``None`` key.
* A file with an unclosed quoted field is rejected. ``csv.DictReader`` swallowed the
  rest of the file into one field.
* A header that repeats a column name resolves to the first occurrence, because
  pandas renames the second to ``name.1``. ``csv.DictReader`` kept the last. Neither
  reader raises.

A blank header cell is named ``Unnamed: <position>`` by pandas, where
``csv.DictReader`` named it ``""``. Neither name is a required or optional column, so
both readers report the same missing-column error for such a header.
"""

from __future__ import annotations

import io
import math
import warnings as warnings_mod
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TextIO

import pandas as pd

from owr.models import HOURS_PER_DAY, DayProfile

REQUIRED_COLUMNS = ("date", "hour", "load_mw")
OPTIONAL_COLUMNS = ("wind_mw", "demand_percentile", "wind_forecast_frac")
PER_DATE_COLUMNS = ("demand_percentile", "wind_forecast_frac")


class ScenarioInputError(ValueError):
    """Raised for any malformed or invalid day-profile CSV input."""


@dataclass(frozen=True)
class DayProfileSet:
    days: list[DayProfile]
    demand_percentile_source: str  # "file" | "derived-rank"
    wind_forecast_frac_source: str  # "file" | "default-zero"
    has_wind: bool
    warnings: tuple[str, ...]
    hour_convention: str  # "hour-ending-1-24" | "hour-beginning-0-23"
    wind_multiplier: float


def _err(origin: str, lineno: int | None, message: str) -> ScenarioInputError:
    where = f"{origin}:{lineno}" if lineno is not None else origin
    return ScenarioInputError(f"{where}: {message}")


def _parse_finite_float(value: str, *, origin: str, lineno: int, column: str) -> float:
    """Parse a float and reject non-finite values.

    ``float()`` raises on "abc" but accepts "nan", "NaN", "inf", "-inf", "+inf" and
    "Infinity", so a bare ``except ValueError`` around ``float(value)`` lets every one
    of those through. Reject anything failing ``math.isfinite`` explicitly: nothing
    downstream catches it, and the engine's own guards only trap non-finite values
    where the check happens to be written as a positive range (verified against
    source: ``StorageAsset(total_mwh=nan)`` is accepted because ``models.py`` tests
    ``<= 0``, which is False for NaN).
    """
    try:
        parsed = float(value)
    except ValueError as exc:
        raise _err(origin, lineno, f"column {column!r}: not a number: {value!r}") from exc
    if not math.isfinite(parsed):
        raise _err(origin, lineno, f"column {column!r}: must be a finite number, got {value!r}")
    return parsed


def read_day_profiles(
    stream: TextIO, *, origin: str, wind_multiplier: float = 1.0
) -> DayProfileSet:
    """Read and validate a day-profile CSV, returning a sorted, validated DayProfileSet.

    ``origin`` is a label used in error messages (e.g. the file path or "<stdin>").

    ``wind_multiplier`` scales every ``wind_mw`` cell after it is parsed (D11, D12:
    the multiplier applies once, at the simulator input boundary; it never touches
    ``wind_forecast_frac``, a fraction of nameplate capacity that scaling has no
    physical meaning for). A non-finite or negative multiplier raises
    ``ScenarioInputError`` immediately. With no ``wind_mw`` column, the multiplier
    has no effect: ``has_wind`` stays False regardless of its value.

    OPEN team question (``wind_multiplier_range``): Component 1 User Inputs lists
    the field's validation range as ``@`` and calls it whole-number; implemented
    here as any finite value ``>= 0.0``, default 1.0.

    Note on line-number bookkeeping: pre-filtering blank/comment lines before handing
    them to csv.DictReader desynchronizes the line-number map from the reader if a
    field contains a newline inside quotes, since one CSV record would then span two
    source lines. The schema here is dates, integers and floats, so a quoted
    multi-line field is not a realistic input; the line numbers are diagnostic aids,
    not a parsing contract, and this edge case is left unhandled deliberately.
    """
    if not math.isfinite(wind_multiplier) or wind_multiplier < 0:
        raise _err(
            origin,
            None,
            f"wind_multiplier must be finite and >= 0, got {wind_multiplier!r}",
        )
    filtered = [
        (n, line)
        for n, line in enumerate(stream, 1)
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not filtered:
        raise _err(origin, None, "no data rows (file is empty or all comments/blank)")

    linenos = [n for n, _ in filtered]
    lines = [line for _, line in filtered]

    try:
        with warnings_mod.catch_warnings():
            warnings_mod.simplefilter("error", pd.errors.ParserWarning)
            frame = pd.read_csv(
                io.StringIO("".join(lines)),
                dtype=str,
                na_filter=False,
                index_col=False,
            )
    except (pd.errors.ParserError, pd.errors.EmptyDataError, pd.errors.ParserWarning) as exc:
        raise _err(origin, None, f"cannot parse as CSV: {exc}") from exc
    if frame.columns.empty:
        raise _err(origin, None, "missing header row")
    fieldmap = {str(name).strip().lower(): str(name) for name in frame.columns}

    missing = [c for c in REQUIRED_COLUMNS if c not in fieldmap]
    if missing:
        raise _err(origin, None, f"header missing required column(s): {', '.join(missing)}")

    has_wind = "wind_mw" in fieldmap
    has_demand_percentile = "demand_percentile" in fieldmap
    has_wind_forecast_frac = "wind_forecast_frac" in fieldmap

    warnings: list[str] = []

    # rows[i] corresponds to data line linenos[i + 1] (line 1 was the header).
    raw_rows = frame.to_dict("records")
    if not raw_rows:
        raise _err(origin, None, "no data rows")

    # raw hour -> value, per date; and per-date scalar tracking. Keyed on the raw
    # hour from the file (0-23 or 1-24) until the convention is known.
    raw_by_date: dict[date, dict[int, dict[str, float]]] = {}
    per_date_scalar: dict[date, dict[str, float]] = {}
    order: list[date] = []
    hours_seen: set[int] = set()

    for i, row in enumerate(raw_rows):
        lineno = linenos[i + 1]

        raw_date = (row.get(fieldmap["date"]) or "").strip()
        if not raw_date:
            raise _err(origin, lineno, "column 'date': required, but cell is blank")
        try:
            d = date.fromisoformat(raw_date)
        except ValueError as exc:
            raise _err(origin, lineno, f"column 'date': cannot parse {raw_date!r}") from exc

        raw_hour = (row.get(fieldmap["hour"]) or "").strip()
        if not raw_hour:
            raise _err(origin, lineno, "column 'hour': required, but cell is blank")
        try:
            hour = int(raw_hour)
        except ValueError as exc:
            raise _err(origin, lineno, f"column 'hour': not an integer: {raw_hour!r}") from exc
        if not 0 <= hour <= 24:
            raise _err(origin, lineno, f"column 'hour': must be in 0..24, got {hour}")
        hours_seen.add(hour)

        raw_load = (row.get(fieldmap["load_mw"]) or "").strip()
        if not raw_load:
            raise _err(origin, lineno, "column 'load_mw': required, but cell is blank")
        load_mw = _parse_finite_float(raw_load, origin=origin, lineno=lineno, column="load_mw")

        if has_wind:
            raw_wind = (row.get(fieldmap["wind_mw"]) or "").strip()
            wind_mw = (
                0.0
                if not raw_wind
                else _parse_finite_float(raw_wind, origin=origin, lineno=lineno, column="wind_mw")
            )
            wind_mw *= wind_multiplier
            if not math.isfinite(wind_mw):
                raise _err(
                    origin,
                    lineno,
                    f"column 'wind_mw': value overflows to non-finite after applying "
                    f"wind_multiplier={wind_multiplier!r}",
                )
        else:
            wind_mw = None

        if d not in raw_by_date:
            raw_by_date[d] = {}
            per_date_scalar[d] = {}
            order.append(d)
        if hour in raw_by_date[d]:
            raise _err(origin, lineno, f"duplicate (date, hour) pair: ({d.isoformat()}, {hour})")
        raw_by_date[d][hour] = {"load_mw": load_mw, "wind_mw": wind_mw}

        for col, present in (
            ("demand_percentile", has_demand_percentile),
            ("wind_forecast_frac", has_wind_forecast_frac),
        ):
            if not present:
                continue
            raw_val = (row.get(fieldmap[col]) or "").strip()
            if not raw_val:
                raise _err(
                    origin,
                    lineno,
                    f"column {col!r}: blank cell. This column is constant per date; "
                    f"omit the column entirely to get the documented default or derivation "
                    f"rather than leaving individual cells blank.",
                )
            val = _parse_finite_float(raw_val, origin=origin, lineno=lineno, column=col)
            existing = per_date_scalar[d].get(col)
            if existing is not None and existing != val:
                raise _err(
                    origin,
                    lineno,
                    f"column {col!r}: varies within date {d.isoformat()} "
                    f"({existing!r} vs {val!r}); it must be constant per date",
                )
            per_date_scalar[d][col] = val

    # Decide the hour convention once, from the set of raw hour values the whole
    # file carries (rule 3, change 9). The convention is per file, not per date.
    has_hour_0 = 0 in hours_seen
    has_hour_24 = 24 in hours_seen
    if has_hour_0 and has_hour_24:
        raise _err(
            origin, None, "mixed hour conventions: the file carries both hour 0 and hour 24"
        )
    if has_hour_24:
        hour_convention = "hour-ending-1-24"

        def _to_internal(raw: int) -> int:
            return raw - 1

    elif has_hour_0:
        hour_convention = "hour-beginning-0-23"

        def _to_internal(raw: int) -> int:
            return raw

    else:
        # Unreachable for a valid file: the reader requires exactly 24 rows per
        # date (checked below) and 24 distinct values drawn from 0..24 must
        # contain 0 or 24. This guards a file that would fail that check.
        raise _err(
            origin,
            None,
            "cannot determine hour convention: no row carries hour 0 or hour 24",
        )

    by_date: dict[date, dict[int, dict[str, float]]] = {
        d: {_to_internal(raw): value for raw, value in hours.items()}
        for d, hours in raw_by_date.items()
    }

    # Sort dates for a stable, order-independent result.
    sorted_dates = sorted(order)

    for d in sorted_dates:
        hours_present = sorted(by_date[d].keys())
        if len(hours_present) != HOURS_PER_DAY:
            raise _err(
                origin,
                None,
                f"date {d.isoformat()}: expected exactly {HOURS_PER_DAY} rows, "
                f"got {len(hours_present)}",
            )

    for prev_d, next_d in zip(sorted_dates, sorted_dates[1:], strict=False):
        if next_d - prev_d != timedelta(days=1):
            raise _err(
                origin,
                None,
                f"dates are not consecutive: {prev_d.isoformat()} is followed by "
                f"{next_d.isoformat()}, a gap of {(next_d - prev_d).days} day(s)",
            )

    # Derive demand_percentile if the column was absent: empirical rank of daily
    # energy within the series.
    daily_loads: dict[date, float] = {
        d: sum(by_date[d][h]["load_mw"] for h in range(HOURS_PER_DAY)) for d in sorted_dates
    }
    n_days = len(sorted_dates)

    if has_demand_percentile:
        demand_percentile_source = "file"
    else:
        demand_percentile_source = "derived-rank"
        warnings.append(
            "demand_percentile column absent: derived as the empirical rank of each "
            "day's energy within the supplied series (count(load_mwh <= load_mwh(d)) "
            "/ n_days)."
        )
        for d in sorted_dates:
            count_le = sum(1 for other in daily_loads.values() if other <= daily_loads[d])
            per_date_scalar[d]["demand_percentile"] = count_le / n_days

    if has_wind_forecast_frac:
        wind_forecast_frac_source = "file"
    else:
        wind_forecast_frac_source = "default-zero"
        warnings.append(
            "wind_forecast_frac column absent: defaulted to 0.0 for every date "
            "(cannot be derived without a wind nameplate capacity)."
        )
        for d in sorted_dates:
            per_date_scalar[d]["wind_forecast_frac"] = 0.0

    days: list[DayProfile] = []
    for d in sorted_dates:
        hourly_load = tuple(by_date[d][h]["load_mw"] for h in range(HOURS_PER_DAY))
        if has_wind:
            hourly_wind: tuple[float, ...] = tuple(
                by_date[d][h]["wind_mw"] for h in range(HOURS_PER_DAY)
            )
        else:
            hourly_wind = ()
        days.append(
            DayProfile(
                date=d,
                hourly_load_mw=hourly_load,
                hourly_wind_mw=hourly_wind,
                demand_percentile=per_date_scalar[d]["demand_percentile"],
                wind_forecast_frac=per_date_scalar[d]["wind_forecast_frac"],
            )
        )

    return DayProfileSet(
        days=days,
        demand_percentile_source=demand_percentile_source,
        wind_forecast_frac_source=wind_forecast_frac_source,
        has_wind=has_wind,
        warnings=tuple(warnings),
        hour_convention=hour_convention,
        wind_multiplier=wind_multiplier,
    )
