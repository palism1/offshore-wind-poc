"""Stress-window detection (Architecture Step 2).

Find runs of X or more consecutive days whose demand sits above a severity
percentile. Pure function over a daily series; no I/O.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

from owr.models import DailyLoadLike, StressWindow


def percentile_threshold(values: list[float], percentile: float) -> float:
    """Linear-interpolation percentile (matches numpy's default 'linear' method) so
    the ETL-side and engine-side percentiles agree without a numpy dependency.

    percentile is a fraction in [0, 1].
    """
    if not values:
        raise ValueError("values must be non-empty")
    if not 0.0 <= percentile <= 1.0:
        raise ValueError("percentile must be in [0, 1]")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = percentile * (len(ordered) - 1)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def find_stress_windows_at_threshold(
    days: Sequence[DailyLoadLike],
    threshold: float,
    min_window_days: int,
) -> list[StressWindow]:
    """Runs of >= min_window_days consecutive CALENDAR days at or above `threshold`.

    Adjacency is by date, not by list position: a run ends when the next
    element's date is not exactly one day after the current element's. A gap in
    the series — a missing or excluded day — therefore splits a run instead of
    merging across it.

    Input is expected sorted ascending by date. It is deliberately NOT sorted
    here; an out-of-order series yields shorter runs rather than silently merged
    ones.
    """
    if min_window_days < 1:
        raise ValueError("min_window_days must be >= 1")
    if not days:
        return []

    stressed = [d.load_mwh >= threshold for d in days]

    windows: list[StressWindow] = []
    run_start: int | None = None

    for i in range(len(days)):
        if stressed[i]:
            if run_start is None:
                run_start = i
            elif days[i].date != days[i - 1].date + timedelta(days=1):
                # Gap: close the run ending at i-1, then open a new one at i.
                _emit(windows, days, run_start, i - 1, min_window_days)
                run_start = i
        elif run_start is not None:
            _emit(windows, days, run_start, i - 1, min_window_days)
            run_start = None

    if run_start is not None:
        _emit(windows, days, run_start, len(days) - 1, min_window_days)

    return windows


def _emit(
    windows: list[StressWindow],
    days: Sequence[DailyLoadLike],
    run_start: int,
    run_end: int,
    min_window_days: int,
) -> None:
    length = run_end - run_start + 1
    if length >= min_window_days:
        windows.append(
            StressWindow(start=days[run_start].date, end=days[run_end].date, days=length)
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
    return find_stress_windows_at_threshold(days, threshold, min_window_days)
