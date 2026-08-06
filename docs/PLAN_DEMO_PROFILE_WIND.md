# Plan — Real Wind in the Demo Profile — 2026-08-05 (revision 1)

Estimated cost: half a working day. Base commit: `b651f00` on `main`.

Revision 1 answers the adversarial review of revision 0. The revision log at the end
records each disposition.

## Goal

Make `etl demo-profile` carry a real hourly wind column, so the regenerated
`examples/real_winter_stress_2026.csv` feeds the engine's wind-dependent paths with
real Energy Information Administration (EIA) data.

The command that proves the change:

```
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 4320 --start-soc-mwh 20000 --lead-days 1 --format json
```

`simulated.soc_at_window_start_mwh` reads `20000.0` today. After this change it reads
`48794.0`, which is `20000 + 28794`, the real wind energy of 2026-01-24.

## What changed since `docs/PLAN_REAL_DEMO_BRIDGE.md`

That plan wrote "There is no real wind total to shape, so the plan shapes nothing."
The reason is now false. `data/wind_winter_2025_26.csv` holds 2,137 real EIA-930
hourly wind rows for the Independent System Operator New England (ISO-NE)
respondent, pulled 2026-08-06T03:08:39Z, `source = eia930.isne.wind`,
`dataset_version = gridstatus==0.36.0`. The file is git-ignored and local.

Measured 2026-08-05 **against that exact file**, over the target window 2026-01-24
to 2026-02-03:

| Date | Wind MWh | Wind min MW | Wind max MW |
|---|---|---|---|
| 2026-01-24 | 28794.0 | 783 | 1675 |
| 2026-01-25 | 13128.0 | 145 | 905 |
| 2026-01-26 | 18452.0 | 465 | 1038 |
| 2026-01-27 | 17924.0 | 332 | 1166 |
| 2026-01-28 | 19132.0 | 553 | 1166 |
| 2026-01-29 | 26824.0 | 809 | 1421 |
| 2026-01-30 | 30294.0 | 1119 | 1401 |
| 2026-01-31 | 16557.0 | 205 | 1159 |
| 2026-02-01 | 28196.0 | 938 | 1486 |
| 2026-02-02 | 24903.0 | 696 | 1473 |
| 2026-02-03 | 9205.0 | 45 | 861 |

All 11 local dates carry the full 24 hours. No daylight saving time (DST)
transition falls inside the window. Every `gen_mw` value is an integer, so a
3-decimal cell is exact.

**Every exact gate in this plan is a gate against that one file.** EIA revises
EIA-930 values after first publication. A fresh pull can move any number above. See
"Data refresh procedure" at the end of Phase 0 for what to do when a refresh is
wanted.

## Three decisions, made up front

### D1 — Emit `wind_mw` only. Do not emit `wind_forecast_frac`.

`wind_mw` is an hourly megawatt series. The rows are actual generation, and the
column takes them without a transform.

`wind_forecast_frac` is a per-date fraction of capacity. To derive it from actual
generation the code must divide by a wind nameplate capacity. This repository holds
no such number, so a value would be an invention. `src/owr/scenario_input.py` states
the same limit twice, and `owr.budget.priority` records that the sign convention of
the wind term is itself unsettled: the docstring says the wind term belongs in the
formula as `(1 - forecast)` while the code implements the literal weighted sum. A
made-up numerator inside a formula with an unsettled sign is worse than a zero.

Therefore: no nameplate constant in `src/owr/config.py`, no `wind_forecast_frac`
column, no proxy. `simulate` keeps its `wind_forecast_frac_source = "default-zero"`
warning, and `tests/test_sweep_cli.py` keeps asserting it.

Record the question in `docs/HANDOFF.md` under the identifier
`wind_forecast_frac_derivation`. Phase 2 registers it, in the same commit that first
ships the identifier in a banner.

### D2 — The in-window recharge term stays at 0.0 MWh. That is the correct result.

`owr.simulator.simulate` recharges from `max(0.0, wind[h] - max(0.0, net))`. In this
window wind runs 45 to 1,675 MW and load runs 14,341 to 20,127 MW. Wind never
exceeds net load in any hour, so the surplus is zero in every hour.

Measured 2026-08-05 on a wind-augmented copy of the profile: every summary field of
the default demo run is unchanged, including `energy_charged_mwh = 0.0` and
`recharge_opportunity_mwh = 0.0`. Only `input.has_wind` flips from `false` to `true`.

Do not scale the wind series. Do not change an engine default. Do not add a
recharge rule. A reserve that charges from a fleet one twentieth the size of system
load is a finding about ISO-NE, not a defect in this bridge.

The path that does change is `owr.initial_soc.charge_from_wind`, which charges from
raw hourly wind with no load subtraction. `simulate --lead-days N` reaches it. The
Goal command above measures it.

