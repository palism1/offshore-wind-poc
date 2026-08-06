# Research — scenario time-series input format

Date: 2026-08-01. Point-in-time record, not current state.

Question: one format, defined once, that `etl transform` writes and
`owr.scenario_input.read_day_profiles` reads.

Pipeline: `deep-build`. Stage 1 `scout` (Sonnet 5, model routing confirmed from the
subagent transcript). Stage 2 `researcher` (Opus 5). Stage 3 `verifier` (Fable).

---

## Stage 1 — breadth survey (scout)

### The repo gap, stated plainly

Two files disagree on the input contract. `src/owr/scenario_input.py:1-27` reads hourly rows
(`date`, `hour` 0-23, `load_mw`) and requires exactly 24 rows per date; its own docstring calls
this "provisional... not a stable interface" and records that no migration carries these columns
and that `docs/PLAN.md` Phase 2 defines no CSV export step.
[Corrected 2026-08-02 after stage 3, finding C4: the original text quoted "nothing produces this
file" as a docstring quotation. That phrase is not in the docstring. The substance is supported.]
`src/owr/etl/transform.py` and `src/owr/etl/daily.py:1-27` compute daily-total energy, not
hourly rows, and already solve the two hard problems correctly: `daily.py` integrates power over
interval width (never sums), stores instants UTC-normalized, and derives 23/24/25-hour local days
from `zoneinfo` at read time rather than hard-coding 24. The gap is that the correct DST and
integration logic lives in `daily.py`, and the simulator input format predates it and never
adopted its conventions.

### What the field uses

| Tool                     | Shape                                                                                                                                   | Timestamp typing                                                    | Metadata sidecar                                        | Source                                                                                                                                        |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| PyPSA                    | Wide CSV, `network.snapshots` as index, one file per component-attribute (`generators-p_set.csv`)                                       | Naive local (project convention), no timezone column                | None; static/series split by filename convention        | [Data Import and Export, PyPSA docs](https://docs.pypsa.org/v0.25.1/import_export.html), retrieved 2026-08-01                                 |
| Calliope                 | Wide CSV, first column ISO 8601 timestamp (`YYYY-MM-DD hh:mm:ss`) as index, one column per location                                     | Naive local, no offset in the timestamp string                      | `config.build.time_format` setting, not a per-row field | [Data tables, Calliope docs](https://calliope.readthedocs.io/en/latest/basic/data_tables/), retrieved 2026-08-01                              |
| GridPath                 | Separate `timepoints` CSV joined by row/id to value CSVs                                                                                | Not UTC/offset-typed in the surveyed pages                          | Yes, `timepoints.csv` is itself the metadata table      | [GridPath docs](https://gridpath.readthedocs.io/en/stable/usage.html), retrieved 2026-08-01                                                   |
| Sienna / PowerSystems.jl | Bulk series values in an HDF5 store, referenced by a JSON or CSV "time series pointer" file that carries an explicit `resolution` field | Resolution explicit and must be uniform across a `SingleTimeSeries` | Yes, pointer file plus HDF5                             | [Time Series Data, PowerSystems.jl docs](https://nrel-sienna.github.io/PowerSystems.jl/v1.0/modeler_guide/time_series/), retrieved 2026-08-01 |
| oemof.tabular            | Frictionless "datapackage": CSV files (`elements/`, `sequences/`) plus a `datapackage.json` Table Schema                                | Governed by the JSON schema per field                               | Yes, `datapackage.json` required                        | [oemof.tabular usage docs](https://oemof-tabular.readthedocs.io/en/latest/usage.html), retrieved 2026-08-01                                   |
| pandapower               | In-memory pandas DataFrame passed to `DFData`; no on-disk format prescribed                                                             | Caller's choice                                                     | None                                                    | [Time Series Simulation, pandapower docs](https://pandapower.readthedocs.io/en/latest/timeseries.html), retrieved 2026-08-01                  |
| Open Power System Data   | Long/wide hybrid CSV plus `datapackage.json`; every row carries **both** a UTC column and a local CET/CEST column                       | Explicit dual-column                                                | Yes, resolution stated as 15min or 60min                | [OPSD time_series README](https://github.com/Open-Power-System-Data/time_series), retrieved 2026-08-01                                        |

Switch and TEMOA use CSV-based scenario inputs, but the searched sources did not surface enough
detail on timestamp typing to state a behavior claim. Marked for stage 2 to pull from source.

**Pattern.** Every actively maintained tool surveyed uses CSV, or CSV plus a JSON sidecar, as the
scenario input format. None of PyPSA, Calliope, GridPath, Switch, oemof, or pandapower use
Parquet, HDF5, or netCDF as the primary scenario input. HDF5 appears only inside Sienna, as a
Julia-only bulk store behind a pointer file.

### Standards bodies

- **EIA API v2** offers a `frequency` of `hourly` (UTC) or `local-hourly` (explicit offset suffix),
  a per-request choice rather than a fixed convention.
  [EIAapi intro](https://ramikrispin.github.io/EIAapi/articles/intro.html), retrieved 2026-08-01.
- **ENTSO-E Transparency Platform** XML carries an explicit `resolution` element per series
  (`PT15M`, `PT30M`, `PT60M`, `P1D`). The clearest surveyed case of a standard that names its own
  interval length instead of assuming it.
  [ENTSO-E XML schema use guide](https://eepublicdownloads.entsoe.eu/clean-documents/pre2015/events/Workshops/Transparency/entso-e-transparency-xml-schema-use-1-0.pdf), retrieved 2026-08-01.
- **Frictionless Data / Table Schema** describes CSV resources in JSON. It is generic, and carries
  no built-in interval-length or timezone field.
  [Data Package v1 spec](https://specs.frictionlessdata.io/guides/data-package/), retrieved 2026-08-01.
- **ISO-NE ISO Express** publishes web-services data as XML plus CSV report downloads. The exact
  CSV column layout is **unsourced** in this pass.
  [ISO-NE Web Services Data](https://www.iso-ne.com/participate/support/web-services-data), retrieved 2026-08-01.
- **NREL OEDI** was reported as stating that all published time-series data is UTC, to avoid DST
  complications. **Citation withdrawn 2026-08-02 after stage 3, finding C3.** The cited page,
  [OEDI on AWS](https://registry.opendata.aws/oedi-data-lake/), resolves and carries no such
  statement. The claim may hold on a specific dataset page. Do not rely on it.

### DST and integration, project by project

- **Open Power System Data** carries UTC and local timestamps on every row, so a reader never
  re-derives the offset.
- **ENTSO-E** carries an explicit `resolution` per series, so the reader is told the interval
  length rather than inferring it from row count.
- **NREL OEDI** avoids DST by storing UTC and saying so.
- **PyPSA and Calliope** index by a naive local timestamp with no offset column. The DST question
  falls to the modeler's `snapshots` construction, not to the format.
- **This repo's `daily.py`** already does the harder thing: UTC instants, local-day length from
  `zoneinfo` (23/24/25 h), naive timestamps rejected, `load_mw * interval_hours` integrated. No
  surveyed tool does strictly more. The gap is that `scenario_input.py` carries none of it.

### Shortlist for stage 2 (ranked by fit, not recommended)

**1. Long-format CSV with an explicit timestamp and resolution column, UTC-stored, local derived
at read time.** Unifies the OPSD dual-column pattern, the ENTSO-E `resolution` field, and this
repo's own `daily.py` conventions into one row shape (`ts_utc`, `interval_hours`, `load_mw`,
`wind_mw`). Cost: no new dependency; it extends `daily.py`'s model to sub-daily grain and adds a
writer. Rejection reason: it changes the row shape, so every fixture in `examples/` and every test
in `tests/test_scenario_input.py` needs updating, and a reader cannot see a day laid out at a
glance.

**2. Frictionless-style datapackage: CSV plus a JSON Table Schema sidecar.** Used by
oemof.tabular and OPSD, both alive. Cost: one new dependency (`frictionless` or `datapackage`,
licence and cadence unchecked, flagged for stage 3) plus a JSON schema to keep synced, a second
source of truth. Rejection reason: possibly more ceremony than a repo of this size needs.

**3. Wide-format CSV indexed by snapshot, one column per series (PyPSA/Calliope pattern).**
Closest to today's shape, so the smallest migration. It inherits the exact weakness that created
this bug class: no timestamp-typing convention and no explicit resolution field, so DST handling
is left to the reader to invent again.

### Set aside, not shortlisted

- **Sienna / PowerSystems.jl.** The most rigorous format found, and Julia. Adopting the layout
  without the Julia code means reimplementing the pointer and HDF5 reader.
- **Parquet, netCDF, xarray.** No surveyed tool uses them as the primary scenario input.
- **GridPath, Switch, TEMOA.** Real and alive, but timestamp typing is unsourced. Stage 2 pulls
  from source.

### What stage 2 must read directly

- `src/owr/etl/daily.py` and `src/owr/etl/rows_csv.py`, to decide how much of candidate 1 is
  "extend" against "invent".
- The OPSD `datapackage.json` itself, for the literal field list.
- PyPI listings for `frictionless` and `datapackage-py`: licence, release date, dependency count.
- `docs/DATA_SOURCES.md` and `docs/PLAN.md`, for whatever Phase 2 already committed to.

---

## Stage 2 — depth (researcher)

Date: 2026-08-02.

### 1. Recommendation

**Take candidate 1: one long-format CSV, one row per hour, with an offset-aware `ts`, an explicit
`interval_minutes`, and an explicit `local_date`.** Reject candidate 2. Reject candidate 3.

```
# scenario_profile = v1
# local_timezone = America/New_York
# load_source = gridstatus.isone.load
# wind_source = eia930.isne.wind
# retrieved_at = 2026-07-30T18:29:13.743802+00:00
# dataset_version = gridstatus==0.36.0
# source_query = gridstatus.ISONE().get_load(start=2025-01-01, end=2026-01-01) [zone=ISONE]
# demand_percentile_basis = pooled winter complete days, n=270
ts,local_date,interval_minutes,load_mw,wind_mw,demand_percentile,wind_forecast_frac
2026-01-06T00:00:00-05:00,2026-01-06,60,7500.0,2000.0,0.933,0.0
```

Required columns: `ts`, `local_date`, `interval_minutes`, `load_mw`. Optional: `wind_mw`,
`demand_percentile`, `wind_forecast_frac`.

One correction to the survey's framing. The recommended shape is long in time and wide in series.
Open Power System Data calls this layout "singleindex" and publishes it as the primary file.

### 2. Candidate 1 — long-format CSV with explicit timestamp and resolution

**Open Power System Data writes both a UTC column and a local column, and declares the primary
key.** Source: `https://data.open-power-system-data.org/time_series/latest/datapackage.json`,
retrieved 2026-08-01. Resource `opsd_time_series_60min`, first two schema fields and the footer:

```json
{
 "name": "utc_timestamp",
 "description": "Start of timeperiod in Coordinated Universal Time",
 "type": "datetime",
 "format": "fmt:%Y-%m-%dT%H%M%SZ"
},
{
 "name": "cet_cest_timestamp",
 "description": "Start of timeperiod in Central European (Summer-) Time",
 "type": "datetime",
 "format": "fmt:%Y-%m-%dT%H%M%S%z",
 "opsdContentfilter": true
}
```

```json
{
  "primaryKey": "utc_timestamp",
  "missingValues": ""
}
```

OPSD writes the local timestamp rather than derives it, and keys on the UTC column.

**GridPath carries the interval width as a required per-timepoint parameter, and permits a
fractional value.** Source:
`https://raw.githubusercontent.com/blue-marble/gridpath/main/gridpath/temporal/operations/timepoints.py`,
lines 115-125, retrieved 2026-08-02:

```
    | | :code:`hrs_in_tmp`                                                    |
    | | *Defined over*: :code:`TMPS`                                          |
    | | *Within*: :code:`NonNegativeReals`                                    |
    |                                                                         |
    | The number of hours in each timepoint (can be a fraction). For example, |
    | a 15-minute timepoint will have 0.25 hours per timepoint whereas a      |
    | 4-hour timepoint will have 4 hours per timepoint. This parameter is     |
    | used by other modules to track energy (e.g. storage state of charge)    |
    | and when evaluation ramp rates. Timepoints do not need to have the      |
    | same  :code:`hrs_in_tmp` value, i.e. one of them can represent a        |
    | 5-minute segment and another a 24-hour segment.                         |
```

**This repository already ships this shape in its real pull.** `data/load_2025.csv`, lines 1-8,
read 2026-08-01:

```
# dataset = load
# table = raw.system_load
# source = gridstatus.isone.load
# retrieved_at = 2026-07-30T18:29:13.743802+00:00
# dataset_version = gridstatus==0.36.0
# source_query = gridstatus.ISONE().get_load(start=2025-01-01, end=2026-01-01) [zone=ISONE]
ts,zone,load_mw,interval_minutes,source,retrieved_at,source_query,dataset_version
2025-01-01T00:00:00-05:00,ISONE,11520.806,5.0,gridstatus.isone.load,...
```

Candidate 1 is mostly "extend", not "invent". The row shape exists one layer up.

**What breaks.** The engine core does not change. Three things do: the byte-identical
regeneration check on `examples/synthetic_winter_stress.csv` recorded at `docs/HANDOFF.md:39`
needs re-baselining; 26 header literals in `tests/test_scenario_input.py` become wrong; and a
human can no longer read one day at a glance.
[Count corrected 26 from 27, 2026-08-02 after stage 3, finding C1.]

### 3. Candidate 2 — Frictionless datapackage with a JSON Table Schema sidecar

Table Schema describes columns. It does not describe an interval width, and it makes the timezone
part of a datetime **optional**. Source: `https://datapackage.org/standard/table-schema/`,
retrieved 2026-08-02, the `datetime` field type:

> The field contains a date with a time.
> Supported formats:
> default: The lexical representation MUST be in a form defined by XML Schema containing
> required date and time parts, followed by optional milliseconds and timezone parts, for
> example, 2024-01-26T15:00:00 or 2024-01-26T15:00:00.300-05:00.

A schema-valid `datetime` field can be naive. The sidecar does not give the offset guarantee the
ETL already enforces at `src/owr/etl/cli.py:188-191`:

```python
    if ts.tzinfo is None:
        raise ValueError(
            f"{origin}: naive timestamp {ts_str!r} (row 'ts' must carry a UTC offset)"
        )
```

The same page lists no `unit` and no `resolution` field property. Confidence note: the page
renders the type list inside a navigation block, so treat the type list as medium confidence and
the `datetime` quote as high confidence.

The strongest evidence is OPSD's own file, which invents three non-standard keys to say what the
specification cannot. Same source, third field of `opsd_time_series_60min`:

```json
{
  "name": "AT_load_actual_entsoe_transparency",
  "description": "Total load in Austria in MW as published on ENTSO-E Transparency Platform",
  "type": "number",
  "unit": "MW",
  "source": {
    "name": "own calculation based on ENTSO-E Transparency",
    "web": "https://transparency.entsoe.eu/load-domain/r2/totalLoadR2/show"
  },
  "opsdProperties": {
    "Region": "AT",
    "Variable": "load_actual_entsoe_transparency"
  }
}
```

`unit`, `source`, and `opsdProperties` are OPSD extensions. OPSD states the resolution in the
resource name and description, not in a schema field:

```json
{
 "profile": "tabular-data-resource",
 "name": "opsd_time_series_60min",
 "title": "Time series 60minutes singleindex",
 "description": "All data that is avaialable in 60minutes-resolution in singleindex format",
 "path": "time_series_60min_singleindex.csv",
```

A reader cannot compute energy from a human-readable string.

**What breaks.** The repository's zero-dependency core. `pyproject.toml`, lines 6-7, read
2026-08-02:

```toml
requires-python = ">=3.12"
dependencies = []
```

### 4. Candidate 3 — wide-format CSV indexed by snapshot

Switch treats the timestamp as a label with no type at all. Source:
`https://raw.githubusercontent.com/switch-model/switch/master/switch_model/timescales.py`,
lines 95-98, retrieved 2026-08-01:

```
    tp_timestamp[t]: The timestamp of the future time represented by
    this timepoint. This is only used as a label and can follow any
    format you wish. Although we highly advise populating this
    parameter, it is optional and will default to t.
```

Same file, line 266:

```python
    mod.tp_timestamp = Param(mod.TIMEPOINTS, default=lambda m, t: t, within=Any)
```

`within=Any` accepts any Python object. The interval width lives in a separate parameter,
`ts_duration_of_tp`, described at line 57: "ts_duration_of_tp[ts]: The duration in hours of each
timepoint".

GridPath does the same separation. Source: `timepoints.py`, lines 98-102 and 163-185, retrieved
2026-08-02:

```
    | | :code:`TMPS`                                                          |
    | | *Within*: :code:`PositiveIntegers`                                    |
    | The list of timepoints being modeled; timepoints are ordered and must   |
    | be non-negative integers.                                               |
```

```python
    m.TMPS = Set(within=PositiveIntegers, ordered=True)
    m.month = Param(
        m.TMPS, within=set(list(range(1, 12 + 1))) | {"undefined"}, default="undefined"
    )
    m.day_of_month = Param(m.TMPS, within=NonNegativeIntegers, default=0)
    m.hour_of_day = Param(m.TMPS, within=NonNegativeIntegers, default=0)
```

GridPath runs without knowing which month a timepoint sits in.

TEMOA has no timestamp concept. Its time index is integer years plus named seasons and times of
day. Source:
`https://raw.githubusercontent.com/TemoaProject/temoa/main/temoa/components/time.py`,
lines 36-50, retrieved 2026-08-02, `validate_time` checks integer status explicitly.

**What breaks.** The defect that caused this work survives. A wide CSV indexed by a naive
snapshot cannot record the interval width, the offset, or the fall-back hour. The repository's
own data proves the last point:

```
$ awk -F, 'NR>7 {print substr($1,20,6)}' data/load_2025.csv | sort | uniq -c
68532 -04:00
36588 -05:00
$ grep -c "2025-11-02T01" data/load_2025.csv
24
```

Run 2026-08-01. Candidate 3 also loses the wind join: load is 5-minute, wind is hourly, and a
single snapshot index forces one grain on both without recording which.

### 5. The DayProfile question — keep 24, guard explicitly

**Decision: keep the 24-hour-per-day assumption in the engine. Make the format carry enough to
detect a non-24-hour day, and reject that day at the reader with a message that names daylight
saving time.** Do not generalize `DayProfile` to variable-length days.

**The study window cannot contain a transition.** United States daylight saving time runs March to
November by statute. Source:
`https://www.govinfo.gov/content/pkg/USCODE-2023-title15/html/USCODE-2023-title15-chap6-subchapIX-sec260a.htm`,
retrieved 2026-08-02, section 260a(a):

> During the period commencing at 2 o'clock antemeridian on the second Sunday of March of each
> year and ending at 2 o'clock antemeridian on the first Sunday of November of each year, the
> standard time of each zone established by sections 261 to 264 of this title, as modified by
> section 265 of this title, shall be advanced one hour

Winter is December 1 to February 28 or 29 (`docs/HANDOFF.md:390-394`), so neither study season can
produce a 23-hour or 25-hour local day. The repository's own pull confirms it:

```
$ awk -F, 'NR>7 {d=substr($1,1,10); c[d]++} END {for (k in c) if (c[k]!=288) print k, c[k]}' data/load_2025.csv
2025-03-09 276
2025-11-02 300
$ awk -F, 'NR>7 {m=substr($1,6,2); off=substr($1,20,6); if (m=="12"||m=="01"||m=="02") c[m" "off]++} END {for (k in c) print k, c[k]}' data/load_2025.csv
01 -05:00 8928
12 -05:00 8928
02 -05:00 8064
```

Run 2026-08-01. 276 intervals equal 23 hours at 5-minute grain; 300 equal 25 hours.

**What generalization would cost.** The number 24 is structural in eight modules and in the public
wire contract: `models.py:15,76-79`, `dispatch.py:44-47`, `config.py:117-118`,
`initial_soc.py:27-28`, `simulator.py:68-76`, and `api/schemas.py:15,50`
(`hourly_load_mw: list[float] = Field(min_length=HOURS_PER_DAY, max_length=HOURS_PER_DAY)`, a
client-visible contract). The hardest case is `peak_window.py:42-47`, which does modular clock
arithmetic:

```python
    clock_hours = tuple((best_start + k) % HOURS_PER_DAY for k in range(window_hours))
    wrapped = best_start + window_hours > HOURS_PER_DAY
```

The wrap convention behind it is an open team question (`models.py:108-113`, `WrapConvention`).
Variable day length would force a re-decision of an already open question against a 23-hour clock.
`soc_engine.py`, `budget.py` and `metrics.py` carry no such assumption; they iterate whatever list
they receive.

**What the guard buys.** Today the reader already rejects a 25-hour day at
`scenario_input.py:204-212`, with a message that reads as a corrupt-file error. With `local_date`
and `interval_minutes` in the row, the reader can name the date, the local day length, and daylight
saving time as the cause.

**Why the decision stays reversible.** The general logic exists in `etl/daily.py:55-67`
(`local_day_hours`, returning 23.0/24.0/25.0) and stays there. A future variable-length engine
needs no format change, only the guard relaxed.

**Cost, stated plainly.** A March or April shoulder study cannot run through this reader, and a
full calendar year cannot run in one file. `docs/HANDOFF.md:392-394` already places March outside
every study window, so the loss is out of scope by a team decision.

### 6. Integration to the hourly grain

**Write average megawatts over the hour. Do not write megawatt hours.** The reason is one line in
the engine, `models.py:81-84`:

```python
    @property
    def load_mwh(self) -> float:
        """Total energy demanded across the day (MWh), i.e. sum of hourly MW."""
        return sum(self.hourly_load_mw)
```

That property equates a sum of megawatt values with megawatt hours, which holds only when every
hour is one hour long and the value is average power. Megawatt hours would break `dispatch.py`,
which compares the same series against a power cap in megawatts (`dispatch.py:44-51`).

The computation:

```
avg_mw(hour) = sum(load_mw * interval_hours) / sum(interval_hours)
```

The numerator is the integral `daily.py:104-107` already computes, under its rule 1: "Energy is an
integral, never a count: `load_mwh = Sum(load_mw * interval_hours)`. Nothing here assumes 288
intervals, 24 hours, or a fixed interval count." The denominator must equal 1.0 within tolerance;
if not, mark the hour incomplete and fail the export for that date.

**Add a sibling module, `src/owr/etl/hourly.py`. Do not change `daily.py`.** `daily.py`'s contract
is one `DailyLoad` per local calendar date, and its value is that it states one rule per line. Bind
the two with a test, not with shared code paths: for any date,
`sum(hourly avg_mw) == daily_loads_from_readings(...).load_mwh` within tolerance. That test is what
guarantees a single convention.

**The wind side, and a hazard.** EIA-930 is already hourly integrated. Source:
`https://www.eia.gov/survey/form/eia_930/instructions.pdf`, "GENERAL INSTRUCTIONS", retrieved
2026-08-02:

> Report all data as hourly integrated values in megawatts by hour ending time.
> Round all reported megawatt data to the nearest integer.
> Report hourly date-time stamps using the Coordinated Universal Time (UTC) that correlates with
> the respondent's local time. For example, the date-time stamp for March 1, 2017, hour ending
> 1:00 AM Eastern Standard Time (with UTC Offset = 5) should be reported as:
> 2017-03-01T06:00:00.000Z.

EIA labels an hour by its **end**. This repository labels an interval by its **start**
(`daily.py:22`). The provider library reconciles the two — `gridstatus` 0.36.0 `eia.py:806-808`:

```python
    df.insert(0, "Interval End", pd.to_datetime(df["period"], utc=True))
    df.insert(0, "Interval Start", df["Interval End"] - pd.Timedelta(frequency))
    df = df.drop("period", axis=1)
```

and `extract.py:253` reads the start key first (`_TS_KEYS = ("Interval Start", "Time", "ts")`). The
chain is correct by accident of two conventions lining up, and nothing asserts it.

**The named hazard.** `WindObservation` (`extract.py:83-90`) carries no interval width, so the ETL
cannot check hourly spacing the way it checks load spacing. Action: in `etl/hourly.py`, assert that
consecutive wind timestamps differ by exactly 3600 seconds before the join, and raise with the
offending timestamp if not.

### 7. demand_percentile

**The new format carries `demand_percentile` as a written column, produced by the ETL.**

The two current populations differ, and the mismatch is the real defect. The reader derives an
empirical rank within the supplied file (`scenario_input.py:225-241`); the ETL computes a pooled
p90 over complete season days (`transform.py:44-54`), measured at 385,832.584 MWh/day over 270
winter days (`docs/HANDOFF.md:636-637`). A six-day file gives its top day a derived rank of exactly
1.0. The same day scored against 270 pooled winter days sits lower.

[Corrected 2026-08-02 after stage 3, finding C2. The original text said the day "could sit at 0.62,
changing `priority()` by more than half". The 0.62 was an arbitrary illustration, not a computed
figure, and the consequence overstated the effect. The real bound, from `src/owr/budget.py:15-24`,
`priority = 0.7*demand_percentile + 0.3*wind_forecast_frac`: a fall from 1.0 to 0.62 moves priority
from 0.700 to 0.434 at zero wind, a 38 percent drop, and less when wind is above zero. The
population mismatch is real and Verified; only the size of its effect was wrong.]

**Add** `percentile_rank_within(daily, *, season)` in `etl/transform.py`, about 20 lines, over the
**same** population `compute_threshold` filters at lines 47-48. Then `demand_percentile >= 0.90`
and `load_mwh >= threshold_mwh` select the identical day set by construction.

**Keep the derived-rank fallback, demoted.** Three reasons: `examples/synthetic_winter_stress.csv`
has no pooled population and the demo depends on the derived rank landing on a tie
(`make_synthetic_winter_stress.py:41-43`, `COLD_DAY_TOTAL_MWH = 216000.0`); the reporting machinery
already exists (`DayProfileSet.demand_percentile_source`, printed by `cli.py:305-306`); and zero is
not a safe default, as `scenario_input.py:20-26` explains. Extend the warning at
`scenario_input.py:234-238` with one clause naming the population.

### 8. Does candidate 2 earn a dependency? No

**`frictionless`.** Source: `https://pypi.org/pypi/frictionless/json`, retrieved 2026-08-01.

```json
{
  "version": "5.19.0",
  "license": null,
  "license_expression": "MIT",
  "requires_python": ">=3.8"
}
```

```
frictionless-5.19.0-py3-none-any.whl upload: 2026-04-13T13:05:50.897731Z
```

`info.requires_dist` holds 69 entries, 49 marked `extra ==` and 20 unconditional: `attrs`,
`chardet` (two markers), `humanize`, `isodate`, `jinja2`, `jsonschema`, `marko`, `petl`,
`pydantic`, `python-dateutil`, `python-slugify`, `pyyaml`, `requests`, `rfc3986`, `simpleeval`,
`tabulate`, `typer`, `typing-extensions`, `validators`. That is 19 distinct mandatory runtime
packages.

**`datapackage`.** Source: `https://pypi.org/pypi/datapackage/json`, retrieved 2026-08-01.

```json
{
  "version": "1.15.4",
  "license": "MIT",
  "license_expression": null,
  "requires_python": ""
}
```

```
datapackage-1.15.4-py2.py3-none-any.whl upload: 2024-03-12T16:11:31.922039Z
```

Nine unconditional dependencies. The project's own PyPI description names its successor:

> **[Important Notice]** We have released [Frictionless Framework](https://github.com/frictionlessdata/framework). This framework provides improved `datapackage` functionality extended to be a complete data solution.

**Verdict: not earned.** The package has no runtime dependencies today (`pyproject.toml:7`), and
the ETL layer's stated rule is stdlib only (`daily.py:3`: "Pure; stdlib `zoneinfo` only, no new
dependency."). The sidecar does not deliver the offset guarantee or an interval-width concept. The
validation it would run is already written and tested across 26 test functions.
[Count corrected 26 from 27, 2026-08-02 after stage 3, finding C1.]

**What carries the schema instead:** the module docstring of `scenario_input.py:1-28` (per the
repo-map rule "Docstrings carry the spec and cite the doc they implement"), the column tuples at
`scenario_input.py:40-42`, and the `# scenario_profile = v1` banner line, which lets a future
reader branch on version without a sidecar.

### 9. Provenance — keep the banner, drop the per-row columns

Both readers already skip `#` lines (`scenario_input.py:95-99`, `rows_csv.py:62`), so the banner
costs nothing. The writer to copy is `rows_csv.py:34-46`; note its `redact_secrets` call at line
41, which the profile writer must also make.

Three reasons to drop the per-row columns. The four-column rule is stated for `raw.*` tables and
the profile is a derived artifact (`provenance.py:5-13`). The values are constant across the file,
so the columns repeat one record thousands of times (`provenance.py:12-13`). And the profile merges
two providers, `gridstatus.isone.load` and `eia930.isne.wind`, so a single `source` column would
name one and lie about the other. Two banner lines, `# load_source` and `# wind_source`, say the
truth. Add one line the raw files lack: `# derived_from = <input paths>`.

### 10. Purity — every place the constraint could break

Today the import arrow points one way. Command run 2026-08-02:

```
$ grep -rn "^from owr\|^import owr" --include="*.py" src/owr/etl | head -20
src/owr/etl/cli.py:25:from owr.config import DEFAULT_CONFIG
src/owr/etl/transform.py:23:from owr.etl.daily import DailyLoad
src/owr/etl/transform.py:25:from owr.models import StressWindow
src/owr/etl/transform.py:26:from owr.stress_finder import find_stress_windows_at_threshold, percentile_threshold
```

No module outside `src/owr/etl/` imports from `owr.etl`. Six places a naive implementation breaks
the rule:

1. **`scenario_input.py` importing `owr.etl.daily`** for `EASTERN` or `local_day_hours` reverses
   that arrow. The reader needs no timezone: the writer emits `local_date`, and the offset sits
   inside `ts`. The reader checks `datetime.fromisoformat(ts).date() == local_date`, stdlib only,
   exact because the writer emits `ts` after `astimezone(EASTERN)`.
2. **`zoneinfo.ZoneInfo` in the engine core.** It reads the system time zone database from the
   filesystem. `daily.py:35` accepts that inside the ETL layer. Do not move it down.
3. **The profile writer's location.** Put `write_profile_csv` in a new `src/owr/etl/profile_csv.py`,
   not in `hourly.py`, following `rows_csv.py:1-7`.
4. **`read_day_profiles` must keep taking a stream** (`scenario_input.py:83`); `cli.py:294-303`
   owns the `open` call.
5. **`etl/cli.py` must not import `owr.scenario_input`** to round-trip its own output. The
   round-trip test goes in `tests/`.
6. **No database driver on the profile path.** `etl/cli.py:35-40` keeps `psycopg` behind a lazy
   import; `--profile-out` must stay inside `cmd_transform`.

### 11. Integration cost, file by file

**New files**

| Path                            | What it does                                                                                                                                                                         | Size       |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| `src/owr/etl/hourly.py`         | `HourlyValue` and `hourly_from_readings()`. Integrates interval readings to one average-megawatt value per local hour. Mirrors `daily.py` rules 1-8. Asserts hourly spacing on wind. | ~110 lines |
| `src/owr/etl/profile_csv.py`    | `write_profile_csv()`. Banner, header, rows. Calls `redact_secrets`. Mirrors `rows_csv.write_rows_csv`.                                                                              | ~120 lines |
| `tests/test_etl_hourly.py`      | Integration correctness, daily-equals-sum-of-hourly invariant, wind spacing rejection, naive timestamp rejection.                                                                    | ~190 lines |
| `tests/test_etl_profile_csv.py` | Banner content, column order, key redaction, round trip through `read_day_profiles`.                                                                                                 | ~150 lines |

**Changed files**

| Path                                       | Change                                                                                                                                                                                                                                                                                                                                                                                                                     | Size       |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| `src/owr/scenario_input.py`                | Docstring `:1-28` rewritten. `REQUIRED_COLUMNS` `:40` becomes `("ts","local_date","interval_minutes","load_mw")`. Hour parse `:142-150` becomes an ISO 8601 parse plus naive rejection copied from `etl/cli.py:188-191`. Duplicate check `:171-172` keys on the absolute instant. 24-row guard `:204-212` gains the daylight-saving message. Derived-rank block `:225-241` keeps its arithmetic, gains one warning clause. | 279 → ~340 |
| `tests/test_scenario_input.py`             | `_rows()` `:15-25` and `_csv()` `:31-35` rewritten. 26 header literals updated. Six new tests.                                                                                                                                                                                                                                                                                                                             | 330 → ~430 |
| `src/owr/etl/transform.py`                 | Add `percentile_rank_within()` over the same season population as `compute_threshold` `:47-49`.                                                                                                                                                                                                                                                                                                                            | 85 → ~110  |
| `src/owr/etl/cli.py`                       | `_run_transform` `:144-182` gains a `--profile-out` branch. New `--wind-input`. `_reading_from_row` `:185-196` gains a wind sibling. Parser additions `:338-386`.                                                                                                                                                                                                                                                          | +~90       |
| `tests/test_etl_cli_transform.py`          | About eight tests for `--profile-out` and `--wind-input`.                                                                                                                                                                                                                                                                                                                                                                  | 425 → ~575 |
| `examples/make_synthetic_winter_stress.py` | `BANNER_LINES` `:46-49` and `render_csv()` `:137-145` rewritten. Invariants `:96-134` unchanged.                                                                                                                                                                                                                                                                                                                           | +~25       |
| `examples/synthetic_winter_stress.csv`     | Regenerated.                                                                                                                                                                                                                                                                                                                                                                                                               | 147 → ~152 |
| `tests/test_cli.py`                        | `:511` writes `"date,hour,load_mw\nnot-a-date,0,100\n"` inline. Update.                                                                                                                                                                                                                                                                                                                                                    | ~5         |
| `tests/test_peak_window.py`                | `EXAMPLE` at `:18` reads the same fixture. Expect no change; confirm by running.                                                                                                                                                                                                                                                                                                                                           | 0-5        |
| `src/owr/cli.py`                           | `--input` help text `:138`. The `input` block in `_render_list_windows` `:592-597`.                                                                                                                                                                                                                                                                                                                                        | ~10        |
| the repo map                                | One changed row, two new rows.                                                                                                                                                                                                                                                                                                                                                                                             | 3 rows     |
| `docs/HANDOFF.md`                          | Re-baseline the byte-identical fixture check at `:39`.                                                                                                                                                                                                                                                                                                                                                                     | 1 row      |
| `docs/DATA_SOURCES.md`                     | Record the profile format and its two upstream sources.                                                                                                                                                                                                                                                                                                                                                                    | ~10        |

**Unchanged, and this is the point:** `models.py`, `dispatch.py`, `soc_engine.py`, `budget.py`,
`metrics.py`, `simulator.py`, `peak_window.py`, `initial_soc.py`, `stress_finder.py`, `config.py`,
`api/schemas.py`, `api/app.py`, `db/migrations/`.

**Total: about 700 new or changed lines. One to two working days including tests.**

### 12. Source gaps from stage 1, now closed

**GridPath, Switch, TEMOA timestamp typing** (quotes in section 4):

| Tool     | Timestamp typing                                                                                              | Interval width                                            |
| -------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------- |
| Switch   | `Param(..., within=Any)`, label only, optional, defaults to the timepoint id                                  | Separate `ts_duration_of_tp`, in hours                    |
| GridPath | `Set(within=PositiveIntegers)`. `month`, `day_of_month`, `hour_of_day` optional, default `"undefined"` or `0` | Required `hrs_in_tmp`, fractional, may vary per timepoint |
| TEMOA    | No timestamp. Integer years plus named `time_season` and `time_of_day`                                        | Derived `segment_fraction`                                |

None of the three types the timestamp. All three carry the interval width as first-class data.
`interval_minutes` copies that.

**The literal OPSD field list.** Same descriptor, retrieved 2026-08-01, declares four resources:

```
RESOURCE time_series time_series.xlsx fields: 0
RESOURCE opsd_time_series_15min time_series_15min_singleindex.csv fields: 61
RESOURCE opsd_time_series_30min time_series_30min_singleindex.csv fields: 41
RESOURCE opsd_time_series_60min time_series_60min_singleindex.csv fields: 300
```

Top-level keys: `profile, name, id, title, description, longDescription, homepage, documentation,
version, created, lastChanges, keywords, geographicalScope, temporal, contributors, sources,
resources`, with `"name": "opsd_time_series"` and `"version": "2020-10-06"`. The package is roughly
six years stale, and the 60-minute resource carries 300 fields, the wide-in-series layout
recommended here at a much smaller width.

**ISO-NE published CSV against what `gridstatus` returns. They do not match.** `gridstatus` reads
the published CSV, discards five lines, keeps two columns, and renames both. Source:
`.venv/.../gridstatus/isone.py`, lines 161-187, read 2026-08-02:

```python
        url = f"https://www.iso-ne.com/transform/csv/fiveminutesystemload?start={date_str}&end={date_str}"
        data = _make_request(url, skiprows=[0, 1, 2, 3, 5], verbose=verbose)
        data["Date/Time"] = pd.to_datetime(data["Date/Time"]).dt.tz_localize(
            self.default_timezone,
            ambiguous="infer",
        )
        df = data[["Date/Time", "Native Load"]].rename(
            columns={"Date/Time": "Time", "Native Load": "Load"},
        )
```

and lines 1000-1005, `pd.read_csv(..., skiprows=skiprows, skipfooter=1, engine="python")`.

What this proves about the published layout: rows 0-3 and 5 are preamble, so the header sits on row
4; the last row is a footer; the published columns include `Date/Time`, `Native Load` and
`Asset Related Load`; and the published timestamps are naive local, with the zone attached
afterwards by `tz_localize("US/Eastern", ambiguous="infer")`.

**Limit of this evidence.** The CSV itself could not be fetched. ISO-NE returned HTTP 403 for
`https://www.iso-ne.com/transform/csv/fiveminutesystemload?start=20250115&end=20250115` on
2026-08-02, with and without a browser user agent, and HTTP 500 for the report tree page. The
layout facts are inferred from the client, not read off the file. A human with a browser settles it
in one minute.

**One consequence for the fall-back hour.** The offsets in `data/load_2025.csv` were produced by
pandas inference (`ambiguous="infer"`), not by the provider. The inference is correct for this data
and the winter window never touches it, but it is the reason `local_date` belongs in the profile as
a written column rather than a re-derived value.

**An extra discrepancy, not asked for.** `docs/DATA_SOURCES.md:21` names the canonical load series
as the ISO-NE hourly wholesale load cost report at `locationId=4000`. The real pull did not use it:
the banner in `data/load_2025.csv` records `gridstatus.ISONE().get_load(...)`, which hits
`transform/csv/fiveminutesystemload` (`extract.py:420-424`). The p90 of 385,832.584 MWh rests on
the five-minute Native Load feed, not on the report `DATA_SOURCES.md` calls canonical. A
documentation gap, not a code defect. Out of scope here; raise it separately.

### 13. Confidence, and what would change the recommendation

**High confidence, read in source:** every repository claim, the `gridstatus` load and EIA client
behavior, the Switch/GridPath/TEMOA time typing, the OPSD field list, the two PyPI listings, the
daylight saving time statute, and the interval counts in `data/load_2025.csv`.

**Medium confidence, read in rendered documentation:** the completeness of the Data Package v2
Table Schema field-type list. The `datetime` description quote is high confidence.

**Low confidence, could not check:** the ISO-NE published CSV layout. See section 12.

**What would change the recommendation.**

1. A study window that crosses March or November. The guard becomes a blocker, `DayProfile` must
   generalize, and the eight-module cost becomes real.
2. A second consumer of the profile file outside this repository. A sidecar earns its keep when a
   tool you do not control must read the file. Today there is none.
3. A load feed at a third grain. A 15-minute feed needs one added rule, not a new format.
4. Evidence that `DayProfile.load_mwh` is meant to be an energy sum of MWh values. The unit
   decision rests on reading `models.py:82-84` as average power.

---

## Stage 2R — bounded revision (researcher)

Date: 2026-08-02. Return 1 of 2 allowed.

**Why the return happened.** Two sources arrived after stage 3: the team's own architecture
specification, now at `docs/source/2026-07-30_Software_Architecture_Documentation.md`, and a
teammate's event list, now at `data/daily_stress_events_team.csv`. The architecture document
carries a Data Contract for Component 2 that **is** the format under design. Stages 1 to 3 never
opened it. Three questions were re-asked. Everything else in stage 2 stands.

### R1. Which shape wins — the contract binds on columns, not on time

**The team contract binds on the column set. It does not bind on the timestamp, because it
explicitly defers that decision. Add `ts` and `interval_minutes` to the team's shape. Do not
replace `date` and `hour`.**

Source: `docs/source/2026-07-30_Software_Architecture_Documentation.md`, lines 5-11, read
2026-08-02:

```
The following engineering decisions require explicit values before implementation. No implicit assumptions shall be made.

System Assumptions

* Simulation time step \= @
* Timestamp format \= @
* Time zone \= @
```

Three placeholders. `interval_minutes` fills "Simulation time step". An offset-aware ISO 8601 `ts`
fills "Timestamp format" and "Time zone" together. The rule above the list forbids an implicit
assumption, and `date` plus `hour` alone forces one: a reader must assume the hour is 60 minutes
long and must assume which zone the date belongs to. Adding the two columns satisfies the rule
rather than breaks the contract.

The contract's Data Contract, same document, lines 234-241:

```
| date | Y | YYYY-MM-DD | date | Calendar date |
| hour | Y | int | hour | Hours in a day |
| load\_mw | Y | float | MW | Hourly system load |
| wind\_mwh | N | float | MWh | Hourly wind generation |
| oil\_mwh | N | float | MWh | Hourly oil generation |
| gas\_mwh | N | float | MWh | Hourly liquid natural gas generation |
| demand\_percentile | N | float, constant per date | % | Daily? historical percentile of demand load |
| wind\_forecast\_frac | N | float, constant per date | ratio | Daily? wind generation fraction of total 7-day wind generation |
```

Stage 2 proposed `local_date`. That is the contract's `date`. **Take the contract's name.** Keep
`hour` as well: it is derivable from `ts`, the contract requires it, and it restores the
readability stage 2 listed as a loss. Redundancy with an exact check is safe; redundancy without a
check is the defect. The reader checks `hour == ts.hour` after the stored offset applies, using
`datetime.fromisoformat` only, with no time zone database access, so the purity argument in
stage 2 §10 is unchanged.

**The unit suffix: choose MW, because the document chooses MW.** Component 2 types wind, oil and
gas as MWh. Component 6 types the same three series as MW, same document, lines 470-472:

```
| oil\_generation\_actual | @ | float | MW | @ |
| gas\_generation\_actual | @ | float | MW | @ |
| wind\_generation\_actual | @ | float | MW | @ |
```

`docs/ARCHITECTURE_REVIEW_2026-07-31.md` already logs the unit mixing as D5. The new fact is that
the document answers itself. MW satisfies Component 6 exactly and Component 2 numerically at
hourly grain, and keeps the single convention stage 2 §6.1 established.

Handle the contract's spelling as an **accepted alias, not a second convention.** When a file
carries `wind_mwh`, `oil_mwh` or `gas_mwh` **and** `interval_minutes` equals 60, the reader
accepts it, treats the value as average megawatts, and warns through the existing
`DayProfileSet.warnings` channel (`scenario_input.py:55`). At any other interval width the reader
raises, because the identity no longer holds. The conversion is the identity, so it adds no
arithmetic.

**Final column list**

| Column               | Required | Type                       | Unit                     | Comes from                                         |
| -------------------- | -------- | -------------------------- | ------------------------ | -------------------------------------------------- |
| `date`               | Y        | `YYYY-MM-DD`               | local calendar date      | Team contract                                      |
| `hour`               | Y        | `int` 0 to 23              | hour index               | Team contract                                      |
| `ts`                 | Y        | ISO 8601 with UTC offset   | instant, interval start  | Analysis; fills "Timestamp format" and "Time zone" |
| `interval_minutes`   | Y        | `float`                    | minutes                  | Analysis; fills "Simulation time step"             |
| `load_mw`            | Y        | `float`                    | average MW over the hour | Both                                               |
| `wind_mw`            | N        | `float`                    | average MW over the hour | Both; contract names it `wind_mwh`                 |
| `oil_mw`             | N        | `float`                    | average MW over the hour | Both; contract names it `oil_mwh`, see R3          |
| `gas_mw`             | N        | `float`                    | average MW over the hour | Both; contract names it `gas_mwh`, see R3          |
| `demand_percentile`  | N        | `float`, constant per date | fraction 0 to 1          | Both; definition from analysis, see R2             |
| `wind_forecast_frac` | N        | `float`, constant per date | fraction 0 to 1          | Both                                               |

Required: `date`, `hour`, `ts`, `interval_minutes`, `load_mw`.
Optional: `wind_mw`, `oil_mw`, `gas_mw`, `demand_percentile`, `wind_forecast_frac`.

**Banner lines the contract requires.** Same document, lines 104-113: "Schema Versioning / Every
exchanged object shall include:" followed by a table of **five** fields, `schema_version`,
`software_version`, `simulation_version`, `calculation_version`, `configuration_version`, each with
an unfilled `@` description.

[Corrected 2026-08-02 after stage 3 re-entry, finding RC2. The revision quoted two of the five and
elided three without an ellipsis.] Two are writable today: `# schema_version = 1` and
`# software_version = <git sha>`, the sha already at `src/owr/version.py`. The other three are not.
`simulation_version` and `calculation_version` describe a simulation run, and the profile file is
an input to a run rather than a product of one. `configuration_version` has no configuration object
to version yet. **Open item for the plan: decide whether the profile writer emits the three as
empty banner keys, or whether the contract's "every exchanged object" is read as applying to
simulation outputs only.** Do not silently drop them.

**Cost change against stage 2 §11.** The revision **reduces** churn. `scenario_input.py:134-150`
parses `date` and `hour` today and both survive, so the change becomes additive: two new required
columns, two new checks, the alias rule. In `tests/test_scenario_input.py` the `_rows()` helper at
lines 15-25 keeps `date_str` and `h` and appends two cells, so the 26 header literals gain two
names rather than change shape. Revise those two files from about 110 new or changed lines down to
about 70.

### R2. `demand_percentile` — one definition, empirical rank in the pooled season population

**Recommend the pooled-population empirical rank, the population `etl/transform.py` already
filters for. The ETL writes it. The other two definitions become a later derived output and a
documented fallback.**

**The architecture formula is not a percentile, its constants are forbidden, and it is archived.**
Same document, line 720:

```
DemandPercentile(d) \= Demand(d)/(561,878MWh for summer or 434,214MWh for winter)
```

A ratio to a fixed denominator. `docs/FACT_CHECK_REPORT.md:24` records that no published source
states those numbers and directs deriving them during ETL rather than hard-coding.
`docs/HANDOFF.md:444-446` repeats the prohibition: "Do not hard-code; derive during ETL and store
in `features.constants` with the query." A ratio to a peak day is a normalized load, not a
percentile.

[Corrected 2026-08-02 after stage 3 re-entry, finding RC1. The revision cited this formula as a
live competing definition. **It is not live.** Line 720 sits inside the section headed `# Archived`
at line 569, titled "V1.0 MVP Architecture". The tokens `DemandPercentile` and `Priority(d)` occur
only at lines 720 and 724, both archived. This strengthens the recommendation rather than weakens
it: the ratio is a superseded reading, so the conflict is between one live definition and one
archived one, not between two live ones.]

**The live definition is the empirical one, and it drives detection.** Same document, lines
265-275, under the live heading `# 3-Stress Event Detection`:

```
Calculate:
historical\_daily\_load

Determine:
90th historical daily load percentile

A stress event begins when:
daily\_load ≥ 90th percentile
for
minimum\_window
consecutive days.
```

The live Component 3 and the archived formula use one word for two quantities, and only the
empirical one drives stress detection. The Component 2 contract column at line 240 reads
"historical percentile of demand load", which agrees with Component 3.
`ARCHITECTURE_REVIEW_2026-07-31.md:139` already logs B6, that the population is unspecified. The
narrower new point: choosing the empirical definition makes Component 3, the Component 2 column
description, and `Priority(d)` agree by construction.

**The recommendation.** `demand_percentile(d)` is the empirical cumulative distribution of that
day's `load_mwh` within the pooled complete days of the same season, using the same population
`compute_threshold` filters at `etl/transform.py:47-49`. Then `demand_percentile >= 0.90` and
`load_mwh >= threshold_mwh` select the identical day set.

**What the other two become.** The architecture ratio becomes a **migration, not a rejection**:
once the ETL holds the pooled population, the seasonal peak-day total falls out of it as the
maximum `load_mwh` over the season, which is exactly the derivation `HANDOFF.md:445` asks for. It
arrives later as a separately named column, `demand_peak_frac`, and the derived totals become the
check against 561,878 and 434,214. **Two names, two quantities.** The file-local rank stays as a
documented fallback, because `examples/synthetic_winter_stress.csv` has no pooled population.

**What the ETL writes.** One value per date, repeated on every hour row, which the constant-per-date
rule at `scenario_input.py:191-198` already enforces. The banner carries the population:
`# demand_percentile_basis = pooled winter complete days, n=270, threshold_mwh=385832.584`.

**What the reader does when the column is absent.** Unchanged, plus two additions. Derive the
file-local rank, set `demand_percentile_source = "derived-rank"`, and extend the warning at
`scenario_input.py:234-238` with one clause naming the population. **New rule:** if the banner
carries `demand_percentile_basis` and the column is absent, raise. That combination means a
truncated write, not a hand-made file.

### R3. `oil_mw` and `gas_mw` — EIA-930 hourly fuel-type data, with a free key

**Source: the EIA-930 hourly fuel-type route the wind extractor already uses, with `fueltype=OIL`
and `fueltype=NG`. Endpoint `electricity/rto/fuel-type-data`, respondent `ISNE`, hourly grain,
free registered API key required.**

EIA-930 resolves them as separate codes. Source:
`https://www.eia.gov/survey/form/eia_930/instructions.pdf`, energy source code list, retrieved
2026-08-02:

```
For Data Type "NG" - Use "SYS" when reporting total net generation. Use "ZZ[Z]" codes below when reporting net generation
by energy source:

     COL - coal
     NG - natural gas
     NUC - nuclear
     OIL - all petroleum products
     WAT - hydro (excluding pumped storage*)
```

The same form fixes the grain and unit: "Report all data as hourly integrated values in megawatts
by hour ending time."

The API route exposes the fuel type as a facet (`gridstatus/eia.py:1032-1035`), and the repository
already passes it (`extract.py:504-511`, `facets={"respondent": ..., "fueltype": ...}`).

**One integration detail that will bite: the pivoted column for oil is "Petroleum".** Source:
`.venv/.../gridstatus/eia_constants.py`, lines 3-19, read 2026-08-02, `EIA_FUEL_TYPES` lists
`"Natural Gas"` and `"Petroleum"`, not "Oil". `extract.py:258` reads
`_WIND_KEYS = ("Wind", "gen_mw", "MW", "wind_mw")`, which works because the pivot column is
`Wind`. The oil key must be `Petroleum` and the gas key `Natural Gas`.

**The credential.** `curl https://api.eia.gov/v2/electricity/rto/fuel-type-data` returned on
2026-08-02:

```json
{
  "error": {
    "code": "API_KEY_MISSING",
    "message": "No api_key was supplied.  Please register for one at https://www.eia.gov/opendata/register.php"
  }
}
```

`src/owr/etl/credentials.py` already handles that key, so no new secret-handling work appears.

**The two ISO-NE alternatives, and why neither wins.** ISO-NE Daily Generation by Fuel Type is
daily (`DATA_SOURCES.md:23`), and Component 7's metrics sum over simulation hours. ISO-NE
`genfuelmix` is credential-free and instantaneous; `gridstatus/isone.py:147-148` carries the
comment "# assume instant in time, unclear if this is correct". An instantaneous megawatt snapshot
carries no interval width, so integrating it would be exactly the multiplicative error
`extract.py:57-61` forbids. Keep `genfuelmix` as a credential-free cross-check. Neither ISO-NE
endpoint could be fetched, for the reason recorded in stage 2 §12.3.

**Reserve now, populate later.** Four reasons. The reader already has an optional-column mechanism
(`scenario_input.py:41`), so reserving costs two names and no logic. The extractor is already
parameterized on fuel type (`extract.py:491-497`), so oil and gas are two more source instances,
not a new adapter. **The database is not ready, and that is the real cost:**
`db/migrations/001_init.sql:36-46` defines `raw.hourly_wind` with
`PRIMARY KEY (source, ts, horizon_days)` and no fuel column, so oil and gas rows would collide on
that key; that needs migration 004. (Precision note from stage 3: the collision follows because
`EIAWindSource.source` is the fixed class attribute `"eia930.isne.wind"` at `extract.py:487`. A
fuel instance that also forked the source string would not collide, but the table would then
mislabel oil as wind.) The CSV path needs no migration, so the profile format can carry oil and gas
before Postgres does. And **two** of the three metrics that consume them are logged as broken at
`ARCHITECTURE_REVIEW_2026-07-31.md:190-191`, Stress Window Effectiveness and Fuel-Fired Generation
Offset, so populating now would feed metrics that need redefinition first. [Corrected 2026-08-02
after stage 3 re-entry, finding RC3: the revision said three. The third consumer, Fuel Offset
Percentage, has no row of its own and appears only in the Robustness note at line 194.] **Reserve
the shape. Do not compute the number.**

### R4. Does the team event list change the format decision?

**No. It adds one supporting argument and one confirmation.**

Supporting argument. `data/daily_stress_events_team.csv`, line 30, read 2026-08-02 [line corrected
from 29 after stage 3 re-entry, finding RC4; line 29 holds W17]:

```
W18,Winter,2026-03-03,2026-03-03,1,75472.0,75472.0,75472.0,15755.0,134.5,134.5
```

A row labelled Winter carries a March date, which `HANDOFF.md:392-394` excludes from winter. The
season is a derived property of the local calendar date, so the format carries the date and the
ETL owns the season tag, which `src/owr/etl/seasons.py` already does. **The format carries no
season column.** That confirms the R1 column list.

Confirmation. The file carries `total_wind`, `avg_cost` and `max_cost` per event, so a teammate
already joins a wind series and a price series to load. That supports keeping `wind_mw` optional
and suggests a price column later. It carries no oil or gas column, confirming the R3 finding that
nobody holds that data yet.

Not bearing. The event-count disagreement (6 multi-day winter events against 4, an 18-day window
against 11) and the daily loads against the p90 of 385,833 MWh point at a different `locationId`.
That is the discrepancy already logged in stage 2 §12.4. [Range corrected 2026-08-02 after stage 3
re-entry, finding RC5. The revision said "75,000 to 92,000 MWh". The file's `avg_daily_load` runs
**75,472 to 103,484** across all events, and **75,472 to 81,447** for winter, with a winter peak
day of 86,519. Every row still sits far below 385,833, so the contrast holds.] None of it changes
which columns the file carries.

---

## Stage 3 — fact-check (verifier)

Date: 2026-08-02. Fable, high effort.

Scope: every cited repository line, all four data commands, twelve external sources, four
arithmetic items. **Counts: 74 Verified, 4 Contradicted, 5 Unverifiable.**

### Contradicted — all four corrected in place above

| #   | Claim                                                                                                              | What the source says                                                                                                                                                                                                 | Impact                                                                                         |
| --- | ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| C1  | Stage 2 §2, §8, §11: "27 header literals" and "27 test functions" in `tests/test_scenario_input.py`                | Both counts are **26**. `grep -c "def test_" tests/test_scenario_input.py` returns 26. A grep for `date.*hour.*load_mw` returns 26 literals, lines 45 to 328.                                                        | Low. Cost table only.                                                                          |
| C2  | Stage 2 §7: a percentile drop from 1.0 to 0.62 "chang[es] `priority()` by more than half"                          | `src/owr/budget.py:15-24`: `priority = 0.7*demand_percentile + 0.3*wind_forecast_frac`. At zero wind, 0.700 drops to 0.434, a 38 percent drop. With wind above zero the drop is smaller. It is never more than half. | Low. The population mismatch is real and Verified. The consequence clause overstated it.       |
| C3  | Stage 1: "NREL OEDI states all published time-series data is UTC", cited to `registry.opendata.aws/oedi-data-lake` | The page resolves and contains no statement about UTC or daylight saving time. The statement may exist on a specific dataset page, not at the cited URL.                                                             | Low. OEDI was set aside, not shortlisted.                                                      |
| C4  | Stage 1: the `scenario_input.py` docstring "says 'nothing produces this file'"                                     | The phrase is not in the docstring. `scenario_input.py:3-10` says no migration carries these columns and PLAN.md Phase 2 defines no CSV export. Substance supported, quotation fabricated.                           | Low. Wording only. The "provisional... not a stable interface" quote is verbatim and Verified. |

**Disposition, 2026-08-02.** All four were corrected directly in the text above, each marked with
its finding number. None required new research: C1 and C2 were replaced with the verifier's own
measured values, C3 was withdrawn, C4 was restated as paraphrase. **No Contradicted finding touches
the load-bearing chain of the recommendation.** The pipeline was not returned to stage 1 or stage 2.

### Unverifiable

| #   | Claim                                                                                              | Evidence                                                                                                                                                                                                                        |
| --- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| U1  | Stage 1: Sienna/PowerSystems.jl HDF5 store plus pointer file with an explicit uniform `resolution` | The cited URL returns HTTP 404, as do two alternate paths. The verifier believes the claim is true and marks it Unverifiable anyway.                                                                                            |
| U2  | Stage 1: EIA API v2 offers `hourly` (UTC) or `local-hourly` (offset suffix)                        | Sole source is a third-party vignette, not an approved source. The official documentation page does not carry it. Likely true, not verifiable under the project's source rule.                                                  |
| U3  | Stage 1: GridPath "separate timepoints CSV joined by row/id"                                       | The cited docs page does not carry the claim. **Superseded** by stage 2's source-code quotes, which are Verified. Stage 1 citation only.                                                                                        |
| U4  | Stage 1: OPSD dual-column and resolution claims, cited to the GitHub README                        | The README is a 496-byte stub. The claims themselves are Verified against `datapackage.json`, stage 2's source. Stage 1 citation only.                                                                                          |
| U5  | ENTSO-E resolution values `PT30M` and `P1D`                                                        | The cited PDF defines `resolution :Duration` per `Series_Period` and names `PT15M`, `PT60M`, `PT1H`. `PT30M` and `P1D` do not appear in the pages read. The core claim, an explicit per-series resolution element, is Verified. |

The ISO-NE CSV layout is the report's own stated low-confidence gap, flagged in §12 and §13. The
verifier reproduced the HTTP 403 independently and confirms the limitation is stated honestly. Not
counted as a finding.

### Verified — 74 claims

- **Repository, 42 claims.** Every checked line matches: `models.py:15,76-79,81-84,108-113`,
  `dispatch.py:44-51`, `peak_window.py:42-47`, `api/schemas.py:15,50`, `config.py:117-118`,
  `initial_soc.py:27-28`, `simulator.py:68-76`, all seven `scenario_input.py` ranges, all six
  `daily.py` ranges, `etl/cli.py:188-191` verbatim, `rows_csv.py` with `redact_secrets` at 41,
  `transform.py:44-54`, `provenance.py:5-13`, all five `extract.py` ranges, `cli.py:294-303`,
  `pyproject.toml:6-7`, `HANDOFF.md:39,390-394,636-637`, `DATA_SOURCES.md:21`,
  `tests/test_cli.py:511`, `tests/test_peak_window.py:18`. `soc_engine.py`, `budget.py` and
  `metrics.py` carry no `HOURS_PER_DAY` and no literal 24. No module outside `src/owr/etl/`
  imports `owr.etl`; the only hits are docstring mentions. **The §12 canonical-source discrepancy
  is real:** the data banner records `get_load`, not the `locationId=4000` report.
- **Vendored gridstatus, 4 claims.** `isone.py:161-187`, `isone.py:1000-1005`, `eia.py:806-808`,
  all verbatim, version 0.36.0. The `python3.13` path is the real one; `requires-python = ">=3.12"`
  permits it. No discrepancy.
- **Data, 4 claims.** All four commands reproduce exactly: 68532/36588, 24 rows for
  `2025-11-02T01`, 276/300, and 8928/8928/8064.
- **External, 20 claims.** Statute 260a(a) verbatim. EIA-930 GENERAL INSTRUCTIONS verbatim, PDF
  page 3. All six OPSD descriptor claims verbatim, including the "avaialable" typo, the resource
  field counts 0/61/41/300, and version 2020-10-06. The Table Schema `datetime` optional-timezone
  quote, and the absence of `unit` and `resolution` field properties. Switch lines 95-98, 266, 57
  verbatim at the exact lines. GridPath lines 98-102, 115-125, 163-185 verbatim. TEMOA 36-50. Both
  PyPI listings exact to the microsecond, including 69/49/20 and 19 distinct packages, and the
  successor notice verbatim. The PyPSA, Calliope, pandapower and oemof.tabular table rows are
  supported by the cited docs.
- **Arithmetic, 4 claims.** 276 × 5 min = 23 h, 300 × 5 min = 25 h. Neither Dec 1 – Feb 28/29 nor
  Jun 1 – Sep 30 can contain a transition, which fall on the second Sunday of March and the first
  Sunday of November. The §6 unit argument holds: `sum(hourly avg MW) = daily MWh` exactly, and
  only when every hour is one hour of average power. The "no surveyed tool does strictly more"
  claim is an evaluative judgment consistent with all verified evidence, with U1 its only open
  corner.

### Re-entry pass over Stage 2R — 2026-08-02, return 1 of 2

Scope: changed claims only. **Counts: 34 Verified, 5 Contradicted, 1 Unverifiable.**

| #   | Revision claimed                                                       | Source says                                                                                                                                                                           | Impact                                                                                              |
| --- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| RC1 | The fixed-denominator ratio at line 720 is a live competing definition | Line 720 sits inside `# Archived` (line 569), "V1.0 MVP Architecture". `DemandPercentile` and `Priority(d)` occur only at 720 and 724, both archived.                                 | Medium for framing, zero for the decision. The archived status makes the empirical choice stronger. |
| RC2 | Schema Versioning requires two banner fields                           | The table at 107-113 requires **five**: `schema_version`, `software_version`, `simulation_version`, `calculation_version`, `configuration_version`. Three elided without an ellipsis. | Low. Now named, with an open item for the plan.                                                     |
| RC3 | Three metrics logged broken at review 190-191                          | **Two**: Stress Window Effectiveness and Fuel-Fired Generation Offset. Fuel Offset Percentage appears only in the Robustness note at 194.                                             | Low. Two broken consumers still justify "reserve, do not populate".                                 |
| RC4 | The W18 row is at team CSV line 29                                     | Line 29 holds W17. The quoted W18 row is verbatim correct at **line 30**.                                                                                                             | Low. Off by one.                                                                                    |
| RC5 | Daily totals run 75,000 to 92,000 MWh                                  | `avg_daily_load` runs 75,472 to 103,484 across all events, 75,472 to 81,447 for winter, winter peak day 86,519.                                                                       | Low. The contrast against 385,833 holds.                                                            |

**All five corrected in place above, each marked with its finding number. The pipeline was not
returned to the researcher.** These are citation and count precision, resolvable from the
verifier's own measured values. Return budget preserved: 1 of 2 used.

**RU1, Unverifiable.** Whether `frequency=hourly` on `electricity/rto/fuel-type-data` resolves OIL
and NG separately for respondent ISNE. Requires a key; `$EIA_API_KEY` is not set. The supporting
facts are Verified: the route exposes a `fueltype` facet (`eia.py:1032-1035`) and EIA-930 defines
OIL and NG as separate codes. **Only the live API behavior is unchecked.**

**Verified in this pass, 34 claims.** Seven architecture-document quotes, verbatim including the
markdown escapes, with component attribution confirmed by heading position: the MWh table sits
under `# 2-Data Pipeline` (line 188), the MW rows under `# 6-Grid Simulation Engine` (line 436).
**The unit conflict is confirmed.** Twenty-two repository claims, including `version.py` returning
the short git sha, `seasons.py` owning the season tag and excluding March, all five
`scenario_input.py` cites, the `_rows()` helper structure at `tests/test_scenario_input.py:15-25`,
all four `extract.py` cites with the `facets=` quote verbatim at line 510, and
`001_init.sql:36-46` verbatim with no fuel column. Three vendored-library claims, including
`EIA_FUEL_TYPES` carrying "Natural Gas" and "Petroleum" and no "Oil". Two external claims, with the
`API_KEY_MISSING` body reproducing byte for byte including its double space.

### Two reasoning verdicts, and one design hole the plan must close

**E1, does adding columns satisfy the contract?** **The researcher's interpretation, not the
document's own statement.** The document demands explicit values for the three placeholders (line
5, placeholders 9-11) and never says the Data Contract column list may grow. Two things make the
reading defensible: the new columns fill exactly the three deferred decisions, and the contract's
own "Optional Fields" entry is an unfilled `@` placeholder at lines 243-245, so the field list is
not closed by its own text. **The document would equally permit filling the placeholders in a
banner or a configuration file rather than per row. Defensible, not compelled.** This is a real
choice for the user at Gate 1, not a settled fact.

**E2, the alias arithmetic.** The identity holds: energy over a 60-minute interval equals average
megawatts times one hour. **The rule as stated has two holes, and the plan must close both.**

1. It does not say whether the 60-minute condition is checked **per row or per file**, so a
   mixed-width file is undefined under it.
2. It cannot detect misdeclared semantics. **A daily MWh total repeated on every hour row passes
   the 60-minute gate and is wrong by a factor of about 24.** That is the same class of error the
   project already hit once, recorded at `docs/HANDOFF.md` under the 5-minute integration finding.

A third, minor gap: no float tolerance is stated on the comparison against 60.

### Minor citation drift, content correct

- `make_synthetic_winter_stress.py` line cites run 2 to 4 lines off: `COLD_DAY_TOTAL_MWH` sits at
  45, `BANNER_LINES` at 49-52, `render_csv` at 135.
- `demand_percentile_source` is serialized at `cli.py:534` and rendered at 635. Lines 305-306 print
  the warnings, which carry the derivation notice.
- The §10 grep output is abridged, 4 of 20 lines shown. The conclusion stands.
- The Switch line 57 quote truncates mid-sentence without an ellipsis.
