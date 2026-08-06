# Plan — EIA-930 Oil and Gas Hourly Generation Extractor — 2026-08-05

Extend the extractor to hourly petroleum and natural gas net generation from EIA-930
(Energy Information Administration form 930), respondent `ISNE` (ISO New England).
The Fuel-Fired Generation Offset metric is a separate task and consumes the output of
this one. This plan pulls and stores the two series. It computes no energy and no metric.

The live pull is blocked: `$EIA_API_KEY` is under re-check. Every phase below lands and
passes with no key. One key-gated verification step remains at the end.

## Revision log

**Revision 1, 2026-08-05.** Adversarial review. Three blocking findings, two non-blocking,
three nits. All accepted. Dispositions:

| # | Finding | Disposition |
|---|---|---|
| B1 | A null EIA value becomes `0.0` inside `pivot_table(aggfunc="sum")`, so "0.0 is real" was false as an invariant | **Accepted.** Reproduced on pandas 2.3.3: `[0.0, None, 12.5]` pivots to `[0.0, 0.0, 12.5]`. Rewrote the adapter docstring, the migration comment, the DATA_SOURCES note, tests 3, 7 and 8, and R3. Kept the non-finite guard: it still catches a renamed column. |
| B2 | A missing hour is an absent row, not a NaN, so R4's mechanism was wrong and gaps land green | **Accepted.** Reproduced: an omitted row drops the hour from the pivot index with no error. Rewrote R4, added the pure `hourly_gaps` helper (step 1f) with tests 24 and 25, and made the gap check a named step in key-gated steps 4 and 6. |
| B3 | The key-leak check filtered out `#` lines first, and `source_query` lives in the `#` banner | **Accepted.** Key-gated step 4 now tests the key against the full file text before any filter. |
| N1 | The two-fuel fixture is not the production frame shape | **Accepted.** It is relabelled a superset (test 14). Tests 15 and 16 add one single-fuel frame per adapter, which is the real shape. |
| N2 | The `gen_mw` alias let a gas row feed the oil adapter and be stamped `OIL` | **Accepted.** Dropped `gen_mw` from both alias tuples. The remaining aliases are fuel specific. Test 5 pins the rejection. |
| a | Definition of done item 2 skip count | **Accepted.** Stated the condition. |
| b | Fixture values not labelled synthetic | **Accepted.** |
| c | R6 cites `extract.py:157`, the comment is at 152 | **Accepted.** |

---

## 0. Ground truth read this session

| Fact | Where |
|---|---|
| `EIA.get_dataset(dataset, start, end, frequency, facets, n_workers, verbose)` sends the key in the `X-Api-Key` header. The facets go in the `X-Params` header, never in the URL. | `.venv/lib/python3.13/site-packages/gridstatus/eia.py:113-194` |
| `_facet_handler` wraps each scalar facet value in a list **in place**. It rewrites the caller's dictionary. | `gridstatus/eia.py:104-111` |
| `electricity/rto/fuel-type-data` pivots on the API field `type-name`, lowercases it, then title-cases the column. Oil arrives as **`Petroleum`**. Gas arrives as **`Natural Gas`**. | `gridstatus/eia.py:918-982` |
| The handler adds **every** name in `EIA_FUEL_TYPES` as a column and fills the absent ones with `numpy.nan`. A frame from a single-fuel request still carries all 15 fuel columns. The NaN fill only covers a fuel absent from the **whole** response, so under a single-fuel facet it never covers the requested fuel. | `gridstatus/eia.py:961-964` |
| The pivot runs `pivot_table(values="MW", aggfunc="sum")` after `astype(float)`. pandas sums an all-null group to `0.0` at the default `min_count=0`, so **a null EIA value lands as `0.0` before our code runs**. Reproduced on pandas 2.3.3: `[0.0, None, 12.5]` pivots to `[0.0, 0.0, 12.5]`. | `gridstatus/eia.py:950-955` |
| An hour with **no row** for the requested fuel is absent from the pivot index. The frame is one row shorter and nothing raises. Reproduced on pandas 2.3.3. | `gridstatus/eia.py:950-955` |
| `EIA_FUEL_TYPES` lists `"Natural Gas"` and `"Petroleum"`. It does not list "Oil" or "Gas". | `gridstatus/eia_constants.py:3-19` |
| The gridstatus integration test asserts the returned columns equal `EIA_FUEL_MIX_COLUMNS` for a respondent-only request. | `gridstatus/tests/source_specific/test_eia.py:188-206` |
| `_handle_time` sets `Interval End = period` and `Interval Start = period - 1h`. Both columns reach our records, so `interval_minutes` derives to 60 and is never assumed. | `gridstatus/eia.py:805-809` |
| The `fueltype` facet is the sort index for this route, so the API accepts it. | `gridstatus/eia.py:1032-1035` |
| EIA-930 energy source codes: `OIL` is "all petroleum products", `NG` is natural gas. | `docs/RESEARCH_SCENARIO_FORMAT_2026-08-01.md:912-943`, quoting the EIA-930 form instructions |
| `raw.hourly_wind` has primary key `(source, ts, horizon_days)` and no fuel column. | `db/migrations/001_init.sql:36-47` |
| `db/migrations/` holds `001`, `002`, `003` only. `004` is free. | `ls db/migrations/` |
| Migrations run in filename order on **first volume init** only. | `docker-compose.yml:12` |
| `--dataset` choices come from `sorted(DATASETS)`, so a new dataset appears in the CLI (command line interface) with no CLI edit. | `src/owr/etl/cli.py:301` |
| `uv run pytest` baseline is 360 passed, 3 skipped. Continuous integration installs the `etl` extra, so `gridstatus` is importable there. | `docs/HANDOFF.md:921`, `.github/workflows/ci.yml:28-31` |

### What gridstatus supports for fuel-type series

One route, one call shape. `EIA().get_dataset("electricity/rto/fuel-type-data", ...)` with
`facets={"respondent": ..., "fueltype": ...}`. The fuel filter is a facet on the same
endpoint the wind path already calls. No separate fuel-mix method exists on the EIA client,
and no per-fuel helper exists. A facet value may be a scalar or a list, so one call can
carry several fuel codes.

The library does not narrow the returned columns to the requested fuel. It pivots and then
adds every known fuel column, `numpy.nan` filled. So the column set is identical whether you
request one fuel or all of them, and the adapter must select its column by name.

Two consequences decide what the adapter can and cannot detect. The library converts a null
value to `0.0` and drops an hour that has no row at all, and both conversions happen before
any of our code runs. So the adapter can catch a **renamed** fuel column, and it cannot catch
a null hour or a missing hour. `hourly_gaps` (step 1h) covers the missing hour. Nothing
covers the null hour, and the plan says so rather than implying a guarantee it cannot give.

---

## Decisions, with the alternative named

