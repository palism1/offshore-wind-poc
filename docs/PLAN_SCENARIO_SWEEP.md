# PLAN — Scenario sweep chart

Date: 2026-08-05
Revision: 2 (adversarial review applied; see section 10)
Branch: `scenario-sweep`, cut from `main` at `219a55a`
Deadline: Friday 2026-08-07. The demo works without this. Cut scope rather than ship red.
Baseline on this branch: 505 passed, 4 skipped, `ruff check .` clean.

## 1. What this builds

A second console script, `sweep`, that runs the engine once per storage size and renders
severity reduction against storage size as a Matplotlib chart.

```
sweep --input <day-profile CSV> --power-mw 4320 --chart out.png
```

Three new modules:

| Module | Layer | Owns |
|---|---|---|
| `src/owr/sweep.py` | engine core (pure) | Sizes in, metrics out. One `simulate` call per size. |
| `src/owr/sweep_cli.py` | CLI | The `sweep` console script. File input, stdout, file output. |
| `src/owr/sweep_chart.py` | CLI | Matplotlib rendering of a sweep frame. Lazy import. |

## 2. Scope

**In scope.** A size ladder over one input file. A two-panel chart: severity reduction
percent on top, energy discharged on the bottom. A text or JSON table on stdout. An
optional data CSV. Provenance stamped on the chart, on stdout and on the data CSV.

**Out of scope, with the reason for each.**

| Cut | Reason |
|---|---|
| Fuel-fired generation offset series | `metrics.fuel_fired_generation_offset_mwh` needs hourly oil, gas and wind. The day-profile CSV carries `date, hour, load_mw, wind_mw, demand_percentile, wind_forecast_frac` only. No oil or gas column exists in any input the reader accepts. Unblocked by `docs/PLAN_SCENARIO_PROFILE_FORMAT.md`. |
| `--window N` window selection | The sweep always simulates every day in the file. Both example files hold exactly one event. Window selection would fork the span-slice logic in `cli._run`, which is the golden demo path. |
| `--start-soc-mwh` and `--start-soc-frac` | An absolute start state of charge is undefined across varying capacity. Every sweep point starts full, which is what the `simulate` CLI default does at each size. A start fraction would turn the sweep into a two-variable experiment. |
| `--lead-days` and pre-event charging | Dead code without a start-state-of-charge input. `soc_engine.clamp_charge` returns 0.0 at zero headroom, so `initial_soc.charge_from_wind` from a full asset returns the same value it was given. A lead-day flag would only trim days off the front of the span while its help text promised charging. See revision-log entry B1. |
| `--energy-budget-fraction`, `--priority-demand-weight`, `--priority-wind-weight` | Three more flags, three more parser tests, and no change to the shape of the curve. The sweep uses the `Config` defaults for all three. Section 4.3 rule 4 states the equivalence limit this creates. |
| A second sweep axis (efficiency, power, percentile) | One variable per chart. A second axis needs a heat map and a new chart type. |
| `--available-capacity-mw`, `--cycles-per-year`, `--name` | Reporting extras on the single-run CLI. They add flags and tests and change no curve. |
| PNG byte reproducibility | The footer carries a generation timestamp by design. Determinism is claimed for the sweep frame, not for the image file. |

**The cut line for Friday.** Phases 0, 1 and 2 give a working `sweep` command with a
table and a `--data-out` CSV. If phase 3 cannot land, plot the CSV in a spreadsheet and
ship the rest. Do not leave a half-wired `--chart` flag on the parser.

## 3. Decisions, with justification

### D1. A separate console script, not a subcommand on `simulate`

`owr/cli.py::build_parser` has no subparsers. Every flag hangs off the root parser and
`main` dispatches through `parser.set_defaults(func=cmd_run)`.

An optional subparser could keep `simulate --input ...` alive, because argparse does not
require a subcommand unless the caller asks for it. That path is possible and it is not
what this plan takes. It puts root-level flags and a subcommand in one grammar, where flag
placement decides which parser consumes an argument, and it edits the module that carries
the demo command in `README.md`, in `docs/HANDOFF.md` and in about 40 tests in
`tests/test_cli.py`. A `--sweep-sizes` flag set inside `cmd_run` has the same drawback in a
different form: two output shapes behind one code path and one `--format` flag.

A second script mirrors the layout the repository already has, `simulate` and `etl`, and
touches zero lines of `cli.py`. That is the lower risk before a hard deadline.

Name: `sweep`. `[project.scripts] sweep = "owr.sweep_cli:main"`.

### D2. Fixed power is the default power rule

`PowerRule.FIXED` holds `--power-mw` constant at every size. `PowerRule.FIXED_DURATION`
sets `power_mw = size_mwh / duration_hours`.

Fixed is the default for three reasons. It reproduces the two reference points already
recorded in `docs/HANDOFF.md` exactly, so the chart cross-checks against known numbers.
It makes the sweep a true one-variable sweep, which is what "severity reduction against
storage size" states. It needs no new physical assumption, where a duration default would
need a number the team has not settled. `docs/HANDOFF.md` carries two competing durations
for one sphere, about 4.5 hours and about 13.9 hours at the demo pair 60,000 MWh over
4,320 MW.

Fixed duration stays available behind `--power-rule fixed_duration --duration-hours H`.
It is the physically-scaled reading: a larger fleet carries more energy and more power.
The chart subtitle names the rule in use, so no reader can mistake one for the other.

### D3. The two new defaults go in `config.py`

