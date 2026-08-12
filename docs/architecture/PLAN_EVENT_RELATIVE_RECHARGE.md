# Implementation plan — event-relative wind routing and recharge

Written 2026-08-10. Revised 2026-08-10 after adversarial review; see Section 17 for the
revision log. Requirements source: `docs/architecture/event_relative_recharge.md`.
Baseline to hold: **738 passed, 4 skipped** (measured 2026-08-10, `uv run pytest`), ruff clean.

This plan answers Section 25 of the requirements document. Section 12 below lists every
deviation from the document's assumptions, with the repository evidence for each.

---

## 1. The architecture in one paragraph

A new value object, `OperatingSchedule`, classifies every hour of every day as one of six
`HourState` values. One module builds it (`src/owr/schedule.py`) from two existing sources:
`stress_finder`'s detected windows and `peak_window`'s rolling-window search. Four consumers
read it and none of them re-derives it: `simulator` (which hours charge), `recharge` (the
wind-to-storage rule, shared with `initial_soc` and with the budget forecast), `dispatch`
(which hours discharge), and `metrics` (which hours use the surplus-wind formula). The old
surplus-wind rule is deleted from all three places it lives today.

```
stress_finder ─┐
               ├─> schedule.build_schedule ─> OperatingSchedule ─┬─> simulator
peak_window ───┘                                                 ├─> recharge ─> initial_soc
                                                                 ├─> dispatch
                                                                 └─> metrics
```

**One stored fact per day.** A `DaySchedule` stores the day mode, the `PeakWindow` the searcher
returned, and the ramp length. The dispatch block and all 24 hour states are **derived**
properties of those three values. No two fields can disagree, because no hour classification is
stored twice.

---

## 2. What the repository actually does today

Read these facts before you judge the design. Each one is verified against source.

1. **`peak_window.py` is orphaned.** No module outside its own test file reads
   `Config.default_peak_window_hours` or `Config.default_peak_window_wrap` (verified by grep
   over `src/` and `tests/`). Section 8 of the requirements is correct: the searcher exists
   and nothing connects it to the simulator.
2. **`simulate()` cannot see events.** Its signature is
   `simulate(asset, window_days, starting_soc, available_capacity_mw, config, peak_weight,
   smooth_weight)`. Both callers (`cli._run`, `api.create_run`) detect stress windows *before*
   the call and never pass them in. The simulator therefore treats every day of its span as
   identical.
3. **Three surplus-wind rules exist, in two different forms.**
   - `simulator.simulate` hour loop: `max(0.0, wind[h] - max(0.0, load[h] - discharge))`.
   - `simulator._surplus_wind_recharge_mwh`: `max(0.0, wind[h] - max(0.0, load[h]))` — no
     discharge term, despite a docstring that claims it matches `initial_soc`.
   - `initial_soc.charge_from_wind`: `max(0.0, wind[hour] - max(0.0, load[hour]))`.
   `metrics.recharge_opportunity_mw` restates the first form as documented duplication.
4. **`find_peak_window` matches Section 9 exactly.** Candidates are
   `[s for s in range(24) if s + window_hours <= len(series)]`, where `series` is the day plus
   `wrap.lookahead_hours` hours of the next day. `STOP_AT_MIDNIGHT` gives `lookahead_hours == 0`,
   so `len(series) == 24`, starts run 0..21, the count is 22, the last triplet is (21, 22, 23)
   and `wrapped` is always `False`. No assumption needed.
5. **Events are whole days.** `stress_finder` emits `StressWindow(start, end, days)` on a daily
   rule, and `StressWindow.last_hour_index` is `24 * days - 1`. An event never ends inside a
   day. Section 11's "event ends during ramp-down" cannot arise from event detection; it can
   only arise from the day boundary. Section 12 (D3) below states how this plan resolves it.
6. **`dispatch.allocate_discharge` spreads energy over all 24 hours** from two load-derived
   signals (above-mean load, positive hour-to-hour rise). It has no concept of a peak window.
7. **A new field on `HourlyResult` costs a database migration.** `api/pg_store._load_result`
   rebuilds `SimulationResult` from `app.run_result_hourly` column by column, so any new field
   reads back as its default. `metrics.py` already carries this warning.
8. **Negative wind reaches the engine today and is floored, not rejected.**
   `scenario_input._parse_finite_float` rejects only non-finite values, and
   `api.schemas.DayProfileIn.hourly_wind_mw` carries no `ge=0`. Both surplus expressions floor a
   negative value at zero. `metrics.recharge_opportunity_mw` is the only function that raises on
   it. See D13.

---

## 3. New and changed files

| File | Action |
|---|---|
| `src/owr/models.py` | Add `DayMode`, `HourState`, `DispatchWindow`, `DaySchedule`, `OperatingSchedule` |
| `src/owr/schedule.py` | **New.** Decides the day mode and runs the peak search. The only place the classification rules live |
| `src/owr/recharge.py` | **New.** The wind-to-storage rule, shared by simulator, `initial_soc` and the budget forecast |
| `src/owr/config.py` | Flip `default_peak_window_wrap`; add `default_ramp_hours` |
| `src/owr/stress_finder.py` | Add `find_stress_windows_for_config` (removes a triplicated call) |
| `src/owr/dispatch.py` | Rework `allocate_discharge` onto `DispatchWindow`; delete both signal helpers |
| `src/owr/initial_soc.py` | Delegate to `recharge`; delete the surplus rule |
| `src/owr/simulator.py` | Consume the schedule; delete `_surplus_wind_recharge_mwh` and the hour-loop surplus rule |
| `src/owr/metrics.py` | `recharge_opportunity_mw` takes the per-hour state |
| `src/owr/cli.py` | Build the schedule, pass it on, report it, restate two open questions |
| `src/owr/api/app.py` | Build a scenario `Config`, build the schedule, pass it on |
| `src/owr/sweep.py` | Build the schedule once, pass it to every size |
| `src/owr/budget.py` | Docstring only. See D11 |
| `src/owr/api/schemas.py` | No change. See D10 and Section 16 |
| `src/owr/scenario_input.py` | No change. It parses input and holds no operating state |

New test modules: `tests/test_schedule.py`, `tests/test_recharge.py`.

---

## 4. Phase 1 — domain types in `models.py`

`models.py` is the lowest layer and takes no intra-package import. It already holds `PeakWindow`
next to `peak_window.py`'s searcher, and `StressWindow` next to `stress_finder.py`'s detector.
The schedule types follow the same split: value objects here, construction in `schedule.py`.

### 4.1 The two enumerations

```python
class DayMode(StrEnum):
    NON_EVENT = "non_event"
    PRE_CHARGE = "pre_charge"
    ACTIVE_EVENT = "active_event"


class HourState(StrEnum):
    NON_EVENT = "non_event"
    PRE_CHARGE = "pre_charge"
    ACTIVE_OFF_PEAK = "active_off_peak"
    ACTIVE_RAMP_UP = "active_ramp_up"
    ACTIVE_PEAK = "active_peak"
    ACTIVE_RAMP_DOWN = "active_ramp_down"

    @property
    def day_mode(self) -> DayMode: ...
    @property
    def charges_from_wind(self) -> bool: ...   # PRE_CHARGE, ACTIVE_OFF_PEAK
    @property
    def is_dispatch_hour(self) -> bool: ...    # ACTIVE_RAMP_UP, ACTIVE_PEAK, ACTIVE_RAMP_DOWN
```

Use `StrEnum` for both, for the reason `WrapConvention` gives: `cli.py` does
`json.dumps(asdict(cfg))` and writes report dictionaries, and a plain `Enum` member is not
JSON-serializable.

