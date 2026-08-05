"""Engine configuration — the design constants the source documents leave open.

Every value here is a **team design choice**, not a verified fact (see
docs/FACT_CHECK_REPORT.md "Common Mistakes": the 0.7/0.3 weights, 80% budget and
33% floor are decisions to benchmark against literature and label, never facts to
verify). They are surfaced as configuration so a scenario can override them and so
the open questions in docs/PLAN.md never get hard-coded as magic numbers.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from owr.models import HOURS_PER_DAY, PowerRule, WrapConvention


@dataclass(frozen=True)
class Config:
    """Tunable design constants for the engine's stress-detection and dispatch models.

    A value belongs here when an engine function or value object takes it as a
    parameter; reporting-only assumptions live with their consumer.

    Attributes map to open questions in docs/PLAN.md / FACT_CHECK_REPORT.md:

    priority_demand_weight / priority_wind_weight
        Architecture doc: ``Priority(d) = 0.7*DemandPercentile + 0.3*WindForecast``.
        Weights must sum to 1.0. (Team design choice.)

    energy_budget_fraction
        The "80% energy budget rule": at most this fraction of the currently usable
        energy may be committed as a single day's discharge budget, leaving a margin
        for forecast error. (Team design choice; FACT_CHECK inconsistency around the
        blank Step 5/6 sections means the exact allocation is not fully specified.)

    default_efficiency
        Round-trip efficiency in ``soc(t+1)=soc(t)+charge*eff-discharge/eff``.
        Defaults to 1.0, which reconciles the Overview's "100% efficient" assumption
        with the Architecture doc's efficiency term (FACT_CHECK inconsistency #2).
        OPEN team question (round_trip_efficiency): ``config.py`` ships 1.0 while
        Report B computed everything at 0.85; at 1.0 the engine understates required
        charging energy by 17.6%. The storage pivot makes efficiency the axis
        candidate technologies differ on (StEnSea 0.80, LAES 0.50-0.70, thermal
        ~0.35). Undecided.

    default_soc_floor_frac / default_strategic_reserve_frac
        Reserve definition (FACT_CHECK inconsistency #3). Team decision 2026-07-17:
        the protected reserve is a 20% floor plus a 10% reserve of total capacity,
        leaving 70% for regular operations. We model the two as separate fractions;
        their sum (0.30) is the minimum state of charge the engine never discharges
        below. OPEN team question (reserve_usage_rules): when the 10% reserve and
        20% floor may each be drawn down (until decided, both are treated as one
        protected floor).

    default_severity_percentile / default_min_stress_window_days
        Stress-event detection parameters passed to ``stress_finder``. **Settled**
        2026-07-28 (HANDOFF.md decision 2): a day is stressed when its daily total
        demand sits at or above the historical 90th percentile of the series, and
        a run of ``default_min_stress_window_days`` (2+) consecutive such days
        forms an event. Report B's competing 12-hour rule (12+ hours above
        threshold within a day) is retired. What remains open is the **threshold
        value on real data**: both published numbers (3,504 and 16,750 MWh) are
        hourly-basis and do not carry over to a daily-basis rule, so a fresh p90
        must be computed on daily sums.

    default_peak_weight / default_smooth_weight
        Relative emphasis of peak shaving vs ramp smoothing in ``dispatch``. The
        Architecture doc names PeakWeight and SmoothWeight without fixing values.
        (Team design choice.)

    default_peak_window_hours
        **Settled** 2026-07-28: each day in a stress window gets a peak load
        defined as a 3-hour period found by rolling window over hour triplets.
        Surfaced as config because ``find_peak_window`` takes it as a parameter,
        not because it is in doubt.

    default_peak_window_wrap
        OPEN team question (peak_window_wrap). Mitchell's enumeration ends at
        (22,23,00). ``WrapConvention.WRAP_TO_NEXT_DAY`` is the physically
        continuous reading and the one HANDOFF.md says to assume;
        ``STOP_AT_MIDNIGHT`` is the 22-triplets alternative. On a multi-day event
        the choice changes which hours get shaved at the day boundary. Flipping
        the default is a one-value change.

    est_transmission_cost_per_mile_usd / est_storage_unit_cost_usd / solution_lifetime_years
        OPEN team question (capital_cost_constants). Component 7's capital-cost
        formulas need these three constants and every one is ``@`` in the source:
        no value exists yet for any of them. **No code path reads these three
        fields.** They park the wiring step that follows once the team supplies
        values, and surface the open question in the ``config`` block of every
        JSON report, mirroring ``storage_physics.py``, whose docstring says "Not
        wired anywhere" for the same reason. They belong in ``Config`` and not in
        ``cli.py`` because ``metrics.estimated_capital_cost_usd`` and
        ``metrics.cost_per_equivalent_full_cycle_usd`` take them as parameters.

    default_sweep_sizes_mwh
        OPEN team question (``sweep_size_ladder``). The seven sizes bracket Report
        A's 40,000 to 60,000 MWh system reserve target and the 60,000 MWh demo
        point. ``docs/FACT_CHECK_REPORT.md`` records that the 40,000 to 60,000 MWh
        target does not reproduce from its own inputs, so the ladder moves when
        that number moves. Read at parser-build time by
        ``sweep_cli.build_parser``; no engine function reads it at run time. See
        docs/PLAN_SCENARIO_SWEEP.md decision D3.

    default_sweep_power_rule
        OPEN team question (``sweep_power_scaling``). Fixed power isolates the
        energy variable and reproduces the recorded reference points. Fixed
        duration is the fleet-scaled reading. See docs/PLAN_SCENARIO_SWEEP.md
        decision D2. Read at parser-build time only, as above.
    """

    priority_demand_weight: float = 0.7
    priority_wind_weight: float = 0.3
    energy_budget_fraction: float = 0.80
    default_efficiency: float = 1.0
    default_soc_floor_frac: float = 0.20
    default_strategic_reserve_frac: float = 0.10
    default_severity_percentile: float = 0.90
    default_min_stress_window_days: int = 2
    default_peak_weight: float = 0.5
    default_smooth_weight: float = 0.5
    default_peak_window_hours: int = 3
    default_peak_window_wrap: WrapConvention = WrapConvention.WRAP_TO_NEXT_DAY
    est_transmission_cost_per_mile_usd: float | None = None
    est_storage_unit_cost_usd: float | None = None
    solution_lifetime_years: float | None = None
    default_sweep_sizes_mwh: tuple[float, ...] = (
        5000.0, 10000.0, 20000.0, 40000.0, 60000.0, 80000.0, 100000.0,
    )
    default_sweep_power_rule: PowerRule = PowerRule.FIXED

    def __post_init__(self) -> None:
        if abs((self.priority_demand_weight + self.priority_wind_weight) - 1.0) > 1e-9:
            raise ValueError("priority weights must sum to 1.0")
        if not 0.0 < self.energy_budget_fraction <= 1.0:
            raise ValueError("energy_budget_fraction must be in (0, 1]")
        if not 0.0 < self.default_efficiency <= 1.0:
            raise ValueError("efficiency must be in (0, 1]")
        floor = self.default_soc_floor_frac + self.default_strategic_reserve_frac
        if not 0.0 <= floor < 1.0:
            raise ValueError("soc_floor + strategic_reserve must be in [0, 1)")
        if not 0.0 <= self.default_severity_percentile <= 1.0:
            raise ValueError("default_severity_percentile must be in [0, 1]")
        if self.default_min_stress_window_days < 1:
            raise ValueError("default_min_stress_window_days must be >= 1")
        if self.default_peak_weight < 0 or self.default_smooth_weight < 0:
            raise ValueError("default_peak_weight and default_smooth_weight must be >= 0")
        if self.default_peak_weight + self.default_smooth_weight <= 0:
            raise ValueError("default_peak_weight + default_smooth_weight must be > 0")
        if not 1 <= self.default_peak_window_hours <= HOURS_PER_DAY:
            raise ValueError(f"default_peak_window_hours must be in 1..{HOURS_PER_DAY}")
        if self.est_transmission_cost_per_mile_usd is not None and (
            self.est_transmission_cost_per_mile_usd < 0
        ):
            raise ValueError("est_transmission_cost_per_mile_usd must be non-negative")
        if self.est_storage_unit_cost_usd is not None and self.est_storage_unit_cost_usd < 0:
            raise ValueError("est_storage_unit_cost_usd must be non-negative")
        if self.solution_lifetime_years is not None and self.solution_lifetime_years < 0:
            raise ValueError("solution_lifetime_years must be non-negative")
        if not self.default_sweep_sizes_mwh:
            raise ValueError("default_sweep_sizes_mwh must not be empty")
        for size in self.default_sweep_sizes_mwh:
            if not math.isfinite(size) or size <= 0:
                raise ValueError("default_sweep_sizes_mwh values must be finite and positive")
        for prev, nxt in zip(
            self.default_sweep_sizes_mwh, self.default_sweep_sizes_mwh[1:], strict=False
        ):
            if not prev < nxt:
                raise ValueError("default_sweep_sizes_mwh must be strictly increasing")


DEFAULT_CONFIG = Config()
