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
    """Tunable design constants for the dispatch model.

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

    default_soc_floor_frac / default_strategic_reserve_frac
        Reserve definition (FACT_CHECK inconsistency #3, still a BLOCKED team
        decision). We model two separate fractions of total capacity; their sum is
        the minimum state of charge the engine will never discharge below. Defaults
        (0.33 + 0.0) reproduce the doc's "constant reserve of 33% total capacity".
    """

    priority_demand_weight: float = 0.7
    priority_wind_weight: float = 0.3
    energy_budget_fraction: float = 0.80
    default_efficiency: float = 1.0
    default_soc_floor_frac: float = 0.33
    default_strategic_reserve_frac: float = 0.0

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


DEFAULT_CONFIG = Config()
