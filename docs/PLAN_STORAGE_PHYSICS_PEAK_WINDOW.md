# Implementation plan — storage physics, peak-window finder, EFC metric, p90 default

Written 2026-07-28. Companion to `docs/PLAN_SIMULATOR_CLI.md`; same conventions.

Four independent work items. The governing rule for every design choice below: **if the
team answers an open question the other way, does this code change?** If yes, it is out of
scope or it is a parameter.

## Governing constraint — what stays open

| Open question | How this plan keeps it open |
|---|---|
| Peak-shaving formula | Not built. The peak-window finder *locates* a window and returns it; nothing applies a formula to it. |
| Ramp-reduction formula, 11-hour shaped window, day-to-day overlap rule | Not built. The 4+3+4 extent is stated but the overlap/clipping rule is not, so no shaped-window object exists. |
| Is 0.70 round-trip or one-way? | `storage_physics` takes `efficiency` as an argument and never reads a default. Two named converters (`one_way_from_round_trip`, `round_trip_from_one_way`) make the conversion available without picking a side. `Config.default_efficiency` stays at 1.0. |
| Which two of {diameter, head, energy} are fixed | All three inversions are implemented. Fixing any two yields the third. No sphere design constant enters `config.py`. |
| p90 threshold *value* on real data | Only the percentile *default* moves 0.95 → 0.90. No MWh threshold is hard-coded anywhere. |
| Wrap convention for the hour triplets | A `WrapConvention` StrEnum with the default in `config.py`. Flipping it is a one-value change; a third reading is one enum member plus one branch. |

Explicitly **not** in scope: flipping `default_efficiency` to 0.70; wiring `storage_physics`
into `models.StorageAsset` / `dispatch.py`; any price, capex or payback term; the shaped
ramp window; the ISO Express re-pull.

---

## Phase 1 — `src/owr/storage_physics.py` (new)

**Goal.** A pure module that derives sphere energy, power and geometry from first
principles, so "20 MWh" stops being a hard-coded number and becomes an output of whichever
two inputs the team fixes.

### Module constants

Physical constants, not design choices, so they do **not** go in `config.py` (whose
docstring states every value there is a team design choice). Cite the source inline.

```python
RHO_SEAWATER_KG_M3: float = 1025.0   # seawater density used throughout DATA_SOURCES [4]
GRAVITY_M_S2: float = 9.81
JOULES_PER_MWH: float = 3.6e9
```

### Function surface

All keyword-only past the first argument where argument order could be confused (head vs.
energy vs. volume are all bare floats). `from __future__ import annotations` at the top,
type hints throughout, no I/O, no numpy — `math` only.

```python
def sphere_internal_diameter_m(outer_diameter_m: float, wall_thickness_m: float) -> float
def sphere_internal_volume_m3(outer_diameter_m: float, wall_thickness_m: float) -> float
def sphere_outer_diameter_for_volume_m(volume_m3: float, wall_thickness_m: float) -> float

# generating (discharge) direction: E = rho * g * V * h * eta
def generating_energy_mwh(*, volume_m3: float, head_m: float, efficiency: float) -> float
def volume_for_energy_m3(*, energy_mwh: float, head_m: float, efficiency: float) -> float
def head_for_energy_m(*, energy_mwh: float, volume_m3: float, efficiency: float) -> float

# generating: P = rho * g * Q * h * eta ; pumping: P = rho * g * Q * h / eta
def generating_power_mw(*, flow_m3_s: float, head_m: float, efficiency: float) -> float
def pumping_power_mw(*, flow_m3_s: float, head_m: float, efficiency: float) -> float
def flow_for_generating_power_m3_s(*, power_mw: float, head_m: float, efficiency: float) -> float
def flow_for_pumping_power_m3_s(*, power_mw: float, head_m: float, efficiency: float) -> float

# the {diameter, head, energy} trio — fix any two, get the third
def sphere_energy_mwh(*, outer_diameter_m, wall_thickness_m, head_m, efficiency) -> float
def sphere_head_m(*, outer_diameter_m, wall_thickness_m, energy_mwh, efficiency) -> float
def sphere_outer_diameter_m(*, head_m, energy_mwh, efficiency, wall_thickness_m) -> float

# efficiency convention helpers — conversion only, no decision
def one_way_from_round_trip(round_trip_efficiency: float) -> float   # sqrt
def round_trip_from_one_way(one_way_efficiency: float) -> float      # square
```

