# Implementation Plan — Simulator CLI
Date: 2026-07-28 · Status: PLAN, nothing built yet
Scope: `docs/PLAN.md` Phase 3 item 7 made runnable from a terminal. MVP v1.0 per the
team's 2026-07-23 decision (CLI first, UI at v1.1+).

## 1. Scope and non-goals

Build one terminal entry point that reads a day-profile file, runs the existing engine
loop end to end, and prints results.

    stress_finder → initial_soc → [ per day: budget → dispatch → soc_engine ] → metrics

**Non-goals.** No engine changes beyond adding labeled constants to `config.py`. No new
stress-detection rule. No database, no DSN flag, no persistence of runs. No ETL changes.
No frontend. No capex or payback arithmetic (open question #7, unowned). No async run
model — the API already runs synchronously and so does this.

**Consistency rule.** The CLI sequences the engine exactly as `src/owr/api/app.py`
`create_run` does, with one documented addition: the API never calls `initial_soc`, and
the CLI reaches it through `--lead-days` (default 0, which reproduces the API's behavior
exactly).

## 2. Entry point and module layout

| Item | Value |
|---|---|
| Console script | `simulate` |
| Registration | `[project.scripts]` in `pyproject.toml`: `simulate = "owr.cli:main"` |
| Module | `src/owr/cli.py` (argparse, orchestration, rendering) |
| `python -m` form | `src/owr/__main__.py` → `python -m owr` |
| Input reader | `src/owr/scenario_input.py` (pure, no argparse) |
| Provenance helper | `src/owr/version.py` |

This mirrors the ETL CLI: `etl = "owr.etl.cli:main"` in `[project.scripts]`,
`src/owr/etl/__main__.py` for `python -m owr.etl`, domain logic in `extract.py` and a
thin argparse layer in `cli.py`. The simulator CLI drives the top-level engine, so it
sits at `owr.cli` rather than in a one-module package.

`main(argv: Sequence[str] | None = None) -> int` and `build_parser() -> ArgumentParser`
match the ETL CLI's shape so tests can call `cli.main([...])` and inspect
`build_parser().parse_args([...])` the same way `tests/test_etl_extract.py` does.

**No third-party runtime dependency.** `pyproject.toml` keeps `dependencies = []`. The
CLI uses stdlib `csv`, `json`, `argparse`, `dataclasses`, `math` only. Do not import
pydantic, fastapi, psycopg, or anything from `owr.api` — that would put the API extras
on the engine's runtime path and break the "engine runs with no database and no
credentials" property.

After adding the script, run `uv sync --group dev` so `.venv/bin/simulate` is created
(the same mechanism that produced `.venv/bin/etl`).

## 3. Where scenario input comes from

**Decision: a day-profile CSV file supplied with `--input`. No database, no credentials,
no in-memory store.**

Reasoning, stated because the sourcing was ambiguous:

- Postgres is out. The Phase 1 migrations have never been run against a live database
  and Phase 2 ETL is blocked on credentials (`docs/HANDOFF.md`). A CLI that needs a DSN
  would be undemoable today.
- The API's in-memory store is per-process and reachable only through HTTP. It carries no
  data across invocations.
- The API takes its day profiles from the request body (`RunCreate.days`), so the engine's
  input already arrives as a caller-supplied series. A file is the same contract on disk.
- No committed data fixture exists anywhere in the repo. Every current test builds
  synthetic `DayProfile` objects inline (`tests/test_simulator.py::_stress_day`,
  `tests/test_api.py::_days`).

### CSV format

One row per hour. Header required, column order irrelevant, names case-insensitive.
Lines that are blank or start with `#` are skipped, so a file can carry its own
provenance banner.

| Column | Required | Type | Maps to |
|---|---|---|---|
| `date` | yes | `YYYY-MM-DD` | `DayProfile.date` |
| `hour` | yes | int 0–23 | index into the hourly tuples |
| `load_mw` | yes | float | `DayProfile.hourly_load_mw` |
| `wind_mw` | no | float | `DayProfile.hourly_wind_mw` |
| `demand_percentile` | no | float, constant per date | `DayProfile.demand_percentile` |
| `wind_forecast_frac` | no | float, constant per date | `DayProfile.wind_forecast_frac` |

Rows are sorted by `(date, hour)` after reading, so file order does not matter.

**This layout is provisional.** Nothing in `db/migrations/001_init.sql` carries these
columns: `features.daily_load` (lines 65–69) is daily-grain with different names
(`load_mwh`, `season`, `demand_percentile`), the hourly tables are `raw.hourly_load` /
`raw.hourly_wind` keyed on `(source, zone, ts)`, and `docs/PLAN.md` Phase 2 defines no
CSV export step at all. The format is what this CLI reads today, not a contract with ETL.
When Phase 2 lands, either this reader gains a second layout or ETL grows an export that
matches this one, and whoever does that work owns reconciling the two. State this in the
reader's module docstring so the format is not mistaken for a stable interface.

### Handling of the optional columns

- `wind_mw` column absent → the day gets `hourly_wind_mw=()`. The simulator already treats
  an empty wind tuple as 24 zeros. Present but blank in a cell → `0.0` for that hour. The
  column is per-hour, so a blank hour reads as no wind in that hour.
- `demand_percentile` absent → derived as the empirical CDF of the day's energy within the
  supplied series: `count(load_mwh <= load_mwh(d)) / n_days`, range `(0, 1]`. A warning
  goes to stderr and `demand_percentile_source` in the JSON records `"derived-rank"`.
  Defaulting to `0.0` instead is wrong: it makes `priority()` zero for every day, which
  drives `remaining_priority_sum <= 0` in `budget.daily_budget` and silently hands every
  day the full 80% cap. The seasonal-denominator definition in the `DayProfile` docstring
  is not usable — `docs/HANDOFF.md` records the seasonal denominators as underivable and
  forbids hard-coding them.
- `wind_forecast_frac` absent → `0.0` (the `DayProfile` default), with a stderr warning and
  `"default-zero"` in the JSON. It cannot be derived without a wind nameplate capacity,
  which is not an input. Priority then reduces to `0.7 * demand_percentile`.
- **A blank cell in `demand_percentile` or `wind_forecast_frac` is rejected, never coerced.**
  These columns are constant per date, so a blank has no per-row reading. Coercing it to
  `0.0` would make the value vary within its date and trip the "varies within a single
  date" rejection with a message pointing at the wrong problem; and a date whose every row
  was blank would read as `0.0`, which is the exact outcome the derivation above exists to
  avoid. The error names the line and the column and tells the caller to omit the column
  entirely to get the documented default or derivation.
- A blank cell in `date`, `hour` or `load_mw` is rejected the same way. They are required.

### Validation, all rejected with exit code 2

- header missing `date`, `hour`, or `load_mw`
- zero data rows
- a date that does not parse, or a required cell left blank
- **a numeric cell that is not a finite number.** `float()` raises on `"abc"` but accepts
  `"nan"`, `"NaN"`, `"inf"`, `"-inf"`, `"+inf"` and `"Infinity"`, so catching `ValueError`
  around `float(value)` lets every one of them through. Parse with `float(value)`, then
  reject anything failing `math.isfinite()`. Nothing downstream catches it. The engine's
  guards trap non-finite values only where the check happens to be written as a positive
  range — verified against source: `StorageAsset(total_mwh=nan)` and
  `StorageAsset(power_mw=nan)` are **accepted** because `models.py:40-43` tests `<= 0`,
  which is False for NaN, while `efficiency=nan` is rejected because `models.py:44` tests
  `not 0.0 < eff <= 1.0`, which is True. `Config(priority_demand_weight=nan)` is
  **accepted** for the same reason (`config.py:53` tests `abs(sum - 1.0) > 1e-9`).
  `percentile_threshold`'s `sorted()` (`stress_finder.py:22`) accepts NaN and returns an
  order that depends on where the NaN sat in the input. `d.load_mwh >= threshold`
  (`stress_finder.py:49`) is always False against a NaN threshold, so a single poisoned row
  silently changes which days count as stressed and NaN propagates through the results
  without raising — no crash, a wrong answer. Reject at the boundary.
- `hour` outside 0–23
- a duplicate `(date, hour)` pair
- a date with other than exactly 24 rows
- `demand_percentile` or `wind_forecast_frac` varying within a single date
- **dates not consecutive calendar days.** `find_stress_windows` builds runs by list index,
  not by date adjacency, so a gap would produce a "consecutive" window that is not
  consecutive. This check closes that hole.

Each message names the source line number and the offending value.

### Shipped example input

`examples/synthetic_winter_stress.csv` — 6 consecutive days, 144 data rows, produced by a
committed generator rather than typed by hand.

Shape:

- Days 1–3: mild. Flat load around 7,500–8,500 MW, wind 1,500–3,000 MW in every hour.
  These are the lead days for `--lead-days`.
- Days 4–6: a cold snap. Evening peaks near 12,000 MW, low wind (300–600 MW).
- **Tie invariant:** all `load_mw` values are whole numbers, and days 4, 5 and 6 have
  identical daily load totals reached through different hourly shapes (peak hour moved,
  morning shoulder added). Integer-valued floats sum exactly regardless of order, so the
  three totals are bit-identical. The default `--severity-percentile 0.95` then
  interpolates its threshold to exactly that shared maximum, all three days clear it, and
  `--min-stress-window-days 2` yields one 3-day window. Break the tie and a 0.95 percentile
  over six days selects at most one day: `--list-windows` prints an empty list and exits 0,
  and the flagship demo command goes quiet with no error to explain it.
  Superseded 2026-07-28 — default is 0.90, not 0.95; see HANDOFF.md decision 2. The tie still
  holds under 0.90 (p90 and p95 both interpolate to 216,000 MWh on this six-day series), so
  the invariant described above is unaffected.
- The file opens with `#` comment lines stating that it is synthetic and not ISO-NE data,
  and naming the generator.

#### Generator: `examples/make_synthetic_winter_stress.py`

Typing 72 tied values by hand and trusting them to stay tied through later edits is the
failure mode above. Generate the file, and make the generator refuse to write when the
invariant breaks.

- Stdlib plus `owr` imports (`DayProfile`, `find_stress_windows`, `DEFAULT_CONFIG`). It
  runs as `uv run python examples/make_synthetic_winter_stress.py`; the package is
  installed editable in the environment (`_editable_impl_owr.pth`), the same mechanism
  that makes `.venv/bin/etl` work.
- Every shape is a labeled module constant: the mild and cold hourly load shapes, the mild
  and cold wind levels, the shared cold-day daily total, the start date. No literals inside
  the row loop — repo convention #5 applies to the fixture too.
- Each cold day fixes hours 0–22 from its shape and computes hour 23 as
  `COLD_DAY_TOTAL_MWH - sum(first 23 hours)`. The tie then holds by construction, and
  reshaping one day cannot silently break it.
- Assertions run **before** anything is written, so a failure raises and leaves the tracked
  file untouched:
  - every hourly load value is a whole number (`float(v).is_integer()`)
  - each computed closing hour is positive and no larger than that day's peak, so a shape
    edit that overshoots the total fails loudly instead of emitting a negative load
  - `days[3].load_mwh == days[4].load_mwh == days[5].load_mwh` — exact `==`, never
    `pytest.approx`; the exactness is the whole point
  - each cold-day total strictly exceeds every mild-day total
  - every mild day has strictly positive wind in all 24 hours, which is what makes the
    `--lead-days` test in Phase 4 able to distinguish one lead day from three
  - 6 consecutive dates, 24 rows each
  - `find_stress_windows(days, DEFAULT_CONFIG.default_severity_percentile,
    DEFAULT_CONFIG.default_min_stress_window_days)` returns exactly one window, of 3 days,
    starting on day 4's date and ending on day 6's — the invariant checked through the
    engine itself rather than through a restatement of the percentile rule
- Output path is `argv[1]`, defaulting to `examples/synthetic_winter_stress.csv`.
- Byte-for-byte deterministic: no randomness, and no timestamp in the banner. Regenerating
  must leave the tracked file unchanged, which Phase 4 verifies with `git diff --exit-code`.
- The script is linted by `uv run ruff check .` like everything else, and is not collected
  by pytest (`testpaths = ["tests"]`).
- The Phase 4 pinned test asserts the same one-window property against the committed file,
  so the invariant is checked at authoring time and again in CI.

**`.gitignore` edit required.** Line 13 is `*.csv`, which matches this file at any depth.
Add immediately after the `*.csv` entry:

```
# Committed example inputs for the simulator CLI (the blanket *.csv rule above is
# for local raw pulls).
!examples/*.csv
```

Verified: with that negation, `examples/*.csv` is tracked while `data/` and root-level
CSVs stay ignored. Without it the example file is silently untracked and the documented
demo command fails on a fresh clone. The generator is a `.py` file and needs no negation.

## 4. Argument surface

`prog="simulate"`. Defaults marked **cfg** are read from `owr.config.DEFAULT_CONFIG` at
parser-build time. Defaults marked **cli** are module-level labeled constants in `cli.py`,
used for values no engine function takes ("Where each default lives", below). Neither is
ever written as an argparse literal: repo convention #5 applied to the CLI, where an
argparse literal is a magic number.

**Every float-valued flag uses a shared `_finite_float` argparse type** — `float(value)`
followed by `math.isfinite`, raising `argparse.ArgumentTypeError` otherwise, at which point
argparse exits 2 on its own. This is the flag-side half of the non-finite rejection in
section 3 and it exists for the same reason: `--storage-mwh nan` and `--power-mw nan` both
slip past `StorageAsset.__post_init__`, and `--priority-demand-weight nan` slips past
`Config.__post_init__`, because every comparison against NaN is False. Verified against
source. `scenario_input.py` keeps its own parse helper — it raises `ScenarioInputError`
with a line number and imports no argparse — so the two are short functions with different
error types, and sharing one would put argparse in the reader for nothing.

### Input and labeling

| Flag | Type | Default | Maps to |
|---|---|---|---|
| `--input` | path, `-` for stdin | required | the day-profile CSV |
| `--name` | str | `None` | label echoed in output; mirrors `ScenarioCreate.name` |

### Storage asset

No config default exists for asset sizing and inventing one would be a magic number, so
the two sizing flags are required.

| Flag | Type | Default | Maps to |
|---|---|---|---|
| `--storage-mwh` | float | required (see note) | `StorageAsset.total_mwh` / `ScenarioCreate.storage_total_mwh` |
| `--power-mw` | float | required (see note) | `StorageAsset.power_mw` / `ScenarioCreate.power_output_mw` |
| `--start-soc-mwh` | float | `None` → `--storage-mwh` | `simulate(starting_soc=)` / `ScenarioCreate.storage_start_mwh` |
| `--efficiency` | float | **cfg** `default_efficiency` = 1.0 | `StorageAsset.efficiency` **and** `Config.default_efficiency` — **OPEN #1** |
| `--soc-floor-frac` | float | **cfg** `default_soc_floor_frac` = 0.20 | `StorageAsset.soc_floor_frac` **and** `Config.default_soc_floor_frac` — **OPEN #4** |
| `--strategic-reserve-frac` | float | **cfg** `default_strategic_reserve_frac` = 0.10 | `StorageAsset.strategic_reserve_frac` **and** `Config.default_strategic_reserve_frac` — **OPEN #4** |

Note: `--storage-mwh` and `--power-mw` are declared with `default=None`, not
`required=True`, and are checked inside the command function so `--list-windows` does not
demand irrelevant flags. Missing either without `--list-windows` prints
`error: --storage-mwh and --power-mw are required (or use --list-windows).` and returns 2.
This is exactly how `etl/cli.py::cmd_extract` handles `--dsn`.

**Behavioral warning for the implementer.** The engine reads only
`priority_demand_weight`, `priority_wind_weight` and `energy_budget_fraction` off
`Config` (confirmed: `budget.py` lines 23–24, 42 and `simulator.py` line 117).
`default_efficiency`, `default_soc_floor_frac` and `default_strategic_reserve_frac` are
documentation defaults that nothing reads. Efficiency and the reserve fractions change
behavior **only** through `StorageAsset`. Set both: `StorageAsset` for behavior, `Config`
for the provenance record in the JSON output.

### Stress-event detection

| Flag | Type | Default | Maps to |
|---|---|---|---|
| `--severity-percentile` | float | **cfg** `default_severity_percentile` = 0.95 | `find_stress_windows(severity_percentile=)` — **OPEN #2**. Superseded 2026-07-28 — default is 0.90; see HANDOFF.md decision 2. |
| `--min-stress-window-days` | int | **cfg** `default_min_stress_window_days` = 2 | `find_stress_windows(min_window_days=)` — **OPEN #2** |
| `--window` | `all` or 1-based int | `all` | which detected window to simulate |
| `--lead-days` | int ≥ 0 | `0` | days fed to `initial_soc.charge_from_wind` |
| `--list-windows` | flag | off | detect and print windows, skip the simulation |

### Dispatch and budgeting

| Flag | Type | Default | Maps to |
|---|---|---|---|
| `--peak-weight` | float | **cfg** `default_peak_weight` = 0.5 | `simulate(peak_weight=)` |
| `--smooth-weight` | float | **cfg** `default_smooth_weight` = 0.5 | `simulate(smooth_weight=)` |
| `--energy-budget-fraction` | float | **cfg** `energy_budget_fraction` = 0.80 | `Config.energy_budget_fraction` |
| `--priority-demand-weight` | float | **cfg** `priority_demand_weight` = 0.7 | `Config.priority_demand_weight` |
| `--priority-wind-weight` | float | **cfg** `priority_wind_weight` = 0.3 | `Config.priority_wind_weight` |

### Reporting

| Flag | Type | Default | Maps to |
|---|---|---|---|
| `--available-capacity-mw` | float | `None` | `simulate(available_capacity_mw=)`; `None` leaves capacity margin unset |
| `--cycles-per-year` | float > 0 | **cli** `DEFAULT_CYCLES_PER_YEAR` = `None` (unset) | reported only, never fed to the engine — **OPEN #5** |
| `--format` | `table` \| `json` | `table` | output rendering |

`--cycles-per-year` must be finite and strictly positive when supplied; `cmd_run` checks
it and returns 2. `Config` does not carry it, so there is no `__post_init__` to lean on.

### Where each default lives

**A value belongs in `owr.config.Config` when an engine function or value object takes it
as a parameter. Everything else stays CLI-local.**

That rule matches every field `Config` already has. `priority_demand_weight`,
`priority_wind_weight` and `energy_budget_fraction` are read off `Config` inside
`budget.py` and `simulator.py`. `default_efficiency` reaches `soc_engine.next_soc(
efficiency=)` through `StorageAsset.efficiency`. `default_soc_floor_frac` and
`default_strategic_reserve_frac` reach `clamp_discharge` through
`StorageAsset.min_soc_mwh`.

The four fields Phase 1 adds pass the same test:
`find_stress_windows(days, severity_percentile, min_window_days)` and
`simulate(..., peak_weight=, smooth_weight=)` take all four as arguments, and today their
only written-down defaults are literals in those signatures and in
`api/schemas.ScenarioCreate` (lines 32–38). Putting a labeled default in `config.py` is
what convention #5 and `docs/PLAN.md` Phase 3's closing line ask for — "constants are
config values labeled as team design choices". Leaving them as signature literals is the
thing the convention forbids. Two of the four are the surface of OPEN question #2, which
`config.py`'s module docstring names as the reason the file exists.

`assumed_cycles_per_year` fails that test and is therefore **not** added to `Config`. No
engine function takes it and none will: it belongs to the capex/payback arithmetic that
section 1 puts out of scope (open question #7, unowned). It lives in `cli.py` as
`DEFAULT_CYCLES_PER_YEAR: float | None = None`, carrying the same open-question comment it
would have carried in the docstring, and appears in the JSON under `reporting` rather than
inside `config`.

On duplicating values that `api/schemas.py` already hardcodes: the repo carries the
reserve fractions across three surfaces today (`Config`, `StorageAsset`, `ScenarioCreate`)
and pins them with `tests/test_reserve_defaults.py`, whose docstring states that intent in
so many words. The Phase 1 drift guard extends an established pattern. Collapsing
`schemas.py` onto `Config` would change the API's request-validation defaults and pull
`owr.config` into the pydantic layer; that is a separate change with its own blast radius
and it is not in this plan's scope.

### Deliberately not exposed

- `transmission_limit_mw` — the engine models no transmission constraint. Exposing a flag
  the engine ignores would be misleading.
- `season`, `date_start`, `date_end` — derived from the input file's dates.
- Any DSN or database flag — the CLI has no persistence path.

## 5. Open team questions the CLI surfaces

Repo conventions #4 and #5: surface the disagreement, do not pick a side. Each of these is
a flag with a labeled default, and each is annotated in both output formats. The JSON
carries an `open_questions` array with these stable ids.

| id | Flags | Default | Note the CLI prints |
|---|---|---|---|
| `round_trip_efficiency` | `--efficiency` | 1.0 | `config.py` ships 1.0; Report B computed everything at 0.85. At 1.0 the engine understates required charging energy by 17.6%. The storage pivot makes efficiency the axis candidate technologies differ on (StEnSea 0.80, LAES 0.50–0.70, thermal ~0.35). Undecided. |
| `stress_event_definition` | `--severity-percentile`, `--min-stress-window-days` | 0.95, 2 | The implemented rule is daily energy at or above a percentile of the series, with runs of N consecutive days forming an event. A competing rule counts hours within the day (12+ hours above threshold = stress day, 2+ consecutive = event). Three artifacts use three rules on the same January 2025 activity. Undecided. Superseded 2026-07-28 — default is 0.90 and the 12-hour rule is retired; see HANDOFF.md decision 2. |
| `reserve_usage_rules` | `--soc-floor-frac`, `--strategic-reserve-frac` | 0.20, 0.10 | The 20% floor and 10% strategic reserve are modeled as two fractions summed into one protected floor. When each may be drawn is open since 2026-07-18. |
| `cycles_per_year` | `--cycles-per-year` | unset | Identified 2026-07-28 as the variable the storage siting trade-off turns on and left unspecified. At ~10 cycles/yr capex dominates; at ~200 the efficiency case returns. The engine does not consume it, so its default is a labeled constant in `cli.py` rather than a `Config` field. |

Open question #3 (is charged wind priced at opportunity cost) gets no flag: the engine
models no prices, so there is nothing to parameterize. Note this in the module docstring
so its absence is not read as a decision.

Implementing the competing stress-event rule is out of scope. It changes `stress_finder`
and belongs to whoever resolves question #2.

## 6. Orchestration sequence

`cmd_run(args) -> int` executes exactly this order:

1. Open `--input` (or `sys.stdin` for `-`). Call
   `scenario_input.read_day_profiles(stream, origin=...)` → `DayProfileSet`. Warnings from
   the reader go to **stderr**.
2. Build `Config(...)` from every config-backed flag. `Config.__post_init__` validates.
3. Build `StorageAsset(...)` from the asset flags. `__post_init__` validates.
4. `windows = find_stress_windows(days, args.severity_percentile, args.min_stress_window_days)`
   over **all** days in the file, including any that become lead days — the percentile is a
   property of the whole series.
5. If `--list-windows`: render the windows, return 0. Zero windows is a valid answer and
   still returns 0.
6. Select the simulated span and the lead days:
   - `--window all` → `lead = days[:lead_days]`, `span = days[lead_days:]`. Error if
     `lead_days >= len(days)`. **Semantics:** with no window selected there is nothing to
     anchor a lead-up to, so `--lead-days N` charges over the *first N days of the file*
     and simulates the rest, wherever the stress happens to sit. Detection in step 4 still
     runs over the whole file and the printed window list is unaffected; only the simulated
     span shrinks. Callers who want the lead-up to sit immediately before the event use
     `--window N`. Both output formats print the simulated date range, so the trim is
     visible.
   - `--window N` → error if there are no windows, or `N < 1`, or `N > len(windows)`.
     Locate the window's start and end dates in `days` as indices `w0`, `w1`;
     `span = days[w0:w1 + 1]`; `lead = days[max(0, w0 - lead_days):w0]`. If fewer than
     `lead_days` precede the window, use what exists and note the shortfall on stderr.
7. `s0 = args.start_soc_mwh if given else asset.total_mwh`. Validate `0 <= s0 <= total_mwh`
   before charging so the message is clear (`simulate` checks it again).
8. `soc_at_start = charge_from_wind(s0, lead, asset) if lead else s0`.
9. `result = simulate(asset, span, starting_soc=soc_at_start, available_capacity_mw=...,
   config=cfg, peak_weight=..., smooth_weight=...)` — the same call shape as
   `api/app.py::create_run`.
10. Derive summary metrics (section 7), render to stdout, return 0.

`--window N` restricts the simulated span, so `baseline_peak_mw` and `reserve_peak_mw`
cover the window only. The table states which days were simulated.

## 7. Output

### Derived summary fields

All computed from what `simulate()` returns. No new engine code.

| Field | Definition |
|---|---|
| `baseline_peak_mw` | `SimulationResult.baseline_peak_mw` |
| `reserve_peak_mw` | `SimulationResult.reserve_peak_mw` |
| `severity_reduction` | `metrics.severity_reduction(baseline, reserve)`, guarded to `0.0` when `baseline <= 0` — the same guard as `api/app.py::_severity_reduction`, duplicated locally because importing it would drag in fastapi |
| `final_soc` | `SimulationResult.final_soc` |
| `min_soc_mwh` | `asset.min_soc_mwh` |
| `energy_discharged_mwh` | sum of `HourlyResult.discharge` over every hour (energy delivered to the grid) |
| `energy_charged_mwh` | sum of `HourlyResult.charge` over every hour |
| `equivalent_full_cycles` | `(energy_discharged_mwh / efficiency) / total_mwh` — energy drawn from the tank over rated capacity. Equals `energy_discharged_mwh / total_mwh` at the default efficiency of 1.0. Label the definition in the output. Superseded 2026-07-28 — see HANDOFF.md decision 5; EFC is energy discharged / rated capacity. |
| `window_share_of_annual_cycles` | `equivalent_full_cycles / cycles_per_year`, or `null` when `--cycles-per-year` is unset |
| `min_capacity_margin_mw` | minimum non-`None` `HourlyResult.capacity_margin`, with the date and hour where it occurs; `null` when `--available-capacity-mw` is unset |

Per day: `date`, `priority`, `budget`, `usable_energy`, `recharge_sufficiency_ratio`,
plus `discharged_mwh` and `charged_mwh` (sums over the day's hours) and `gross_peak_mw` /
`net_peak_mw` (maxima over the day's hours).

Two labeling traps to get right:
- `DailyResult.usable_energy` is recorded **after** the day's 24 hours run
  (`simulator.py` line 128 uses the end-of-day SoC). Header it `usable MWh (end of day)`.
- `recharge_sufficiency_ratio` is `None` on the final day by construction
  (`next_need = 0.0`). Render it as `—` in the table and `null` in JSON.

### Table (default)

Sections in order. Number formats: `{:,.0f}` for MW and MWh (matching the annotation
style in `api/app.py`), `{:.3f}` for fractions, `{v * 100:.1f}%` for severity reduction.

```
simulate — <name or "unnamed scenario"> (engine <short sha>)

Inputs
  input                examples/synthetic_winter_stress.csv
  days read            6  (2026-01-06 .. 2026-01-11)
  demand percentile    derived from series rank (column absent)
  wind forecast frac   defaulted to 0.000 (column absent)
  storage              20,000 MWh / 2,000 MW
  efficiency           1.000                      [OPEN: round_trip_efficiency]
  protected floor      0.200 + 0.100 = 0.300 -> 6,000 MWh   [OPEN: reserve_usage_rules]
  energy budget        0.800 of usable energy
  priority weights     0.700 demand / 0.300 wind
  dispatch weights     0.500 peak / 0.500 smooth
  cycles per year      unset                      [OPEN: cycles_per_year]

Stress windows                                    [OPEN: stress_event_definition]
  rule: daily energy >= 0.950 percentile of the series; >= 2 consecutive days
  1   2026-01-09 .. 2026-01-11   3 days
  simulated: window 1 (3 days)   lead days: 3

Pre-event charging (initial_soc)
  8,000 MWh -> 14,600 MWh over 3 lead day(s)

Daily results
  date         priority   budget MWh   usable MWh (eod)   discharged MWh   recharge ratio   gross peak MW   net peak MW
  2026-01-09      0.700        6,720             10,120            6,720            0.312          12,000         9,800
  ...

Summary
  baseline peak                     12,000 MW
  reserve peak                       9,800 MW
  severity reduction                    18.3%
  final state of charge              7,240 MWh   (protected floor 6,000 MWh)
  energy discharged                 12,400 MWh
  energy charged                     3,100 MWh
  equivalent full cycles                 0.620   (energy drawn / rated capacity)
  min capacity margin                1,200 MW    (2026-01-10 hour 18)

Open team questions carried by this run
  round_trip_efficiency    used 1.000  — <note text>
  stress_event_definition  used 0.950 / 2 days  — <note text>
  reserve_usage_rules      used 0.200 + 0.100  — <note text>
  cycles_per_year          unset  — <note text>
```

Superseded 2026-07-28 — this transcript is illustrative only and is now stale in two ways
(see HANDOFF.md decisions 2 and 5): a real run prints `rule: daily energy >= 0.900
percentile...` and `stress_event_definition  used 0.900 / 2 days` (default moved 0.95 → 0.90),
and the `equivalent full cycles` line reads `(energy discharged / rated capacity)`, not
`(energy drawn / rated capacity)` — the divide-by-efficiency formula was retired.

Omit the pre-event charging section when there are no lead days. Omit the min capacity
margin line when `--available-capacity-mw` is unset.

### JSON (`--format json`)

Stdout carries the JSON document and nothing else, so it pipes into `jq`. Warnings go to
stderr in both formats. Full float precision, no rounding, so the payload is diffable
against `GET /runs/{id}/results`. `indent=2`, trailing newline. Dates as
`date.isoformat()`.

Top-level keys, in this order:

```
code_version, generated_at, input, asset, config, dispatch, reporting, stress_windows,
simulated, daily, summary, open_questions
```

- `input`: `{path, days_read, date_start, date_end, demand_percentile_source,
  wind_forecast_frac_source, has_wind}`
- `asset`: `{total_mwh, power_mw, efficiency, soc_floor_frac, strategic_reserve_frac,
  min_soc_mwh}`
- `config`: every `Config` field, so the record of design constants used is complete
- `dispatch`: `{peak_weight, smooth_weight}`
- `reporting`: `{cycles_per_year}` — the assumption behind
  `summary.window_share_of_annual_cycles`, kept out of `config` because no engine function
  reads it (section 4, "Where each default lives")
- `stress_windows`: `[{start, end, days}]` — same field names as
  `schemas.StressWindowOut`
- `simulated`: `{window, lead_days_used, date_start, date_end, starting_soc_mwh,
  soc_at_window_start_mwh}`
- `daily`: the per-day fields from section 7 plus `hourly`, whose objects use the exact
  field names of `schemas.HourlyResultOut` (`ts_hour, soc, charge, discharge,
  discharge_peak, discharge_smooth, gross_load, net_load, capacity_margin`). Hourly detail
  is always included in JSON and never in the table, mirroring the API's
  `RunResultsOut`.
- `summary`: the fields from section 7. `final_soc`, `baseline_peak_mw`,
  `reserve_peak_mw` and `severity_reduction` keep the API's names.
- `open_questions`: `[{id, flags, value_used, note, handoff_ref}]` for the four ids in
  section 5.

`generated_at` is a UTC ISO-8601 timestamp. Tests must not assert on its value.

`code_version` is the short git sha, from `owr.version.code_version()`.

## 8. Error handling and exit codes

| Code | Meaning |
|---|---|
| 0 | Ran and printed results, including `--list-windows` with zero windows found |
| 2 | Usage or input error. Bad or missing flags (argparse's own exit code is already 2, which also covers a non-finite value rejected by `_finite_float`), unreadable or malformed input, `--window N` out of range, `--lead-days` too large or negative, `--cycles-per-year` not positive, and any `ValueError` from `Config`, `StorageAsset`, `charge_from_wind` or `simulate` |
| 1 | Anything unexpected — an uncaught exception propagates with its traceback and Python exits 1 |

`cmd_run` wraps steps 1–9 in a single `except ValueError as exc:` that prints
`error: {exc}` and returns 2. `scenario_input.ScenarioInputError` subclasses `ValueError`
so one handler covers both input-file and engine validation failures. This mirrors the
API's `except ValueError` → 422 "simulation rejected inputs". Do not catch bare
`Exception`; the ETL CLI catches nothing broad and neither should this.

**Errors and warnings go to stderr**, results to stdout. This diverges from `etl/cli.py`,
which prints its DSN error to stdout. The divergence is deliberate: the ETL CLI has no
machine-readable output mode, and `--format json` here would be corrupted by diagnostics
on stdout. Note the reason in the module docstring.

## 9. Phases

### Phase 1 — Config constants

**Files:** `src/owr/config.py`, new `tests/test_config.py`.

Add to `Config`, all with defaults so existing construction sites keep working
(`DEFAULT_CONFIG = Config()`, `tests/test_budget.py`, `tests/test_reserve_defaults.py`):

| Field | Type | Default |
|---|---|---|
| `default_severity_percentile` | `float` | `0.95`. Superseded 2026-07-28 — default is `0.90`; see HANDOFF.md decision 2. |
| `default_min_stress_window_days` | `int` | `2` |
| `default_peak_weight` | `float` | `0.5` |
| `default_smooth_weight` | `float` | `0.5` |

The defaults equal the values already shipping in `api/schemas.ScenarioCreate` and in the
`simulate()` / `allocate_discharge()` signatures. Nothing changes behavior.

`assumed_cycles_per_year` is deliberately **not** among them; it lives in `cli.py`. The
rule and the reasoning are in section 4, "Where each default lives".

Extend `__post_init__`:

```
0.0 <= default_severity_percentile <= 1.0
default_min_stress_window_days >= 1
default_peak_weight >= 0 and default_smooth_weight >= 0 and their sum > 0
```

Widen the class docstring's opening line. It currently reads "Tunable design constants for
the dispatch model", which reads as excluding `default_severity_percentile` and
`default_min_stress_window_days` — those parameterize `stress_finder`, not `dispatch`.
Proposed replacement:

> Tunable design constants for the engine's stress-detection and dispatch models.
>
> A value belongs here when an engine function or value object takes it as a parameter;
> reporting-only assumptions live with their consumer.

The second sentence is what keeps the next `assumed_cycles_per_year` out.

Add a docstring entry per new field naming the open question, per repo convention #5.
Proposed text:

> `default_severity_percentile` / `default_min_stress_window_days`
>     Stress-event detection parameters passed to `stress_finder`: a day is stressed
>     when its daily energy sits at or above this percentile of the series, and a run
>     of this many consecutive stressed days is an event. OPEN team question (one
>     canonical stress-event definition): three artifacts use three thresholds and
>     merge rules on the same January 2025 activity, and a competing rule counts hours
>     within the day (12+ hours above threshold = stress day, 2+ consecutive = event).
>     These are the shipped defaults of the implemented rule, not a decision.
>
> `default_peak_weight` / `default_smooth_weight`
>     Relative emphasis of peak shaving vs ramp smoothing in `dispatch`. The
>     Architecture doc names PeakWeight and SmoothWeight without fixing values.
>     (Team design choice.)

Also append to the existing `default_efficiency` entry: it currently names only
FACT_CHECK inconsistency #2. Add that this is an OPEN team question — `config.py` ships
1.0 while Report B computed at 0.85, and the storage pivot makes efficiency the axis
candidate technologies differ on.

**Tests (`tests/test_config.py`):**
- new fields exist with the documented defaults
- each new validation rejects its bad value (`pytest.raises(ValueError)`), following
  `tests/test_budget.py::test_priority_weights_must_sum_to_one`
- drift guard: `Config()` defaults equal the corresponding `ScenarioCreate` field defaults
  for severity percentile, min stress window days, peak weight and smooth weight — the
  same intent and the same three-surface pattern as `tests/test_reserve_defaults.py`

**Verify:** `uv run pytest tests/test_config.py tests/test_budget.py tests/test_reserve_defaults.py`

### Phase 2 — Shared code-version helper

**Files:** new `src/owr/version.py`, edit `src/owr/api/app.py`.

Move `code_version()` (with its `@lru_cache(maxsize=1)` and the `subprocess`/`git
rev-parse --short HEAD` body, returning `"unknown"` on failure) from `api/app.py` into
`owr/version.py` verbatim. In `api/app.py` delete the local definition and add
`from owr.version import code_version`; every call site is unchanged.

This is the only non-CLI file touched. Justification: the CLI needs the same provenance
sha the API stamps on runs, and copying the function would let the two drift.

**Tests:** add to `tests/test_cli.py` that `code_version()` returns a non-empty string.
The existing `tests/test_api.py::test_full_run_flow` already asserts
`pkg["payload"]["code_version"]` is truthy and must keep passing.

**Verify:** `uv run pytest tests/test_api.py`

### Phase 3 — Input reader

**Files:** new `src/owr/scenario_input.py`, new `tests/test_scenario_input.py`.

```python
class ScenarioInputError(ValueError): ...

@dataclass(frozen=True)
class DayProfileSet:
    days: list[DayProfile]
    demand_percentile_source: str    # "file" | "derived-rank"
    wind_forecast_frac_source: str   # "file" | "default-zero"
    has_wind: bool
    warnings: tuple[str, ...]

def read_day_profiles(stream: TextIO, *, origin: str) -> DayProfileSet: ...
```

Takes a text stream rather than a path so tests use `io.StringIO` and the CLI passes an
open file or `sys.stdin`. `origin` is a label used in error messages.

Line-number bookkeeping: build
`filtered = [(n, line) for n, line in enumerate(stream, 1) if line.strip() and not
line.lstrip().startswith("#")]`, feed `csv.DictReader` the line text, and keep the
parallel `[n for n, _ in filtered]` so the i-th data row reports `linenos[i + 1]`.
Lowercase and strip the header names.

Footnote on that approach: pre-filtering by line desynchronizes the line-number map from
`csv.DictReader` if a field contains a newline inside quotes, since one CSV record would
then span two source lines. The schema is dates, integers and floats, so a quoted
multi-line field is not a realistic input, and the line numbers are diagnostic aids rather
than a parsing contract. Left unhandled deliberately; say so in a code comment.

Numeric parsing goes through one internal helper: `float(value)`, then `math.isfinite`,
raising `ScenarioInputError` with the origin, line number, column and offending text on
either failure. Every numeric column uses it.

Implement every validation and derivation rule from section 3. Every failure raises
`ScenarioInputError` with the origin, the line number and the offending value.

**Tests:**
- minimal CSV (`date,hour,load_mw`) → one `DayProfile`, `hourly_wind_mw == ()`
- `wind_mw` column present → 24 wind values, `has_wind is True`
- rows shuffled in the file → same result as sorted
- per-day scalars read from the file → `demand_percentile_source == "file"`
- scalars absent → ECDF derivation, with the exact expected values for a 3-day series
  and a warning naming the derivation
- `wind_forecast_frac` absent → `0.0` and `"default-zero"`
- blank lines and `#` comments are skipped
- **non-finite rejection, parametrized over `"nan"`, `"NaN"`, `"inf"`, `"-inf"`, `"+inf"`
  and `"Infinity"`** — `float()` accepts every one of these (confirmed), so each must raise
  `ScenarioInputError` with the line number in the message. Run the parametrization against
  `load_mw`, and once each against `wind_mw`, `demand_percentile` and `wind_forecast_frac`,
  so no column is left on a bare `try: float(...) except ValueError` path.
- blank-cell handling: blank `wind_mw` cell → `0.0`; blank `demand_percentile` cell →
  `ScenarioInputError` naming the line and the column; blank `wind_forecast_frac` cell →
  the same; blank `load_mw` cell → the same
- one `ScenarioInputError` case per remaining validation rule in section 3, each asserting
  the line number appears in the message
- date-gap rejection gets its own named test — it is the subtle one

**Verify:** `uv run pytest tests/test_scenario_input.py`

### Phase 4 — CLI

**Files:** new `src/owr/cli.py`, new `src/owr/__main__.py`, edit `pyproject.toml`, new
`examples/make_synthetic_winter_stress.py`, new `examples/synthetic_winter_stress.csv`
(its output), edit `.gitignore`, new `tests/test_cli.py`.

Module docstring: name the engine loop, state that the CLI mirrors
`api/app.py::create_run` and adds `initial_soc` via `--lead-days`, state that errors go
to stderr and why, and state that open question #3 has no CLI surface because the engine
models no prices.

Structure, mirroring `etl/cli.py`:

```python
DEFAULT_CYCLES_PER_YEAR: float | None = None   # labeled constant, see section 4

def _finite_float(value: str) -> float: ...          # argparse type, rejects nan/inf
def _window_spec(value: str) -> str | int: ...       # "all" or a positive int
def build_parser() -> argparse.ArgumentParser: ...   # prog="simulate"
def cmd_run(args: argparse.Namespace) -> int: ...    # set as parser.set_defaults(func=)
def _render_table(report, out) -> None: ...
def _render_json(report, out) -> None: ...
def main(argv: Sequence[str] | None = None) -> int: ...
```

Build a single `report` dict (the JSON document from section 7) and render it either way,
so the two formats cannot disagree.

`src/owr/__main__.py` mirrors `src/owr/etl/__main__.py` exactly.

`pyproject.toml`: add under `[project.scripts]`, keeping the existing comment style:

```toml
# Simulator CLI: runs a scenario end to end over the engine (see src/owr/cli.py).
simulate = "owr.cli:main"
```

Write `examples/make_synthetic_winter_stress.py` to the contract in section 3 and run it
to produce the CSV. Do not hand-edit the CSV afterwards.

**Tests (`tests/test_cli.py`),** following `tests/test_etl_extract.py`'s CLI section
(`capsys`, `cli.main([...])`, `pytest.raises(SystemExit)`):

*Wiring and defaults*
- `build_parser()` defaults equal the matching `DEFAULT_CONFIG` fields — asserted against
  `DEFAULT_CONFIG`, not literals. This is the guard against magic numbers creeping into
  argparse.
- the `--cycles-per-year` default is `cli.DEFAULT_CYCLES_PER_YEAR`, asserted against the
  constant rather than against `None` written twice
- `--help` raises `SystemExit(0)`; no `--input` raises `SystemExit(2)`
- `from owr.cli import main` is importable at the path named in `[project.scripts]`

*Shipped example*
- it parses and `main([...])` returns 0
- `find_stress_windows` over it, at `DEFAULT_CONFIG.default_severity_percentile` and
  `default_min_stress_window_days`, returns exactly one window of 3 days — this pins the
  tied-daily-total construction from section 3, independently of the generator's own
  authoring-time assertion

*Run behavior* (small CSVs written to `tmp_path`, or `io.StringIO` via `--input -` with
monkeypatched stdin)
- table output contains the summary labels and all four `[OPEN: ...]` markers
- `--format json`: `json.loads(capsys.out)` succeeds with no extra text on stdout, and
  carries every top-level key from section 7
- the JSON summary equals the values from calling `simulate()` directly with the same
  inputs — the real consistency assertion
- no hourly `soc` in the JSON falls below `asset.min_soc_mwh`, mirroring
  `tests/test_api.py::test_full_run_flow`
- `reserve_peak_mw < baseline_peak_mw` and `severity_reduction > 0` on the example
- `--window 1` simulates only the window (`len(daily) == window.days`)
- **`--lead-days` correctness, by equality against `charge_from_wind`.** Run
  `main(["--input", EXAMPLE, "--storage-mwh", "200000", "--power-mw", "2000",
  "--start-soc-mwh", "20000", "--window", "1", "--lead-days", "3", "--format", "json"])`.
  The oversized asset is deliberate: at the demo's 20,000 MWh sizing the mild days' wind
  fills the tank within hours, every lead-day count returns the same saturated SoC, and an
  equality assertion would pass against a broken slice. Assert, in order:
  1. `report["simulated"]["lead_days_used"] == 3`
  2. derive the expected lead days **from dates, not from the implementation's index
     arithmetic**: `days = read_day_profiles(...).days`;
     `start = find_stress_windows(days, cfg.default_severity_percentile,
     cfg.default_min_stress_window_days)[0].start`;
     `expected_lead = [d for d in days if start - timedelta(days=3) <= d.date < start]`;
     then assert `[d.date for d in expected_lead] == [start - timedelta(days=k) for k in
     (3, 2, 1)]`. Recomputing the slice as `days[max(0, w0 - 3):w0]` inside the test would
     reproduce any off-by-one in the code under test and prove nothing.
  3. `report["simulated"]["soc_at_window_start_mwh"] ==
     pytest.approx(charge_from_wind(20000.0, expected_lead, asset))`, with `asset =
     StorageAsset(total_mwh=200000, power_mw=2000)`
  4. `soc_at_window_start_mwh < asset.total_mwh` — proves the equality is discriminating
     rather than two saturated values agreeing
  5. the same run at `--lead-days 1` and `--lead-days 2` yields strictly smaller values, in
     order, so a slice shifted by one day changes the result
  A wrong-column read fails this as well: `charge_from_wind` reads `hourly_wind_mw`, so
  charging off load values lands nowhere near the expected number.
- `--lead-days 0 --window 1` → `soc_at_window_start_mwh == starting_soc_mwh` exactly, and
  `lead_days_used == 0`
- **lead-day shortfall.** `--window 1 --lead-days 99` on the example: only 3 days precede
  the window, so `lead_days_used == 3`, `soc_at_window_start_mwh` equals the `--lead-days 3`
  value, the shortfall note appears on stderr, and the exit code is 0. This exercises the
  `max(0, ...)` clamp.
- **`--window all --lead-days 2`, the positive path.** At the same oversized sizing:
  `report["simulated"]["window"] == "all"`; `date_start` equals the file's third date and
  `date_end` its sixth; `len(report["daily"]) == 4`; `lead_days_used == 2`; the lead is
  derived by date as `[d for d in days if d.date < date_start]` and asserted to be exactly
  the file's first two dates; `soc_at_window_start_mwh ==
  pytest.approx(charge_from_wind(20000.0, that_lead, asset))`; and
  `soc_at_window_start_mwh < asset.total_mwh`. This pins "trim the head of the file" as the
  intended semantics rather than leaving it to the error-case test alone.
- `--window all --lead-days 0` → the simulated span is the whole file and
  `soc_at_window_start_mwh == starting_soc_mwh`
- `--available-capacity-mw` set → `min_capacity_margin_mw` is a number; unset → `null`
- `--cycles-per-year 200` → `window_share_of_annual_cycles` is a number and
  `reporting.cycles_per_year == 200`; unset → both `null`
- `--list-windows` returns 0 without `--storage-mwh`/`--power-mw`, and prints the windows
- warnings land on `capsys.readouterr().err`, results on `.out`

*Exit codes*
- missing `--storage-mwh` without `--list-windows` → 2, message on stderr
- `--window 99` → 2
- `--efficiency 0` → 2 (from `StorageAsset`)
- `--priority-demand-weight 0.6 --priority-wind-weight 0.3` → 2 (from `Config`)
- `--start-soc-mwh` above `--storage-mwh` → 2
- `--lead-days` ≥ day count with `--window all` → 2
- `--cycles-per-year 0` → 2, and `--cycles-per-year -5` → 2
- `--storage-mwh nan` → 2, and `--power-mw inf` → 2 (the `_finite_float` type; without it
  both are accepted, confirmed against `models.py:39-45`)
- malformed CSV → 2

**Verify:**
```
uv sync --group dev
uv run pytest
uv run ruff check .
uv run simulate --input examples/synthetic_winter_stress.csv --storage-mwh 20000 --power-mw 2000
uv run simulate --input examples/synthetic_winter_stress.csv --storage-mwh 20000 \
  --power-mw 2000 --window 1 --lead-days 3 --start-soc-mwh 8000 --format json
uv run python -m owr --help
git check-ignore examples/synthetic_winter_stress.csv   # must exit 1 (not ignored)
git add examples/synthetic_winter_stress.csv            # so the diff below is meaningful
uv run python examples/make_synthetic_winter_stress.py  # regenerate over the tracked file
git diff --exit-code examples/synthetic_winter_stress.csv   # must exit 0: byte-identical
git status --short                                      # CSV and generator both appear
```

The `git add` before regenerating matters: `git diff` ignores untracked files, so without
it the byte-identity check would pass on a file that was never written.

Ruff: `line-length = 100`, rules `E, F, I, UP, B`, and it lints `examples/` along with
everything else. No new per-file ignores should be needed.

### Phase 5 — Documentation

**Files:** `README.md`, `docs/PLAN.md`, `docs/HANDOFF.md`.

- `README.md` Quickstart: add the `uv run simulate` example line next to the existing
  `uv run --with uvicorn uvicorn ...` line, and add `examples/` to the Layout block with a
  one-line note that the CSV is generated by the script beside it and that its column
  layout is provisional pending Phase 2 ETL.
- `docs/PLAN.md` Phase 3: note that item 7 now has a terminal entry point, with the
  module path.
- `docs/HANDOFF.md`: add the `simulate` invocation to "How to run it", and move the
  simulator CLI from "Next step" to the completed table with the verified test count.

No authoring metadata, tool names, or assistant references in any of these files.

## 10. Risks and assumptions

**Assumptions made, each visible in the output.**

1. **Deriving `demand_percentile` by empirical rank when the column is absent.** The
   `DayProfile` docstring defines it against a seasonal denominator, and `HANDOFF.md`
   records those denominators as underivable and forbids hard-coding them. The empirical
   CDF over the supplied series is the only derivation available from the input alone.
   It is warned on stderr and recorded as `demand_percentile_source` in the JSON. If some
   future ETL export supplies the column, the derivation stops firing; no such export
   exists today and the CSV layout is provisional (section 3).
2. **`wind_forecast_frac` defaults to 0.0** when the column is absent, which reduces
   `Priority(d)` to the demand term. Deriving it would need a wind nameplate capacity that
   is not an input.
3. **Full charge as the default starting SoC.** `--start-soc-mwh` defaults to
   `--storage-mwh`, matching `tests/test_simulator.py` ("fully charged pre-event"). The API
   instead requires an explicit `storage_start_mwh`; the CLI's default is a convenience,
   and it is printed.
4. **`--lead-days 0` by default**, so `initial_soc` is a no-op unless asked for. This keeps
   the default path byte-identical in sequencing to `api/app.py::create_run`. The engine
   loop's `initial_soc` stage is reachable and tested through `--lead-days N`.

**Risks.**

1. **The `.gitignore` `*.csv` rule silently drops the example file.** Verified against a
   scratch repository: adding `!examples/*.csv` re-includes it while leaving `data/` and
   root CSVs ignored. If the negation is skipped, everything passes locally and the
   documented demo command fails on a fresh clone. The Phase 4 verification includes an
   explicit `git check-ignore` check.
2. **The example's stress window depends on exact float equality across three daily
   totals.** Whole-number hourly loads make the sums exact regardless of order, and one
   non-integer value in those three days breaks the tie. The failure is silent:
   `--list-windows` prints an empty list and exits 0, and the demo command produces nothing
   to look at with no error to explain it. Two mitigations, both required. The file is
   written by `examples/make_synthetic_winter_stress.py`, which builds the tie by
   construction (hour 23 is the balancing remainder) and asserts the resulting one-window
   property through `find_stress_windows` before writing anything. The Phase 4 test
   re-asserts that property against the committed file, so a hand-edit is caught in CI even
   if nobody reruns the generator.
3. **`--efficiency` and the reserve fractions change behavior only through
   `StorageAsset`.** Nothing in the engine reads `Config.default_efficiency` or the two
   `Config` reserve fractions. Setting only `Config` would produce a run that reports one
   efficiency and simulates another. The JSON consistency test (JSON summary equals a
   direct `simulate()` call) is the backstop.
4. **DST days.** A 23- or 25-hour day fails the "exactly 24 rows per date" check with a
   clear message. `HOURS_PER_DAY = 24` is baked into `models.py` and `dispatch.py`, so
   this is an engine-level limitation, not a CLI one. `docs/PLAN.md` Phase 2 step 2 already
   owns DST handling.
5. **No committed real data exists**, so the shipped example is synthetic. The file states
   this in a comment banner and the table header prints its path. It must not be presented
   as ISO-NE output.
6. **The console script name `simulate` is generic** and installs into the environment's
   `bin/`. It follows the precedent set by `etl`. If the team objects, changing it is a
   one-line `pyproject.toml` edit plus the doc references.
7. **No subcommands.** The CLI has one action, so the surface is flat flags plus
   `--list-windows`. Adding a required subcommand later would break the flag-only form;
   that trade is accepted rather than scaffolding subcommands for hypothetical future
   commands.
8. **Non-finite floats reach the engine unnoticed.** `float("nan")` and `float("inf")`
   parse without raising, and the engine's guards catch them only where the check is
   written as a positive range — `StorageAsset(total_mwh=nan)` and
   `Config(priority_demand_weight=nan)` are both accepted today (confirmed by running
   them). A NaN then makes `d.load_mwh >= threshold` False for every day and propagates
   through the results with no exception. Both entry points reject non-finite values at the
   boundary: `math.isfinite` in the reader (section 3) and the `_finite_float` argparse
   type on every float flag (section 4). Tests cover both surfaces. Anything that later
   builds `Config` or `StorageAsset` from another source inherits the same hole and needs
   its own boundary check.
9. **The CSV layout has no counterpart in the schema.** Nothing in
   `db/migrations/001_init.sql` matches it and `docs/PLAN.md` Phase 2 defines no export
   step, so the reader and a future ETL export will have to be reconciled by whoever builds
   the export. The format is marked provisional in section 3, in the reader's docstring and
   in the README so it is not treated as a settled contract in the meantime.
