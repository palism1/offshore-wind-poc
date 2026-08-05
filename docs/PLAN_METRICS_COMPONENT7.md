# Implementation plan — metrics.py toward Architecture Component 7

Written 2026-08-05. Revised 2026-08-05 after adversarial review; see section 12.
Target module: `src/owr/metrics.py`. Tests: `tests/test_metrics.py`.

Sources this plan implements:

- `docs/source/2026-08-04_Software_Architecture_Documentation.md`, Component 7, Scenario
  Metrics Engine.
- `docs/source/2026-08-05_Overview_Document.md`, Metrics tab.
- `docs/FINDINGS_SOURCE_DOCS_2026-08-05.md` section 3, the two conflicting capacity-margin
  formulas.

Baseline to hold: 360 passed, 3 skipped, ruff clean (measured 2026-08-05).

---

## 1. Scope

**In scope.** Seven new pure functions in `metrics.py`, one new module docstring section, and
one additive block in the `simulate` CLI summary.

| Metric | Function | Phase |
|---|---|---|
| Fuel-Fired Generation Offset | `fuel_fired_generation_offset_mwh` | 1 |
| Fuel Offset Percentage | `fuel_offset_fraction` | 1 |
| Cycle Recharge Mismatch | `cycle_recharge_mismatch_mwh` | 2 |
| Average Recharge Mismatch | `average_recharge_mismatch_mwh` | 2 |
| Recharge Capacity Mismatch | `recharge_capacity_mismatch_fraction` | 2 |
| (input helper) recharge opportunity | `recharge_opportunity_mw` | 2 |
| Capacity Margin Deficit Reduction, formula 1 | `capacity_margin_deficit_reduction_mw` + `_series_mw` | 3 |
| Capacity Margin Deficit Reduction, formula 2 | `net_load_change_percent` | 3 |
| CLI summary wiring, recharge family only | `cli._build_report` / `cli._render_table` | 4 |
| Estimated Capital Costs, Cost per EFC | `estimated_capital_cost_usd`, `cost_per_equivalent_full_cycle_usd` | 5, optional |

**Out of scope, with the reason for each.**

- **Stress Window Effectiveness.** The numerator field name is ambiguous, and the source does
  not define it. Component 7 writes `charge_dispatched(t)`; the Overview Metrics tab writes
  `capacity_dispatched(t)`. The Component 5 data contract carries both `charge_power` and
  `charge_dispatched`, each with an `@` description cell, so nothing in the source states which
  direction `charge_dispatched` measures.
  `docs/FINDINGS_SOURCE_DOCS_2026-08-05.md` section 2 records the rename
  "`dispatched_capacity` became `charge_dispatched`", which points at discharge and would make
  the two numerators agree. That reading is likely and unconfirmed. Hold the metric out until
  the team confirms it. The cost of adding it later is one function.
- **Scenario Robustness Score.** Every threshold is `@`.
- **The five-winter loop**, oil and gas ingestion, migration 004, API and Postgres wiring.
- **Capacity Margin Deficit Reduction in the CLI.** The engine holds no without-storage net
  load series. Building one needs a baseline decision (gross load, or load minus wind).
- **The Component 5 dispatch change** from a sum to an exclusive choice
  (`FINDINGS_SOURCE_DOCS_2026-08-05.md` section 2). Separate task.

---

## 2. Conventions that apply to every phase

**2.1 Sequence type.** Inputs are `collections.abc.Sequence[float]`. Outputs are `float`,
`list[float]`, or `float | None`. No pandas and no numpy: the module has zero third-party
imports today, and each formula is one pass of `sum()` or `zip()`. Use `len()`, `sum()` and
`zip()` only. Do not index positionally.

**2.2 Keyword-only arguments.** Every function that takes two or more same-unit arguments
makes all of them keyword-only. Four bare `Sequence[float]` in one call is the swap hazard
that `equivalent_full_cycles` already guards against, and a swapped call returns a plausible
wrong number instead of raising.

**2.3 Unit in the name.** The new functions carry the return unit in the name
(`_mwh`, `_mw`, `_percent`, `_fraction`). Component 7 mixes MW, MWh, `%` and bare ratios in
one family. The four existing functions keep their present names.

**2.4 Percent against fraction.** A source formula that carries `• 100` returns a percentage
and the name ends in `_percent`. A source formula without `• 100` returns the dimensionless
ratio and the name ends in `_fraction`. The docstring states the Component 7 contract field
and its `%` unit, so the reporting layer multiplies by 100. This follows `severity_reduction`,
which returns a fraction that `cli.py` renders as a percentage. Any reporting layer that
prints a `_fraction` value multiplies it by 100 and prints the `%` sign; section 7.2 applies
this rule.

**2.5 Hourly MW summed to MWh.** Component 6 delivers the generation series in MW. The
simulation step is one hour, so a sum over hours is MWh. This is the convention
`models.DayProfile.load_mwh` already uses. State it in each docstring that sums MW into MWh.

