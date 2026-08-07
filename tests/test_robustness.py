"""Tests for owr.robustness (Metric Thresholds v1.1, change 6)."""

import pytest

from owr.config import DEFAULT_CONFIG
from owr.robustness import (
    EventMetrics,
    EventStatus,
    Zone,
    classify_absolute_band,
    classify_event,
    classify_higher_is_better,
    evaluate_scenario,
    evaluate_winter,
)

_CFG = DEFAULT_CONFIG


def _metrics(
    *,
    label: str = "event",
    cmdr: float | None = 25.0,
    swe: float | None = 5.0,
    fop: float | None = 6.0,
    rcm: float | None = 1.0,
) -> EventMetrics:
    return EventMetrics(
        event_label=label, cmdr_percent=cmdr, swe_percent=swe, fop_percent=fop, rcm_percent=rcm
    )


# --------------------------------------------------------------------------- #
# One test per metric per zone (mid-band values)
# --------------------------------------------------------------------------- #


def test_cmdr_acceptable_mid_band():
    assert (
        classify_higher_is_better(30.0, acceptable=20.0, failure=0.0, failure_is_inclusive=True)
        == Zone.ACCEPTABLE
    )


def test_cmdr_warning_mid_band():
    assert (
        classify_higher_is_better(10.0, acceptable=20.0, failure=0.0, failure_is_inclusive=True)
        == Zone.WARNING
    )


def test_cmdr_failure_mid_band():
    assert (
        classify_higher_is_better(-10.0, acceptable=20.0, failure=0.0, failure_is_inclusive=True)
        == Zone.FAILURE
    )


def test_swe_acceptable_mid_band():
    assert (
        classify_higher_is_better(5.0, acceptable=3.0, failure=0.5, failure_is_inclusive=False)
        == Zone.ACCEPTABLE
    )


def test_swe_warning_mid_band():
    assert (
        classify_higher_is_better(1.5, acceptable=3.0, failure=0.5, failure_is_inclusive=False)
        == Zone.WARNING
    )


def test_swe_failure_mid_band():
    assert (
        classify_higher_is_better(0.1, acceptable=3.0, failure=0.5, failure_is_inclusive=False)
        == Zone.FAILURE
    )


def test_fop_acceptable_mid_band():
    assert (
        classify_higher_is_better(10.0, acceptable=5.0, failure=2.0, failure_is_inclusive=False)
        == Zone.ACCEPTABLE
    )


def test_fop_warning_mid_band():
    assert (
        classify_higher_is_better(3.5, acceptable=5.0, failure=2.0, failure_is_inclusive=False)
        == Zone.WARNING
    )


def test_fop_failure_mid_band():
    assert (
        classify_higher_is_better(1.0, acceptable=5.0, failure=2.0, failure_is_inclusive=False)
        == Zone.FAILURE
    )


def test_rcm_acceptable_mid_band():
    assert classify_absolute_band(2.0, acceptable_abs=5.0, failure_abs=10.0) == Zone.ACCEPTABLE


def test_rcm_warning_mid_band():
    assert classify_absolute_band(7.0, acceptable_abs=5.0, failure_abs=10.0) == Zone.WARNING


def test_rcm_failure_mid_band():
    assert classify_absolute_band(15.0, acceptable_abs=5.0, failure_abs=10.0) == Zone.FAILURE


# --------------------------------------------------------------------------- #
# Boundary tests at every stated bound
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "value,expected",
    [(20.0, Zone.ACCEPTABLE), (19.0, Zone.WARNING), (5.0, Zone.WARNING), (0.0, Zone.FAILURE)],
)
def test_cmdr_boundaries(value, expected):
    assert (
        classify_higher_is_better(value, acceptable=20.0, failure=0.0, failure_is_inclusive=True)
        == expected
    )


@pytest.mark.parametrize(
    "value,expected",
    [(3.0, Zone.ACCEPTABLE), (2.9, Zone.WARNING), (0.5, Zone.WARNING), (0.49, Zone.FAILURE)],
)
def test_swe_boundaries(value, expected):
    assert (
        classify_higher_is_better(value, acceptable=3.0, failure=0.5, failure_is_inclusive=False)
        == expected
    )


@pytest.mark.parametrize(
    "value,expected",
    [(5.0, Zone.ACCEPTABLE), (4.9, Zone.WARNING), (2.0, Zone.WARNING), (1.99, Zone.FAILURE)],
)
def test_fop_boundaries(value, expected):
    assert (
        classify_higher_is_better(value, acceptable=5.0, failure=2.0, failure_is_inclusive=False)
        == expected
    )


