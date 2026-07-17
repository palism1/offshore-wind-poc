"""Rolling-window (MPC-style) simulation loop (Architecture Step 5 / simulator).

Orchestrates the per-day cycle over a stress window:

    for each day d in the window:
        priority(d)      -> budget(d)         (budget module)
        allocate budget  -> hourly discharge  (dispatch module)
        apply discharge, then off-peak recharge from wind  (soc_engine)
        record hourly + daily results, capacity margin      (metrics)

Model predictive control in spirit: each day is planned with that day's forecast and
executed one step at a time; state (SoC) carries forward. No I/O — inputs are plain
DayProfile objects, so the whole loop is unit-testable offline.
"""

from __future__ import annotations

from dataclasses import dataclass

from owr import budget as budget_mod
from owr import dispatch as dispatch_mod
from owr.config import DEFAULT_CONFIG, Config
from owr.models import HOURS_PER_DAY, DailyResult, DayProfile, HourlyResult, StorageAsset
from owr.soc_engine import clamp_charge, clamp_discharge, next_soc, usable_energy


@dataclass
class SimulationResult:
    daily: list[DailyResult]
    final_soc: float
    baseline_peak_mw: float  # worst hour of gross load across the window (no storage)
    reserve_peak_mw: float   # worst hour of net load across the window (with storage)


def simulate(
    asset: StorageAsset,
    window_days: list[DayProfile],
    starting_soc: float,
    available_capacity_mw: float | None = None,
    config: Config = DEFAULT_CONFIG,
    peak_weight: float = 0.5,
    smooth_weight: float = 0.5,
) -> SimulationResult:
    """Run the reserve through a stress window and return per-day + summary results."""
    if starting_soc < 0 or starting_soc > asset.total_mwh:
        raise ValueError("starting_soc must be within [0, total_mwh]")

    soc = starting_soc
    daily: list[DailyResult] = []
    baseline_peak = 0.0
    reserve_peak = 0.0

    # Priority of each remaining day, so budget(d) can take a fair share of the cap.
    priorities = [
        budget_mod.priority(d.demand_percentile, d.wind_forecast_frac, config)
        for d in window_days
    ]

    for i, day in enumerate(window_days):
        remaining_priority_sum = sum(priorities[i:])
        day_budget = budget_mod.daily_budget(
            usable_energy_mwh=usable_energy(soc, asset),
            day_priority=priorities[i],
            remaining_priority_sum=remaining_priority_sum,
            config=config,
        )

        load = list(day.hourly_load_mw)
        wind = list(day.hourly_wind_mw) if day.hourly_wind_mw else [0.0] * HOURS_PER_DAY
        d_total, d_peak, d_smooth = dispatch_mod.allocate_discharge(
            load, day_budget, asset.power_mw, peak_weight, smooth_weight
        )

        hourly: list[HourlyResult] = []
        discharged_today = 0.0
        for h in range(HOURS_PER_DAY):
            # Discharge, clamped again against the live SoC (budget is an energy cap,
            # but SoC must never cross the reserve floor within the day).
            discharge = clamp_discharge(soc, d_total[h], asset)
            # Scale the peak/smooth split to the actually-delivered discharge.
            ratio = discharge / d_total[h] if d_total[h] > 0 else 0.0
            dp, ds = d_peak[h] * ratio, d_smooth[h] * ratio
            soc = next_soc(soc, charge=0.0, discharge=discharge, efficiency=asset.efficiency)
            discharged_today += discharge

            # Off-peak recharge: any wind above this hour's (already reduced) net load
            # tops the reserve back up, capped by headroom and power.
            net = load[h] - discharge
            surplus_wind = max(0.0, wind[h] - max(0.0, net))
            charge = clamp_charge(soc, surplus_wind, asset)
            soc = next_soc(soc, charge=charge, discharge=0.0, efficiency=asset.efficiency)

            net_load_mw = load[h] - discharge + charge
            margin = (
                available_capacity_mw - net_load_mw
                if available_capacity_mw is not None
                else None
            )
            baseline_peak = max(baseline_peak, load[h])
            reserve_peak = max(reserve_peak, net_load_mw)
            hourly.append(
                HourlyResult(
                    ts_hour=h,
                    soc=soc,
                    charge=charge,
                    discharge=discharge,
                    discharge_peak=dp,
                    discharge_smooth=ds,
                    gross_load=load[h],
                    net_load=net_load_mw,
                    capacity_margin=margin,
                )
            )

        # How much the next day is expected to need vs. what we can recharge.
        next_need = (
            config.energy_budget_fraction * usable_energy(soc, asset)
            if i + 1 < len(window_days)
            else 0.0
        )
        recharge_available = sum(h.charge for h in hourly)
        daily.append(
            DailyResult(
                date=day.date,
                budget=day_budget,
                priority=priorities[i],
                usable_energy=usable_energy(soc, asset),
                recharge_sufficiency_ratio=budget_mod.recharge_sufficiency_ratio(
                    recharge_available, next_need
                ),
                hourly=hourly,
            )
        )

    return SimulationResult(
        daily=daily,
        final_soc=soc,
        baseline_peak_mw=baseline_peak,
        reserve_peak_mw=reserve_peak,
    )
