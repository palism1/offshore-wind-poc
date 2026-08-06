# Plan: sync the code to the 2026-08-05 Architecture export

**Status, 2026-08-05: shipped.** Branch `arch-0805-sync`, cut from `main` at
`9dee3ef`. Commits: `86979ba` (Phase 1), `51aba25` (Change B phase 1), `a5e4bfa`
(Change B phase 2), `3ec20e1` (Change B phase 3), plus this docs commit for Phase 5.
Final counts: 572 passed, 4 skipped (3 Postgres, 1 viz), `uv run ruff check .` clean.

Two changes against `docs/source/2026-08-05_Software_Architecture_Documentation.md`,
Component 3. Change A relabels one config value from a team choice to a sourced value.
Change B implements the four output-table fields the export named.

Five phases, five commits. Phase 1 is Change A and lands alone. Phases 2 to 5 are
Change B. Every phase ends green on `uv run pytest` and `uv run ruff check .`.

Baseline at plan time: `main` at `9dee3ef`, suite green, 4 skipped (3 Postgres, 1 viz).

Revision 1, 2026-08-05: adversarial review added decision D9, corrected the D4
evidence and the Assumption 1 reversal cost, and fixed four spec defects in
Phases 3 and 4.

---

## Source text this plan implements

Component 3, Event Detection Rule:

> Determine:
> 90th historical daily load percentile
>
> A stress event begins when:
> daily_load >= 90th percentile
> for
> minimum_window
> consecutive days.

Component 3, Data Contract, the four rows that were blank in the 2026-08-04 export:

| Field | Unit | Description |
|---|---|---|
| `first_hour_index` | hour | @ |
| `last_hour_index` | hour | @ |
| `peak_hourly_load` | MW? | @ |
| `load_percentile_threshold` | Percentile | @ |

All four Description cells hold `@`. The repo treats an `@` cell as an open team
question with a documented reading, the same as `recharge_opportunity_definition`
and `recharge_capacity_denominator` in `docs/PLAN_METRICS_COMPONENT7.md`.

---

## Decisions and their reasons

### D1 — `stress_event_definition` keeps its id, its flags and its `[OPEN]` marker

`docs/PLAN_STORAGE_PHYSICS_PEAK_WINDOW.md` line 553 already set this precedent:
"The rule is settled; the p90 threshold value on real data is not, and that is what
the flag now points at." Change A narrows the note text only. A rename would touch
`tests/test_cli.py:109`, two plan docs and the `handoff_ref` for no gain.

### D2 — The percentile becomes sourced; `minimum_window` stays a team choice

The export fixes 0.90. The export names `minimum_window` and gives it no value.
The `config.py` attribute block therefore splits into two entries with different
provenance. `default_min_stress_window_days` keeps the 2026-07-28 team decision.

### D3 — `sweep_cli.py` needs no change in either phase

The task brief expected a sweep-side edit. There is none to make.
`src/owr/sweep_cli.py` declares no `--severity-percentile` flag, carries no
`stress_event_definition` entry in `_OPEN_QUESTIONS_STATIC`, and renders no
`config` block. `src/owr/sweep.py` contains no reference to stress detection: the
sweep simulates every day in the file and does no window selection. The chart
footer text "Team design constants, not verified facts" stays true, because it
covers efficiency, floors, the size ladder and the power rule, and none of those
moved.

### D4 — `first_hour_index` and `last_hour_index` are event-local properties

The reading: both indices sit on an event-local hour axis. `first_hour_index` is 0.
`last_hour_index` is `HOURS_PER_DAY * days - 1`.

**The source evidence is mixed, and the plan does not claim otherwise.** Component 4
carries this row in full:

| Field | Unit | Description |
|---|---|---|
| `current_hour_index` | index | an index referencing the most recent hour in the Eastern Time zone |

The phrase "the most recent hour" fits an event-local counter that the Component 5
loop advances over "each hour between event_start and event_end". The phrase "in the
Eastern Time zone" names a wall-clock anchor and fits an absolute index instead. One
sentence supports both readings. Component 3 gives its own two fields the Unit "hour"
and no description at all, so it settles nothing.

**The decision rests on what is computable, not on the quote.** An absolute index
needs an origin for the hour axis. No detection path has a stable one:

- The ETL path allows gaps. `find_stress_windows_at_threshold` splits a run on a
  missing date, and `validate` reports gaps without failing. An hour offset counted
  from the first row is therefore wrong whenever a day is missing.
- The simulator CLI path has no gaps, but its origin is the first date in the input
  file. That is an artifact of which file the operator passed, not a property of the
  event. Two files that both contain the same event would report different indices.

Event-local is the only reading that is well defined on every path and stable across
inputs. Ship it, tag it, and let the team overrule it. Assumption 1 records what a
reversal costs, and the cost is a migration.

Under the settled daily rule both values are a pure function of `days`. Three
consequences follow, and all three favour properties over stored fields:

1. A stored copy can drift from `days`. A property cannot.
2. `api/pg_store.py` writes windows into the `result_summary` JSON. A derived value
   in that JSON would go stale and would need a migration to change. A property
   needs neither.
3. Every existing `StressWindow` construction site stays unchanged.

The honest caveat goes in the docstring: the two indices carry no information that
`days` does not already carry. They exist because the source table names them.

### D5 — `peak_hourly_load_mw` is a stored optional field, filled by a separate function

Detection runs on `DailyLoadLike`, a protocol of `date` and `load_mwh`. It has no
hourly series, and it must not gain one: `owr.etl.daily.DailyLoad` and
`owr.etl.transform._DailyPoint` both satisfy `DailyLoadLike` and neither can supply
hourly data, because the ETL path reduces interval readings to a daily total before
detection runs.

So `stress_finder` gains one new function, `with_peak_hourly_load(windows, days)`,
which takes a second protocol, `HourlyLoadLike`. `DayProfile` satisfies it. The
simulator CLI and the API both hold `DayProfile` objects and both call it straight
after detection. The ETL path does not call it, and its windows keep
`peak_hourly_load_mw = None`.

This mirrors the existing `find_stress_windows` and `find_stress_windows_at_threshold`
split: one function per set of available inputs, no duck typing, no hidden behaviour.

