"""Engine configuration — the design constants the source documents leave open.

Every value here is a **team design choice**, not a verified fact (see
docs/archive/reviews/FACT_CHECK_REPORT.md "Common Mistakes": the 0.7/0.3 weights and the
33% floor are decisions to benchmark against literature and label, never facts to
verify). They are surfaced as configuration so a scenario can override them and so
the open questions in docs/PLAN.md never get hard-coded as magic numbers.

**One exception, as of 2026-08-05: ``default_severity_percentile``.** The
Architecture export of that date fixes the 90th percentile in Component 3, so that
field is sourced and the rule above does not apply to it. It stays in this class
because ``stress_finder`` takes it as a parameter and a scenario may still override
it. Its attribute entry below carries the source quote.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from owr.models import HOURS_PER_DAY, PercentileRounding, PowerRule, WrapConvention


@dataclass(frozen=True)
class Config:
    """Tunable design constants for the engine's stress-detection and dispatch models.

    A value belongs here when an engine function or value object takes it as a
    parameter; reporting-only assumptions live with their consumer.

    Attributes map to open questions in docs/PLAN.md / docs/archive/reviews/FACT_CHECK_REPORT.md:

    priority_demand_weight / priority_wind_weight
        Architecture doc: ``Priority(d) = 0.7*DemandPercentile + 0.3*WindForecast``.
        Weights must sum to 1.0. (Team design choice.)

    default_efficiency
        Round-trip efficiency, measured at the terminals, in
        ``soc(t+1)=soc(t)+charge*one_way_eff-discharge/one_way_eff``. The engine
        splits it symmetrically: each leg carries ``sqrt(eff)``
        (`StorageAsset.one_way_efficiency`), so the two legs multiply back to this
        round-trip figure. Enter a round-trip figure directly, never pre-squared:
        Dick et al. Table 1 (`docs/archive/reviews/FINDINGS_STENSEA_PAPER_2026-08-02.md`) gives 0.72
        full cycle for StEnSea, and ``--efficiency 0.72`` realizes exactly that.
        Defaults to 0.7225 as of Week 4B: ``0.85 * 0.85 = 0.7225``, reading Report
        B's 0.85 as a per-leg figure and squaring it to the round-trip figure this
        field takes. The StEnSea 0.72 full-cycle citation above stays as the
        alternative reading. This narrows, but does not close, the open team
        question: the source Global Assumptions block still reads
        ``Round-trip efficiency = @`` (OPEN team question round_trip_efficiency).
        The storage pivot makes efficiency the axis candidate technologies differ
        on (StEnSea 0.80, LAES 0.50-0.70, thermal ~0.35). Undecided.

    default_soc_floor_frac / default_strategic_reserve_frac
        Reserve definition (FACT_CHECK inconsistency #3). Team decision 2026-07-17:
        the protected reserve is a 20% floor plus a 10% reserve of total capacity,
        leaving 70% for regular operations. We model the two as separate fractions;
        their sum (0.30) is the minimum state of charge the engine never discharges
        below. OPEN team question (reserve_usage_rules): when the 10% reserve and
        20% floor may each be drawn down (until decided, both are treated as one
        protected floor).

        The **combined** 0.30 is now sourced by
        `docs/source/2026-08-05_Metric_Thresholds_v1.1.pdf`, Winter Data Anchors
        table, rows "Protected Reserve 30% of Total Capacity" and "Max Available
        Charge 70% of Total Capacity". The source fixes the total, not the 20/10
        split; the split stays a team choice. The document disagrees with itself:
        its RCM derivation writes "Protected reserve floor = 20% of Total Capacity
        (cannot discharge below)", while its anchor table writes 30%. This repo
        reads 20% floor plus 10% strategic reserve as equal to the anchor table's
        30% protected, and records the discrepancy here rather than silently
        picking one branch.

    default_severity_percentile
        **Doc-sourced** 2026-08-05. The Architecture export
        ``docs/source/2026-08-05_Software_Architecture_Documentation.md``,
        Component 3, states: "Determine: 90th historical daily load percentile. A
        stress event begins when: daily_load >= 90th percentile for minimum_window
        consecutive days." The 0.90 default is that number, and it is the one value
        in this class the source now fixes.
        OPEN team question (stress_event_definition) is **narrowed, not closed**.
        The source fixes the rule and the percentile. It leaves the **threshold
        value in MWh on real data** open: both published numbers (3,504 and 16,750
        MWh) are hourly-basis and do not carry over to a daily-basis rule, so a
        fresh p90 must be computed on daily sums.

    default_min_stress_window_days
        The ``minimum_window`` of the Component 3 rule above. The source names the
        parameter and gives it no value, so 2 stays a **team design choice**.
        Settled 2026-07-28 (HANDOFF.md decision 2) at 2 or more consecutive days.
        Report B's competing 12-hour rule (12+ hours above an hourly threshold
        within a day) is retired.

    default_peak_weight / default_smooth_weight
        Relative emphasis of peak shaving vs ramp smoothing in ``dispatch``. The
        Architecture doc names PeakWeight and SmoothWeight without fixing values.
        (Team design choice.)

    default_peak_window_hours
        **Settled** 2026-07-28: each day in a stress window gets a peak load
        defined as a 3-hour period found by rolling window over hour triplets.
        Surfaced as config because ``find_peak_window`` takes it as a parameter,
        not because it is in doubt.

    default_peak_window_wrap
        OPEN team question (peak_window_wrap). Mitchell's enumeration ends at
        (22,23,00). ``WrapConvention.WRAP_TO_NEXT_DAY`` is the physically
        continuous reading and the one HANDOFF.md says to assume;
        ``STOP_AT_MIDNIGHT`` is the 22-triplets alternative. On a multi-day event
        the choice changes which hours get shaved at the day boundary. Flipping
        the default is a one-value change.

        The default is now ``STOP_AT_MIDNIGHT``, per requirements Section 9 of
        ``docs/architecture/event_relative_recharge.md``, so a dispatch block
        never crosses midnight. The open question stays open. Consequence for a
        future flipper: under ``WRAP_TO_NEXT_DAY`` a day whose highest triplet
        wraps gets peak slots such as (22, 23, 24); slot 24 does not exist in
        the day, so that share of the peak pool is not delivered and is not
        moved to another hour (D14, R7).

    default_ramp_hours
        The ramp-up and ramp-down block length in hours on each side of the
        peak window, used by ``schedule.build_schedule`` and
        ``dispatch.allocate_discharge``. OPEN team question (``ramp_duration``):
        no source names a value. ``[TWEAK]`` 1 hour is the smallest value that
        makes the ramp-up -> peak -> ramp-down sandwich real, and it gives a
        5-hour dispatch block at the settled 3-hour peak window.

    est_transmission_cost_per_mile_usd / est_storage_unit_cost_usd / solution_lifetime_years
        OPEN team question (capital_cost_constants). Component 7's capital-cost
        formulas need these three constants and every one is ``@`` in the source:
        no value exists yet for any of them. **No code path reads these three
        fields.** They park the wiring step that follows once the team supplies
        values, and surface the open question in the ``config`` block of every
        JSON report, mirroring ``storage_physics.py``, whose docstring says "Not
        wired anywhere" for the same reason. They belong in ``Config`` and not in
        ``cli.py`` because ``metrics.estimated_capital_cost_usd`` and
        ``metrics.cost_per_equivalent_full_cycle_usd`` take them as parameters.

    default_sweep_sizes_mwh
        OPEN team question (``sweep_size_ladder``). The seven sizes bracket Report
        A's 40,000 to 60,000 MWh system reserve target and the 60,000 MWh demo
        point. ``docs/archive/reviews/FACT_CHECK_REPORT.md`` records that the 40,000 to 60,000 MWh
        target does not reproduce from its own inputs, so the ladder moves when
        that number moves. Read at parser-build time by
        ``sweep_cli.build_parser``; no engine function reads it at run time. See
        docs/archive/plans/PLAN_SCENARIO_SWEEP.md decision D3.

    default_sweep_power_rule
        OPEN team question (``sweep_power_scaling``). Fixed power isolates the
        energy variable and reproduces the recorded reference points. Fixed
        duration is the fleet-scaled reading. See docs/archive/plans/PLAN_SCENARIO_SWEEP.md
        decision D2. Read at parser-build time only, as above.

    default_wind_generation_multiplier
        Sourced, Architecture doc Component 1 User Inputs. Scales historical wind
        before the engine sees it; defaults to 1.0, the identity scale.

    stress_percentile_floor_percent
        Sourced, Component 3: the stress-event comparison bound, 90.0 on a 0 to 100
        scale. Not the same value as ``default_severity_percentile``, which is the
        same bound expressed as a fraction, 0 to 1.

    stress_percentile_rounding
        OPEN team question (``stress_percentile_rounding``). See
        ``owr.models.PercentileRounding``. Defaults to ``FLOOR``.

    cmdr_p90_hourly_mwh
        Sourced, Metric Thresholds v1.1 Winter Data Anchors: "Stressed hours p90
        threshold 18,413 MWh/hr". This is an **hourly** MWh figure and is **not**
        the daily threshold that ``default_severity_percentile`` drives; see
        `docs/DATA_SOURCES.md:87-89`.

    zone_cmdr_acceptable_percent / zone_cmdr_failure_percent
        Sourced CMDR operating-range bounds: Acceptable >= 20%, Failure <= 0%.

    zone_swe_acceptable_percent / zone_swe_failure_percent
        Sourced SWE operating-range bounds: Acceptable >= 3.0%, Failure < 0.5%.

    zone_fop_acceptable_percent / zone_fop_failure_percent
        Sourced FOP operating-range bounds: Acceptable >= 5.0%, Failure < 2.0%.

    zone_rcm_acceptable_abs_percent / zone_rcm_failure_abs_percent
        Sourced RCM operating-range bounds, applied to ``abs(value)``: Acceptable
        <= 5.0%, Failure > 10.0%.

    robustness_analysis_years
        Sourced, Metric Thresholds v1.1: "The maximum possible score is 5 - one
        point per analysis year (2022-2026)."
    """

    priority_demand_weight: float = 0.7
    priority_wind_weight: float = 0.3
    default_efficiency: float = 0.7225
    default_soc_floor_frac: float = 0.20
    default_strategic_reserve_frac: float = 0.10
    default_severity_percentile: float = 0.90
    default_min_stress_window_days: int = 2
    default_peak_weight: float = 0.5
    default_smooth_weight: float = 0.5
    default_peak_window_hours: int = 3
    default_peak_window_wrap: WrapConvention = WrapConvention.STOP_AT_MIDNIGHT
    default_ramp_hours: int = 1
    est_transmission_cost_per_mile_usd: float | None = None
    est_storage_unit_cost_usd: float | None = None
    solution_lifetime_years: float | None = None
    default_sweep_sizes_mwh: tuple[float, ...] = (
        5000.0, 10000.0, 20000.0, 40000.0, 60000.0, 80000.0, 100000.0,
    )
    default_sweep_power_rule: PowerRule = PowerRule.FIXED
    default_wind_generation_multiplier: float = 1.0
    stress_percentile_floor_percent: float = 90.0
    stress_percentile_rounding: PercentileRounding = PercentileRounding.FLOOR
    cmdr_p90_hourly_mwh: float = 18413.0
    zone_cmdr_acceptable_percent: float = 20.0
    zone_cmdr_failure_percent: float = 0.0
    zone_swe_acceptable_percent: float = 3.0
    zone_swe_failure_percent: float = 0.5
    zone_fop_acceptable_percent: float = 5.0
    zone_fop_failure_percent: float = 2.0
    zone_rcm_acceptable_abs_percent: float = 5.0
    zone_rcm_failure_abs_percent: float = 10.0
    robustness_analysis_years: int = 5

    def __post_init__(self) -> None:
        if abs((self.priority_demand_weight + self.priority_wind_weight) - 1.0) > 1e-9:
            raise ValueError("priority weights must sum to 1.0")
        if not 0.0 < self.default_efficiency <= 1.0:
            raise ValueError("efficiency must be in (0, 1]")
        floor = self.default_soc_floor_frac + self.default_strategic_reserve_frac
        if not 0.0 <= floor < 1.0:
            raise ValueError("soc_floor + strategic_reserve must be in [0, 1)")
        if not 0.0 <= self.default_severity_percentile <= 1.0:
            raise ValueError("default_severity_percentile must be in [0, 1]")
        if self.default_min_stress_window_days < 1:
            raise ValueError("default_min_stress_window_days must be >= 1")
        if self.default_peak_weight < 0 or self.default_smooth_weight < 0:
            raise ValueError("default_peak_weight and default_smooth_weight must be >= 0")
        if self.default_peak_weight + self.default_smooth_weight <= 0:
            raise ValueError("default_peak_weight + default_smooth_weight must be > 0")
        if not 1 <= self.default_peak_window_hours <= HOURS_PER_DAY:
            raise ValueError(f"default_peak_window_hours must be in 1..{HOURS_PER_DAY}")
        if not 0 <= self.default_ramp_hours <= HOURS_PER_DAY:
            raise ValueError(f"default_ramp_hours must be in 0..{HOURS_PER_DAY}")
        if self.est_transmission_cost_per_mile_usd is not None and (
            self.est_transmission_cost_per_mile_usd < 0
        ):
            raise ValueError("est_transmission_cost_per_mile_usd must be non-negative")
        if self.est_storage_unit_cost_usd is not None and self.est_storage_unit_cost_usd < 0:
            raise ValueError("est_storage_unit_cost_usd must be non-negative")
        if self.solution_lifetime_years is not None and self.solution_lifetime_years < 0:
            raise ValueError("solution_lifetime_years must be non-negative")
        if not self.default_sweep_sizes_mwh:
            raise ValueError("default_sweep_sizes_mwh must not be empty")
        for size in self.default_sweep_sizes_mwh:
            if not math.isfinite(size) or size <= 0:
                raise ValueError("default_sweep_sizes_mwh values must be finite and positive")
        for prev, nxt in zip(
            self.default_sweep_sizes_mwh, self.default_sweep_sizes_mwh[1:], strict=False
        ):
            if not prev < nxt:
                raise ValueError("default_sweep_sizes_mwh must be strictly increasing")
        if (
            not math.isfinite(self.default_wind_generation_multiplier)
            or self.default_wind_generation_multiplier < 0
        ):
            raise ValueError("default_wind_generation_multiplier must be finite and >= 0")
        if not 0.0 <= self.stress_percentile_floor_percent <= 100.0:
            raise ValueError("stress_percentile_floor_percent must be in [0, 100]")
        if not math.isfinite(self.cmdr_p90_hourly_mwh) or self.cmdr_p90_hourly_mwh <= 0:
            raise ValueError("cmdr_p90_hourly_mwh must be finite and > 0")
        if self.zone_cmdr_failure_percent >= self.zone_cmdr_acceptable_percent:
            raise ValueError("zone_cmdr_failure_percent must be < zone_cmdr_acceptable_percent")
        if self.zone_swe_failure_percent >= self.zone_swe_acceptable_percent:
            raise ValueError("zone_swe_failure_percent must be < zone_swe_acceptable_percent")
        if self.zone_fop_failure_percent >= self.zone_fop_acceptable_percent:
            raise ValueError("zone_fop_failure_percent must be < zone_fop_acceptable_percent")
        if not 0.0 < self.zone_rcm_acceptable_abs_percent < self.zone_rcm_failure_abs_percent:
            raise ValueError(
                "zone_rcm_acceptable_abs_percent must be in "
                "(0, zone_rcm_failure_abs_percent)"
            )
        if self.robustness_analysis_years < 1:
            raise ValueError("robustness_analysis_years must be >= 1")


DEFAULT_CONFIG = Config()