**2.6 Division-by-zero and undefined-value policy.** Component 7 requires
"divide-by-zero protection" and "undefined values handled according to policy". The policy
line in the source is `@`, so this plan defines it:

- A denominator that cannot be zero in a physically valid scenario raises `ValueError`.
  This covers total generation, maximum available capacity, and the sum of observed net load.
  It follows `severity_reduction` and `equivalent_full_cycles`.
- A result that is genuinely undefined for an empty input returns `None`. This covers the
  average over zero cycles. It follows `budget.recharge_sufficiency_ratio`.
- No function returns `0.0`, `NaN` or `inf` in place of an undefined result.
- A length mismatch between two series raises `ValueError` and names both lengths.
- A negative value in a generation, wind, load, discharge or recharge series raises
  `ValueError`. Component 6 validation rule: "no negative generation".
- **Four series are exempt from the element rule above**, because each is legitimately
  negative in a valid hour: `net_load_dispatch_mw` and `net_load_observed_mw` (high wind puts
  net load below zero), and the two capacity-margin series (a negative margin is a shortfall).
  Do not add an element-level sign check to them. Their denominator check stays.

**2.7 No NaN guard.** `float("nan") <= 0` is `False`, so a NaN input passes the guards above.
The input boundary owns this: `cli._finite_float` and `scenario_input` reject non-finite
values. Do not add NaN checks inside `metrics.py`. Record this as risk R6.

**2.8 Shared private helpers.** Add three module-private helpers, in the style of
`storage_physics._require_positive`:

```python
def _require_positive(value: float, name: str) -> None
def _require_non_negative_series(values: Sequence[float], name: str) -> None
def _require_same_length(a: Sequence[float], b: Sequence[float], name_a: str, name_b: str) -> None
```

**2.9 Docstring citation format.** The Google Docs export dropped the summation glyphs. Quote
the mangled source once, then give the ASCII reading. Cite the file and the heading, never a
line number. Example, to copy:

```
Component 7, "Fuel-Fired Generation Offset", in
``docs/source/2026-08-04_Software_Architecture_Documentation.md``:

    t=0N(+)(historical_oil_generation(t))+(+)t=0N(historical_gas_generation(t) )
    +(-)t=0N(wind_generation(t)+(-)t=0Ncapacity_dispatched(t)

The export lost the summation signs; read ``t=0N(x)`` as "sum of x over t = 0..N".
The formula is then::

    sum(oil) + sum(gas) - sum(wind) - sum(capacity_dispatched)
```

---

## 3. Phase 0 — module docstring and the field map

**Goal.** Point the module at Component 7 and record which function answers which contract
field, so a reader never has to guess whether a name was invented.

Rewrite the `metrics.py` module docstring. Keep the historical note that the Jul 30 Step 6 was
blank, and add that the 2026-08-04 export fills it as Component 7. Add this table, in the style
of the `simulator.hourly_frame` mapping table:

| Function | Component 7 contract field | Unit of the field |
|---|---|---|
| `fuel_fired_generation_offset_mwh` | `fuel_fired_generation_offset` | MWh |
| `fuel_offset_fraction` | `fuel_offset_percentage` | % (fraction × 100) |
| `cycle_recharge_mismatch_mwh` | `cycle_recharge_mismatch` | MWh |
| `average_recharge_mismatch_mwh` | `average_recharge_mismatch` | MW in the source, MWh here (R4) |
| `recharge_capacity_mismatch_fraction` | `recharge_capacity_mismatch` | % (fraction × 100) |
| `capacity_margin_deficit_reduction_mw` | `capacity_magin_improvement` (source typo), formula 1 | MW |
| `net_load_change_percent` | `capacity_magin_improvement` (source typo), formula 2 | % |
| `recharge_opportunity_mw` | Component 5 `recharge_opportunity` | MWh in the source, MW per hour here |
| `equivalent_full_cycles` | `annual_equivalent_full_cycles` | cycle |

Below the table, list the open questions this module carries, with the same identifiers the
CLI uses. Section 10 gives the text.

**Verify.** `uv run pytest tests/test_metrics.py -q` still reports the same count as the
baseline. `uv run ruff check .` passes.

---

## 4. Phase 1 — fuel security metrics

### 4.1 Signatures

```python
def fuel_fired_generation_offset_mwh(
    *,
    oil_generation_mw: Sequence[float],
    gas_generation_mw: Sequence[float],
    wind_generation_mw: Sequence[float],
    capacity_dispatched_mw: Sequence[float],
) -> float

def fuel_offset_fraction(
    offset_mwh: float,
    *,
    total_generation_mw: Sequence[float],
) -> float
```

### 4.2 Behavior

`fuel_fired_generation_offset_mwh` returns
`sum(oil) + sum(gas) - sum(wind) - sum(capacity_dispatched)`.

- All four series must have the same length. A mismatch means the caller aligned different
  windows. Raise `ValueError`.
- All four series must be non-negative.
- Four empty series return `0.0`.
- The result may be negative. State in the docstring that a negative result means the wind
  and storage supply exceeded the oil and gas generation over the window.