The "MW?" unit: the engine's hourly series is in MW (`DayProfile.hourly_load_mw`),
and `DayProfile.load_mwh` sums MW over 24 hours to get MWh. At one-hour resolution
the peak hour's energy in MWh equals its average power in MW. The `?` is therefore a
label question, not a value question. Document that, tag it, ship the MW label.

### D6 — `load_percentile_threshold` travels as two fields

The Unit cell reads "Percentile" and points at the fraction 0.90. The field name's
head noun is "threshold" and points at the MWh cut value. The repo already models
both, as `owr.etl.transform.ThresholdResult.percentile` and `.threshold_mwh`, and
`etl/cli.py` already prints both.

`StressWindow` therefore gains `threshold_mwh` and `severity_percentile`.
`threshold_mwh` is set on every detection path. `severity_percentile` is `None` when
the caller supplied a threshold directly and never named a percentile, which is the
ETL path.

This also serves Change A: the still-open item is the MWh threshold value on real
data, and this field puts that number on every detected window.

### D7 — One new open-question id covers all four fields

New id: `stress_window_output_fields`. Alternative considered and rejected: one id
per `@` cell, which is the `PLAN_METRICS_COMPONENT7.md` pattern. Rejected because
these four cells are one table block in one component, they land in one commit, and
one person fills all four in one edit. One note that names each field's reading
keeps the CLI open-questions block readable.

No `Config` field goes with it. There is no number to tune, only a reading to
record. `recharge_opportunity_definition` and `recharge_capacity_denominator` set
that precedent: an open question with `"flags": []`, no `Config` field, and a
`handoff_ref` that points at the plan doc.

### D8 — `hour_count` is not added

The source lists "event hour count" under Derived Fields, not in the Data Contract.
It equals `last_hour_index + 1`. A consumer that wants it computes it. Adding it is
scope the task did not ask for.

### D9 — The ETL event frame stays at four columns

`src/owr/etl/transform.py::find_windows_per_winter` calls its output "The Component 3
event table", and `EVENT_FRAME_COLUMNS` holds `winter_label`, `event_start_date`,
`event_end_date` and `event_duration_days`. After Phase 2 the `StressWindow` objects
that function builds carry `threshold_mwh`, and the frame still drops it. That is
deliberate.

**Reason 1: the value is a scalar over the whole frame, not a per-row value.**
`find_windows_per_winter(daily, *, threshold_mwh, min_window_days)` receives one
threshold and applies it to every winter. Copying it onto every event row would
repeat one number N times and invite a reader to treat it as varying.

**Reason 2: the ETL CLI already reports it, once, at the right grain.**
`src/owr/etl/cli.py::_transform_result_json` puts `percentile` and `threshold_mwh` at
the top level of the JSON payload, beside `season`, `population_days`, `min_mwh`,
`median_mwh` and `max_mwh`. `_print_transform_text` prints the same two in the text
mode header. Nothing is missing from the ETL output.

**Reason 3: the frame is a separate contract.** `EVENT_FRAME_COLUMNS` feeds the ETL
CLI's JSON and text renderers and their tests. `StressWindow` feeds the engine, the
simulator CLI and the API. The two changed for different reasons on different dates,
and coupling them now would pull `tests/test_etl_cli_transform.py` into Change B for
no new information.

`src/owr/etl/transform.py` therefore has no code change in any phase. Phase 2 test
item 10 pins the object-level behaviour so the split stays visible.

Reopen this decision only when `find_windows_per_winter` learns to take more than one
threshold. At that point the value becomes per-row and belongs in the frame.

---

## Phase 1 — Change A: the percentile is doc-sourced

Goal: every surface that describes the 0.90 default names the source, and the
narrowed open question replaces the old note text.

### Files

| File | Change |
|---|---|
| `src/owr/config.py` | Module docstring carve-out; split the attribute entry in two. |
| `src/owr/cli.py` | `_OPEN_QUESTIONS_STATIC` note; two flag help strings; two render blocks. |
| `src/owr/api/schemas.py` | One source comment above `severity_percentile`. |
| `db/migrations/001_init.sql` | Line 106 trailing comment. |
| `tests/test_config.py` | One docstring update. |
| `tests/test_cli.py` | Three new tests. |
| `CLAUDE.md` | The `config.py` row. |
| `docs/PLAN_SIMULATOR_CLI.md` | One line appended to the existing supersession note. |

### 1.1 `src/owr/config.py`, module docstring

Append this paragraph after the existing one:

```
**One exception, as of 2026-08-05: ``default_severity_percentile``.** The
Architecture export of that date fixes the 90th percentile in Component 3, so that
field is sourced and the rule above does not apply to it. It stays in this class
because ``stress_finder`` takes it as a parameter and a scenario may still override
it. Its attribute entry below carries the source quote.
```

### 1.2 `src/owr/config.py`, attribute block

Replace the single `default_severity_percentile / default_min_stress_window_days`
entry (lines 56 to 65) with these two entries, verbatim:

```
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
```

No field, default or validation changes. `default_severity_percentile: float = 0.90`
stays exactly as it is.

### 1.3 `src/owr/cli.py`, the open-question note

Replace the `"note"` value of `_OPEN_QUESTIONS_STATIC["stress_event_definition"]`
(lines 65 to 73) with this, verbatim. Keep the id, `"flags"` and `"handoff_ref"`
unchanged (D1):

```python
        "note": (
            "Rule and percentile are doc-sourced as of the 2026-08-05 "
            "Architecture export, Component 3: 'Determine: 90th historical "
            "daily load percentile. A stress event begins when: daily_load >= "
            "90th percentile for minimum_window consecutive days.' Report B's "
            "12-hour rule is retired. Still open: the threshold value in MWh on "
            "real data. Both published numbers (3,504 and 16,750 MWh) are "
            "hourly-basis and do not carry over to a daily-basis rule, so a "
            "fresh p90 must be computed on daily sums. The source gives "
            "minimum_window no value, so 2 stays a team choice."
        ),
```

### 1.4 `src/owr/cli.py`, the two flag help strings