D2 has a reporting consequence. The default `--format table` run prints
`energy charged 0 MWh` and `wind forecast frac defaulted to 0.000 (column absent)`,
and it never states that `wind_mw` is present. A demo audience reads that as "no
wind data". Phase 4 fixes the report, not the engine.

### D3 — Reuse the load integrator for the wind series.

`demo_profile.hourly_loads_from_readings` integrates interval megawatt readings into
one bucket per local clock hour. It already rejects a naive timestamp and a
duplicate absolute instant, and it already converts to `America/New_York`. Wind is
the same shape of input, so it goes through the same function and returns the same
`HourlyLoad` type.

`HourlyLoad.load_mwh` therefore holds wind energy on the wind path. A parallel
dataclass would force a parallel integrator in a module that is already marked for
retirement. Name the reuse in the module docstring instead.

## Phase 0 — Unblock the wind rows CSV

**This phase blocks every later phase.** `read_rows_csv` cannot read
`data/wind_winter_2025_26.csv` today. Measured 2026-08-05:

```
RowsCsvError data/wind_winter_2025_26.csv: cannot parse as CSV: Length of header
or names does not match length of data.
```

Cause: `EIAWindSource.describe_query` returns a two-line string.
`rows_csv.write_rows_csv` writes it as `# source_query = <line 1>\n<line 2>\n`, so
line 7 of the file starts with `[api key read from` and carries no `#`. The reader
keeps that line and pandas reads it as the header.
`docs/PLAN_EIA_OIL_GAS.md` decision D5 already settled the convention for
`EIAFuelSource`: one line. The wind source never got it.

**Change 1.** `src/owr/etl/extract.py`, `EIAWindSource.describe_query`. Replace the
`\n` at the end of the first fragment with a single space:

```python
            f"facets={{respondent={self.respondent}, fueltype={self.fuel_type}}}) "
            f"[api key read from ${EIA_API_KEY_ENV}; value not recorded]"
```

**Change 2.** `src/owr/etl/provenance.py`, `Provenance.stamp`. Collapse newlines in
`source_query` at the one point where every extract batch creates its audit record:

```python
        return cls(
            source=source,
            source_query=" ".join(source_query.splitlines()),
            dataset_version=dataset_version,
            retrieved_at=retrieved_at or datetime.now(UTC),
        )
```

Document the reason in the `source_query` attribute docstring: a newline in this
value reaches both the CSV banner and every row's `source_query` cell, and both
readers work on physical lines. Every current value is already one line, so no
stored row and no committed artifact changes.

**Change 3.** `src/owr/etl/rows_csv.py`. Add a private helper and apply it to the
two provider-supplied banner values, `source_query` and `dataset_version`:

```python
def _one_line(value: str) -> str:
    """Collapse a multi-line banner value onto one ``#`` comment line.

    ``read_rows_csv`` keeps a line only when it does not start with ``#``. A value
    that carries a newline puts its tail on an uncommented line, and pandas then
    reads that line as the header. The file becomes unreadable by its own reader.
    Measured 2026-08-05 on ``data/wind_winter_2025_26.csv``, written by
    ``EIAWindSource`` before its ``describe_query`` became single-line.

    ``Provenance.stamp`` already collapses ``source_query``, so a stamped batch
    cannot reach here with a newline. This guard covers a ``Provenance`` built
    directly, which is what the tests do.

    One limit stays, and it predates this change: ``read_rows_csv`` filters
    **physical** lines, so a quoted data cell must not contain a line that is blank
    or starts with ``#``. Collapsing the provenance values removes the only source
    of a newline inside a cell that this repository produces.
    """
    return " ".join(value.splitlines())
```

Apply `_one_line` after `redact_secrets`, never before.

**Change 4.** Repair the local data file. `data/` is git-ignored, so this is a local
action and no commit records it. **This is the primary path.** It keeps the exact
bytes that every measured gate in this plan was taken against.

Run this once, from the repository root:

```
uv run python - <<'PY'
from pathlib import Path
p = Path("data/wind_winter_2025_26.csv")
lines = p.read_text().splitlines(keepends=True)
for i, line in enumerate(lines[:10]):
    if line.startswith("[api key read from"):
        lines[i] = "# " + line
        p.write_text("".join(lines))
        print("repaired line", i + 1)
        break
else:
    print("no repair needed")
PY
```

Read only the first 10 lines. The same text also appears inside every quoted
`source_query` data cell, and a whole-file replace would corrupt 2,137 rows.

The repair drops the `[api key ...]` suffix from the banner `source_query` value,
because that suffix moves onto its own comment line. No key value appears in either
form. `_read_provenance_banner` reads back the query text without the suffix, so
that is what the committed profile carries.

**Tests.**