- `capacity_dispatched_mw[h]` maps to `HourlyResult.discharge`, which is energy delivered from
  storage in that hour and never negative. A charging hour enters as `0.0`. This matches the
  "energy delivered" convention `equivalent_full_cycles` already documents.

`fuel_offset_fraction` returns `offset_mwh / sum(total_generation_mw)`.

- `total_generation_mw` must be non-negative and its sum must be greater than zero, else
  raise `ValueError` (policy 2.6).
- The sign of the result follows the sign of `offset_mwh`.

### 4.3 Docstring duties

Both docstrings quote the source formula per 2.9, from Component 7 and from the Overview
Metrics tab. Both name the open question `fuel_offset_definition` and state its two parts:

1. The formula computes fossil generation minus clean supply, which reads as
   "fuel-fired generation that remains", while the metric name reads as
   "fuel-fired generation displaced". The two readings invert what a good score looks like.
   Implement the formula as written. Do not flip the sign.
2. The source does not define what `total_generation(t)` contains. Imports, nuclear, hydro and
   storage discharge each change the denominator.

### 4.4 Tests

Use one fixture of three hours: `oil = [100, 200, 300]`, `gas = [50, 50, 50]`,
`wind = [10, 20, 30]`, `dispatched = [5, 5, 5]`.

1. `fuel_fired_generation_offset_mwh(...) == 675.0` (600 + 150 − 60 − 15).
2. Zero wind and zero dispatch give `750.0`.
3. Zero oil and zero gas give `-75.0`. Comment the sign, citing R5.
4. Four empty series give `0.0`.
5. A length mismatch on each of the four arguments raises `ValueError` (parametrize).
6. A negative value in each of the four series raises `ValueError` (parametrize).
7. Positional call raises `TypeError`, matching
   `test_equivalent_full_cycles_rated_energy_is_keyword_only`.
8. `fuel_offset_fraction(675.0, total_generation_mw=[200, 300, 400]) == approx(0.75)`.
9. `fuel_offset_fraction(x, total_generation_mw=[0, 0, 0])` raises `ValueError`.
10. `fuel_offset_fraction(x, total_generation_mw=[])` raises `ValueError`.
11. A negative offset gives a negative fraction.

**Verify.** `uv run pytest tests/test_metrics.py -q`.

---

## 5. Phase 2 — recharge mismatch family

### 5.1 Signatures

```python
def recharge_opportunity_mw(
    *,
    hourly_wind_mw: Sequence[float],
    hourly_load_mw: Sequence[float],
    hourly_discharge_mw: Sequence[float],
) -> list[float]

def cycle_recharge_mismatch_mwh(
    *,
    recharge_opportunity_mw: Sequence[float],
    actual_recharged_mw: Sequence[float],
) -> float

def average_recharge_mismatch_mwh(cycle_mismatches_mwh: Sequence[float]) -> float | None

def recharge_capacity_mismatch_fraction(
    average_mismatch_mwh: float,
    *,
    maximum_available_capacity_mwh: float,
) -> float
```

### 5.2 What a cycle is, and what it is not

The source sums from `tstart` to `tend`, which is the span of one stress event.
`cycle_recharge_mismatch_mwh` sums whatever pair of series the caller passes, and the function
cannot check that the pair covers one event. The caller owns the boundary. Every docstring and
every printed label must name the boundary it used:

- `simulate()` runs one span per call. When the caller selects a detected window with
  `--window N`, the span is exactly that window (`cli.py` slices `days[w0:w1+1]`), so the
  result is one event's mismatch.
- Under the default `--window all`, the span is every file day after the lead days, so the
  result covers non-stress days too. On `examples/synthetic_winter_stress.csv` that is 7 days
  around one 3-day window.
- The CLI therefore reports a **span** total and labels it as such, with the window basis on
  the same line (section 7). Per-event breakdown belongs to the five-winter loop, which is out
  of scope.

Put this paragraph in the `cycle_recharge_mismatch_mwh` docstring.

### 5.3 Behavior

`recharge_opportunity_mw` returns, per hour,
`max(0.0, wind - max(0.0, load - discharge))`.

This restates the rule `simulator.simulate` applies before it clamps, at the two lines that
compute `net` and `surplus_wind`. The simulator discards the value, so the metric layer
rebuilds it from `DayProfile.hourly_wind_mw`, `HourlyResult.gross_load` and
`HourlyResult.discharge`. Do **not** add a field to `HourlyResult`, `DailyResult` or
`SimulationResult`: `api/pg_store.py::_load_result` rebuilds `SimulationResult` from the
database, so a new field would silently read back as its default and would need migration 004.

- The three series must have the same length and must be non-negative.
- Docstring must name the duplication, cite `simulator.py`, and point at the drift-guard test
  (5.5 item 12). The same documented-duplication pattern already exists at
  `cli._severity_reduction`.
