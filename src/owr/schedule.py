"""Day-mode and peak-window classification (event-relative recharge).

The only module that decides what day a day is. Builds ``OperatingSchedule``
from two existing sources: ``stress_finder``'s detected windows and
``peak_window``'s rolling-window search. Every consumer — ``simulator``,
``recharge``/``initial_soc``, ``dispatch`` and ``metrics`` — reads the result
and none of them re-derives the classification rules.

``schedule.py`` is the only ``src/owr`` module that imports ``peak_window``
(a guard test in ``tests/test_schedule.py`` checks this): the searcher exists,
and this module is what connects it to the rest of the engine.
"""

from __future__ import annotations

from collections.abc import Sequence

from owr.config import Config
from owr.models import DayMode, DayProfile, DaySchedule, OperatingSchedule, StressWindow
from owr.peak_window import find_peak_window_for_day
from owr.stress_finder import find_stress_windows_for_config


def build_schedule(
    days: Sequence[DayProfile],
    *,
    stress_windows: Sequence[StressWindow],
    config: Config,
) -> OperatingSchedule:
    """Classify every day in ``days`` as ``NON_EVENT``, ``PRE_CHARGE`` or
    ``ACTIVE_EVENT``, and locate the peak window on every ``ACTIVE_EVENT`` day.

    Per day ``i``:

    1. Filter ``stress_windows`` to the ones that qualify under
       ``config.default_min_stress_window_days`` (requirements Section 5).
       Applied here even though ``find_stress_windows_at_percentile`` already
       filters, because a caller may pass windows detected at a different
       minimum.
    2. A day is ``ACTIVE_EVENT`` when it falls inside a qualifying window,
       ``PRE_CHARGE`` when a qualifying window starts later, else
       ``NON_EVENT``.
    3. On an ``ACTIVE_EVENT`` day only, run ``peak_window.find_peak_window_for_day``
       with ``days[i + 1]`` (or ``None`` on the last day) as the look-ahead day.

    Raises ``ValueError`` when the input dates are not strictly ascending
    (``OperatingSchedule.__post_init__`` enforces this).
    """
    qualifying = [w for w in stress_windows if w.days >= config.default_min_stress_window_days]

    schedules: list[DaySchedule] = []
    for i, day in enumerate(days):
        active = any(w.start <= day.date <= w.end for w in qualifying)
        future = any(w.start > day.date for w in qualifying)
        if active:
            mode = DayMode.ACTIVE_EVENT
        elif future:
            mode = DayMode.PRE_CHARGE
        else:
            mode = DayMode.NON_EVENT

        if mode is DayMode.ACTIVE_EVENT:
            next_day = days[i + 1] if i + 1 < len(days) else None
            peak = find_peak_window_for_day(
                day,
                next_day,
                window_hours=config.default_peak_window_hours,
                wrap=config.default_peak_window_wrap,
            )
            schedules.append(
                DaySchedule(
                    date=day.date, mode=mode, peak_window=peak, ramp_hours=config.default_ramp_hours
                )
            )
        else:
            schedules.append(DaySchedule(date=day.date, mode=mode, peak_window=None, ramp_hours=0))

    return OperatingSchedule(days=tuple(schedules))


def detect_and_build_schedule(days: Sequence[DayProfile], *, config: Config) -> OperatingSchedule:
    """Detect stress windows and build the schedule in one call.

    Only ``sweep.run_sweep`` uses this: ``cli`` and ``api`` already hold the
    detected windows (they report them) and pass them to ``build_schedule``
    directly, so no path detects stress windows twice.
    """
    windows = find_stress_windows_for_config(days, config)
    return build_schedule(days, stress_windows=windows, config=config)
