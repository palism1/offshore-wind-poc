"""Pre-event charging (Architecture Step 3 / initial_soc module).

Before a stress window begins, the reserve charges from available wind. This
returns the state of charge at the start of the event given a starting SoC
and the wind energy available to charge during the lead-up days, capped by
capacity and power.

Delegates to ``recharge.charge_forward``: the wind-to-storage rule lives in
one place and this module's job is to slice the schedule for the lead dates
and read off the resulting SoC. A lead day that falls inside an earlier
stress window is ``ACTIVE_EVENT``, so it charges off-peak only; that follows
from the one shared rule rather than a second policy.
"""

from __future__ import annotations

from owr import recharge
from owr.models import DayProfile, OperatingSchedule, StorageAsset


def charge_from_wind(
    starting_soc: float,
    lead_days: list[DayProfile],
    asset: StorageAsset,
    *,
    schedule: OperatingSchedule,
) -> float:
    """Roll a pre-event charging schedule forward and return the SoC reached.

    OPEN team question (``wind_charge_source``): the shipped profiles carry
    ISO-NE system-wide wind, which serves load and is almost never surplus.
    A dedicated offshore farm whose output goes to the reserve first, rather
    than to system load, is a different model that this engine does not
    assume. Under the new policy the model assumes the dedicated reading on
    pre-charge and off-peak hours: every watt of wind on those hours routes
    to storage, load or no load.
    """
    day_schedules = schedule.slice_for([d.date for d in lead_days])
    forecast = recharge.charge_forward(starting_soc, lead_days, day_schedules, asset)
    return forecast.final_soc_mwh
