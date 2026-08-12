"""The wind-to-storage rule (event-relative recharge).

One rule, shared by ``simulator``, ``initial_soc`` and the budget forecast.
Replaces the three surplus-wind expressions that used to disagree (D1):
``simulator.simulate``'s hour loop, ``simulator._surplus_wind_recharge_mwh``,
and ``initial_soc.charge_from_wind``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from owr.models import HOURS_PER_DAY, DayProfile, DaySchedule, HourState, StorageAsset
from owr.soc_engine import clamp_charge, next_soc


def charge_request_mw(wind_mw: float, state: HourState) -> float:
    """Wind routed to storage in one hour, before the SoC and power clamps.

    A negative wind value floors at 0.0, which is what both retired surplus
    expressions did. See D13: this function does not widen the engine's input
    validation.
    """
    return max(0.0, wind_mw) if state.charges_from_wind else 0.0


def _require_aligned(days: Sequence[DayProfile], day_schedules: Sequence[DaySchedule]) -> None:
    """Shared guard for ``charge_forward`` and ``recharge_opportunity_mwh``.

    Raises ``ValueError`` when ``days`` and ``day_schedules`` differ in length
    or a date does not match at the same position.
    """
    if len(days) != len(day_schedules):
        raise ValueError(
            f"days (len {len(days)}) and day_schedules (len {len(day_schedules)}) must match"
        )
    for day, day_schedule in zip(days, day_schedules, strict=True):
        if day.date != day_schedule.date:
            raise ValueError(f"date mismatch: day {day.date} vs day_schedule {day_schedule.date}")


@dataclass(frozen=True)
class ChargeForecast:
    final_soc_mwh: float
    # Energy accepted at the terminals, after every clamp. No budget term
    # reads this field: PLAN_BUDGET_FULL_TANK_FIX.md moved the budget's
    # recharge term to recharge_opportunity_mwh, below. A future caller must
    # not wire this field into a budget term; that is the defect the plan
    # fixes.
    charged_mwh: float


def recharge_opportunity_mwh(
    days: Sequence[DayProfile], day_schedules: Sequence[DaySchedule]
) -> float:
    """The recharge term of ``budget.daily_budget``: Component 5's "available
    recharge throughout the remaining forecast horizon."

    An opportunity, not a dispatch. It takes no starting SoC and no
    ``StorageAsset``, so no state of charge can enter it by construction. On
    a charging hour its per-hour value equals ``metrics.
    recharge_opportunity_mw``'s value for the same hour, so the budget term
    and the reported metric share one definition.

    A caller must not clamp this by headroom. Doing that puts the SoC into
    both terms of ``daily_budget``'s minimum: the budget then falls as
    stored energy rises, and a full reserve floors the whole minimum at 0.0.
    See ``docs/architecture/PLAN_BUDGET_FULL_TANK_FIX.md``.

    Applies no power clamp either. Whether to cap this at ``asset.power_mw``
    stays an open team question; see Section 4 item 5 of the plan above.

    Raises ``ValueError`` when ``days`` and ``day_schedules`` differ in length
    or a date does not match at the same position.
    """
    _require_aligned(days, day_schedules)
    total = 0.0
    for day, day_schedule in zip(days, day_schedules, strict=True):
        wind = day.hourly_wind_mw if day.hourly_wind_mw else (0.0,) * HOURS_PER_DAY
        for hour in range(HOURS_PER_DAY):
            total += charge_request_mw(wind[hour], day_schedule.hours[hour])
    return total


def charge_forward(
    starting_soc: float,
    days: Sequence[DayProfile],
    day_schedules: Sequence[DaySchedule],
    asset: StorageAsset,
) -> ChargeForecast:
    """Roll the wind-to-storage rule forward over ``days`` and return the SoC
    reached and the energy accepted.

    Serves ``initial_soc`` only, where the headroom clamp is correct: that
    caller wants the SoC a tank would reach, not a resource-side opportunity.
    No budget term reads this forecast's output; see
    ``recharge_opportunity_mwh``, above, for that role.

    Models no discharge over its horizon. Without discharge the tank fills
    sooner, so ``charged_mwh`` is a lower bound on the recharge a real day
    would accept.

    Raises ``ValueError`` when ``days`` and ``day_schedules`` differ in length
    or a date does not match at the same position.
    """
    _require_aligned(days, day_schedules)

    soc = starting_soc
    charged_mwh = 0.0
    for day, day_schedule in zip(days, day_schedules, strict=True):
        wind = day.hourly_wind_mw if day.hourly_wind_mw else (0.0,) * HOURS_PER_DAY
        for hour in range(HOURS_PER_DAY):
            request = charge_request_mw(wind[hour], day_schedule.hours[hour])
            charge = clamp_charge(soc, request, asset)
            soc = next_soc(
                soc, charge=charge, discharge=0.0, one_way_efficiency=asset.one_way_efficiency
            )
            charged_mwh += charge

    return ChargeForecast(final_soc_mwh=min(soc, asset.total_mwh), charged_mwh=charged_mwh)