| File | Test | Asserts |
|---|---|---|
| `tests/test_etl_eia.py` | Rename `test_wind_describe_query_is_deterministic` to `test_wind_describe_query_is_single_line_and_deterministic` | Add `assert "\n" not in a`, mirroring `tests/test_etl_eia_fuel.py` |
| `tests/test_etl_extract.py` | New: `test_stamp_collapses_a_multi_line_source_query` | `Provenance.stamp(source_query="line one\nline two", ...)` gives `"line one line two"`; a single-line value is unchanged |
| `tests/test_etl_rows_csv.py` | New: `test_multi_line_source_query_stays_on_one_banner_line` | Build a `Provenance` **directly**, not through `stamp`, with `source_query="line one\nline two"`. Write rows with `HOURLY_WIND`. Read the file back through `read_rows_csv` and assert the frame holds the written row count. Assert no line before the header both lacks `#` and holds text |

**Gate.** Run each command and make sure it passes.

```
uv run pytest tests/test_etl_eia.py tests/test_etl_extract.py tests/test_etl_rows_csv.py
uv run ruff check .
uv run python -c "from owr.etl.rows_csv import read_rows_csv; from owr.etl.extract import DATASETS; f=open('data/wind_winter_2025_26.csv'); print(read_rows_csv(f, DATASETS['wind'], origin='wind').shape)"
```

The last command must print `(2137, 8)`.

**Commit 1:** `Phase 0: single-line provenance, unblocking the wind rows CSV`

### Data refresh procedure — not part of this change

A fresh pull is the way to extend or update the wind window. It is **not** the way
to unblock this plan. EIA revises EIA-930 values after first publication, so a new
pull can change any measured number here: the day sums in "What changed", the
`(2137, 8)` shape gate, and the `48794.0` gate of Phase 3 Check 3.

When a refresh is wanted, run it as its own change, after this one lands:

```
uv run etl extract --dataset wind --start 2025-12-01 --end 2026-02-28 \
  --dry-run --out data/wind_winter_2025_26.csv
```

Then re-measure the "What changed" table and Phase 3 Check 3, update both, and
regenerate the artifact. Phase 3 Check 2 must still hold, because the load path does
not move.

## Phase 1 — The pure renderer gains an optional wind column

**Change:** `src/owr/etl/demo_profile.py`. The module stays pure. No file access, no
network, no database.

New signature:

```python
def render_day_profile_csv(
    hourly: Sequence[HourlyLoad],
    *,
    demand_percentile: Mapping[date, float],
    banner: Sequence[str],
    wind: Sequence[HourlyLoad] | None = None,
) -> str:
```

Rules, continuing the numbering of `docs/PLAN_REAL_DEMO_BRIDGE.md` Phase 1:

21. When `wind` is `None`, write the header `date,hour,load_mw,demand_percentile`
    and no wind cell. This is the existing behavior, unchanged.
22. When `wind` is a sequence, write the header
    `date,hour,load_mw,wind_mw,demand_percentile`. Put `wind_mw` after `load_mw`,
    so the two hourly series sit together and the per-date scalar stays last.
23. Every emitted `(date, hour)` pair must have one wind bucket. Raise `ValueError`
    with this message when one is absent:
    `f"{d.isoformat()} hour {hour}: no wind_mw value supplied"`.
24. Every wind bucket must cover `1.0 +/- _HOUR_TOLERANCE` hours. Raise `ValueError`
    with this message when it does not:
    `f"{d.isoformat()} hour {hour}: wind_mw covers {bucket.hours_covered:.4f} hours, expected 1.0 +/- {_HOUR_TOLERANCE}"`.
25. Put the two wind checks inside the existing per-date validation loop, in the
    `for hour in range(24)` body, **after** the load coverage check for that same
    hour. Position is what makes rule 24 safe to write without a DST branch: on a
    DST date the load checks raise first, and their messages already name DST.
26. Ignore a wind bucket whose date falls outside the emitted dates. The load series
    alone defines which dates the file carries.
27. Write the wind cell as `f"{avg_mw:.3f}"`, where
    `avg_mw = bucket.load_mwh / bucket.hours_covered`. This mirrors the load cell
    exactly.
28. Do not add a duplicate `(date, hour)` check for wind. The load path does not
    have one either, and `hourly_loads_from_readings` cannot produce a duplicate.

Update the module docstring. Replace the final paragraph, which reads "No
``wind_mw`` column is emitted here, and none is shaped. There is no real ISO-NE or
EIA wind series in this repository to shape one from." with this text:

```
``render_day_profile_csv`` emits an optional ``wind_mw`` column. The column is off
by default and appears only when the caller passes a ``wind`` rollup. The wind
series goes through ``hourly_loads_from_readings`` as well, because an EIA-930
hourly wind row and an ISO-NE five-minute load row are the same shape of input: a
timestamped megawatt value with a width. ``HourlyLoad.load_mwh`` therefore holds
wind energy on that path. A parallel dataclass would need a parallel integrator in
a module that ``docs/PLAN_SCENARIO_PROFILE_FORMAT.md`` already supersedes.

No ``wind_forecast_frac`` column is emitted, and none is derived. The rows are
actual generation, and a fraction of capacity needs a wind nameplate capacity that
this repository does not hold. See ``docs/PLAN_DEMO_PROFILE_WIND.md`` decision D1.
```