### Documented semantics (put these in the docstrings)

- `efficiency` in the generating functions is the **one-way generating** efficiency. The
  result of `generating_energy_mwh` is energy delivered at the terminals on discharge, which
  is the convention `DATA_SOURCES.md` [4] uses to get 20 MWh and 4.5–5.0 MWh.
- `pumping_power_mw` divides by efficiency where `generating_power_mw` multiplies, so at the
  same `(Q, h, eta)` the pump draws `1/eta**2` times the turbine's output. Name that ratio in
  the docstring — it is the point `dispatch.py` will eventually need.
- `one_way_from_round_trip` / `round_trip_from_one_way` docstrings must state: **the team has
  not decided whether 0.70 is round-trip or one-way** (`HANDOFF.md` third-reply block). These
  functions convert; they do not choose. Give both numbers in the docstring —
  `sqrt(0.70) = 0.8367` each way if 0.70 is round-trip, `0.70**2 = 0.49` round-trip if 0.70
  is the one-way turbine figure.
- The trio functions take **four** inputs, not three: wall thickness and efficiency are
  always required. "Fix two of {D, h, E}" means two at a given wall thickness and efficiency.
- `sphere_outer_diameter_m` returns the **outer** diameter (internal + 2 × wall). See risk R5.

### Validation

Raise `ValueError` (matching `soc_engine` / `models` style) for: non-positive
`outer_diameter_m`, `head_m`, `energy_mwh`, `volume_m3`, `flow_m3_s`, `power_mw`; negative
`wall_thickness_m`; `2 * wall_thickness_m >= outer_diameter_m`; `efficiency` outside `(0, 1]`.

### Tests — `tests/test_storage_physics.py` (new)

Define the spec numbers as named module-level constants in the test file with a
`docs/DATA_SOURCES.md [4]` citation comment. Use `pytest.approx(..., rel=1e-3)` unless noted.

Geometry:
- `sphere_internal_volume_m3(30.0, 0.5) == approx(12770.05)`; `(30.0, 1.0) == approx(11494.04)`
- `sphere_outer_diameter_for_volume_m(sphere_internal_volume_m3(30.0, 0.75), 0.75) == approx(30.0)`

**Fraunhofer validation (the load-bearing assertions):**
- `sphere_head_m(outer_diameter_m=30.0, wall_thickness_m=0.5, energy_mwh=20.0, efficiency=0.80) == approx(700.90)`
- `sphere_head_m(outer_diameter_m=30.0, wall_thickness_m=1.0, energy_mwh=20.0, efficiency=0.80) == approx(778.71)`
- for `wall in (0.5, 0.75, 1.0)`: `600.0 <= sphere_head_m(...) <= 800.0` — the published
  StEnSea depth band, recovered from published diameter, energy and efficiency alone.

**Shallow-variant validation:**
- `sphere_energy_mwh(outer_diameter_m=30.0, wall_thickness_m=0.5, head_m=200.0, efficiency=0.70) == approx(4.9936)`
- `sphere_energy_mwh(outer_diameter_m=30.0, wall_thickness_m=1.0, head_m=200.0, efficiency=0.70) == approx(4.4946)`
- for `wall in (0.5, 0.75, 1.0)`: `4.49 <= E <= 5.00`. **Assert 4.49, not 4.5** — the 1.0 m
  wall case is 4.4946 and `>= 4.5` fails (risk R7).

Power:
- `generating_power_mw(flow_m3_s=1.02, head_m=200.0, efficiency=0.70) == approx(1.4359)` —
  Mitchell's stated flow does not give his stated 1.67 MW