`docs/PLAN_SIMULATOR_CLI.md` section "Where each default lives" states the rule: a value
belongs in `owr.config.Config` when an engine function or value object takes it as a
parameter. `sweep.SweepSpec` is an engine-core value object and takes both the size ladder
and the power rule. `Config` already carries three parked fields no code path reads
(`est_transmission_cost_per_mile_usd` and its two companions), on the argument that the
`metrics` functions take them as parameters.

Both fields act at the parser boundary only. `sweep_cli.build_parser` reads them once, at
parser-build time, exactly as `cli.build_parser` reads `cfg.default_efficiency`. Section 4.3
rule 10 states this, and `SweepSpec` carries no class-level default that could bind
`DEFAULT_CONFIG` at import time.

The counter-argument is real and is recorded in section 9 as an open question: a size
ladder is a chart default, and `cli.DEFAULT_CYCLES_PER_YEAR` is the precedent for a
labeled module constant instead.

### D4. `sweep.py` is engine core; nothing in the core imports Matplotlib

`sweep.py` takes `DayProfile` objects and numbers, calls `simulator.simulate` and
`metrics`, and returns dataclasses plus a `pandas.DataFrame`. It does no file access, no
network access and no database access. Its third-party imports are `pandas` only. It
qualifies under the two-library allowlist in the repo map.

`sweep_chart.py` imports Matplotlib inside the render function, not at module scope. Two
consequences. `sweep_cli.py` imports `sweep_chart` unconditionally and costs nothing when
Matplotlib is absent. A missing dependency raises at call time with an install hint.

A guard test in `tests/test_sweep.py` reads the source of every engine-core module and
asserts that none contains `matplotlib`, `sweep_chart` or `owr.cli`.

### D5. Matplotlib is an optional extra, `viz`, and CI installs it

`pyproject.toml` gains `viz = ["matplotlib>=3.9"]`. `.github/workflows/ci.yml` gains
`--extra viz` on the sync line, so the render tests run in CI rather than skip there.

Every render test calls `pytest.importorskip("matplotlib")` at function level, so
`uv run pytest` stays green in an environment without the extra. Matplotlib does not enter
the base `dependencies` list: the engine, the API and the ETL all run without it.

### D6. Severity reduction comes from `metrics.severity_reduction`

`sweep.py` is engine core, so it calls the engine-core metric rather than copying
`cli._severity_reduction`. The two differ at one input: `metrics.severity_reduction` raises
`ValueError` when `baseline_peak_mw <= 0`, where `cli._severity_reduction` returns `0.0`.
A day-profile file whose every load value is zero therefore exits 2 under `sweep` and
prints `0.0%` under `simulate`. Document the divergence in the `run_sweep` docstring. Both
example files carry a positive baseline peak.

## 4. Interfaces

### 4.1 `src/owr/models.py` (addition)

```python
class PowerRule(StrEnum):
    """How a sweep sets storage power at each energy size. OPEN team question
    (sweep_power_scaling): see docs/PLAN_SCENARIO_SWEEP.md section 3, decision D2.

    ``StrEnum``, not a plain ``Enum``, for the same reason ``WrapConvention`` is one:
    ``Config`` carries it and ``cli.py`` does ``json.dumps(asdict(cfg))``.
    """

    FIXED = "fixed"                    # power_mw is the same at every size
    FIXED_DURATION = "fixed_duration"  # power_mw = size_mwh / duration_hours
```

### 4.2 `src/owr/config.py` (additions to `Config`)

```python
default_sweep_sizes_mwh: tuple[float, ...] = (
    5000.0, 10000.0, 20000.0, 40000.0, 60000.0, 80000.0, 100000.0,
)
default_sweep_power_rule: PowerRule = PowerRule.FIXED
```

`__post_init__` additions:

- `default_sweep_sizes_mwh` must not be empty.
- every element must be finite and greater than zero (`math.isfinite`; add `import math`).
- the elements must be strictly increasing, which rejects both duplicates and an unsorted
  ladder.

Docstring entries, in the style of the fields already there:

- `default_sweep_sizes_mwh`. OPEN team question (`sweep_size_ladder`). The seven sizes
  bracket Report A's 40,000 to 60,000 MWh system reserve target and the 60,000 MWh demo
  point. `docs/FACT_CHECK_REPORT.md` records that the 40,000 to 60,000 MWh target does not
  reproduce from its own inputs, so the ladder moves when that number moves. Read at
  parser-build time by `sweep_cli.build_parser`; no engine function reads it at run time.
- `default_sweep_power_rule`. OPEN team question (`sweep_power_scaling`). Fixed power
  isolates the energy variable and reproduces the recorded reference points. Fixed duration
  is the fleet-scaled reading. See decision D2. Read at parser-build time only, as above.

### 4.3 `src/owr/sweep.py`

```python
SWEEP_FRAME_COLUMNS: tuple[str, ...] = (
    "storage_mwh", "power_mw", "duration_hours", "severity_reduction",
    "baseline_peak_mw", "reserve_peak_mw", "energy_discharged_mwh",
    "energy_charged_mwh", "final_soc_mwh", "equivalent_full_cycles",
)


@dataclass(frozen=True)
class SweepSpec:
    sizes_mwh: tuple[float, ...]
    power_rule: PowerRule
    efficiency: float
    soc_floor_frac: float
    strategic_reserve_frac: float
    power_mw: float | None = None
    duration_hours: float | None = None

    def __post_init__(self) -> None: ...
    def power_for(self, size_mwh: float) -> float: ...
    def duration_for(self, size_mwh: float) -> float: ...
    def asset_for(self, size_mwh: float) -> StorageAsset: ...


@dataclass(frozen=True)
class SweepPoint:
    storage_mwh: float
    power_mw: float
    duration_hours: float
    severity_reduction: float
    baseline_peak_mw: float
    reserve_peak_mw: float
    energy_discharged_mwh: float
    energy_charged_mwh: float
    final_soc_mwh: float
    equivalent_full_cycles: float


@dataclass(frozen=True)
class SweepResult:
    points: tuple[SweepPoint, ...]

    def frame(self) -> pd.DataFrame: ...


def run_sweep(
    spec: SweepSpec,
    *,
    span_days: Sequence[DayProfile],
    config: Config = DEFAULT_CONFIG,
) -> SweepResult: ...
```

