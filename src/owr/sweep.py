"""Pure sweep runner: one `simulator.simulate` call per storage size.

Implements docs/archive/plans/PLAN_SCENARIO_SWEEP.md section 4.3. Engine core: no file access,
no network access, no database access. Third-party imports are ``pandas`` only,
per the engine-core two-library allowlist (pandas, numpy).

Every sweep point starts full (``starting_soc = asset.total_mwh``); ``run_sweep``
performs no pre-event charging and takes no lead days (see the plan's revision-log
entry B1, section 4.3 rule 5).

``severity_reduction`` comes from ``metrics.severity_reduction``, which raises
``ValueError`` when ``baseline_peak_mw <= 0``. This diverges from
``cli._severity_reduction``, which returns ``0.0`` in that case: a day-profile
file whose every load value is zero therefore exits 2 under ``sweep`` and prints
``0.0%`` under ``simulate`` (plan decision D6). Both example files carry a
positive baseline peak.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from owr.config import DEFAULT_CONFIG, Config
from owr.metrics import equivalent_full_cycles as _equivalent_full_cycles
from owr.metrics import severity_reduction as _severity_reduction
from owr.models import DayProfile, PowerRule, StorageAsset
from owr.simulator import simulate

SWEEP_FRAME_COLUMNS: tuple[str, ...] = (
    "storage_mwh", "power_mw", "duration_hours", "severity_reduction",
    "baseline_peak_mw", "reserve_peak_mw", "energy_discharged_mwh",
    "energy_charged_mwh", "final_soc_mwh", "equivalent_full_cycles",
)


@dataclass(frozen=True)
class SweepSpec:
    """One sweep's inputs: a size ladder, a power rule, and the asset fractions
    every point shares.

    Carries no ``Config`` class-level default (plan section 4.3 rule 10). A
    class-level default would bind ``DEFAULT_CONFIG`` at import time, so a caller
    passing a custom ``Config`` to ``run_sweep`` would silently keep the
    import-time value. The caller supplies ``efficiency``, ``soc_floor_frac`` and
    ``strategic_reserve_frac`` explicitly. ``Config.default_sweep_sizes_mwh`` and
    ``Config.default_sweep_power_rule`` reach this class through
    ``sweep_cli.build_parser`` only.
    """

    sizes_mwh: tuple[float, ...]
    power_rule: PowerRule
    efficiency: float
    soc_floor_frac: float
    strategic_reserve_frac: float
    power_mw: float | None = None
    duration_hours: float | None = None

    def __post_init__(self) -> None:
        if not self.sizes_mwh:
            raise ValueError("sizes_mwh must not be empty")
        for size in self.sizes_mwh:
            if not math.isfinite(size) or size <= 0:
                raise ValueError("sizes_mwh values must be finite and positive")
        for prev, nxt in zip(self.sizes_mwh, self.sizes_mwh[1:], strict=False):
            if not prev < nxt:
                raise ValueError("sizes_mwh must be strictly increasing")

        if self.power_rule is PowerRule.FIXED:
            if self.power_mw is None:
                raise ValueError("power_mw is required under PowerRule.FIXED")
            if not math.isfinite(self.power_mw) or self.power_mw <= 0:
                raise ValueError("power_mw must be finite and positive")
            if self.duration_hours is not None:
                raise ValueError("duration_hours must not be set under PowerRule.FIXED")
        elif self.power_rule is PowerRule.FIXED_DURATION:
            if self.duration_hours is None:
                raise ValueError("duration_hours is required under PowerRule.FIXED_DURATION")
            if not math.isfinite(self.duration_hours) or self.duration_hours <= 0:
                raise ValueError("duration_hours must be finite and positive")
            if self.power_mw is not None:
                raise ValueError("power_mw must not be set under PowerRule.FIXED_DURATION")

    def power_for(self, size_mwh: float) -> float:
        """Power at one size. Constant under ``FIXED``; ``size / duration`` under
        ``FIXED_DURATION``."""
        if self.power_rule is PowerRule.FIXED:
            assert self.power_mw is not None  # guaranteed by __post_init__
            return self.power_mw
        assert self.duration_hours is not None  # guaranteed by __post_init__
        return size_mwh / self.duration_hours

    def duration_for(self, size_mwh: float) -> float:
        """Duration at one size: ``size_mwh / power_for(size_mwh)``. Constant
        under ``FIXED_DURATION`` and rises with size under ``FIXED``."""
        return size_mwh / self.power_for(size_mwh)

    def asset_for(self, size_mwh: float) -> StorageAsset:
        """The ``StorageAsset`` a sweep point simulates at one size."""
        return StorageAsset(
            total_mwh=size_mwh,
            power_mw=self.power_for(size_mwh),
            efficiency=self.efficiency,
            soc_floor_frac=self.soc_floor_frac,
            strategic_reserve_frac=self.strategic_reserve_frac,
        )


@dataclass(frozen=True)
class SweepPoint:
    storage_mwh: float
    power_mw: float
    duration_hours: float
    severity_reduction: float
    baseline_peak_mw: float
    reserve_peak_mw: float
    energy_discharged_mwh: float
    energy_charged_mwh: float
    final_soc_mwh: float
    equivalent_full_cycles: float


@dataclass(frozen=True)
class SweepResult:
    points: tuple[SweepPoint, ...]

    def frame(self) -> pd.DataFrame:
        """The sweep result table, one row per size, in ladder order. Every
        column carries an explicit ``float64`` dtype, matching the dtype discipline of
        ``SimulationResult.hourly_frame``."""
        return pd.DataFrame(
            {
                "storage_mwh": pd.Series(
                    [p.storage_mwh for p in self.points], dtype="float64"
                ),
                "power_mw": pd.Series([p.power_mw for p in self.points], dtype="float64"),
                "duration_hours": pd.Series(
                    [p.duration_hours for p in self.points], dtype="float64"
                ),
                "severity_reduction": pd.Series(
                    [p.severity_reduction for p in self.points], dtype="float64"
                ),
                "baseline_peak_mw": pd.Series(
                    [p.baseline_peak_mw for p in self.points], dtype="float64"
                ),
                "reserve_peak_mw": pd.Series(
                    [p.reserve_peak_mw for p in self.points], dtype="float64"
                ),
                "energy_discharged_mwh": pd.Series(
                    [p.energy_discharged_mwh for p in self.points], dtype="float64"
                ),
                "energy_charged_mwh": pd.Series(
                    [p.energy_charged_mwh for p in self.points], dtype="float64"
                ),
                "final_soc_mwh": pd.Series(
                    [p.final_soc_mwh for p in self.points], dtype="float64"
                ),
                "equivalent_full_cycles": pd.Series(
                    [p.equivalent_full_cycles for p in self.points], dtype="float64"
                ),
            },
            columns=list(SWEEP_FRAME_COLUMNS),
        )


def run_sweep(
    spec: SweepSpec,
    *,
    span_days: Sequence[DayProfile],
    config: Config = DEFAULT_CONFIG,
) -> SweepResult:
    """Run the engine once per size in ``spec.sizes_mwh`` over the same span.

    Reads ``peak_weight`` and ``smooth_weight`` off ``config.default_peak_weight``
    and ``config.default_smooth_weight``; it takes no separate weight parameters.
    ``cli._run`` builds its ``Config`` from the same two flags, so a sweep and a
    single run reach ``simulate`` with identical arguments **while
    ``energy_budget_fraction``, ``priority_demand_weight`` and
    ``priority_wind_weight`` keep their ``Config`` defaults**, the only state the
    ``sweep`` CLI can produce (plan section 4.3 rule 4).

    Raises ``ValueError`` on an empty ``span_days``.
    """
    if not span_days:
        raise ValueError("span_days must not be empty")

    days = list(span_days)
    points: list[SweepPoint] = []
    for size in spec.sizes_mwh:
        asset = spec.asset_for(size)
        result = simulate(
            asset,
            days,
            starting_soc=asset.total_mwh,
            config=config,
            peak_weight=config.default_peak_weight,
            smooth_weight=config.default_smooth_weight,
        )
        energy_discharged = sum(h.discharge for d in result.daily for h in d.hourly)
        energy_charged = sum(h.charge for d in result.daily for h in d.hourly)
        points.append(
            SweepPoint(
                storage_mwh=size,
                power_mw=asset.power_mw,
                duration_hours=spec.duration_for(size),
                severity_reduction=_severity_reduction(
                    result.baseline_peak_mw, result.reserve_peak_mw
                ),
                baseline_peak_mw=result.baseline_peak_mw,
                reserve_peak_mw=result.reserve_peak_mw,
                energy_discharged_mwh=energy_discharged,
                energy_charged_mwh=energy_charged,
                final_soc_mwh=result.final_soc,
                equivalent_full_cycles=_equivalent_full_cycles(
                    energy_discharged, rated_energy_mwh=size
                ),
            )
        )

    return SweepResult(points=tuple(points))
