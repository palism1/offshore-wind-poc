"""Sphere energy, power and geometry from first principles.

Pure module: derives "20 MWh" and its siblings from whichever two of
{diameter, head, energy} the team fixes, rather than shipping them as hard-coded
numbers. See `docs/DATA_SOURCES.md` [4] and `docs/HANDOFF.md`'s third-reply block
for the spec inconsistency this recovers.

**Not wired anywhere.** No caller in this codebase uses this module yet.
`StorageAsset.total_mwh` keeps taking MWh directly. Deriving it from geometry is a
follow-up gated on the team fixing two of {D, h, E} and on the round-trip-vs-one-way
efficiency question — both still open. See `HANDOFF.md`.
"""

from __future__ import annotations

import math

RHO_SEAWATER_KG_M3: float = 1025.0  # seawater density used throughout DATA_SOURCES [4]
GRAVITY_M_S2: float = 9.81
JOULES_PER_MWH: float = 3.6e9


def _require_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _require_efficiency(efficiency: float) -> None:
    if not 0.0 < efficiency <= 1.0:
        raise ValueError("efficiency must be in (0, 1]")


# --- geometry ----------------------------------------------------------------


def sphere_internal_diameter_m(outer_diameter_m: float, wall_thickness_m: float) -> float:
    """Internal diameter of a sphere shell: outer minus two wall thicknesses."""
    _require_positive(outer_diameter_m, "outer_diameter_m")
    if wall_thickness_m < 0:
        raise ValueError("wall_thickness_m must be non-negative")
    if 2 * wall_thickness_m >= outer_diameter_m:
        raise ValueError("2 * wall_thickness_m must be less than outer_diameter_m")
    return outer_diameter_m - 2 * wall_thickness_m


def sphere_internal_volume_m3(outer_diameter_m: float, wall_thickness_m: float) -> float:
    """Working (internal) volume of the sphere shell."""
    internal_diameter_m = sphere_internal_diameter_m(outer_diameter_m, wall_thickness_m)
    return (math.pi / 6.0) * internal_diameter_m**3


def sphere_outer_diameter_for_volume_m(volume_m3: float, wall_thickness_m: float) -> float:
    """Invert `sphere_internal_volume_m3`: the outer diameter whose internal volume
    (at this wall thickness) equals `volume_m3`."""
    _require_positive(volume_m3, "volume_m3")
    if wall_thickness_m < 0:
        raise ValueError("wall_thickness_m must be non-negative")
    internal_diameter_m = (6.0 * volume_m3 / math.pi) ** (1.0 / 3.0)
    return internal_diameter_m + 2 * wall_thickness_m


# --- generating (discharge) direction: E = rho * g * V * h * eta -------------


def generating_energy_mwh(*, volume_m3: float, head_m: float, efficiency: float) -> float:
    """Energy delivered at the terminals on discharge for a full working volume at
    a given hydraulic head.

    `efficiency` here is the **one-way generating** efficiency. This is the
    interpretation under which this module reproduces `DATA_SOURCES.md` [4]'s own
    arithmetic — the team has not decided whether the source's stated 0.70 is
    round-trip or one-way; see `one_way_from_round_trip` / `round_trip_from_one_way`.
    """
    _require_positive(volume_m3, "volume_m3")
    _require_positive(head_m, "head_m")
    _require_efficiency(efficiency)
    joules = RHO_SEAWATER_KG_M3 * GRAVITY_M_S2 * volume_m3 * head_m * efficiency
    return joules / JOULES_PER_MWH


def volume_for_energy_m3(*, energy_mwh: float, head_m: float, efficiency: float) -> float:
    """Invert `generating_energy_mwh` for volume."""
    _require_positive(energy_mwh, "energy_mwh")
    _require_positive(head_m, "head_m")
    _require_efficiency(efficiency)
    joules = energy_mwh * JOULES_PER_MWH
    return joules / (RHO_SEAWATER_KG_M3 * GRAVITY_M_S2 * head_m * efficiency)


def head_for_energy_m(*, energy_mwh: float, volume_m3: float, efficiency: float) -> float:
    """Invert `generating_energy_mwh` for head."""
    _require_positive(energy_mwh, "energy_mwh")
    _require_positive(volume_m3, "volume_m3")
    _require_efficiency(efficiency)
    joules = energy_mwh * JOULES_PER_MWH
    return joules / (RHO_SEAWATER_KG_M3 * GRAVITY_M_S2 * volume_m3 * efficiency)


# --- power: generating P = rho*g*Q*h*eta ; pumping P = rho*g*Q*h/eta ---------


def generating_power_mw(*, flow_m3_s: float, head_m: float, efficiency: float) -> float:
    """Discharge (turbine) power at a given flow and head."""
    _require_positive(flow_m3_s, "flow_m3_s")
    _require_positive(head_m, "head_m")
    _require_efficiency(efficiency)
    watts = RHO_SEAWATER_KG_M3 * GRAVITY_M_S2 * flow_m3_s * head_m * efficiency
    return watts / 1.0e6


