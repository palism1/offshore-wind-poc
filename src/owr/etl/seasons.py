"""Season tagging and winter labelling (docs/archive/plans/PLAN_EIA_EXTRACTOR.md Phase B2).

Settled definitions (HANDOFF.md): winter = Dec 1 - Feb 28/29, summer = Jun 1 -
Sep 30. Both land exactly on month boundaries, so no day-of-month logic is
needed, and Feb 29 falls out of the month check for free. March belongs to
neither season and must never be pooled into a seasonal denominator.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

_WINTER_MONTHS = frozenset({12, 1, 2})
_SUMMER_MONTHS = frozenset({6, 7, 8, 9})


class Season(StrEnum):  # values match features.daily_load's CHECK constraint
    WINTER = "winter"
    SUMMER = "summer"
    SHOULDER = "shoulder"


def season_for(d: date) -> Season:
    """Winter: Dec/Jan/Feb. Summer: Jun-Sep. Everything else: shoulder."""
    if d.month in _WINTER_MONTHS:
        return Season.WINTER
    if d.month in _SUMMER_MONTHS:
        return Season.SUMMER
    return Season.SHOULDER


def winter_label(d: date) -> str | None:
    """``"2021/22"`` for any day in Dec 2021 or Jan/Feb 2022; ``None`` outside winter.

    Groups December of year Y with January/February of year Y+1 — the grouping
    key Phase B3 needs to keep winters separate under the pooled threshold.
    """
    if d.month == 12:
        return f"{d.year}/{(d.year + 1) % 100:02d}"
    if d.month in (1, 2):
        return f"{d.year - 1}/{d.year % 100:02d}"
    return None