One flat `HourState` replaces a (day mode, hour role) pair on purpose. A pair permits the
invalid combination `(NON_EVENT, ACTIVE_PEAK)`; the flat enum cannot represent it.

### 4.2 `DispatchWindow` — two stored fields, the rest derived

```python
@dataclass(frozen=True)
class DispatchWindow:
    """The planned ramp-up -> peak -> ramp-down block for one active-event day.

    Slots are day-local hour indices. A slot may be negative or 24 and above: those
    slots are planned but do not exist in the day, and nothing is delivered in them.
    """

    peak_slots: tuple[int, ...]   # consecutive ascending; the last slot may exceed 23
    ramp_hours: int

    @classmethod
    def around(cls, peak_window: PeakWindow, ramp_hours: int) -> DispatchWindow:
        start = peak_window.start_hour
        return cls(
            peak_slots=tuple(range(start, start + len(peak_window.load_mw))),
            ramp_hours=ramp_hours,
        )

    @property
    def ramp_up_slots(self) -> tuple[int, ...]: ...      # range(peak_slots[0] - ramp_hours, peak_slots[0])
    @property
    def ramp_down_slots(self) -> tuple[int, ...]: ...    # range(peak_slots[-1] + 1, peak_slots[-1] + 1 + ramp_hours)
    @property
    def planned_slot_count(self) -> int: ...             # len(peak_slots) + 2 * ramp_hours
    @property
    def peak_hours(self) -> tuple[int, ...]: ...         # peak_slots inside 0..23
    @property
    def ramp_up_hours(self) -> tuple[int, ...]: ...
    @property
    def ramp_down_hours(self) -> tuple[int, ...]: ...
    @property
    def dispatch_hours(self) -> tuple[int, ...]: ...     # all in-day slots, ascending
```

Storing only `peak_slots` and `ramp_hours` makes ramp adjacency structural. There is no
`ramp_up_slots` constructor argument to contradict `peak_slots`, so the previous plan's
adjacency checks are gone: the invalid state cannot be built.

`__post_init__` raises `ValueError` when `peak_slots` is empty, when it is not a run of
consecutive ascending integers, when no peak slot lies in 0..23, or when `ramp_hours < 0`.

Use `peak_window.start_hour` and `len(peak_window.load_mw)`, never `peak_window.clock_hours`.
Under `WRAP_TO_NEXT_DAY` the clock hours wrap back to 0 while the slots keep counting past 23,
and the slot form is what the truncation rule needs.

### 4.3 `DaySchedule` — three stored fields, `hours` and the block derived

```python
@dataclass(frozen=True)
class DaySchedule:
    date: date
    mode: DayMode
    peak_window: PeakWindow | None   # not None if and only if mode is ACTIVE_EVENT
    ramp_hours: int                  # must be 0 when peak_window is None

    @cached_property
    def dispatch_window(self) -> DispatchWindow | None: ...
    @cached_property
    def hours(self) -> tuple[HourState, ...]: ...   # exactly 24

    def charges_from_wind(self, hour: int) -> bool: ...
    def is_dispatch_hour(self, hour: int) -> bool: ...
```

`dispatch_window` returns `None` when `peak_window is None`, else
`DispatchWindow.around(self.peak_window, self.ramp_hours)`.

`hours` returns 24 `HourState` values: `NON_EVENT` or `PRE_CHARGE` throughout on those days;
on an active day, `ACTIVE_RAMP_UP`, `ACTIVE_PEAK` and `ACTIVE_RAMP_DOWN` for the in-day slots of
each group, and `ACTIVE_OFF_PEAK` for every other hour.

**Both are `functools.cached_property`, not constructor fields.** This is the single most
important structural decision in the plan. The hour classification and the block are the same
fact; storing both invites a hand-built `DaySchedule` or a future refactor to desync them, and a
desync would produce an hour that both charges and discharges — the exact bug class this feature
exists to remove. A derived property forecloses it. A redundant cross-check would only relocate
the risk to whoever forgets to run the check.

`functools.cached_property` works on a frozen dataclass: it writes through `instance.__dict__`
directly and never calls `__setattr__`, and no dataclass in this repository sets `slots=True`.
If the implementer hits trouble with it, the fallback with identical guarantees is a
`field(init=False, repr=False, compare=False)` value computed once in `__post_init__` through
`object.__setattr__`. Do **not** fall back to a plain constructor argument.

Cost: each `DaySchedule` object computes `hours` once. `simulator` and `recharge` share the same
objects, sliced from one `OperatingSchedule`, so the whole run computes each day's states once.

`__post_init__` raises `ValueError` when `(peak_window is None) == (mode is DayMode.ACTIVE_EVENT)`,
when `ramp_hours < 0`, or when `peak_window is None and ramp_hours != 0`. The last rule removes
an ignored field: a non-active day carries no ramp length.

### 4.4 `OperatingSchedule`

```python
@dataclass(frozen=True)
class OperatingSchedule:
    days: tuple[DaySchedule, ...]

    def for_date(self, day: date) -> DaySchedule: ...
    def slice_for(self, dates: Sequence[date]) -> tuple[DaySchedule, ...]: ...
```

`__post_init__` raises `ValueError` when the dates are not strictly ascending. `slice_for`
raises `ValueError` naming the first missing date. It takes dates, not `DayProfile` objects, so
`models` needs no new protocol and callers stay explicit.

**Verify:** `tests/test_models.py` gains a case for each `__post_init__` rejection, each
`HourState` predicate, and each derived tuple. Add one structural guard:
`{f.name for f in dataclasses.fields(DaySchedule)}` must not contain `hours` or
`dispatch_window`, and the same set for `DispatchWindow` must not contain `ramp_up_slots` or
`ramp_down_slots`. That guard is what stops a later change from re-storing a derived fact.

---

## 5. Phase 2 — `src/owr/config.py`

Two changes.

```python
default_peak_window_wrap: WrapConvention = WrapConvention.STOP_AT_MIDNIGHT
default_ramp_hours: int = 1
```

Validation: `if not 0 <= self.default_ramp_hours <= HOURS_PER_DAY: raise ValueError(...)`.

Docstring entry for `default_ramp_hours`: the ramp-up and ramp-down block length in hours on
each side of the peak window. **OPEN team question (`ramp_duration`)**: no source names a
value. 1 hour is the smallest value that makes the ramp-up → peak → ramp-down sandwich real,
and it gives a 5-hour dispatch block at the settled 3-hour peak window. Mark it `[TWEAK]`.

Rewrite the `default_peak_window_wrap` docstring entry: the default is now `STOP_AT_MIDNIGHT`,
per requirements Section 9, so a dispatch block never crosses midnight. Keep the open question
open. **Add the consequence a future flipper needs to see:** under `WRAP_TO_NEXT_DAY` a day
whose highest triplet wraps gets peak slots such as (22, 23, 24); slot 24 does not exist in the
day, so that share of the peak pool is not delivered and is not moved to another hour. See R7
and D14.

No CLI flag for `default_ramp_hours`. This follows the nearest precedent:
`default_peak_window_hours` and `default_peak_window_wrap` have no flags either. The CLI JSON
report already echoes every `Config` field through `asdict(cfg)`, so the value is visible in
output. Requirements Section 18 forbids configuration added only for configurability.

**Verify:** update `tests/test_config.py` lines 106-123 (default value and the JSON round trip
now read `stop_at_midnight`) and add range tests for `default_ramp_hours`.

---