def pumping_power_mw(*, flow_m3_s: float, head_m: float, efficiency: float) -> float:
    """Charge (pump) power at a given flow and head.

    Divides by efficiency where `generating_power_mw` multiplies, so at the same
    `(Q, h, eta)` the pump draws `1 / eta**2` times what the turbine outputs — the
    ratio `dispatch.py` will eventually need when charge and discharge power stop
    being modeled as the same number at the same flow.
    """
    _require_positive(flow_m3_s, "flow_m3_s")
    _require_positive(head_m, "head_m")
    _require_efficiency(efficiency)
    watts = RHO_SEAWATER_KG_M3 * GRAVITY_M_S2 * flow_m3_s * head_m / efficiency
    return watts / 1.0e6


def flow_for_generating_power_m3_s(*, power_mw: float, head_m: float, efficiency: float) -> float:
    """Invert `generating_power_mw` for flow."""
    _require_positive(power_mw, "power_mw")
    _require_positive(head_m, "head_m")
    _require_efficiency(efficiency)
    watts = power_mw * 1.0e6
    return watts / (RHO_SEAWATER_KG_M3 * GRAVITY_M_S2 * head_m * efficiency)


def flow_for_pumping_power_m3_s(*, power_mw: float, head_m: float, efficiency: float) -> float:
    """Invert `pumping_power_mw` for flow."""
    _require_positive(power_mw, "power_mw")
    _require_positive(head_m, "head_m")
    _require_efficiency(efficiency)
    watts = power_mw * 1.0e6
    return watts * efficiency / (RHO_SEAWATER_KG_M3 * GRAVITY_M_S2 * head_m)


# --- the {diameter, head, energy} trio — fix any two, wall thickness and -----
# --- efficiency are always required, get the third ---------------------------


def sphere_energy_mwh(
    *, outer_diameter_m: float, wall_thickness_m: float, head_m: float, efficiency: float
) -> float:
    """Energy for a sphere of given outer diameter and wall thickness at a given
    head. "Fix two of {D, h, E}" means two at a given wall thickness and
    efficiency — this function fixes D and h."""
    volume_m3 = sphere_internal_volume_m3(outer_diameter_m, wall_thickness_m)
    return generating_energy_mwh(volume_m3=volume_m3, head_m=head_m, efficiency=efficiency)


def sphere_head_m(
    *, outer_diameter_m: float, wall_thickness_m: float, energy_mwh: float, efficiency: float
) -> float:
    """Head required for a sphere of given outer diameter and wall thickness to
    deliver `energy_mwh`. Fixes D and E."""
    volume_m3 = sphere_internal_volume_m3(outer_diameter_m, wall_thickness_m)
    return head_for_energy_m(energy_mwh=energy_mwh, volume_m3=volume_m3, efficiency=efficiency)


def sphere_outer_diameter_m(
    *, head_m: float, energy_mwh: float, efficiency: float, wall_thickness_m: float
) -> float:
    """**Outer** diameter of a sphere (internal + 2 x wall) needed to deliver
    `energy_mwh` at `head_m`. Fixes h and E. See `docs/DATA_SOURCES.md` [4] —
    its "~46 m" figure for this case is the internal diameter, not the outer one."""
    volume_m3 = volume_for_energy_m3(energy_mwh=energy_mwh, head_m=head_m, efficiency=efficiency)
    return sphere_outer_diameter_for_volume_m(volume_m3, wall_thickness_m)


# --- efficiency convention helpers — conversion only, no decision ------------


def one_way_from_round_trip(round_trip_efficiency: float) -> float:
    """Convert a round-trip efficiency to its one-way (pump or turbine)
    equivalent, assuming pump and turbine are equally efficient: `sqrt(rt)`.

    Conversion only — it does not choose a side. The team has not decided
    whether `DATA_SOURCES.md` [4]'s 0.70 is round-trip or one-way
    (`HANDOFF.md` third-reply block). If 0.70 is round-trip, one-way is
    `sqrt(0.70) = 0.8367`. If 0.70 is already the one-way turbine figure, its
    round-trip equivalent is `0.70**2 = 0.49` (see `round_trip_from_one_way`).
    """
    _require_efficiency(round_trip_efficiency)
    return math.sqrt(round_trip_efficiency)


def round_trip_from_one_way(one_way_efficiency: float) -> float:
    """Convert a one-way efficiency to its round-trip equivalent, assuming pump
    and turbine are equally efficient: `one_way**2`.

    Conversion only — it does not choose a side. The team has not decided
    whether `DATA_SOURCES.md` [4]'s 0.70 is round-trip or one-way
    (`HANDOFF.md` third-reply block). If 0.70 is the one-way turbine figure,
    round-trip is `0.70**2 = 0.49`. If 0.70 is round-trip, one-way is
    `sqrt(0.70) = 0.8367` (see `one_way_from_round_trip`).
    """
    _require_efficiency(one_way_efficiency)
    return one_way_efficiency**2