**Tests:** `tests/test_etl_demo_profile.py`. Keep every existing test. Keep
`test_render_output_contains_no_wind_column`, which calls the function without the
new keyword and now guards that the column stays off by default.

| # | Test | Asserts |
|---|---|---|
| 17 | Render one day with wind | Header is exactly `date,hour,load_mw,wind_mw,demand_percentile`; 24 data rows; hour 0 carries the supplied wind value |
| 18 | Render with wind, then read through `scenario_input.read_day_profiles` | `has_wind is True`; `wind_forecast_frac_source == "default-zero"`; each `DayProfile.hourly_wind_mw` value matches the input within `pytest.approx` |
| 19 | Render with a wind rollup missing hour 5 | Raises; the message names the date and `hour 5` |
| 20 | Render with a wind bucket covering 2.0 hours | Raises; the message names `wind_mw`, the date and the hour |
| 21 | Render a date whose load hour 1 **and** wind hour 1 both cover 2.0 hours | Raises; the message names DST and not `wind_mw`. This is the position-sensitive case: the 23-hour check runs before the hour loop, so only a shared coverage fault proves rule 25 |
| 22 | Render with wind buckets for a date outside `hourly` | Exits normally; the extra date appears in no data row |
| 23 | Render a wind value of `1186.0` | The cell reads exactly `1186.000` |

**Gate.**

```
uv run pytest tests/test_etl_demo_profile.py
uv run ruff check .
```

**Commit 2:** `Phase 1: optional wind_mw column in the day-profile renderer`

## Phase 2 — `--wind-input` on the `etl demo-profile` command

**Change:** `src/owr/etl/cli.py`. Keep the existing split: the command function owns
the file input and output, and `demo_profile.py` stays pure.

Add a module constant next to `_PROVENANCE_BANNER_KEYS`:

```python
# raw.hourly_wind carries no interval_minutes column, so the wind rows CSV carries
# no per-row width. The width is fixed by the frequency=hourly facet that each
# file's own source_query banner records (owr.etl.extract.EIAWindSource). This
# command does not read that facet back, so the width is an assumption about the
# input. It is not a silent one: render_day_profile_csv rule 24 rejects any bucket
# that does not cover 1.0 hour, so a five-minute series would build 12.0-hour
# buckets and raise.
_WIND_INTERVAL_HOURS = 1.0
```

Add the row adapter beside `_reading_from_row`:

```python
def _wind_reading_from_row(row: dict[str, str], origin: str) -> IntervalReading:
```

Rules for the adapter:

1. Parse `row["ts"]`. Reject a naive timestamp with the existing message:
   `f"{origin}: naive timestamp {ts_str!r} (row 'ts' must carry a UTC offset)"`.
2. Reject a blank `gen_mw` cell: `f"{origin}: blank gen_mw at ts={ts_str}"`.
3. Reject a non-finite `gen_mw` value: `f"{origin}: non-finite gen_mw at ts={ts_str}"`.
   `float("nan")` does not raise, and `owr.etl.extract.wind_observations_from_records`
   already rejects it at the provider boundary for the same reason.
4. Return `IntervalReading(ts=ts, load_mw=gen_mw, interval_hours=_WIND_INTERVAL_HOURS)`.

Add a second small helper so no bare parse error escapes:

```python
def _wind_horizon_days(row: dict[str, str], origin: str) -> int:
```

5. Return `int(row["horizon_days"])`. On `ValueError`, raise
   `f"{origin}: bad horizon_days {raw!r} at ts={row['ts']}"`. A bare `int("")` says
   only "invalid literal" and names neither the file nor the row.

Add the flag to the `demo-profile` subparser:

```python
    demo_profile_p.add_argument(
        "--wind-input",
        action="append",
        default=None,
        dest="wind_inputs",
        metavar="PATH",
        help="a wind rows CSV written by `etl extract --dataset wind --out` "
        "(repeatable; all inputs are pooled). Omit it to emit no wind_mw column. "
        "Only realized rows (horizon_days = 0) are read.",
    )
```

Use `default=None`, never `default=[]`. `argparse` appends to the default object
itself, so a shared list would leak values between parser instances. Normalize once
inside `_run_demo_profile` with `wind_inputs = args.wind_inputs or []`.

Extend `_run_demo_profile` after its existing step 8 (the load rollup and the
`[--start, --end]` filter):

9. For each wind input, read the file through
   `read_rows_csv(io.StringIO(text), DATASETS["wind"], origin=path)`.