## 6. Phase 3 — `src/owr/schedule.py`

The only module that decides what day a day is. It no longer builds hour tuples or blocks:
Section 4.3 derives both.

```python
def build_schedule(
    days: Sequence[DayProfile],
    *,
    stress_windows: Sequence[StressWindow],
    config: Config,
) -> OperatingSchedule


def detect_and_build_schedule(
    days: Sequence[DayProfile], *, config: Config
) -> OperatingSchedule
```

`build_schedule` algorithm, per day `i`:

1. Filter once: `qualifying = [w for w in stress_windows if w.days >= config.default_min_stress_window_days]`.
   Requirements Section 5 states this rule, so apply it here even though
   `find_stress_windows_at_percentile` already filters. A caller may pass windows detected at a
   different minimum.
2. `active = any(w.start <= day.date <= w.end for w in qualifying)`.
3. `future = any(w.start > day.date for w in qualifying)`.
4. `mode = ACTIVE_EVENT if active else PRE_CHARGE if future else NON_EVENT`.
5. On an `ACTIVE_EVENT` day only:
   `peak = peak_window.find_peak_window_for_day(day, next_day, window_hours=config.default_peak_window_hours, wrap=config.default_peak_window_wrap)`
   where `next_day` is `days[i + 1]` or `None`.
6. `DaySchedule(date=day.date, mode=mode, peak_window=peak, ramp_hours=config.default_ramp_hours)`.
   On any other day, `peak_window=None` and `ramp_hours=0`.

`detect_and_build_schedule` calls `stress_finder.find_stress_windows_for_config(days, config)`
and then `build_schedule`. Only `sweep.run_sweep` uses it; `cli` and `api` already hold the
detected windows and pass them, so no path detects twice.

`build_schedule` raises `ValueError` when the input dates are not strictly ascending.

**New in `stress_finder.py`:**

```python
def find_stress_windows_for_config(
    days: Sequence[DailyPercentileLike], config: Config
) -> list[StressWindow]:
    return find_stress_windows_at_percentile(
        days,
        config.default_min_stress_window_days,
        percentile_floor_percent=round(config.default_severity_percentile * 100.0, 9),
        rounding=config.stress_percentile_rounding,
    )
```

This is the exact call `cli._run` and `api.create_run` make today, including D1's
`round(x * 100.0, 9)` float guard. Both call sites replace their copy with it. `stress_finder`
gains an import of `Config`; `config` imports only `models`, so no cycle appears.

**Verify:** `tests/test_schedule.py` covers the three modes, gap days between two windows, the
day after the last window, the qualifying filter, slot arithmetic at hour 0 and hour 21, wrapped
peak windows, and the ascending-date rejection.

---

## 7. Phase 4 — `src/owr/recharge.py` and `initial_soc.py`

One rule, three consumers. This closes requirements Section 12 and Section 15 together.

```python
def charge_request_mw(wind_mw: float, state: HourState) -> float:
    """Wind routed to storage in one hour, before the SoC and power clamps.

    A negative wind value floors at 0.0, which is what both retired surplus
    expressions did. See D13: this function does not widen the engine's input
    validation.
    """
    return max(0.0, wind_mw) if state.charges_from_wind else 0.0


@dataclass(frozen=True)
class ChargeForecast:
    final_soc_mwh: float
    charged_mwh: float          # energy accepted at the terminals, after every clamp


def charge_forward(
    starting_soc: float,
    days: Sequence[DayProfile],
    day_schedules: Sequence[DaySchedule],
    asset: StorageAsset,
) -> ChargeForecast
```

`charge_forward` walks day by day and hour by hour: request from `charge_request_mw`, clamp
with `soc_engine.clamp_charge`, advance with `soc_engine.next_soc(charge=..., discharge=0.0)`,
accumulate `charged_mwh`. It raises `ValueError` when the two sequences differ in length or a
date does not match. It returns `min(soc, asset.total_mwh)` as `final_soc_mwh`, keeping the
belt-and-braces cap `initial_soc` has today.

`charge_forward` models no discharge over its horizon. State this in the docstring: without
discharge the tank fills sooner, so `charged_mwh` is a lower bound on the recharge a real day
would accept, and the budget term it feeds is therefore conservative. Today's
`_surplus_wind_recharge_mwh` ignores discharge in the same way, so this is not a new
simplification.

`initial_soc.charge_from_wind` keeps its name and its place as the Architecture Step 3 boundary
(named in `CLAUDE.md`, `docs/PLAN.md`, `docs/architecture/architecture_overview.md` and the CLI
docstring). New signature:

```python
def charge_from_wind(
    starting_soc: float,
    lead_days: list[DayProfile],
    asset: StorageAsset,
    *,
    schedule: OperatingSchedule,
) -> float
```

Body: slice the schedule for the lead dates, call `recharge.charge_forward`, return
`final_soc_mwh`. Delete the surplus expression. A lead day that falls inside an earlier stress
window is `ACTIVE_EVENT`, so it charges off-peak only; that is correct and follows from one
rule rather than a second policy.

**Verify:** `tests/test_recharge.py` (new) and a rewritten `tests/test_initial_soc.py`. The two
existing surplus tests become pre-charge tests: on a `PRE_CHARGE` day all wind charges
regardless of load, and capacity stops it. Add one negative-wind case pinning the floor (D13).

---

## 8. Phase 5 — `src/owr/dispatch.py`

New signature. The load series is gone: the peak-window search already used the load to pick
the block, and re-shaping inside the block by load cannot be made truncation-invariant
(see D7).

```python
def allocate_discharge(
    *,
    dispatch_window: DispatchWindow | None,
    budget_mwh: float,
    power_mw: float,
    peak_weight: float = 0.5,
    smooth_weight: float = 0.5,
) -> tuple[list[float], list[float], list[float]]
```

Return three lists of length 24, in the existing order `(total, peak, smooth)`.

Rule:

1. `dispatch_window is None` or `budget_mwh <= 0` or `power_mw <= 0` → three zero lists.
2. Normalize the weights as today: `total_weight = peak_weight + smooth_weight`; use 0.5/0.5
   when `total_weight <= 0`.
3. `planned_peak = len(dispatch_window.peak_slots)`;
   `planned_ramp = 2 * dispatch_window.ramp_hours`.
4. When `planned_ramp == 0`, the whole budget forms the peak pool. Read step 4a before changing
   this line.
5. Otherwise `peak_pool = budget_mwh * peak_weight_norm` and
   `ramp_pool = budget_mwh * smooth_weight_norm`.
6. `per_peak_slot = peak_pool / planned_peak`; `per_ramp_slot = ramp_pool / planned_ramp`.
7. Assign `per_peak_slot` to each hour in `peak_hours`, and `per_ramp_slot` to each hour in
   `ramp_up_hours` and `ramp_down_hours`. Slots outside 0..23 receive nothing.
8. Clip each hour at `power_mw` by scaling both components, exactly as today. Clipping only
   ever reduces discharge, so the budget constraint stays safe.

### 8a. Step 4 must test the configuration, never the delivered count

The fold condition is `planned_ramp == 0`, which is `config.default_ramp_hours == 0`. It is
**not** `len(ramp_up_hours) + len(ramp_down_hours) == 0`.

The two differ when ramp slots are planned but every one falls outside the day. A peak window of
24 hours with `ramp_hours = 1` gives slots -1 and 24, so the delivered ramp count is zero while
the planned count is two. Folding on the delivered count there would move the smooth-weighted
share into the peak hours **because the ramp hours were truncated**, which is precisely the
squeeze requirements Section 11 forbids. Folding on the configured count cannot: a configuration
with no ramp block is a design choice, not an event boundary, and dropping that energy would
halve the budget for a reason that has nothing to do with the event.