Rules the implementer must follow.

1. `SweepSpec.__post_init__` validates: `sizes_mwh` non-empty, every size finite and
   positive, strictly increasing. Under `FIXED`, `power_mw` is required and
   `duration_hours` must be `None`. Under `FIXED_DURATION`, `duration_hours` is required,
   positive and finite, and `power_mw` must be `None`. Reject the wrong pairing rather than
   ignore the extra value, so no flag is silently dropped.
2. `duration_for` returns `size_mwh / self.power_for(size_mwh)`, which is constant under
   `FIXED_DURATION` and falls with size under `FIXED`.
3. `run_sweep` raises `ValueError` on an empty `span_days`.
4. `run_sweep` reads `peak_weight` and `smooth_weight` off `config.default_peak_weight` and
   `config.default_smooth_weight` and passes both to `simulate`. It takes no separate
   weight parameters. `cli._run` builds its `Config` from the same two flags. A sweep and a
   single run therefore reach `simulate` with identical arguments **while
   `energy_budget_fraction`, `priority_demand_weight` and `priority_wind_weight` keep their
   `Config` defaults**, which is the only state the `sweep` CLI can produce: section 2 cuts
   those three flags.
5. Every point starts full: `starting_soc = asset.total_mwh`. `run_sweep` performs no
   pre-event charging and takes no lead days. `initial_soc.charge_from_wind` from a full
   asset returns its input, because `soc_engine.clamp_charge` returns 0.0 at zero
   headroom, so a lead-day path here would be dead code. See revision-log entry B1.
6. `severity_reduction` comes from `metrics.severity_reduction`. `equivalent_full_cycles`
   comes from `metrics.equivalent_full_cycles(discharged, rated_energy_mwh=size)`.
7. `energy_discharged_mwh` and `energy_charged_mwh` sum `HourlyResult.discharge` and
   `HourlyResult.charge` over every hour of every day, the same two expressions
   `cli._build_report` uses.
8. `frame()` builds every column with an explicit `float64` dtype and passes
   `columns=list(SWEEP_FRAME_COLUMNS)`, mirroring `SimulationResult.hourly_frame`.
9. The module docstring cites this plan and states the `metrics.severity_reduction`
   divergence from `cli._severity_reduction` named in decision D6.
10. **No field of `SweepSpec` carries a `DEFAULT_CONFIG` default.** A class-level default
    would bind the value at import time, so a caller passing a custom `Config` to
    `run_sweep` would silently keep the import-time value. The caller supplies
    `efficiency`, `soc_floor_frac` and `strategic_reserve_frac` explicitly. Say this in the
    class docstring, and say that `Config.default_sweep_sizes_mwh` and
    `Config.default_sweep_power_rule` reach this class through `sweep_cli.build_parser`
    only.

### 4.4 `src/owr/sweep_chart.py`

```python
CHART_FIGSIZE_INCHES: tuple[float, float] = (11.0, 7.5)
CHART_DPI: int = 150
CHART_TITLE_FONTSIZE: int = 17
CHART_SUBTITLE_FONTSIZE: int = 12
CHART_LABEL_FONTSIZE: int = 13
CHART_TICK_FONTSIZE: int = 12
CHART_ANNOTATION_FONTSIZE: int = 11
CHART_FOOTER_FONTSIZE: int = 8
CHART_LINE_WIDTH: float = 2.4
CHART_MARKER_SIZE: float = 8.0


class ChartDependencyError(ValueError):
    """Matplotlib is absent. Subclasses ValueError so the CLI's own handler
    turns it into exit 2 with a message on stderr."""


def render_sweep_chart(
    frame: pd.DataFrame,
    *,
    path: str,
    title: str,
    subtitle: str,
    footer: str,
) -> None: ...
```

Rules.

1. **Validate the frame before the import.** The frame must be non-empty and must carry
   `storage_mwh`, `severity_reduction` and `energy_discharged_mwh`. Raise `ValueError`
   otherwise. This order lets the two validation tests run without Matplotlib installed.
2. Import Matplotlib inside a private `_matplotlib()` helper, called after validation.
   Catch `ImportError` and raise `ChartDependencyError` with this message: `chart output
   needs matplotlib, an optional dependency. Install it with: uv sync --group dev --extra
   viz`.
3. Use the object API, not `pyplot`: `Figure`, `FigureCanvasAgg`, `StrMethodFormatter`.
   Attach the canvas with `FigureCanvasAgg(fig)` before `fig.savefig(path)`. The file
   extension picks the output format, so one function writes both PNG and SVG.
4. Two panels through `fig.subplots(2, 1, sharex=True)`. Top plots
   `severity_reduction * 100` against `storage_mwh`. Bottom plots `energy_discharged_mwh`
   against `storage_mwh`.
5. Projector legibility. Set `ax.set_ylim(bottom=0)` on both panels, so a small effect
   cannot look large. Draw markers on every point. Set `ax.grid(True, alpha=0.3)`. Format
   the x axis with `StrMethodFormatter("{x:,.0f}")` and the top y axis with `"{x:,.1f}"`.
   Annotate each top-panel point with `f"{value:.2f}%"`.
