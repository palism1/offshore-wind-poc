"""Real-data bridge: interval readings -> day-profile CSV (docs/PLAN_REAL_DEMO_BRIDGE.md).

Pure. No file access, no network, no database.

This module is disposable. ``docs/PLAN_SCENARIO_PROFILE_FORMAT.md`` section b.3
makes ``ts`` and ``interval_minutes`` required columns of the day-profile format;
when that redesign lands it supersedes this module and its planned
``hourly.py`` / ``profile_csv.py`` replacements. Retire this module in the same
change (see ``docs/HANDOFF.md``).

Two functions bridge ``owr.etl.daily`` (interval readings) to
``owr.scenario_input`` (the simulator's day-profile reader):

* :func:`hourly_loads_from_readings` rolls interval readings up to one energy
  total per local clock hour, mirroring ``owr.etl.daily.daily_loads_from_readings``
  one level finer.
* :func:`percentile_ranks` computes the empirical rank of a set of day totals
  against a population, the same formula ``owr.scenario_input`` uses for its
  derived ``demand_percentile``.
* :func:`render_day_profile_csv` writes the two above into the
  ``date,hour,load_mw,demand_percentile`` format ``owr.scenario_input`` reads.

No ``wind_mw`` column is emitted here, and none is shaped. There is no real ISO-NE
or EIA wind series in this repository to shape one from.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from owr.etl.daily import EASTERN, IntervalReading

# Coverage tolerance for one hourly bucket, matching owr.etl.daily's own default
# tolerance_hours for a full day.
_HOUR_TOLERANCE = 0.01
# The fall-back DST signature: one bucket absorbing the repeated local hour.
_DST_FALLBACK_HOURS = 2.0


@dataclass(frozen=True)
class HourlyLoad:
    date: date  # LOCAL calendar date
    hour: int  # 0..23, local clock hour
    load_mwh: float  # integral of load_mw over the hour
    hours_covered: float
    intervals: int


def hourly_loads_from_readings(
    readings: list[IntervalReading],
    *,
    tz: ZoneInfo = EASTERN,
) -> list[HourlyLoad]:
    """Integrate interval readings into one ``HourlyLoad`` per local clock hour.

    Mirrors ``owr.etl.daily.daily_loads_from_readings`` one level finer: energy is
    an integral (``load_mwh = Sum(load_mw * interval_hours)``), never a count. An
    interval is attributed wholly to the local hour of its start. Naive timestamps
    and duplicate absolute instants are both rejected, naming the timestamp.
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

    by_bucket: dict[tuple[date, int], list[IntervalReading]] = {}
    for r in ordered:
        local = r.ts.astimezone(tz)
        by_bucket.setdefault((local.date(), local.hour), []).append(r)

    results: list[HourlyLoad] = []
    for d, hour in sorted(by_bucket):
        group = by_bucket[(d, hour)]
        results.append(
            HourlyLoad(
                date=d,
                hour=hour,
                load_mwh=sum(r.load_mw * r.interval_hours for r in group),
                hours_covered=sum(r.interval_hours for r in group),
                intervals=len(group),
            )
        )
    return results


def percentile_ranks(
    population_mwh: Sequence[float],
    day_totals: Mapping[date, float],
) -> dict[date, float]:
    """Empirical rank of each day total against ``population_mwh``.

    Rank = ``count(p <= v) / len(population_mwh)``. Raises ``ValueError`` on an
    empty population.

    The caller must pass the day total that the population itself holds, never a
    total recomputed from an hourly rollup: two summation orders over the same day
    differ by about 1e-9, enough to drop a day below its own population value and
    cost it one rank step (measured 2026-08-05, docs/PLAN_REAL_DEMO_BRIDGE.md).
    """
    if not population_mwh:
        raise ValueError("percentile_ranks: population_mwh is empty")
    n = len(population_mwh)
    return {d: sum(1 for p in population_mwh if p <= v) / n for d, v in day_totals.items()}


def render_day_profile_csv(
    hourly: Sequence[HourlyLoad],
    *,
    demand_percentile: Mapping[date, float],
    banner: Sequence[str],
) -> str:
    """Render ``hourly`` into the ``date,hour,load_mw,demand_percentile`` format.

    Each ``banner`` line is written with a leading ``# `` before the header. Every
    date must carry exactly the 24 hours 0..23, each within 1.0 +/- 0.01 hours
    coverage, a ``demand_percentile`` entry, and the dates must be consecutive.
    Daylight saving time is named in the error message under exactly two
    conditions: a date with 23 hour buckets (spring-forward), or a bucket covering
    about 2.0 hours (fall-back). Any other coverage shortfall is reported as a
    plain gap, with no mention of daylight saving time.

    No ``ts`` and no git revision are written, so the committed artifact stays
    byte stable across a data-only regeneration.
    """
    by_date: dict[date, dict[int, HourlyLoad]] = {}
    for h in hourly:
        by_date.setdefault(h.date, {})[h.hour] = h

    sorted_dates = sorted(by_date)

    for d in sorted_dates:
        hours_present = sorted(by_date[d].keys())
        if hours_present != list(range(24)):
            if len(hours_present) == 23:
                raise ValueError(
                    f"{d.isoformat()}: only 23 hours present (daylight saving time "
                    "spring-forward day; this bridge format carries no half-hour "
                    "slot for it)"
                )
            raise ValueError(
                f"{d.isoformat()}: expected exactly 24 hours (0-23), got "
                f"{len(hours_present)}"
            )
        for hour in range(24):
            bucket = by_date[d][hour]
            if abs(bucket.hours_covered - 1.0) > _HOUR_TOLERANCE:
                if abs(bucket.hours_covered - _DST_FALLBACK_HOURS) <= _HOUR_TOLERANCE:
                    raise ValueError(
                        f"{d.isoformat()} hour {hour}: covers "
                        f"{bucket.hours_covered:.4f} hours (daylight saving time "
                        "fall-back; this bridge format has no way to split the "
                        "repeated hour)"
                    )
                raise ValueError(
                    f"{d.isoformat()} hour {hour}: covers "
                    f"{bucket.hours_covered:.4f} hours, expected 1.0 +/- "
                    f"{_HOUR_TOLERANCE}"
                )
        if d not in demand_percentile:
            raise ValueError(f"{d.isoformat()}: no demand_percentile supplied")

    for prev_d, next_d in zip(sorted_dates, sorted_dates[1:], strict=False):
        if (next_d - prev_d).days != 1:
            raise ValueError(
                f"dates are not consecutive: {prev_d.isoformat()} is followed by "
                f"{next_d.isoformat()}"
            )

    buf = io.StringIO()
    for line in banner:
        buf.write(f"# {line}\n")
    writer = csv.writer(buf)
    writer.writerow(["date", "hour", "load_mw", "demand_percentile"])
    for d in sorted_dates:
        dp_token = f"{demand_percentile[d]:.6f}"
        for hour in range(24):
            bucket = by_date[d][hour]
            avg_mw = bucket.load_mwh / bucket.hours_covered
            writer.writerow([d.isoformat(), hour, f"{avg_mw:.3f}", dp_token])
    return buf.getvalue()