Both branches get a test. See the test table, rows `F3` and `F4`.

### 8b. `discharge_peak` and `discharge_smooth`

`discharge_peak` now carries peak-window energy and `discharge_smooth` carries ramp energy. The
two column names, the `Config` fields, the CLI flags, the API fields and the database columns
all keep their names; only the docstrings and help text restate the meaning.

### 8c. The no-squeeze guarantee is structural

Divisors are `planned_peak` and `planned_ramp`, counted before truncation. An hour's allocation
therefore depends only on the budget, the two weights and the planned slot counts. It cannot
rise because another slot was dropped. This is the testable form of requirements Section 11's
second bullet, "do not increase discharge power to consume the remaining planned energy".

The rule is uniform across the peak side and the ramp side. Under `WRAP_TO_NEXT_DAY` a wrapped
peak window can lose a peak slot the same way a boundary ramp loses a ramp slot, and the same
arithmetic applies: `per_peak_slot` still divides by three, two hours receive it, and one third
of the peak pool is not delivered. `sum(total) <= budget_mwh` still holds, and no hour receives
more than it would with the slot present. R7 and D14 record the magnitude; row `H2` tests it.

Delete `_peak_signal` and `_ramp_signal`.

**Verify:** rewrite `tests/test_dispatch.py`. Keep the two constraint tests (budget cap, power
cap) and add the rows named `F1` to `F4` and `H2` in the test table.

---

## 9. Phase 6 — `src/owr/simulator.py`

Signature. Everything after `window_days` becomes keyword-only; every current call site already
passes those arguments by keyword, so no caller breaks on that alone.

```python
def simulate(
    asset: StorageAsset,
    window_days: list[DayProfile],
    starting_soc: float,
    *,
    schedule: OperatingSchedule,
    available_capacity_mw: float | None = None,
    config: Config = DEFAULT_CONFIG,
    peak_weight: float = 0.5,
    smooth_weight: float = 0.5,
) -> SimulationResult
```

`schedule` is **required**, with no default and no internal detection fallback. A default that
detects internally would let a caller report one set of windows and simulate another. The
repository already fixed that class of bug once, with `scenario_input.load_day_profiles`
(review finding B1).

First statement of the body:
`day_schedules = schedule.slice_for([d.date for d in window_days])`. Alignment is then
impossible to get wrong, and a missing date raises immediately.

Per day `i`:

```python
day_schedule = day_schedules[i]
remaining_days = window_days[i:]
remaining_cycles = len(remaining_days)
if day_schedule.mode is DayMode.ACTIVE_EVENT:
    forecast = recharge.charge_forward(soc, remaining_days, day_schedules[i:], asset)
    day_budget = budget_mod.daily_budget(
        available_charge_mwh=usable_energy(soc, asset),
        remaining_stress_days=remaining_cycles,
        expected_recharge_mwh=forecast.charged_mwh,
        remaining_cycles=remaining_cycles,
    )
else:
    day_budget = 0.0
hourly_discharge, hourly_peak, hourly_smooth = dispatch_mod.allocate_discharge(
    dispatch_window=day_schedule.dispatch_window,
    budget_mwh=day_budget,
    power_mw=asset.power_mw,
    peak_weight=peak_weight,
    smooth_weight=smooth_weight,
)
```

A day with no dispatch window discharges nothing whatever the budget says, so reporting
`0.0` states the fact rather than a number the day could never spend.

Per hour: keep the discharge clamp, the peak/smooth ratio scaling, and
`net_load_mw = load[h] - discharge` exactly as they are. Replace the charge block with:

```python
request = recharge.charge_request_mw(wind[h], day_schedule.hours[h])
charge = clamp_charge(soc, request, asset)
soc = next_soc(soc, charge=charge, discharge=0.0, one_way_efficiency=asset.one_way_efficiency)
```

Charge and discharge are now mutually exclusive by construction: `charge_request_mw` returns
0.0 on every dispatch hour, and `allocate_discharge` returns 0.0 on every other hour.

**Delete `_surplus_wind_recharge_mwh` entirely.** Update the `hourly_frame` docstring: `charge`
now carries event-relative charging and still never enters `net_load`, so D2 holds unchanged.
Update the module docstring's pipeline comment.

Cost: `charge_forward` over the remaining days inside a per-day loop is `O(n^2 * 24)`.
`_surplus_wind_recharge_mwh` has the same shape today. At 150 days that is about 540,000
float operations per run, which is acceptable for this engine.

**Out of scope:** `remaining_stress_days` and `remaining_cycles` keep the D14 basis, the
remaining days of the simulated span. Counting only active-event days is the separate open
question `recharge_cycle_basis`. D15 states what that leaves unresolved on a multi-event span.

---

## 10. Phase 7 — `src/owr/metrics.py`

```python
def recharge_opportunity_mw(
    *,
    hourly_wind_mw: Sequence[float],
    hourly_load_mw: Sequence[float],
    hourly_discharge_mw: Sequence[float],
    hourly_state: Sequence[HourState],
) -> list[float]
```

Per hour:

| Hour state | Value |
|---|---|
| `PRE_CHARGE`, `ACTIVE_OFF_PEAK` | `wind[h]` |
| `ACTIVE_RAMP_UP`, `ACTIVE_PEAK`, `ACTIVE_RAMP_DOWN` | `max(0.0, wind - max(0.0, load - discharge))` |
| `NON_EVENT` | `0.0` |

Add a fourth length check. Keep the existing `_require_non_negative_series` calls unchanged:
this function is the repository's only negative-wind rejection today, and this change does not
move that boundary (D13). `metrics.py` gains one import, `HourState` from `models`. The module
docstring's claim "metrics.py imports nothing from models" refers to `StorageAsset` in
`recharge_capacity_mismatch_fraction`; restate it as "imports no asset or result type from
models". An enum of six names is the lightest possible carrier of the classification and keeps
`models` as the shared vocabulary.

**Section 17 of the requirements is verified, not assumed.** `cycle_recharge_mismatch_mwh` sums
the two series and rejects a negative element. Every branch above returns a non-negative number:
`wind` is checked non-negative, `0.0` is non-negative, and the surplus branch is floored at
zero. Lengths are unchanged. `recharge_capacity_mismatch_fraction` divides by a capacity it
checks positive and never inspects the series. **Neither downstream formula needs a change.**

Rewrite the docstring: the metric now restates the schedule-driven rule rather than the
simulator's surplus rule, and the drift guard changes (Section 13 below).

---

## 11. Phase 8 — callers

### `src/owr/cli.py`

```python
windows = with_peak_hourly_load(find_stress_windows_for_config(days, cfg), days)
...
schedule = build_schedule(days, stress_windows=windows, config=cfg)
soc_at_start = charge_from_wind(initial_soc_mwh, lead, asset, schedule=schedule) if lead else initial_soc_mwh
result = simulate(asset, span, starting_soc=soc_at_start, schedule=schedule, ...)
```

The schedule is built over **all** file days, so lead days and span days share one
classification. In `_build_report`, the recharge-opportunity loop passes
`hourly_state=list(schedule.for_date(day_profile.date).hours)`.

Report additions, all inside the CLI's own report dictionary and none on an engine value
object: per day `"mode"` and `"peak_window_hours"` (the in-day peak hours, or `null`); per hour
`"state"`. Add one `Daily results` table column, `mode`, so an operator can see why a day
charged nothing. Requirements Section 19 asks that runs be able to use the new behavior; a run
whose output cannot show the operating mode does not demonstrate it.