10. Skip a file with zero data rows. Print the same
    `f"etl demo-profile: {path}: 0 data rows, skipping"` note to stderr.
11. Keep a row only when `_wind_horizon_days(row, path) == 0`. A value above zero
    marks a forecast row, and two rows at the same instant would make
    `hourly_loads_from_readings` raise a duplicate-instant error. Ignore
    `forecast_mw`.
12. Add each wind file's banner provenance tuple to the existing
    `provenance_tuples` set, through the existing `_read_provenance_banner` call.
13. Raise
    `ValueError("no realized (horizon_days = 0) wind rows in any --wind-input file")`
    when at least one wind input was given and no wind row survived. The message
    must not say "no data rows": an all-forecast file has data rows and still
    reaches here.
14. Build the rollup:
    `wind_hourly = [h for h in hourly_loads_from_readings(wind_readings) if args.start <= h.date <= args.end]`.
15. Pass `wind=wind_hourly` to `render_day_profile_csv` when wind inputs were given,
    and `wind=None` otherwise.

Extend `_demo_profile_banner`. Build the `Generated by:` line from both flag groups,
and join the parts with one space so the no-wind output keeps its exact current
bytes:

```python
    parts = [f"--input {path}" for path in args.inputs]
    parts += [f"--wind-input {path}" for path in (args.wind_inputs or [])]
    inputs_str = " ".join(parts)
```

Replace the three `ABSENT wind_mw` lines with a branch. Keep those three lines
verbatim when no wind input was given. Emit these lines instead when wind was
given, verbatim:

```
REAL  wind_mw: hourly wind generation, realized rows only (horizon_days = 0). One
      value per America/New_York wall-clock hour. No interpolation, no scaling.
      The producer, the query and the retrieval instant of every wind input are on
      the source lines below. A source that pivots an unreported hour to 0.0, as
      EIA-930 does, makes a 0.0 cell no proof of zero output.
ABSENT wind_forecast_frac: these rows are actual generation, not a forecast, and a
      fraction of capacity needs a wind nameplate capacity this repository does not
      hold. No proxy is emitted, so Priority(d) runs on the demand term alone
      [OPEN: wind_forecast_frac_derivation].
NOTE  wind is about 5% of ISO-NE system load in this window, 45 to 1,675 MW against
      14,341 to 20,127 MW. simulate's surplus-wind recharge is therefore 0.0 MWh in
      every hour. Pre-event charging through --lead-days does use these values.
```

The banner must not restate the respondent or the fuel type. This command never
reads them: it takes the `source` value from each input's banner and prints it on a
`source = ...` line below. A hard-coded "respondent ISNE, fuel type WND" would be an
unchecked claim about a file the command did not inspect.

Add one line to the stdout summary, after `population_days`:

```python
    print(f"  wind            = {wind_summary}")
```

where `wind_summary` reads `f"{len(wind_hourly)} hour(s) from {len(wind_inputs)} file(s)"`
when wind is present, and `"absent (no --wind-input)"` when it is not.

Update the `demo_profile_p` and `cmd_demo_profile` help text and docstring: the
command now emits `date,hour,load_mw,wind_mw,demand_percentile` when a wind input is
given.

**Also in this commit:** register the open question in `docs/HANDOFF.md`. The banner
above ships the identifier `[OPEN: wind_forecast_frac_derivation]`, so the entry that
resolves it must land in the same commit, never one commit later. Text:

> `wind_forecast_frac_derivation` — the day-profile format has a
> `wind_forecast_frac` column and this repository holds no wind nameplate capacity
> to derive it from. `owr.budget.priority` also disagrees with its own docstring
> about whether the term enters as the forecast or as `1 - forecast`. Settle both
> before any run reports a non-zero wind priority term.

**Tests:** `tests/test_etl_cli_demo_profile.py`. Build wind fixtures with
`write_rows_csv(str(path), DATASETS["wind"], rows, prov)`, exactly as the load
fixtures are built. Every fixture stays offline. No network, no credential, no
database.

