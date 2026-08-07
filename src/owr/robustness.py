"""Scenario Robustness Score (Metric Thresholds v1.1, changes 6).

Maps the four Component 7 / Metric Thresholds metrics (CMDR, SWE, FOP, RCM) to a
zone per stress event, reduces zones to a per-event status, reduces events to a
per-winter verdict, and reduces winters to the scenario robustness score. This
module ships **unwired** (R4): nothing calls it yet, because wiring needs
per-event oil, gas, and wind series that exist for one winter (2025/26) only in
this repo's local data (section 3 of the plan). Wire it for that one winter as a
follow-up, never inside this phase.

Engine core rules apply: no file, network, or database access. Imports limited
to ``owr.config``, ``owr.models``, and the standard library.

Operating range tables, ``docs/source/2026-08-05_Metric_Thresholds_v1.1.pdf``,
page 5 summary table::

    Metric  Acceptable              Warning          Failure   Pass Condition
    CMDR    >= 20% (Score >= 20)    5% to 19%        <= 0%     CMDR% >= 20%
    SWE     >= 3.0% (Score >= 3)    0.5% to 2.9%     < 0.5%    SWE >= 3.0%
    FOP     >= 5.0% (Score >= 5)    2.0% to 4.9%     < 2.0%    FOP >= 5.0%
    RCM     0% to +-5% (Score>=75)  +-5% to +-10%    > +-10%   RCM Score >= 75

The PDF's score sentence: "A year earns its Robustness Score point only when
all four metrics simultaneously meet their Acceptable threshold. The maximum
possible score is 5 - one point per analysis year (2022-2026)."

The PDF's per-event note: "All four metrics should be computed per identified
stress event, not across the entire winter dataset ... For years with multiple
events (e.g., 2025: W02, W03, W04), the year passes if any single event meets
all four thresholds."

The architecture doc's "that winter automatically receives one robustness
failure point" phrasing is the complement of the same rule (D8): a year that
does not earn the point takes a failure point instead. Both forms ship:
``WinterVerdict.failure_points`` and ``RobustnessResult.scenario_robustness_score``.

OPEN team question (``zone_band_gaps``): the source tables leave real gaps and
one overlap between the stated Acceptable and Failure bounds.

- CMDR: Acceptable ``>= 20%``, Warning ``5% to 19%``, Failure ``<= 0%``, so
  ``0 < x < 5`` and ``19 < x < 20`` belong to no stated band.
- SWE: Acceptable ``>= 3.0%``, Failure ``< 0.5%``, leaving ``2.9 < x < 3.0``
  unstated between the Warning row's stated ceiling and Acceptable's floor.
- FOP: Acceptable ``>= 5.0%``, Failure ``< 2.0%``, leaving ``4.9 < x < 5.0``
  unstated.
- RCM: the summary table states ``±5.0`` twice, once as the Acceptable
  boundary and once as the Warning boundary.

This module resolves every case the same way: the Acceptable band is closed at
its stated bound, the Failure band is closed at its stated bound, and Warning
absorbs everything between them (D7). RCM's double claim on ``±5.0`` resolves
to Acceptable.

OPEN team question (``robustness_metric_definitions``): the FOP zone band
above is calibrated against the PDF's own formula, ``(Sum(wind) +
Sum(capacity_dispatched)) / Sum(total_generation) * 100``, which is not the
formula ``metrics.fuel_offset_fraction`` implements (the architecture doc's
``fuel_fired_generation_offset / total_generation``, a different quantity that
can be negative). ``EventMetrics.fop_percent`` comes from the caller, so this
module never picks a formula; the conflict is recorded, not resolved, here.
See risk R6.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from owr.config import Config


class Zone(StrEnum):
    ACCEPTABLE = "acceptable"
    WARNING = "warning"
    FAILURE = "failure"


class EventStatus(StrEnum):
    """Per D10a. NOT_EVALUABLE is not a failure: it means at least one metric was
    undefined for a benign reason, such as an event with no capacity deficit, so
    the event proves nothing either way."""

    PASS = "pass"
    FAIL = "fail"
    NOT_EVALUABLE = "not_evaluable"


@dataclass(frozen=True)
class EventMetrics:
    event_label: str
    cmdr_percent: float | None
    swe_percent: float | None
    fop_percent: float | None
    rcm_percent: float | None


@dataclass(frozen=True)
class EventVerdict:
    event_label: str
    zones: dict[str, Zone | None]  # keys: "cmdr", "swe", "fop", "rcm"
    undefined_metrics: tuple[str, ...]
    status: EventStatus


@dataclass(frozen=True)
class WinterVerdict:
    winter_label: str
    events: tuple[EventVerdict, ...]
    status: EventStatus  # PASS, FAIL or NOT_EVALUABLE
    failure_points: int  # 1 when status is FAIL, else 0


@dataclass(frozen=True)
class RobustnessResult:
    winters: tuple[WinterVerdict, ...]
    scenario_robustness_score: int  # count of PASS years (D8, D10)
    years_evaluated: int  # PASS plus FAIL
    years_not_evaluable: int
    max_score_attainable: int  # equals years_evaluated
    analysis_years_in_source: int  # config.robustness_analysis_years, 5


def classify_higher_is_better(
    value: float | None,
    *,
    acceptable: float,
    failure: float,
    failure_is_inclusive: bool,
) -> Zone | None:
    """Zone for a metric where a higher value is better (CMDR, SWE, FOP).

    ``value >= acceptable`` gives ACCEPTABLE. FAILURE when ``value <= failure``
    and ``failure_is_inclusive`` is True, or ``value < failure`` when it is
    False. Everything else gives WARNING. Returns ``None`` for a ``None``
    input, per D10a.
    """
    if value is None:
        return None
    if value >= acceptable:
        return Zone.ACCEPTABLE
    if failure_is_inclusive:
        if value <= failure:
            return Zone.FAILURE
    elif value < failure:
        return Zone.FAILURE
    return Zone.WARNING


def classify_absolute_band(
    value: float | None, *, acceptable_abs: float, failure_abs: float
) -> Zone | None:
    """Zone for RCM, whose band is symmetric around zero.

    ``abs(value) <= acceptable_abs`` gives ACCEPTABLE, ``abs(value) >
    failure_abs`` gives FAILURE, otherwise WARNING. This resolves the source's
    double claim on ``±5.0`` (D7) in favor of Acceptable. Returns ``None`` for
    a ``None`` input.
    """
    if value is None:
        return None
    magnitude = abs(value)
    if magnitude <= acceptable_abs:
        return Zone.ACCEPTABLE
    if magnitude > failure_abs:
        return Zone.FAILURE
    return Zone.WARNING


def classify_event(metrics: EventMetrics, config: Config) -> EventVerdict:
    """Reduce one event's four metric values to zones and a status (D9, D10a).

    PASS when all four zones are ACCEPTABLE. NOT_EVALUABLE when any metric is
    undefined (``None``). FAIL otherwise. Undefined outranks fail, so a missing
    input can never masquerade as a failure.
    """
    zones: dict[str, Zone | None] = {
        "cmdr": classify_higher_is_better(
            metrics.cmdr_percent,
            acceptable=config.zone_cmdr_acceptable_percent,
            failure=config.zone_cmdr_failure_percent,
            failure_is_inclusive=True,
        ),
        "swe": classify_higher_is_better(
            metrics.swe_percent,
            acceptable=config.zone_swe_acceptable_percent,
            failure=config.zone_swe_failure_percent,
            failure_is_inclusive=False,
        ),
        "fop": classify_higher_is_better(
            metrics.fop_percent,
            acceptable=config.zone_fop_acceptable_percent,
            failure=config.zone_fop_failure_percent,
            failure_is_inclusive=False,
        ),
        "rcm": classify_absolute_band(
            metrics.rcm_percent,
            acceptable_abs=config.zone_rcm_acceptable_abs_percent,
            failure_abs=config.zone_rcm_failure_abs_percent,
        ),
    }
    undefined_metrics = tuple(name for name, zone in zones.items() if zone is None)
    if undefined_metrics:
        status = EventStatus.NOT_EVALUABLE
    elif all(zone == Zone.ACCEPTABLE for zone in zones.values()):
        status = EventStatus.PASS
    else:
        status = EventStatus.FAIL
    return EventVerdict(
        event_label=metrics.event_label,
        zones=zones,
        undefined_metrics=undefined_metrics,
        status=status,
    )


def evaluate_winter(
    winter_label: str, events: list[EventMetrics], config: Config
) -> WinterVerdict:
    """Reduce one winter's events to a verdict (D9, D10a).

    PASS when any event is PASS. FAIL when at least one event is FAIL and none
    is PASS. NOT_EVALUABLE when the winter has no events, or every event is
    NOT_EVALUABLE. ``failure_points`` is 1 only for FAIL.
    """
    verdicts = tuple(classify_event(event, config) for event in events)
    if not verdicts:
        status = EventStatus.NOT_EVALUABLE
    elif any(v.status == EventStatus.PASS for v in verdicts):
        status = EventStatus.PASS
    elif any(v.status == EventStatus.FAIL for v in verdicts):
        status = EventStatus.FAIL
    else:
        status = EventStatus.NOT_EVALUABLE
    return WinterVerdict(
        winter_label=winter_label,
        events=verdicts,
        status=status,
        failure_points=1 if status == EventStatus.FAIL else 0,
    )


def evaluate_scenario(
    winters_events: dict[str, list[EventMetrics]], config: Config
) -> RobustnessResult:
    """Reduce every winter to the scenario robustness score (D8, D10).

    ``scenario_robustness_score`` is the count of PASS winters.
    ``max_score_attainable`` equals ``years_evaluated`` (PASS plus FAIL).
    ``analysis_years_in_source`` carries ``config.robustness_analysis_years`` so
    a reader can see, e.g., 3 of 5 at a glance.
    """
    winters = tuple(
        evaluate_winter(label, events, config) for label, events in winters_events.items()
    )
    scenario_robustness_score = sum(1 for w in winters if w.status == EventStatus.PASS)
    years_evaluated = sum(
        1 for w in winters if w.status in (EventStatus.PASS, EventStatus.FAIL)
    )
    years_not_evaluable = sum(1 for w in winters if w.status == EventStatus.NOT_EVALUABLE)
    return RobustnessResult(
        winters=winters,
        scenario_robustness_score=scenario_robustness_score,
        years_evaluated=years_evaluated,
        years_not_evaluable=years_not_evaluable,
        max_score_attainable=years_evaluated,
        analysis_years_in_source=config.robustness_analysis_years,
    )