**D1. One new table, `raw.hourly_fuel_gen`, keyed on `(source, ts, fuel_code)`.**
The alternative is to reuse `raw.hourly_wind`. It fails: that table's primary key is
`(source, ts, horizon_days)` and it has no fuel column, so oil and gas rows collide under a
shared `source` string, and a per-fuel `source` string labels oil rows as wind
(`docs/HANDOFF.md:861-865`). A second alternative, one table per fuel, duplicates the schema
for every future fuel code. The `fuel_code` column costs one column and generalizes.

**D2. Two dataset keys, `oil` and `gas`, over one combined `fuel` key.**
The repository's unit is "one dataset key = one provider query = one provenance record".
A single key that pulls both fuels stamps one `source` string across two series and makes
the audit record ambiguous. Two keys cost one extra `RawDataset` descriptor of six lines.
Both descriptors point at the same table.

**D3. Store `interval_minutes` on every row.**
EIA-930 fuel-type data is hourly, so the value is 60. Store it anyway. Energy is
`gen_mw * interval_minutes / 60`, the repository has already paid for one assumed interval
(five minute readings read as hourly, a 12x error, `extract.py:57-61`), and `Interval End`
is present on every record so the width is free. `raw.system_load` already carries the
column; `raw.hourly_wind` does not. Follow the newer pattern.

**D4. `fuel_code` holds the EIA-930 code, `OIL` and `NG`.**
It is the provider's own code, it appears verbatim in `source_query`, and it is the value
the facet carried. The alternative, a friendly `PETROLEUM` / `NATURAL_GAS`, invents a second
vocabulary for the same thing.

**D5. `describe_query` returns a single line.**
`EIAWindSource.describe_query` embeds a newline before the "api key read from" note
(`extract.py:533-539`). `write_rows_csv` writes `source_query` into one `#` banner line, so
that newline splits the banner and the second line is not comment prefixed. `read_rows_csv`
then treats it as the header and raises `RowsCsvError`. See risk R2. The new source avoids
the defect by construction, and Phase 4 test 43 proves the round trip.

**D6. Leave `EIAWindSource` and the wind path untouched.**
The change is additive. The one shared edit is the `--zone` guard, extracted to a helper that
produces a byte-identical message for wind (Phase 3).

---

## Phase 1 — the pure layer: fuel series, observation, datasets, adapter

Goal: everything below the provider call, testable with plain dictionaries and one pandas
frame. No network. No credentials. No database.

### File: `src/owr/etl/extract.py`

Insert in this order. Line numbers refer to the file as it stands today.

**1a. After `WindObservation` (line 91), add the observation.**

```python
@dataclass(frozen=True)
class FuelGenObservation:
    """One interval net-generation reading for a single EIA-930 fuel code.

    ``interval_minutes`` is required for the same reason ``LoadObservation``
    requires it: energy is ``gen_mw * interval_minutes / 60``, and an assumed
    width is a silent multiplicative error. EIA-930 fuel-type data is hourly, so
    the value is 60 in practice, derived from ``Interval End - Interval Start``
    rather than hard-coded (docs/PLAN_EIA_OIL_GAS.md D3).
    """

    ts: datetime
    fuel_code: str
    gen_mw: float
    interval_minutes: float

    def __post_init__(self) -> None:
        if not self.fuel_code:
            raise ValueError("fuel_code is required")
        if self.interval_minutes <= 0:
            raise ValueError("interval_minutes must be positive")
```

**1b. Immediately after it, add the fuel series descriptors under a new banner comment.**

```python
# ---------------------------------------------------------------------------
# EIA-930 fuel series — the API facet code, the pivoted column, the stored code
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EIAFuelSeries:
    """One EIA-930 fuel category, from the API facet down to the stored row.

    dataset_name
        CLI key and ``RawDataset.name``, e.g. ``'oil'``.
    code
        EIA-930 energy source code, used twice on purpose: as the ``fueltype``
        facet value sent to the API, and as the ``fuel_code`` written to
        ``raw.hourly_fuel_gen``. ``'OIL'`` is "all petroleum products",
        ``'NG'`` is natural gas (EIA-930 form instructions, energy source codes).
    frame_columns
        Accepted column names on a provider record, most authoritative first.
        ``gridstatus._handle_fuel_type_data`` pivots the API's ``type-name`` and
        title-cases it, so oil arrives as ``'Petroleum'`` and gas as
        ``'Natural Gas'`` — never ``'Oil'``, never ``'Gas'``
        (gridstatus/eia_constants.py:3-19). ``frame_columns[0]`` is the canonical
        name and is what the non-finite error reports. Every alias is fuel
        specific on purpose: a shared ``'gen_mw'`` alias would let a gas record
        feed the oil adapter and be stamped ``fuel_code='OIL'``.
    source
        Provenance producer id, and the first component of the idempotency key.
    """

    dataset_name: str
    code: str
    frame_columns: tuple[str, ...]
    source: str


EIA_OIL = EIAFuelSeries(
    dataset_name="oil",
    code="OIL",
    frame_columns=("Petroleum", "oil_mw"),
    source="eia930.isne.oil",
)

EIA_GAS = EIAFuelSeries(
    dataset_name="gas",
    code="NG",
    frame_columns=("Natural Gas", "gas_mw"),
    source="eia930.isne.gas",
)

EIA_FUEL_SERIES: dict[str, EIAFuelSeries] = {s.dataset_name: s for s in (EIA_OIL, EIA_GAS)}
```

**1c. After `_wind_values` (line 149), add the value mapping.**

```python
def _fuel_values(obs: FuelGenObservation) -> dict[str, object]:
    return {
        "ts": obs.ts,
        "fuel_code": obs.fuel_code,
        "gen_mw": obs.gen_mw,
        "interval_minutes": obs.interval_minutes,
    }
```

**1d. After `HOURLY_WIND` (line 177), add the table constants and the two datasets, then
extend `DATASETS` at line 179.**

```python
# Oil and gas share one table: the row's natural key is (source, ts, fuel_code),
# so a second fuel code never collides with a first (docs/PLAN_EIA_OIL_GAS.md D1).
FUEL_GEN_TABLE = "raw.hourly_fuel_gen"
FUEL_GEN_VALUE_COLUMNS = ("ts", "fuel_code", "gen_mw", "interval_minutes")
FUEL_GEN_CONFLICT_KEY = ("source", "ts", "fuel_code")

HOURLY_OIL = RawDataset(
    name=EIA_OIL.dataset_name,
    table=FUEL_GEN_TABLE,
    value_columns=FUEL_GEN_VALUE_COLUMNS,
    conflict_key=FUEL_GEN_CONFLICT_KEY,
    to_values=_fuel_values,
)

HOURLY_GAS = RawDataset(
    name=EIA_GAS.dataset_name,
    table=FUEL_GEN_TABLE,
    value_columns=FUEL_GEN_VALUE_COLUMNS,
    conflict_key=FUEL_GEN_CONFLICT_KEY,
    to_values=_fuel_values,
)

DATASETS: dict[str, RawDataset] = {
    ds.name: ds
    for ds in (HOURLY_LOAD, HOURLY_LMP, HOURLY_WIND, HOURLY_OIL, HOURLY_GAS)
}
```

