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

    F5: this is now the simulator's own surplus rule (`simulator.simulate`) with
    ``discharge = 0``, since no dispatch happens before the event: each hour
    charges only the wind above that hour's load, clamped to headroom and the
    power limit. Before this fix, pre-event charging counted the full wind series
    as chargeable regardless of load, while in-window charging took only the
    surplus above net load; the two paths disagreed, so `soc_at_window_start` was
    optimistic.

    OPEN team question (``wind_charge_source``): the shipped profiles carry
    ISO-NE system-wide wind, which serves load and is almost never surplus, so
    this rule returns the starting SoC unchanged on both example files. A
    dedicated offshore farm whose output goes to the reserve first, rather than to
    system load, is a different model that this engine does not assume.
    """
    soc = starting_soc
    for day in lead_days:
        wind = day.hourly_wind_mw or (0.0,) * HOURS_PER_DAY
        load = day.hourly_load_mw
        for hour in range(HOURS_PER_DAY):
            surplus = max(0.0, wind[hour] - max(0.0, load[hour]))
            charge = clamp_charge(soc, surplus, asset)
            soc = next_soc(
                soc, charge=charge, discharge=0.0, one_way_efficiency=asset.one_way_efficiency
            )
    return min(soc, asset.total_mwh)
