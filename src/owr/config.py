"""Engine configuration — the design constants the source documents leave open.

Every value here is a **team design choice**, not a verified fact (see
docs/FACT_CHECK_REPORT.md "Common Mistakes": the 0.7/0.3 weights, 80% budget and
33% floor are decisions to benchmark against literature and label, never facts to
verify). They are surfaced as configuration so a scenario can override them and so
the open questions in docs/PLAN.md never get hard-coded as magic numbers.
"""

from __future__ import annotations

from dataclasses import dataclass


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
        Stress-event detection parameters passed to ``stress_finder``: a day is
        stressed when its daily energy sits at or above this percentile of the
        series, and a run of this many consecutive stressed days is an event. OPEN
        team question (stress_event_definition): three artifacts use three
        thresholds and merge rules on the same January 2025 activity, and a
        competing rule counts hours within the day (12+ hours above threshold =
        stress day, 2+ consecutive = event). These are the shipped defaults of the
        implemented rule, not a decision.

    default_peak_weight / default_smooth_weight
        Relative emphasis of peak shaving vs ramp smoothing in ``dispatch``. The
        Architecture doc names PeakWeight and SmoothWeight without fixing values.
        (Team design choice.)
    """

    priority_demand_weight: float = 0.7
    priority_wind_weight: float = 0.3
    energy_budget_fraction: float = 0.80
    default_efficiency: float = 1.0
    default_soc_floor_frac: float = 0.20
    default_strategic_reserve_frac: float = 0.10
    default_severity_percentile: float = 0.95
    default_min_stress_window_days: int = 2
    default_peak_weight: float = 0.5
    default_smooth_weight: float = 0.5

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


DEFAULT_CONFIG = Config()
