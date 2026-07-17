"""Intra-day discharge allocation (Architecture Step 5 / dispatch module).

Split a day's discharge budget across its 24 hours between two objectives:

  * peak reduction  — shave the hours whose load is highest (Discharge_peak)
  * ramp smoothing  — cut the steepest hour-to-hour increases (Discharge_smooth)

subject to the hard constraint ``sum_t Discharge(t) <= Budget(d)`` and the per-hour
power limit. The relative emphasis is set by peak_weight / smooth_weight (a team
design choice; the doc names PeakWeight and SmoothWeight without fixed values).
"""

from __future__ import annotations

from owr.models import HOURS_PER_DAY


def _peak_signal(load: list[float]) -> list[float]:
    """How far each hour rises above the day's mean load (0 if at/below mean)."""
    mean = sum(load) / len(load)
    return [max(0.0, x - mean) for x in load]


def _ramp_signal(load: list[float]) -> list[float]:
    """Positive hour-to-hour increase into each hour (the ramp we want to smooth)."""
    signal = [0.0] * len(load)
    for t in range(1, len(load)):
        signal[t] = max(0.0, load[t] - load[t - 1])
    return signal


def allocate_discharge(
    hourly_load_mw: list[float],
    budget_mwh: float,
    power_mw: float,
    peak_weight: float = 0.5,
    smooth_weight: float = 0.5,
) -> tuple[list[float], list[float], list[float]]:
    """Return (discharge_total, discharge_peak, discharge_smooth), each length 24.

    Guarantees: every hour in [0, power_mw]; sum(discharge_total) <= budget_mwh
    (within floating-point tolerance).
    """
    if len(hourly_load_mw) != HOURS_PER_DAY:
        raise ValueError(f"hourly_load_mw must have {HOURS_PER_DAY} values")
    if budget_mwh <= 0 or power_mw <= 0:
        zeros = [0.0] * HOURS_PER_DAY
        return zeros, list(zeros), list(zeros)

    peak = _peak_signal(hourly_load_mw)
    ramp = _ramp_signal(hourly_load_mw)
    peak_sum = sum(peak)
    ramp_sum = sum(ramp)

    # Normalize each signal to a shape (sums to 1), then blend by the weights.
    peak_shape = [p / peak_sum if peak_sum > 0 else 0.0 for p in peak]
    ramp_shape = [r / ramp_sum if ramp_sum > 0 else 0.0 for r in ramp]
    total_weight = peak_weight + smooth_weight
    pw = peak_weight / total_weight if total_weight > 0 else 0.5
    sw = smooth_weight / total_weight if total_weight > 0 else 0.5

    # Provisional per-hour split of the budget.
    d_peak = [budget_mwh * pw * s for s in peak_shape]
    d_smooth = [budget_mwh * sw * s for s in ramp_shape]
    total = [p + s for p, s in zip(d_peak, d_smooth, strict=True)]

    # Enforce the per-hour power cap; redistribute the spilled energy proportionally
    # is out of POC scope — we simply clip, which keeps the budget constraint safe
    # (clipping only ever reduces discharge) and the power constraint exact.
    scale = [1.0] * HOURS_PER_DAY
    for t in range(HOURS_PER_DAY):
        if total[t] > power_mw:
            scale[t] = power_mw / total[t]
    d_peak = [d * scale[t] for t, d in enumerate(d_peak)]
    d_smooth = [d * scale[t] for t, d in enumerate(d_smooth)]
    total = [p + s for p, s in zip(d_peak, d_smooth, strict=True)]
    return total, d_peak, d_smooth