6. Labels. X: `storage energy capacity (MWh)`. Top Y: `severity reduction (%)`. Bottom Y:
   `energy discharged (MWh)`.
7. `fig.suptitle(title)`, the subtitle through `fig.text(0.5, 0.945, subtitle,
   ha="center")`, the footer through `fig.text(0.01, 0.01, footer, ha="left",
   va="bottom")`. Call `fig.tight_layout(rect=(0, 0.04, 1, 0.93))` last.
8. The caller owns the text. This function composes no provenance string of its own.

### 4.5 `src/owr/sweep_cli.py`

Functions: `build_parser`, `cmd_sweep`, `_run`, `_build_report`, `_render_table`,
`_render_json`, `_write_data_csv`, `_size_list`, `main`. This mirrors `cli.py` one for one.

Error policy, copied from `cli.py`: results to stdout, errors and warnings to stderr,
`cmd_sweep` catches `ValueError` and returns 2.

`_finite_float` is imported from `owr.cli`. Both modules are the CLI layer and both need
one parser-boundary rule for non-finite numbers. A copy would drift. Add a one-line comment
saying so.

Flags:

| Flag | Type | Default | Effect |
|---|---|---|---|
| `--input` | path or `-` | required | day-profile CSV, read by `scenario_input.read_day_profiles` |
| `--sizes-mwh` | `_size_list` | `DEFAULT_CONFIG.default_sweep_sizes_mwh` | comma-separated MWh ladder |
| `--power-rule` | choice | `DEFAULT_CONFIG.default_sweep_power_rule` | `fixed` or `fixed_duration` |
| `--power-mw` | `_finite_float` | `None` | required under `fixed` |
| `--duration-hours` | `_finite_float` | `None` | required under `fixed_duration` |
| `--efficiency` | `_finite_float` | `cfg.default_efficiency` | `[OPEN: round_trip_efficiency]` |
| `--soc-floor-frac` | `_finite_float` | `cfg.default_soc_floor_frac` | `[OPEN: reserve_usage_rules]` |
| `--strategic-reserve-frac` | `_finite_float` | `cfg.default_strategic_reserve_frac` | `[OPEN: reserve_usage_rules]` |
| `--peak-weight` | `_finite_float` | `cfg.default_peak_weight` | dispatch weight |
| `--smooth-weight` | `_finite_float` | `cfg.default_smooth_weight` | dispatch weight |
| `--chart` | path | `None` | write the chart here; extension picks PNG or SVG (phase 3) |
| `--data-out` | path | `None` | write the bannered sweep CSV here |
| `--title` | str | `None` | chart title and table heading |
| `--format` | choice | `table` | `table` or `json` on stdout |

`_size_list(value)` splits on `,`, strips each token, rejects an empty list, rejects a
non-numeric or non-finite token, rejects a value at or below zero, rejects a duplicate,
then sorts ascending and returns a tuple. Every failure raises
`argparse.ArgumentTypeError`, so argparse exits 2 on its own. Sorting is documented in the
flag help, because the chart x axis must rise.

`_run` order. **The chart renders before anything reaches stdout.** A missing Matplotlib
must not produce a report that names a file nobody wrote.

1. Open the input the way `cli._run` does, `newline=""` and `encoding="utf-8"`, or read
   stdin for `-`. Print every reader warning to stderr.
2. Build `Config(default_efficiency=..., default_soc_floor_frac=...,
   default_strategic_reserve_frac=..., default_peak_weight=..., default_smooth_weight=...)`.
3. Build `SweepSpec` from the flags. A missing `--power-mw` under `fixed` reaches the user
   as the `SweepSpec` `ValueError`, caught by `cmd_sweep` as exit 2.
4. Call `run_sweep(spec, span_days=day_set.days, config=cfg)`. The span is every day in the
   file; the sweep does no window selection and no lead-day trimming.
5. Build the report with `report["chart"] = None`.
6. When `--chart` is set, call `render_sweep_chart` with the report's own provenance
   strings, then set `report["chart"] = args.chart`. Any failure propagates as `ValueError`
   and exits 2 with nothing on stdout.
7. When `--data-out` is set, write the bannered CSV.
8. Render stdout, `table` or `json`.

`_build_report` returns, in this key order: `code_version`, `generated_at`, `input`,
`spec`, `dispatch`, `points`, `chart`, `open_questions`. The `chart` key exists from phase
2 with the value `null`; phase 3 fills it with the written path. `code_version` comes from
`owr.version.code_version()` and `generated_at` from `datetime.now(UTC).isoformat()`, the
same two calls `cli._build_report` makes.

`open_questions` holds two entries defined locally in `sweep_cli.py`, in the shape
`cli._OPEN_QUESTIONS_STATIC` uses: `sweep_power_scaling` and `sweep_size_ladder`. Each
carries `flags`, `value_used`, `note` and `handoff_ref`. `handoff_ref` points at
`docs/PLAN_SCENARIO_SWEEP.md section 9`.

`_write_data_csv` mirrors `owr.etl.rows_csv.write_rows_csv`: open with `newline=""`, write
`# key = value` banner lines, then `frame.to_csv(handle, index=False,
lineterminator="\r\n")`. Banner keys: `generated_by`, `code_version`, `generated_at`,
`input`, `days`, `date_start`, `date_end`, `power_rule`, `power_mw` or `duration_hours`,
`efficiency`, `soc_floor_frac`, `strategic_reserve_frac`.

Chart text the CLI composes:

- title: `args.title` or `severity reduction vs storage size`.
- subtitle: `f"{path}, {n} days {start} to {end}, power rule {rule}, efficiency {eff:.3f},
  protected floor {floor:.3f}"`.
- footer: `f"engine {code_version}, generated {generated_at}, sizes {first:,.0f} to
  {last:,.0f} MWh, {n} points. Team design constants, not verified facts."`

## 5. Phases

Each phase ends with `uv run pytest` and `uv run ruff check .`, both clean.

### Phase 0 — dependency and defaults (about 30 minutes)

1. Add `viz = ["matplotlib>=3.9"]` to `[project.optional-dependencies]` in
   `pyproject.toml`, with a comment saying the engine core never imports it.
2. Run `uv sync --group dev --extra etl --extra api --extra viz`. If the network blocks the
   install, stop and read risk R1 before continuing.
3. Add `--extra viz` to the sync step in `.github/workflows/ci.yml` and extend the existing
   comment: the viz extra carries Matplotlib, which the chart tests import.
4. Add `PowerRule` to `src/owr/models.py`, next to `WrapConvention`.
5. Add the two fields, the validation and the docstring entries to `src/owr/config.py`.
   Add `import math`.
6. Add six cases to `tests/test_config.py`, listed in section 6.4.

Verify additionally: `uv run simulate --input examples/synthetic_winter_stress.csv
--storage-mwh 20000 --power-mw 2000 --format json` still parses, and its `config` block now
carries the two new keys.

### Phase 1 — the pure sweep runner (about 60 minutes)

1. Write `src/owr/sweep.py` to the interface in section 4.3.
2. Write `tests/test_sweep.py` with the 20 cases in section 6.1.
3. Export nothing new from `src/owr/__init__.py`. The package `__all__` carries the engine
   value objects and `simulate`. A sweep is a harness, not a value object. State this in
   the module docstring so the omission reads as a choice.

### Phase 2 — the `sweep` console script, no chart (about 75 minutes)

1. Write `src/owr/sweep_cli.py` to the interface in section 4.5, without `--chart`.
   `_build_report` still emits the `chart` key with the value `null`.
2. Add `sweep = "owr.sweep_cli:main"` to `[project.scripts]` with a one-line comment.
3. Run `uv sync --group dev --extra etl --extra api --extra viz` so the new script
   registers.
4. Write `tests/test_sweep_cli.py` with cases 1 to 13 of section 6.3.

Verify additionally: `uv run sweep --input examples/real_winter_stress_2026.csv --power-mw
4320` prints seven rows, and its 60,000 MWh row reads `1.06%`.

### Phase 3 — the chart (about 60 minutes)

1. Write `src/owr/sweep_chart.py` to the interface in section 4.4.
2. Add `--chart` to `sweep_cli.build_parser`, and step 6 plus the `Chart` stdout block to
   `_run`, in the order section 4.5 gives.
3. Write `tests/test_sweep_chart.py` with the 6 cases in section 6.2, and add cases 14 and
   15 to `tests/test_sweep_cli.py`.

Verify additionally: render both example charts to `/tmp`, open each, and read it at arm's
length. Legibility is a judgement call and no test covers it.

### Phase 4 — documentation and the demo run (about 30 minutes)

1. the repo map: add `uv run sweep --help` to the Commands block. Add a `src/owr/sweep.py`
   row to the engine-core table. Add a new two-row table under the ETL table, headed
   **Sweep chart** (`src/owr/sweep_cli.py`, `src/owr/sweep_chart.py`), noting that
   Matplotlib is the `viz` extra and never enters the engine core.
2. `README.md`: one Quickstart line for the sweep command, and one Layout line.
3. `docs/BOARD.md`: a Done row pointing at this plan, with the **measured** test counts,
   not the predicted ones.
4. `docs/HANDOFF.md`: a new session block at the bottom, in the shape the four blocks
   from 2026-08-05 use. Record what works, the files changed, the two new open questions
   and the next step.
5. Run both demo commands in section 7 and record the output shape in the handoff block.

## 6. Tests

Tests mirror module names one to one. Case counts: `tests/test_sweep.py` 20,
`tests/test_sweep_chart.py` 6, `tests/test_sweep_cli.py` 15, `tests/test_config.py` 6 more.
That is **47 new cases**.

Expected suite totals, from the 505 passed / 4 skipped baseline:

- With the `viz` extra installed: **552 passed, 4 skipped**.
- Without it: three render cases skip, giving **549 passed, 7 skipped**.

`tests/test_sweep.py` and `tests/test_sweep_cli.py` each define one module-level helper,
`_spec(**overrides)`, that builds a valid `SweepSpec`. `SweepSpec` carries no class-level
`Config` defaults (rule 10), so every test would otherwise repeat five fields.

### 6.1 `tests/test_sweep.py`

1. `SweepSpec` rejects an empty `sizes_mwh`.
2. `SweepSpec` rejects a size at or below zero.
3. `SweepSpec` rejects a non-finite size.
4. `SweepSpec` rejects sizes that are not strictly increasing.
5. `FIXED` without `power_mw` raises.
6. `FIXED` with `duration_hours` set raises.
7. `FIXED_DURATION` without `duration_hours` raises.
8. `FIXED_DURATION` with `power_mw` set raises.
9. `power_for` under `FIXED` returns the same value at the first and last size.
10. `power_for` under `FIXED_DURATION` returns `size / duration`.
11. `duration_for` under `FIXED` returns `size / power`, so it rises with size.
12. `asset_for` carries efficiency, floor fraction and reserve fraction onto the
    `StorageAsset`, and `min_soc_mwh` scales with size.