@pytest.mark.parametrize(
    "value,expected",
    [
        (5.0, Zone.ACCEPTABLE),
        (-5.0, Zone.ACCEPTABLE),
        (10.0, Zone.WARNING),
        (-10.0, Zone.WARNING),
        (10.01, Zone.FAILURE),
    ],
)
def test_rcm_boundaries(value, expected):
    assert classify_absolute_band(value, acceptable_abs=5.0, failure_abs=10.0) == expected


# --------------------------------------------------------------------------- #
# Gap values, failure inclusivity, undefined handling
# --------------------------------------------------------------------------- #


def test_gap_values_land_in_warning():
    assert (
        classify_higher_is_better(19.5, acceptable=20.0, failure=0.0, failure_is_inclusive=True)
        == Zone.WARNING
    )
    assert (
        classify_higher_is_better(2.5, acceptable=20.0, failure=0.0, failure_is_inclusive=True)
        == Zone.WARNING
    )
    assert (
        classify_higher_is_better(2.95, acceptable=3.0, failure=0.5, failure_is_inclusive=False)
        == Zone.WARNING
    )
    assert (
        classify_higher_is_better(4.95, acceptable=5.0, failure=2.0, failure_is_inclusive=False)
        == Zone.WARNING
    )


def test_swe_and_fop_at_the_failure_bound_are_warning_not_failure():
    assert (
        classify_higher_is_better(0.5, acceptable=3.0, failure=0.5, failure_is_inclusive=False)
        == Zone.WARNING
    )
    assert (
        classify_higher_is_better(2.0, acceptable=5.0, failure=2.0, failure_is_inclusive=False)
        == Zone.WARNING
    )


def test_cmdr_at_zero_is_failure():
    assert (
        classify_higher_is_better(0.0, acceptable=20.0, failure=0.0, failure_is_inclusive=True)
        == Zone.FAILURE
    )


def test_undefined_metric_gives_not_evaluable_not_fail():
    metrics = _metrics(cmdr=None)
    verdict = classify_event(metrics, _CFG)
    assert verdict.status == EventStatus.NOT_EVALUABLE
    assert verdict.undefined_metrics == ("cmdr",)


def test_event_with_no_capacity_deficit_does_not_fail_its_year():
    event = _metrics(cmdr=None, swe=5.0, fop=6.0, rcm=1.0)
    winter = evaluate_winter("2025/26", [event], _CFG)
    assert winter.status == EventStatus.NOT_EVALUABLE
    assert winter.failure_points == 0


def test_year_passes_when_any_event_passes():
    passing = _metrics(label="e1", cmdr=25.0, swe=5.0, fop=6.0, rcm=1.0)
    failing = _metrics(label="e2", cmdr=1.0, swe=5.0, fop=6.0, rcm=1.0)
    winter = evaluate_winter("2025/26", [failing, passing], _CFG)
    assert winter.status == EventStatus.PASS
    assert winter.failure_points == 0


def test_year_fails_when_no_event_passes():
    failing_a = _metrics(label="e1", cmdr=1.0, swe=5.0, fop=6.0, rcm=1.0)
    failing_b = _metrics(label="e2", cmdr=1.0, swe=5.0, fop=6.0, rcm=1.0)
    winter = evaluate_winter("2025/26", [failing_a, failing_b], _CFG)
    assert winter.status == EventStatus.FAIL
    assert winter.failure_points == 1


def test_winter_with_no_events_is_not_evaluable():
    winter = evaluate_winter("2021/22", [], _CFG)
    assert winter.status == EventStatus.NOT_EVALUABLE
    assert winter.failure_points == 0


def test_scenario_score_counts_passing_years():
    passing = _metrics(cmdr=25.0, swe=5.0, fop=6.0, rcm=1.0)
    failing = _metrics(cmdr=1.0, swe=5.0, fop=6.0, rcm=1.0)
    winters_events = {
        "2021/22": [passing],
        "2022/23": [passing],
        "2023/24": [passing],
        "2024/25": [failing],
        "2025/26": [],
    }
    result = evaluate_scenario(winters_events, _CFG)
    assert result.scenario_robustness_score == 3
    assert result.years_evaluated == 4
    assert result.years_not_evaluable == 1
    assert result.max_score_attainable == 4
    assert result.analysis_years_in_source == 5


def test_score_never_exceeds_years_evaluated():
    passing = _metrics(cmdr=25.0, swe=5.0, fop=6.0, rcm=1.0)
    winters_events = {"2025/26": [passing]}
    result = evaluate_scenario(winters_events, _CFG)
    assert result.scenario_robustness_score <= result.years_evaluated