**1e. After `wind_observations_from_records` (line 355), add the adapter.**

```python
def fuel_observations_from_records(
    records: Iterable[dict[str, object]],
    fuel: EIAFuelSeries,
    *,
    default_interval_minutes: float | None = None,
) -> list[FuelGenObservation]:
    """Normalize gridstatus EIA-930 fuel-type records for one fuel code.

    **What ``0.0`` means here, and what this function cannot tell you.**
    ``_handle_fuel_type_data`` pivots with ``aggfunc='sum'`` after ``astype(float)``
    (gridstatus/eia.py:950-955), and pandas sums an all-null group to ``0.0`` at
    the default ``min_count=0``. So a null EIA telemetry value arrives as ``0.0``,
    indistinguishable from a real zero. ISO-NE petroleum output is legitimately
    ``0.0`` for most hours of the year, so the two cases cannot be separated after
    the fact. Do not read ``0.0`` as proof of zero output.

    **What a NaN means.** Under a single-fuel facet the requested fuel column is
    built from the returned rows, so it is never NaN-filled; only the other 14
    fuel columns are. A NaN in the requested column therefore means the pivot
    produced no such column at all, which is the signature of a renamed fuel in
    the API. That is what the guard below catches. A missing hour is a different
    failure and is invisible here: it is an absent row, so use
    :func:`hourly_gaps`.

    ``0.0`` is kept; NaN and infinity raise.
    """
    observations: list[FuelGenObservation] = []
    for r in records:
        ts = _as_datetime(_first(r, _TS_KEYS))
        gen_mw = float(_first(r, fuel.frame_columns))  # type: ignore[arg-type]
        if not math.isfinite(gen_mw):
            raise ValueError(
                f"non-finite {fuel.frame_columns[0]} value at ts={ts.isoformat()}: "
                f"gridstatus NaN-fills an unreported fuel column, so EIA-930 returned "
                f"no {fuel.code} rows for this hour"
            )
        observations.append(
            FuelGenObservation(
                ts=ts,
                fuel_code=fuel.code,
                gen_mw=gen_mw,
                interval_minutes=_interval_minutes_for(
                    r, ts, default_interval_minutes=default_interval_minutes
                ),
            )
        )
    return observations
```

**1f. After the adapter, add the gap check.** A missing hour is an absent row, not a
NaN, so nothing in the pull path can raise on it (R4). This is the only thing that detects
it. It takes timestamps rather than observations so the operator can run it over an `--out`
CSV as well as over a live pull.

```python
def hourly_gaps(timestamps: Iterable[datetime]) -> list[datetime]:
    """Hours missing from an hourly series, between its own first and last reading.

    EIA-930 omits an hour entirely when it has no row for the requested fuel, and
    ``pivot_table`` then drops that hour from the index, so a gap arrives as a
    shorter frame rather than as a NaN or an error
    (docs/PLAN_EIA_OIL_GAS.md R4). Duplicates and unsorted input are tolerated.

    Detects interior holes only. Truncation at either end is invisible here,
    because the series defines its own bounds; compare ``rows_built`` against the
    requested window for that. The eventual home for this gate is
    ``etl validate`` (docs/PLAN.md Phase 2 step 2).
    """
    seen = sorted(set(timestamps))
    if len(seen) < 2:
        return []
    step = timedelta(hours=1)
    gaps: list[datetime] = []
    cursor = seen[0] + step
    for ts in seen[1:]:
        while cursor < ts:
            gaps.append(cursor)
            cursor += step
        cursor = ts + step
    return gaps
```

Add `timedelta` to the existing `from datetime import date, datetime` import at
`src/owr/etl/extract.py:32`.

**1g. Module docstring.** In the paragraph that starts "Adding LMP or EIA is a matter of",
replace the last sentence with: ``` ``load``, ``wind``, ``oil`` and ``gas`` are wired end to
end; ``lmp`` has its dataset + record adapter registered (and tested) with the live source
left as the documented extension point. ```

**1h. `records_from_frame` docstring.** Append one sentence to the "No missing-value
conversion" paragraph: "The same reasoning covers ``fuel_observations_from_records``."

### File: `tests/test_etl_eia_fuel.py` (new)

Import the fakes rather than copy them. `tests/test_etl_eia.py` already exports
`FakeEIAClient`, `FakeFrame`, `FakeTimestamp` and `SENTINEL`; `tests/test_etl_extract.py`
exports `FakeConn`. Cross-test import is the existing pattern
(`tests/test_etl_eia.py:212`).

Add a module constant copied verbatim from `gridstatus/eia_constants.py:21-26` at version
0.36.0:

```python
GRIDSTATUS_FUEL_MIX_COLUMNS = (
    "Interval Start", "Interval End", "Respondent", "Respondent Name",
    "Battery Storage", "Coal", "Geothermal", "Hydro", "Natural Gas", "Nuclear",
    "Other", "Other Energy Storage", "Petroleum", "Pumped Storage", "Solar",
    "Solar With Integrated Battery Storage", "Unknown Energy Storage", "Wind",
    "Wind With Integrated Battery Storage",
)
```

Add two frame builders. Every number in them is synthetic, chosen to be readable, and none
of it is measured ISO-NE data.

1. `both_fuels_frame()` returns a `pandas.DataFrame` with those 19 columns, two hourly rows,
   `Petroleum = [0.0, 12.5]`, `Natural Gas = [4210.0, 4155.0]`, and `numpy.nan` in the other
   13 fuel columns. This is a **superset** of the production shape, not a mirror of it: it
   proves column selection when several fuels are populated.
2. `single_fuel_frame(column, values)` returns the same 19 columns with only `column`
   populated and the other **14** NaN. This is the real shape, because production sends one
   fuel per call (decision D2).

Tests 1 to 25:

| # | Test | Asserts |
|---|---|---|
| 1 | `test_oil_record_normalizes_from_the_petroleum_column` | `{"Interval Start": ts, "Interval End": ts+1h, "Petroleum": 512.3}` gives `FuelGenObservation(ts, "OIL", 512.3, 60.0)` |
| 2 | `test_gas_record_normalizes_from_the_natural_gas_column` | same with `"Natural Gas"`, `fuel_code == "NG"` |
| 3 | `test_fuel_record_rejects_the_wrong_column_name` | a hand-built record carrying `"Oil"` raises `KeyError` listing the record's keys. On a real frame a renamed fuel arrives as a NaN-filled column instead, which test 7 covers. Both paths are loud. |
| 4 | `test_fuel_record_accepts_the_fuel_specific_alias_and_coerces_int` | `{"oil_mw": 400}` gives `400.0`; `{"gas_mw": 400}` gives `400.0` for the gas series |
| 5 | `test_gen_mw_alias_is_not_accepted_for_a_fuel_series` | a record carrying only `gen_mw` raises `KeyError` for both series. Pins finding N2: a shared alias would let a gas value be stamped `fuel_code="OIL"`. |
| 6 | `test_fuel_record_accepts_a_pandas_like_timestamp` | `FakeTimestamp` for both `Interval Start` and `Interval End` |
| 7 | `test_zero_generation_is_kept_and_is_not_a_reported_zero` | `Petroleum = 0.0` gives `gen_mw == 0.0` and raises nothing. The docstring and this test name state the limit: gridstatus already summed a null group to `0.0`, so `0.0` means "zero or not reported" and the adapter cannot separate the two. **Load bearing.** |
| 8 | `test_fuel_record_rejects_nan_and_inf_and_names_the_column` | both raise `ValueError`; message matches `"Petroleum"` and `"OIL"`. This is the renamed-column signal, not the missing-hour signal. |
| 9 | `test_fuel_record_missing_timestamp_raises_keyerror` | |
| 10 | `test_fuel_record_without_interval_end_and_without_default_raises` | `ValueError` matching `"interval_minutes"` |
| 11 | `test_fuel_record_interval_minutes_from_default` | `default_interval_minutes=60.0` applies |
| 12 | `test_fuel_record_empty_list_is_empty` | |
| 13 | `test_fuel_observation_rejects_blank_code_and_non_positive_interval` | both `__post_init__` guards |
| 14 | `test_both_fuels_frame_yields_only_the_requested_fuel` | `both_fuels_frame()` through `records_from_frame`, then each adapter. Oil gives `[0.0, 12.5]` and `"OIL"`; gas gives `[4210.0, 4155.0]` and `"NG"`. Neither reads a NaN column. Superset shape. |
| 15 | `test_single_fuel_frame_is_the_production_shape` | `single_fuel_frame("Petroleum", [0.0, 12.5])` through the oil adapter gives two observations; the 14 other fuel columns stay NaN and are never read. **Load bearing: this is the frame a real single-fuel call returns.** |
| 16 | `test_single_fuel_frame_of_the_other_fuel_raises_non_finite` | `single_fuel_frame("Natural Gas", ...)` through the **oil** adapter raises `ValueError` naming `Petroleum`. Proves the guard fires on the column the request did not populate. |
| 17 | `test_fixture_columns_match_the_installed_gridstatus_constant` | `pytest.importorskip("gridstatus")`, then `list(GRIDSTATUS_FUEL_MIX_COLUMNS) == EIA_FUEL_MIX_COLUMNS`. Catches a library rename on upgrade. Runs in the local venv and in continuous integration, both of which carry the `etl` extra. |
| 18 | `test_oil_and_gas_datasets_registered` | `DATASETS["oil"] is HOURLY_OIL`, `DATASETS["gas"] is HOURLY_GAS`, both `.table == "raw.hourly_fuel_gen"` |
| 19 | `test_fuel_build_rows_column_order_matches_dataset_columns` | row length equals `len(HOURLY_OIL.columns)`; `zip` maps `fuel_code` to `"OIL"` |
| 20 | `test_fuel_upsert_sql_shape` | `INSERT INTO raw.hourly_fuel_gen`; `ON CONFLICT (source, ts, fuel_code)`; `gen_mw = EXCLUDED.gen_mw` and `interval_minutes = EXCLUDED.interval_minutes` present; `fuel_code = EXCLUDED.`, `ts = EXCLUDED.`, `source = EXCLUDED.` absent |
| 21 | `test_fuel_upsert_sql_placeholder_count` | `sql.count("%s") == len(HOURLY_OIL.columns)` |
| 22 | `test_oil_and_gas_rows_do_not_collide_on_the_conflict_key` | build one oil row and one gas row at the same `ts`, extract the `(source, ts, fuel_code)` triples from both, assert they differ. Answers the collision blocker in `docs/HANDOFF.md:861-865`. **Load bearing.** |
| 23 | `test_fuel_upsert_rows_through_fake_conn` | two rows written through `FakeConn` |
| 24 | `test_hourly_gaps_finds_an_interior_hole` | drop the 02:00 reading from a 00:00 to 04:00 series; `hourly_gaps` returns exactly that hour. Unsorted input and a repeated timestamp change nothing. **Load bearing: this is the only detector for finding B2.** |
| 25 | `test_hourly_gaps_is_empty_for_a_contiguous_short_or_empty_series` | contiguous series, one reading, and `[]` all return `[]` |

### Verify Phase 1

```bash
cd /Users/mikkopalis/Desktop/Projects/active/offshore-wind-poc
uv run pytest tests/test_etl_eia_fuel.py -q
uv run ruff check .
```

---

## Phase 2 — migration 004

Goal: create the table, and pin the SQL (structured query language) against the Python
dataset descriptor without a database.

### File: `db/migrations/004_hourly_fuel_gen.sql` (new)

Take number 004. `docs/HANDOFF.md:864` and `docs/RESEARCH_SCENARIO_FORMAT_2026-08-01.md:973`
both reserve it for this work, and no `004` file exists.

```sql
-- Offshore Wind Reserve — Phase 2 ETL, migration 004
-- raw.hourly_fuel_gen: EIA-930 hourly net generation by fuel type, one row per
-- (source, ts, fuel_code). Feeds the Fuel-Fired Generation Offset metric.
--
-- Why a new table and not raw.hourly_wind: that table's primary key is
-- (source, ts, horizon_days) and it carries no fuel column, so oil and gas rows
-- collide under a shared source string, and a per-fuel source string would label
-- oil rows as wind. See docs/PLAN_EIA_OIL_GAS.md decision D1.
--
-- Why interval_minutes is stored and not assumed: energy is
-- gen_mw * interval_minutes / 60. See decision D3.
--
-- What gen_mw = 0.0 means: "zero output OR not reported". gridstatus pivots with
-- aggfunc='sum', and pandas sums an all-null group to 0.0, so a null EIA
-- telemetry value is already 0.0 before it reaches this table. ISO-NE petroleum
-- output is legitimately 0.0 for most hours, so the two cases cannot be told
-- apart here. Do not read a zero as evidence of a reporting outage, and do not
-- read it as evidence of a real measurement.
--
-- What a missing row means: EIA omits an hour that has no row for the fuel, so a
-- gap in ts is a gap in the source, never a NaN. Use extract.hourly_gaps.

CREATE TABLE raw.hourly_fuel_gen (
    ts               TIMESTAMPTZ      NOT NULL,
    fuel_code        TEXT             NOT NULL,  -- EIA-930 energy source code: 'OIL', 'NG'
    gen_mw           DOUBLE PRECISION NOT NULL,  -- avg MW over the interval; see note below
    interval_minutes DOUBLE PRECISION NOT NULL,
    -- provenance (db/migrations/001_init.sql header)
    source           TEXT             NOT NULL,
    retrieved_at     TIMESTAMPTZ      NOT NULL DEFAULT now(),
    source_query     TEXT             NOT NULL,
    dataset_version  TEXT             NOT NULL,
    PRIMARY KEY (source, ts, fuel_code),
    CONSTRAINT hourly_fuel_gen_fuel_code_upper
        CHECK (fuel_code <> '' AND fuel_code = upper(fuel_code)),
    CONSTRAINT hourly_fuel_gen_interval_positive
        CHECK (interval_minutes > 0)
);
SELECT create_hypertable('raw.hourly_fuel_gen', 'ts', if_not_exists => TRUE);
```

