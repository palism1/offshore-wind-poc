"""Stress-window detection (Architecture Step 2).

Find runs of X or more consecutive days whose demand sits above a severity
percentile. Pure function over a daily series; no I/O.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import timedelta

import numpy as np

from owr.config import Config
from owr.models import (
    DailyLoadLike,
    DailyPercentileLike,
    DayProfile,
    HourlyLoadLike,
    PercentileRounding,
    StressWindow,
)


def percentile_threshold(values: Sequence[float], percentile: float) -> float:
    """Linear-interpolation percentile, computed by ``numpy.quantile`` with the default
    ``'linear'`` method. ``percentile`` is a fraction in [0, 1], which is what
    ``numpy.quantile`` takes, so no rescale to 0..100 is needed.

    The result can differ from a hand-written ``lo + (hi - lo) * frac`` by a few units
    in the last place. NumPy uses that same form when ``frac`` is below 0.5, so those
    results are bit identical; at or above 0.5 it uses ``hi - (hi - lo) * (1 - frac)``,
    which rounds differently. Measured 2026-08-05 over 20000 random series: 471 of
    20000 results differ, worst relative difference 1.08e-15.

    **A stressed-day comparison cannot flip.** The difference between the two forms
    comes from rounding the product ``(hi - lo) * frac``, so it appears only when the
    gap ``hi - lo`` is wide enough for that product to round. The threshold lies between
    two adjacent values of the sorted population, so no other daily total lies between
    them, and the nearest candidate for a flip is ``lo`` itself, at distance
    ``(hi - lo) * frac``, which is at least half the gap. A flip therefore needs a gap
    of a few units in the last place, and at that width both products are exactly
    representable and both forms return the same value. The two conditions exclude each
    other. Confirmed 2026-08-05 by 200000 adversarial trials with zero stress-set flips.
    """
    if len(values) == 0:
        raise ValueError("values must be non-empty")
    if not 0.0 <= percentile <= 1.0:
        raise ValueError("percentile must be in [0, 1]")
    return float(np.quantile(np.asarray(values, dtype=float), percentile, method="linear"))


def _rank_fraction(population_mwh: Sequence[float], value_mwh: float) -> float:
    if not population_mwh:
        raise ValueError("percentile_rank_percent: population_mwh is empty")
    n = len(population_mwh)
    return sum(1 for p in population_mwh if p <= value_mwh) / n


def percentile_rank_percent(population_mwh: Sequence[float], value_mwh: float) -> float:
    """Empirical rank of one day total against a population, in percent 0 to 100.

    ``rank = count(p <= value) / len(population) * 100``. Ties take the highest
    rank. Raises ``ValueError`` on an empty population. Mirrors
    ``owr.etl.demo_profile.percentile_ranks``; the drift guard is
    ``tests/test_stress_finder.py::test_percentile_rank_matches_demo_profile``.
    """
    return _rank_fraction(population_mwh, value_mwh) * 100.0


def with_demand_percentile(
    days: Sequence[DayProfile],
    *,
    population_mwh: Sequence[float] | None = None,
) -> list[DayProfile]:
    """Return copies of ``days`` carrying ``demand_percentile`` as a fraction 0 to 1.

    Component 3 attaches the percentile at Stress Event Detection, not at input
    parsing. ``population_mwh`` defaults to the day totals of ``days`` itself,
    which is the single-file fallback. The pooled five-winter population reaches
    this function through its caller. Never mutates its input, mirroring
    ``with_peak_hourly_load``.
    """
    if population_mwh is None:
        population_mwh = [d.load_mwh for d in days]
    return [replace(d, demand_percentile=_rank_fraction(population_mwh, d.load_mwh)) for d in days]


def _runs(
    stressed: Sequence[bool],
    dated: Sequence[DailyLoadLike] | Sequence[DailyPercentileLike],
    min_window_days: int,
    make_window: Callable[[int, int, int], StressWindow],
) -> list[StressWindow]:
    """Shared run-splitting loop for both detection paths (Phase 7).

    Adjacency is by date, not by list position: a run ends when the next
    element's date is not exactly one day after the current element's. A gap in
    the series — a missing or excluded day — therefore splits a run instead of
    merging across it. ``dated`` is expected sorted ascending by date; it is
    deliberately NOT sorted here, so an out-of-order series yields shorter runs
    rather than silently merged ones. ``make_window(run_start, run_end,
    length)`` builds the emitted ``StressWindow``; the two public functions
    supply distinct closures that fill in ``threshold_mwh`` /
    ``severity_percentile`` differently.
    """
    windows: list[StressWindow] = []
    run_start: int | None = None

    def emit(run_start: int, run_end: int) -> None:
        length = run_end - run_start + 1
        if length >= min_window_days:
            windows.append(make_window(run_start, run_end, length))

    for i in range(len(dated)):
        if stressed[i]:
            if run_start is None:
                run_start = i
            elif dated[i].date != dated[i - 1].date + timedelta(days=1):
                # Gap: close the run ending at i-1, then open a new one at i.
                emit(run_start, i - 1)
                run_start = i
        elif run_start is not None:
            emit(run_start, i - 1)
            run_start = None

    if run_start is not None:
        emit(run_start, len(dated) - 1)

    return windows


def find_stress_windows_at_threshold(
    days: Sequence[DailyLoadLike],
    threshold: float,
    min_window_days: int,
    *,
    severity_percentile: float | None = None,
) -> list[StressWindow]:
    """Runs of >= min_window_days consecutive CALENDAR days at or above `threshold`.

    Adjacency and sort expectations: see ``_runs``.

    ``severity_percentile`` is recorded on every window this call emits and is
    never used to compute anything. Callers that derived ``threshold`` from a
    percentile pass it so the window can report both halves of the source's
    ``load_percentile_threshold`` field. Callers that chose a threshold directly
    leave it ``None``.
    """
    if min_window_days < 1:
        raise ValueError("min_window_days must be >= 1")
    if not days:
        return []

    stressed = [d.load_mwh >= threshold for d in days]

    def make_window(run_start: int, run_end: int, length: int) -> StressWindow:
        return StressWindow(
            start=days[run_start].date,
            end=days[run_end].date,
            days=length,
            threshold_mwh=threshold,
            severity_percentile=severity_percentile,
        )

    return _runs(stressed, days, min_window_days, make_window)


def integer_percentile_from_fraction(fraction: float, rounding: PercentileRounding) -> int:
    """Component 3: "The comparison should be 90.0 and current day's percentile as
    an integer". Takes a FRACTION in [0, 1] and returns an integer 0 to 100.

    Raises ``ValueError`` when ``fraction`` is above ``1.0 + 1e-9``. The ETL
    frame carries ``load_percentile`` in percent (D3), so a caller that forgets
    the divide-by-100 would otherwise compute e.g. 9407 and mark every day
    stressed (review finding B4). The guard turns that into a raise at the
    first row.

    The inner round to 9 decimals is required, not cosmetic: ``0.29 * 100.0``
    is ``28.999999999999996`` in IEEE 754 double, so a bare floor returns 28
    for a day that is exactly at the 29th percentile.

    OPEN team question (``stress_percentile_rounding``). See
    ``config.PercentileRounding``.
    """
    if fraction > 1.0 + 1e-9:
        raise ValueError(
            f"fraction must be a fraction in [0, 1], got {fraction!r}; "
            "a percent value divided by 100 was likely expected"
        )
    percent = round(fraction * 100.0, 9)
    if rounding is PercentileRounding.FLOOR:
        return math.floor(percent)
    return round(percent)


def find_stress_windows_at_percentile(
    days: Sequence[DailyPercentileLike],
    min_window_days: int,
    *,
    percentile_floor_percent: float = 90.0,
    rounding: PercentileRounding = PercentileRounding.FLOOR,
) -> list[StressWindow]:
    """Runs of >= min_window_days consecutive CALENDAR days whose integer percentile
    is at or above ``percentile_floor_percent``.

    Component 3: "A stress event begins when percentile of daily load is >= 90".

    Additive to ``find_stress_windows_at_threshold``, which stays the ETL's MWh
    comparison path and keeps its own tests. ``StressWindow.threshold_mwh``
    stays ``None`` here (see the ``models.StressWindow`` docstring);
    ``severity_percentile`` receives ``percentile_floor_percent / 100.0``, so
    the field keeps its documented 0 to 1 range. Adjacency and sort
    expectations: see ``_runs``.
    """
    if min_window_days < 1:
        raise ValueError("min_window_days must be >= 1")
    if not days:
        return []

    stressed = [
        integer_percentile_from_fraction(d.demand_percentile, rounding) >= percentile_floor_percent
        for d in days
    ]

    def make_window(run_start: int, run_end: int, length: int) -> StressWindow:
        return StressWindow(
            start=days[run_start].date,
            end=days[run_end].date,
            days=length,
            threshold_mwh=None,
            severity_percentile=percentile_floor_percent / 100.0,
        )

    return _runs(stressed, days, min_window_days, make_window)


def find_stress_windows_for_config(
    days: Sequence[DailyPercentileLike], config: Config
) -> list[StressWindow]:
    """``find_stress_windows_at_percentile`` called with one ``Config``'s fields,
    including D1's float guard (``round(x * 100.0, 9)``).

    This is the exact call ``cli._run`` and ``api.create_run`` made before this
    function existed, now centralized so no caller repeats the float-trap guard
    or the argument list by hand.
    """
    return find_stress_windows_at_percentile(
        days,
        config.default_min_stress_window_days,
        percentile_floor_percent=round(config.default_severity_percentile * 100.0, 9),
        rounding=config.stress_percentile_rounding,
    )


def find_stress_windows(
    days: Sequence[DailyLoadLike],
    severity_percentile: float,
    min_window_days: int,
) -> list[StressWindow]:
    """Return every maximal run of >= min_window_days consecutive stressed days.

    A day is "stressed" if its daily energy sits at or above the severity-percentile
    threshold of the whole series' daily energy.
    """
    if not days:
        if min_window_days < 1:
            raise ValueError("min_window_days must be >= 1")
        return []
    threshold = percentile_threshold([d.load_mwh for d in days], severity_percentile)
    return find_stress_windows_at_threshold(
        days, threshold, min_window_days, severity_percentile=severity_percentile
    )


def with_peak_hourly_load(
    windows: Sequence[StressWindow],
    days: Sequence[HourlyLoadLike],
) -> list[StressWindow]:
    """Return copies of ``windows`` with ``peak_hourly_load_mw`` filled in.

    Implements the Component 3 ``peak_hourly_load`` output field (Unit "MW?",
    Description "@") of
    ``docs/source/2026-08-05_Software_Architecture_Documentation.md``. The value is
    the maximum hourly load in MW over every hour of every day from ``start`` to
    ``end`` inclusive.

    A separate function, and not part of ``find_stress_windows``: detection takes
    ``DailyLoadLike``, which has no hourly series, and widening that protocol would
    break the ETL path, whose points are daily totals. A caller that holds
    ``DayProfile`` objects calls this straight after detection. A caller that does
    not leaves the field ``None``.

    Never mutates its input. The Architecture doc's Global Interface Contract says
    a component shall never modify another component's output.

    Raises ``ValueError`` when a window covers a date absent from ``days``, or a
    date whose hourly series is empty.
    """
    by_date = {d.date: tuple(d.hourly_load_mw) for d in days}
    out: list[StressWindow] = []
    for w in windows:
        peak: float | None = None
        day = w.start
        while day <= w.end:
            hours = by_date.get(day)
            if hours is None:
                raise ValueError(
                    f"window {w.start} .. {w.end} covers a date absent from days: {day}"
                )
            if not hours:
                raise ValueError(f"date {day} carries an empty hourly load series")
            day_peak = max(hours)
            peak = day_peak if peak is None else max(peak, day_peak)
            day += timedelta(days=1)
        out.append(replace(w, peak_hourly_load_mw=peak))
    return out
