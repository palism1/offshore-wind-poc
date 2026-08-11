"""Daily budgeting (Architecture Step 5 / budget module).

Priority, and the daily discharge budget. Week 4B change 7 replaced the "80% cap
times priority share" rule with Component 5's two-term minimum, revised
2026-08-06::

    daily_budget = min(
        available_charge / remaining_stress_days,
        energy_recharged_over_N_remaining_cycles / N_remaining_cycles,
    )

``priority()`` stays: ``DailyResult.priority`` is still in the JSON report and
the API's ``run_result_daily`` table (D13), so removing it needs an API break.
``simulator.simulate`` still computes it and no longer passes it to
``daily_budget``; the list is report-only from this phase on. See OPEN team
question ``priority_weighting_retired``.
"""

from __future__ import annotations

from owr.config import Config


def priority(demand_percentile: float, wind_forecast_frac: float, config: Config) -> float:
    """Architecture: ``Priority(d) = 0.7*DemandPercentile + 0.3*WindForecast``.

    Higher demand raises priority; higher forecast wind (self-supply) lowers the need
    to lean on storage, so the wind term is entered as (1 - forecast) elsewhere. Here
    we implement the doc's literal weighted sum; the simulator decides how to combine.

    Report-only as of Week 4B change 7 (D13): ``simulator.simulate`` still
    computes this per day and writes it to ``DailyResult.priority``, but no
    longer feeds it into ``daily_budget``. See OPEN team question
    ``priority_weighting_retired``.
    """
    return (
        config.priority_demand_weight * demand_percentile
        + config.priority_wind_weight * wind_forecast_frac
    )


def daily_budget(
    *,
    available_charge_mwh: float,
    remaining_stress_days: int,
    expected_recharge_mwh: float,
    remaining_cycles: int,
) -> float:
    """Energy (MWh) this day may discharge.

    Component 5, as revised 2026-08-06::

        daily_budget = min(
            available_charge / remaining_stress_days,
            energy_recharged_over_N_remaining_cycles / N_remaining_cycles,
        )

    Both terms come from the caller, so this function fixes no definition of a
    cycle. See ``simulator.simulate`` for the basis this engine applies and OPEN
    team question ``recharge_cycle_basis``.

    ``expected_recharge_mwh`` is a recharge **opportunity** over the remaining
    horizon, not the charge a tank could accept. The caller must not clamp it
    by headroom. ``available_charge_mwh`` is the only term that carries the
    state of charge. A headroom-clamped recharge term makes this function
    return less as the reserve holds more, and a full reserve then returns
    0.0 for every remaining day. See
    ``docs/architecture/PLAN_BUDGET_FULL_TANK_FIX.md``.

    Takes no ``Config``: the 80 percent energy budget rule is deleted from the
    engine. ``available_charge_mwh`` comes from ``soc_engine.usable_energy``,
    which already subtracts the protected reserve floor. That floor is the only
    limit on how much energy a day may use.
    """
    if remaining_stress_days < 1:
        raise ValueError("remaining_stress_days must be >= 1")
    if remaining_cycles < 1:
        raise ValueError("remaining_cycles must be >= 1")
    if available_charge_mwh < 0:
        raise ValueError("available_charge_mwh must be >= 0")
    if expected_recharge_mwh < 0:
        raise ValueError("expected_recharge_mwh must be >= 0")
    term_a = available_charge_mwh / remaining_stress_days
    term_b = expected_recharge_mwh / remaining_cycles
    return max(0.0, min(term_a, term_b))


def recharge_sufficiency_ratio(
    recharge_available_mwh: float, discharge_needed_mwh: float
) -> float | None:
    """Ratio of energy the asset can recharge vs. what the next day is expected to
    need. >= 1.0 means the reserve is self-sustaining across the window; < 1.0 warns
    the reserve is drawing down. Returns None when nothing is needed.

    ``simulator.simulate`` passes the next day's full usable energy as
    ``discharge_needed_mwh``. Before the ``energy_budget_fraction`` removal it
    passed 80 percent of that figure, so a day now needs 1.25 times the old
    recharge to report 1.0.
    """
    if discharge_needed_mwh <= 0:
        return None
    return recharge_available_mwh / discharge_needed_mwh
