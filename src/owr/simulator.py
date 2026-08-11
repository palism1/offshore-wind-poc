"""Rolling-window (MPC-style) simulation loop (Architecture Step 5 / simulator).

Orchestrates the per-day cycle over a span of days, event-relative:

    for each day d in the span:
        schedule.for_date(d) says the day's mode and hour states
        priority(d), report-only (D13) -> budget(d) on ACTIVE_EVENT days only
        allocate budget over the day's dispatch window -> hourly discharge (dispatch)
        apply discharge, then event-relative charge from wind (soc_engine)
        record hourly + daily results, capacity margin (metrics)

Charge and discharge are mutually exclusive by construction: ``recharge.
charge_request_mw`` returns 0.0 on every dispatch hour, and ``dispatch.
allocate_discharge`` returns 0.0 on every hour outside the day's dispatch
window. Which hour does what is decided once, by ``schedule.build_schedule``,
and this module only reads that decision — it never re-derives it (D1, D2).

Week 4B change 7 replaced ``budget.daily_budget``'s "80% cap times priority
share" rule with Component 5's two-term minimum. ``priority(d)`` is still
computed for the report; it no longer feeds the budget (D13, OPEN team
question ``priority_weighting_retired``).

The budget's recharge term now comes from ``recharge.recharge_opportunity_mwh``,
not from ``recharge.charge_forward``: the per-hour clamp and state update that
``charge_forward`` used to roll forward drop out of the per-day loop, so the
loop shape stays O(n^2 * 24) but does less work per iteration. See
``docs/architecture/PLAN_BUDGET_FULL_TANK_FIX.md``.

Model predictive control in spirit: each day is planned with that day's forecast and
executed one step at a time; state (SoC) carries forward. No I/O — inputs are plain
DayProfile objects, so the whole loop is unit-testable offline.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from owr import budget as budget_mod
from owr import dispatch as dispatch_mod
from owr import recharge as recharge_mod
from owr.config import DEFAULT_CONFIG, Config
from owr.models import (
    HOURS_PER_DAY,
    DailyResult,
    DayMode,
    DayProfile,
    HourlyResult,
    OperatingSchedule,
    StorageAsset,
)
from owr.soc_engine import clamp_charge, clamp_discharge, next_soc, usable_energy

HOURLY_FRAME_COLUMNS: tuple[str, ...] = (
    "date", "ts_hour", "soc", "charge", "discharge", "discharge_peak",
    "discharge_smooth", "gross_load", "net_load", "capacity_margin",
)
DAILY_FRAME_COLUMNS: tuple[str, ...] = (
    "date", "budget", "priority", "usable_energy", "recharge_sufficiency_ratio",
)

# Every hourly column is float64 except the two named below. The map is derived from
# HOURLY_FRAME_COLUMNS so the schema keeps one source of truth. The dtypes must stay
# explicit: pandas infers ``object`` for an all-``None`` capacity_margin column and for
# every column of an empty frame (measurement M16).
_HOURLY_FRAME_DTYPES: dict[str, str] = {
    column: {"date": "object", "ts_hour": "int64"}.get(column, "float64")
    for column in HOURLY_FRAME_COLUMNS
}


@dataclass
class SimulationResult:
    daily: list[DailyResult]
    final_soc: float
    baseline_peak_mw: float  # worst hour of gross load across the window (no storage)
    reserve_peak_mw: float   # worst hour of net load across the window (with storage);
    # net load is gross load minus discharge (D2), so reserve_peak_mw <= baseline_peak_mw always

    def hourly_frame(self) -> pd.DataFrame:
        """The Component 6 hourly result table, one row per simulated hour.

        ``date`` stays an ``object`` column of ``datetime.date``, never ``datetime64``
        (see docs/archive/plans/PLAN_PANDAS_ADOPTION.md risk 3). ``capacity_margin`` is always
        ``float64``, ``NaN`` when the caller passed no ``available_capacity_mw``
        (measurement M16: an all-``None`` column must be built with an explicit
        dtype, or it silently infers ``object``).

        Column names keep the ``HourlyResult`` field names rather than the
        architecture doc's names, because a rename would misstate what the field
        holds:

        | Frame column     | Architecture doc field    | Component |
        |------------------|----------------------------|-----------|
        | ``gross_load``   | ``observed_load``          | 6         |
        | ``net_load``     | ``dispatched_net_load``    | 6         |
        | ``discharge``    | ``discharge_power``        | 5         |
        | ``charge``       | ``charge_power``            | 5         |
        | ``soc``          | ``updated_SOC``             | 6         |
        | ``capacity_margin`` | derived field "capacity margin" | 6    |

        The doc also names fields this engine does not model: ``charge_dispatched``,
        ``recharge_opportunity``, ``dispatch_reason``, ``remaining_capacity``,
        ``observed_net_load``, ``oil_generation_actual``, ``gas_generation_actual``,
        ``wind_generation_actual``.

        D2: ``net_load`` equals ``gross_load - discharge``. ``charge`` now carries
        event-relative charging (``recharge.charge_request_mw``, gated by the
        hour's ``HourState``) and still never enters ``net_load``, because that
        wind is never supplied to the grid to net back out. So
        ``capacity_dispatched(t)`` equals ``discharge(t)`` and equals
        ``gross_load - net_load`` for any later per-event metric (CMDR, SWE, FOP).
        """
        rows = [{"date": day.date, **vars(hr)} for day in self.daily for hr in day.hourly]
        frame = pd.DataFrame(rows, columns=list(HOURLY_FRAME_COLUMNS))
        return frame.astype(_HOURLY_FRAME_DTYPES)

    def daily_frame(self) -> pd.DataFrame:
        """The Component 4 daily result table, one row per simulated day.

        ``date`` stays an ``object`` column of ``datetime.date``, never
        ``datetime64``. ``recharge_sufficiency_ratio`` is always ``float64``, ``NaN``
        on the last day of a window (measurement M16 is the reason for the explicit
        dtype).
        """
        dates = [day.date for day in self.daily]
        budgets = [day.budget for day in self.daily]
        priorities = [day.priority for day in self.daily]
        usable_energies = [day.usable_energy for day in self.daily]
        ratios = [day.recharge_sufficiency_ratio for day in self.daily]
        return pd.DataFrame(
            {
                "date": pd.Series(dates, dtype="object"),
                "budget": pd.Series(budgets, dtype="float64"),
                "priority": pd.Series(priorities, dtype="float64"),
                "usable_energy": pd.Series(usable_energies, dtype="float64"),
                "recharge_sufficiency_ratio": pd.Series(ratios, dtype="float64"),
            },
            columns=list(DAILY_FRAME_COLUMNS),
        )


def simulate(
    asset: StorageAsset,
    window_days: list[DayProfile],
    starting_soc: float,
    *,
    schedule: OperatingSchedule,
    available_capacity_mw: float | None = None,
    config: Config = DEFAULT_CONFIG,
    peak_weight: float = 0.5,
    smooth_weight: float = 0.5,
) -> SimulationResult:
    """Run the reserve over ``window_days`` and return per-day + summary results.

    ``schedule`` is required, with no default and no internal detection
    fallback: a caller must build it once (``schedule.build_schedule`` or
    ``schedule.detect_and_build_schedule``) and pass the same object to every
    consumer, so the reported windows and the simulated windows are always the
    same objects (D2).
    """
    if starting_soc < 0 or starting_soc > asset.total_mwh:
        raise ValueError("starting_soc must be within [0, total_mwh]")

    day_schedules = schedule.slice_for([d.date for d in window_days])

    soc = starting_soc
    daily: list[DailyResult] = []
    baseline_peak = 0.0
    reserve_peak = 0.0

    # Priority per day is report-only as of Week 4B change 7 (D13): still
    # computed and written to DailyResult.priority, no longer passed into
    # daily_budget. See OPEN team question priority_weighting_retired.
    priorities = [
        budget_mod.priority(d.demand_percentile, d.wind_forecast_frac, config)
        for d in window_days
    ]

    for i, day in enumerate(window_days):
        day_schedule = day_schedules[i]
        # D14: the recharge-cycle basis this engine applies is the remaining
        # days of the current span, both for N_remaining_cycles and for the
        # count remaining_stress_days divides by. See OPEN team question
        # recharge_cycle_basis for the event-level alternative. D15: on a
        # multi-event span this divisor mixes gap and unrelated-event days
        # with the numerator below, which is now schedule-aware. The
        # numerator is the horizon recharge opportunity
        # (recharge.recharge_opportunity_mwh): it carries no state of
        # charge, so D15's day-set mismatch is a mismatch of which days are
        # counted, never a mismatch of what the tank could accept.
        remaining_days = window_days[i:]
        remaining_cycles = len(remaining_days)
        if day_schedule.mode is DayMode.ACTIVE_EVENT:
            day_budget = budget_mod.daily_budget(
                available_charge_mwh=usable_energy(soc, asset),
                remaining_stress_days=remaining_cycles,
                expected_recharge_mwh=recharge_mod.recharge_opportunity_mwh(
                    remaining_days, day_schedules[i:]
                ),
                remaining_cycles=remaining_cycles,
            )
        else:
            day_budget = 0.0

        load = list(day.hourly_load_mw)
        wind = list(day.hourly_wind_mw) if day.hourly_wind_mw else [0.0] * HOURS_PER_DAY
        hourly_discharge, hourly_discharge_peak, hourly_discharge_smooth = (
            dispatch_mod.allocate_discharge(
                dispatch_window=day_schedule.dispatch_window,
                budget_mwh=day_budget,
                power_mw=asset.power_mw,
                peak_weight=peak_weight,
                smooth_weight=smooth_weight,
            )
        )

        hourly: list[HourlyResult] = []
        for h in range(HOURS_PER_DAY):
            # Discharge, clamped again against the live SoC (budget is an energy cap,
            # but SoC must never cross the reserve floor within the day).
            discharge = clamp_discharge(soc, hourly_discharge[h], asset)
            # Scale the peak/smooth split to the actually-delivered discharge.
            ratio = discharge / hourly_discharge[h] if hourly_discharge[h] > 0 else 0.0
            discharge_peak_scaled = hourly_discharge_peak[h] * ratio
            discharge_smooth_scaled = hourly_discharge_smooth[h] * ratio
            soc = next_soc(
                soc, charge=0.0, discharge=discharge, one_way_efficiency=asset.one_way_efficiency
            )

            # Event-relative charge: request comes from the hour's classification,
            # never from load or discharge. Mutually exclusive with discharge by
            # construction (charges_from_wind is False on every dispatch hour).
            request = recharge_mod.charge_request_mw(wind[h], day_schedule.hours[h])
            charge = clamp_charge(soc, request, asset)
            soc = next_soc(
                soc, charge=charge, discharge=0.0, one_way_efficiency=asset.one_way_efficiency
            )

            # D2: net_load_mw = gross_load - discharge. Charging never enters
            # net_load. The baseline peak (below) never counts the charging
            # draw either, so the metric compares two worlds that differ by storage
            # alone; the grid never supplies the charged wind, so charging from it
            # adds no grid load to net out.
            net_load_mw = load[h] - discharge
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
                    discharge_peak=discharge_peak_scaled,
                    discharge_smooth=discharge_smooth_scaled,
                    gross_load=load[h],
                    net_load=net_load_mw,
                    capacity_margin=margin,
                )
            )

        # The next day may need every MWh above the protected reserve floor.
        # usable_energy already subtracts that floor, and no further fraction
        # applies. Zero on the last day, which makes the ratio None.
        usable_at_close = usable_energy(soc, asset)
        next_need = usable_at_close if i + 1 < len(window_days) else 0.0
        recharge_available = sum(h.charge for h in hourly)
        daily.append(
            DailyResult(
                date=day.date,
                budget=day_budget,
                priority=priorities[i],
                usable_energy=usable_at_close,
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
