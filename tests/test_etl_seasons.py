"""Tests for season tagging (docs/archive/plans/PLAN_EIA_EXTRACTOR.md Phase B2)."""

from __future__ import annotations

from datetime import date

from owr.etl.seasons import Season, season_for, winter_label


def test_season_for_boundaries():
    assert season_for(date(2021, 12, 1)) == Season.WINTER
    assert season_for(date(2024, 2, 29)) == Season.WINTER
    assert season_for(date(2024, 3, 1)) == Season.SHOULDER
    assert season_for(date(2024, 5, 31)) == Season.SHOULDER
    assert season_for(date(2024, 6, 1)) == Season.SUMMER
    assert season_for(date(2024, 9, 30)) == Season.SUMMER
    assert season_for(date(2024, 10, 1)) == Season.SHOULDER
    assert season_for(date(2024, 11, 30)) == Season.SHOULDER


def test_winter_label_groups_december_with_following_jan_feb():
    assert winter_label(date(2021, 12, 15)) == "2021/22"
    assert winter_label(date(2022, 2, 10)) == "2021/22"
    assert winter_label(date(2022, 3, 1)) is None