The primary key contains `ts`, which TimescaleDB requires of a hypertable's unique key. The
`upper` check catches the trap of writing the pivoted column name `Petroleum` into
`fuel_code`.

### Test 26, in `tests/test_etl_eia_fuel.py`

`test_migration_004_matches_the_dataset_descriptor` (test 26). Read the SQL file through
`pathlib.Path(__file__).resolve().parents[1] / "db" / "migrations" / "004_hourly_fuel_gen.sql"`.
Assert every name in `HOURLY_OIL.columns` appears in the text, that
`"PRIMARY KEY (source, ts, fuel_code)"` appears, and that `HOURLY_OIL.table` appears. This
catches schema drift with no database.

### Verify Phase 2

```bash
uv run pytest tests/test_etl_eia_fuel.py -q
```

---

## Phase 3 — the provider source

Goal: the only network-touching and credential-touching code. Same key discipline as
`EIAWindSource`.

### File: `src/owr/etl/extract.py`

**3a. After `EIAWindSource` (line 543), add the source.**

```python
class EIAFuelSource:
    """Live EIA-930 hourly net generation for one fuel code (ISO-NE respondent).

    Same key discipline as :class:`EIAWindSource`. No key is stored on the
    instance, ``self._getenv`` is a callable rather than a mapping, and this is a
    plain class rather than a ``@dataclass`` so no generated ``__repr__`` can
    print a field that later holds a credential. Never call ``list_routes`` or
    ``list_facets`` on the client: they pass the key as a URL query parameter.

    Two deliberate differences from ``EIAWindSource``, both explained in
    docs/PLAN_EIA_OIL_GAS.md: ``version_provider`` is injectable, so this module's
    tests run with gridstatus absent (D6); and ``describe_query`` returns a single
    line, so ``write_rows_csv`` cannot split the provenance banner (D5).
    """

    def __init__(
        self,
        fuel: EIAFuelSeries,
        *,
        respondent: str = EIA_ISONE_RESPONDENT,
        client_factory: Callable[[], Any] = _default_eia_client,
        getenv: Callable[[str], str | None] = os.environ.get,
        version_provider: Callable[[], str] = gridstatus_version,
    ) -> None:
        self.fuel = fuel
        self.respondent = respondent
        self.source = fuel.source
        self._client_factory = client_factory
        self._getenv = getenv
        self._version_provider = version_provider

    def get_observations(self, start: date, end: date) -> list[object]:
        require_eia_api_key(self._getenv)  # before the client is built (our message first)
        client = self._client_factory()
        # Build the facets mapping here, never from a module-level constant:
        # gridstatus._facet_handler rewrites the caller's dict in place
        # (gridstatus/eia.py:104-111), so a shared constant would be corrupted
        # after the first call.
        frame = client.get_dataset(
            EIA_FUEL_TYPE_DATASET,
            start=start.isoformat(),
            end=end.isoformat(),
            frequency="hourly",
            facets={"respondent": self.respondent, "fueltype": self.fuel.code},
        )
        records = records_from_frame(frame)
        return list(fuel_observations_from_records(records, self.fuel))

    def describe_query(self, start: date, end: date) -> str:
        return (
            f"gridstatus.EIA().get_dataset('{EIA_FUEL_TYPE_DATASET}', "
            f"start={start.isoformat()}, end={end.isoformat()}, frequency=hourly, "
            f"facets={{respondent={self.respondent}, fueltype={self.fuel.code}}}) "
            f"[column={self.fuel.frame_columns[0]}; fuel_code={self.fuel.code}; "
            f"api key read from ${EIA_API_KEY_ENV}, value not recorded]"
        )

    def dataset_version(self) -> str:
        return self._version_provider()
```

**3b. Just before `source_for` (line 545), add the zone guard.**

```python
def _reject_load_zone(dataset_name: str, zone: str) -> None:
    """Guard: EIA-930 datasets are balancing-authority grain and take no load zone.

    With ``dataset_name='wind'`` the message is byte-identical to the one
    ``source_for`` raised inline before this helper existed.
    """
    if zone not in ("ISONE", "ISNE"):
        raise ValueError(
            f"the {dataset_name} dataset is EIA-930 balancing-authority data (respondent "
            f"{EIA_ISONE_RESPONDENT}) and has no load zone; got --zone {zone!r}. "
            f"Omit --zone or pass ISNE."
        )
```

**3c. Rewire `source_for`.** Replace the inline wind zone check with
`_reject_load_zone("wind", zone)`. Add this branch after the wind branch and before the
`if dataset_name in DATASETS` fallback:

```python
    if dataset_name in EIA_FUEL_SERIES:
        _reject_load_zone(dataset_name, zone)
        return EIAFuelSource(EIA_FUEL_SERIES[dataset_name])
```

Update the `source_for` docstring: "``load`` is wired to ISO-NE; ``wind``, ``oil`` and
``gas`` to EIA-930."

### File: `src/owr/etl/credentials.py`

The message in `require_eia_api_key` names only the wind dataset. Change the middle clause
to name all three:

```python
            f"https://www.eia.gov/opendata/register.php). The EIA datasets (wind, "
            f"oil, gas) need it even for --dry-run, because --dry-run still performs "
            f"the provider pull."
```

No existing test asserts the old phrase (`tests/test_etl_credentials.py:16-21` and
`tests/test_etl_eia.py:387-398` check the variable name, the URL, and the absence of a
traceback only).

### Tests 27 to 38

Tests 27 to 37 go in `tests/test_etl_eia_fuel.py`. Test 38 goes in
`tests/test_etl_credentials.py`.