- Docstring must name the open question `recharge_opportunity_definition`. Component 5 lists
  `recharge_opportunity | MWh | @` and describes the step as "Estimate available recharge
  throughout the remaining forecast horizon". A forward-looking forecast reading is possible.
  Under that reading the mismatch measures forecast error. Under the reading implemented here
  it measures wind energy that was available but not stored.

`cycle_recharge_mismatch_mwh` returns `sum(opportunity) - sum(actual_recharged)`.

- Equal lengths, both non-negative.
- The result may be negative. The Overview RCM score table runs on `±` values, so do not
  floor it.
- Two empty series return `0.0`.

`average_recharge_mismatch_mwh` returns the arithmetic mean of the cycle values, and `None`
for an empty sequence. Input values may be any sign. The intended input is one value per stress
event across a winter. A single-element list returns that element unchanged.

`recharge_capacity_mismatch_fraction` returns
`average_mismatch_mwh / maximum_available_capacity_mwh`.

- `maximum_available_capacity_mwh` must be positive, else raise `ValueError`.
- The result may be any sign.
- Docstring names the open question `recharge_capacity_denominator`. The source description
  cell is `@`. The reading this plan recommends to callers is
  `asset.total_mwh - asset.min_soc_mwh`, which is the Overview's Available Charge band
  (`0 ≤ Available Charge ≤ 70% Total Capacity`). The alternative reading is the full
  `total_mwh`. The two differ by a factor of about 1.43 at the shipped fractions.
- Docstring states that the Overview RCM score bands are in percent, so a reporting layer
  multiplies this value by 100 (rule 2.4).
- Keep the function free of `StorageAsset`. `metrics.py` imports nothing from `models` today.

### 5.4 Docstring duties

Quote all three Component 7 formulas per 2.9, including the source typo `recharge_opporunity`.
Record in `average_recharge_mismatch_mwh` that the source contract labels the field MW while
its inputs are MWh, that the mean of MWh values is MWh, and that the reporting layer must not
relabel it MW (risk R4).

### 5.5 Tests

12 tests. Items 1 to 11 are unit tests; item 12 is the drift guard.

1. `recharge_opportunity_mw(wind=[100, 0, 50], load=[80, 80, 10], discharge=[0, 20, 0])`
   returns `[20.0, 0.0, 40.0]`.
2. Discharge above load drives net negative: `wind=[30], load=[10], discharge=[20]` returns
   `[30.0]`, proving the inner `max(0.0, ...)` clamps net load, not wind.
3. Length mismatch and negative input raise `ValueError` (parametrize over the three series).
4. `cycle_recharge_mismatch_mwh(opportunity=[10, 20, 30], actual=[10, 15, 20]) == 15.0`.
5. Equal series give `0.0`.
6. Actual above opportunity gives a negative result.
7. Length mismatch and negative input raise `ValueError`.
8. `average_recharge_mismatch_mwh([10, 20, 30]) == 20.0`.
9. `average_recharge_mismatch_mwh([]) is None`.
10. `average_recharge_mismatch_mwh([-10, 10]) == 0.0`.
11. `recharge_capacity_mismatch_fraction(700.0, maximum_available_capacity_mwh=14000.0)`
    equals `approx(0.05)`, which is 5% and sits inside the Overview RCM score table. A zero
    and a negative denominator raise `ValueError`. A negative average gives a negative
    fraction.
12. **Drift guard, two assertions with different jobs.**
    - *Assertion A, sanity only.* On a shipped-scale asset (20000 MWh, 2000 MW,
      `starting_soc=total_mwh`), assert `sum(opportunity) >= sum(charge)`. This holds by
      construction, because `soc_engine.clamp_charge` only ever reduces the requested charge
      (`min` of request, headroom and power). It catches a sign error or a swapped argument,
      nothing more.
    - *Assertion B, the real guard.* Build an asset with `total_mwh=1_000_000`,
      `power_mw=1_000_000`, `soc_floor_frac=0.20`, `strategic_reserve_frac=0.10`, and days
      whose wind exceeds load in some hours (for example flat load 1000 MW with wind 2000 MW
      for six hours). Run `simulate(asset, days, starting_soc=asset.min_soc_mwh)`. No clamp
      binds at that scale, so assert `opportunity[h] == approx(charge[h])` for **every** hour.
      This fails the moment the simulator's recharge rule changes shape.

    Rebuild the opportunity series with `recharge_opportunity_mw` from `HourlyResult.gross_load`
    and `HourlyResult.discharge` in both assertions. If assertion B fails, stop and report. Do
    not change `simulator.py` to make it pass.

The shipped fixture `examples/synthetic_winter_stress.csv` has wind at 2000 MW against load at
7500 MW and above, so its recharge opportunity is zero in every hour. Do not use it for items
1 to 12; build the fixture in the test file, as `tests/test_simulator.py::_stress_day` does.

**Verify.** `uv run pytest tests/test_metrics.py -q`.

---

## 6. Phase 3 — capacity margin, both formulas