Open-question maintenance:
- `wind_charge_source`: keep the id, replace the note. The retired text describes the surplus
  rule. The question that stays open is whether the profile's wind is system-wide (which serves
  load) or a dedicated farm (which routes to the reserve first). Under the new policy the model
  assumes the dedicated reading on pre-charge and off-peak hours.
- `recharge_opportunity_definition`: replace the note with the three-way rule and its
  `value_used` string.
- Add `ramp_duration` (flags `[]`, value `cfg.default_ramp_hours`, handoff ref
  `docs/architecture/event_relative_recharge.md` Section 10).
- Add `peak_window_wrap` (flags `[]`, value `cfg.default_peak_window_wrap`, handoff ref
  Section 9). Its note carries the R7 consequence.
- Add `recharge_cycle_basis` to the note text of D15's limitation. The id already exists in
  `_OPEN_QUESTIONS_STATIC` and is already reported; extend its note with the multi-event case.

### `src/owr/api/app.py`

```python
cfg = replace(
    DEFAULT_CONFIG,
    default_severity_percentile=inp.severity_percentile,
    default_min_stress_window_days=inp.min_stress_window_days,
)
run.stress_windows = with_peak_hourly_load(find_stress_windows_for_config(days, cfg), days)
schedule = build_schedule(days, stress_windows=run.stress_windows, config=cfg)
run.result = simulate(asset, days, starting_soc=starting_soc, schedule=schedule, config=cfg, ...)
```

Use `dataclasses.replace`, and replace only these two fields. The API today detects with the
scenario's percentile and window length but simulates with `DEFAULT_CONFIG`; without this the
schedule builder would filter qualifying windows against a different minimum than detection
used. Do not push `peak_weight` or `smooth_weight` into the `Config`: the schema permits both
to be 0.0, which `Config.__post_init__` rejects, and that would turn a currently valid request
into a 422.

### `src/owr/sweep.py`

Build once before the size loop:
`schedule = detect_and_build_schedule(days, config=config)`. The schedule depends on load, wind
and config only, never on storage size, so one build serves every point and every point sees the
same classification.

### `src/owr/api/schemas.py`, `src/owr/scenario_input.py`, `src/owr/budget.py`

No code change. See D10, D11 and Section 16.

---

## 12. Deviations from the requirements document

Each item states the document's assumption, the repository evidence, and the chosen resolution.

**D1 — `initial_soc` and the simulator do not share a rule today.** Section 12 says
`initial_soc` uses "a surplus-wind rule". It uses `max(0, wind - max(0, load))`, while the
simulator hour loop uses `max(0, wind - max(0, load - discharge))` and
`_surplus_wind_recharge_mwh` uses the first form again, under a docstring that claims it matches
the second. All three are deleted, so the discrepancy disappears rather than being ported.

**D2 — the simulator has no event input.** Sections 2 and 13 leave open who owns schedule
construction but assume the simulator can act on event state. It cannot: `simulate` never
receives a `StressWindow`. The plan adds a required `schedule` argument instead of detecting
inside the simulator, so exactly one detection runs per command and the reported windows and the
simulated windows are the same objects.

**D3 — an event cannot end inside a day.** Section 11 and cases F and G assume sub-day
termination. `stress_finder` emits whole-day windows and `StressWindow.last_hour_index` is
`24 * days - 1`. The reachable truncation is the day boundary. The plan implements one general
rule that covers both readings: *a planned slot outside 0..23 is not delivered, and its energy is
not moved.* Cases F, G and "immediately after the peak window" are tested as boundary
geometries. If the team later adds sub-day event ends, the same rule applies without change,
because the divisor is the planned slot count.

**D4 — Section 16 names only two hour classes.** Four exist. `PRE_CHARGE` takes the off-peak
value, `wind[h]`, because the policy routes all its wind to storage. `NON_EVENT` takes `0.0`,
because the policy routes all its wind to the grid by design, so no recharge opportunity exists
to miss. The alternative — keeping the surplus formula on non-event hours — would report every
non-event hour of surplus wind as a missed opportunity and would make `RCM` look worse the more
non-event days a span contains, which the CLI default `--window all` guarantees. **This choice
needs team confirmation.** It is surfaced as the CLI open question
`recharge_opportunity_definition`.

**D5 — Section 17 verified.** Both downstream formulas are unchanged, and Section 10 above gives
the argument from source, not from assumption.

**D6 — Section 9 verified, and it changes nothing on its own.** The candidate arithmetic matches
the document exactly. However no engine module reads `default_peak_window_wrap` today, so the
flip is observable only after the schedule consumes `peak_window`. Do not treat the flip as an
independently testable behavior change beyond `tests/test_config.py`.

**D7 — dispatch loses its load-derived shape.** Section 14 asks for a ramp-up → peak →
ramp-down structure with no squeezing on early termination. Any allocation whose per-hour share
is renormalized over the surviving hours can raise an hour's discharge when a slot is dropped,
which Section 11's second bullet forbids. Any allocation shaped by in-block load cannot be
evaluated for a slot outside the day. The two constraints together force a positional rule. The
plan keeps `peak_weight` and `smooth_weight` with a restated meaning (peak-window energy share
against ramp energy share) instead of deleting them, because deleting them would break the API
wire format, the `app.scenario` table and two CLI flags. Consequence to expect: dispatch is
confined to the block and no longer smooths ramps elsewhere in the day, which is the intended
effect of the new operating model.

**D8 — discharge is confined to dispatch hours.** Section 3's table states wind routing and
charging but not discharge. Section 6.1 says grid load in off-peak hours is covered by other
resources, and Section 7 asks whether the dispatch schedule should be active in an hour. The
plan reads both as: storage discharges only in ramp-up, peak and ramp-down hours. A model that
charges and discharges in the same hour is not physical, and the current code permits it.

**D9 — cycle basis unchanged.** `remaining_stress_days` and `remaining_cycles` keep the D14
reading of `docs/archive/plans/PLAN_ARCH_0805_SYNC.md`. Changing them belongs to the open
question `recharge_cycle_basis`. D15 records what that leaves open here.

**D10 — no new public result field.** Section 20 permits a `models.py` change only when
reporting needs it. `api/pg_store._load_result` rebuilds `SimulationResult` column by column, so
a new `HourlyResult` field would silently read back as its default without a new migration. The
CLI holds the schedule object and reports from it instead, at no schema cost. The API therefore
does not expose the hour state in this change; Section 16 records the follow-on.

**D11 — `budget.py` needs no formula change.** `daily_budget` already takes
`expected_recharge_mwh` from its caller and fixes no recharge definition. The rule moves from
`simulator._surplus_wind_recharge_mwh` (deleted) to `recharge.charge_forward` (schedule-driven).
Only the module docstring changes, to name the new source of the term. Requirements Section 15
is met by the value, not by editing the file.

**D12 — pre-charge has no lead-time limit.** Section 5 makes every non-active day that precedes
a qualifying window a pre-charge day. The plan implements exactly that, including gap days
between two windows. No lead-time cap is invented.

