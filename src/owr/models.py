"""Domain models for the simulation engine.

All value objects the engine passes around. Storage is a *generic* long-duration
asset (power / energy / efficiency / floors) so the pumped-hydro-vs-battery naming
question is a UI/copy decision, not a code fork (FACT_CHECK inconsistency #1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Protocol

HOURS_PER_DAY = 24


@dataclass(frozen=True)
class StorageAsset:
    """A generic long-duration storage asset.

    total_mwh
        Usable energy capacity end to end.
    power_mw
        Max charge/discharge power; caps energy moved in any single hour.
    efficiency
        Round-trip efficiency used in the state equation (default 1.0).
    soc_floor_frac, strategic_reserve_frac
        Fractions of total capacity that together define the minimum SoC the engine
        never discharges below (the "reserve"). Team decision 2026-07-17: 20% floor
        + 10% reserve = 30% protected, 70% for regular operations. See Config for the
        still-open question of when each may be drawn down.
    """

    total_mwh: float
    power_mw: float
    efficiency: float = 1.0
    soc_floor_frac: float = 0.20
    strategic_reserve_frac: float = 0.10

    def __post_init__(self) -> None:
        if self.total_mwh <= 0:
            raise ValueError("total_mwh must be positive")
        if self.power_mw <= 0:
            raise ValueError("power_mw must be positive")
        if not 0.0 < self.efficiency <= 1.0:
            raise ValueError("efficiency must be in (0, 1]")

    @property
    def min_soc_mwh(self) -> float:
        """Minimum state of charge (MWh) — the protected reserve floor."""
        return (self.soc_floor_frac + self.strategic_reserve_frac) * self.total_mwh


@dataclass(frozen=True)
class DayProfile:
    """One day of inputs for the rolling-window loop.

    hourly_load_mw / hourly_wind_mw
        24-value gross-load and wind-availability profiles for the day.
    demand_percentile
        Day's load as a fraction of the seasonal denominator (0..1+); used for
        stress detection and dispatch priority. Precomputed in ETL (features.*).
    wind_forecast_frac
        Forecast wind availability for the day as a fraction of capacity (0..1);
        the 0.3-weighted term in Priority(d).
    """

    date: date
    hourly_load_mw: tuple[float, ...]
    hourly_wind_mw: tuple[float, ...] = field(default=())
    demand_percentile: float = 0.0
    wind_forecast_frac: float = 0.0

    def __post_init__(self) -> None:
        if len(self.hourly_load_mw) != HOURS_PER_DAY:
            raise ValueError(f"hourly_load_mw must have {HOURS_PER_DAY} values")
        if self.hourly_wind_mw and len(self.hourly_wind_mw) != HOURS_PER_DAY:
            raise ValueError(f"hourly_wind_mw must have {HOURS_PER_DAY} values")

    @property
    def load_mwh(self) -> float:
        """Total energy demanded across the day (MWh), i.e. sum of hourly MW."""
        return sum(self.hourly_load_mw)


@dataclass(frozen=True)
class StressWindow:
    """A run of consecutive stressed days found by stress_finder."""

    start: date
    end: date
    days: int


class DailyLoadLike(Protocol):
    """What stress detection actually needs: a date and a daily energy total.

    ``DayProfile`` satisfies this structurally; so does ``owr.etl.daily.DailyLoad``.
    Not marked ``runtime_checkable``: ``DayProfile.load_mwh`` is a property, and
    ``isinstance`` against a data protocol raises anyway.
    """

    date: date
    load_mwh: float


class WrapConvention(StrEnum):
    """Which hour triplets a day gets when locating its peak window. OPEN team
    question (peak_window_wrap): HANDOFF.md, Mitchell 2026-07-28 23:12. Mitchell's
    enumeration ends at (22,23,00); whether that 00 is the next day's or the same
    day's is unconfirmed.

    ``StrEnum``, not a plain ``Enum``: ``cli.py`` does ``"config": asdict(cfg)``
    then ``json.dumps``, and a plain ``Enum`` member is not JSON-serializable.
    """

    STOP_AT_MIDNIGHT = "stop_at_midnight"  # windows must fit inside the day: 22 triplets
    WRAP_TO_NEXT_DAY = "wrap_to_next_day"  # last window is (22,23,next-day-00): 23 triplets

    @property
    def lookahead_hours(self) -> int:
        """Hours of look-ahead into the next day this convention needs. 1 for
        ``WRAP_TO_NEXT_DAY`` at any window size, matching Mitchell's enumeration,
        which wraps by exactly one hour. A fully continuous reading (look-ahead
        ``window_hours - 1``) is reachable through ``find_peak_window`` directly,
        without touching this enum."""
        return 1 if self is WrapConvention.WRAP_TO_NEXT_DAY else 0


@dataclass(frozen=True)
class PeakWindow:
    """The highest-summing rolling window of consecutive hours in a day, found by
    ``peak_window.find_peak_window``."""

    start_hour: int  # 0..23, index into the day's own 24 hours
    clock_hours: tuple[int, ...]  # (start_hour + k) % 24 for each hour, e.g. (22, 23, 0)
    load_mw: tuple[float, ...]  # the loads summed, in order
    wrapped: bool  # True when the window crosses into the next day
    candidates_considered: int  # number of start positions evaluated

    def __post_init__(self) -> None:
        if not 0 <= self.start_hour <= 23:
            raise ValueError("start_hour must be in 0..23")
        if len(self.clock_hours) != len(self.load_mw):
            raise ValueError("clock_hours and load_mw must be the same length")
        if len(self.load_mw) < 1:
            raise ValueError("load_mw must have at least one value")
        if self.candidates_considered < 1:
            raise ValueError("candidates_considered must be >= 1")

    @property
    def load_mwh(self) -> float:
        """Total energy summed across the window (MWh), mirrors DayProfile.load_mwh."""
        return sum(self.load_mw)


@dataclass(frozen=True)
class HourlyResult:
    ts_hour: int
    soc: float
    charge: float
    discharge: float
    discharge_peak: float
    discharge_smooth: float
    gross_load: float
    net_load: float
    capacity_margin: float | None = None


@dataclass(frozen=True)
class DailyResult:
    date: date
    budget: float
    priority: float
    usable_energy: float
    recharge_sufficiency_ratio: float | None
    hourly: list[HourlyResult]