`docs/FINDINGS_SOURCE_DOCS_2026-08-05.md` section 3 records that Component 7 carries two
formulas under one heading, in different units. This phase implements both under distinct
names and resolves nothing.

### 6.1 Signatures

```python
def capacity_margin_deficit_reduction_mw(
    *,
    capacity_margin_with_storage_mw: float,
    capacity_margin_without_storage_mw: float,
) -> float

def capacity_margin_deficit_reduction_series_mw(
    *,
    capacity_margin_with_storage_mw: Sequence[float],
    capacity_margin_without_storage_mw: Sequence[float],
) -> list[float]

def net_load_change_percent(
    *,
    net_load_dispatch_mw: Sequence[float],
    net_load_observed_mw: Sequence[float],
) -> float
```

### 6.2 Behavior

`capacity_margin_deficit_reduction_mw` returns
`max(0.0, capacity_margin_with_storage_mw - capacity_margin_without_storage_mw)`.

- Source: `ΔCM(t)=max(0,(+)CM_with_storage(t)-(+)CM_without_storage(t))`.
- Margins may be negative, so no sign validation (rule 2.6, exempt list).
- Both inputs come from the existing `capacity_margin(available_capacity_mw, net_load_mw)`.
  Say so in the docstring.
- Record the algebraic identity: at one hour the available capacity is the same in both cases,
  so it cancels, and the result equals `max(0.0, net_load_observed - net_load_dispatch)`. The
  metric therefore needs no capacity input, and a caller with only the two net loads reaches
  the same number.

`capacity_margin_deficit_reduction_series_mw` applies the scalar form per hour. Equal lengths
required. No element-level sign check.

`net_load_change_percent` returns
`(sum(dispatch) - sum(observed)) / sum(observed) * 100`.

- Source: `t=0N(net_load_dispatch(t)-net_load_observed(t)) / t=0N(net_load_observed(t)) • 100`.
- Equal lengths required. `sum(observed)` must be greater than zero, else raise `ValueError`.
- **Do not apply the element-level non-negative check to either series** (rule 2.6, exempt
  list). Net load goes below zero in an hour when wind exceeds load, which is a valid hour and
  which the Overview's Duck Curve definition names. Only the **sum** of the observed series is
  checked, because it is the divisor. State this in the docstring.
- **The sign as written is negative when storage lowers net load.** The Overview scores this
  metric as `(0, ≤0MW; 50, =75; 100, ≥150)`, which treats a larger positive number as better
  and states MW units for a percentage metric. Do not flip the sign and do not clamp. State
  the conflict in the docstring.

### 6.3 Docstring duties

Both docstrings name the open question `capacity_margin_metric_definition` and cite
`docs/FINDINGS_SOURCE_DOCS_2026-08-05.md` section 3. Each states which of the two source
formulas it implements and that the other function implements the other. `net_load_change_percent`
also records that the Overview still labels this formula "Capacity Margin Improvement" and that
the Component 7 heading now reads "Capacity Margin Deficit Reduction".

### 6.4 Tests

1. `capacity_margin_deficit_reduction_mw(with=500.0, without=300.0) == 200.0`.
2. `capacity_margin_deficit_reduction_mw(with=300.0, without=500.0) == 0.0` (floor).
3. Both margins negative, with storage less negative: returns the positive difference.
4. **Cancellation property.** For `available in (10_000.0, 50_000.0)`, build
   `with = capacity_margin(available, 9_000.0)` and
   `without = capacity_margin(available, 9_500.0)`; assert the result is `500.0` for both
   values of `available`.
5. Series version returns `[200.0, 0.0]` for two paired hours; a length mismatch raises
   `ValueError`; a pair of negative margins is accepted and returns a value.
6. `net_load_change_percent(dispatch=[90, 90], observed=[100, 100]) == approx(-10.0)`. Comment
   that the negative sign is the source formula's own sign and cite section 3.
7. **Negative element accepted.** `dispatch=[-50, 200]`, `observed=[-100, 200]` returns
   `approx(50.0)`: the sums are 150 and 100, so the change is +50%. This proves the
   element-level sign check is not applied to the net-load series.
8. `sum(observed) == 0` raises `ValueError`; a negative sum raises `ValueError`.
9. Length mismatch raises `ValueError`; positional call raises `TypeError`.

**Verify.** `uv run pytest tests/test_metrics.py -q`.

---

## 7. Phase 4 — CLI summary wiring, recharge family only

Additive. Nothing existing changes value.

### 7.1 Changes in `src/owr/cli.py`

Import in the existing aliased style beside `_equivalent_full_cycles`:

```python
from owr.metrics import average_recharge_mismatch_mwh as _average_recharge_mismatch_mwh
from owr.metrics import cycle_recharge_mismatch_mwh as _cycle_recharge_mismatch_mwh
from owr.metrics import recharge_capacity_mismatch_fraction as _recharge_capacity_mismatch_fraction
from owr.metrics import recharge_opportunity_mw as _recharge_opportunity_mw
```