13. `run_sweep` returns one point per size, in ladder order.
14. `run_sweep` raises on an empty `span_days`.
15. **Anti-fork guard.** Build one `StorageAsset` by hand, call `simulate` directly with
    `starting_soc=asset.total_mwh`, and assert that a one-size `run_sweep` returns the same
    `severity_reduction`, `baseline_peak_mw`, `reserve_peak_mw`, `energy_discharged_mwh`
    and `final_soc_mwh`. Use exact float equality. Any divergence means the sweep forked
    the engine call path.
16. Determinism: two `run_sweep` calls on the same inputs produce equal frames, checked
    with `pandas.testing.assert_frame_equal`.
17. `frame()` column order equals `SWEEP_FRAME_COLUMNS` and every dtype is `float64`.
18. **Config pass-through.** Monkeypatch `owr.sweep.simulate` with a spy that records its
    keyword arguments and delegates to the real function. Assert that `run_sweep` passed
    `peak_weight` and `smooth_weight` equal to `config.default_peak_weight` and
    `config.default_smooth_weight`, for a `Config` whose two weights differ from the
    defaults. Assert that the spy call count equals the size count. Do **not** assert an
    output difference: measured at `219a55a`, the weight extremes 1.0/0.0 and 0.0/1.0
    return the same `reserve_peak_mw` (9,000.0 MW) and the same discharged energy
    (12,768.0 MWh) on `examples/synthetic_winter_stress.csv`, so an output-level assertion
    would fail while the code is correct.
19. **Purity guard.** Read the source of each engine-core module named in the repo map and
    assert that none contains `matplotlib`, `sweep_chart` or `owr.cli`. List the module
    paths in the test so a new core module has to be added on purpose.
20. `run_sweep` raises `ValueError` when every load value is zero, the documented D6
    divergence from `cli._severity_reduction`.

### 6.2 `tests/test_sweep_chart.py`

Cases 1 to 3 start with `pytest.importorskip("matplotlib")` at function level. Cases 4 to 6
need no Matplotlib, because `render_sweep_chart` validates before it imports (rule 1).

1. Renders a PNG to `tmp_path`. The file exists, is larger than 1 kB, and starts with the
   PNG magic bytes `\x89PNG`.
2. Renders an SVG to `tmp_path`. The file contains `<svg`.
3. The footer text reaches the SVG output: render with a known footer string and assert the
   code version appears in the file text. This proves the provenance stamp lands.
4. Rejects an empty frame with `ValueError`.
5. Rejects a frame missing `severity_reduction` with `ValueError`.
6. `ChartDependencyError` is a subclass of `ValueError`.

### 6.3 `tests/test_sweep_cli.py`

Cases 1 to 13 land in phase 2. Cases 14 and 15 land in phase 3.

1. `--help` exits 0.
2. Parser defaults equal the `DEFAULT_CONFIG` fields, including the size ladder and the
   power rule.
3. `--sizes-mwh "20000,10000"` parses to `(10000.0, 20000.0)`.
4. `--sizes-mwh "10000,10000"` exits 2.
5. `--sizes-mwh ""` exits 2.
6. `--sizes-mwh "abc"` exits 2.
7. A missing `--power-mw` under the fixed rule exits 2 and names the flag on stderr.
8. `--power-rule fixed_duration --duration-hours 4` gives `power_mw == size / 4` on every
   row.
9. `--format json` writes clean, parseable stdout, and its top-level keys equal the list in
   section 4.5 in that order. In phase 2 the `chart` value is `null`.
10. The table output carries one row per size and the code version in its heading.
11. **Reference point.** `examples/real_winter_stress_2026.csv` at `--sizes-mwh 60000
    --power-mw 4320` returns `severity_reduction == pytest.approx(0.010633, abs=1e-6)`, and
    `examples/synthetic_winter_stress.csv` at the same flags returns
    `pytest.approx(0.25, abs=1e-9)`. These pin the two numbers `docs/HANDOFF.md` records.
12. `--data-out` writes a file whose banner lines start with `#`, whose header equals
    `SWEEP_FRAME_COLUMNS`, and whose data row count equals the size count.
13. Reader warnings reach stderr and not stdout, so `--format json` stays parseable. Use
    the real example file, which warns about the absent `wind_forecast_frac` column.
14. `--chart` writes the file, and stdout names the path (`importorskip`).
15. `--chart` exits 2 with the install hint on stderr **and writes nothing to stdout**, when
    `sweep_cli.render_sweep_chart` is monkeypatched to raise `ChartDependencyError`. This
    pins the step order in section 4.5. No Matplotlib needed.

### 6.4 `tests/test_config.py` (six added cases)

1. `default_sweep_sizes_mwh` and `default_sweep_power_rule` equal the documented values.
2. An empty ladder raises.
3. A size at or below zero raises.
4. A non-finite size raises.
5. A ladder that is not strictly increasing raises.
6. `json.dumps(asdict(Config()))` round-trips: the ladder reads back as a list and the rule
   reads back as `"fixed"`. This extends the existing `WrapConvention` round-trip test.

## 7. The Friday demo commands

Real ISO-NE data, the 11-day event 2026-01-24 to 2026-02-03:

```
uv run sweep --input examples/real_winter_stress_2026.csv \
  --power-mw 4320 \
  --chart /tmp/sweep_real_2026.png \
  --title "Severity reduction vs storage size, ISO-NE 2026-01-24 to 2026-02-03"
```

Synthetic profile, the illustrated case:

```
uv run sweep --input examples/synthetic_winter_stress.csv \
  --power-mw 4320 \
  --chart /tmp/sweep_synthetic.png \
  --title "Severity reduction vs storage size, synthetic winter stress event"
```

Expected stdout shape:

```
sweep - Severity reduction vs storage size, ISO-NE 2026-01-24 to 2026-02-03 (engine 219a55a)

Inputs
  input                examples/real_winter_stress_2026.csv
  days read            11  (2026-01-24 .. 2026-02-03)
  simulated            11 days, every day in the file
  power rule           fixed, 4,320 MW at every size      [OPEN: sweep_power_scaling]
  efficiency           1.000                              [OPEN: round_trip_efficiency]
  protected floor      0.200 + 0.100 = 0.300              [OPEN: reserve_usage_rules]
  sizes                7 points, 5,000 .. 100,000 MWh     [OPEN: sweep_size_ladder]

Sweep
  storage MWh   power MW   duration h   severity %   discharged MWh   charged MWh     EFC
        5,000      4,320          1.2         0.09            3,394             0   0.679
       10,000      4,320          2.3         0.18            6,788             0   0.679
       20,000      4,320          4.6         0.35           13,577             0   0.679
       40,000      4,320          9.3         0.71           27,153             0   0.679
       60,000      4,320         13.9         1.06           40,730             0   0.679
       80,000      4,320         18.5         1.42           54,306             0   0.679
      100,000      4,320         23.1         1.74           67,883             0   0.679

Chart
  wrote /tmp/sweep_real_2026.png

Open team questions carried by this run
  sweep_power_scaling   used fixed  -- ...
  sweep_size_ladder     used 5,000 .. 100,000 MWh  -- ...
```

Every number in the table above was measured on 2026-08-05 at `219a55a`, through
`simulate --format json`, one run per size. Treat them as the expected shape and as the
target for test 11, not as a claim about a future engine. The 60,000 MWh row must equal the
`1.1%` figure `docs/HANDOFF.md` records.

**The real curve.** Severity reduction rises almost linearly and stays under 2%. Energy
discharged rises linearly with capacity across the whole ladder, and equivalent full cycles
hold flat at 0.679. Nothing saturates, because the file carries no wind column, so the
reserve never recharges inside the event and every size is limited by its own stock.

**The synthetic curve, measured at the same seven sizes.**

| Storage MWh | Severity % | Discharged MWh | EFC |
|---|---|---|---|
| 5,000 | 7.70 | 3,192 | 0.638 |
| 10,000 | 15.40 | 6,384 | 0.638 |
| 20,000 | 25.00 | 12,768 | 0.638 |
| 40,000 | 25.00 | 16,832 | 0.421 |
| 60,000 | 25.00 | 17,280 | 0.288 |
| 80,000 | 25.00 | 17,280 | 0.216 |
| 100,000 | 25.00 | 17,280 | 0.173 |

Three knees sit at three different sizes, and the talk track must keep them apart. Severity
reduction goes flat at 20,000 MWh. Energy discharged keeps rising past that point and goes
flat only at 60,000 MWh. Equivalent full cycles hold flat through 20,000 MWh, then fall as
capacity outruns throughput. The reading: **capacity past 20,000 MWh buys throughput, not
peak relief, and capacity past 60,000 MWh buys nothing at all.** The two panels show
exactly this, which is why the second panel carries discharged energy and not a repeat of
the first.

## 8. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | The Matplotlib install needs the network. `uv run python -c "import matplotlib"` fails today. | Phase 0 step 2 runs the install first, before any code lands. If it fails, ship phases 0 to 2 and plot the `--data-out` CSV in a spreadsheet. Phases 1 and 2 need no Matplotlib. |
| R2 | Matplotlib versions lay figures out differently. | No test asserts pixels, sizes or positions. Tests check the file exists, is non-empty and carries the expected magic bytes or text. |
| R3 | `Figure.savefig` to SVG with an Agg canvas attached may not switch format. | Test 6.2.2 proves it at implementation time. If it fails, pick the canvas class by file extension inside `_matplotlib()`. |
| R4 | Two new `Config` fields change the `config` block of every `simulate --format json` report. | `tests/test_cli.py` asserts top-level keys only, so nothing breaks. Anyone holding a stored JSON baseline sees two added keys. Record this in the handoff block. |
| R5 | `metrics.severity_reduction` raises where `cli._severity_reduction` returns `0.0`. | Documented in the `run_sweep` docstring and pinned by test 6.1.20. Both example files carry a positive baseline peak. |
| R6 | `uv run sweep` fails until the environment re-syncs after the script entry lands. | Phase 2 step 3 runs the sync. |
| R7 | The 1.1% real curve looks like a flat line next to the 25% synthetic curve. | Each chart plots one input file. Never put both on one axis. The y axis starts at zero on both, so neither curve is inflated. `docs/HANDOFF.md` open question 5 owns the framing. |
| R8 | Time runs out. | The cut line in section 2 leaves a working command at the end of phase 2. |
| R9 | A reader takes the size ladder for a sourced number. | The `config.py` docstring, the chart footer and the stdout block all mark it `[OPEN: sweep_size_ladder]` and name Report A's unreproduced target. |
| R10 | A viewer reads the synthetic chart's flat top panel as "storage stops working at 20,000 MWh". | The bottom panel keeps rising to 60,000 MWh and contradicts that reading directly. Section 7 carries the talk track. |

## 9. Open questions this work adds

1. **`sweep_power_scaling`.** Fixed power against fixed duration. Both are implemented and
   labeled. Fixed is the default because it reproduces the recorded reference points and
   adds no physical assumption. The team should say which one the slide carries, because
   the two curves differ in shape and not only in scale.
