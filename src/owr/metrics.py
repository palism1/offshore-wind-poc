"""Outcome metrics (Architecture Step 6 / metrics module).

The doc's Step 6 is one of the blank/duplicated sections (FACT_CHECK inconsistency
#4). These are the well-defined metrics from the outline and Phase 3 plan; anything
requiring the missing text is left out rather than invented.
"""

from __future__ import annotations


def net_load(gross_load_mw: float, discharge_mw: float, charge_mw: float = 0.0) -> float:
    """Load the grid must serve after the reserve acts: gross - discharge + charge."""
    return gross_load_mw - discharge_mw + charge_mw


def capacity_margin(available_capacity_mw: float, net_load_mw: float) -> float:
    """Headroom (MW) between firm available capacity and the net load it must serve.
    Negative means a shortfall."""
    return available_capacity_mw - net_load_mw


def severity_reduction(baseline_peak_mw: float, reserve_peak_mw: float) -> float:
    """Fractional reduction in the peak net load achieved by the reserve vs. the
    direct-to-grid baseline (no storage). 0.0 = no help; 1.0 = peak eliminated."""
    if baseline_peak_mw <= 0:
        raise ValueError("baseline_peak_mw must be positive")
    return (baseline_peak_mw - reserve_peak_mw) / baseline_peak_mw


def equivalent_full_cycles(discharged_mwh: float, *, rated_energy_mwh: float) -> float:
    """Total energy discharged over a period divided by the asset's rated energy
    capacity. Settled 2026-07-28 (HANDOFF.md decision 5): the metric that survives
    partial cycles, and what degradation and warranty terms are quoted against. A
    half-depth discharge counts 0.5; one event containing a mid-event recharge can
    count more than 1.

    ``discharged_mwh`` is energy **delivered**, i.e. drawn out of the asset at the
    terminals, not energy drawn from the tank before the efficiency term — the two
    differ by the efficiency term. ``rated_energy_mwh`` is keyword-only: both
    arguments are bare same-unit floats, and a swapped call (e.g. ``(1000, 250)``
    instead of ``(250, rated_energy_mwh=1000)``) would silently return a plausible
    but wrong number rather than raising.
    """
    if rated_energy_mwh <= 0:
        raise ValueError("rated_energy_mwh must be positive")
    if discharged_mwh < 0:
        raise ValueError("discharged_mwh must be non-negative")
    return discharged_mwh / rated_energy_mwh
