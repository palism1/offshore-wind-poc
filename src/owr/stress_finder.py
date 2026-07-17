"""Stress-window detection (Architecture Step 2).

Find runs of X or more consecutive days whose demand sits above a severity
percentile. Pure function over a daily series; no I/O.
"""

from __future__ import annotations

from owr.models import DayProfile, StressWindow


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


def find_stress_windows(
    days: list[DayProfile],
    severity_percentile: float,
    min_window_days: int,
) -> list[StressWindow]:
    """Return every maximal run of >= min_window_days consecutive stressed days.

    A day is "stressed" if its daily energy sits at or above the severity-percentile
    threshold of the whole series' daily energy.
    """
    if min_window_days < 1:
        raise ValueError("min_window_days must be >= 1")
    if not days:
        return []

    loads = [d.load_mwh for d in days]
    threshold = percentile_threshold(loads, severity_percentile)
    stressed = [d.load_mwh >= threshold for d in days]

    windows: list[StressWindow] = []
    run_start: int | None = None
    for i, is_stressed in enumerate(stressed):
        if is_stressed and run_start is None:
            run_start = i
        is_last = i == len(stressed) - 1
        if run_start is not None and (not is_stressed or is_last):
            run_end = i if is_stressed and is_last else i - 1
            length = run_end - run_start + 1
            if length >= min_window_days:
                windows.append(
                    StressWindow(
                        start=days[run_start].date,
                        end=days[run_end].date,
                        days=length,
                    )
                )
            run_start = None
    return windows