`--severity-percentile` (lines 216 to 219):

```python
        help=(
            f"stress-day percentile threshold (default {cfg.default_severity_percentile}, "
            "sourced: Architecture 2026-08-05 Component 3) [OPEN: stress_event_definition]"
        ),
```

`--min-stress-window-days` (lines 225 to 228):

```python
        help=(
            f"minimum consecutive stressed days forming an event "
            f"(default {cfg.default_min_stress_window_days}, team choice; the source names "
            "minimum_window and gives no value) [OPEN: stress_event_definition]"
        ),
```

### 1.5 `src/owr/cli.py`, `_render_list_windows` text mode

After the existing `out.write(...)` at lines 687 to 690, and before the
`if not windows:` branch, add one line:

```python
    out.write(
        "  source: Architecture 2026-08-05 Component 3. The percentile is sourced; "
        "the minimum_window value is a team choice.\n"
    )
```

### 1.6 `src/owr/cli.py`, `_render_table` stress block

After the `rule:` line (lines 750 to 753), add the same source line:

```python
    out.write(
        "  source: Architecture 2026-08-05 Component 3. The percentile is sourced; "
        "the minimum_window value is a team choice.\n"
    )
```

### 1.7 `src/owr/api/schemas.py`

Above `severity_percentile` on line 33, add:

```python
    # 0.90 is sourced: Architecture 2026-08-05 Component 3, "90th historical daily
    # load percentile". min_stress_window_days is the source's minimum_window, which
    # the source leaves without a value; 2 is a team choice.
```

Do not change the field or its default.
`tests/test_config.py::test_config_defaults_match_scenario_create_defaults` is a
drift guard between this file and `config.py`.

### 1.8 `db/migrations/001_init.sql` line 106

Change the trailing comment `-- e.g. 0.90` to
`-- 0.90, Architecture 2026-08-05 Component 3`. Comment only, no schema change.

### 1.9 Test inventory, Phase 1

Update in `tests/test_config.py`:

1. `test_default_severity_percentile_is_0_90` — extend the docstring to name the
   2026-08-05 export as the source. Keep both assertions unchanged.

Add to `tests/test_cli.py`:

2. `test_stress_event_note_names_the_source` — run `_report([])`, find the
   `stress_event_definition` entry in `report["open_questions"]`, assert
   `"90th historical daily load percentile"` and `"minimum_window"` are in its
   `note`, and assert `"12+ hours above threshold within a day"` is not.
3. `test_list_windows_text_names_the_source` — run
   `cli.main(["--input", EXAMPLE, "--list-windows"])`, assert
   `"Architecture 2026-08-05 Component 3"` in stdout and
   `"[OPEN: stress_event_definition]"` still in stdout.
4. `test_table_stress_block_names_the_source` — full run, assert the same source
   string in stdout.

Must still pass unchanged:
`tests/test_cli.py::test_table_output_contains_summary_labels_and_open_markers`
(guards the `[OPEN: stress_event_definition]` marker, D1) and
`tests/test_cli.py::test_build_parser_defaults_match_default_config`.

### 1.10 Docs, Phase 1

`CLAUDE.md`, the `src/owr/config.py` row. Replace the last sentence
"Every value is a team choice, not a sourced fact." with:
"Every value is a team choice, not a sourced fact, except
`default_severity_percentile`, sourced 2026-08-05."

`docs/PLAN_SIMULATOR_CLI.md`, after the existing supersession note at line 494, add
one line: "Superseded again 2026-08-05: the 0.90 percentile is doc-sourced. See
`docs/PLAN_ARCH_0805_SYNC.md` Change A."

### 1.11 Verify and commit Phase 1

```
uv run pytest -q
uv run ruff check .
uv run simulate --input examples/synthetic_winter_stress.csv --list-windows
```

The last command must print the source line under the header. Commit before Phase 2
starts. Suggested message: `Change A: the 0.90 severity percentile is doc-sourced`.

---

## Phase 2 — Change B, engine core: the value object and the finder

Goal: `StressWindow` carries the Component 3 output fields. The engine core stays
pure and keeps to `pandas` and `numpy`.

### Files

| File | Change |
|---|---|
| `src/owr/models.py` | `StressWindow` fields, properties, validation; new `HourlyLoadLike`. |
| `src/owr/stress_finder.py` | Stamp threshold and percentile; new `with_peak_hourly_load`. |
| `tests/test_stress_finder.py` | One update, eight new tests. |
| `tests/test_etl_transform.py` | One new test. |

`src/owr/etl/transform.py` is deliberately absent from this list. See D9.

### 2.1 `src/owr/models.py`, `StressWindow`

Replace the class (lines 87 to 93) with this, verbatim:

```python
@dataclass(frozen=True)
class StressWindow:
    """A run of consecutive stressed days found by ``stress_finder``.

    Implements the Component 3 output table of
    ``docs/source/2026-08-05_Software_Architecture_Documentation.md``. That table
    names four fields whose Description cell is still ``@``: ``first_hour_index``
    (hour), ``last_hour_index`` (hour), ``peak_hourly_load`` ("MW?") and
    ``load_percentile_threshold`` (Percentile). The readings below are documented
    choices, not sourced facts. OPEN team question (stress_window_output_fields):
    see docs/PLAN_ARCH_0805_SYNC.md decisions D4 to D7.

    start / end / days
        Inclusive calendar bounds and the day count. These carry the source's
        ``event_start_date``, ``event_end_date`` and ``event_duration``.

    threshold_mwh / severity_percentile
        The two halves of the source's single ``load_percentile_threshold`` field.
        The Unit cell reads "Percentile", which points at ``severity_percentile``
        (the fraction, 0.90 by default). The field name points at the MWh cut value
        applied to the day totals. This repo already models both, as
        ``owr.etl.transform.ThresholdResult.percentile`` and ``.threshold_mwh``, so
        both travel with the window. ``threshold_mwh`` is set on every detection
        path. ``severity_percentile`` is ``None`` when the caller supplied a
        threshold directly and never named a percentile, which is the ETL path.

    peak_hourly_load_mw
        The highest single-hour gross load over every hour of every day in the
        window, in MW. ``None`` until ``stress_finder.with_peak_hourly_load``
        attaches it, because detection runs on ``DailyLoadLike``, which carries a
        daily total and no hourly series. The source Unit cell reads "MW?". At
        one-hour resolution the peak hour's energy in MWh is the same number as its
        average power in MW, so the open part is which label the team wants, not
        which value.
    """

    start: date
    end: date
    days: int
    threshold_mwh: float | None = None
    severity_percentile: float | None = None
    peak_hourly_load_mw: float | None = None

    def __post_init__(self) -> None:
        if self.severity_percentile is not None and not 0.0 <= self.severity_percentile <= 1.0:
            raise ValueError("severity_percentile must be in [0, 1]")
        if self.peak_hourly_load_mw is not None and self.peak_hourly_load_mw < 0:
            raise ValueError("peak_hourly_load_mw must be non-negative")

    @property
    def first_hour_index(self) -> int:
        """Source Component 3 ``first_hour_index`` (Unit: hour). Always 0.

        The settled rule is daily: "daily_load >= 90th percentile for
        minimum_window consecutive days". An event therefore starts at the first
        hour of its start date, and no sub-day start hour exists to report.

        The index is event-local. An absolute index would need an origin for the
        hour axis, and no detection path has a stable one: the ETL path allows
        gaps, and the simulator CLI path would count from whichever file the
        operator passed. See docs/PLAN_ARCH_0805_SYNC.md decision D4, which also
        records the mixed source evidence.
        """
        return 0

    @property
    def last_hour_index(self) -> int:
        """Source Component 3 ``last_hour_index`` (Unit: hour).

        ``HOURS_PER_DAY * days - 1``: the last hour of the end date on the same
        event-local axis. Both indices are a pure function of ``days`` under the
        daily rule, so they are properties and never stored. A stored copy could
        drift, and a persisted copy would need a migration to change.
        """
        return HOURS_PER_DAY * self.days - 1
```

Validation is deliberately narrow. It covers the new optional fields only. It does
not add a `days >= 1` check, because that would change behaviour existing tests rely
on and Change B does not need it.

### 2.2 `src/owr/models.py`, `HourlyLoadLike`

Add directly after `DailyLoadLike` (after line 105):

```python
class HourlyLoadLike(Protocol):
    """What ``stress_finder.with_peak_hourly_load`` needs: a date and the day's
    hourly loads in MW.

    ``DayProfile`` satisfies this structurally. ``owr.etl.daily.DailyLoad`` does
    not, and must not: the ETL path reduces interval readings to a daily total
    before window detection runs, so no hourly series survives that far. That is
    why this protocol is separate from ``DailyLoadLike`` instead of an extension of
    it. Not marked ``runtime_checkable``, for the same reason ``DailyLoadLike`` is
    not.
    """

    date: date
    hourly_load_mw: tuple[float, ...]
```

### 2.3 `src/owr/stress_finder.py`, stamp the threshold and the percentile

Change the signature of `find_stress_windows_at_threshold`:

```python
def find_stress_windows_at_threshold(
    days: Sequence[DailyLoadLike],
    threshold: float,
    min_window_days: int,
    *,
    severity_percentile: float | None = None,
) -> list[StressWindow]:
```

Add this paragraph to its docstring:

```
    ``severity_percentile`` is recorded on every window this call emits and is
    never used to compute anything. Callers that derived ``threshold`` from a
    percentile pass it so the window can report both halves of the source's
    ``load_percentile_threshold`` field. Callers that chose a threshold directly
    leave it ``None``.
```

Delete the module-level `_emit` helper (lines 89 to 100) and replace it with a
closure inside `find_stress_windows_at_threshold`, defined after `windows` and
`run_start`:

```python
    def emit(run_start: int, run_end: int) -> None:
        length = run_end - run_start + 1
        if length >= min_window_days:
            windows.append(
                StressWindow(
                    start=days[run_start].date,
                    end=days[run_end].date,
                    days=length,
                    threshold_mwh=threshold,
                    severity_percentile=severity_percentile,
                )
            )
```

Change the three call sites from `_emit(windows, days, run_start, i - 1, min_window_days)`
to `emit(run_start, i - 1)`, and the trailing one to `emit(run_start, len(days) - 1)`.
The closure keeps every call site inside 100 columns. Nothing outside this module
imports `_emit`.

In `find_stress_windows`, pass the percentile through:

```python
    return find_stress_windows_at_threshold(
        days, threshold, min_window_days, severity_percentile=severity_percentile
    )
```

### 2.4 `src/owr/stress_finder.py`, `with_peak_hourly_load`

Add `from dataclasses import replace` and `HourlyLoadLike` to the imports. Append
this function at the end of the module:

```python
def with_peak_hourly_load(
    windows: Sequence[StressWindow],
    days: Sequence[HourlyLoadLike],
) -> list[StressWindow]:
    """Return copies of ``windows`` with ``peak_hourly_load_mw`` filled in.

    Implements the Component 3 ``peak_hourly_load`` output field (Unit "MW?",
    Description "@") of
    ``docs/source/2026-08-05_Software_Architecture_Documentation.md``. The value is
    the maximum hourly load in MW over every hour of every day from ``start`` to
    ``end`` inclusive.

    A separate function, and not part of ``find_stress_windows``: detection takes
    ``DailyLoadLike``, which has no hourly series, and widening that protocol would
    break the ETL path, whose points are daily totals. A caller that holds
    ``DayProfile`` objects calls this straight after detection. A caller that does
    not leaves the field ``None``.

    Never mutates its input. The Architecture doc's Global Interface Contract says
    a component shall never modify another component's output.

    Raises ``ValueError`` when a window covers a date absent from ``days``, or a
    date whose hourly series is empty.
    """
    by_date = {d.date: tuple(d.hourly_load_mw) for d in days}
    out: list[StressWindow] = []
    for w in windows:
        peak: float | None = None
        day = w.start
        while day <= w.end:
            hours = by_date.get(day)
            if hours is None:
                raise ValueError(
                    f"window {w.start} .. {w.end} covers a date absent from days: {day}"
                )
            if not hours:
                raise ValueError(f"date {day} carries an empty hourly load series")
            day_peak = max(hours)
            peak = day_peak if peak is None else max(peak, day_peak)
            day += timedelta(days=1)
        out.append(replace(w, peak_hourly_load_mw=peak))
    return out
```