- `flow_for_generating_power_m3_s(power_mw=1.67, head_m=200.0, efficiency=0.70) == approx(1.1863)`
- `generating_power_mw(flow_m3_s=1.186, head_m=200.0, efficiency=0.70) == approx(1.6696)`
- `pumping_power_mw(...) / generating_power_mw(...)` at the same `(Q, h, eta=0.70)`
  `== approx(2.0408)` i.e. `1 / 0.70**2`
- `flow_for_pumping_power_m3_s` round-trips against `pumping_power_mw`

Efficiency helpers:
- `one_way_from_round_trip(0.70) == approx(0.836660)`
- `round_trip_from_one_way(0.70) == approx(0.49)`
- `round_trip_from_one_way(one_way_from_round_trip(x)) == approx(x)` for x in `(0.35, 0.5, 0.7, 0.8, 1.0)`
- both raise `ValueError` outside `(0, 1]`

Inversion round-trips (this is what "fixing any two yields the third" means, so test it
directly): for a few `(D, wall, h, eta)` sets,
- `sphere_head_m(energy_mwh=sphere_energy_mwh(...), ...) == approx(h)`
- `sphere_outer_diameter_m(energy_mwh=sphere_energy_mwh(...), ...) == approx(D)`

The spec inconsistency, pinned as a test so it cannot silently disappear:
- `sphere_outer_diameter_m(head_m=200.0, energy_mwh=20.0, efficiency=0.70, wall_thickness_m=0.5)`
  `== approx(47.05)`, and its internal diameter `== approx(46.05)`. Comment that
  `DATA_SOURCES.md` [4]'s "~46 m" is the **internal** figure, and that 30 m is what the team
  actually specified — the two cannot both hold.

Errors: one `pytest.raises(ValueError)` case per validation rule listed above.

### Verify

`uv run pytest tests/test_storage_physics.py -q` and `uv run ruff check .`.

### Not wired anywhere

No caller uses this module in this batch. `StorageAsset.total_mwh` keeps taking MWh
directly. Deriving it from geometry is a follow-up gated on the team fixing two of
{D, h, E} and on the round-trip-vs-one-way answer. Say so in the module docstring.

---

## Phase 2 — 3-hour rolling peak-window finder

**Goal.** Given a day's 24 hourly loads, return the highest-summing rolling window of
`window_hours` consecutive hours. Identification only.

### `src/owr/models.py` — additions

`WrapConvention` and `PeakWindow` are domain vocabulary, so they belong beside
`StressWindow` (same split as `StressWindow` in `models.py` / `find_stress_windows` in
`stress_finder.py`). `models.py` imports nothing from `owr`, so `config.py` importing from
it is acyclic.

```python
class WrapConvention(StrEnum):
    """Which hour triplets a day gets. OPEN team question (peak_window_wrap):
    HANDOFF.md, Mitchell 2026-07-28 23:12. Mitchell's enumeration ends at
    (22,23,00); whether that 00 is the next day's or the same day's is unconfirmed.
    """
    STOP_AT_MIDNIGHT = "stop_at_midnight"    # windows must fit inside the day: 22 triplets
    WRAP_TO_NEXT_DAY = "wrap_to_next_day"    # last window is (22,23,next-day-00): 23 triplets

    @property
    def lookahead_hours(self) -> int: ...    # 0 / 1
```

`enum.StrEnum` specifically, **not** `Enum` — `cli.py` does `"config": asdict(cfg)` and then
`json.dumps`, and a plain `Enum` member is not JSON-serializable (risk R2). `lookahead_hours`
is 1 for `WRAP_TO_NEXT_DAY` at any `window_hours`, matching Mitchell's enumeration, which
wraps by exactly one hour. Document that a fully continuous reading (lookahead
`window_hours - 1`) is reachable through the primitive without touching the enum.

