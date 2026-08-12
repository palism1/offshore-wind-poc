"""Intra-day discharge allocation (Architecture Step 5 / dispatch module).

Split a day's discharge budget across a planned ramp-up -> peak -> ramp-down
block (``DispatchWindow``) between two objectives:

  * peak reduction  — the peak-window hours (Discharge_peak)
  * ramp smoothing  — the ramp-up and ramp-down hours (Discharge_smooth)

subject to the hard constraint ``sum_t Discharge(t) <= Budget(d)`` and the
per-hour power limit.

D7: the load-derived shape (mean-relative peak signal, hour-to-hour ramp
signal) is gone. The peak-window search already used the load to pick the
block; re-shaping inside the block by load cannot be made truncation-invariant
without a caller-visible squeeze (requirements Section 11's second bullet).
The allocation is now purely positional: divisors are the *planned* peak and
ramp slot counts, counted before truncation, so an hour's share depends only
on the budget, the two weights and the planned slot counts — never on which
slots survived the day boundary (Section 8c, the no-squeeze guarantee).
"""

from __future__ import annotations

from owr.models import HOURS_PER_DAY, DispatchWindow


def allocate_discharge(
    *,
    dispatch_window: DispatchWindow | None,
    budget_mwh: float,
    power_mw: float,
    peak_weight: float = 0.5,
    smooth_weight: float = 0.5,
) -> tuple[list[float], list[float], list[float]]:
    """Return (discharge_total, discharge_peak, discharge_smooth), each length 24.

    Guarantees: every hour in [0, power_mw]; sum(discharge_total) <= budget_mwh
    (within floating-point tolerance). No dispatch window, or a non-positive
    budget or power, returns three zero lists.
    """
    zeros = [0.0] * HOURS_PER_DAY
    if dispatch_window is None or budget_mwh <= 0 or power_mw <= 0:
        return list(zeros), list(zeros), list(zeros)

    total_weight = peak_weight + smooth_weight
    peak_weight_norm = peak_weight / total_weight if total_weight > 0 else 0.5
    smooth_weight_norm = smooth_weight / total_weight if total_weight > 0 else 0.5

    planned_peak = len(dispatch_window.peak_slots)
    planned_ramp = 2 * dispatch_window.ramp_hours

    # Section 8a: fold on the CONFIGURED ramp count (dispatch_window.ramp_hours),
    # never on how many ramp slots survive truncation. A configuration with no
    # ramp block is a design choice; an out-of-day ramp slot is an event
    # boundary, and the two must not be treated alike (see the module docstring
    # of models.DispatchWindow and revision-log finding 6 of the plan).
    if planned_ramp == 0:
        peak_pool = budget_mwh
        ramp_pool = 0.0
    else:
        peak_pool = budget_mwh * peak_weight_norm
        ramp_pool = budget_mwh * smooth_weight_norm

    per_peak_slot = peak_pool / planned_peak if planned_peak > 0 else 0.0
    per_ramp_slot = ramp_pool / planned_ramp if planned_ramp > 0 else 0.0

    d_peak = [0.0] * HOURS_PER_DAY
    d_smooth = [0.0] * HOURS_PER_DAY
    for h in dispatch_window.peak_hours:
        d_peak[h] = per_peak_slot
    for h in dispatch_window.ramp_up_hours:
        d_smooth[h] = per_ramp_slot
    for h in dispatch_window.ramp_down_hours:
        d_smooth[h] = per_ramp_slot

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
