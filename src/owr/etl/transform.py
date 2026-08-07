"""Threshold and window orchestration (docs/archive/plans/PLAN_EIA_EXTRACTOR.md Phase B3).

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

docs/archive/plans/PLAN_PANDAS_ADOPTION.md phase 5 moved the daily and event tables onto
``pandas.DataFrame``. ``daily_loads_from_readings`` (owr.etl.daily) still
accumulates with Python ``sum()``; only the table assembly, filtering and
rendering below is pandas.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import NamedTuple

import numpy as np
import pandas as pd

from owr.etl.daily import DAILY_CORE_COLUMNS
from owr.etl.seasons import Season, season_for, winter_label
from owr.models import PercentileRounding
from owr.stress_finder import (
    find_stress_windows_at_percentile,
    find_stress_windows_at_threshold,
    percentile_threshold,
)

DAILY_FRAME_COLUMNS: tuple[str, ...] = DAILY_CORE_COLUMNS + (
    "season", "winter_label", "load_percentile",
)

EVENT_FRAME_COLUMNS: tuple[str, ...] = (
    "winter_label", "event_start_date", "event_end_date", "event_duration_days",
)


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


def add_season_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a new frame with ``season`` and ``winter_label`` appended.

    Never mutates the input. The architecture doc's Global Interface Contract says a
    component shall never modify another component's output.
    """
    out = frame.copy()
    out["season"] = pd.Series(
        [season_for(d).value for d in frame["date"]], index=frame.index, dtype="object"
    )
    out["winter_label"] = pd.Series(
        [winter_label(d) for d in frame["date"]], index=frame.index, dtype="object"
    )
    return out


def winter_labels(daily: pd.DataFrame) -> tuple[str, ...]:
    """Every winter label present in ``daily``, sorted, duplicates removed.

    Filter on ``winter_label`` being present, and **do not** filter on ``complete``.
    The retired ``find_windows_per_winter`` grouped by label before it dropped
    incomplete days, so a winter whose days are all incomplete still produced a key
    with an empty list. The ETL CLI emits one JSON entry per label returned here, so
    this function is the sole reason a winter with zero events keeps its key.
    """
    return tuple(sorted(daily.loc[daily["winter_label"].notna(), "winter_label"].unique()))


def compute_threshold(
    daily: pd.DataFrame, *, percentile: float, season: Season
) -> ThresholdResult:
    """p90 (or given percentile) over complete days of one season, pooled across
    however many years ``daily`` spans. Incomplete days are excluded from the
    population and reported (not fatal — see ``owr.etl.daily`` point 9).

    Takes the frame that :func:`add_season_columns` produced, and keeps its
    current order of operations exactly: mask on season, split on ``complete``,
    raise before any aggregation touches an empty population (``Series.min()``
    on an empty series returns ``NaN`` instead of raising).
    """
    in_season = daily[daily["season"] == season.value]
    population = in_season[in_season["complete"]]
    excluded = in_season[~in_season["complete"]]
    excluded_incomplete = tuple(sorted(excluded["date"]))

    if len(population.index) == 0:
        raise ValueError(f"no complete {season} days in the input population")

    values = population["load_mwh"].to_numpy()
    threshold = percentile_threshold(values, percentile)

    return ThresholdResult(
        percentile=percentile,
        threshold_mwh=threshold,
        population_days=int(len(population.index)),
        season=season,
        excluded_incomplete=excluded_incomplete,
        min_mwh=float(values.min()),
        median_mwh=percentile_threshold(values, 0.5),
        max_mwh=float(values.max()),
    )


def with_load_percentile(daily: pd.DataFrame, *, season: Season) -> pd.DataFrame:
    """Return a new frame carrying ``load_percentile``, in percent 0 to 100 (D3).

    The population is every complete day of ``season`` in ``daily``, pooled
    across however many winters (or other-season years) the frame spans (D4),
    the same population ``compute_threshold`` uses. Out-of-season and
    incomplete days get ``NaN``. Component 2 data contract: ``load_percentile |
    % | Pre-processed 5-winters percentile of daily load``.

    ``rank = count(p <= v) / n * 100``, matching
    ``owr.stress_finder.percentile_rank_percent``. Ties take the highest rank.
    Never mutates its input; raises ``ValueError`` with
    :func:`compute_threshold`'s message when the season has no complete days.
    """
    out = daily.copy()
    population_mask = (out["season"] == season.value) & out["complete"]
    pop_values = out.loc[population_mask, "load_mwh"].to_numpy()
    if pop_values.size == 0:
        raise ValueError(f"no complete {season} days in the input population")

    n = pop_values.size
    load_percentile = pd.Series(np.nan, index=out.index, dtype="float64")
    values = out.loc[population_mask, "load_mwh"].to_numpy()
    ranks = (pop_values[None, :] <= values[:, None]).sum(axis=1) / n * 100.0
    load_percentile.loc[population_mask] = ranks
    out["load_percentile"] = load_percentile
    return out


