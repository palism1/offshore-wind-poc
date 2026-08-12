"""Tests for owr.schedule: day-mode classification and peak-window attachment.

Also carries the two architectural guard tests from PLAN_EVENT_RELATIVE_RECHARGE.md
Section 13.1, under the "architectural guards" section below.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

import owr.simulator
from owr.config import DEFAULT_CONFIG, Config
from owr.models import DayMode, DayProfile, StressWindow, WrapConvention
from owr.schedule import build_schedule, detect_and_build_schedule


def _day(d: date, load: list[float] | None = None) -> DayProfile:
    return DayProfile(date=d, hourly_load_mw=tuple(load or [100.0] * 24))


def _days(start: date, n: int, load: list[float] | None = None) -> list[DayProfile]:
    from datetime import timedelta

    return [_day(start + timedelta(days=i), load) for i in range(n)]


def _peaked_load(hours: list[int], value: float = 500.0) -> list[float]:
    loads = [100.0] * 24
    for h in hours:
        loads[h] = value
    return loads


# --------------------------------------------------------------------------- #
# Day-mode classification
# --------------------------------------------------------------------------- #


def test_three_modes_pre_charge_active_non_event():
    days = _days(date(2026, 1, 1), 6)
    window = StressWindow(start=date(2026, 1, 4), end=date(2026, 1, 5), days=2)
    schedule = build_schedule(days, stress_windows=[window], config=DEFAULT_CONFIG)
    modes = [d.mode for d in schedule.days]
    assert modes == [
        DayMode.PRE_CHARGE,
        DayMode.PRE_CHARGE,
        DayMode.PRE_CHARGE,
        DayMode.ACTIVE_EVENT,
        DayMode.ACTIVE_EVENT,
        DayMode.NON_EVENT,
    ]


def test_gap_days_between_two_windows_are_pre_charge():
    days = _days(date(2026, 1, 1), 8)
    windows = [
        StressWindow(start=date(2026, 1, 2), end=date(2026, 1, 3), days=2),
        StressWindow(start=date(2026, 1, 6), end=date(2026, 1, 7), days=2),
    ]
    schedule = build_schedule(days, stress_windows=windows, config=DEFAULT_CONFIG)
    modes = [d.mode for d in schedule.days]
    assert modes == [
        DayMode.PRE_CHARGE,  # 01: before window 1
        DayMode.ACTIVE_EVENT,  # 02
        DayMode.ACTIVE_EVENT,  # 03
        DayMode.PRE_CHARGE,  # 04: gap, but before window 2 (D12)
        DayMode.PRE_CHARGE,  # 05: gap, but before window 2 (D12)
        DayMode.ACTIVE_EVENT,  # 06
        DayMode.ACTIVE_EVENT,  # 07
        DayMode.NON_EVENT,  # 08: after the last window
    ]


def test_day_after_last_window_is_non_event():
    days = _days(date(2026, 1, 1), 3)
    window = StressWindow(start=date(2026, 1, 1), end=date(2026, 1, 1), days=2)
    schedule = build_schedule(days, stress_windows=[window], config=DEFAULT_CONFIG)
    assert schedule.for_date(date(2026, 1, 1)).mode is DayMode.ACTIVE_EVENT
    assert schedule.for_date(date(2026, 1, 2)).mode is DayMode.NON_EVENT
    assert schedule.for_date(date(2026, 1, 3)).mode is DayMode.NON_EVENT


def test_qualifying_filter_rejects_short_windows():
    """build_schedule re-applies the min_stress_window_days filter itself (Section
    6), so a window shorter than the configured minimum does not activate a day
    even though the caller already ran detection at some other minimum."""
    days = _days(date(2026, 1, 1), 3)
    short_window = StressWindow(start=date(2026, 1, 2), end=date(2026, 1, 2), days=1)
    config = Config(default_min_stress_window_days=2)
    schedule = build_schedule(days, stress_windows=[short_window], config=config)
    assert all(d.mode is DayMode.NON_EVENT for d in schedule.days)


def test_ascending_date_rejection():
    days = [_day(date(2026, 1, 2)), _day(date(2026, 1, 1))]
    with pytest.raises(ValueError):
        build_schedule(days, stress_windows=[], config=DEFAULT_CONFIG)


# --------------------------------------------------------------------------- #
# Peak-window slot arithmetic
# --------------------------------------------------------------------------- #


def test_peak_window_at_hour_0_no_ramp_up_truncation_needed():
    days = _days(date(2026, 1, 1), 1, load=_peaked_load([0, 1, 2]))
    window = StressWindow(start=date(2026, 1, 1), end=date(2026, 1, 1), days=2)
    schedule = build_schedule(days, stress_windows=[window], config=DEFAULT_CONFIG)
    day_schedule = schedule.for_date(date(2026, 1, 1))
    dw = day_schedule.dispatch_window
    assert dw.peak_slots == (0, 1, 2)
    assert dw.ramp_up_slots == (-1,)
    assert dw.ramp_up_hours == ()
    assert dw.ramp_down_slots == (3,)
    assert dw.ramp_down_hours == (3,)


def test_peak_window_at_hour_21_ramp_down_truncated():
    days = _days(date(2026, 1, 1), 1, load=_peaked_load([21, 22, 23]))
    window = StressWindow(start=date(2026, 1, 1), end=date(2026, 1, 1), days=2)
    schedule = build_schedule(days, stress_windows=[window], config=DEFAULT_CONFIG)
    day_schedule = schedule.for_date(date(2026, 1, 1))
    dw = day_schedule.dispatch_window
    assert dw.peak_slots == (21, 22, 23)
    assert dw.ramp_down_slots == (24,)
    assert dw.ramp_down_hours == ()
    assert dw.ramp_up_slots == (20,)
    assert dw.ramp_up_hours == (20,)


def test_wrapped_peak_window_under_wrap_to_next_day():
    day1 = _day(date(2026, 1, 1), _peaked_load([22, 23]))
    day2 = _day(date(2026, 1, 2), _peaked_load([0]))
    days = [day1, day2]
    window = StressWindow(start=date(2026, 1, 1), end=date(2026, 1, 2), days=2)
    config = Config(default_peak_window_wrap=WrapConvention.WRAP_TO_NEXT_DAY)
    schedule = build_schedule(days, stress_windows=[window], config=config)
    day_schedule = schedule.for_date(date(2026, 1, 1))
    assert day_schedule.peak_window.wrapped is True
    assert day_schedule.peak_window.start_hour == 22
    dw = day_schedule.dispatch_window
    assert dw.peak_slots == (22, 23, 24)
    assert dw.peak_hours == (22, 23)


# --------------------------------------------------------------------------- #
# detect_and_build_schedule
# --------------------------------------------------------------------------- #


def test_detect_and_build_schedule_runs_detection_itself():
    days = _days(date(2026, 1, 1), 3)
    schedule = detect_and_build_schedule(days, config=DEFAULT_CONFIG)
    assert len(schedule.days) == 3
    # flat, identical load every day never crosses the percentile threshold
    assert all(d.mode is DayMode.NON_EVENT for d in schedule.days)


# --------------------------------------------------------------------------- #
# architectural guards
# --------------------------------------------------------------------------- #

_SRC = Path(__file__).resolve().parent.parent / "src" / "owr"


def test_guard_peak_window_imported_only_by_schedule():
    """Requirements Section 24 criterion 6: schedule.py is the only src/owr
    module that imports peak_window. tests/ and src/owr/etl/ stay out of scope."""
    offenders = []
    for path in sorted(_SRC.glob("*.py")):
        if path.name in ("schedule.py", "peak_window.py"):
            continue
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "owr.peak_window":
                offenders.append(path.name)
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "owr.peak_window":
                        offenders.append(path.name)
    assert offenders == []


_SURPLUS = ast.unparse(ast.parse("max(0.0, wind - max(0.0, load - discharge))")).strip()


def _code_text(path: Path) -> str:
    """Module source with every docstring and every comment removed."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if ast.get_docstring(node) is not None:
                node.body = node.body[1:]
    return ast.unparse(tree)