| # | Test | Asserts |
|---|---|---|
| 11 | End to end with one wind fixture | Exit 0; the output parses through `read_day_profiles`; `has_wind is True`; each hour's `hourly_wind_mw` matches the fixture |
| 12 | No `--wind-input` | `has_wind is False`; the output header carries no `wind_mw` |
| 13 | Wind banner | The text holds `source = eia930.isne.wind` and the line `REAL  wind_mw` |
| 14 | Wind fixture missing one hour of one selected date | Exit 2; stdout starts with `error:`; the message names the date and the hour |
| 15 | Wind fixture holding both `horizon_days = 0` and `horizon_days = 1` rows at the same instant | Exit 0; the emitted cell carries the realized value |
| 16 | Wind fixture holding only `horizon_days = 1` rows | Exit 2; the message says `no realized (horizon_days = 0) wind rows` |
| 17 | Wind fixture with a `horizon_days` cell of `"x"` | Exit 2; the message names the file and the timestamp |
| 18 | A load rows CSV passed to `--wind-input` | Exit 2; the message names the header mismatch |
| 19 | Wind fixture with a blank `gen_mw` cell | Exit 2; the message names the timestamp |
| 20 | Wind fixture with zero data rows, and no other wind input | Skip note on stderr; then exit 2 |
| 21 | Banner `Generated by:` line | Holds `--wind-input <path>` after every `--input <path>` |
| 22 | Two runs with the same wind fixture | Produce byte-identical output |
| 23 | Parser wiring | `--wind-input a --wind-input b` gives `args.wind_inputs == ["a", "b"]`; the flag absent gives `None` |

**Gate.**

```
uv run pytest tests/test_etl_cli_demo_profile.py
uv run pytest
uv run ruff check .
```

**Commit 3:** `Phase 2: --wind-input on etl demo-profile`

## Phase 3 — Regenerate and commit the artifact

Run exactly this, from the repository root:

```
uv run etl demo-profile \
  --input data/load_2023.csv --input data/load_2024.csv \
  --input data/load_2025.csv --input data/load_2026.csv \
  --wind-input data/wind_winter_2025_26.csv \
  --start 2026-01-24 --end 2026-02-03 \
  --out examples/real_winter_stress_2026.csv
```

Expect 264 data rows and about 14 kilobytes. `.gitignore` carries `*.csv` with a
`!examples/*.csv` exception, so the file commits.

The banner now carries five provenance pairs, not four. The command sorts them, and
`eia930.isne.wind` sorts before `gridstatus.isone.load`, so the wind pair prints
first. That reordering is expected.

**Check 1, the day totals.** Each date's 24 `wind_mw` cells must sum to the Wind MWh
column of the table in "What changed" above, exactly. Every `gen_mw` value in that
file is an integer, so no rounding tolerance applies. A mismatch means the local file
is not the one this plan was measured against; read "Data refresh procedure".

**Check 2, the default demo run is unchanged.** Every number below was measured
2026-08-05 both before and after a wind column was added to this file. A field that
moves means the wind column leaked into the load path. Investigate before you ship.

```
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 4320 --format json
```

| JSON field | Expected |
|---|---|
| `input.days_read` | 11, 2026-01-24 to 2026-02-03 |
| `input.has_wind` | `true` (was `false`) |
| `input.demand_percentile_source` | `"file"` |
| `input.wind_forecast_frac_source` | `"default-zero"` |
| `summary.baseline_peak_mw` | 20126.584 |
| `summary.reserve_peak_mw` | 19912.576 |
| `summary.severity_reduction` | 0.010633 |
| `summary.energy_discharged_mwh` | 40729.644 |
| `summary.energy_charged_mwh` | 0.0 |
| `summary.recharge_opportunity_mwh` | 0.0 |
| `summary.final_soc` | 19270.356 |
| `summary.equivalent_full_cycles` | 0.678827 |

Tolerance +/- 0.01 on every numeric field.

**Check 3, the wind path runs.** This is the point of the change.

```
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 4320 \
  --start-soc-mwh 20000 --lead-days 1 --format json
```

| JSON field | Before | After |
|---|---|---|
| `simulated.soc_at_window_start_mwh` | 20000.0 | 48794.0 |
| `summary.energy_discharged_mwh` | 1934.898 | 29791.617 |
| `summary.severity_reduction` | 0.000545 | 0.008390 |
| `summary.final_soc` | 18065.102 | 19002.383 |

`48794.0` is exact: the starting state of charge plus the whole 28,794 MWh of
2026-01-24 wind. Round-trip efficiency is 1.0, the 4,320 MW power cap never binds
against a 1,675 MW peak, and 40,000 MWh of headroom exceeds the day's wind energy.

**Commit 4:** `Phase 3: regenerate the real demo profile with EIA wind`

## Phase 4 — The table report, and documents

### 4a — `_render_table` states whether `wind_mw` is present

`src/owr/cli.py` builds `input.has_wind` into the report and the JSON, and
`_render_table` never prints it. The Inputs block therefore says
`wind forecast frac   defaulted to 0.000 (column absent)` and nothing else about
wind, and the Summary says `energy charged 0 MWh`. On a real-wind file a reader
concludes the file has no wind. Fix the report.

Add this block immediately **before** the existing `wind_forecast_frac_source`
block, so the two wind facts read together:

```python
    if inp["has_wind"]:
        out.write("  wind_mw              present (hourly series, from file)\n")
    else:
        out.write("  wind_mw              absent (column not in file)\n")
```

The label column is 21 characters wide in this block. `"  wind_mw"` plus 14 spaces
puts the value at the same column as its neighbours.

