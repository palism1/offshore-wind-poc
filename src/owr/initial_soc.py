"""Pre-event charging (Architecture Step 3 / initial_soc module).

Before a stress window begins, the reserve charges from available wind. This returns
the state of charge at the start of the event given a starting SoC and the wind
energy available to charge during the lead-up days, capped by capacity and power.
"""

from __future__ import annotations

from owr.models import HOURS_PER_DAY, DayProfile, StorageAsset
from owr.soc_engine import clamp_charge, next_soc


def charge_from_wind(
    starting_soc: float,
    lead_days: list[DayProfile],
    asset: StorageAsset,
) -> float:
    """Roll a pre-event charging schedule forward and return the SoC reached.

    Each lead-up day contributes its hourly wind availability as charging power,
    clamped to headroom and the power limit. Days without a wind profile contribute
    nothing.
    """
    soc = starting_soc
    for day in lead_days:
        wind = day.hourly_wind_mw or (0.0,) * HOURS_PER_DAY
        for hour in range(HOURS_PER_DAY):
            charge = clamp_charge(soc, wind[hour], asset)
            soc = next_soc(
                soc, charge=charge, discharge=0.0, one_way_efficiency=asset.one_way_efficiency
            )
    return min(soc, asset.total_mwh)
