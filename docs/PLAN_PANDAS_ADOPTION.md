# Plan — pandas and NumPy adoption

Date: 2026-08-05. Status: revision 1, ready to implement. Type: data-structure refactor.

## Revision log

**Revision 1, 2026-08-05, after adversarial review of revision 0.** The numeric core held:
200000 adversarial trials produced zero stress-set flips, the caller inventory was confirmed
complete, and the baseline stands at 323 passed and 3 skipped. Two findings blocked. Both are
resolved below.

| Finding | Disposition |
|---|---|
| B1. The event frame drops a winter label that has zero windows, so the JSON payload loses a key that is emitted today. | Fixed. `transform.winter_labels()` is new, phase 5b. The ETL CLI emits one entry per label with an empty list. New CLI test, phase 5 test 10. |
| B2. Over-long rows and unclosed quotes change acceptance, and the behavior depends on row position. | Fixed. Both readers now promote `ParserWarning` to an error, so every over-long row is rejected at any position. Recorded as an admitted acceptance change, phases 4b and 6. The phase 6 goal wording is corrected. |
| N1. Risk 9 understates the collision with the scenario format plan. | Fixed. Risk 10 now names the header-check insertion point and the `csv.DictReader` wording. |
| N2. The purity rewording would equally permit `import psycopg`. | Fixed. The rule is now an allowlist of two libraries. |
| N3. Three orphaned imports missing from the lint-trap table. | Fixed. `DailyLoad`, `season_for` and `winter_label` added. |
| N4. An all-`None` column infers `object` dtype, so `isna().all()` passes on a wrong dtype. | Fixed. Phase 3 mandates `dtype="float64"` construction and phase 3 test 4 asserts the dtype. |
| N5. Phase 3 test 2 as written cannot pass for `capacity_margin`. | Fixed. Test 2 now runs with `available_capacity_mw` set. |
| N6. The empty-file guard in `read_rows_csv` was left ambiguous. | Fixed. Phase 4b now keeps it explicitly and states the message it protects. |
| N7. Unlisted improvement: a missing trailing cell moves from a traceback to a clean exit 2. | Recorded as admitted change A3, phase 4c. |
| Nit a. A blank header cell becomes `Unnamed: <position>` under pandas. | Recorded, phase 6 and risk 9. |
| Nit b. Risk 1 hedged after asserting impossibility. | Fixed. The structural argument replaces the hedge and moves into the phase 2 docstring. |

---

## What this plan does

The team asked for `pandas.DataFrame` at the component data contracts, and for Python
dataclasses to hold the system state. This plan puts `pandas` and `numpy` into the real
project dependencies, replaces the hand-rolled percentile with `numpy.quantile`, and makes a
`DataFrame` the exchange format at four tabular boundaries:

1. The raw rows table that `etl transform` reads.
2. The daily rollup table that the ETL (extract, transform, load) pipeline produces.
3. The stress event table that stress detection produces.
4. The hourly and daily simulation result tables.

Scalar state stays on the frozen dataclasses in `src/owr/models.py`. Per hour engine
arithmetic in `dispatch.py`, `soc_engine.py`, `budget.py` and `metrics.py` stays on scalars.

## What this plan does not do

| Item | Reason |
|---|---|
| Typer, Rich, Matplotlib, Plotly, mypy | Out of scope for this pass, by instruction. |
| Pydantic changes | Pydantic stays in the API (application programming interface) layer. |
| A Component 7 metrics table | The doc lists capital cost, robustness score and cycle mismatch fields that no code computes. A table of them is a new feature, not a refactor. |
| A new Component 4 state dataclass | `models.py` already holds the world state. The doc's `dispatch_history`, `recharge_history` and `charging_window_remaining` fields are unmodeled. Record the gap, add nothing. |
| A pandas rewrite of energy accumulation | Measured: `groupby.sum()` uses compensated summation and differs from Python `sum()` in about 1 case in 75 at 288 values. See risk 11. |
| `event_id` and `winter_id` hash columns | The architecture doc calls them hash values and defines no hash. Do not invent one. |
| `write_rows_csv` on pandas | A `DataFrame` maps `None` to `NaN` and promotes an integer column to float. See risk 5. |

## Admitted behavior changes

This is a refactor, and every numeric result stays the same. Four non-numeric behaviors do
change. Each one is deliberate, and each has a test that pins it.

| # | Change | Where | Pinned by |
|---|---|---|---|
| A1 | A data row with more fields than the header is now rejected, at any row position. `csv.DictReader` accepted it and dropped the extra field. | Phases 4b and 6 | Phase 4 test 3, phase 6 test 2 |
| A2 | A CSV (comma separated values) file with an unclosed quoted field is now rejected. `csv.DictReader` swallowed the rest of the file into one field. | Phases 4b and 6 | Phase 4 test 4, phase 6 test 3 |
| A3 | A row missing its trailing cell now exits 2 with a clean message instead of a traceback. Today the cell is `None`, `float(None)` raises `TypeError`, and `cmd_transform` catches only `OSError` and `ValueError`. After phase 4 the cell reads back `""` and `float("")` raises `ValueError`. | Phase 4c | Phase 4 test 5 |
| A4 | A header that repeats a column name now resolves to the first occurrence. `csv.DictReader` kept the last. Neither reader raises. | Phase 6 | Phase 6 test 1 |

A1 and A2 reject files that parse today. Both inputs are malformed, and both were silently
mishandled before. Raise them with the team if any real input file is affected. Nothing in
`examples/` or `tests/` is affected; the phase 4 and phase 6 test runs prove that.

## Measurements this plan relies on

The planner ran these against the repository venv (pandas 2.3.3, numpy 2.5.1). Treat them as
facts, not guesses. The implementer does not need to repeat them.