Add `HOURS_PER_DAY` to the existing `from owr.models import ...` line.

In `_build_report`, after `energy_charged`:

```python
# One simulate() call is one span. Under --window N the span is one detected
# stress window; under --window all it is every file day after the lead days,
# so this total covers non-stress days too. The key name says "span" for that
# reason; see docs/PLAN_METRICS_COMPONENT7.md section 5.2.
opportunity: list[float] = []
actual: list[float] = []
for day_profile, day_result in zip(span, result.daily, strict=True):
    wind = list(day_profile.hourly_wind_mw) or [0.0] * HOURS_PER_DAY
    opportunity.extend(
        _recharge_opportunity_mw(
            hourly_wind_mw=wind,
            hourly_load_mw=[h.gross_load for h in day_result.hourly],
            hourly_discharge_mw=[h.discharge for h in day_result.hourly],
        )
    )
    actual.extend(h.charge for h in day_result.hourly)
span_mismatch = _cycle_recharge_mismatch_mwh(
    recharge_opportunity_mw=opportunity, actual_recharged_mw=actual
)
average_mismatch = _average_recharge_mismatch_mwh([span_mismatch])
if average_mismatch is None:  # unreachable: the list always holds one element
    raise ValueError("average recharge mismatch is undefined for an empty span list")
max_available = asset.total_mwh - asset.min_soc_mwh
# Defensive: Config rejects a floor sum of 1.0, so max_available > 0 on every CLI path.
recharge_capacity_mismatch = (
    _recharge_capacity_mismatch_fraction(
        average_mismatch, maximum_available_capacity_mwh=max_available
    )
    if max_available > 0
    else None
)
```

Use an explicit `raise`, never `assert`: `python -O` strips assertions, and `cmd_run` already
turns a `ValueError` into `error: ...` on stderr with exit code 2.

The `list(...) or [0.0] * HOURS_PER_DAY` fallback mirrors `simulator.simulate`, which
substitutes 24 zeros when a day carries no wind column.

Add four keys to the `summary` dict, after `min_capacity_margin_at`:

```python
"recharge_opportunity_mwh": sum(opportunity),
"span_recharge_mismatch_mwh": span_mismatch,
"recharge_capacity_mismatch_fraction": recharge_capacity_mismatch,
"maximum_available_capacity_mwh": max_available,
```

The JSON value stays a fraction. `report["simulated"]["window"]` already carries the basis
(`"all"` or the window index), so do not duplicate it in the summary.

Add one entry to `_OPEN_QUESTIONS_STATIC` and one to the `open_questions` list for each of
`recharge_opportunity_definition` and `recharge_capacity_denominator`. Set `"flags": []`
because neither has a command-line flag. Set `handoff_ref` to
`"docs/PLAN_METRICS_COMPONENT7.md open questions"`. Set `value_used` to a short string naming
the interpretation, for example
`"surplus wind after serving net load, before the SoC and power clamps"` and
`"total_mwh - min_soc_mwh"`.

### 7.2 Changes in `_render_table`

Add the three labels to the `max(len(...))` list that computes `label_width`, then print three
lines in the Summary block after `min capacity margin`. `simulated` is already unpacked at the
top of `_render_table`, so printing the window basis costs nothing:

```
  recharge opportunity          X MWh   [OPEN: recharge_opportunity_definition]
  span recharge mismatch        X MWh   (opportunity - recharged, window all)
  recharge capacity mismatch    X.X%    (of Y MWh available) [OPEN: recharge_capacity_denominator]
```

Render the mismatch fraction as `value * 100` with a `%` sign, matching how the same block
renders `severity_reduction` and matching the Overview RCM score bands, which are in percent
(rule 2.4). Print `-` when the value is `None`, following the `recharge_sufficiency_ratio`
precedent in the daily table.

**Hard constraint.** `_render_table` must read the new values from `report` only.
`tests/test_cli.py::test_daily_table_columns_align_across_magnitudes` calls it with
`argparse.Namespace(name=None)`, so any new `args` attribute read breaks that test.

**Do not** add a column to the Daily results table. That test asserts
`len(cells) == len(numeric_headers) + 1` against a hard-coded header list.

### 7.3 Tests in `tests/test_cli.py`

1. The JSON summary carries the four new keys.
2. Invariant: `span_recharge_mismatch_mwh == approx(recharge_opportunity_mwh - energy_charged_mwh)`.
3. Table output contains `span recharge mismatch` and
   `[OPEN: recharge_opportunity_definition]`.
4. `maximum_available_capacity_mwh == approx(0.70 * 20000)` for the shipped example at default
   fractions.
5. **Percent rendering.** Take `report = _report([])`, set
   `report["summary"]["recharge_capacity_mismatch_fraction"] = 0.05`, call
   `cli._render_table(report, argparse.Namespace(name=None), buf)`, and assert `"5.0%"` is in
   the output. This is the doctored-report pattern
   `test_daily_table_columns_align_across_magnitudes` already uses.

