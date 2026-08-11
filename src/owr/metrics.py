"""Outcome metrics (Architecture Step 6 / metrics module).

The doc's Step 6 is one of the blank/duplicated sections (FACT_CHECK inconsistency
#4). The four original functions below are the well-defined metrics from the
outline and Phase 3 plan; anything requiring the missing text was left out rather
than invented.

The 2026-08-04 export of
``docs/source/2026-08-04_Software_Architecture_Documentation.md`` fills Step 6 in
as **Component 7, Scenario Metrics Engine**. The functions below the four original
ones implement the well-defined part of that component, per
``docs/archive/plans/PLAN_METRICS_COMPONENT7.md``. Field map, Component 7 contract field to
function:

| Function | Component 7 contract field | Unit of the field |
|---|---|---|
| ``fuel_fired_generation_offset_mwh`` | ``fuel_fired_generation_offset`` | MWh |
| ``fuel_offset_fraction`` | ``fuel_offset_percentage`` | % (fraction x 100) |
| ``cycle_recharge_mismatch_mwh`` | ``cycle_recharge_mismatch`` | MWh |
| ``average_recharge_mismatch_mwh`` | ``average_recharge_mismatch`` | MW in source, MWh here (R4) |
| ``recharge_capacity_mismatch_fraction`` | ``recharge_capacity_mismatch`` | % (fraction x 100) |
| ``capacity_margin_deficit_reduction_mw`` | ``capacity_magin_improvement`` (typo), formula 1 | MW |
| ``net_load_change_percent`` | ``capacity_magin_improvement`` (source typo), formula 2 | % |
| ``recharge_opportunity_mw`` | Component 5 ``recharge_opportunity`` | MWh in source, MW/hr here |
| ``equivalent_full_cycles`` | ``annual_equivalent_full_cycles`` | cycle |
| ``estimated_capital_cost_usd`` / ``cost_per_equivalent_full_cycle_usd`` | capital cost | USD |
| ``stress_window_effectiveness_fraction`` | Metric Thresholds ``SWE`` | fraction |
| ``capacity_margin_deficit_reduction_percent`` | Metric Thresholds ``CMDR`` | % |

Open questions this module carries (same identifiers the CLI's ``open_questions``
block uses):

1. ``capacity_margin_metric_definition``. Component 7 holds two formulas under
   "Capacity Margin Deficit Reduction": a per-hour MW deficit reduction floored at
   zero, and the legacy percentage change in net load. Both are implemented, under
   distinct names. Which one is the metric, and is the percentage form retired?
2. ``recharge_opportunity_definition``. Component 5 lists
   ``recharge_opportunity | MWh | @``. Implemented here as surplus wind in the
   hour, before the state-of-charge and power clamps. A forward-looking forecast
   reading is possible and would measure a different thing.
3. ``recharge_capacity_denominator``. What is ``maximum_available_capacity``?
   Recommended reading: ``total_mwh - min_soc_mwh`` (the Overview's 70% Available
   Charge band). The alternative, full ``total_mwh``, differs by about 1.43x.
4. ``fuel_offset_definition``. The formula computes fossil generation minus clean
   supply, which reads as fossil generation remaining, while the name reads as
   fossil generation displaced. The source also does not define
   ``total_generation(t)``.
5. ``stress_window_effectiveness_numerator``. Implemented as the discharge leg
   (D5); two sources agree; confirm with the team. Component 7 writes
   ``charge_dispatched(t)``; the Overview Metrics tab and the Metric Thresholds
   PDF both write ``capacity_dispatched(t)`` for the same series, and both name
   the discharge leg. See
   ``docs/archive/plans/PLAN_METRICS_COMPONENT7.md`` section 1.
6. ``capital_cost_constants``. No source value exists for
   ``est_transmission_cost_per_mile``, ``est_storage_unit_cost`` or
   ``solution_lifetime``; see ``config.py``.
7. ``cmdr_scalar_aggregation``. CMDR aggregates as a ratio of sums over the
   event's stressed hours (D6), matching the Metric Thresholds PDF's derivation
   ``4,050 MWh dispatch / 43,200 MWh deficit = 9.4%``. The alternative, a mean
   of per-hour ratios, gives a different number and no source computes it.

Conventions applying to every Component 7 function below (full detail in
``docs/archive/plans/PLAN_METRICS_COMPONENT7.md`` section 2):

- Inputs are ``collections.abc.Sequence[float]``; no pandas, no numpy.
- Every function with two or more same-unit arguments makes them keyword-only.
- The return unit is in the function name (``_mwh``, ``_mw``, ``_percent``,
  ``_fraction``).
- A denominator that cannot be zero in a physically valid scenario raises
  ``ValueError``. A result undefined for an empty input returns ``None``. No
  function returns ``0.0``, ``NaN`` or ``inf`` in place of an undefined result.
  A length mismatch raises ``ValueError`` naming both lengths. A negative element
  in a generation, wind, load, discharge or recharge series raises ``ValueError``,
  except the four series named in ``_require_non_negative_series`` call sites
  below, which are legitimately negative in a valid hour.
- NaN is not guarded here: ``float("nan") <= 0`` is ``False``, so NaN passes every
  check above. The input boundary (``cli._finite_float``, ``scenario_input``) owns
  rejecting non-finite values (risk R6).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

from owr.models import HourState


def _require_positive(value: float, name: str) -> None:
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _require_non_negative_series(values: Sequence[float], name: str) -> None:
    for v in values:
        if v < 0:
            raise ValueError(f"{name} must be non-negative")


def _require_same_length(a: Sequence[float], b: Sequence[float], name_a: str, name_b: str) -> None:
    if len(a) != len(b):
        raise ValueError(f"{name_a} (len {len(a)}) and {name_b} (len {len(b)}) must match")


def net_load(gross_load_mw: float, discharge_mw: float, charge_mw: float = 0.0) -> float:
    """Load the grid must serve after the reserve acts: gross - discharge + charge.

    ``charge_mw`` is charge drawn **from the grid**. ``simulator.simulate`` charges
    only from surplus wind (D2, `docs/archive/plans/PLAN_REVIEW_FIXES.md`) and therefore passes no
    grid charge here, so its ``net_load`` column is ``gross - discharge``. This
    reconciles the two modules without a formula change: this function's signature,
    formula and default stay exactly as they were.
    """
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


def equivalent_full_cycles(discharged_mwh: float, *, rated_energy_mwh: float) -> float:
    """Total energy discharged over a period divided by the asset's rated energy
    capacity. Settled 2026-07-28 (HANDOFF.md decision 5): the metric that survives
    partial cycles, and what degradation and warranty terms are quoted against. A
    half-depth discharge counts 0.5; one event containing a mid-event recharge can
    count more than 1.

    ``discharged_mwh`` is energy **delivered**, i.e. drawn out of the asset at the
    terminals, not energy drawn from the tank before the efficiency term — the two
    differ by the efficiency term. ``rated_energy_mwh`` is keyword-only: both
    arguments are bare same-unit floats, and a swapped call (e.g. ``(1000, 250)``
    instead of ``(250, rated_energy_mwh=1000)``) would silently return a plausible
    but wrong number rather than raising.
    """
    if rated_energy_mwh <= 0:
        raise ValueError("rated_energy_mwh must be positive")
    if discharged_mwh < 0:
        raise ValueError("discharged_mwh must be non-negative")
    return discharged_mwh / rated_energy_mwh


# --- Component 7: fuel security ----------------------------------------------


def fuel_fired_generation_offset_mwh(
    *,
    oil_generation_mw: Sequence[float],
    gas_generation_mw: Sequence[float],
    wind_generation_mw: Sequence[float],
    capacity_dispatched_mw: Sequence[float],
) -> float:
    """Fossil generation remaining after wind and storage supply are netted out.

    Component 7, "Fuel-Fired Generation Offset", in
    ``docs/source/2026-08-04_Software_Architecture_Documentation.md``:

        t=0N(+)(historical_oil_generation(t))+(+)t=0N(historical_gas_generation(t) )
        +(-)t=0N(wind_generation(t)+(-)t=0Ncapacity_dispatched(t)

    The export lost the summation signs; read ``t=0N(x)`` as "sum of x over
    t = 0..N". The formula is then::

        sum(oil) + sum(gas) - sum(wind) - sum(capacity_dispatched)

    Each series is hourly MW; the simulation step is one hour, so a sum over
    hours is MWh (``models.DayProfile.load_mwh`` uses the same convention).
    ``capacity_dispatched_mw[h]`` maps to ``HourlyResult.discharge``: energy
    delivered from storage in that hour, never negative, 0.0 in a charging hour.

    OPEN team question ``fuel_offset_definition`` (see module docstring): (1) this
    formula computes fossil generation *remaining*, while the function/metric name
    reads as fossil generation *displaced* — the two readings invert what a good
    score looks like. Implemented as written; the sign is not flipped (risk R5).
    (2) the source does not define what ``total_generation(t)`` contains for the
    companion ``fuel_offset_fraction`` denominator — imports, nuclear, hydro and
    storage discharge each change it.

    The result may be negative: a negative result means wind and storage supply
    exceeded oil and gas generation over the window.
    """
    _require_same_length(
        oil_generation_mw, gas_generation_mw, "oil_generation_mw", "gas_generation_mw"
    )
    _require_same_length(
        oil_generation_mw, wind_generation_mw, "oil_generation_mw", "wind_generation_mw"
    )
    _require_same_length(
        oil_generation_mw,
        capacity_dispatched_mw,
        "oil_generation_mw",
        "capacity_dispatched_mw",
    )
    _require_non_negative_series(oil_generation_mw, "oil_generation_mw")
    _require_non_negative_series(gas_generation_mw, "gas_generation_mw")
    _require_non_negative_series(wind_generation_mw, "wind_generation_mw")
    _require_non_negative_series(capacity_dispatched_mw, "capacity_dispatched_mw")
    return (
        sum(oil_generation_mw)
        + sum(gas_generation_mw)
        - sum(wind_generation_mw)
        - sum(capacity_dispatched_mw)
    )


def fuel_offset_fraction(offset_mwh: float, *, total_generation_mw: Sequence[float]) -> float:
    """Fuel-fired generation offset as a fraction of total generation.

    Component 7, "Fuel Offset Percentage" (formula quoted per module docstring
    convention): ``fuel_fired_generation_offset(t) / total_generation(t)``. This
    function returns the bare ratio; a reporting layer multiplies by 100 for the
    Overview's ``fuel_offset_percentage`` contract field.

    OPEN team question ``fuel_offset_definition`` part 2: the source does not
    define what ``total_generation(t)`` contains. The sign of the result follows
    the sign of ``offset_mwh``.
    """
    _require_non_negative_series(total_generation_mw, "total_generation_mw")
    total = sum(total_generation_mw)
    if total <= 0:
        raise ValueError("sum(total_generation_mw) must be positive")
    return offset_mwh / total


# --- Component 7: recharge mismatch family ------------------------------------


def recharge_opportunity_mw(
    *,
    hourly_wind_mw: Sequence[float],
    hourly_load_mw: Sequence[float],
    hourly_discharge_mw: Sequence[float],
    hourly_state: Sequence[HourState],
) -> list[float]:
    """Per-hour wind energy available to recharge storage but not yet claimed,
    now schedule-driven rather than a restated surplus formula:

    | Hour state | Value |
    |---|---|
    | ``PRE_CHARGE``, ``ACTIVE_OFF_PEAK`` | ``wind[h]`` |
    | ``ACTIVE_RAMP_UP``, ``ACTIVE_PEAK``, ``ACTIVE_RAMP_DOWN`` | dispatch-hour surplus (below) |
    | ``NON_EVENT`` | ``0.0`` |

    The dispatch-hour surplus is the old rule, restated:
    ``max(0.0, wind - max(0.0, load - discharge))``.

    D4: ``PRE_CHARGE`` and ``ACTIVE_OFF_PEAK`` hours route all their wind to
    storage under the event-relative policy, so the opportunity equals the
    wind itself on those hours. ``NON_EVENT`` hours route all wind to the grid
    by design, so no recharge opportunity exists to miss on them. The dispatch
    hours keep the old surplus-above-net-load formula: storage still competes
    with load on those hours, and that is the one place in this module the
    retired rule legitimately survives (Section 13.1's guard test pins this).

    Do **not** add a field to ``HourlyResult``/``DailyResult``/``SimulationResult``
    for this: ``api/pg_store.py::_load_result`` rebuilds ``SimulationResult`` from
    the database, so a new field would silently read back as its default without
    migration 004.

    OPEN team question ``recharge_opportunity_definition`` (module docstring):
    Component 5 lists ``recharge_opportunity | MWh | @`` and describes the step as
    "Estimate available recharge throughout the remaining forecast horizon", which
    admits a forward-looking forecast reading. Under that reading the mismatch
    this family reports would measure forecast error; under the reading
    implemented here it measures wind energy that was available but not stored.
    """
    _require_same_length(hourly_wind_mw, hourly_load_mw, "hourly_wind_mw", "hourly_load_mw")
    _require_same_length(
        hourly_wind_mw, hourly_discharge_mw, "hourly_wind_mw", "hourly_discharge_mw"
    )
    _require_same_length(hourly_wind_mw, hourly_state, "hourly_wind_mw", "hourly_state")
    _require_non_negative_series(hourly_wind_mw, "hourly_wind_mw")
    _require_non_negative_series(hourly_load_mw, "hourly_load_mw")
    _require_non_negative_series(hourly_discharge_mw, "hourly_discharge_mw")
    result = []
    for wind, load, discharge, state in zip(
        hourly_wind_mw, hourly_load_mw, hourly_discharge_mw, hourly_state, strict=True
    ):
        if state.charges_from_wind:
            result.append(wind)
        elif state.is_dispatch_hour:
            result.append(max(0.0, wind - max(0.0, load - discharge)))
        else:
            result.append(0.0)
    return result


def cycle_recharge_mismatch_mwh(
    *,
    recharge_opportunity_mw: Sequence[float],
    actual_recharged_mw: Sequence[float],
) -> float:
    """Recharge opportunity missed over one cycle: ``sum(opportunity) -
    sum(actual_recharged)``.

    A "cycle" is the source's span from ``tstart`` to ``tend``, one stress
    event. This function sums whatever pair of series the caller passes and
    cannot check that the pair covers one event; the caller owns the boundary,
    and every docstring/printed label must name the boundary it used:

    - ``simulate()`` runs one span per call. When the CLI caller selects a
      detected window with ``--window N``, the span is exactly that window
      (``cli.py`` slices ``days[first_day_idx : last_day_idx + 1]``), so the result
      is one event's mismatch.
    - Under the CLI default ``--window all``, the span is every file day after
      the lead days, so the result covers non-stress days too. The CLI reports
      this as a **span** total (``span_recharge_mismatch_mwh``) and labels it as
      such, with the window basis on the same line. Per-event breakdown belongs
      to the five-winter loop, out of scope here.

    The result may be negative; the Overview's RCM score table runs on ± values,
    so it is not floored. Two empty series return ``0.0``.
    """
    _require_same_length(
        recharge_opportunity_mw,
        actual_recharged_mw,
        "recharge_opportunity_mw",
        "actual_recharged_mw",
    )
    _require_non_negative_series(recharge_opportunity_mw, "recharge_opportunity_mw")
    _require_non_negative_series(actual_recharged_mw, "actual_recharged_mw")
    return sum(recharge_opportunity_mw) - sum(actual_recharged_mw)


def average_recharge_mismatch_mwh(cycle_mismatches_mwh: Sequence[float]) -> float | None:
    """Arithmetic mean of the per-cycle mismatch values, or ``None`` when the
    sequence is empty (undefined, follows ``budget.recharge_sufficiency_ratio``).

    The intended input is one value per stress event across a winter. Input
    values may be any sign; a single-element list returns that element
    unchanged.

    Risk R4: the Component 7 contract labels ``average_recharge_mismatch`` MW,
    but its inputs (``cycle_recharge_mismatch_mwh``) are MWh, and the mean of MWh
    values is MWh. This function returns MWh, not MW, and a reporting layer must
    not relabel it MW.
    """
    if not cycle_mismatches_mwh:
        return None
    return sum(cycle_mismatches_mwh) / len(cycle_mismatches_mwh)


def recharge_capacity_mismatch_fraction(
    average_mismatch_mwh: float, *, maximum_available_capacity_mwh: float
) -> float:
    """Average recharge mismatch as a fraction of the storage asset's available
    capacity: ``average_mismatch_mwh / maximum_available_capacity_mwh``.

    ``maximum_available_capacity_mwh`` must be positive, else raise
    ``ValueError`` (division-by-zero policy). The result may be any sign. A
    reporting layer multiplies this value by 100 for display: the Overview's RCM
    score bands are in percent.

    OPEN team question ``recharge_capacity_denominator`` (module docstring): the
    source description cell is ``@``. The reading this module recommends to
    callers is ``asset.total_mwh - asset.min_soc_mwh``, the Overview's Available
    Charge band (``0 <= Available Charge <= 70% Total Capacity``). The
    alternative reading is the full ``total_mwh``; the two differ by a factor of
    about 1.43 at the shipped fractions. This function stays free of
    ``StorageAsset``: ``metrics.py`` imports no asset or result type from
    ``models`` (``recharge_opportunity_mw`` imports ``HourState``, the lightest
    possible carrier of the hour classification).
    """
    _require_positive(maximum_available_capacity_mwh, "maximum_available_capacity_mwh")
    return average_mismatch_mwh / maximum_available_capacity_mwh


# --- Component 7: capacity margin, both formulas ------------------------------


def capacity_margin_deficit_reduction_mw(
    *, capacity_margin_with_storage_mw: float, capacity_margin_without_storage_mw: float
) -> float:
    """Improvement in capacity margin the reserve provides at one hour, floored
    at zero: ``max(0.0, with_storage - without_storage)``.

    Source: ``dCM(t)=max(0,(+)CM_with_storage(t)-(+)CM_without_storage(t))``.
    Both inputs come from the existing ``capacity_margin(available_capacity_mw,
    net_load_mw)``. Margins may be negative, so there is no sign validation.

    Algebraic identity: at one hour the available capacity is the same in both
    cases, so it cancels, and this equals
    ``max(0.0, net_load_without_storage_mw - net_load_with_storage_mw)``. The
    metric therefore needs no capacity input, and a caller with only the two net
    loads reaches the same number.

    OPEN team question ``capacity_margin_metric_definition`` (module docstring),
    citing ``docs/archive/reviews/FINDINGS_SOURCE_DOCS_2026-08-05.md`` section 3: Component 7
    carries two formulas under one "Capacity Margin Deficit Reduction" heading, in
    different units. This function implements the per-hour MW formula;
    ``net_load_change_percent`` implements the other, the legacy percentage-change
    formula. Both are implemented under distinct names; this plan resolves
    nothing about which one is the metric.
    """
    return max(0.0, capacity_margin_with_storage_mw - capacity_margin_without_storage_mw)


def capacity_margin_deficit_reduction_series_mw(
    *,
    capacity_margin_with_storage_mw: Sequence[float],
    capacity_margin_without_storage_mw: Sequence[float],
) -> list[float]:
    """Per-hour form of ``capacity_margin_deficit_reduction_mw``. Equal lengths
    required; no element-level sign check (margins are legitimately negative)."""
    _require_same_length(
        capacity_margin_with_storage_mw,
        capacity_margin_without_storage_mw,
        "capacity_margin_with_storage_mw",
        "capacity_margin_without_storage_mw",
    )
    return [
        capacity_margin_deficit_reduction_mw(
            capacity_margin_with_storage_mw=with_storage,
            capacity_margin_without_storage_mw=without_storage,
        )
        for with_storage, without_storage in zip(
            capacity_margin_with_storage_mw, capacity_margin_without_storage_mw, strict=True
        )
    ]


def net_load_change_percent(
    *, net_load_dispatch_mw: Sequence[float], net_load_observed_mw: Sequence[float]
) -> float:
    """Percentage change in net load the reserve dispatch produced, over a
    window: ``(sum(dispatch) - sum(observed)) / sum(observed) * 100``.

    Source:
    ``t=0N(net_load_dispatch(t)-net_load_observed(t)) / t=0N(net_load_observed(t)) * 100``.

    Equal lengths required. ``sum(net_load_observed_mw)`` must be greater than
    zero, else raise ``ValueError`` (it is the divisor). **No element-level
    non-negative check is applied to either series**: net load goes below zero in
    an hour when wind exceeds load, a valid hour the Overview's Duck Curve
    definition names. Only the sum of the observed series is checked.

    OPEN team question ``capacity_margin_metric_definition`` (module docstring),
    citing ``docs/archive/reviews/FINDINGS_SOURCE_DOCS_2026-08-05.md`` section 3: this function
    implements the legacy percentage-change formula;
    ``capacity_margin_deficit_reduction_mw`` implements the per-hour MW formula
    under the same Component 7 heading. The Overview still labels this formula
    "Capacity Margin Improvement", while the Component 7 heading now reads
    "Capacity Margin Deficit Reduction".

    The sign as written is negative when storage lowers net load (a good
    outcome). The Overview scores this metric as ``(0, <=0MW; 50, =75; 100,
    >=150)``, which treats a larger positive number as better and states MW
    units for a percentage metric. This function does not flip the sign and does
    not clamp; the conflict is not resolved here.
    """
    _require_same_length(
        net_load_dispatch_mw, net_load_observed_mw, "net_load_dispatch_mw", "net_load_observed_mw"
    )
    observed_sum = sum(net_load_observed_mw)
    if observed_sum <= 0:
        raise ValueError("sum(net_load_observed_mw) must be positive")
    return (sum(net_load_dispatch_mw) - observed_sum) / observed_sum * 100


# --- Component 7: capital costs (optional; see config.py) --------------------


def estimated_capital_cost_usd(
    *,
    transmission_cost_per_mile_usd: float,
    miles: float,
    storage_unit_cost_usd: float,
    total_unit_count: float,
) -> float:
    """Estimated capital cost: ``per_mile * miles + unit_cost * unit_count``.

    All four inputs must be non-negative. Parks the constants named in
    ``Config``'s ``capital_cost_constants`` open question
    (``est_transmission_cost_per_mile``, ``est_storage_unit_cost``): no source
    value exists for either yet.
    """
    for value, name in (
        (transmission_cost_per_mile_usd, "transmission_cost_per_mile_usd"),
        (miles, "miles"),
        (storage_unit_cost_usd, "storage_unit_cost_usd"),
        (total_unit_count, "total_unit_count"),
    ):
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    return transmission_cost_per_mile_usd * miles + storage_unit_cost_usd * total_unit_count


def cost_per_equivalent_full_cycle_usd(
    capital_cost_usd: float,
    *,
    annual_equivalent_full_cycles: float,
    solution_lifetime_years: float,
) -> float:
    """Capital cost per equivalent full cycle delivered over the asset's
    lifetime: ``capital_cost / (annual_efc * lifetime_years)``.

    ``annual_equivalent_full_cycles`` is the yearly total of
    ``equivalent_full_cycles``, which links to the open question
    ``cycles_per_year`` already carried by ``cli.py``. Both divisor parts must be
    positive, else raise ``ValueError`` (division-by-zero policy). The capital
    cost must be non-negative. Parks the ``solution_lifetime`` constant named in
    ``Config``'s ``capital_cost_constants`` open question: no source value exists
    yet.
    """
    if capital_cost_usd < 0:
        raise ValueError("capital_cost_usd must be non-negative")
    _require_positive(annual_equivalent_full_cycles, "annual_equivalent_full_cycles")
    _require_positive(solution_lifetime_years, "solution_lifetime_years")
    return capital_cost_usd / (annual_equivalent_full_cycles * solution_lifetime_years)


# --- Metric Thresholds v1.1: SWE and CMDR --------------------------------------


def stress_window_effectiveness_fraction(
    *,
    capacity_dispatched_mw: Sequence[float],
    oil_generation_mw: Sequence[float],
    gas_generation_mw: Sequence[float],
) -> float:
    """Storage energy delivered over an event's stressed hours, as a fraction of the
    fossil generation those hours ran.

    Component 7 writes the numerator ``charge_dispatched(t)``; the Overview
    Metrics tab and the Metric Thresholds PDF both write ``capacity_dispatched(t)``
    for the same series (D5a). ``capacity_dispatched_mw[h]`` maps to
    ``HourlyResult.discharge``, per D5: two sources agree that the SWE numerator
    is the discharge leg, not the charge leg.

    ``SWE = sum(capacity_dispatched(t)) / sum(oil_generation(t) + gas_generation(t))``,
    per ``docs/source/2026-08-05_Metric_Thresholds_v1.1.pdf``: "Denominator is
    fossil fuel generation only ... This makes SWE a direct fossil displacement
    metric."

    The caller supplies stressed hours only; this function applies no mask of its
    own. Returns the bare ratio; a reporting layer multiplies by 100.
    """
    _require_same_length(
        capacity_dispatched_mw, oil_generation_mw, "capacity_dispatched_mw", "oil_generation_mw"
    )
    _require_same_length(
        capacity_dispatched_mw, gas_generation_mw, "capacity_dispatched_mw", "gas_generation_mw"
    )
    _require_non_negative_series(capacity_dispatched_mw, "capacity_dispatched_mw")
    _require_non_negative_series(oil_generation_mw, "oil_generation_mw")
    _require_non_negative_series(gas_generation_mw, "gas_generation_mw")
    fossil_sum = sum(oil_generation_mw) + sum(gas_generation_mw)
    if fossil_sum <= 0:
        raise ValueError("sum(oil_generation_mw) + sum(gas_generation_mw) must be positive")
    return sum(capacity_dispatched_mw) / fossil_sum


def capacity_margin_deficit_reduction_percent(
    *,
    capacity_dispatched_mw: Sequence[float],
    hourly_load_mw: Sequence[float],
    p90_threshold_mwh: float,
) -> float | None:
    """CMDR as the contract-facing percent: the share of the event's capacity
    deficit that storage removed.

    A stressed hour is ``Load(t) > p90_threshold_mwh``. This function builds
    that mask itself and gates **both** sums with it (D6)::

        numerator   = sum(max(0.0, capacity_dispatched(t)))  over stressed hours
        denominator = sum(Load(t) - p90_threshold_mwh)       over stressed hours
        result      = numerator / denominator * 100

    An hour at or below the threshold contributes nothing to either sum.
    Crediting dispatch in a non-deficit hour would report a reduction of a
    deficit that does not exist. OPEN team question ``cmdr_scalar_aggregation``
    (module docstring): this ratio-of-sums reading matches the Metric
    Thresholds PDF's derivation, ``4,050 MWh dispatch / 43,200 MWh deficit =
    9.4%``, over 54 stressed hours. The alternative, a mean of per-hour ratios,
    gives a different number and no source computes it.

    Returns ``None`` when no hour is stressed. A window with no hour above the
    threshold has no deficit to reduce, which is physically valid (D10a): a
    consumer must read ``None`` as "no deficit", not "model failure".
    """
    _require_same_length(
        capacity_dispatched_mw, hourly_load_mw, "capacity_dispatched_mw", "hourly_load_mw"
    )
    _require_non_negative_series(capacity_dispatched_mw, "capacity_dispatched_mw")
    _require_non_negative_series(hourly_load_mw, "hourly_load_mw")
    if not math.isfinite(p90_threshold_mwh) or p90_threshold_mwh <= 0:
        raise ValueError("p90_threshold_mwh must be finite and positive")
    numerator = 0.0
    denominator = 0.0
    stressed = False
    for dispatch, load in zip(capacity_dispatched_mw, hourly_load_mw, strict=True):
        if load > p90_threshold_mwh:
            stressed = True
            numerator += max(0.0, dispatch)
            denominator += load - p90_threshold_mwh
    if not stressed:
        return None
    return numerator / denominator * 100