| # | Measurement | Result |
|---|---|---|
| M1 | `numpy.quantile(v, p)` against the current `percentile_threshold(v, p)`, 20000 random cases | 471 differ, worst relative difference 1.08e-15 |
| M2 | `numpy.percentile(v, p*100)` against the same | 1831 differ. `quantile` is the better call |
| M3 | `json.dumps(numpy.float64(2.5))` | Works. `numpy.float64` subclasses `float` |
| M4 | `json.dumps(numpy.int64(3))` | Raises `TypeError: Object of type int64 is not JSON serializable` |
| M5 | `pandas.read_csv(dtype=str, na_filter=False)` | Every cell is a `str`. A blank cell reads back as `""` |
| M6 | `read_csv(index_col=False)` with a data row longer than the header | **First** data row: parses, drops the extra field, emits `ParserWarning`. **Later** data row: raises `ParserError("Expected 3 fields in line 3, saw 4")`. Without `index_col=False` the first-row case silently shifts every column left |
| M7 | `DataFrame` column built from `datetime.date` objects | Stays `object` dtype, survives `itertuples` and `groupby` |
| M8 | `DataFrame` column built from a mix of `int` and `None` | Becomes `float64`, `None` becomes `NaN` |
| M9 | `to_csv(index=False, lineterminator="\r\n")` against `csv.writer` output | Byte identical, for both the in-memory string form and a real path write |
| M10 | `pandas.groupby.sum()` against Python `sum()`, 3000 cases of 288 floats | 40 differ. `numpy.sum` is worse: 970 differ |
| M11 | `pandas.errors.ParserError` and `EmptyDataError` | Both subclass `ValueError`. `ParserWarning` does **not**; it subclasses `Warning` |
| M12 | Duplicate header name | pandas renames to `load_mw.1`, first wins; `csv.DictReader` kept the last |
| M13 | `read_csv` with `warnings.simplefilter("error", ParserWarning)` | Every over-long row raises, at any position. Short rows and normal rows still parse |
| M14 | `read_csv` with an unclosed quoted field | Raises `ParserError("EOF inside string starting at row 1")` |
| M15 | Blank header cell | pandas names the column `Unnamed: <position>`; `csv.DictReader` named it `""` |
| M16 | `pandas.Series([None, None])` dtype | `object`, and `isna().all()` returns `True` on it |
| M17 | `float(None)` and `float("")` | `TypeError` and `ValueError` |

## Baseline to hold

`docs/HANDOFF.md` records the current state: `uv run pytest` gives 323 passed and 3 skipped,
`uv run ruff check .` passes, and the example CSV file is byte identical after the generator
runs. Every phase must keep all three true.

Before phase 1, capture the whole pipeline numeric baseline:

```bash
uv run simulate --input examples/synthetic_winter_stress.csv \
  --storage-mwh 20000 --power-mw 2000 --format json > /tmp/owr_baseline.json
```

After every phase, run the same command into `/tmp/owr_phaseN.json` and compare with
`code_version` and `generated_at` removed:

```bash
python - <<'PY'
import json
drop = ("code_version", "generated_at")
a = json.load(open("/tmp/owr_baseline.json")); b = json.load(open("/tmp/owr_phaseN.json"))
for k in drop: a.pop(k, None); b.pop(k, None)
print("IDENTICAL" if a == b else "CHANGED")
PY
```

This command must print `IDENTICAL` after every phase.

**This gate does not cover `etl transform`.** The simulator CLI (command line interface) never
calls the ETL modules. Phase 5 therefore carries its own byte-level and payload-level tests;
do not treat the `IDENTICAL` result as coverage for the ETL output.

---

## Phase 1 — Dependencies and the purity rule

Goal: pandas and numpy become real runtime dependencies. Every claim of "no third party
dependency" gets corrected. No logic changes.

### Files

**`pyproject.toml`.** Replace `dependencies = []` with:

```toml
dependencies = [
    "pandas>=2.2",
    "numpy>=1.26",
]
```

Replace the comment above `[project.optional-dependencies]` with text that states the new
rule: the engine takes pandas and numpy as data structure and numeric dependencies, and stays
free of file access, network access, database access and provider code, so it remains fully
testable offline before any ISO-NE or EIA (Energy Information Administration) credential
exists.

**the repo map.** Replace the first Conventions bullet with:

```
- Engine core stays pure: no file or network access, and no database. Third-party
  imports in the engine core are limited to an allowlist of exactly two libraries,
  `pandas` and `numpy`. No database driver, no provider client, no HTTP library, and
  no import of `owr.api` or `owr.etl` below the CLI and API layers. `pandas.read_csv`
  is file access and belongs only in a module that already takes a stream or a path.
```

The allowlist form is deliberate. A rule phrased as "the import opens no file or socket" would
equally permit `import psycopg`, which the repo forbids below the CLI and API layers.

Also change the "Engine core (pure, no I/O, no DB)" heading above the module table to
"Engine core (no file, network or database access; pandas and numpy allowed)".

**Docstrings that must change.** Each one currently makes a claim that this phase makes false:

| File | Line | Current claim | Required correction |
|---|---|---|---|
| `src/owr/__init__.py` | 3 | "Pure-Python, no I/O in the core" | Drop "Pure-Python". Keep the no I/O claim. |
| `src/owr/etl/__init__.py` | 13 | "no `gridstatus`/`pandas` install required" | "no `gridstatus` install and no credentials required". |
| `src/owr/etl/daily.py` | 3 | "Pure; stdlib `zoneinfo` only, no new dependency." | "Pure; no file, network or database access. Uses stdlib `zoneinfo` and `pandas`." |
| `src/owr/stress_finder.py` | 16-19 | "without a numpy dependency" | Rewritten in phase 2. Leave it alone here. |
| `tests/test_etl_extract.py` | 3 | "no gridstatus, no pandas, no ..." | "no gridstatus and no credentials". |
| `README.md` | 17 | "Simulation engine (pure Python, ...)" | "Simulation engine (no I/O, ...)". |

### Steps

1. Edit `pyproject.toml` as above.
2. Run `uv lock` to regenerate `uv.lock`.
3. Run `uv sync --group dev`.
4. Confirm pandas and numpy install as project dependencies, not only as gridstatus extras:
   `uv run python -c "import pandas, numpy; print(pandas.__version__, numpy.__version__)"`.
5. Apply the six docstring and text corrections above.

### Verify

```bash
uv run pytest          # 323 passed, 3 skipped
uv run ruff check .
```

Time: about 20 minutes.

---

## Phase 2 — NumPy percentile in `stress_finder`

Goal: `percentile_threshold` delegates to `numpy.quantile`.

### Interface

`src/owr/stress_finder.py`:

```python
def percentile_threshold(values: Sequence[float], percentile: float) -> float:
```

The signature widens from `list[float]` to `Sequence[float]` so `transform.py` can pass a
NumPy array in phase 5. The return type stays `float`, and the body casts.

Body, in this exact order. The two guards must stay ahead of the NumPy call, because
`numpy.quantile` raises `IndexError` on an empty input and its own `ValueError` text for a
percentile outside `[0, 1]`:

```python
if len(values) == 0:
    raise ValueError("values must be non-empty")
if not 0.0 <= percentile <= 1.0:
    raise ValueError("percentile must be in [0, 1]")
return float(np.quantile(np.asarray(values, dtype=float), percentile, method="linear"))
```

`if not values` must become `len(values) == 0`. A NumPy array raises on truth testing.

New docstring, which replaces the "without a numpy dependency" claim:

```
Linear-interpolation percentile, computed by ``numpy.quantile`` with the default
``'linear'`` method. ``percentile`` is a fraction in [0, 1], which is what
``numpy.quantile`` takes, so no rescale to 0..100 is needed.

The result can differ from a hand-written ``lo + (hi - lo) * frac`` by a few units
in the last place. NumPy uses that same form when ``frac`` is below 0.5, so those
results are bit identical; at or above 0.5 it uses ``hi - (hi - lo) * (1 - frac)``,
which rounds differently. Measured 2026-08-05 over 20000 random series: 471 of
20000 results differ, worst relative difference 1.08e-15.

**A stressed-day comparison cannot flip.** The difference between the two forms
comes from rounding the product ``(hi - lo) * frac``, so it appears only when the
gap ``hi - lo`` is wide enough for that product to round. The threshold lies between
two adjacent values of the sorted population, so no other daily total lies between
them, and the nearest candidate for a flip is ``lo`` itself, at distance
``(hi - lo) * frac``, which is at least half the gap. A flip therefore needs a gap
of a few units in the last place, and at that width both products are exactly
representable and both forms return the same value. The two conditions exclude each
other. Confirmed 2026-08-05 by 200000 adversarial trials with zero stress-set flips.
```

### Tests — `tests/test_stress_finder.py`

Keep every existing test. Add:

1. `test_percentile_matches_reference_implementation`. Hold a local copy of the retired
   formula in the test file. Compare it against `percentile_threshold` over a seeded random
   sweep (seed 7, 2000 cases, series length 2 to 40, values 0 to 600000, percentile drawn from
   `random.random()` plus the fixed set 0.0, 0.5, 0.75, 0.9, 0.95, 1.0). Assert
   `pytest.approx(expected, rel=1e-12)`. Do not assert exact equality; measurement M1 shows it
   fails.
2. `test_percentile_returns_builtin_float`. Assert `type(percentile_threshold([1.0, 2.0], 0.5)) is float`.
   This pins the cast that keeps `json.dumps` safe.
3. `test_percentile_accepts_a_numpy_array`. Pass `numpy.array([1.0, 2.0, 3.0, 4.0])` and assert
   the result is 2.5. This pins the `len(values) == 0` guard change.
4. `test_percentile_empty_raises_value_error` and `test_percentile_out_of_range_raises_value_error`.
   Match on the existing message text so the guard order stays fixed.
5. `test_stress_set_is_unchanged_under_the_new_percentile`. Over the same seeded sweep, compute
   the retired threshold and the new threshold, then assert
   `[v >= old for v in values] == [v >= new for v in values]`. This is the property the
   docstring claims, expressed as a test.

### Verify

```bash
uv run pytest tests/test_stress_finder.py tests/test_etl_transform.py tests/test_cli.py
uv run pytest
uv run ruff check .
```

Then run the whole pipeline JSON (JavaScript Object Notation) comparison from the baseline
section. It must print `IDENTICAL`.

Time: about 45 minutes.

---

## Phase 3 — Simulation result frames

Goal: `SimulationResult` gains two `DataFrame` views. Purely additive. No existing caller
changes.

### Interface

`src/owr/simulator.py`:

```python
HOURLY_FRAME_COLUMNS: tuple[str, ...] = (
    "date", "ts_hour", "soc", "charge", "discharge", "discharge_peak",
    "discharge_smooth", "gross_load", "net_load", "capacity_margin",
)
DAILY_FRAME_COLUMNS: tuple[str, ...] = (
    "date", "budget", "priority", "usable_energy", "recharge_sufficiency_ratio",
)

@dataclass
class SimulationResult:
    daily: list[DailyResult]
    final_soc: float
    baseline_peak_mw: float
    reserve_peak_mw: float

    def hourly_frame(self) -> pd.DataFrame: ...
    def daily_frame(self) -> pd.DataFrame: ...
```

Dtypes, which the tests must assert:

| Column | Dtype | Note |
|---|---|---|
| `date` | `object` holding `datetime.date` | Never `datetime64`. See risk 3. |
| `ts_hour` | `int64` | |
| `capacity_margin` | `float64` | `NaN` when the caller passed no `available_capacity_mw`. |
| `recharge_sufficiency_ratio` | `float64` | `NaN` on the last day of a window. |
| every other column | `float64` | |

**Every column that can hold `None` must be built with an explicit dtype.** Measurement M16
shows that `pandas.Series([None, None])` infers `object`, not `float64`, and that
`isna().all()` returns `True` on that object column, so a dtype error would pass a naive test
unseen. Build `capacity_margin` and `recharge_sufficiency_ratio` as
`pd.Series(values, dtype="float64")` in every case, empty or not.

Both methods must return a frame with the declared columns and dtypes even when `daily` is
empty. Build the empty case from explicit `pd.Series(dtype=...)` values, not from an empty
list of records.

Column names keep the `HourlyResult` and `DailyResult` field names. Do not rename to the
architecture doc's names. `projected_SOC` means a forecast in the doc and the repo field is the
realized state of charge, so a rename would state something false. Put this mapping table in
the `hourly_frame` docstring instead:

| Frame column | Architecture doc field | Component |
|---|---|---|
| `gross_load` | `observed_load` | 6 |
| `net_load` | `dispatched_net_load` | 6 |
| `discharge` | `discharge_power` | 5 |
| `charge` | `charge_power` | 5 |
| `soc` | `updated_SOC` | 6 |
| `capacity_margin` | derived field "capacity margin" | 6 |

Also name the doc fields the engine does not model: `charge_dispatched`,
`recharge_opportunity`, `dispatch_reason`, `remaining_capacity`, `observed_net_load`,
`oil_generation_actual`, `gas_generation_actual`, `wind_generation_actual`.

### Tests — `tests/test_simulator.py`

Add:

1. `test_hourly_frame_shape_and_columns`. Run a two day simulation. Assert
   `tuple(frame.columns) == HOURLY_FRAME_COLUMNS` and `len(frame.index) == 48`.
2. `test_hourly_frame_values_match_the_dataclasses`. **Run this case with
   `available_capacity_mw` set to a finite number**, so `capacity_margin` is a float on both
   sides. For every row, assert the frame value equals the matching `HourlyResult` attribute
   exactly, with `==`, not `approx`. With `available_capacity_mw=None` the dataclass holds
   `None` and the frame holds `NaN`, and `==` matches neither; test 4 covers that case.
3. `test_hourly_frame_date_column_holds_date_objects`. Assert
   `isinstance(frame["date"].iloc[0], datetime.date)` and
   `not isinstance(frame["date"].iloc[0], datetime.datetime)`, and `frame["date"].dtype == object`.
4. `test_capacity_margin_is_nan_and_float64_when_unset`. Run with `available_capacity_mw=None`.
   Assert `frame["capacity_margin"].dtype == "float64"` **and** `frame["capacity_margin"].isna().all()`.
   The dtype assertion is the load-bearing half; measurement M16 shows `isna().all()` alone
   passes on an `object` column.
5. `test_daily_frame_columns_and_nan_ratio`. Assert the last day's
   `recharge_sufficiency_ratio` is `NaN` and the column dtype is `float64`.