class _DailyPoint(NamedTuple):
    """A minimal ``DailyLoadLike`` built from one event-frame row."""

    date: date
    load_mwh: float


class _DailyPercentilePoint(NamedTuple):
    """A minimal ``DailyPercentileLike`` built from one event-frame row.

    ``demand_percentile`` is a FRACTION, 0 to 1; the frame's ``load_percentile``
    column is percent, 0 to 100 (D3a). The division below is the single
    conversion site in the repo; do not inline the divide anywhere else.
    """

    date: date
    demand_percentile: float


def find_windows_per_winter(
    daily: pd.DataFrame,
    *,
    threshold_mwh: float | None = None,
    min_window_days: int,
    use_percentile: bool = False,
    percentile_floor_percent: float = 90.0,
    rounding: PercentileRounding = PercentileRounding.FLOOR,
) -> pd.DataFrame:
    """The Component 3 event table: one row per stress window, grouped by winter.

    **The event frame carries only event rows.** A winter with no event contributes
    no row, by design. The label set lives in :func:`winter_labels`, and the CLI
    joins the two. Do not try to recover the label set from the event frame; that
    is the defect docs/archive/plans/PLAN_PANDAS_ADOPTION.md revision 1 fixes (finding B1).

    The doc calls the identifier ``winter_id`` and describes it as a hash. This
    repo has a readable label and no hash; ``winter_label`` stays, and no
    ``event_id`` column is added (D15 supersedes this in Phase 8, which adds a
    per-run integer id).

    ``use_percentile`` (Phase 7, change 3) selects the MWh-threshold detection
    path (default, ``find_stress_windows_at_threshold``) or the integer-percentile
    comparison path (``find_stress_windows_at_percentile``, requires the frame's
    ``load_percentile`` column from :func:`with_load_percentile`). Default False,
    so a caller that does not pass it keeps the MWh path and its existing tests
    unmoved. ``threshold_mwh`` is required when ``use_percentile`` is False and
    ignored when it is True.
    """
    complete = daily[daily["complete"] & daily["winter_label"].notna()]

    winter_frames: list[pd.DataFrame] = []
    for label, group in complete.groupby("winter_label"):
        ordered = group.sort_values("date")
        if use_percentile:
            percentile_points = [
                _DailyPercentilePoint(date=row.date, demand_percentile=row.load_percentile / 100.0)
                for row in ordered.itertuples()
            ]
            windows = find_stress_windows_at_percentile(
                percentile_points,
                min_window_days,
                percentile_floor_percent=percentile_floor_percent,
                rounding=rounding,
            )
        else:
            if threshold_mwh is None:
                raise ValueError("threshold_mwh is required when use_percentile is False")
            points = [
                _DailyPoint(date=row.date, load_mwh=row.load_mwh) for row in ordered.itertuples()
            ]
            windows = find_stress_windows_at_threshold(points, threshold_mwh, min_window_days)
        for w in windows:
            winter_frames.append(
                {
                    "winter_label": label,
                    "event_start_date": w.start,
                    "event_end_date": w.end,
                    "event_duration_days": w.days,
                }
            )

    if not winter_frames:
        return pd.DataFrame(
            {
                "winter_label": pd.Series([], dtype="object"),
                "event_start_date": pd.Series([], dtype="object"),
                "event_end_date": pd.Series([], dtype="object"),
                "event_duration_days": pd.Series([], dtype="int64"),
            },
            columns=list(EVENT_FRAME_COLUMNS),
        )

    events = pd.DataFrame(winter_frames, columns=list(EVENT_FRAME_COLUMNS))
    events["event_duration_days"] = events["event_duration_days"].astype("int64")
    return events.sort_values(["winter_label", "event_start_date"]).reset_index(drop=True)
