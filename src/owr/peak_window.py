"""Rolling-window peak-load finder (Architecture Step, Mitchell 2026-07-28 23:12).

Identification only: locates the highest-summing rolling window of consecutive
hours in a day and returns it. Nothing here applies a peak-shaving or
ramp-reduction formula to the window it finds — those formulas are unspecified
(see docs/HANDOFF.md, the peak-window block) and out of scope for this module.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta

from owr.models import HOURS_PER_DAY, DayProfile, PeakWindow, WrapConvention


def find_peak_window(
    hourly_load_mw: Sequence[float],
    *,
    window_hours: int,
    next_hours: Sequence[float] = (),
) -> PeakWindow:
    """Return the highest-summing rolling window of `window_hours` consecutive
    hours, scanning `hourly_load_mw` (exactly one day, 24 values) optionally
    extended by `next_hours` (values from the following day, used for look-ahead).

    Ties break to the earliest start index. This is a guarantee of the
    implementation (``max(..., key=...)`` over an ordered enumeration keeps the
    first maximum), stated here because flat days are all ties.

    Negative loads are allowed — the max is still well defined and rejecting them
    would be a modeling opinion this function does not hold.
    """
    if len(hourly_load_mw) != HOURS_PER_DAY:
        raise ValueError(f"hourly_load_mw must have {HOURS_PER_DAY} values")
    if window_hours < 1 or window_hours > HOURS_PER_DAY:
        raise ValueError(f"window_hours must be in 1..{HOURS_PER_DAY}")
    if len(next_hours) > HOURS_PER_DAY:
        raise ValueError(f"next_hours must have at most {HOURS_PER_DAY} values")

    series = list(hourly_load_mw) + list(next_hours)
    candidates = [s for s in range(HOURS_PER_DAY) if s + window_hours <= len(series)]

    best_start = max(candidates, key=lambda s: sum(series[s : s + window_hours]))
    window_loads = tuple(series[best_start : best_start + window_hours])
    clock_hours = tuple((best_start + k) % HOURS_PER_DAY for k in range(window_hours))
    wrapped = best_start + window_hours > HOURS_PER_DAY

    return PeakWindow(
        start_hour=best_start,
        clock_hours=clock_hours,
        load_mw=window_loads,
        wrapped=wrapped,
        candidates_considered=len(candidates),
    )


def find_peak_window_for_day(
    day: DayProfile,
    next_day: DayProfile | None = None,
    *,
    window_hours: int,
    wrap: WrapConvention,
) -> PeakWindow:
    """Resolve the look-ahead hours for `day` per `wrap`, then delegate to
    `find_peak_window`.

    `next_hours` is empty when `wrap is STOP_AT_MIDNIGHT`, when `next_day is
    None`, or when `next_day.date` is not `day.date + 1 day` (a non-adjacent day
    is not the physical successor). The last day of a series therefore reports
    `candidates_considered == 22` (for window_hours=3) instead of 23 — that is
    missing data, not a convention, and it is visible in the returned value
    rather than silently swallowed.
    """
    next_hours: tuple[float, ...] = ()
    if (
        wrap.lookahead_hours > 0
        and next_day is not None
        and next_day.date == day.date + timedelta(days=1)
    ):
        next_hours = next_day.hourly_load_mw[: wrap.lookahead_hours]

    return find_peak_window(day.hourly_load_mw, window_hours=window_hours, next_hours=next_hours)


def find_peak_windows_over_days(
    days: Sequence[DayProfile],
    *,
    window_hours: int,
    wrap: WrapConvention,
) -> list[tuple[date, PeakWindow]]:
    """Map `find_peak_window_for_day` over a series of days, in input order,
    passing each day's chronological successor (``days[i + 1]``) as `next_day`
    for every day but the last."""
    results: list[tuple[date, PeakWindow]] = []
    for i, day in enumerate(days):
        next_day = days[i + 1] if i + 1 < len(days) else None
        window = find_peak_window_for_day(day, next_day, window_hours=window_hours, wrap=wrap)
        results.append((day.date, window))
    return results