**D13 — negative wind keeps today's flooring, and the engine does not gain a new failure
surface.** `charge_request_mw` could reasonably raise on a negative wind value, since
`metrics.recharge_opportunity_mw` does. It does not, for three reasons. First, both retired
surplus expressions floored the value, so raising would change behavior for a reason unrelated
to this feature. Second, the boundary that owns input validation is `scenario_input` and
`api/schemas`, and neither rejects negative wind today; widening them is a separate input-format
decision with an ETL cost. Third, the raise would fire per hour inside `simulate`, which turns a
silently-degraded run into a 422 for `api.create_run` and an uncaught error for
`sweep.run_sweep`. The floor is pinned by a test in `tests/test_recharge.py`, and the
pre-existing asymmetry with `metrics.py` is recorded here rather than resolved.

**D14 — a wrapped peak window loses its out-of-day slot.** Requirements Section 9 flips the
default to `STOP_AT_MIDNIGHT`, which makes this unreachable at the shipped configuration. The
value `WRAP_TO_NEXT_DAY` stays legal because the team question is open. Under it, a day whose
highest triplet wraps gets peak slots (22, 23, 24), and slot 24 does not exist in that day. The
plan applies the same rule it applies to a truncated ramp: the slot is not delivered and its
energy is not moved, so up to `1 / window_hours` of the peak pool goes unspent. Special-casing
the peak side would break the uniform slot rule that makes the no-squeeze guarantee provable.
The consequence is documented in `config.py`, reported through the `peak_window_wrap` open
question, and tested by row `H2`.

**D15 — a multi-event span mixes two bases in `daily_budget`, and this change does not fix it.**
On a span containing two qualifying windows, the divisor `remaining_stress_days` counts every
remaining day, including gap days and the days of a later unrelated event. The numerator is now
schedule-aware: gap days are `PRE_CHARGE` and contribute their full wind, while the tail after
the last window is `NON_EVENT` and contributes nothing. The two terms therefore no longer count
the same set of days. This mismatch predates the change — today's divisor has the same shape and
today's numerator credits surplus wind on every remaining day — and correcting it means choosing
a cycle basis, which is the open question `recharge_cycle_basis` (D9). Neither shipped example
contains a second window, so the interaction is untested today. The plan adds a two-window
fixture that pins and documents the resulting behavior (test row `M1`) without changing the
basis, and extends the `recharge_cycle_basis` open-question note with the multi-event case. Fix
the basis in a separate change, once the team answers.

---

## 13. Test plan

### Requirements Section 23, cases A to J

| Case | Test | Module |
|---|---|---|
| A — no upcoming event | A span with no qualifying window gives `HourState.NON_EVENT` for all 24 hours, `charge == 0.0` every hour, and `sum(discharge) == 0.0` | `test_schedule.py`, `test_simulator.py` |
| B — future qualifying event | A day before a 2-day window is `PRE_CHARGE`; every hour's `charge` equals `wind[h]` until capacity binds, and SoC gains `charge * one_way_efficiency` | `test_schedule.py`, `test_recharge.py`, `test_simulator.py` |
| C — active off-peak | On an active day, every hour outside `dispatch_hours` is `ACTIVE_OFF_PEAK` and charges `wind[h]` | `test_simulator.py` |
| D — active peak and ramp | Every hour in `dispatch_hours` has `charge == 0.0` and is the only place discharge appears | `test_simulator.py` |
| E — capacity reached | Pre-charge with wind far above headroom ends at `soc == total_mwh` and stays there | `test_recharge.py`, `test_simulator.py` |
| F1 — ends before ramp-down | Peak at 21,22,23 with `ramp_hours=1`: `ramp_down_slots == (24,)`, `ramp_down_hours == ()`, and every other hour's discharge equals its value for a peak at 17 with the same budget | `test_dispatch.py`, `test_schedule.py` |
| F2 — ends during ramp-down | `ramp_hours=2` and peak at 20,21,22: `ramp_down_slots == (23, 24)`, hour 23 delivers `per_ramp_slot` and hour 24 delivers nothing; hours 18 and 19 are unchanged against an untruncated block | `test_dispatch.py` |
| G — ends immediately after the peak | Peak at 21,22,23 with `ramp_hours=1` and `peak_weight=1.0`: peak hours deliver the whole budget and the day ends at the last peak hour | `test_dispatch.py` |
| H1 — peak at end of day | With `STOP_AT_MIDNIGHT` and `window_hours=3`, a day whose highest triplet is 21,22,23 gives `start_hour == 21`, `candidates_considered == 22`, `wrapped is False`, and `peak_hours == (21, 22, 23)`; hour 0 of the next day never appears | `test_peak_window.py` (exists), `test_schedule.py` |
| I — recharge opportunity | Each of the three branches of the table in Section 10, on a hand-built state sequence | `test_metrics.py` |
| J — downstream metrics | `recharge_opportunity_mw` → `cycle_recharge_mismatch_mwh` → `recharge_capacity_mismatch_fraction` on a hand-checked series, with the two downstream functions unmodified | `test_metrics.py` |

### Cases added by the adversarial review

| Case | Test |
|---|---|
| H2 — wrapped peak window truncated | Build a day whose highest triplet wraps, with `WRAP_TO_NEXT_DAY`. Assert `peak_slots == (22, 23, 24)`, `peak_hours == (22, 23)`, `wrapped is True`, `planned_slot_count == 5` at `ramp_hours=1`; assert hours 22 and 23 each receive `peak_pool / 3` and `sum(total) < budget_mwh`; assert those two values are identical to a run of the same budget with an untruncated peak at hour 17. This is the peak-side proof of Section 8c |
| F3 — ramp planned but wholly outside the day | `window_hours=24`, `ramp_hours=1`: `ramp_up_slots == (-1,)`, `ramp_down_slots == (24,)`, both hour tuples empty. Assert the smooth pool is **dropped**, not folded, and that every peak hour receives `peak_pool / 24` — the same value it receives when both ramp slots exist |
| F4 — no ramp configured | `ramp_hours=0`: assert the smooth pool **is** folded into the peak pool, so each peak hour receives `budget_mwh / window_hours`. Together with F3 this pins Section 8a |
| M1 — two-window span | An 8-day fixture with two 2-day windows, a 2-day gap and a 2-day trailing tail, simulated under the `--window all` shape. Assert the gap days are `PRE_CHARGE` and charge their full wind, and the trailing days are `NON_EVENT` and charge nothing. **Then pin the D15 mismatch itself**, per Section 13.2. Reference D15 in the test docstring |
| N1 — negative wind floors | One `PRE_CHARGE` day with a negative wind hour: `charge_request_mw` returns 0.0 and `simulate` completes without raising. Reference D13 |

### Requirements Section 24, architectural criteria

| # | How the suite demonstrates it |
|---|---|
| 1 | `OperatingSchedule` is the only type carrying hour classification, and `DaySchedule.hours` is derived, not stored. The structural guard in Section 4.4 proves the second half |
| 2, 3, 4, 5 | `simulate`, `allocate_discharge`, `charge_forward` and `recharge_opportunity_mw` each take the schedule or a value derived from it; none accepts a `StressWindow` or a `PeakWindow` |
| 6 | A guard test asserts that `schedule.py` is the only `src/owr` module that imports `peak_window`, by reading the source files and searching for the import |
| 7 | A source guard proves the surplus rule did not come back **in code**. A plain text search cannot do this; see Section 13.1 for why and for the test |
| 8 | Rows F1, F2, F3 and H2, each stated as equality against the untruncated allocation |
| 9 | Case E, plus the existing floor tests in `test_simulator.py` |
| 10 | Case H1, plus `tests/test_config.py`'s default assertion |
| 11, 12 | Not test-provable. Demonstrated by the file table in Section 3: three business rules (classification, charging, dispatch shape) live in one module each, and three duplicate copies are deleted |

### 13.1 The two architectural guard tests