```python
@dataclass(frozen=True)
class PeakWindow:
    start_hour: int                  # 0..23, index into the day's own 24 hours
    clock_hours: tuple[int, ...]     # (start_hour + k) % 24 for each hour, e.g. (22, 23, 0)
    load_mw: tuple[float, ...]       # the loads summed, in order
    wrapped: bool                    # True when the window crosses into the next day
    candidates_considered: int       # number of start positions evaluated

    @property
    def load_mwh(self) -> float:     # sum(load_mw); mirrors DayProfile.load_mwh
```

`load_mwh` is a property, not a field, so it cannot drift from `load_mw` (same pattern as
`DayProfile.load_mwh`). `__post_init__` validates `0 <= start_hour <= 23`,
`len(clock_hours) == len(load_mw) >= 1`, `candidates_considered >= 1`.

Optionally add `PeakWindow` and `WrapConvention` to `owr/__init__.py`'s imports and
`__all__`, for parity with `StressWindow`.

### `src/owr/peak_window.py` (new)

```python
def find_peak_window(
    hourly_load_mw: Sequence[float],
    *,
    window_hours: int,
    next_hours: Sequence[float] = (),
) -> PeakWindow
```

The primitive. Scans `series = list(hourly_load_mw) + list(next_hours)` over every start
index `s` in `0 <= s <= 23` with `s + window_hours <= len(series)`, and returns the
max-summing window. **Ties break to the earliest start index** — document it and test it;
`max(..., key=...)` over an ordered enumeration already does this, but the guarantee must be
stated because flat days are all ties.

Validation: `len(hourly_load_mw) != HOURS_PER_DAY` → `ValueError` (matches `DayProfile` and
`allocate_discharge`); `window_hours < 1` or `window_hours > HOURS_PER_DAY` → `ValueError`;
`len(next_hours) > HOURS_PER_DAY` → `ValueError`. Negative loads are allowed — the max is
still well defined and rejecting them is a modeling opinion.

```python
def find_peak_window_for_day(
    day: DayProfile,
    next_day: DayProfile | None = None,
    *,
    window_hours: int,
    wrap: WrapConvention,
) -> PeakWindow
```

Resolves `next_hours` from `next_day` per `wrap.lookahead_hours`, then delegates.
`next_hours` is empty when `wrap is STOP_AT_MIDNIGHT`, when `next_day is None`, or when
`next_day.date != day.date + timedelta(days=1)` (a non-adjacent day is not the physical
successor). The last day of a series therefore reports `candidates_considered == 22` instead
of 23 — that is missing data, not a convention, and it is visible in the returned value
rather than silently swallowed. Document it; test it.

```python
def find_peak_windows_over_days(
    days: Sequence[DayProfile],
    *,
    window_hours: int,
    wrap: WrapConvention,
) -> list[tuple[date, PeakWindow]]
```

Maps `find_peak_window_for_day` over the series, passing `days[i + 1]` as `next_day` for
every day but the last.

`window_hours` and `wrap` are **required keyword-only** on both day-level functions. No call
site may inherit a wrap convention silently while the question is open; `find_stress_windows`
sets the precedent of taking its parameters with no defaults. The defaults live in `Config`.

### `src/owr/config.py` — two new fields

```python
default_peak_window_hours: int = 3
default_peak_window_wrap: WrapConvention = WrapConvention.WRAP_TO_NEXT_DAY
```

Docstring entries, in the existing "attribute → open question" style:

- `default_peak_window_hours` — **settled** 2026-07-28: each day in a stress window gets a
  peak load defined as a 3-hour period found by rolling window over hour triplets. Surfaced
  as config because `find_peak_window` takes it as a parameter, not because it is in doubt.
- `default_peak_window_wrap` — OPEN team question (`peak_window_wrap`). Mitchell's
  enumeration ends at (22,23,00). `WRAP_TO_NEXT_DAY` is the physically continuous reading and
  the one `HANDOFF.md` says to assume; `STOP_AT_MIDNIGHT` is the 22-triplets alternative. On
  a multi-day event the choice changes which hours get shaved at the day boundary. Flipping
  the default is a one-value change.