Do not export `with_peak_hourly_load` from `src/owr/__init__.py`.
`find_stress_windows` is not exported either, and the package surface stays as it is.

### 2.5 Test inventory, Phase 2

Update in `tests/test_stress_finder.py`:

1. `test_threshold_split_reproduces_find_stress_windows` — **this test breaks
   without the update**. `StressWindow` equality now covers `severity_percentile`,
   and the two paths disagree on it. Pass `severity_percentile=0.9` to the
   `find_stress_windows_at_threshold` call. The test then proves the two paths agree
   on all six fields, which is stronger than before. Add a second block that omits
   the keyword and asserts the windows differ on `severity_percentile` only, with
   `threshold_mwh` still equal.

Add to `tests/test_stress_finder.py`:

2. `test_windows_carry_the_threshold_and_percentile` — after `find_stress_windows`
   the window's `severity_percentile == 0.9` and `threshold_mwh ==
   percentile_threshold([d.load_mwh for d in days], 0.9)`.
3. `test_threshold_variant_leaves_percentile_none` — a direct
   `find_stress_windows_at_threshold` call gives `severity_percentile is None` and
   `threshold_mwh == threshold`.
4. `test_hour_indices_are_event_local` — `first_hour_index == 0` and
   `last_hour_index == HOURS_PER_DAY * w.days - 1` on a 3-day window, so
   `last_hour_index == 71`.
5. `test_peak_hourly_load_is_none_before_enrichment`.
6. `test_with_peak_hourly_load_takes_the_max_over_the_window` — build day profiles
   whose highest hour sits inside the window and whose second highest sits outside
   it. Assert the result equals the inside value. Use a non-flat hourly profile, so
   the test cannot pass by reading `load_mwh / 24`.
7. `test_with_peak_hourly_load_raises_on_a_missing_date` — `pytest.raises(ValueError,
   match="absent from days")`.
8. `test_with_peak_hourly_load_does_not_mutate_its_input` — the input windows still
   have `peak_hourly_load_mw is None` after the call, and the returned objects are
   different objects.
9. `test_stress_window_rejects_invalid_optional_fields` — `severity_percentile=1.5`
   raises, and `peak_hourly_load_mw=-1.0` raises.

Add to `tests/test_etl_transform.py`:

10. `test_etl_path_leaves_severity_percentile_none` — call
    `find_stress_windows_at_threshold(days, threshold=400_000.0, min_window_days=2)`
    exactly as `find_windows_per_winter` does. Assert `severity_percentile is None`,
    `threshold_mwh == 400_000.0` and `peak_hourly_load_mw is None`. Reference D9 in
    the test docstring: this pins the split between the `StressWindow` object and
    the ETL event frame, so a later refactor cannot close it by accident.

`src/owr/etl/transform.py` needs no change (D9). `find_windows_per_winter` calls
`find_stress_windows_at_threshold` with three positional arguments, and the new
parameter is keyword-only with a default. The function reads `.start`, `.end` and
`.days` only, and `EVENT_FRAME_COLUMNS` stays at four columns.

### 2.6 Verify and commit Phase 2

```
uv run pytest tests/test_stress_finder.py tests/test_etl_transform.py -q
uv run pytest -q
uv run ruff check .
```

Suggested message: `Change B phase 1: Component 3 output fields on StressWindow`.

---

## Phase 3 — Change B, simulator CLI

Goal: both CLI window surfaces carry the new fields, and the new open question
appears in the report.

### Files

| File | Change |
|---|---|
| `src/owr/cli.py` | Call `with_peak_hourly_load`; one `_window_json` helper; new open question; two render blocks. |
| `tests/test_cli.py` | Five new tests. |

### 3.1 Call the enrichment

In `_run`, after line 350:

```python
    windows = find_stress_windows(days, args.severity_percentile, args.min_stress_window_days)
    windows = with_peak_hourly_load(windows, days)
```

Add `with_peak_hourly_load` to the `owr.stress_finder` import on line 42. `days` are
`DayProfile` objects and satisfy `HourlyLoadLike`. Both the `--list-windows` path
and the report path read `windows` after this point, so one call covers both.

### 3.2 One shared serializer for the two JSON sites

`_build_report` (lines 624 to 627) and `_render_list_windows` JSON mode (lines 678 to
681) both build window dicts by hand today. Both hold `StressWindow` objects.
Replace both with one module-level helper, so the two can never drift:

```python
def _window_json(w: StressWindow) -> dict:
    """One JSON shape for a stress window, shared by the report and by
    ``--list-windows``. Carries the Component 3 output fields; the two hour indices
    are read from ``StressWindow`` properties and are never stored on the object.
    """
    return {
        "start": w.start.isoformat(),
        "end": w.end.isoformat(),
        "days": w.days,
        "first_hour_index": w.first_hour_index,
        "last_hour_index": w.last_hour_index,
        "peak_hourly_load_mw": w.peak_hourly_load_mw,
        "threshold_mwh": w.threshold_mwh,
        "severity_percentile": w.severity_percentile,
    }
```

Both call sites become `[_window_json(w) for w in windows]`. Import `StressWindow`
from `owr.models` for the annotation; `cli.py` already imports `DayProfile` and
`StorageAsset` from that module. The top-level report keys do not change, so
`tests/test_cli.py::test_json_output_is_clean_stdout_with_all_top_level_keys` stays
green.

### 3.3 The new open question

Add to `_OPEN_QUESTIONS_STATIC`, directly after `stress_event_definition`:

```python
    "stress_window_output_fields": {
        "flags": [],
        "note": (
            "Component 3 names four output fields whose description cell is @: "
            "first_hour_index, last_hour_index, peak_hourly_load (unit 'MW?') "
            "and load_percentile_threshold. Implemented readings: the two hour "
            "indices are event-local and run 0 to 24*days-1, so under the daily "
            "rule they are a pure function of the duration; peak_hourly_load is "
            "the highest single-hour gross load in MW across the window; "
            "load_percentile_threshold travels as both the percentile and the "
            "MWh cut value, because the unit cell and the field name disagree."
        ),
        "handoff_ref": "docs/PLAN_ARCH_0805_SYNC.md decisions D4 to D7",
    },