| # | Test | Asserts |
|---|---|---|
| 27 | `test_source_for_oil_and_gas_return_fuel_sources` | `isinstance(..., EIAFuelSource)`; `.source` equals `"eia930.isne.oil"` and `"eia930.isne.gas"` |
| 28 | `test_source_for_fuel_rejects_a_load_zone` | `zone="ISNE"` and `zone="ISONE"` pass; `zone="NEMA"` raises `ValueError` naming the dataset and `ISNE` |
| 29 | `test_wind_zone_error_message_is_unchanged` | compare the full `str(exc)` from `source_for("wind", zone="NEMA")` against the literal expected text. Pins the 3b refactor. |
| 30 | `test_fuel_describe_query_contents` | contains `EIA_FUEL_TYPE_DATASET`, `respondent=ISNE`, `fueltype=OIL`, `frequency=hourly`, both dates, `column=Petroleum`, `fuel_code=OIL`, `$EIA_API_KEY` |
| 31 | `test_fuel_describe_query_is_single_line_and_deterministic` | `"\n" not in text`; two calls give the same string. Pins D5. |
| 32 | `test_fuel_get_observations_calls_get_dataset_with_expected_kwargs` | `dataset`, `frequency == "hourly"`, `facets == {"respondent": "ISNE", "fueltype": "OIL"}` |
| 33 | `test_fuel_source_sends_a_fresh_facets_mapping_on_every_call` | use a client subclass that snapshots `facets` and then list-wraps it in place, exactly as `_facet_handler` does. Call `get_observations` twice. Both snapshots equal the scalar form. A module-level facets constant fails this. |
| 34 | `test_fuel_get_observations_missing_key_never_builds_the_client` | `MissingCredentialError`; the factory is never called |
| 35 | `test_fuel_describe_query_never_contains_the_key_value` | `SENTINEL not in text` |
| 36 | `test_fuel_repr_and_vars_never_contain_the_key_value` | `SENTINEL` absent from `repr(src)` and `str(vars(src))` |
| 37 | `test_fuel_extract_rows_and_provenance_never_contain_the_key` | `monkeypatch.setenv("EIA_API_KEY", SENTINEL)`, run `extract(HOURLY_OIL, src, ...)` with `version_provider=lambda: "gridstatus==0.36.0-fake"`; no cell and no provenance field contains `SENTINEL`. The injected version keeps this test free of gridstatus. |
| 38 | `test_missing_key_message_names_the_eia_datasets` | message contains `"wind"`, `"oil"` and `"gas"` |

### Verify Phase 3

```bash
uv run pytest tests/test_etl_eia_fuel.py tests/test_etl_eia.py tests/test_etl_credentials.py -q
uv run ruff check .
```

---

## Phase 4 — CLI and CSV, tests only

Goal: prove the command line interface and the CSV (comma separated values) writer carry the
two new datasets with no production code change.

**No edit to `src/owr/etl/cli.py` and none to `src/owr/etl/rows_csv.py`.** `--dataset`
choices derive from `sorted(DATASETS)` (`cli.py:301`), and `write_rows_csv` and
`read_rows_csv` are already dataset generic. If either needs a change, stop and report it:
that means an assumption in this plan is wrong.

### Tests 39 to 45, in `tests/test_etl_eia_fuel.py`

| # | Test | Asserts |
|---|---|---|
| 39 | `test_cli_dataset_choices_include_oil_and_gas` | `cli.build_parser().parse_args(["extract", "--dataset", "oil", ...]).dataset == "oil"`; same for `gas` |
| 40 | `test_cli_dry_run_stdout_never_contains_the_key_for_oil` | key set to `SENTINEL`, a fake source, `SENTINEL` absent from captured stdout |
| 41 | `test_cli_missing_key_returns_2_for_oil_and_gas` | parametrized over `"oil"` and `"gas"`; uses the real `source_for`; exit code 2; output names `EIA_API_KEY` and the registration URL; no `"Traceback"` |
| 42 | `test_cli_dry_run_out_csv_carries_the_fuel_columns` | `--out` to `tmp_path`; banner has `# dataset = oil` and `# table = raw.hourly_fuel_gen`; the header line equals `",".join(HOURLY_OIL.columns)`; every data row's second field is `OIL` |
| 43 | `test_oil_rows_csv_round_trips_through_read_rows_csv` | write with a provenance whose `source_query` came from a real `EIAFuelSource.describe_query`, read it back with `read_rows_csv`, assert the columns equal `HOURLY_OIL.columns` and `set(frame["fuel_code"]) == {"OIL"}`. **Load bearing: this is the test D5 exists for.** |
| 44 | `test_fuel_dry_run_builds_rows_and_writes_nothing` | `rows_built == 2`, `rows_written == 0`, `dry_run is True` |
| 45 | `test_fuel_reextract_same_window_is_idempotent` | two extracts with the same `retrieved_at` build identical rows |

### Verify Phase 4

```bash
uv run pytest -q
uv run ruff check .
env -u EIA_API_KEY uv run etl extract --dataset oil --start 2026-01-01 --end 2026-01-02 --dry-run; echo "exit=$?"
uv run etl extract --help | grep -- --dataset
uv run simulate --input examples/synthetic_winter_stress.csv --storage-mwh 20000 --power-mw 2000
```

Expect from the third command:

```
error: no EIA API key. Set $EIA_API_KEY (free registration: https://www.eia.gov/opendata/register.php). The EIA datasets (wind, oil, gas) need it even for --dry-run, because --dry-run still performs the provider pull.
exit=2
```

Expect from the fourth command: `--dataset {gas,lmp,load,oil,wind}`.
Expect the fifth command to print exactly what it prints today. The engine is untouched.

---

## Phase 5 — Docker-gated Postgres round trip

Goal: prove migration 004 and `build_upsert_sql(HOURLY_OIL)` agree against a real database.
This phase raises the skip count from 3 to 4 whenever `OWR_TEST_DATABASE_URL` is unset, which
is the default developer and continuous-integration case. With that variable set against a
database carrying migration 004, the test runs and skips stay at 3. Say so in the handoff so
nobody reads the new skip as an accident.

> **Destructive.** `docker compose down -v` deletes the development database volume.
> Migrations run only on first volume init (`docker-compose.yml:12`). Apply the single file
> instead if you want to keep the volume.

### Test 46, in `tests/test_etl_eia_fuel.py`

Follow `tests/test_pg_store.py:9-24` exactly: `psycopg = pytest.importorskip("psycopg")`,
read `OWR_TEST_DATABASE_URL`, and skip the test when it is unset. Then:

1. Truncate `raw.hourly_fuel_gen`.
2. Build oil rows and gas rows for the same two timestamps.
3. Call `upsert_rows(conn, HOURLY_OIL, oil_rows)` and `upsert_rows(conn, HOURLY_GAS, gas_rows)`.
4. Assert `SELECT count(*)` returns 4.
5. Run both upserts again with a later `retrieved_at`.
6. Assert the count is still 4 and `retrieved_at` moved. That is the idempotency proof.

### Verify Phase 5

```bash
docker compose exec -T db psql -U owr -d owr < db/migrations/004_hourly_fuel_gen.sql
OWR_TEST_DATABASE_URL=postgresql://owr:owr@localhost:5432/owr uv run pytest tests/test_etl_eia_fuel.py -q
```

If Docker is unavailable, skip this phase and record that in the handoff. Test 26 stays the
mandatory substitute.

---

## Phase 6 — documents and close out

