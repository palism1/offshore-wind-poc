"""State-of-charge accounting.

Implements the Architecture doc state equation in one-way terms:

    soc(t+1) = soc(t) + charge(t) * one_way_eff - discharge(t) / one_way_eff

with a reserve floor the engine never discharges below. Callers pass
``asset.one_way_efficiency``, the per-leg split of the round-trip
``asset.efficiency`` (see `StorageAsset.one_way_efficiency`). Efficiency defaults
to 1.0, which reconciles the Overview's "100% efficient" assumption with the
Architecture doc's efficiency term (FACT_CHECK inconsistency #2); at 1.0 the split
is also 1.0, so the default case is unaffected by the one-way reframing.
"""

from __future__ import annotations

from owr.models import StorageAsset


def next_soc(
    soc: float, charge: float, discharge: float, one_way_efficiency: float
) -> float:
    """One step of ``soc(t+1) = soc(t) + charge*eff - discharge/eff``, where ``eff``
    is the per-leg (one-way) efficiency, not the round-trip figure."""
    if charge < 0 or discharge < 0:
        raise ValueError("charge and discharge must be non-negative")
    return soc + charge * one_way_efficiency - discharge / one_way_efficiency


def usable_energy(soc: float, asset: StorageAsset) -> float:
    """Energy that may be discharged before hitting the protected reserve floor."""
    return max(0.0, soc - asset.min_soc_mwh)


def clamp_discharge(soc: float, requested: float, asset: StorageAsset) -> float:
    """Limit a requested discharge to what is available above the reserve floor and
    within the per-hour power limit."""
    if requested < 0:
        raise ValueError("requested discharge must be non-negative")
    available = usable_energy(soc, asset)
    return min(requested, available, asset.power_mw)


def clamp_charge(soc: float, requested: float, asset: StorageAsset) -> float:
    """Limit a requested charge to remaining headroom and the per-hour power limit."""
    if requested < 0:
        raise ValueError("requested charge must be non-negative")
    headroom = max(0.0, asset.total_mwh - soc)
    # headroom is measured in stored MWh; charge*eff is what actually lands in the tank
    max_charge_by_headroom = headroom / asset.one_way_efficiency
    return min(requested, max_charge_by_headroom, asset.power_mw)