```

Add the matching entry to the `open_questions` list in `_build_report`, directly
after the `stress_event_definition` entry:

```python
        {
            "id": "stress_window_output_fields",
            "flags": _OPEN_QUESTIONS_STATIC["stress_window_output_fields"]["flags"],
            "value_used": "hours 0..24*days-1; peak in MW; threshold as percentile and MWh",
            "note": _OPEN_QUESTIONS_STATIC["stress_window_output_fields"]["note"],
            "handoff_ref": _OPEN_QUESTIONS_STATIC["stress_window_output_fields"][
                "handoff_ref"
            ],
        },
```

### 3.4 Render the fields — two sites, two access styles

**The two render sites do not take the same input.** `_render_table` reads
`report["stress_windows"]`, a list of dicts. `_render_list_windows` text mode
iterates `windows`, a list of `StressWindow` objects, with attribute access. Use the
matching style at each site. A dict subscript at the second site raises `TypeError`.

**Site 1, `_render_table`.** After the Phase 1 `source:` line, add one field line,
then replace the window row loop:

```python
    out.write(
        "  fields: hour indices are event-local; peak is the highest single hour, MW"
        "   [OPEN: stress_window_output_fields]\n"
    )
    for i, w in enumerate(report["stress_windows"], 1):
        peak = w["peak_hourly_load_mw"]
        peak_str = f"{peak:,.0f} MW" if peak is not None else "-"
        out.write(
            f"  {i}   {w['start']} .. {w['end']}   {w['days']} days   "
            f"hours {w['first_hour_index']}..{w['last_hour_index']}   peak {peak_str}\n"
        )
```

**Site 2, `_render_list_windows` text mode.** Add the same field line after the
Phase 1 `source:` line, keep the `if not windows:` branch as it is, then replace the
loop with the attribute-access form:

```python
    out.write(
        "  fields: hour indices are event-local; peak is the highest single hour, MW"
        "   [OPEN: stress_window_output_fields]\n"
    )
    if not windows:
        out.write("  none\n")
    for i, w in enumerate(windows, 1):
        peak = w.peak_hourly_load_mw
        peak_str = f"{peak:,.0f} MW" if peak is not None else "-"
        out.write(
            f"  {i}   {w.start.isoformat()} .. {w.end.isoformat()}   {w.days} days   "
            f"hours {w.first_hour_index}..{w.last_hour_index}   peak {peak_str}\n"
        )
```

The `-` fallback for a missing peak follows the `recharge_sufficiency_ratio`
precedent in the daily table. On the CLI path the peak is never `None`, because
step 3.1 always runs, but `_render_table` reads from `report` only and the repo's
doctored-report test pattern can hand it anything.

**Hard constraint, unchanged from `docs/PLAN_METRICS_COMPONENT7.md`:**
`_render_table` must read new values from `report` only.
`tests/test_cli.py::test_daily_table_columns_align_across_magnitudes` calls it with
`argparse.Namespace(name=None)`, so any new `args` attribute read breaks that test.
Do not add a column to the Daily results table.

### 3.5 Test inventory, Phase 3

Add to `tests/test_cli.py`:

1. `test_list_windows_json_carries_the_component3_fields` — run with
   `--list-windows --format json`. Assert the eight keys are present, that
   `first_hour_index == 0`, that `last_hour_index == 24 * days - 1`, that
   `severity_percentile == DEFAULT_CONFIG.default_severity_percentile`, and that
   `threshold_mwh > 0`.
2. `test_peak_hourly_load_matches_the_file` — read `EXAMPLE` with
   `read_day_profiles`, compute the max hourly load over 2026-01-09 to 2026-01-11
   independently, and assert equality with the reported `peak_hourly_load_mw`.
   Compute the expected value from the parsed days, never as a literal.
3. `test_report_and_list_windows_agree_on_window_fields` — the window dict from
   `_report([])["stress_windows"][0]` equals the one from the `--list-windows` JSON
   run, key for key.
4. `test_stress_window_output_fields_open_question_is_reported` — the id appears in
   `report["open_questions"]`, and `"[OPEN: stress_window_output_fields]"` appears
   in the table output.
5. `test_render_table_prints_dash_for_a_missing_peak` — take `report = _report([])`,
   set `report["stress_windows"][0]["peak_hourly_load_mw"] = None`, call
   `cli._render_table(report, argparse.Namespace(name=None), buf)`, assert
   `"peak -"` is in the output. This uses the doctored-report pattern that
   `test_daily_table_columns_align_across_magnitudes` already uses.

Test 3 also guards the site-1 and site-2 split from 3.4: both JSON paths go through
the same helper, so any drift shows up as a key mismatch.

Before writing these, grep `tests/` for any assertion on the **length** of
`open_questions` or on an exact window dict. The Phase 3 change adds one entry and
five keys. The audit at plan time found none, but confirm before you edit.

### 3.6 Verify and commit Phase 3

```
uv run pytest tests/test_cli.py -q
uv run pytest -q
uv run ruff check .
uv run simulate --input examples/synthetic_winter_stress.csv --list-windows
```

The last command exercises site 2 and must print
`1   2026-01-09 .. 2026-01-11   3 days   hours 0..71   peak <N> MW`.

Suggested message: `Change B phase 2: stress-window fields in the simulate CLI`.

---

## Phase 4 — Change B, API and persistence

Goal: the wire contract and the Postgres round trip carry the new fields, and the
round trip is covered by a test that needs no live database.

### Files

| File | Change |
|---|---|
| `src/owr/api/schemas.py` | `StressWindowOut` gains five fields. |
| `src/owr/api/app.py` | Call `with_peak_hourly_load`; one `_window_json` helper. |
| `src/owr/api/pg_store.py` | Two persisted-shape helpers. |
| `tests/test_api.py` | One new test. |
| `tests/test_pg_store.py` | Skip-marker refactor, two new tests. |

**Two shapes, two names.** The wire shape has eight keys and includes the two derived
hour indices. The persisted shape has six keys and excludes them. Name them apart, so
no reader assumes they interchange:

| Layer | Helper | Keys |
|---|---|---|
| `cli.py` | `_window_json` | 8, wire |
| `api/app.py` | `_window_json` | 8, wire |
| `api/pg_store.py` | `_persisted_window_json` / `_window_from_persisted` | 6, persisted |

### 4.1 `src/owr/api/schemas.py`

```python
class StressWindowOut(BaseModel):
    """Component 3 event row. ``first_hour_index`` and ``last_hour_index`` are
    derived from ``days`` on the engine side and are echoed here, never stored.
    The three optional fields are ``None`` when the detection path could not supply
    them. See docs/PLAN_ARCH_0805_SYNC.md decisions D4 to D7.
    """

    start: date
    end: date
    days: int
    first_hour_index: int
    last_hour_index: int
    peak_hourly_load_mw: float | None = None
    threshold_mwh: float | None = None
    severity_percentile: float | None = None