1. `docs/DATA_SOURCES.md`, "Ingest sources" table: add one row.

   | EIA hourly generation by fuel type (RTO) — oil and gas | https://www.eia.gov/opendata/browser/electricity/rto/fuel-type-data | REST/JSON | hourly | **EIA API key (free, required)** | Hourly petroleum (`OIL`) and natural gas (`NG`) net generation, respondent `ISNE`; lands in `raw.hourly_fuel_gen`; feeds the Fuel-Fired Generation Offset metric | extractor shipped; live pull unverified, key pending |

2. `docs/DATA_SOURCES.md`: add a section "## EIA-930 fuel series, what the numbers mean —
   2026-08-05". Record four facts, each with its citation.

   - The pivoted column for oil is `Petroleum` and for gas is `Natural Gas`, never "Oil" and
     never "Gas" (`gridstatus/eia_constants.py:3-19`).
   - **`0.0` means "zero output or not reported".** gridstatus pivots with `aggfunc="sum"`
     and pandas sums an all-null group to `0.0`, so a null EIA telemetry value arrives as a
     zero (`gridstatus/eia.py:950-955`; reproduced on pandas 2.3.3). ISO-NE petroleum output
     is legitimately `0.0` for most hours, so the two cases cannot be told apart. Any metric
     built on these rows inherits that limit.
   - **A missing hour is an absent row, not a NaN.** EIA omits an hour that has no row for
     the requested fuel, so a gap arrives as a shorter series. `extract.hourly_gaps` reports
     interior holes; edge truncation needs a row count against the window.
   - A NaN in the requested fuel column means the pivot produced no such column, which is the
     signature of a renamed fuel upstream. The adapter raises on it.

3. the repo map: no change. No new module lands, and `db/migrations/` is already mapped.

4. `docs/BOARD.md`: add a Done row with the date, the pytest counts, and the ruff result.

5. `docs/HANDOFF.md`: add a session block. State the real test counts, the migration number,
   and that the live pull is still key-gated.

---

## Key-gated verification — run once `$EIA_API_KEY` is confirmed

Everything above passes with no key. This section is the only part that needs one.

**Step 1, the control.** Run the shipped wind path first. It has never run live either
(`docs/HANDOFF.md:866-868`). If it fails, the fault is not in the new code.

```bash
uv run etl extract --dataset wind --start 2026-01-01 --end 2026-01-03 --dry-run --out /tmp/wind_probe.csv
```

**Step 2, oil. Step 3, gas.**

```bash
uv run etl extract --dataset oil --start 2026-01-01 --end 2026-01-03 --dry-run --out /tmp/oil_probe.csv
uv run etl extract --dataset gas --start 2026-01-01 --end 2026-01-03 --dry-run --out /tmp/gas_probe.csv
```

Expected stdout for step 2:

```
etl extract [oil]: would write 49 rows
  source          = eia930.isne.oil
  retrieved_at    = 2026-08-05T...+00:00
  source_query    = gridstatus.EIA().get_dataset('electricity/rto/fuel-type-data', start=2026-01-01, end=2026-01-03, frequency=hourly, facets={respondent=ISNE, fueltype=OIL}) [column=Petroleum; fuel_code=OIL; api key read from $EIA_API_KEY, value not recorded]
  dataset_version = gridstatus==0.36.0
```

The row count is 49 if the EIA window includes both edge hours and 48 if it excludes the end
hour. gridstatus asserts both edges inclusive in its own integration test, so expect 49. Any
count far from 48 means the window handling changed; stop and report it.

**Step 4, the five checks that matter.** Run them as one Python command so the key never
enters the shell command line or the shell history.

Test the key against the **whole file text**, before any filter. `source_query` is written
into the `#` banner (`rows_csv.py:45`), which is the likeliest place for a provider leak to
land, so a check that filters `#` lines first would print "clean" over a real leak.

```bash
uv run python - <<'PY'
import csv, os
from datetime import datetime
from owr.etl.extract import hourly_gaps

raw = open("/tmp/oil_probe.csv").read()                 # full text, banner included
print("key in file   :", "LEAK" if os.environ["EIA_API_KEY"] in raw else "clean")

data = list(csv.DictReader([r for r in raw.splitlines(True) if not r.startswith("#")]))
gaps = hourly_gaps(datetime.fromisoformat(r["ts"]) for r in data)
print("rows          :", len(data))
print("fuel codes    :", sorted({r["fuel_code"] for r in data}))
print("interval      :", sorted({r["interval_minutes"] for r in data}))
print("nonzero hours :", sum(1 for r in data if float(r["gen_mw"]) != 0.0))
print("interior gaps :", len(gaps), [g.isoformat() for g in gaps[:5]])
PY
```

Expected: `key in file : clean`, `fuel codes : ['OIL']`, `interval : ['60.0']`,
`interior gaps : 0 []`.

Read `nonzero hours` as shape, not as a pass or fail. A count of 0 is **not** a failure:
ISO-NE runs almost no petroleum outside a winter cold snap, and a reported null also arrives
as a zero (R3), so the two cannot be separated. Run the same block against
`/tmp/gas_probe.csv` and expect `['NG']` and a nonzero hour count close to the row count,
because natural gas runs continuously in ISO-NE. Any nonzero `interior gaps` is a real hole
in the source; record the hours and tell the team before the backfill.

**Step 5, the database path.** Destructive branch first.

```bash
# Keeps the volume: apply the one file.
docker compose exec -T db psql -U owr -d owr < db/migrations/004_hourly_fuel_gen.sql
uv run etl extract --dataset oil --start 2026-01-01 --end 2026-01-03 --dsn postgresql://owr:owr@localhost:5432/owr
uv run etl extract --dataset oil --start 2026-01-01 --end 2026-01-03 --dsn postgresql://owr:owr@localhost:5432/owr
docker compose exec -T db psql -U owr -d owr -c \
  "SELECT fuel_code, count(*), min(ts), max(ts) FROM raw.hourly_fuel_gen GROUP BY 1;"
```

Expect one row, `OIL`, count 49 after both runs. A count of 98 means the upsert key is wrong.

**Step 6, the backfill, once the probes pass.** Pull one winter at a time. gridstatus pages
at 5000 rows with no retry, so a five-year single-fuel pull is nine sequential pages and a
network error loses the whole call. The upsert is idempotent, so a failed year is safe to
re-run.

**Run the completeness check after every window. It is not optional.** A gap is an absent
row, so the pull reports success over an incomplete series (R4). Two numbers close it:

1. Compare `rows_built` from the CLI output against the window's hour count. For
   `--start YYYY-01-01 --end YYYY-04-01` expect `24 * days + 1` if the EIA window includes
   both edges. A shortfall is missing hours at the edges or inside.
2. Run the step 4 block over that window's `--out` CSV and read `interior gaps`. It must be
   `0`.

Record both numbers per window in the handoff. A window that fails either check is not
backfilled; report it and decide with the team before you write it to Postgres.

---

## Risks, ranked

