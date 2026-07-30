"""Threshold and window orchestration (docs/PLAN_EIA_EXTRACTOR.md Phase B3).

Ties together ``owr.etl.daily``, ``owr.etl.seasons``, and ``owr.stress_finder``:

- ``compute_threshold`` takes the p90 (or any percentile) over the *pooled*
  five-winter record of complete days in one season — the settled definition
  (HANDOFF.md: "all Dec-Feb days in the five-year set").
- ``find_windows_per_winter`` groups days by ``winter_label`` and finds stress
  windows *within* each winter using the pooled threshold, so a naive
  concatenation of winters (Feb 28 followed by the next Dec 1) can never merge
  across the season boundary. Combined with the date-aware adjacency inside
  ``find_stress_windows_at_threshold``, an excluded incomplete day in the middle
  of a winter safely splits a run instead of merging across the gap. Neither
  mechanism raises on a gap; gaps are reported by ``validate`` (Phase B4), not
  fatal here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from owr.etl.daily import DailyLoad
from owr.etl.seasons import Season, season_for, winter_label
from owr.models import StressWindow
from owr.stress_finder import find_stress_windows_at_threshold, percentile_threshold


@dataclass(frozen=True)
class ThresholdResult:
    percentile: float
    threshold_mwh: float
    population_days: int
    season: Season
    excluded_incomplete: tuple[date, ...]
    min_mwh: float
    median_mwh: float
    max_mwh: float


def compute_threshold(
    daily: list[DailyLoad], *, percentile: float, season: Season
) -> ThresholdResult:
    """p90 (or given percentile) over complete days of one season, pooled across
    however many years ``daily`` spans. Incomplete days are excluded from the
    population and reported (not fatal — see ``owr.etl.daily`` point 9)."""
    in_season = [d for d in daily if season_for(d.date) == season]
    population = [d for d in in_season if d.complete]
    excluded = tuple(sorted(d.date for d in in_season if not d.complete))

    values = [d.load_mwh for d in population]
    if not values:
        raise ValueError(f"no complete {season} days in the input population")
    threshold = percentile_threshold(values, percentile)
    ordered = sorted(values)

    return ThresholdResult(
        percentile=percentile,
        threshold_mwh=threshold,
        population_days=len(population),
        season=season,
        excluded_incomplete=excluded,
        min_mwh=ordered[0],
        median_mwh=percentile_threshold(values, 0.5),
        max_mwh=ordered[-1],
    )


def find_windows_per_winter(
    daily: list[DailyLoad], *, threshold_mwh: float, min_window_days: int
) -> dict[str, list[StressWindow]]:
    """Group ``daily`` by ``winter_label`` (days outside winter are dropped) and
    find stress windows within each winter at the shared pooled threshold."""
    by_winter: dict[str, list[DailyLoad]] = {}
    for d in daily:
        label = winter_label(d.date)
        if label is None:
            continue
        by_winter.setdefault(label, []).append(d)

    result: dict[str, list[StressWindow]] = {}
    for label, days in by_winter.items():
        ordered = sorted((d for d in days if d.complete), key=lambda d: d.date)
        result[label] = find_stress_windows_at_threshold(ordered, threshold_mwh, min_window_days)
    return result