```

The change is additive, so existing clients keep working.

### 4.2 `src/owr/api/app.py`

In `create_run`, wrap the detection call:

```python
            run.stress_windows = with_peak_hourly_load(
                find_stress_windows(days, inp.severity_percentile, inp.min_stress_window_days),
                days,
            )
```

Add `with_peak_hourly_load` to the `owr.stress_finder` import.

Add a module-level helper next to `_severity_reduction`, and use it in both
`_annotation` and `get_stress_windows`, so the decision package and the endpoint
never disagree:

```python
def _window_json(w: StressWindow) -> dict:
    """The wire shape for one stress window across the API layer. Mirrors
    ``schemas.StressWindowOut`` and matches ``cli._window_json`` key for key. The
    persisted shape in ``pg_store`` is different and is named apart."""
    return {
        "start": w.start.isoformat(),
        "end": w.end.isoformat(),
        "days": w.days,
        "first_hour_index": w.first_hour_index,
        "last_hour_index": w.last_hour_index,
        "peak_hourly_load_mw": w.peak_hourly_load_mw,
        "threshold_mwh": w.threshold_mwh,
        "severity_percentile": w.severity_percentile,
    }
```

Add `StressWindow` to the `owr.models` import for the annotation. `_annotation` uses
`[_window_json(w) for w in run.stress_windows]`. `get_stress_windows` builds
`schemas.StressWindowOut(**_window_json(w))`. Pydantic parses the ISO date strings
back into `date`, which the existing `ScenarioOut` path already relies on.

### 4.3 `src/owr/api/pg_store.py`

Add two helpers and use them in `_summary_json` and `_load_windows`:

```python
def _persisted_window_json(w: StressWindow) -> dict:
    """The persisted shape for one stress window. **Not the wire shape**; the wire
    shape lives in ``api/app.py`` and carries two more keys.

    Stores the constructor fields only. ``first_hour_index`` and
    ``last_hour_index`` are ``StressWindow`` properties derived from ``days``, so a
    stored copy could go stale and would need a migration to change. They are
    recomputed on load instead.
    """
    return {
        "start": w.start.isoformat(),
        "end": w.end.isoformat(),
        "days": w.days,
        "threshold_mwh": w.threshold_mwh,
        "severity_percentile": w.severity_percentile,
        "peak_hourly_load_mw": w.peak_hourly_load_mw,
    }


def _window_from_persisted(row: dict) -> StressWindow:
    """Inverse of :func:`_persisted_window_json`. Uses ``.get`` for the three fields
    added 2026-08-05, so a row written before that date still loads, with ``None``
    in each."""
    return StressWindow(
        start=date.fromisoformat(row["start"]),
        end=date.fromisoformat(row["end"]),
        days=row["days"],
        threshold_mwh=row.get("threshold_mwh"),
        severity_percentile=row.get("severity_percentile"),
        peak_hourly_load_mw=row.get("peak_hourly_load_mw"),
    )
```

`_summary_json` uses `[_persisted_window_json(w) for w in run.stress_windows]`.
`_load_windows` uses
`[_window_from_persisted(w) for w in summary.get("stress_windows", [])]`.

No migration. Windows live inside the `result_summary` JSON column, not in a table.

### 4.4 Test inventory, Phase 4

Add to `tests/test_api.py`:

1. `test_stress_windows_endpoint_carries_component3_fields` — extend the existing
   flow. Assert the eight keys, `first_hour_index == 0`, `last_hour_index == 71`
   (the fixture builds 3 days), `severity_percentile == 0.5` (the value in
   `_scenario_body`), `threshold_mwh` is a number, and `peak_hourly_load_mw` equals
   the max hourly load in `_days()`.

`tests/test_pg_store.py`, refactor then add:

2. Replace the module-level `pytestmark` with a named decorator:
   ```python
   requires_db = pytest.mark.skipif(
       not _DSN, reason="set OWR_TEST_DATABASE_URL to a live Postgres to run PG store tests"
   )
   ```
   Apply `@requires_db` to the three tests that take the `dsn` fixture:
   `test_scenario_roundtrips_all_fields`, `test_run_persists_across_fresh_repository`
   and `test_failed_run_persists_failed_status`. The reason for the refactor: the
   default gate skips the whole module today, so a window round-trip bug would ship
   unseen.

   Two follow-on edits in the same file:
   - The `dsn` fixture body carries `assert _DSN is not None  # guarded by pytestmark`.
     That comment goes stale. Change it to `# guarded by @requires_db`.
   - Update the module docstring. It currently says the whole module skips without a
     database. It must say the two serializer tests run without one, and that the
     three integration tests still need `OWR_TEST_DATABASE_URL`.

   **The module-level `psycopg = pytest.importorskip("psycopg")` on line 15 stays and
   still gates the new tests.** They import `owr.api.pg_store`, which imports
   `psycopg` at module level, so the `importorskip` is what makes them runnable at
   all. `psycopg[binary]` is in the `dev` dependency group, so the import succeeds
   under `uv run pytest` and the new tests run. If a future environment drops that
   dev dependency, the whole module skips again, including the two new tests. That
   is the intended behaviour and it is why the `importorskip` stays.