Change nothing else in `cli.py`. No new flag, no engine call, no JSON key:
`has_wind` is already in the report dictionary.

**Tests:** `tests/test_cli.py`.

| # | Test | Asserts |
|---|---|---|
| 1 | Table run over `examples/synthetic_winter_stress.csv`, which carries `wind_mw` | stdout holds `wind_mw              present` |
| 2 | Table run over a `tmp_path` CSV with `date,hour,load_mw` only, 24 rows | stdout holds `wind_mw              absent` |

### 4b — Documents

1. `README.md` line 52. Replace
   `# same command, over a real 11-day ISO-NE winter stress event (no wind data; see below)`
   with
   `# same command, over a real 11-day ISO-NE winter stress event (real load and wind)`.
2. `README.md`, the `examples/real_winter_stress_2026.csv` paragraph. Replace
   "it carries no wind column, since no real wind series exists in this repository, and"
   with: "it carries a real EIA-930 hourly wind column and no `wind_forecast_frac`
   column, and". Then add these two sentences, which keep the demo narration honest
   about D2:

   > Wind runs about 5% of system load in this window, so the in-window recharge term
   > is 0.0 MWh and the table prints `energy charged 0 MWh`. To see the wind series do
   > work, add `--start-soc-mwh 20000 --lead-days 1`: the report's pre-event charging
   > block then reads 20,000 MWh to 48,794 MWh.

3. `docs/HANDOFF.md`. Append a session block with three items. The fourth item, the
   `wind_forecast_frac_derivation` entry, already landed in commit 3.
   - The EIA extractor has now run. `data/wind_winter_2025_26.csv` holds 2,137
     realized EIA-930 hourly wind rows for 2025-12-01 to 2026-02-28, ISO-NE
     respondent. It is git-ignored and lives on one machine. Every exact figure in
     `docs/PLAN_DEMO_PROFILE_WIND.md` is a figure against that file, and EIA revises
     EIA-930 after publication.
   - The Phase 0 local banner repair ran against that file. Name the alternative,
     `etl extract --dataset wind`, and say that a refresh needs the plan's measured
     tables re-taken.
   - The retirement list for `docs/PLAN_SCENARIO_PROFILE_FORMAT.md` grows: that
     redesign must now carry the `wind_mw` column of
     `examples/real_winter_stress_2026.csv` as well as the load column.
4. `CLAUDE.md`: no change. The `demo_profile.py` row still describes the module
   correctly, and the new plan document is already covered by the `docs/PLAN_*.md`
   row.
5. `docs/BOARD.md`: no change. It is a synced job board, not a place for this state.
6. `docs/DATA_SOURCES.md`: no change. The EIA hourly series is already registered as
   the canonical wind source, resolved 2026-07-28.

**Gate.**

```
uv run pytest
uv run ruff check .
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 4320 --start-soc-mwh 20000 --lead-days 1
```

The last command must print `wind_mw              present` in the Inputs block and
`20,000 MWh -> 48,794 MWh over 1 lead day(s)` in the pre-event charging block.

**Commit 5:** `Phase 4: report and docs for real wind in the demo profile`

## Verification

Run in this order.

```
uv run ruff check .
uv run pytest
uv run simulate --input examples/synthetic_winter_stress.csv \
  --storage-mwh 20000 --power-mw 2000
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 4320 --format json
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 4320 --start-soc-mwh 20000 --lead-days 1 --format json
uv run sweep --input examples/real_winter_stress_2026.csv --power-mw 4320 \
  --sizes-mwh 60000 --format json
```

Pass conditions:

- `ruff` reports `All checks passed`.
- `pytest` reports the 572-passed baseline plus the new tests, and 4 skipped.
- The synthetic demo prints the output it printed before this change, plus the one
  new `wind_mw              present` line.
- The first JSON run matches the Phase 3 Check 2 table within +/- 0.01.
- The second JSON run matches the Phase 3 Check 3 "After" column.
- The sweep run still reports `severity_reduction` of 0.010633, which
  `tests/test_sweep_cli.py` also asserts.
- `git status` shows no change under `src/owr/scenario_input.py`,
  `src/owr/config.py`, `src/owr/models.py`, `src/owr/simulator.py`,
  `src/owr/initial_soc.py`, `src/owr/budget.py`, `src/owr/metrics.py`,
  `examples/synthetic_winter_stress.csv`, or
  `docs/PLAN_SCENARIO_PROFILE_FORMAT.md`.

## Risks, ranked

1. **Phase 0 blocks everything.** The wind rows CSV on disk is unreadable by its own
   reader, measured 2026-08-05. An implementer who starts at Phase 1 hits a header
   mismatch in Phase 3 and can misread it as a bug in the new code.