Write both in `tests/test_schedule.py` under a section comment named `architectural guards`, and
say in a comment what each one protects.

**Guard 6, import centralization.** Read each file under `src/owr/` and assert that
`peak_window` is imported by `src/owr/schedule.py` only. `tests/` and `src/owr/etl/` stay out of
scope.

**Guard 7, the surplus rule did not come back.** A plain text search fails on day one. The
expression `max(0.0, wind - max(0.0, load - discharge))` already appears **twice** in
`src/owr/metrics.py` today: at line 242 inside the `recharge_opportunity_mw` docstring, and at
line 271 in code (both verified 2026-08-10). The house style quotes a formula in prose beside the
code, and Section 10 keeps that docstring, so the prose occurrence must survive.

Count code occurrences only. Strip every docstring through the abstract syntax tree, then
unparse, which also drops comments:

```python
SURPLUS = ast.unparse(ast.parse("max(0.0, wind - max(0.0, load - discharge))")).strip()


def _code_text(path: Path) -> str:
    """Module source with every docstring and every comment removed."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            if ast.get_docstring(node) is not None:
                node.body = node.body[1:]
    return ast.unparse(tree)
```

Two assertions:

- `SURPLUS` appears exactly once across the `_code_text` of every module under `src/owr/`, and
  that occurrence is in `src/owr/metrics.py`.
- `not hasattr(owr.simulator, "_surplus_wind_recharge_mwh")`. An attribute check, not a text
  search, so a renamed-but-retained helper still fails it.

Build `SURPLUS` by parsing and unparsing the expression itself, as shown. Both sides then pass
through the same normalizer, so no hand-written spacing can drift from what `ast.unparse` emits.

Anchor on the whole expression, never on a short idiom such as `- max(0.0, load`. A short idiom
cannot tell the surplus rule from an unrelated line that shares six characters.

Measured on the current tree: the raw text count in `metrics.py` is 2, the `_code_text` count is
1, and no other module under `src/owr/` contains it. The guard therefore passes before the change
and keeps passing after it.

One honest limit: the guard depends on the three local names `wind`, `load` and `discharge`
inside `recharge_opportunity_mw`. A rename breaks it. The fix is to update the constant in the
test, never to shorten the pattern.

**This is a new kind of test for this repository. Do not describe it as an existing pattern.**
The nearest relatives,
`tests/test_metrics.py::test_recharge_opportunity_matches_simulator_at_scale_where_no_clamp_binds`
and `tests/test_stress_finder.py::test_percentile_rank_matches_demo_profile`, compare **computed
values** across two modules; neither reads source text. A value comparison cannot observe code
structure, and requirements criterion 7 is a claim about code structure, so a source guard is the
only mechanical evidence available for it. Every other part of criterion 7 rests on the
behavioral tests above.

### 13.2 Test M1 must pin the D15 mismatch, not restate the schedule

The mode and charge assertions in row M1 duplicate what `tests/test_schedule.py` already covers,
and they would hold equally before and after a future `recharge_cycle_basis` fix. An assertion
that a budget is "finite and non-negative" carries no regression signal at all. Add the following,
which does carry one:

```python
def soc_at_start_of(i: int) -> float:
    return starting_soc if i == 0 else result.daily[i - 1].hourly[-1].soc


for i, day_result in enumerate(result.daily):
    if day_schedules[i].mode is not DayMode.ACTIVE_EVENT:
        assert day_result.budget == 0.0
        continue
    soc = soc_at_start_of(i)
    remaining = len(span) - i     # D15: counts gap days and the second event's days
    expected = budget.daily_budget(
        available_charge_mwh=usable_energy(soc, asset),
        remaining_stress_days=remaining,
        expected_recharge_mwh=recharge.charge_forward(
            soc, span[i:], day_schedules[i:], asset
        ).charged_mwh,
        remaining_cycles=remaining,
    )
    assert day_result.budget == pytest.approx(expected)
```

Call `budget.daily_budget` rather than restating its `min`. The documented mismatch lives in the
two **inputs**, not in the formula: `remaining` is the divisor D15 names and it counts days that
are not stress days, while `charged_mwh` is schedule-aware and returns nothing on the trailing
`NON_EVENT` days. A future change to the cycle basis must therefore edit this test, which is the
whole point of writing it.

### Existing tests that must change

| File | Change |
|---|---|
| `tests/test_config.py` | Lines 106-123: default wrap is now `STOP_AT_MIDNIGHT` and the JSON value is `"stop_at_midnight"`; add `default_ramp_hours` range tests |
| `tests/test_dispatch.py` | Full rewrite onto the new signature |
| `tests/test_initial_soc.py` | Full rewrite: the two surplus tests become pre-charge tests |
| `tests/test_simulator.py` | Add `schedule=` to every `simulate(` call; rewrite `test_surplus_wind_charging_does_not_raise_the_reserve_peak`, `test_budget_is_zero_without_surplus_wind`, `test_budget_rises_with_more_surplus_wind`, `test_capacity_margin_follows_the_net_load_definition` |
| `tests/test_metrics.py` | Add `hourly_state` to every `recharge_opportunity_mw` call; restrict `test_recharge_opportunity_matches_simulator_at_scale_where_no_clamp_binds` to off-peak hours, because opportunity and charge now differ by design on peak/ramp hours |
| `tests/test_cli.py` | Line 265 `simulate(` call; `test_reserve_peak_equals_baseline_without_surplus_wind` inverts (see below); `test_lead_days_correctness_by_equality_against_charge_from_wind` must build its asset at the CLI's efficiency and pass the same schedule |
| `tests/test_sweep.py` | Line 173 direct `simulate(` call gains a schedule |
| `tests/test_api.py` | Comments naming the surplus rule; `test_run_with_no_surplus_wind_discharges_nothing` |

**Expect `test_reserve_peak_equals_baseline_without_surplus_wind` to invert.**
`examples/synthetic_winter_stress.csv` carries 400 MW of wind per hour on its three stress days
against an 8,000-12,000 MW load, so today's surplus rule yields zero recharge and a zero budget.
Under the new rule those off-peak hours charge 400 MW each, the recharge term becomes positive,
and severity reduction becomes positive at the identity wind multiplier. That is the feature
working. Rewrite the test to assert the new fact and keep its comment naming the reason.

### Measured facts to build fixtures against

- `examples/synthetic_winter_stress.csv`: 6 days, one detected window 2026-01-09 to 2026-01-11.
  Days 0-2 become `PRE_CHARGE`; days 3-5 become `ACTIVE_EVENT`. Peak start hours under
  `STOP_AT_MIDNIGHT` are `[0, 0, 0, 16, 17, 16]`.
- `examples/real_winter_stress_2026.csv`: 11 days, one detected window covering all of them, so
  no pre-charge or non-event day exists in that file. Peak start hours are
  `[17, 12, 17, 17, 17, 17, 17, 17, 17, 17, 17]`.
- Neither shipped example produces a truncated dispatch block on an active day, and neither
  contains a second window. Rows F1 to F4, G, H2, M1 and N1 need hand-built fixtures.

---

## 14. Documentation to update

- `CLAUDE.md`: two new rows (`src/owr/schedule.py`, `src/owr/recharge.py`); update the pipeline
  line to `stress_finder + peak_window → schedule → initial_soc → [per day: budget → dispatch →
  soc_engine] → metrics`.
- `docs/architecture/architecture_overview.md`: the Step 3 and Step 5 recharge descriptions and
  the `net_load` note at line 238.