2. **`sweep_size_ladder`.** The seven default sizes bracket Report A's 40,000 to 60,000 MWh
   system reserve target. `docs/FACT_CHECK_REPORT.md` records that this target does not
   reproduce from Report A's own inputs. The ladder moves when that number moves.
3. **Where the two defaults belong.** They sit in `Config` under decision D3, because
   `SweepSpec` takes both as parameters. The counter-reading is that a size ladder is a
   reporting choice, which `docs/PLAN_SIMULATOR_CLI.md` keeps CLI-local, as
   `cli.DEFAULT_CYCLES_PER_YEAR` shows. Moving them later is a two-file change.
4. **Fuel offset against storage size.** Out of scope until a day-profile file carries
   `oil_mw` and `gas_mw`. `metrics.fuel_fired_generation_offset_mwh` already exists and
   `db/migrations/004_hourly_fuel_gen.sql` already lands the raw table. The missing link is
   the input format, which `docs/PLAN_SCENARIO_PROFILE_FORMAT.md` owns.
5. **A start-state-of-charge axis.** Every sweep point starts full. A partly charged start,
   and with it any pre-event charging, needs a second input and turns the sweep into a
   two-variable experiment. Revision-log entry B1 records why revision 2 cut it.
6. **Does the sweep belong to the API?** The FastAPI layer exposes single runs only. A
   sweep endpoint would need a new response schema and a new store shape. Not proposed here.

## 10. Revision log

### Revision 2, 2026-08-05, adversarial review applied

**B1 (blocking). The lead-days path was dead code and contradicted its own test.**
Resolved by option (a): `run_sweep` loses the `lead_days` parameter and the
`charge_from_wind` call, the CLI loses `--lead-days`, and the old test 6.1.18 is deleted.
Reason for choosing (a) over a start-state-of-charge field: `soc_engine.clamp_charge`
returns 0.0 at zero headroom, so charging a full asset is a no-op, and every sweep point
starts full by decision. Making the path live would need a start fraction, which is a
second sweep variable and a new open question three days before the demo. Section 2 now
cuts `--lead-days` explicitly with this reason, section 4.3 rule 5 states it, and section 9
item 5 records the deferred axis. A new test 6.1.18 takes the free slot and pins the
`Config` weight pass-through that rule 4 depends on. That test is a call-argument spy and
not an output comparison, because the two dispatch weights were measured at `219a55a` to
return identical outputs at both extremes on both example files.

**B2 (blocking). The synthetic narrative in section 7 was wrong.** The old text claimed
discharged energy and equivalent full cycles both turn at 20,000 MWh. Measured at
`219a55a`: severity turns at 20,000, discharged energy turns at 60,000, and equivalent full
cycles hold flat through 20,000 and then fall. Section 7 now carries the full measured
table and the corrected reading, that capacity past 20,000 MWh buys throughput and not peak
relief. Risk R10 covers the misreading this invites.

**M1 (major). The report could claim a chart that was never written.** `_run` rendered the
chart after stdout, so a `ChartDependencyError` produced a JSON payload naming a missing
file, with exit 2. Section 4.5 now fixes the step order: build the report with
`chart: null`, render the chart, set the key only after `render_sweep_chart` returns, write
the data CSV, then render stdout. Test 6.3.15 asserts that the failure path writes nothing
to stdout.

**M2 (major). The test arithmetic was wrong.** The listed cases were 42, not 36, and the
six `tests/test_config.py` cases from phase 0 were never counted. Section 6 now states 20
plus 6 plus 15 plus 6, which is 47, and the expected totals 552 passed / 4 skipped with the
`viz` extra and 549 passed / 7 skipped without it. Phase 4 step 3 now says to record the
measured counts rather than the predicted ones.

**N1 (minor). Test 6.3.9 asserted a `chart` key before the flag existed.** Section 4.5 and
phase 2 step 1 now state that `_build_report` emits `chart: null` from phase 2, so the
ordered key assertion is valid in both phases.

**N2 (minor). D1 overstated the subparser cost.** The claim that a subparser forces
`simulate run ...` is wrong; an optional subparser can keep the current invocation. D1 now
says so and rests on the real argument: a mixed grammar plus edits to the module that
carries the demo path, against a second script that touches zero lines of `cli.py`.

**N3 (minor). The "identical arguments" equivalence was unqualified.** Section 2 now cuts
`--energy-budget-fraction`, `--priority-demand-weight` and `--priority-wind-weight` in the
out-of-scope table, and section 4.3 rule 4 states that the equivalence holds while those
three keep their `Config` defaults, which is the only state the `sweep` CLI can produce.

**N4 (minor). `SweepSpec` bound `DEFAULT_CONFIG` at import time.** Resolved by removing
every class-level `Config` default from `SweepSpec`: `sizes_mwh`, `power_rule`,
`efficiency`, `soc_floor_frac` and `strategic_reserve_frac` are now required fields, and
only `power_mw` and `duration_hours` default to `None`. New rule 10 in section 4.3 states
the reason and states that the two new `Config` fields act at the parser boundary only. D3
carries the same sentence. Section 6 adds the `_spec(**overrides)` test helper the change
requires.

**N5 (minor). The purity guard grepped for one string.** Test 6.1.19 now also asserts that
no engine-core module contains `sweep_chart` or `owr.cli`. D4 states the same.

**Unchanged, confirmed sound by the review:** every reference number at `219a55a`, risk R1
and the phase 2 cut line, decision D5 and its CI precedent, decision D6 and test 6.1.20,
decisions D3 and D4.