On `examples/synthetic_winter_stress.csv` all three new numbers are `0.0`, because the
example's wind never exceeds its net load. That is correct output, not a wiring fault. Assert
`>= 0.0` rather than a positive value on that fixture.

**Verify.**

```
uv run pytest tests/test_cli.py tests/test_metrics.py tests/test_simulator.py -q
uv run simulate --input examples/synthetic_winter_stress.csv --storage-mwh 20000 --power-mw 2000
```

---

## 8. Phase 5 — capital costs (optional, do last, safe to skip)

Skip this phase if the suite is not green at the end of Phase 4.

### 8.1 `src/owr/config.py`

Add three fields, each `float | None = None`, because every constant is `@` in the source:

```python
est_transmission_cost_per_mile_usd: float | None = None
est_storage_unit_cost_usd: float | None = None
solution_lifetime_years: float | None = None
```

`__post_init__` rejects a value below zero when the field is not `None`. Do not enforce the
Overview's "≥ 0.01 OR = 0.00" rule; that is an input rule, not an engine rule.

Extend the `Config` docstring with a block that names the open question
`capital_cost_constants`, states that no source value exists yet, and states plainly:
**no code path reads these three fields.** They park the wiring step that follows once the team
supplies values, and they surface the open question in the `config` block of every JSON report.
This mirrors `storage_physics.py`, whose docstring says "Not wired anywhere" for the same
reason. The three fields belong in `Config` and not in `cli.py` because the `Config` docstring's
own rule is "a value belongs here when an engine function or value object takes it as a
parameter", and the two new metric functions take them.

### 8.2 `src/owr/metrics.py`

```python
def estimated_capital_cost_usd(
    *,
    transmission_cost_per_mile_usd: float,
    miles: float,
    storage_unit_cost_usd: float,
    total_unit_count: float,
) -> float

def cost_per_equivalent_full_cycle_usd(
    capital_cost_usd: float,
    *,
    annual_equivalent_full_cycles: float,
    solution_lifetime_years: float,
) -> float
```

First function: `per_mile * miles + unit_cost * unit_count`. All four inputs must be
non-negative. Second function: `capital_cost / (annual_efc * lifetime_years)`; both divisor
parts must be positive, else raise `ValueError` (policy 2.6); the capital cost must be
non-negative.

Docstrings quote both source formulas per 2.9, name `capital_cost_constants`, and state that
`annual_equivalent_full_cycles` is the yearly `equivalent_full_cycles` total, which links to
the open question `cycles_per_year` already carried by `cli.py`.

### 8.3 Tests

`tests/test_metrics.py`: cost arithmetic on one worked example; negative input raises;
zero `annual_equivalent_full_cycles` raises; zero `solution_lifetime_years` raises.
`tests/test_config.py`: the three new fields default to `None`; a negative value raises;
`json.dumps(asdict(Config()))` still round-trips, which extends the existing
`test_config_json_serializes_wrap_convention` guard.

The three new fields add three `null` keys to the `config` block of the CLI JSON report. No
test enumerates the `Config` field set, so this stays additive.

---

## 9. Verification, in order

```
uv run ruff check .
uv run pytest tests/test_metrics.py -q
uv run pytest -q
uv run simulate --input examples/synthetic_winter_stress.csv \
  --storage-mwh 20000 --power-mw 2000
uv run simulate --input examples/synthetic_winter_stress.csv \
  --storage-mwh 20000 --power-mw 2000 --format json | grep recharge
```

Pass condition: 360 passed plus the new tests, 3 skipped, ruff clean. Record the measured
count in `docs/HANDOFF.md`. Do not claim a count this plan predicts.

After the suite is green, update three documents:

- `docs/HANDOFF.md`: append the open questions from section 10 to the newest
  "Open questions and decisions not yet made" block, and record what shipped.
- `docs/BOARD.md`: add a Done row in the format of the pandas row.
- `CLAUDE.md`: no change. `metrics.py` keeps its row, "Outcome metrics".

---

## 10. Open questions this work adds

Copy this list into the `metrics.py` module docstring and into `docs/HANDOFF.md`.

1. **`capacity_margin_metric_definition`.** Component 7 holds two formulas under
   "Capacity Margin Deficit Reduction": a per-hour MW deficit reduction floored at zero, and
   the legacy percentage change in net load. The Overview scores the metric in MW, which fits
   the first and not the second. Both are implemented. Which one is the metric, and is the
   percentage form retired or kept as a second metric?
2. **`recharge_opportunity_definition`.** Component 5 lists `recharge_opportunity | MWh | @`.
   The implementation reads it as surplus wind in the hour, before the state-of-charge and
   power clamps. The forecast reading gives a different metric.
3. **`recharge_capacity_denominator`.** What is `maximum_available_capacity`? The
   implementation recommends `total_mwh - min_soc_mwh`, which is the Overview's 70% Available
   Charge band. The full `total_mwh` is the alternative and differs by about 1.43 times.