6. `test_frames_are_empty_with_declared_columns`. Call `simulate` with an empty window and
   assert both frames have zero rows, the declared columns, and the declared dtypes.

### Verify

```bash
uv run pytest tests/test_simulator.py
uv run pytest
uv run ruff check .
```

The pipeline JSON comparison must print `IDENTICAL`. Nothing in `cli.py` reads the frames.

Time: about 45 minutes.

---

## Phase 4 — ETL ingest boundary

Goal: the raw rows table becomes a `DataFrame`, and the provider frame gets a named boundary
function.

### 4a. `src/owr/etl/extract.py`

Add one function above the record adapters:

```python
def records_from_frame(frame: Any) -> list[dict[str, object]]:
    """Convert a provider ``pandas.DataFrame`` into plain records.

    ``gridstatus`` returns a ``DataFrame``; every adapter below takes plain dicts, so
    the normalization stays testable without a provider installed. This function is
    the single named place that crosses that boundary.

    **No missing-value conversion happens here, on purpose.** ``gridstatus``
    ``_handle_fuel_type_data`` fills an absent fuel column with ``numpy.nan``.
    Mapping ``NaN`` to ``None`` would make ``_first`` treat the column as absent and
    raise ``KeyError`` instead of the ``non-finite wind value at ts=...`` error that
    ``wind_observations_from_records`` raises today. That guard stays live.
    """
```

Body: raise `TypeError` when `frame` has no `to_dict`, then return `frame.to_dict("records")`.

Replace both `frame.to_dict("records")` calls with `records_from_frame(frame)`:
`ISONELoadSource.get_observations` and `EIAWindSource.get_observations`.

Everything else in `extract.py` stays. `ExtractResult.rows` stays a tuple of tuples.
`build_rows` and `upsert_rows` stay on tuples. Measurement M8 is the reason: a `DataFrame`
built from those rows turns `forecast_mw=None` into `NaN` and promotes `horizon_days` to float.

### 4b. `src/owr/etl/rows_csv.py`

```python
def read_rows_csv(stream: TextIO, dataset: RawDataset, *, origin: str) -> pd.DataFrame:
    """Read a rows CSV written by :func:`write_rows_csv` into a string-typed frame.

    Every column is ``object`` dtype holding ``str``; a blank cell reads back as
    ``""``, which is what ``write_rows_csv`` writes for ``None``. No column is
    converted to a number here: the caller owns the unit conversion, and an early
    conversion would turn an empty ``forecast_mw`` cell into ``NaN`` instead of ``""``.

    Two inputs that ``csv.DictReader`` accepted are now rejected, both malformed:
    a data row with more fields than the header, and an unclosed quoted field. See
    docs/PLAN_PANDAS_ADOPTION.md admitted changes A1 and A2.
    """
```

**Keep the existing comment and blank line filter, and keep the empty-file guard that follows
it**, unchanged:

```python
filtered = [line for line in stream if line.strip() and not line.lstrip().startswith("#")]
if not filtered:
    raise RowsCsvError(f"{origin}: no data rows (file is empty or all comments/blank)")
```

That guard is load bearing. Without it an empty file reaches `read_csv` and the caller gets
`cannot parse as CSV: No columns to parse from file` instead of the module's own message.

Then:

```python
try:
    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.ParserWarning)
        frame = pd.read_csv(
            io.StringIO("".join(filtered)),
            dtype=str,
            na_filter=False,
            index_col=False,
        )
except (pd.errors.ParserError, pd.errors.EmptyDataError, pd.errors.ParserWarning) as exc:
    raise RowsCsvError(f"{origin}: cannot parse as CSV: {exc}") from exc
if tuple(frame.columns) != dataset.columns:
    raise RowsCsvError(
        f"{origin}: header {list(frame.columns)!r} does not match expected columns "
        f"{dataset.columns!r}"
    )
return frame
```

Three details are load bearing:

- `index_col=False` is mandatory. Measurement M6 shows that without it a first data row longer
  than the header silently shifts every value one column left.
- The `simplefilter("error", ParserWarning)` block is mandatory, and it is what makes the
  behavior uniform. Measurement M6 shows pandas raises `ParserError` for a **later** over-long
  row but only warns for the **first** one. Without the promotion the reader would reject an
  over-long row at line 3 and silently accept the same row at line 2. Measurement M13 confirms
  the promotion rejects both, and still accepts short rows and normal rows.
- `pd.errors.ParserWarning` must appear in the `except` tuple. Measurement M11 shows it
  subclasses `Warning`, not `ValueError`, so the ETL CLI's `except (OSError, ValueError)` would
  not catch it and the command would show a traceback.

The header mismatch message keeps its exact wording, and `list(frame.columns)` renders the same
as the old `reader.fieldnames`.

`write_rows_csv` does not change.

### 4c. `src/owr/etl/cli.py`, `_run_transform`

```python
frame = read_rows_csv(stream, dataset, origin=path)
if frame.empty:
    print(f"etl transform: {path}: 0 data rows, skipping", file=sys.stderr)
    continue
for record in frame.to_dict("records"):
    readings.append(_reading_from_row(record, path))
```

Never write `if not frame`. A `DataFrame` raises `ValueError` on truth testing.
`_reading_from_row` does not change.

Admitted change A3 lands here. A row missing its trailing cell gives `None` today, and
`float(None)` raises `TypeError`, which `cmd_transform` does not catch, so the user sees a
traceback. After this phase the cell reads back `""`, `float("")` raises `ValueError`, and the
command exits 2 with `error: could not convert string to float: ''`. This is an improvement,
and phase 4 test 5 pins it.

### Tests

`tests/test_etl_rows_csv.py`: update the round trip test. `len(read_rows)` becomes
`len(frame.index)`, and the per row loop reads `frame.to_dict("records")`. Add:

1. `test_read_rows_csv_returns_string_dtype`. Assert every column dtype is `object` and every
   cell is a `str`.
2. `test_blank_cell_reads_back_as_empty_string`. Build rows with `forecast_mw=None` through the
   `wind` dataset, write, read, assert the cell is `""` and not `NaN`.
3. `test_over_long_data_row_is_rejected_at_any_position`. Parametrize over two files: one whose
   **first** data row carries an extra field, and one whose **second** data row does. Assert
   both raise `RowsCsvError`. This pins the `ParserWarning` promotion, which is the only reason
   the two positions behave the same. Admitted change A1.
4. `test_unclosed_quote_is_rejected`. Assert `RowsCsvError`. Admitted change A2.
5. `test_empty_file_keeps_the_module_message`. Assert the message is
   `no data rows (file is empty or all comments/blank)` and not a pandas message.

`tests/test_etl_cli_transform.py`: add

6. `test_row_missing_a_trailing_cell_exits_two_not_traceback`. Write a fixture whose last row is
   short, run `etl transform`, and assert the exit code is 2 and stdout starts with `error:`.
   Admitted change A3.