`__post_init__`: `1 <= default_peak_window_hours <= HOURS_PER_DAY` else `ValueError`.
Importing `HOURS_PER_DAY` and `WrapConvention` from `owr.models` into `config.py` is the only
new import edge; it is acyclic.

### Tests — `tests/test_peak_window.py` (new)

Locating:
- clear single peak at hours 17–19 → `start_hour == 17`, `clock_hours == (17, 18, 19)`,
  `load_mwh == sum of those three`, `wrapped is False`
- flat 24-hour day → `start_hour == 0` (earliest-start tie-break)
- two tied triplets → earliest wins

Conventions, on one constructed day (hours 22 and 23 high, next day's hour 0 higher still):
- `STOP_AT_MIDNIGHT` → `candidates_considered == 22`, `wrapped is False`, winner is `(21,22,23)`
- `WRAP_TO_NEXT_DAY` with `next_day` → `candidates_considered == 23`, `wrapped is True`,
  `start_hour == 22`, `clock_hours == (22, 23, 0)`
- `WRAP_TO_NEXT_DAY` with `next_day=None` → `candidates_considered == 22`, `wrapped is False`
- `WRAP_TO_NEXT_DAY` with a non-adjacent `next_day` → same as `None`

Window size:
- `window_hours=1` → the single max hour; `window_hours=24` → the whole day,
  `candidates_considered == 1`
- `window_hours=0`, `-1`, `25` → `ValueError`
- 23-value or 25-value `hourly_load_mw` → `ValueError`

Against the shipped example (`examples/synthetic_winter_stress.csv`, read via
`read_day_profiles` exactly as `tests/test_cli.py` does) — these pin that the convention is
observable, not cosmetic. Expected values, derived from the generator's construction:

| Day | date | `STOP_AT_MIDNIGHT` `start_hour` | `WRAP_TO_NEXT_DAY` `start_hour` |
|---|---|---|---|
| 0 | 2026-01-06 | 0 (flat, all tie) | 22, `wrapped=True` |
| 1 | 2026-01-07 | 0 | 22, `wrapped=True` |
| 2 | 2026-01-08 | 0 | 22, `wrapped=True` |
| 3 | 2026-01-09 | 16 | 16 |
| 4 | 2026-01-10 | 17 | 17 |
| 5 | 2026-01-11 | 16 | 16 (no successor: `candidates_considered == 22`) |

Mild days rise day to day (7500 → 8000 → 8500 → 9000), so under wrap the
(22, 23, next-00) triplet strictly beats every flat triplet. Cold days peak at hour 18 (day 4
at hour 19) against a 9000 MW flat, so the winner is the earliest triplet containing the
peak. `find_peak_windows_over_days` must return 6 entries with dates in input order.

Config, in `tests/test_config.py`:
- `Config().default_peak_window_hours == 3`
- `Config().default_peak_window_wrap == WrapConvention.WRAP_TO_NEXT_DAY`
- `Config(default_peak_window_hours=0)` and `(=25)` raise `ValueError`
- **JSON guard**: `json.dumps(asdict(Config()))` succeeds and round-trips to
  `["default_peak_window_wrap"] == "wrap_to_next_day"`. This is the guard on `cli.py`'s
  `"config": asdict(cfg)` path (risk R2).

### Verify

`uv run pytest -q`, `uv run ruff check .`, and
`uv run simulate --input examples/synthetic_winter_stress.csv --storage-mwh 20000 --power-mw 2000 --format json`
to confirm the JSON report still serializes with the new Config field.

---

## Phase 3 — equivalent full cycles

**Goal.** Land the settled EFC definition in `metrics.py` and make `cli.py` use it instead
of its own second definition.

### `src/owr/metrics.py` — one function

```python
def equivalent_full_cycles(discharged_mwh: float, rated_energy_mwh: float) -> float:
    """Total energy discharged over a period divided by the asset's rated energy
    capacity. Settled 2026-07-28 (HANDOFF.md decision 5): the metric that survives
    partial cycles, and what degradation and warranty terms are quoted against. A
    half-depth discharge counts 0.5; one event containing a mid-event recharge can
    count more than 1.
    """
```

`ValueError` when `rated_energy_mwh <= 0` (mirrors `severity_reduction`'s guard) or when
`discharged_mwh < 0`. Docstring must note that `discharged_mwh` is energy **delivered**, not
energy drawn from the tank — the two differ by the efficiency term.

### `src/owr/cli.py` — replace the local formula

`cli.py:442` currently computes `(energy_discharged / asset.efficiency) / asset.total_mwh`,
which is energy *drawn from the tank* over rated capacity. That is a second, conflicting
definition. Replace with
`equivalent_full_cycles(energy_discharged, asset.total_mwh)` imported from `owr.metrics`, and
change the table label at `cli.py:753` from `(energy drawn / rated capacity)` to
`(energy discharged / rated capacity)`. No test asserts either string or the numeric value
today, and the two definitions coincide at the shipped `efficiency = 1.0`, so the suite will
not catch the change on its own — hence the test below.

`cli.py` importing from `owr.metrics` is fine; the local `_severity_reduction` duplication
exists to avoid importing from the **API** layer, not from `metrics`.

### Tests

`tests/test_metrics.py`:
- `equivalent_full_cycles(1000.0, 500.0) == 2.0`
- `equivalent_full_cycles(250.0, 1000.0) == approx(0.25)`
- `equivalent_full_cycles(0.0, 1000.0) == 0.0`
- `pytest.raises(ValueError)` for `rated_energy_mwh` of `0.0` and `-1.0`, and for negative
  `discharged_mwh`

`tests/test_cli.py`:
- for the default run, `summary["equivalent_full_cycles"] == approx(summary["energy_discharged_mwh"] / asset_total_mwh)`
- the same identity holds for a run with `--efficiency 0.7`, which is what proves the
  `/ efficiency` term is gone

### Doc pointer

`docs/PLAN_SIMULATOR_CLI.md` line 425 states the old formula. Per the repo's convention of
dated pointers rather than rewrites, append one dated line to that table cell:
`Superseded 2026-07-28 — see HANDOFF.md decision 5; EFC is energy discharged / rated capacity.`

---

## Phase 4 — `default_severity_percentile` 0.95 → 0.90

Decision 2 is resolved: the implemented rule already matches Mitchell's, and the only code
delta is the default plus the retired "competing 12-hour rule" language.

### Changes

1. `src/owr/config.py:75` — `default_severity_percentile: float = 0.90`.
2. `src/owr/config.py:53-61` — rewrite the docstring entry. Drop "three artifacts use three
   thresholds" and the whole "a competing rule counts hours within the day (12+ hours above
   threshold = stress day, 2+ consecutive = event)" sentence. Replacement content: the rule is
   **settled** 2026-07-28 — daily total demand at or above the historical 90th percentile,
   with a run of `min_stress_window_days` consecutive such days forming an event; Report B's
   12-hour rule is retired. What remains open is the **threshold value on real data**: both
   published numbers (3,504 and 16,750 MWh) are hourly-basis and do not carry over to a
   daily-basis rule, so a fresh p90 must be computed on daily sums.
3. **`src/owr/api/schemas.py:33`** — `severity_percentile: float = Field(default=0.90, ...)`.
   Mandatory, not optional: `tests/test_config.py::test_config_defaults_match_scenario_create_defaults`
   is a drift guard asserting the two are equal, and it fails if only `config.py` moves.
4. `src/owr/cli.py:58-67` — `_OPEN_QUESTIONS_STATIC["stress_event_definition"]["note"]`
   carries the same retired 12-hour language. Rewrite it to match the new config docstring.
   **Keep the id, the flags, the `handoff_ref` and the `[OPEN: stress_event_definition]`
   marker** — `tests/test_cli.py:110` asserts the marker, and the question is still genuinely
   open on the threshold value, so removing it would be both scope creep and wrong.
5. `db/migrations/001_init.sql:106` — the trailing comment `-- e.g. 0.95` → `-- e.g. 0.90`.
   Comment only, no schema change, and per `HANDOFF.md` the migrations have never been run
   against a live DB.
6. `docs/PLAN_SIMULATOR_CLI.md` lines 281 and 361 quote the 0.95 default and the retired
   competing rule. Dated pointer, not a rewrite:
   `Superseded 2026-07-28 — default is 0.90 and the 12-hour rule is retired; see HANDOFF.md decision 2.`

### Test changes

- `tests/test_config.py:15` is the only assertion that hard-codes `0.95`. Change to `0.90`.
  Every other reference in `tests/` and `examples/` reads `DEFAULT_CONFIG.default_severity_percentile`.
- Add to `tests/test_config.py`, in the `test_reserve_defaults.py` three-surface style, a test
  that pins 0.90 on both surfaces with a docstring naming the 2026-07-28 decision, so it
  cannot drift back.

### Regression to check by running, not by reading

`examples/make_synthetic_winter_stress.py` asserts at generation time that the default
percentile yields exactly one 3-day window. Daily totals are
`[180000, 192000, 204000, 216000, 216000, 216000]`; linear-interpolated p90 over six values
is `216000`, the same threshold p95 gives, so the invariant should still hold and the CSV
should be byte-identical. **Prove it:**

```
uv run python examples/make_synthetic_winter_stress.py
git diff --exit-code examples/synthetic_winter_stress.csv
```

Both must succeed. If the CSV changes, stop — the demo command in `README.md` and
`HANDOFF.md` depends on the tie holding.

### Verify

`uv run pytest -q` — expect 152 passed + the new tests, 3 skipped, and no failures in
`test_cli.py`, `test_api.py` or `test_config.py`. `uv run ruff check .`.

---

## Phase 5 — record the pause point

Update `docs/HANDOFF.md`:

- Decision 2: note the `0.95 → 0.90` change and the schema/CLI/migration surfaces it touched.
- Decision 5: note that EFC now has one implementation, in `metrics.py`, and that `cli.py`'s
  divide-by-efficiency variant is retired.
- The peak-window block: note that identification is built and formula application is not,
  and that the wrap convention is a labeled `Config` default rather than a decision.
- Add `storage_physics.py` and `peak_window.py` to the "Where everything is" table.
- Update the verified test counts and the "What is in flight" section.

Update `docs/DATA_SOURCES.md` [4] with a dated line: the model is now executable in
`src/owr/storage_physics.py` and the 701–779 m / 4.5–5.0 MWh figures are pinned as tests. Fix
the "~46 m outer diameter" line — 46.05 m is the **internal** diameter; outer is 47.05 m at a
0.5 m wall (risk R5).

No commits or pushes unless asked.

---

## Risks

**R1 — The EFC change is invisible to the current suite.** `cli.py`'s formula and the new
`metrics.py` one agree exactly at the shipped `efficiency = 1.0`, and no existing test runs
the CLI at any other efficiency or asserts the EFC number. Without the Phase 3
`--efficiency 0.7` test the change is unverified. *Mitigation: that test is required, not
optional.* Downstream consequence to state in the commit message: once decision 1 flips
`default_efficiency` to 0.70, reported EFC drops by a factor of 0.70 versus today's formula.

**R2 — `cli.py` serializes the whole Config.** `"config": asdict(cfg)` followed by
`json.dumps` means any non-JSON-serializable `Config` field breaks `--format json` at
runtime. `StrEnum` serializes as its string value; a plain `Enum` raises `TypeError`.
*Mitigation: `StrEnum` plus the explicit `json.dumps(asdict(Config()))` test.*

**R3 — The percentile default lives on three surfaces.** `Config`, `ScenarioCreate` and the
`test_config.py` drift guard. Changing one of the first two alone fails the guard.
*Mitigation: Phase 4 items 1 and 3 are a single unit of work.*

**R4 — The shipped example's stress-window invariant.** Analytically the p90 and p95
thresholds coincide at 216,000 MWh on this six-day series, so nothing should move — but the
generator asserts the invariant at write time and the flagship demo depends on it. *Mitigation:
run the generator and `git diff --exit-code` the CSV.*

**R5 — `DATA_SOURCES.md` [4] mislabels a diameter.** The "~46 m" derived for 20 MWh at
200 m / 0.70 is the **internal** diameter (46.054 m); the outer diameter is 47.05 m at a
0.5 m wall, 48.05 m at 1.0 m. A test asserting 46 m as an outer diameter would encode the
doc's error. *Mitigation: assert 47.05 outer / 46.05 internal and correct the doc.*

**R6 — `HANDOFF.md`'s "15–21 MWh at 600–800 m" is wall-dependent.** The model gives
15.41 MWh (1.0 m wall, 600 m) to 22.83 MWh (0.5 m wall, 800 m). Do not assert that band. The
`DATA_SOURCES.md` [4] claim — 20 MWh lands at 701–779 m for any wall in 0.5–1.0 m — is the
one that holds exactly and is the one to test.

**R7 — The "4.5–5.0 MWh" band is rounded.** The 1.0 m wall case is 4.4946 MWh, so
`assert E >= 4.5` fails. Assert `4.49`.

**R8 — Peak-window results depend on the open convention.** Under `WRAP_TO_NEXT_DAY` the
example's three mild days all peak at `start_hour = 22` rather than 0. If the team picks
`STOP_AT_MIDNIGHT` those flip. Nothing consumes peak windows yet, so the blast radius is the
tests in Phase 2, which assert both conventions side by side and therefore document rather
than assume. *Residual risk: any future consumer must take the convention as a parameter.*

**R9 — The literal reading of "(22,23,00)" is not implemented.** Mitchell's text is
circular-within-one-day; `HANDOFF.md` rejects that as non-physical and frames the live
options as the two implemented here. If the team confirms the literal circular reading, it is
one enum member and one branch in `find_peak_window_for_day`. Stated so nobody re-derives it.

**R10 — The last day of a series gets 22 candidates under wrap.** Missing successor data, not
a convention. It is reported in `candidates_considered` and tested, but a caller that assumes
23 candidates per day would be wrong on the final day of every window.

**R11 — `storage_physics` has no caller.** A pure module with no consumer can drift out of
sync with whatever eventually consumes it. Accepted deliberately: wiring it into
`StorageAsset` requires the team to fix two of {D, h, E} and to answer round-trip-vs-one-way,
and building that wiring now is exactly the rewrite this batch exists to avoid.

## Assumptions

- **Efficiency semantics.** `E = rho*g*V*h*eta` is read as delivered-at-terminals energy with
  a one-way generating efficiency, because that is the convention under which
  `DATA_SOURCES.md` [4] recovers both 20 MWh and 4.5–5.0 MWh. If the team instead means gross
  hydraulic potential, the argument name changes and the numbers do not.
- **Wall thickness is an independent input**, not one of the two fixed quantities. The
  trio-of-three framing in `HANDOFF.md` is really a trio at a given wall thickness and
  efficiency.
- **`WRAP_TO_NEXT_DAY` wraps by exactly one hour** at any window size, matching Mitchell's
  enumeration ending at (22,23,00). A fully continuous scan needs `window_hours - 1`
  look-ahead hours and is reachable through `find_peak_window(..., next_hours=...)`.
- **Ties break to the earliest start hour.** Not specified by anyone; chosen because it is
  deterministic and because flat days are entirely ties. Documented in the docstring and
  pinned by a test so it can be changed deliberately.
- **`stress_event_definition` stays flagged `[OPEN]` in the CLI.** The rule is settled; the
  p90 threshold value on real data is not, and that is what the flag now points at.