def test_guard_surplus_wind_rule_does_not_reappear_in_code():
    """Requirements Section 24 criterion 7: the old surplus-wind rule
    (max(0.0, wind - max(0.0, load - discharge))) must not come back in code.

    The expression legitimately appears once, in metrics.py's
    recharge_opportunity_mw, in both a docstring and code (Section 10 keeps that
    docstring). Docstrings and comments are stripped through the AST first, so
    only the code occurrence is counted.
    """
    occurrences = []
    for path in sorted(_SRC.glob("*.py")):
        count = _code_text(path).count(_SURPLUS)
        if count:
            occurrences.append((path.name, count))
    assert occurrences == [("metrics.py", 1)]
    assert not hasattr(owr.simulator, "_surplus_wind_recharge_mwh")


# --------------------------------------------------------------------------- #
# stress_finder.find_stress_windows_for_config
# --------------------------------------------------------------------------- #


def test_find_stress_windows_for_config_matches_direct_call():
    from owr.stress_finder import find_stress_windows_at_percentile, find_stress_windows_for_config

    days = _days(date(2026, 1, 1), 3)
    for i, d in enumerate(days):
        days[i] = DayProfile(
            date=d.date,
            hourly_load_mw=d.hourly_load_mw,
            demand_percentile=0.95 if i == 1 else 0.5,
        )
    direct = find_stress_windows_at_percentile(
        days,
        DEFAULT_CONFIG.default_min_stress_window_days,
        percentile_floor_percent=round(DEFAULT_CONFIG.default_severity_percentile * 100.0, 9),
        rounding=DEFAULT_CONFIG.stress_percentile_rounding,
    )
    via_config = find_stress_windows_for_config(days, DEFAULT_CONFIG)
    assert direct == via_config