`tests/test_etl_extract.py`: keep the `_FakeTimestamp` test, which covers any duck typed
provider object. Add real pandas tests, now that pandas is a project dependency:

7. `test_records_from_frame_round_trips_a_real_dataframe`. Build a `pd.DataFrame` with an
   `Interval Start` column of `pd.Timestamp` values and a `Load` column, pass it through
   `records_from_frame` and `load_observations_from_records`, assert the observations.
8. `test_records_from_frame_rejects_a_non_frame`. Assert `TypeError`.

`tests/test_etl_eia.py`: add

9. `test_real_nan_wind_cell_raises_non_finite`. Build a `pd.DataFrame` whose `Wind` column holds
   `numpy.nan`, pass it through `records_from_frame` and `wind_observations_from_records`, and
   assert the `non-finite wind value` `ValueError`. This proves the guard survives the new
   boundary function.

### Verify

```bash
uv run pytest tests/test_etl_rows_csv.py tests/test_etl_extract.py tests/test_etl_eia.py \
              tests/test_etl_cli_transform.py
uv run pytest -W error::pandas.errors.ParserWarning
uv run pytest
uv run ruff check .
```

The second command proves no `ParserWarning` escapes into the pytest warning summary.

Time: about 80 minutes.

---

## Phase 5 — ETL table boundary

Goal: the daily rollup and the stress event table become `DataFrame` objects with declared
column contracts. The `etl transform` text output and JSON payload stay exactly as they are.

### 5a. `src/owr/etl/daily.py`

`daily_loads_from_readings` does not change. Its Python `sum()` accumulation stays, for the
reason in risk 11. Add below it:

```python
DAILY_CORE_COLUMNS: tuple[str, ...] = (
    "date", "load_mwh", "hours_covered", "expected_hours", "intervals", "complete",
)

def daily_frame(loads: Sequence[DailyLoad]) -> pd.DataFrame:
    """The Component 2 daily contract as a frame, one row per local calendar date.

    ``date`` holds ``datetime.date`` objects in an ``object`` column, never
    ``datetime64``. The engine does calendar arithmetic with ``timedelta(days=1)``,
    formats with ``date.isoformat()``, and uses dates as dictionary keys; a
    ``Timestamp`` changes all three.
    """
```

Dtypes: `date` object, `load_mwh` float64, `hours_covered` float64, `expected_hours` float64,
`intervals` int64, `complete` bool. Rows keep the input order, which
`daily_loads_from_readings` already sorts ascending by date. The empty input case returns a
frame with the declared columns and dtypes and zero rows.

### 5b. `src/owr/etl/transform.py`

```python
DAILY_FRAME_COLUMNS: tuple[str, ...] = DAILY_CORE_COLUMNS + ("season", "winter_label")

EVENT_FRAME_COLUMNS: tuple[str, ...] = (
    "winter_label", "event_start_date", "event_end_date", "event_duration_days",
)

def add_season_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a new frame with ``season`` and ``winter_label`` appended.

    Never mutates the input. The architecture doc's Global Interface Contract says a
    component shall never modify another component's output.
    """

def winter_labels(daily: pd.DataFrame) -> tuple[str, ...]: ...

def compute_threshold(
    daily: pd.DataFrame, *, percentile: float, season: Season
) -> ThresholdResult: ...

def find_windows_per_winter(
    daily: pd.DataFrame, *, threshold_mwh: float, min_window_days: int
) -> pd.DataFrame: ...
```

`add_season_columns` sets `season` to `season_for(d).value` (`object` dtype holding `str`) and
`winter_label` to `winter_label(d)` (`object` dtype holding `str` or `None`).

**`winter_labels` is new and it is what keeps the JSON payload complete.**

```python
def winter_labels(daily: pd.DataFrame) -> tuple[str, ...]:
    """Every winter label present in ``daily``, sorted, duplicates removed.

    Filter on ``winter_label`` being present, and **do not** filter on ``complete``.
    The retired ``find_windows_per_winter`` grouped by label before it dropped
    incomplete days, so a winter whose days are all incomplete still produced a key
    with an empty list. The ETL CLI emits one JSON entry per label returned here, so
    this function is the sole reason a winter with zero events keeps its key.
    """
```

Implementation: `tuple(sorted(daily.loc[daily["winter_label"].notna(), "winter_label"].unique()))`.

`compute_threshold` takes the frame that `add_season_columns` produced. It must keep its
current order of operations exactly:

1. Mask `daily["season"] == season.value`.
2. Split that mask on `daily["complete"]` into the population and the excluded set.
3. `excluded_incomplete = tuple(sorted(excluded["date"]))`.
4. Raise `ValueError(f"no complete {season} days in the input population")` when the population
   is empty. This guard must stay ahead of every aggregation, because
   `Series.min()` on an empty series returns `NaN` instead of raising.
5. `values = population["load_mwh"].to_numpy()`, then `percentile_threshold(values, percentile)`.
6. `min_mwh=float(values.min())`, `max_mwh=float(values.max())`,
   `median_mwh=percentile_threshold(values, 0.5)`, `population_days=int(len(population.index))`.

`ThresholdResult` field types do not change. Every numeric field must carry a builtin `float`
or `int`, never `numpy.int64`. Measurement M4 is the reason.

`find_windows_per_winter` returns the Component 3 event table:

| Column | Dtype | Source |
|---|---|---|
| `winter_label` | `object` of `str` | `seasons.winter_label` |
| `event_start_date` | `object` of `datetime.date` | `StressWindow.start` |
| `event_end_date` | `object` of `datetime.date` | `StressWindow.end` |
| `event_duration_days` | `int64` | `StressWindow.days` |

The doc calls the identifier `winter_id` and describes it as a hash. The repo has a readable
label and no hash. Keep `winter_label`. Add no `event_id` column.

Body: mask on `daily["complete"]`, drop rows where `daily["winter_label"].notna()` is false,
group by `winter_label`, sort each group by `date`, build a `_DailyPoint` named tuple per row
that satisfies `DailyLoadLike`, call the unchanged
`find_stress_windows_at_threshold(points, threshold_mwh, min_window_days)`, and concatenate the
results. Sort the final frame by `winter_label` then `event_start_date`. The empty case returns
a frame with the declared columns and dtypes and zero rows.

**The event frame carries only event rows.** A winter with no event contributes no row, by
design. The label set lives in `winter_labels`, and the CLI joins the two. Do not try to
recover the label set from the event frame; that is the defect this revision fixes.

`stress_finder.py` does not change in this phase. It stays the single implementation of run
detection.

### 5c. `src/owr/etl/cli.py`

`_run_transform`:

```python
daily = daily_loads_from_readings(readings)
frame = add_season_columns(daily_frame(daily))
season = Season(args.season)
threshold = compute_threshold(frame, percentile=args.percentile, season=season)
events: pd.DataFrame | None
labels: tuple[str, ...]
if season == Season.WINTER:
    events = find_windows_per_winter(
        frame, threshold_mwh=threshold.threshold_mwh, min_window_days=args.min_window_days
    )
    labels = winter_labels(frame)
else:
    events = None
    labels = ()
if args.out:
    _write_daily_csv(args.out, frame)
```

Keep the existing comment that explains why non winter seasons skip window detection. Keep the
`None` sentinel and test it with `is None`, never with truth testing.

`_write_daily_csv(path: str, frame: pd.DataFrame) -> None`:

```python
ordered = frame.sort_values("date")[list(DAILY_FRAME_COLUMNS)]
ordered.to_csv(path, index=False, lineterminator="\r\n")
```

`lineterminator="\r\n"` is mandatory. `csv.writer` uses `\r\n` by default and the current file
uses `csv.writer`. Measurement M9 confirms the two outputs are then byte identical, for both an
in-memory write and a path write, including the `""` cell for a `None` `winter_label`, the
`True` and `False` spellings for the bool column, and the shortest-repr float formatting.

`_print_transform_text(threshold, events)`: iterate `events.itertuples()` in the frame's
existing sort order. The printed lines must stay exactly:

```
    {winter_label}: {start.isoformat()} -> {end.isoformat()} ({days} days)
```

Replace `if total == 0` with `if len(events.index) == 0`. The text output needs no label set:
today a label with no window contributes no printed line, because the inner loop does not run.

`_transform_result_json(threshold, events, labels)`: the signature gains `labels`. Keep the
payload shape exactly as it is today, a dictionary of winter label to a list of
`{"start", "end", "days"}`, **with one key per label in `labels`, including a label whose list
is empty**:

```python
result["windows"] = {
    label: [
        {"start": row.event_start_date.isoformat(),
         "end": row.event_end_date.isoformat(),
         "days": int(row.event_duration_days)}
        for row in events[events["winter_label"] == label].itertuples()
    ]
    for label in labels
}
```

Two details are load bearing:

- Iterating `labels`, not the event frame, is what keeps a winter with zero events in the
  payload. `find_windows_per_winter` today returns `result[label] = []` for every winter it
  groups, and `_transform_result_json` emits that empty list. Real winter data produces such
  labels often.
- The `int()` cast is mandatory. Measurement M4 shows `json.dumps` raises `TypeError` on
  `numpy.int64`.

### Tests

`tests/test_etl_daily.py`: keep every existing test. Add

1. `test_daily_frame_columns_dtypes_and_row_order`.
2. `test_daily_frame_date_column_holds_date_objects`.
3. `test_daily_frame_empty_input_has_declared_columns`.

`tests/test_etl_transform.py`: rewrite the helper so `_day(...)` builds a `DailyLoad` and the
tests pass `add_season_columns(daily_frame([...]))` into the three functions. Keep every
existing assertion about thresholds, population counts and window counts, and translate the
window assertions to the event frame. Add

4. `test_event_frame_columns_and_dtypes`.
5. `test_event_frame_is_empty_with_declared_columns_when_no_run_qualifies`.
6. `test_threshold_result_fields_are_builtin_floats`. Assert `type(result.threshold_mwh) is float`
   and `type(result.population_days) is int`.
7. `test_add_season_columns_does_not_mutate_the_input`. Assert the input frame columns are
   unchanged after the call.
8. `test_winter_labels_includes_a_winter_with_no_complete_day`. Build a frame with one winter of
   complete days and one winter whose days are all `complete=False`. Assert both labels appear.
   This pins the "do not filter on complete" rule.

`tests/test_etl_cli_transform.py`: keep all 19 tests. Add

9. `test_transform_out_daily_csv_is_byte_identical_to_the_expected_text`. Write a fixture of
   three known days, run `transform --out`, and compare `out_path.read_bytes()` against an
   explicit expected byte string that ends every line with `\r\n`. This pins the `to_csv`
   migration.
10. `test_transform_json_keeps_a_winter_with_no_window`. Build a two-winter fixture: winter A
    has a run long enough to qualify, winter B has days below the threshold and no run. Run
    `--format json`. Assert `set(payload["windows"]) == {"<label A>", "<label B>"}` and
    `payload["windows"]["<label B>"] == []`. **This is the regression test for the blocking
    finding B1.**
11. `test_transform_json_days_field_is_a_plain_int`. Parse the payload from a fixture that
    produces at least one window and assert
    `type(payload["windows"]["<label A>"][0]["days"]) is int`.

Test 10 is a characterization test. Write it before phase 5 starts, run it on unchanged code,
and confirm it is green. A characterization test that fails on the current code is measuring
the wrong thing.

### Verify

```bash
uv run pytest tests/test_etl_daily.py tests/test_etl_transform.py tests/test_etl_cli_transform.py
uv run pytest
uv run ruff check .
```

Time: about 2 hours 15 minutes.

---

## Phase 6 — `scenario_input` on `pandas.read_csv`

Goal: pandas parses the day profile CSV. Every validation rule the reader applies keeps its
message and its line number. Three inputs behave differently, and all three are admitted
changes A1, A2 and A4 in the table above. No other acceptance behavior moves.

### Design constraint that drives the shape

`tests/test_scenario_input.py` asserts on `test:2` line numbers in 14 tests. The current code
gets those numbers from a pre filter that records the source line number of every kept line.
pandas reports no source line numbers. Therefore the pre filter stays, and pandas parses the
filtered text.

### Change, confined to lines 106 to 122 of `src/owr/scenario_input.py`

Replace `reader = csv.DictReader(lines)` and the two lines after it with:

```python
try:
    with warnings.catch_warnings():
        warnings.simplefilter("error", pd.errors.ParserWarning)
        frame = pd.read_csv(
            io.StringIO("".join(lines)),
            dtype=str,
            na_filter=False,
            index_col=False,
        )
except (pd.errors.ParserError, pd.errors.EmptyDataError, pd.errors.ParserWarning) as exc:
    raise _err(origin, None, f"cannot parse as CSV: {exc}") from exc
if frame.columns.empty:
    raise _err(origin, None, "missing header row")
fieldmap = {str(name).strip().lower(): str(name) for name in frame.columns}
```

and replace `raw_rows = list(reader)` with `raw_rows = frame.to_dict("records")`.

Remove `import csv`. Add `import io`, `import warnings` and `import pandas as pd`.

Each element is load bearing:

| Element | Reason |
|---|---|
| `dtype=str` | Every cell stays the token as written. `_parse_finite_float` and the blank checks work on strings today and must keep working. |
| `na_filter=False` | Without it a blank cell becomes `NaN` and `"nan"` becomes a float. The tests in `NON_FINITE_TOKENS` depend on `"nan"` reaching `_parse_finite_float` as text. |
| `index_col=False` | Measurement M6. Without it a first data row longer than the header shifts every value left, and the `date` cell silently becomes the `hour` value. |
| `simplefilter("error", ParserWarning)` | Measurement M6 and M13. pandas raises for a later over-long row but only warns for the first one. The promotion makes both positions behave the same, and keeps the warning off stderr and out of the pytest warning summary. |
| `ParserWarning` in the `except` tuple | Measurement M11. It subclasses `Warning`, not `ValueError`, so `cmd_run` would not catch it and the CLI would show a traceback. |
| `io.StringIO("".join(lines))` | The pre filter already stripped comment and blank lines and recorded their line numbers. Do not use `comment="#"`: pandas truncates a line at `#` anywhere in it, not only at the start. |

Nothing below line 122 changes. `row.get(fieldmap[col]) or ""` keeps working, because
`to_dict("records")` yields `str` values and a blank cell is `""`.

Add to the module docstring:

```
Parsed by ``pandas.read_csv`` with ``dtype=str`` and ``na_filter=False``, so every
cell reaches the validation below as the token the file carried. Three behaviors
differ from the retired ``csv.DictReader``:

* A data row with more fields than the header is rejected, at any row position.
  ``csv.DictReader`` accepted it and stored the extra field under the ``None`` key.
* A file with an unclosed quoted field is rejected. ``csv.DictReader`` swallowed the
  rest of the file into one field.
* A header that repeats a column name resolves to the first occurrence, because
  pandas renames the second to ``name.1``. ``csv.DictReader`` kept the last. Neither
  reader raises.

A blank header cell is named ``Unnamed: <position>`` by pandas, where
``csv.DictReader`` named it ``""``. Neither name is a required or optional column, so
both readers report the same missing-column error for such a header.
```

### Tests — `tests/test_scenario_input.py`

Keep all 30 existing tests unchanged. They are the regression gate for this phase. Add

1. `test_duplicate_header_column_first_wins`. Header `date,hour,load_mw,load_mw`, first
   `load_mw` column 1.0 and second 2.0. Assert the parsed load is 1.0. Admitted change A4.
2. `test_over_long_data_row_is_rejected_at_any_position`. Parametrize over two files: one whose
   first data row carries a fourth field under a three column header, and one whose second data
   row does. **Assert both raise `ScenarioInputError` whose message contains
   `cannot parse as CSV`.** Admitted change A1. This is a specification, not an observation:
   without the `ParserWarning` promotion the first-row case would parse silently and only the
   second-row case would raise.
3. `test_unclosed_quote_is_rejected`. A data row containing `"1` with no closing quote. Assert
   `ScenarioInputError`, not a bare pandas error. Admitted change A2.
4. `test_blank_header_cell_still_reports_the_missing_column`. Header `date,,load_mw`. Assert the
   error names `hour`, the same as today.

### Verify

```bash
uv run pytest tests/test_scenario_input.py tests/test_cli.py
uv run pytest -W error::pandas.errors.ParserWarning
uv run pytest
uv run ruff check .
uv run simulate --input examples/synthetic_winter_stress.csv --storage-mwh 20000 --power-mw 2000
uv run python examples/make_synthetic_winter_stress.py
git diff --exit-code examples/synthetic_winter_stress.csv
```

The last command must exit 0. The pipeline JSON comparison must print `IDENTICAL`.

Time: about 60 minutes.

---

## Phase 7 — Close out

1. Update `docs/HANDOFF.md`: new test count, the date, one paragraph naming the four
   `DataFrame` boundaries and the purity rule change, and the four admitted behavior changes.
2. Add one row to `docs/BOARD.md` for this workstream.
3. Add a short section to `docs/DATA_SOURCES.md` that records the percentile change: the
   function now calls `numpy.quantile`, the difference against the retired formula is bounded
   at about 1e-15 relative, the stress set is provably unchanged, and any recorded p90 threshold
   is unchanged at the three decimal places the CLI prints.
4. Run the full acceptance set:

```bash
uv run pytest
uv run ruff check .
uv run simulate --input examples/synthetic_winter_stress.csv --storage-mwh 20000 --power-mw 2000
uv run etl transform --help
uv run python examples/make_synthetic_winter_stress.py && git diff --exit-code examples/synthetic_winter_stress.csv
```

Time: about 25 minutes.

Total: about 6 hours 45 minutes.

---

## Risks, ranked

**1. `numpy.quantile` is not bit identical to the retired percentile.** Measured M1: 471 of
20000 random cases differ, worst relative difference 1.08e-15. NumPy uses
`hi - (hi - lo) * (1 - frac)` when `frac` is at or above 0.5 and `lo + (hi - lo) * frac`
otherwise, so results below 0.5 are bit identical and only the upper half can move.

A stressed-day comparison cannot flip. The difference comes from rounding the product
`(hi - lo) * frac`, so it appears only when the gap `hi - lo` is wide enough for that product
to round. The threshold lies between two adjacent values of the sorted population, so no other
daily total lies between them, and the nearest candidate for a flip is `lo`, at distance
`(hi - lo) * frac`, which is at least half the gap. A flip therefore needs a gap of a few units
in the last place; at that width both products are exactly representable and both forms return
the same value. The two conditions exclude each other. The adversarial review confirmed this
over 200000 trials with zero stress-set flips. Guard: the reference sweep test and the
stress-set test in phase 2, plus the `IDENTICAL` pipeline JSON check after every phase, plus
the p90 note in phase 7 step 3.

**2. `numpy.int64` breaks `json.dumps`.** Measured M4. `numpy.float64` is safe because it
subclasses `float` (M3); `numpy.int64` is not. Two JSON paths are exposed:
`etl/cli._transform_result_json` and `cli._build_report`. Guard: the explicit `int()` cast in
phase 5c, `population_days=int(...)` in `compute_threshold`, and phase 5 test 11.

**3. A `date` column must never become `datetime64`.** Measured M7 shows an object column of
`datetime.date` survives `itertuples` and `groupby`. If any code calls `pd.to_datetime` on such
a column, the cells become `pandas.Timestamp` and `isoformat()` returns
`2021-12-01T00:00:00` instead of `2021-12-01`. That would change the `etl transform` text
output, the JSON payload and the daily CSV, all silently. Guard: the phrase "never
`datetime64`" in three docstrings, plus one dtype test per frame builder, plus a code review
rule: this refactor introduces no `pd.to_datetime` call anywhere.

**4. `read_csv` over-long-row behavior depends on row position.** Measured M6: the first data
row warns and loses a field; a later one raises. Without `index_col=False` the first-row case
also shifts every column left. Guard: `index_col=False` plus the `ParserWarning` promotion at
both call sites, and a parametrized two-position test in each of `tests/test_etl_rows_csv.py`
and `tests/test_scenario_input.py`. This is admitted change A1.

