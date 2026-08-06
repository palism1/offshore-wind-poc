"""Interval readings -> daily energy, correctly (docs/archive/plans/PLAN_EIA_EXTRACTOR.md Phase B2).

Pure; no file, network or database access. Uses stdlib ``zoneinfo`` and ``pandas``.

Specification, point by point:

1. Energy is an integral, never a count: ``load_mwh = Sum(load_mw * interval_hours)``.
   Nothing here assumes 288 intervals, 24 hours, or a fixed interval count.
2. Day boundary: local wall-clock (``America/New_York``). Group on
   ``reading.ts.astimezone(tz).date()``.
3. ``raw.system_load.ts`` is an absolute instant, stored UTC-normalized — never a
   local date. The daily rollup converts at read time.
4. ``local_day_hours`` subtracts two tz-aware midnights, so it returns 23.0 / 24.0
   / 25.0 automatically around a DST transition. Never hard-code 24.
5. DST is handled, not avoided: every interval is exactly its provider-supplied
   width; only the *count* of intervals per local day varies on a transition day.
6. Naive timestamps are rejected: with naive local timestamps the fall-back hour
   repeats and the 01:00-02:00 block would be double-counted or silently
   deduplicated.
7. Duplicate absolute instants are rejected, naming the timestamp.
8. Straddle rule: an interval is attributed wholly to the local date of its
   *start*. At 5- and 60-minute grain nothing straddles local midnight.
9. Incomplete days (``hours_covered`` differs from ``expected_hours`` by more than
   ``tolerance_hours``) are marked ``complete=False`` but never dropped here —
   exclusion from the p90 population and from window detection is the caller's
   decision (Phase B3), not this pure transform's.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pandas as pd

EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class IntervalReading:
    ts: datetime  # tz-aware, interval START
    load_mw: float
    interval_hours: float


@dataclass(frozen=True)
class DailyLoad:
    date: date  # LOCAL calendar date
    load_mwh: float
    hours_covered: float
    expected_hours: float  # 23 / 24 / 25, derived from the tz
    intervals: int
    complete: bool


def local_day_hours(day: date, tz: ZoneInfo = EASTERN) -> float:
    """Length of local calendar day ``day`` in hours (23.0 / 24.0 / 25.0 around DST).

    Converts both midnights to UTC before subtracting. Aware-datetime subtraction
    in Python ignores ``tzinfo`` (and skips UTC conversion) whenever both operands
    share the exact same ``tzinfo`` object — the case here, since both midnights
    are built from the same ``tz`` — so subtracting them directly would silently
    return the naive wall-clock difference (always 24h) instead of the true
    elapsed time across a DST transition. Converting to UTC first sidesteps that.
    """
    start = datetime.combine(day, time(0), tzinfo=tz).astimezone(UTC)
    end = datetime.combine(day + timedelta(days=1), time(0), tzinfo=tz).astimezone(UTC)
    return (end - start).total_seconds() / 3600.0


def daily_loads_from_readings(
    readings: list[IntervalReading],
    *,
    tz: ZoneInfo = EASTERN,
    tolerance_hours: float = 0.01,
) -> list[DailyLoad]:
    """Integrate interval readings into one ``DailyLoad`` per local calendar date.

    Sorts by timestamp before integrating; does not assume input order. Rejects
    naive timestamps and duplicate absolute instants.
    """
    if not readings:
        return []

    for r in readings:
        if r.ts.tzinfo is None:
            raise ValueError(f"naive timestamp not allowed: {r.ts.isoformat()}")

    ordered = sorted(readings, key=lambda r: r.ts)

    seen: set[datetime] = set()
    for r in ordered:
        if r.ts in seen:
            raise ValueError(f"duplicate absolute instant: {r.ts.isoformat()}")
        seen.add(r.ts)

    by_date: dict[date, list[IntervalReading]] = {}
    for r in ordered:
        local_date = r.ts.astimezone(tz).date()
        by_date.setdefault(local_date, []).append(r)

    results: list[DailyLoad] = []
    for d in sorted(by_date):
        group = by_date[d]
        load_mwh = sum(r.load_mw * r.interval_hours for r in group)
        hours_covered = sum(r.interval_hours for r in group)
        expected_hours = local_day_hours(d, tz)
        complete = abs(hours_covered - expected_hours) <= tolerance_hours
        results.append(
            DailyLoad(
                date=d,
                load_mwh=load_mwh,
                hours_covered=hours_covered,
                expected_hours=expected_hours,
                intervals=len(group),
                complete=complete,
            )
        )
    return results


DAILY_CORE_COLUMNS: tuple[str, ...] = (
    "date", "load_mwh", "hours_covered", "expected_hours", "intervals", "complete",
)


def daily_frame(loads: Sequence[DailyLoad]) -> pd.DataFrame:
    """The Component 2 daily contract as a frame, one row per local calendar date.

    ``date`` holds ``datetime.date`` objects in an ``object`` column, never
    ``datetime64``. The engine does calendar arithmetic with ``timedelta(days=1)``,
    formats with ``date.isoformat()``, and uses dates as dictionary keys; a
    ``Timestamp`` changes all three.
    """
    return pd.DataFrame(
        {
            "date": pd.Series([d.date for d in loads], dtype="object"),
            "load_mwh": pd.Series([d.load_mwh for d in loads], dtype="float64"),
            "hours_covered": pd.Series([d.hours_covered for d in loads], dtype="float64"),
            "expected_hours": pd.Series([d.expected_hours for d in loads], dtype="float64"),
            "intervals": pd.Series([d.intervals for d in loads], dtype="int64"),
            "complete": pd.Series([d.complete for d in loads], dtype="bool"),
        },
        columns=list(DAILY_CORE_COLUMNS),
    )