- `README.md` line 61 and `DEMO.md` lines 70, 88, 100, 138: the surplus-wind narrative and every
  pinned number in those runs. Regenerate the DEMO output after implementation; do not hand-edit
  the numbers.
- `src/owr/etl/cli.py` line 461: the `simulate`'s surplus-wind recharge sentence.
- `docs/BOARD.md`: one entry recording the change.

---

## 15. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | Every shipped example changes its numbers. Charging rises sharply, budgets stop being zero, severity reduction becomes positive at the identity wind multiplier | Named in Section 13. Rewrite the affected tests to assert the new fact, and regenerate `DEMO.md` from a real run |
| R2 | `charge_forward` inside the per-day loop is `O(n^2 * 24)` | Same shape as the deleted `_surplus_wind_recharge_mwh`. Acceptable at the season lengths this engine runs |
| R3 | The budget forecast ignores discharge over its horizon, so it under-states headroom and therefore under-states recharge | Documented in the `charge_forward` docstring as a conservative lower bound; unchanged in character from today |
| R4 | `--window all` and `--window N` now diverge more, because non-event days charge nothing at all | Report the per-day mode in the CLI so the divergence is visible, not silent |
| R5 | `default_ramp_hours = 1` has no source | Marked `[TWEAK]` and surfaced as the open question `ramp_duration` in every JSON report |
| R6 | The `NON_EVENT` opportunity value of `0.0` is a plan decision, not a document statement | D4 states the alternative and routes the decision to the team through `recharge_opportunity_definition` |
| R7 | Under `WRAP_TO_NEXT_DAY` a wrapped peak window silently under-spends up to `1 / window_hours` of the peak pool. That is one third at the settled 3-hour window, a much larger loss than a dropped ramp slot | D14. The shipped default makes it unreachable; `config.py` records the consequence; the `peak_window_wrap` open question reports it every run; test row `H2` pins it |
| R8 | `cached_property` on a frozen dataclass is unusual in this repository and could surprise a reader | Section 4.3 states why it is required and names the `__post_init__` fallback. The structural guard in Section 4.4 fails loudly if someone converts it back to a stored field |

---

## 16. Deferred follow-on: schedule state over the API

The CLI reports `mode` and `state`; the API does not. An API or Postgres consumer therefore sees
a run whose charge and discharge are zero on many hours with nothing in the payload to explain
why. This is a real reporting gap, and it is out of scope here for the cost stated in D10: the
field would need migration 004 on `app.run_result_hourly`, a new `HourlyResultOut` field, and a
matching read in `api/pg_store._load_result`, or every persisted run would read the state back as
a default and lie.

Record it as a follow-on task in `docs/BOARD.md` with this shape: add `hour_state text` to
`app.run_result_hourly` and `day_mode text` to `app.run_result_daily` in migration 004, carry
both on the wire, and write them from the schedule the run already built. Do not attempt it
inside this change.

---

## 17. Revision log

Revised 2026-08-10 after adversarial review. Six findings; five changed the plan.

1. **`DaySchedule` stored the hour states and the block separately (moderate).** Accepted.
   Section 4 now stores one fact per day — the mode, the `PeakWindow` and the ramp length — and
   derives `dispatch_window` and `hours` as `cached_property` values. `DispatchWindow` likewise
   stores only `peak_slots` and `ramp_hours` and derives both ramp groups. `schedule._hour_states`
   and `schedule._dispatch_window` are gone. A structural guard test (Section 4.4) fails if a
   later change re-stores a derived fact.
2. **Multi-event spans mix two bases in `daily_budget` (moderate).** Accepted as a documented
   limitation plus a fixture, not a fix: correcting the divisor means choosing a cycle basis,
   which is the open question `recharge_cycle_basis`. Added D15, test row `M1`, and an extension
   to the `recharge_cycle_basis` open-question note.
3. **A wrapped peak window can lose a peak slot, untested (moderate).** Accepted. Added D14,
   risk R7, test row `H2`, Section 8c's peak-side statement, and a consequence note in
   `config.py`'s `default_peak_window_wrap` docstring. The uniform slot rule is kept on purpose;
   special-casing the peak side would break the no-squeeze proof.
4. **`charge_request_mw` raising on negative wind widened the engine's failure surface (low).**
   Accepted. The function now floors, matching both retired surplus expressions. Added D13, test
   row `N1`, and evidence item 8 in Section 2.
5. **API consumers get no explanation field (nit).** Accepted as scope. Added Section 16 with
   the migration cost and a `docs/BOARD.md` follow-on entry.
6. **Fold the smooth pool on the delivered ramp count instead of the configured count (nit).**
   **Rejected, and the plan now says why.** Folding on the delivered count would move the
   smooth-weighted share into the peak hours *because the ramp hours were truncated*, which is
   the squeeze requirements Section 11 forbids. The configured count is the correct condition:
   a configuration with no ramp block is a design choice, an out-of-day ramp slot is an event
   boundary, and the two must behave differently. Section 8a states the distinction and test rows
   `F3` and `F4` pin both branches.

Second review pass, same day. Two findings, both accepted.

7. **The criterion-7 guard would have failed on day one.** The reviewer read the live file: the
   surplus expression already appears twice in `src/owr/metrics.py`, once in the docstring at
   line 242 and once in code at line 271. Counting raw text therefore fails before any code
   changes. New Section 13.1 counts code occurrences only, by stripping docstrings through the
   abstract syntax tree and unparsing, which also drops comments. Measured on the current tree:
   raw count 2, code count 1, no other module. The guard now anchors on the whole expression
   rather than the idiom `- max(0.0, load`, adds a direct
   `hasattr(owr.simulator, "_surplus_wind_recharge_mwh")` check, and names its own brittleness.
   The claim that this style has precedent in the repository was **wrong** and is withdrawn:
   the two existing drift guards compare computed values, not source text, and Section 13.1 now
   says so.
8. **Test M1 did not pin the D15 mismatch.** Its assertions would have survived a future cycle
   basis change untouched. New Section 13.2 recomputes each active day's budget from the two
   documented inputs — the all-remaining-days divisor and the schedule-aware numerator — and
   asserts equality against the reported budget. A change to the basis now forces an edit to this
   test.

---

## 18. Phase order and verification gate

Run `uv run pytest` and `uv run ruff check .` after each phase.

1. `models.py` types — suite stays green (additive).
2. `config.py` flip and `default_ramp_hours` — only `tests/test_config.py` changes.
3. `schedule.py` and `stress_finder.find_stress_windows_for_config` — additive; new tests pass.
4. `recharge.py` and `initial_soc.py` — `tests/test_initial_soc.py` and `tests/test_cli.py` lead-day tests change.
5. `dispatch.py` — `tests/test_dispatch.py` rewritten; `simulator` is still broken at this point, so run phases 5 and 6 together if the suite must stay green between commits.
6. `simulator.py` — `tests/test_simulator.py`, `tests/test_sweep.py`, `tests/test_metrics.py` change.
7. `metrics.py` — `tests/test_metrics.py` completes.
8. `cli.py`, `api/app.py`, `sweep.py` — `tests/test_cli.py`, `tests/test_api.py` complete.
9. Documentation, `DEMO.md` regeneration, and the `docs/BOARD.md` follow-on entry from Section 16.

The gate for "done": `uv run pytest` reports at least 738 passed with 4 skipped, `uv run ruff
check .` is clean, and `uv run simulate --input examples/real_winter_stress_2026.csv
--storage-mwh 60000 --power-mw 5000 --format json` shows a non-zero `energy_charged_mwh`, a
per-day `mode`, and a per-hour `state`.