3. `test_persisted_window_json_round_trips_every_field` — build a `StressWindow` with
   all three optional fields set, assert
   `_window_from_persisted(_persisted_window_json(w)) == w`, and assert the persisted
   dict has no `first_hour_index` key.
4. `test_window_from_persisted_accepts_a_pre_0805_row` — pass
   `{"start": "2026-01-09", "end": "2026-01-11", "days": 3}` and assert all three
   optional fields are `None` and `last_hour_index == 71`.

**Skip-count expectation.** The skipped count stays at 4 (3 Postgres, 1 viz). The
three Postgres tests keep skipping under `@requires_db`, and the viz skip is
untouched. Tests 3 and 4 were never in the skipped count, because they do not exist
yet, so the arithmetic is "4 before, 4 after, two more passes". The check to run:

```
uv run pytest tests/test_pg_store.py -v
```

Both new test names must report `PASSED`, not `SKIPPED`.

### 4.5 Verify and commit Phase 4

```
uv run pytest tests/test_api.py tests/test_pg_store.py -v
uv run pytest -q
uv run ruff check .
```

Suggested message: `Change B phase 3: stress-window fields in the API and the store`.

---

## Phase 5 — Docs

No code change, no test change.

1. `CLAUDE.md`, the `src/owr/stress_finder.py` row. Replace the cell with:
   "Finds runs of N consecutive days above a demand percentile. Also stamps the
   Component 3 output fields, and fills the hourly peak through
   `with_peak_hourly_load`."
2. `CLAUDE.md`, the `src/owr/models.py` row. Append: "`StressWindow` carries the
   Component 3 event row."
3. `docs/HANDOFF.md`, append a session entry: what landed in each phase, the test
   counts, and the two open questions the run now carries
   (`stress_event_definition`, narrowed; `stress_window_output_fields`, new). Name
   D9 as well, because the ETL event frame stayed put on purpose.
4. `docs/BOARD.md`, add one Done row that links this plan, with the date and the
   final pass and skip counts.
5. This file, add a Status line at the top: the date, the five commit hashes, and
   the final counts.

Verify with `uv run pytest -q` and `uv run ruff check .` one last time, then commit.
Suggested message: `Change B phase 4: docs for the 2026-08-05 architecture sync`.

---

## Risks

| # | Risk | Where it bites | Mitigation |
|---|---|---|---|
| R1 | `StressWindow` equality now covers three more fields | `tests/test_stress_finder.py::test_threshold_split_reproduces_find_stress_windows` fails | Step 2.5 item 1 updates it and makes it stronger |
| R2 | Postgres round trip drops the new fields, and the covering test is database-gated | Silent data loss on reload | Step 4.3 adds the two persisted-shape helpers; step 4.4 item 2 moves the skip marker so items 3 and 4 run in the default gate |
| R3 | `dataclasses.asdict` does not pick up properties | Any future `asdict(window)` loses the hour indices | Nothing calls `asdict` on a window today. All serializers are explicit, and steps 3.2, 4.2 and 4.3 reduce them to one per layer |
| R4 | New `_render_table` output breaks a column-alignment test | `test_daily_table_columns_align_across_magnitudes` | That test reads the Daily results table only. The stress block is above it and is not asserted on. Confirm with a targeted run first |
| R5 | Line length over 100 in the new docstrings, notes and render lines | `uv run ruff check .` fails | Run ruff after each file, not only at the phase gate |
| R6 | A test asserts the length of `open_questions` | Phase 3 adds one entry | Step 3.5 tells the implementer to grep first. The audit at plan time found no such assertion |
| R7 | The ETL path silently changes | `find_windows_per_winter` | The new parameter is keyword-only with a default, D9 keeps the frame at four columns, and step 2.5 item 10 pins the behaviour |
| R8 | The two render sites take different input types | `_render_list_windows` text mode raises `TypeError` on a dict subscript | Step 3.4 gives both variants explicitly. Step 3.6 runs the `--list-windows` command, which is the only exercise of site 2 |

## Assumptions

1. **`first_hour_index` and `last_hour_index` are event-local.** The source evidence
   is mixed and D4 records both readings. The decision rests on computability: no
   detection path carries a stable origin for an absolute hour axis.

   **Reversal is a migration, not a two-line change.** If the team answers
   "absolute", all of this moves:
   - The two properties become stored or enriched fields, because they stop being a
     function of `days`.
   - `stress_finder` needs a series origin it does not have today, and the ETL path
     with gaps has no well-defined answer at all. That sub-question must be settled
     first.
   - `pg_store` must persist both indices, so `_persisted_window_json` and
     `_window_from_persisted` both change.
   - `test_persisted_window_json_round_trips_every_field` inverts: it currently
     asserts the persisted dict has **no** `first_hour_index` key.
   - Rows written before the flip **cannot be backfilled**. The origin they were
     computed against is not stored anywhere.

   The property design still stands. It is the cheapest correct implementation of the
   reading this plan ships, and a stored field today would persist a number the repo
   cannot defend either.

2. `peak_hourly_load` covers gross load, not net load after dispatch. Detection runs
   before dispatch, so gross is the only value available at that point.
3. The team fills all four `@` cells together, which is why they share one open
   question id.
4. No frontend consumes `StressWindowOut` yet, so the additive field change breaks
   nothing downstream.

## Out of scope

- The Component 5 dispatch rule conflict (`OR` against `+`), recorded in
  `docs/FINDINGS_SOURCE_DOCS_2026-08-05.md` section 2.
- The Capacity Margin Deficit Reduction formula conflict, recorded in the same file,
  section 3.
- `event_id` and `winter_id` hash identifiers. `etl/transform.py` already records
  why this repo keeps a readable `winter_label` instead.
- `EVENT_FRAME_COLUMNS` in `src/owr/etl/transform.py`. See D9.
- Any change to `src/owr/sweep.py` or `src/owr/sweep_cli.py`. See D3.

---

Start here:

```
uv run pytest -q && uv run ruff check .
```

Then open `src/owr/config.py` and apply section 1.1.