**R1 (high). The pivoted column names are unverified against a live response.** The evidence
is the installed library's `EIA_FUEL_TYPES` list and its title-case pivot, not a live payload.
If the API's `type-name` changes, the adapter raises `KeyError` listing the record's actual
keys. That is loud and diagnosable, never silent bad data. On a real frame a renamed fuel
arrives as a NaN-filled column instead, which raises the non-finite error. Mitigation: the
fuel-specific alias tuple, tests 3, 8, 16 and 17, and key-gated step 2.

**R2 (high, pre-existing, out of scope).** `EIAWindSource.describe_query`
(`src/owr/etl/extract.py:533-539`) embeds a newline. `write_rows_csv`
(`src/owr/etl/rows_csv.py:45`) writes `source_query` into one `#` banner line, so the newline
produces a second line with no `#` prefix. `read_rows_csv` does not filter that line and
parses it as the header, which raises `RowsCsvError`. Any wind CSV written by
`etl extract --dataset wind --out` therefore fails to read back. The fix is one line: join
the two clauses with a space instead of `\n`. It is out of scope because it changes a shipped
provenance string. The new fuel path avoids it by construction (D5, test 43). Report it to
the team.

Reproduced 2026-08-05: `write_rows_csv` then `read_rows_csv` on a wind batch raises
`RowsCsvError: ... cannot parse as CSV: Length of header or names does not match length of
data.` The stray banner line becomes the header row.

**R3 (high). `gen_mw = 0.0` means "zero output or not reported", and nothing downstream can
tell the two apart.** Two facts combine. gridstatus pivots with
`pivot_table(values="MW", aggfunc="sum")` and pandas sums an all-null group to `0.0` at the
default `min_count=0`, so a null EIA telemetry value is already `0.0` before our adapter
runs. Reproduced on pandas 2.3.3: `[0.0, None, 12.5]` pivots to `[0.0, 0.0, 12.5]`. And
ISO-NE petroleum output is legitimately `0.0` for most hours of the year, so a zero is the
expected value as well as the failure value. There is no fix inside this repository: the
conversion happens in the library, upstream of every line we write. Mitigation is honesty,
not code. The adapter docstring, the migration comment, the DATA_SOURCES note, and test 7 all
state the limit. The key-gated checks report a nonzero-hour count so the operator sees the
shape of the series rather than a single row total. Do not add a rule that treats zero as
suspect: for oil that would flag most of the year.

**R4 (medium). A missing hour is an absent row, so a backfill with holes lands green.**
Under a single-fuel facet the requested fuel column is built from the rows that came back, so
an hour with no row is simply absent from the pivot index. The frame is one row shorter, the
adapter sees nothing wrong, and the upsert writes fewer rows than the window has hours.
Reproduced on pandas 2.3.3. The NaN column fill covers only a fuel absent from the whole
response, that is the other 14 fuels, so it never rescues this case. Mitigation:
`extract.hourly_gaps` (step 1f, tests 24 and 25) reports interior holes, and it is a named
step in key-gated steps 4 and 6. For truncation at the window edge, compare `rows_built`
against the window's hour count, which key-gated step 6 does. Do not silently backfill a gap
with an interpolated value; report it and decide with the team.

**R5 (medium). Migration 004 applies only on first volume init.** An existing development
database never gets the table. Mitigation: the `psql <` command in key-gated step 5.

**R6 (medium, pre-existing, out of scope). `raw.system_load` has no migration.**
The comment at `extract.py:152` cites "migration 005" and the descriptor at
`extract.py:157` targets `raw.system_load`, but
`db/migrations/` holds only 001, 002, 003. So `etl extract --dataset load` without
`--dry-run` fails against any database built from the repository. Taking 004 for the fuel
table does not block a later 005; the files are independent and run in filename order.
Report it to the team.

**R7 (medium). `gridstatus._facet_handler` mutates the caller's dictionary in place.** A
module-level facets constant would carry list-wrapped values into every later call.
Mitigation: build the dictionary inside `get_observations`, plus test 33.

**R8 (low). An empty window raises `KeyError: 'period'` from inside gridstatus.**
`_handle_time` reads `df["period"]` on a frame that has no columns. The CLI catches it and
prints `error: KeyError: 'period'` with exit code 1. Do not wrap it. Name it here so the
operator recognizes it as "no data in this window", not a defect.

**R9 (low). Two dataset descriptors share one table**, so `read_rows_csv` cannot tell an oil
CSV from a gas CSV by its header. The banner line `# dataset = oil` carries the difference.
No consumer reads fuel CSVs yet.

**R10 (low). `docs/PLAN_REAL_DEMO_BRIDGE.md` is in flight** and edits
`src/owr/etl/cli.py`, `docs/DATA_SOURCES.md`, `docs/BOARD.md` and `docs/HANDOFF.md`. This
plan edits none of the CLI and only appends to the three documents. Land whichever finishes
first and rebase the other.

---

## Assumptions

1. The EIA-930 `fueltype` facet accepts `OIL` and `NG` for respondent `ISNE` at hourly
   frequency. Evidence: the EIA-930 form's energy source code list and the `fueltype` sort
   index in `gridstatus/eia.py:1032-1035`. Unproven live. This is the single assumption the
   key-gated steps exist to settle.
2. `Interval End - Interval Start` is 60 minutes on this route, so `interval_minutes` is 60.
   Evidence: `gridstatus/eia.py:805-809`.
3. The Fuel-Fired Generation Offset task reads `raw.hourly_fuel_gen` or its CSV and owns any
   conversion to energy. This plan stores average MW (megawatts) plus the interval width, and
   computes no MWh (megawatt hours).
4. Migration number 004 is free and is the number both `docs/HANDOFF.md:864` and
   `docs/RESEARCH_SCENARIO_FORMAT_2026-08-01.md:973` reserved for this work.

---

## Definition of done

1. `uv run ruff check .` prints "All checks passed".
2. `uv run pytest` passes. The count rises by the number of new tests, about 47 collected.
   No existing test changes status. Skips stay at **3** when Phase 5 is not written, and when
   Phase 5 is written and `OWR_TEST_DATABASE_URL` points at a live Postgres with migration
   004 applied. Skips are **4** when Phase 5 is written and that variable is unset, which is
   the default developer and continuous-integration case. Record the real numbers in the
   handoff; do not copy the estimate.
3. `env -u EIA_API_KEY uv run etl extract --dataset oil ... --dry-run` exits 2 with the
   actionable message and no traceback.
4. `uv run etl extract --help` lists `oil` and `gas` in `--dataset`.
5. `db/migrations/004_hourly_fuel_gen.sql` exists and test 26 passes.
6. `src/owr/etl/cli.py` and `src/owr/etl/rows_csv.py` are unchanged.
7. The key-gated section is recorded as not yet run, with the exact command to run.
8. No model name, no assistant tooling reference, and no generated-by attribution in any
   tracked file, commit message, or pull request body.