4. **`fuel_offset_definition`.** The formula computes fossil generation minus clean supply,
   which reads as fossil generation remaining, while the name reads as fossil generation
   displaced. Also, the source does not say what `total_generation(t)` contains.
5. **`stress_window_effectiveness_numerator`.** Does `charge_dispatched(t)` in Component 7
   mean the charge leg or the discharge leg? The rename record in
   `FINDINGS_SOURCE_DOCS_2026-08-05.md` section 2 points at discharge, which would match the
   Overview's `capacity_dispatched(t)`. Confirm this, and the metric becomes one function.
6. **`capital_cost_constants`** (Phase 5 only). No source value exists for
   `est_transmission_cost_per_mile`, `est_storage_unit_cost` or `solution_lifetime`.

---

## 11. Risks, ranked

**R1, high. The capacity-margin decision can delete code.** If the team picks one formula, the
other function must go, not stay as a second metric. Both functions are pure and unwired, so a
deletion is a one-function change plus its tests. Nothing else depends on them.

**R2, high. `recharge_opportunity` has no definition in the source.** The CLI will print a
number built on this plan's reading. If the team means the Component 5 forecast quantity, the
printed number changes meaning from "wind not stored" to "forecast error". Mitigation: the
`[OPEN: recharge_opportunity_definition]` marker on the table line, the entry in
`open_questions`, and no propagation to the API, the database or the frames.

**R3, medium. Duplication drift.** `recharge_opportunity_mw` restates the simulator's recharge
rule in a second place. Mitigation: test 5.5 item 12 assertion B, which runs the simulator at a
scale where no clamp binds and demands per-hour equality. Assertion A is a sanity check only;
it holds by construction, because `clamp_charge` never increases a request.

**R4, medium. The source unit for `average_recharge_mismatch` is wrong.** The contract says
MW; the inputs are MWh and the mean of MWh values is MWh. The implementation returns MWh and
the docstring records the discrepancy. A reporting layer that relabels it MW would publish a
wrong unit.

**R5, medium. The fuel offset sign reads backward against its own name.** Implemented as
written. Anyone who builds a score band on top must read the docstring first.

**R6, low. NaN bypasses the guards.** `float("nan") <= 0` is `False`, so a NaN input flows
through every check. The input boundary owns this and already rejects non-finite values.

**R7, low. The shipped example prints zeros.** Its wind never exceeds its net load, so all
three new summary numbers are `0.0`. Correct output. Tests use an inline fixture with high
wind.

**R8, low. Phase 5 grows the JSON `config` block.** Three `null` keys appear. No test
enumerates the field set.

**R9, low. `_render_table` takes a stub Namespace in one test.** New render code must read
from `report` only.

---

## 12. Revision log

Adversarial review returned 2026-08-05: one blocking finding, three non-blocking, three nits.
The review confirmed the formula readings, the division-by-zero policy, the CLI trap list and
the 360/3 baseline. Dispositions:

| ID | Finding | Disposition | Sections changed |
|---|---|---|---|
| B1 | The CLI wiring contradicted the plan's own cycle definition; under `--window all` the span covers non-stress days | **Accepted, option (a).** The cycle is the simulated span. New section 5.2 states the boundary rule and both `--window` cases, and the `cycle_recharge_mismatch_mwh` docstring carries it. The summary key is `span_recharge_mismatch_mwh`, and the table line names the window basis. Per-event breakdown stays with the five-winter loop. | 5.2, 5.3, 7.1, 7.2, 7.3 |
| N1 | Section 2.4 promised percent rendering; 7.2 printed a bare fraction, off by 100 against the Overview RCM bands | **Accepted.** `_render_table` prints `value * 100` with a `%` sign; the JSON key stays a fraction. New test 7.3 item 5 pins it at 5.0%. | 2.4, 5.3, 7.2, 7.3 |
| N2 | The Stress Window Effectiveness exclusion claimed Component 5 "defines" `charge_dispatched` as charging; every description cell is `@`, and the rename record points at discharge | **Accepted.** Rationale rewritten as "field name ambiguous, and the rename record points the other way", citing findings section 2. The exclusion stands as conservative and is now open question 5. | 1, 10 |
| N3 | Policy 2.6 could be over-applied to the net-load series, which go negative in a valid hour | **Accepted.** Rule 2.6 carries an explicit exempt list of four series; 6.2 repeats it for `net_load_change_percent`; new test 6.4 item 7 uses a negative element. | 2.6, 6.2, 6.4 |
| T1 | The drift guard did not say which assertion catches which drift | **Accepted.** Item 12 splits assertion A (sanity, holds by construction) from assertion B (the real guard). R3 updated. | 5.5, 11 |
| T2 | Phase 5 `Config` fields needed a statement that nothing reads them | **Accepted.** 8.1 states that no code path consumes them and cites the `storage_physics` precedent. | 8.1 |
| T3 | `assert average_mismatch is not None` vanishes under `python -O` | **Accepted.** Replaced with an explicit `raise ValueError`, which `cmd_run` already converts to exit code 2. | 7.1 |
