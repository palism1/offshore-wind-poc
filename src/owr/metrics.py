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