**5. A `DataFrame` turns `None` into `NaN` and promotes an integer column to float.** Measured
M8. This is why `build_rows`, `upsert_rows`, `write_rows_csv` and `ExtractResult.rows` all stay
on tuples. A `raw.hourly_wind` row carries `forecast_mw=None` and `horizon_days=0`; a
round trip through a `DataFrame` would write `NaN` and `0.0`. Guard: the explicit "stays on
tuples" statement in phase 4a and phase 4 test 2.

**6. An all-`None` column infers `object`, and `isna().all()` passes on it.** Measured M16. A
`capacity_margin` column of all `None` would satisfy a naive NaN test while carrying the wrong
dtype, and would then serialize or compare differently downstream. Guard: mandatory
`dtype="float64"` construction in phase 3, and a dtype assertion in phase 3 test 4.

**7. `to_csv` line terminator.** pandas defaults differ from `csv.writer`'s `\r\n`. Guard:
`lineterminator="\r\n"` in `_write_daily_csv` plus the byte comparison test in phase 5.

**8. `DataFrame` truth testing raises.** `if not rows:` and `if windows:` both raise
`ValueError: The truth value of a DataFrame is ambiguous`. Guard: `frame.empty`,
`len(frame.index) == 0` and `events is None` are the only permitted forms. Grep for
`if not frame` and `if frame` before the phase closes.

**9. Header-name edge cases change which column wins.** Measured M12: a duplicate name keeps the
first and renames the second to `name.1`, where `csv.DictReader` kept the last. Measured M15: a
blank header cell becomes `Unnamed: <position>` instead of `""`. Neither raises, and neither
affects a well-formed file. Guard: phase 6 tests 1 and 4, plus the docstring note. This plan
adds no new validation for either, because the instruction is to keep validation semantics and
error messages unchanged. Record both as follow-up candidates.

**10. Collision with `docs/PLAN_SCENARIO_PROFILE_FORMAT.md`.** That plan is pending, is large,
and owns `scenario_input.py`, `etl/transform.py` and `etl/cli.py`. It needs re-lining and
rewording before it can run, not just one table correction. Four concrete collisions:

| Collision | Detail | Action |
|---|---|---|
| `pyproject.toml` | That plan's shared file table says "**No change.** `dependencies = []` stays empty. Everything here is stdlib." | This plan supersedes that row. Correct it before starting that plan. |
| That plan's line 362 | It reasons about the line filter in terms of `csv.DictReader`: "Comment lines never reach `csv.DictReader`". This plan deletes that import. | Reword to `pandas.read_csv`. The behavior it describes is unchanged. |
| That plan's lines 398 to 405 | It inserts two header checks at the `fieldmap` site, `scenario_input.py:109`, which sits **inside** the 106 to 122 region this plan rewrites. | Re-line those references after this plan lands. The checks themselves still apply, unchanged, against the same `fieldmap` dict. |
| That plan's `transform.py` addition | `percentile_rank_within(daily: list[DailyLoad], *, season: Season)`. This plan changes the two neighbouring functions to take a frame. | That signature must become `percentile_rank_within(daily: pd.DataFrame, *, season: Season)`. Flag it to whoever owns that plan. |

Land this plan first. It is smaller, it is a pure refactor, and it sets the frame contracts the
scenario format plan will then write against.

**11. `pandas.groupby.sum()` is not Python `sum()`.** Measured M10: 40 of 3000 cases of 288
floats differ, because the pandas kernel uses compensated summation. `numpy.sum` is worse for
this purpose: 970 of 3000 differ, because it sums pairwise. This is why
`daily_loads_from_readings` keeps its Python accumulation and pandas only assembles, filters
and renders the table. A future performance pass may revisit this; it must then re-baseline the
recorded p90 thresholds.

**12. Continuous integration installs no pandas today.** The workflow runs
`uv sync --group dev`, and `dependencies` is currently empty. Guard: regenerate `uv.lock` in
phase 1 and confirm the import command in phase 1 step 4 succeeds in a clean checkout.

**13. pandas exceptions leak through as pandas messages.** Measured M11:
`ParserError` and `EmptyDataError` both subclass `ValueError`, so the CLI already catches them
and exits 2, but the message would name pandas instead of the module. `ParserWarning` does not
subclass `ValueError` and would escape as a traceback. Guard: all three are wrapped into
`RowsCsvError` and `ScenarioInputError` at each call site, as phases 4b and 6 specify.

---

## Assumptions

1. `pandas>=2.2` and `numpy>=1.26` are acceptable floors. The venv holds 2.3.3 and 2.5.1. The
   `method=` keyword on `numpy.quantile` needs 1.22 or later; `lineterminator` on `to_csv` needs
   pandas 1.5 or later. Both floors clear those.
2. "Preserve numeric behavior exactly" allows the bounded last-place difference in risk 1,
   because the instruction also names `numpy.percentile` as the required replacement. If the
   team wants bit exactness instead, phase 2 must be dropped and the hand-rolled formula kept.
   Raise this before starting phase 2 if in doubt.
3. The `etl transform` stdout text and JSON payload shape are a contract. This plan changes
   neither, including the empty list a winter with no event carries today. If the team wants the
   payload to carry the new event frame columns, that is a separate change.
4. The four admitted behavior changes in the table above are acceptable. A1 and A2 reject
   malformed files that parse today. If any real input file relies on either, stop and raise it.
5. The architecture doc's Component 3 `event_id` and `winter_id` hash columns stay unbuilt until
   the team defines the hash.
6. `docs/source/2026-08-04_Software_Architecture_Documentation.md` is the current architecture
   doc. The 2026-07-30 file in the same directory is superseded.

---

## Lint traps to expect

`uv run ruff check .` selects `E`, `F`, `I`, `UP` and `B`. Five imports go unused as the phases
land. Remove each one in the phase that orphans it, or `F401` fails the build.

| Phase | File | Import to remove | Orphaned by |
|---|---|---|---|
| 5 | `src/owr/etl/cli.py` | `import csv` | `_write_daily_csv` moves to `DataFrame.to_csv`. |
| 5 | `src/owr/etl/cli.py` | `DailyLoad` from line 27 | Used only in the `_write_daily_csv` annotation at line 199, which becomes `pd.DataFrame`. |
| 5 | `src/owr/etl/cli.py` | `season_for` and `winter_label` from line 30 | Used only at lines 223 and 224, replaced by `add_season_columns`. Keep `Season`. |
| 5 | `src/owr/etl/cli.py` | `StressWindow` from `owr.models` | The event frame replaces `dict[str, list[StressWindow]]`. |
| 6 | `src/owr/scenario_input.py` | `import csv` | `pandas.read_csv` replaces `csv.DictReader`. |

Ruff rule `I` sorts imports. `import pandas as pd` and `import numpy as np` are third party and
belong in the block after the standard library block, before the `owr` block. `warnings` is
standard library.
