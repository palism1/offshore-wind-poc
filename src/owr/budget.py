"""Daily budgeting (Architecture Step 5 / budget module).

Priority and the daily discharge budget. The exact Step 5/6 allocation text is a
blank/blocked section in the source doc (FACT_CHECK inconsistency #4); the rule
implemented here is the documented-and-labeled interpretation: a day may commit at
most ``energy_budget_fraction`` of the currently usable energy, scaled by that day's
priority relative to the rest of the stress window.
"""

from __future__ import annotations

from owr.config import Config


def priority(demand_percentile: float, wind_forecast_frac: float, config: Config) -> float:
    """Architecture: ``Priority(d) = 0.7*DemandPercentile + 0.3*WindForecast``.

    Higher demand raises priority; higher forecast wind (self-supply) lowers the need
    to lean on storage, so the wind term is entered as (1 - forecast) elsewhere. Here
    we implement the doc's literal weighted sum; the simulator decides how to combine.
    """
    return (
        config.priority_demand_weight * demand_percentile
        + config.priority_wind_weight * wind_forecast_frac
    )


def daily_budget(
    usable_energy_mwh: float,
    day_priority: float,
    remaining_priority_sum: float,
    config: Config,
) -> float:
    """Energy (MWh) this day is allowed to discharge.

    Caps at ``energy_budget_fraction`` of usable energy (the "80% rule"), then takes
    this day's share of that cap in proportion to its priority among the remaining
    stress days. With a single remaining day this is just the 80% cap.
    """
    if usable_energy_mwh <= 0:
        return 0.0
    cap = config.energy_budget_fraction * usable_energy_mwh
    if remaining_priority_sum <= 0:
        return cap
    share = min(1.0, day_priority / remaining_priority_sum)
    return cap * share


def recharge_sufficiency_ratio(
    recharge_available_mwh: float, discharge_needed_mwh: float
) -> float | None:
    """Ratio of energy the asset can recharge vs. what the next day is expected to
    need. >= 1.0 means the reserve is self-sustaining across the window; < 1.0 warns
    the reserve is drawing down. Returns None when nothing is needed."""
    if discharge_needed_mwh <= 0:
        return None
    return recharge_available_mwh / discharge_needed_mwh