2. **A fresh EIA pull can break the exact gates.** EIA revises EIA-930 after first
   publication. Every wind figure here is measured against one local file. The Phase
   0 repair keeps that file byte for byte; the refresh procedure is deliberately
   outside this change and carries a re-measurement step.
3. **Zero in-window recharge reads like a failure.** `energy_charged_mwh` stays 0.0
   after the change. The cause is physical, not a defect: wind is about 5% of load.
   Decision D2, the banner NOTE line, the new `wind_mw present` report line and the
   README sentences all state it. Do not scale the series to make the number move.
4. **The regenerated artifact must not move the recorded simulator numbers.** Phase 3
   Check 2 is the guard. `tests/test_sweep_cli.py` pins 0.010633 independently.
5. **A future wind pull could carry forecast rows.** `horizon_days` above zero would
   put two rows at one instant and raise a duplicate-instant error. The
   `horizon_days == 0` filter and CLI tests 15 to 17 cover it.
6. **The one-hour interval width is an assumption.** The wind table carries no
   `interval_minutes` column, and this command does not read the `frequency=hourly`
   facet back out of the banner. Renderer rule 24 turns a wrong width into a loud
   error, not a silent multiplicative one.
7. **A zero cell can mean "no telemetry".** `gridstatus` sums an all-null group to
   zero, so an unreported EIA-930 hour arrives as `0.0`. The measured minimum in this
   window is 45 MW, so no zero appears. The banner states the limit.
8. **The bridge is still disposable.** `docs/PLAN_SCENARIO_PROFILE_FORMAT.md`
   supersedes this module and now inherits one more column to carry. Phase 4 item 3
   records it. Do not open or edit that plan.
9. **Only the holder of `data/` can regenerate the artifact.** Unchanged by this
   work, already recorded in `docs/HANDOFF.md`. Continuous integration runs the
   tests and never regenerates the file.
10. **The banner grows by about eight lines.** `scenario_input.read_day_profiles`
    skips every `#` line, so no reader is affected. Keep every added line inside the
    100-character `ruff` limit.

## Out of scope

Do not add a wind nameplate constant to `src/owr/config.py`. Do not emit a
`wind_forecast_frac` column. Do not change `src/owr/scenario_input.py`,
`src/owr/models.py`, `src/owr/simulator.py`, `src/owr/initial_soc.py`,
`src/owr/budget.py`, `src/owr/metrics.py`, `src/owr/sweep.py`, or anything under
`src/owr/api/`. The only change to `src/owr/cli.py` is the two-branch Inputs line of
Phase 4a. Do not scale, smooth, interpolate or forecast the wind series. Do not
change an engine default to make the recharge term non-zero. Do not open or edit
`docs/PLAN_SCENARIO_PROFILE_FORMAT.md`. Do not edit `docs/BOARD.md`.

## Revision log

Revision 1, 2026-08-05, after adversarial review of revision 0.

| # | Finding | Disposition |
|---|---|---|
| M1 | The "preferred" re-pull path can invalidate the plan's own exact gates | **Accepted.** The local banner repair is now Phase 0 Change 4 and the primary path. The re-pull moved to "Data refresh procedure", outside this change, with a re-measurement step. New risk 2, and a warning under the "What changed" table |
| M2 | The table report contradicts the README claim in front of a demo audience | **Accepted.** New Phase 4a adds a two-branch `wind_mw` line to `_render_table` and two tests. The README wind sentences now point at the `--lead-days 1` command. D2 gained a reporting paragraph, and the out-of-scope list names the one allowed `cli.py` change |
| m1 | The `[OPEN: wind_forecast_frac_derivation]` identifier ships two commits before it is registered | **Accepted.** The `docs/HANDOFF.md` entry moved into Phase 2, the same commit that ships the banner. Phase 4 keeps the other three items |
| m2 | `_one_line` guards the banner only; data cells and the physical-line filter stay exposed | **Accepted.** New Phase 0 Change 2 collapses `source_query` in `Provenance.stamp`, which covers the banner, every row cell and the database column. `_one_line` stays as the guard for a directly-built `Provenance`, and its docstring names the residual physical-line limit |
| m3 | Step 13's message says "no data rows" for a file that has data rows | **Accepted.** The message is now "no realized (horizon_days = 0) wind rows in any --wind-input file". New CLI test 16 |
| m4 | A bad `horizon_days` cell raises a bare `int()` error | **Accepted.** New `_wind_horizon_days` helper, adapter rule 5, and CLI test 17 |
| m5 | The banner hard-codes a respondent and a fuel type the command never reads | **Accepted.** The banner now points at the `source = ...` lines it does emit, and states the zero-cell caveat without claiming a producer. A paragraph forbids restating the respondent |
| m6 | Rule 24's DST reasoning depends on an unstated check position | **Accepted.** New rule 25 fixes the position inside the existing per-date loop, after the load coverage check. New renderer test 21 proves the load message wins on a 23-hour date |
