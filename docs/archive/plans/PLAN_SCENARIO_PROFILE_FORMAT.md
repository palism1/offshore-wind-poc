# Plan — scenario profile format

Date: 2026-08-02. Revision 1. Gate 1 approved the format on 2026-08-02.

Research: `docs/RESEARCH_SCENARIO_FORMAT_2026-08-01.md`. Team contract:
`docs/source/2026-07-30_Software_Architecture_Documentation.md`, Component 2 Data Contract at
lines 234 to 245.

Abbreviations used once each: CSV = comma separated values. ETL = extract, transform, load.
CLI = command line interface. DST = daylight saving time. UTC = Coordinated Universal Time.
MW = megawatt. MWh = megawatt hour. CDF = cumulative distribution function.

The approved format, not re-opened here:

```
date,hour,ts,interval_minutes,load_mw,wind_mw,oil_mw,gas_mw,demand_percentile,wind_forecast_frac
```

Required: `date`, `hour`, `ts`, `interval_minutes`, `load_mw`. Optional: the rest.
`oil_mw` and `gas_mw` are reserved names only. No extractor work. No migration 004.

---

## Revision 1 — findings applied

An adversarial review attacked revision 0 on 2026-08-02. Every finding below is accepted. None is
declined. A fourth spike (`spike_rev1.py`) reproduced the four measurable claims before the
rewrite; the measurements sit in section 0.

| # | Finding | Disposition | Where |
|---|---|---|---|
| B1 | The 25 hour reader test cannot pass. A date holds at most 24 hour keys, so the duplicate check fires first and the guard's 25 branch is dead code. | Accepted. Deleted the 25 branch from the guard clause. Re-specified the test to assert the duplicate pair message. | b.3 guard, phase 3 tests |
| B2 | b.5 rule 5 contradicted b.1 rule 7. The fall back day yields 24 buckets, never 25, so a literal implementation never names DST. | Accepted. Rule 5 rewritten as two conditions. Both phase 6 tests renamed. | b.5 rule 5, phase 6 tests |
| B3 | Nothing rejected a non-finite or blank `interval_minutes`, and the 60 minute check fails open on `nan`. | Accepted. Added four parametrized tests and two blank cell tests. | b.3 step 4, phase 3 tests |
| N1 | The wind join had no frozen interface: no forecast row filter, no join key, no unit rule. | Accepted. b.5 rule 8 rewritten in three parts. Two tests added. | b.5 rule 8, phase 6 tests |
| N2 | The MWh rejection test asserted nothing, and a mixed case header would slip through. | Accepted. Fixture and assertion stated. Lowercased fieldmap pinned. | b.3 header checks, phase 3 tests |
| N3 | The minimum day rank is 0.0 only for a strictly unique minimum. A tied minimum returns 0.5. | Accepted. Spec now says strictly unique, and a second test pins the tied case. | phase 2 tests |
| N4 | Reading `demand_percentile_basis` needs the comment lines kept, which was never listed as a change, and substring matching false-positives. | Accepted. Filter change listed. Banner grammar specified. | b.3 banner rule |
| N5 | The unit choice resolves a team document disagreement unilaterally, and the `demand_percentile` unit mismatch was unstated. | Accepted. Added a team notification phase before phase 3. Added the fraction to the units banner. | phase 0, open item 2 |
| N6 | The reader does not enforce continuous timestamps. A mixed offset day carries a phantom gap. | Accepted, and taken further than proposed. Added a same offset per date check, which is cheaper and stricter than a 3600 s check. | b.3 step 7, phase 3 tests |
| Nit 1 | "the writer can never emit a file its own reader rejects" is overstated. | Accepted. Claim narrowed to the three row checks, and the gap named and tested. | b.2 rule 8, phase 5 tests |
| Nit 2 | "five blank cell tests" should be six. | Accepted, all six named. | phase 3 breakage table |
| Nit 3 | The size delta itemization does not add up. | Accepted. The growth is test volume. Split stated. | section (a) |
| Nit 4 | The refusal advice is wrong for a range spanning a transition date. | Accepted. The inherent limit stated once, plainly. | b.5 rule 5, R1 |
| Nit 5 | `EASTERN` was shown as both an assignment and an import. | Accepted. It is an import. | b.1 |

The review confirmed and left standing: spike finding A reproduced independently at 21,000 trials
with 0 mismatches, the single track decision, the red suite ordering of phases 3 and 4, the three
resolved open items, the breakage enumeration, the 26 header literal count, and every purity
boundary.

---

## 0. Stage 4a spike results

Four throwaway scripts ran under `uv run python` on this machine, Python 3.12, outside the
repository. Nobody commits them. The results below are measured, not documented behavior.

| # | Question | Measured answer |
|---|---|---|
| 1 | `datetime.fromisoformat("2026-01-06T00:00:00-05:00")` | `.tzinfo` is `datetime.timezone`, a fixed offset, **not** `ZoneInfo`. `.hour` is `0`, the local wall clock hour. `.date()` is `2026-01-06`, the local date under the stored offset. The same instant in UTC is `2026-01-06T05:00:00+00:00`. |
| 2 | Fall back pair `2025-11-02T01:00:00-04:00` and `...-05:00` | `==` is `False`. Both `.hour` are `1`. Both `.date()` are `2025-11-02`. A `set` holds 2 elements. `hash` differs. The difference is 3600.0 s. |
| 3 | `datetime.fromisoformat` on a naive string | **It does not raise.** It returns a datetime with `tzinfo=None`. The reader must test `tzinfo is None` itself. |
| 3 | The same on garbage | `ValueError: Invalid isoformat string: 'not-a-ts'`. An empty string and a one digit offset `-5:00` raise the same type and message shape. |
| 4 | `csv.DictWriter` under a `#` banner, read by `csv.DictReader` | Round trip is clean. `csv.writer` emits `\r\n` while the banner uses `\n`; the mixed file still parses. The filter idiom at `scenario_input.py:95-99` keeps a quoted field that holds a comma and a `#`. |
| 5 | `owr.etl.rows_csv.read_rows_csv` real signature | `read_rows_csv(stream, dataset, *, origin) -> list[dict[str, str]]`. Every value is a `str`. It accepts any iterable of lines. Called with `DATASETS["load"]` over the first 400 lines of `data/load_2025.csv` it returned 393 dicts. `daily_loads_from_readings` on the first 100 returned one `DailyLoad` with `complete=False`, `hours_covered=8.333...`. |
| 6 | `sum(hourly avg_mw) == daily load_mwh` on real data | **Holds exactly** for 2025-01-01. `sum_avg_mw = 298077.7115833333`, `daily_mwh = 298077.7115833333`, residual `0.0`, 24 hours, `complete=True`. |
| 7 | `float("60") == 60` | `True`. Also `12 * (5.0/60.0) == 1.0` is `True` and `sum([5.0/60.0] * 12) == 1.0` is `True`. Every realistic grain sums to an exact hour. |

Revision 1 measurements, from `spike_rev1.py`:

| # | Question | Measured answer |
|---|---|---|
| 8 | Does the 60 minute tolerance check fail open on a non-finite value? | **On `nan` only.** `abs(nan - 60.0) > 1e-9` is `False`, so `nan` passes. `inf` and `-inf` do **not** pass the magnitude test, so they are rejected, but with a message that names the wrong problem. `_parse_finite_float` is therefore load bearing for both correctness and the message. |
| 9 | Does a merged fall back bucket report exactly 2.0 hours? | Yes at every realistic grain: `sum([5.0/60.0] * 24) == 2.0`, `sum([0.25] * 8) == 2.0`, `1.0 + 1.0 == 2.0`. The plan still compares with a tolerance, for generality. |
| 10 | What rank does a tied minimum get? | `inv_rank([1, 2, 3], 1) == 0.0`. `inv_rank([1, 1, 2], 1) == 0.5`. `inv_rank([1, 1, 1, 2], 1) == 0.667`. The 0.0 result needs a **strictly unique** minimum. |
| 11 | Does the reader lowercase header names? | Yes. `scenario_input.py:109` is `fieldmap = {name.strip().lower(): name for name in reader.fieldnames}`. Every header comparison must use the lowercased key. |
| 12 | Can a date bucket hold more than 24 hours? | No. `by_date[d]` is keyed by `hour` after a `0 <= hour <= 23` range check, so it holds at most 24 keys. A row count of 25 is unreachable at the guard. |

Two findings the spike added.

**Spike finding A. The research claim about `demand_percentile` is false as written.** The research
says a plain empirical CDF rank and `percentile_threshold` "select the identical day set by
construction". Over 21,000 random trials the plain CDF rank `count(x <= v)/n` disagreed with
`owr.stress_finder.percentile_threshold` in **5,777** trials. `percentile_threshold` uses linear
interpolation (`src/owr/stress_finder.py:15-32`). The inverse of that same interpolation agreed in
**0 of 21,000** trials, across ties, `n=1`, `p=0.0` and `p=1.0`. The adversarial review reproduced
this independently at the same counts. Section b.4 takes the inverse definition. Section (c) makes
the agreement a property test.

**Spike finding B. `datetime.combine(d, time(h), tzinfo=ZoneInfo("America/New_York"))` is safe for
the fixture dates and unsafe in general.** It returned `-05:00` for January dates and `-04:00` for
July dates. For the nonexistent hour `2025-03-09 02:00` it returned `-05:00` and raised nothing.
The example generator builds 2026-01-06 to 2026-01-11 only, so it never meets that hour, and
phase 4 adds an assertion that pins every generated offset to `-05:00`.

**Correction to a cited line.** The research cites the byte identical regeneration check at
`docs/HANDOFF.md:39`. The row is at **`docs/HANDOFF.md:43`**. Section 7 re-baselines that row.

**Header literal count, checked independently.** `grep -c "def test_" tests/test_scenario_input.py`
returns **26**. `grep -o "date,hour[a-z_,]*"` returns **26** full header literals plus **1** bare
`date,hour` at line 261, so 27 lines carry the string. The research count of 26 is correct for
full headers.

---

## Phase 0 — one message to the team, before phase 3 merges

Open item 2 chooses MW over MWh, which resolves a disagreement inside the team's own architecture
document. Repo convention 4 in `docs/HANDOFF.md` says a document disagreement goes to the team as a
decision, not into the code silently. `docs/ARCHITECTURE_REVIEW_2026-07-31.md:247` already logs the
mixing as finding D5, so the disagreement is on record, but the resolution is not.

Post one message before phase 3 merges. It states four things:

1. The profile carries `wind_mw`, `oil_mw` and `gas_mw`, in average MW over the hour.
2. Component 2 types the same three series as MWh at lines 237 to 239, and Component 6 types them
   as MW at lines 470 to 472. The plan takes Component 6.
3. The reader **rejects** the `*_mwh` spelling with a message that names the rename, because a daily
   MWh total repeated on 24 rows cannot be told apart from an average MW series.
4. Component 2 types `demand_percentile` as `%` at line 240. The ETL writes a fraction in `[0, 1]`,
   because `owr.budget.priority` at `src/owr/budget.py:15-24` multiplies it by a weight of 0.7.

This is a notification, not a gate. Phase 1 and phase 2 may start before the reply arrives. Phase 3
does not merge without it. See risk R11 for the cost if the team reverses it.

---

## (a) The track decision

**Single track. Seven build phases plus phase 0, run in order, by one implementer.**

The two track option fails condition 2 of the four. Each condition, stated:

1. **Two disjoint file sets, path by path. PASS.**
   Track A would own `src/owr/etl/hourly.py`, `src/owr/etl/profile_csv.py`,
   `src/owr/etl/transform.py`, `src/owr/etl/cli.py`, `tests/test_etl_hourly.py`,
   `tests/test_etl_profile_csv.py`, `tests/test_etl_transform.py`,
   `tests/test_etl_cli_transform.py`. Track B would own `src/owr/scenario_input.py`,
   `tests/test_scenario_input.py`, `src/owr/cli.py`, `tests/test_cli.py`,
   `examples/make_synthetic_winter_stress.py`, `examples/synthetic_winter_stress.csv`. The two
   lists do not overlap.
2. **Neither track needs the other's code. FAIL.**
   The round trip test writes a file with `write_profile_csv` and reads it with
   `read_day_profiles`. It is the one test that proves the writer and the reader agree, and it
   needs both tracks. Moving it to the merge stage leaves the frozen interface unproven until the
   last step, which is the exact failure mode stage 4a exists to prevent. A second coupling:
   `examples/synthetic_winter_stress.csv` is track B, and `tests/test_peak_window.py:18` and
   `tests/test_cli.py:22` read it. The whole suite is red from the moment the reader changes until
   the fixture is regenerated. Two tracks cannot both hold a green suite across that gap.
3. **Build time per track above 45 minutes. PASS.** Track A is about 2 hours 55 minutes.
   Track B is about 1 hour 25 minutes.
4. **Every shared file assignable to the merge stage. PASS.** See section (d).

One condition fails, so the plan is single track. Single track is the default here, not a
degradation.

**Size, stated honestly, and where the growth sits.** About **500 new or changed source lines** and
about **835 new or changed test lines**, so about **1,335** total. The research said "about 700",
but the research's own file table sums to about 1,036 once its per file deltas are added, so its
headline figure understated its own table.

The source figure agrees with the research to within about 10 lines. **All of the remaining growth
is test volume**, about 300 lines above the research table:

| Added tests | Lines |
|---|---|
| The percentile rank property and tie tests, phase 2 | about 100 |
| The DST, completeness and refusal tests, phases 1 and 6 | about 80 |
| The non-finite and blank cell parametrizations for `ts` and `interval_minutes`, phase 3 | about 60 |
| The wind forecast row, wind offset and wind gap tests, phase 6 | about 45 |
| The banner injection, redaction, grammar and writer gap tests, phases 3 and 5 | about 40 |

No new guard in the source is large. The three added guards (per row 60 minute check, same offset
per date, banner newline rejection) are about 20 source lines in total. The size delta is a test
count decision, not a design decision.

Estimated implementer time: about **4 hours 55 minutes** plus verification.

---

## (b) Frozen interfaces

Each entry is marked **verified** (a spike called it) or **designed** (from documentation and
source reading, never executed).

### b.1 New file `src/owr/etl/hourly.py`

```python
# EASTERN is IMPORTED from owr.etl.daily, never redefined here.
from owr.etl.daily import EASTERN, IntervalReading   # designed

@dataclass(frozen=True)
class HourlyValue:                              # designed
    date: date          # LOCAL calendar date
    hour: int           # 0..23, local wall clock
    ts: datetime        # tz-aware, interval START, the earliest instant in the bucket
    avg_mw: float       # energy weighted average MW over the hour
    hours_covered: float
    intervals: int
    complete: bool      # abs(hours_covered - 1.0) <= tolerance_hours

def hourly_from_readings(                       # designed
    readings: list[IntervalReading],
    *,
    tz: ZoneInfo = EASTERN,
    tolerance_hours: float = 1e-9,
) -> list[HourlyValue]:
    ...

def check_hourly_spacing(                       # designed
    timestamps: Sequence[datetime], *, label: str
) -> None:
    ...
```

Rules the module docstring must state, one per line, mirroring `daily.py`:

1. `avg_mw = Sum(load_mw * interval_hours) / Sum(interval_hours)`. Never a mean of `load_mw`.
   The numerator is the integral `daily.py:104` computes.
2. Group on `(reading.ts.astimezone(tz).date(), reading.ts.astimezone(tz).hour)`.
3. Reject a naive timestamp. Message: `naive timestamp not allowed: <iso>`, the same text
   `daily.py:86` uses.
4. Reject a duplicate absolute instant. Message: `duplicate absolute instant: <iso>`, the same
   text `daily.py:93` uses.
5. Attribute an interval wholly to the local hour of its start. At 5 minute and 60 minute grain
   nothing straddles an hour boundary. The module does not split a straddling interval.
6. `tolerance_hours` defaults to `1e-9`. Spike question 7 measured `sum([5.0/60.0] * 12) == 1.0`
   exactly, and spike question 6 measured a daily residual of `0.0` on real data, so a tight
   tolerance carries no known false positive. If a real feed trips it, loosen to `1e-6` and record
   the residual.
7. The DST fall back hour collapses two distinct instants into one bucket, because both carry
   local hour 1 on the same local date. **A fall back date therefore yields 24 buckets, never 25.**
   The merged bucket reports `hours_covered` close to `2.0` and `complete = False`. Spike question
   9 measured `sum([5.0/60.0] * 24) == 2.0` exactly. The module does not raise; the caller refuses
   the export. Rule 7 is the reason `complete` exists per hour.
8. `ts` on a merged bucket is the earliest instant in the bucket.
9. Return the list sorted by `ts`, one entry per local hour that has at least one reading. A spring
   forward date yields **23** buckets, because the skipped local hour has no readings.

`check_hourly_spacing` raises `ValueError` if any two consecutive sorted timestamps do not differ
by exactly 3600.0 s, naming both timestamps and the measured gap. It exists because
`WindObservation` (`extract.py:83-90`) and `raw.hourly_wind` carry no interval width, so a 60
minute assumption on the wind feed is otherwise unchecked. **Verified as safe against DST**: spike
question 2 measured the two fall back instants 3600.0 s apart, so the check does not fire on a
transition day.

### b.2 New file `src/owr/etl/profile_csv.py`

```python
PROFILE_SCHEMA_VERSION = "1"                    # designed
PROFILE_COLUMNS: tuple[str, ...] = (            # designed
    "date", "hour", "ts", "interval_minutes", "load_mw",
    "wind_mw", "oil_mw", "gas_mw", "demand_percentile", "wind_forecast_frac",
)
PROFILE_REQUIRED_COLUMNS: tuple[str, ...] = (
    "date", "hour", "ts", "interval_minutes", "load_mw",
)

class ProfileCsvError(ValueError):              # designed
    """Raised for an invalid profile row or banner on write."""

@dataclass(frozen=True)
class ProfileRow:                               # designed
    date: date
    hour: int
    ts: datetime
    interval_minutes: float
    load_mw: float
    wind_mw: float | None = None
    oil_mw: float | None = None
    gas_mw: float | None = None
    demand_percentile: float | None = None
    wind_forecast_frac: float | None = None

def write_profile_csv(                          # designed
    path: str,
    rows: Sequence[ProfileRow],
    *,
    banner: Sequence[tuple[str, str]],
    getenv: Callable[[str], str | None] = os.environ.get,
) -> int:
    """Write a bannered hourly profile CSV. Return the row count written."""
```

Writer rules:

1. Open with `open(path, "w", newline="")`, the same call `rows_csv.py:35` makes.
2. Write each banner pair as `# {key} = {value}\n`, in the given order, before the header.
3. Pass every banner **value** through `redact_secrets(value, getenv=getenv)`. The rows CSV writer
   redacts only `source_query` (`rows_csv.py:41`). The profile banner carries file paths, so
   redact all of them.
4. Raise `ProfileCsvError` if any banner key or value holds `\n` or `\r`. A newline in a value
   would inject a fake banner line or a fake header. Raise if a key holds `=`.
5. Emit `PROFILE_REQUIRED_COLUMNS` always. Emit an optional column only when at least one row
   carries a non `None` value for it. Column order always follows `PROFILE_COLUMNS`.
6. Write `hour` as an `int`. **Verified**: spike question 4 measured `csv.writer` rendering `0` for
   an int and `60.0` for a float, using `repr` for floats at full precision.
7. Write `ts` as `ts.isoformat()`. Raise `ProfileCsvError` if `ts.tzinfo is None`.
8. Raise `ProfileCsvError` if `row.hour != row.ts.hour` or `row.date != row.ts.date()`.
   **The accurate claim, narrowed after review:** these three row level checks mean the writer
   cannot emit a **row** that fails the reader's per row cross checks. They say nothing about the
   file as a whole. The writer does **not** check day completeness, date consecutiveness, the
   24 row count, per date scalar constancy, or the same offset per date rule. Those are file level
   properties, and the CLI owns them at b.5 rules 3 to 7. A caller who hands `write_profile_csv`
   a 23 row day gets a 23 row file that the reader then rejects. Phase 5 tests that gap on purpose.
9. Do not import `owr.scenario_input`, `owr.cli`, or any database driver.

The banner keys the ETL writes, in this order:

```
# scenario_profile = v1
# schema_version = 1
# software_version = <owr.version.code_version()>
# version_fields_note = simulation_version, calculation_version and configuration_version are run scoped; this file is a simulation input
# units = average MW over the interval; energy = value * interval_minutes / 60; demand_percentile and wind_forecast_frac are fractions in [0, 1], not percent
# local_timezone = America/New_York
# generated_at = <UTC ISO 8601>
# derived_from = <input paths, comma separated>
# load_source = <provenance source of the load inputs>
# wind_source = <provenance source of the wind input>        (omitted when no wind)
# dataset_version = <provider version>
# source_query = <redacted>
# demand_percentile_basis = pooled <season> complete days, n=<N>, threshold_mwh=<T>, percentile=<P>
```

The fraction clause in `# units` answers the Component 2 mismatch named in phase 0 item 4.

### b.3 Changed `src/owr/scenario_input.py`

```python
REQUIRED_COLUMNS = ("date", "hour", "ts", "interval_minutes", "load_mw")   # designed
OPTIONAL_COLUMNS = ("wind_mw", "demand_percentile", "wind_forecast_frac")  # unchanged
RESERVED_COLUMNS = ("oil_mw", "gas_mw")                                    # designed, read and ignored
REJECTED_COLUMNS = ("load_mwh", "wind_mwh", "oil_mwh", "gas_mwh")          # designed
PER_DATE_COLUMNS = ("demand_percentile", "wind_forecast_frac")             # unchanged
PROFILE_INTERVAL_MINUTES = 60.0                                            # designed
INTERVAL_MINUTES_TOLERANCE = 1e-9                                          # designed
BANNER_BASIS_KEY = "demand_percentile_basis"                               # designed

class ScenarioInputError(ValueError): ...                                  # unchanged

@dataclass(frozen=True)
class DayProfileSet:                                                       # UNCHANGED, all five fields
    days: list[DayProfile]
    demand_percentile_source: str   # "file" | "derived-rank"
    wind_forecast_frac_source: str  # "file" | "default-zero"
    has_wind: bool
    warnings: tuple[str, ...]

def read_day_profiles(stream: TextIO, *, origin: str) -> DayProfileSet:    # signature UNCHANGED
```

`DayProfileSet` gains no field. That keeps `src/owr/cli.py:528-540` and `src/owr/cli.py:585-600`
free of change beyond help text. `read_day_profiles` keeps a `TextIO` stream and never takes a
path. `scenario_input.py` imports nothing from `owr.etl` and nothing from `zoneinfo`.

**Change to the line filter at `scenario_input.py:95-99`, listed explicitly.** Today the
comprehension discards every comment line. It must now **keep** them in a second list, so the
banner rule below can run. One pass over the stream, two outputs: the data lines with their line
numbers, exactly as today, and a list of comment lines. Comment lines never reach
`csv.DictReader`, so the existing skip behavior is unchanged from the parser's point of view.

Parse order per row, each error carrying the origin and the line number:

1. `date`: blank check, then `date.fromisoformat`. Unchanged.
2. `hour`: blank check, `int`, then range `0 <= hour <= 23`. Unchanged. **The range check stays
   before every new check**, so `tests/test_scenario_input.py:282-289` keeps its current message.
3. `ts`: blank check, then `datetime.fromisoformat`. On `ValueError` report
   `column 'ts': cannot parse <value>`. Then, if `ts.tzinfo is None`, report
   `column 'ts': naive timestamp <value> (must carry a UTC offset)`, the wording at
   `etl/cli.py:188-191`. **Verified**: spike question 3 measured that a naive string parses without
   an exception, so the explicit `tzinfo is None` test is load bearing.
4. `interval_minutes`: blank check, then **`_parse_finite_float`**, then
   `abs(v - PROFILE_INTERVAL_MINUTES) > INTERVAL_MINUTES_TOLERANCE` raises.
   **`_parse_finite_float` is mandatory, not stylistic.** Spike question 8 measured
   `abs(nan - 60.0) > 1e-9` as `False`, so a bare `float()` lets `nan` through the magnitude test
   and into the file. The same spike measured that `inf` and `-inf` fail the magnitude test, so
   they are rejected either way, but with a message that names the wrong problem. **The check is
   per row.** See open item 2.
5. Cross checks: `ts.hour != hour` raises; `ts.date() != d` raises. Both use the stored offset
   only. **Verified**: spike question 1 measured `.hour` as the local wall clock hour and `.date()`
   as the local date under the stored offset, so no time zone database is needed.
6. `load_mw`, `wind_mw`, and the two per date scalars: unchanged.
7. **Same offset per date, new.** Record `ts.utcoffset()` for the date on its first row. A later
   row of the same date with a different offset raises:
   `date <d>: rows carry two different UTC offsets (<a> and <b>). A local day that changes offset
   is a daylight saving time transition day, and this reader takes 24 hour days only.`

Rule 7 replaces the "continuous timestamps" rule the team contract names at line 249. It is
cheaper than a 3600 s spacing check and strictly stronger for this format, for two reasons. A day
of 24 distinct hours that all share one offset has no phantom gap by construction, so spacing needs
no separate test. And rule 7 catches the one DST case the row count cannot see: a fall back date
written with only 24 of its 25 rows passes the count guard, but its offsets differ, so rule 7
rejects it. Without rule 7 that file reads as a valid day and is silently wrong by one hour of
load.

Header checks, in this order, before any row parse:

1. **Rejected names.** Compare against the **lowercased** `fieldmap` keys at
   `scenario_input.py:109`, so `Wind_MWh` and `WIND_MWH` are caught too. **Verified**: spike
   question 11 read the line and confirmed it lowercases. If any name in `REJECTED_COLUMNS` is
   present, raise. The message names the rename and the unit. This runs first, so a file with
   `wind_mwh` gets the specific message rather than a missing column message.
2. Missing required columns. Unchanged mechanism, new required set.

Duplicate detection, replacing the `(date, hour)` key at `scenario_input.py:171-172`:

1. Keep a `set[datetime]` of every `ts` seen. A repeat raises
   `duplicate absolute instant: <iso>`. **Verified**: spike question 2 measured the two fall back
   instants as two distinct set elements with different hashes.
2. Keep the `(date, hour)` bucket for assembly. A repeat with a **different** `ts` raises:
   `date <d> hour <h> appears twice with different UTC offsets. That is the daylight saving time
   fall back hour. This reader takes 24 hour days only.`

The 24 row guard at `scenario_input.py:204-212` keeps its arithmetic and gains **one** conditional
clause, for the count 23 only:

```
date <d>: expected exactly 24 rows, got 23. A local day of 23 hours is a daylight saving time
spring forward day. 15 U.S.C. 260a puts every United States transition in March or November.
Both study seasons (Dec 1 to Feb 28 or 29, Jun 1 to Sep 30) exclude those dates.
```

**There is no 25 branch, and adding one would be dead code.** `by_date[d]` is keyed by `hour` after
the `0 <= hour <= 23` range check at step 2, so it holds at most 24 keys. **Verified** by spike
question 12. A 25th row must repeat an hour, and the per row duplicate check at parse time fires
first with the fall back message above. For any count other than 23 the guard does not mention DST,
because a truncated file is the likelier cause.

**Honest limit of the row count guard.** It is a shape guard, not a calendar guard. It cannot see
that 2025-11-02 really holds 25 hours. Rule 7 catches that case instead, and the ETL export refuses
the date before it is ever written (b.5 rule 5).

The derived rank block at `scenario_input.py:223-241` keeps its arithmetic exactly. It gains one
warning clause: `This rank is local to the supplied file. It is not the pooled seasonal
population the ETL writes, and the two values are not comparable.`

**The banner rule, with its grammar.** After the filter change above, parse each retained comment
line as `# key = value`: strip the leading `#` and the surrounding spaces, split on the **first**
`=`, strip both sides, and lowercase the key. Ignore any comment line with no `=`. Compare the key
**exactly** against `BANNER_BASIS_KEY`. If the key is present and the `demand_percentile` column is
absent, raise: `banner declares 'demand_percentile_basis' but the demand_percentile column is
absent; the file looks truncated.` Exact key comparison, never a substring search, so a prose
comment that mentions the phrase does not false-positive. The reader takes no **value** from the
banner; it reads one key as a consistency signal only.

### b.4 Changed `src/owr/etl/transform.py`

```python
def percentile_rank_within(                     # designed; property VERIFIED by spike
    daily: list[DailyLoad], *, season: Season
) -> dict[date, float]:
    """Percentile rank of each complete season day within the pooled population.

    The population is the one ``compute_threshold`` filters at lines 47 to 49:
    days of ``season`` with ``complete=True``, pooled across every year in
    ``daily``. Out of season days and incomplete days are absent from the result.

    The rank is the inverse of ``owr.stress_finder.percentile_threshold`` on the
    same values, so for every ``p`` in [0, 1]::

        {d: rank[d] >= p} == {d: d.load_mwh >= percentile_threshold(values, p)}

    Raise ``ValueError`` with the ``compute_threshold`` message when the
    population is empty.
    """
```

The definition, over `ordered = sorted(values)` of length `n`:

```
n == 1              -> 1.0
v >= ordered[-1]    -> 1.0
v <  ordered[0]     -> 0.0
otherwise           -> j = bisect_right(ordered, v) - 1
                       frac = 0.0 if ordered[j] == v
                              else (v - ordered[j]) / (ordered[j + 1] - ordered[j])
                       (j + frac) / (n - 1)
```

**Verified**: 21,000 random trials, 0 mismatches, across ties, `n=1`, `p=0.0` and `p=1.0`. The
plain CDF `count(x <= v)/n` mismatched in 5,777 of the same 21,000. The adversarial review
reproduced both figures independently.

Two boundary notes the docstring must carry.

- The set identity holds for every value inside `[min, max]`. A value strictly below `min` returns
  `0.0` while `percentile_threshold(values, 0.0)` returns `min`, so the identity does not hold for
  an out of range value at `p = 0.0`. Every population day sits inside the range by construction,
  so the corner is out of scope.
- **A rank of `0.0` requires a strictly unique minimum.** With a tied minimum the shared value
  takes the rank of the **last** tied index. Spike question 10 measured `inv_rank([1, 1, 2], 1)`
  as `0.5` and `inv_rank([1, 1, 1, 2], 1)` as `0.667`. The `frac` branch cannot divide by zero,
  because it runs only when `ordered[j] < v < ordered[j + 1]`.

### b.5 Changed `src/owr/etl/cli.py`, the `--profile-out` surface

```
etl transform --input PATH [--input PATH ...]
              [--wind-input PATH]
              [--profile-out PATH]
              [--profile-start YYYY-MM-DD] [--profile-end YYYY-MM-DD]
              [--percentile P] [--season S] [--min-window-days N]
              [--out PATH] [--format text|json]
```

| Flag | Type | Default | Behavior |
|---|---|---|---|
| `--profile-out` | path | `None` | Write the hourly profile CSV. Off by default, so every existing test keeps passing. |
| `--profile-start` | `_date` | `None` | Earliest local date to export, inclusive. |
| `--profile-end` | `_date` | `None` | Latest local date to export, inclusive. |
| `--wind-input` | path | `None` | A wind rows CSV written by `etl extract --dataset wind --out`. Read with `read_rows_csv(stream, DATASETS["wind"], origin=path)`. |

Rules the CLI applies, each an exit code 2 usage error through the existing
`except (OSError, ValueError)` handler at `cli.py:139-141`:

1. Refuse `--profile-start` or `--profile-end` without `--profile-out`.
2. Refuse `--wind-input` without `--profile-out`.
3. Refuse an export whose date set is empty after the range filter.
4. Refuse an export whose dates are not consecutive.
5. **The completeness guard, rewritten after review.** Two conditions, either one refuses:
   - the date's bucket count from `hourly_from_readings` is not 24, or
   - any bucket of the date has `complete is False`.

   Name daylight saving time in the message when **either** the bucket count is 23, **or** any
   bucket has `hours_covered` within `tolerance_hours` of `2.0`. The first is the spring forward
   day. The second is the fall back day, which yields 24 buckets with one of them two hours wide
   (b.1 rule 7). **A bucket count of 25 never occurs**, so the message must not test for it.
   For any other cause, report the date, the bucket count, and the first incomplete hour, without
   mentioning DST.

   **The inherent limit, stated once.** A consecutive date range that contains a transition date
   cannot be expressed in this format at all, because the reader requires consecutive dates and 24
   hour days. The operator must choose a range that ends before the transition or starts after it.
   Put that sentence in the message. Do not say "stay inside a single season", which is wrong
   advice for a shoulder study.
6. Refuse a date whose season differs from `--season`, so one `demand_percentile_basis` line
   describes the whole file.
7. Refuse a date absent from `percentile_rank_within`, which means an incomplete or out of season
   day.
8. **The wind join, specified in four parts after review.**
   - **Filter.** Keep only rows with `horizon_days == 0`. `raw.hourly_wind` carries realized and
     forecast rows on one table, keyed `(source, ts, horizon_days)`
     (`db/migrations/001_init.sql:36-46`), and `WindObservation.horizon_days` documents `0` as
     realized and above zero as reserved for forecast rows (`src/owr/etl/extract.py:83-90`). An
     implementation that joins every row silently overwrites a realized value with a forecast.
   - **Key.** Join on the absolute instant `HourlyValue.ts`, not on `(date, hour)`. Python compares
     aware datetimes by instant, so a wind file stored at `+00:00` joins correctly to a load file
     stored at `-05:00`. Spike question 2 verified that two datetimes at the same wall clock and
     different offsets are unequal, which is the same property.
   - **Units.** EIA-930 reports hourly integrated values in MW (research section 6). At 60 minute
     grain, energy over the hour in MWh equals average MW over the hour, so `gen_mw` needs no
     conversion. Build each wind reading as
     `IntervalReading(ts=..., load_mw=gen_mw, interval_hours=1.0)` and run it through
     `hourly_from_readings`, so the wind side and the load side share one code path.
   - **Spacing.** Run `check_hourly_spacing` on the filtered realized timestamps **before** the
     readings are built, because `raw.hourly_wind` carries no interval width and the `1.0` above
     would otherwise be an unchecked assumption.
   - Refuse the export if any exported hour has no wind value. A blank `wind_mw` cell reads as
     `0.0` at `scenario_input.py:159-163`, which is a silent zero.
9. Never write `wind_forecast_frac`. Nothing computes it. The reader defaults it to `0.0` and
   warns, which is the current behavior.
10. Never write `oil_mw` or `gas_mw`.
11. Keep `--profile-out` inside `cmd_transform`. Import no database driver on this path.
12. Do not import `owr.scenario_input` in `src/owr/etl/`.

### b.6 Changed `src/owr/cli.py`

`--input` help text at line 136 gains the required column list. No other change. **Designed.**

---

## Open item 1 — per row against banner

**Decision: carry `ts` and `interval_minutes` per row. Keep the banner for provenance and version
keys only.**

The fact checker ruled that reading the team contract as permitting new columns is defensible, not
compelled, and that a banner or a configuration file would fill the same three placeholders
("Simulation time step", "Timestamp format", "Time zone" at architecture document lines 9 to 11).

**Reason 1, and it is decisive.** A banner value is file scoped, and the DST fall back hour needs a
row scoped instant. Two rows with the same `date` and `hour` are indistinguishable without `ts`.
Spike question 2 measured the two fall back instants as distinct only through their offsets. No
banner can carry that distinction, so a banner only design cannot detect the duplicate at all.

**Reason 2.** `read_day_profiles` skips every `#` line today (`scenario_input.py:95-99`). Reading
values out of the banner would require a banner parser, a second header grammar, and a second
source of truth beside the CSV header. Per row keeps one grammar. Revision 1 does add a **key only**
banner read for `demand_percentile_basis`, which takes no value from the banner and so does not
weaken this reason.

**Reason 3.** The team contract already types `date` and `hour` per row, and its "Optional Fields"
entry is an unfilled placeholder at lines 243 to 245, so the field list is not closed by its own
text.

**What it costs, stated plainly.**

- Two extra cells on every row, about 34 bytes each. `examples/synthetic_winter_stress.csv` grows
  from 147 lines to about 151, and from about 4 kilobytes to about 9 kilobytes.
- Twenty six header literals and the `_rows()` helper in `tests/test_scenario_input.py` change.
- A human reading the file sees ten possible columns instead of six.
- The same three values now appear twice in a written file, once per row and once implied by the
  banner `local_timezone` line. The `ts.hour == hour`, `ts.date() == date` and same offset per date
  checks make the redundancy safe. Redundancy without a check is the defect; redundancy with an
  exact check is not.

---

## Open item 2 — the MWh alias hole

**Decision, part 1: `interval_minutes` is checked per row, and must equal 60 within `1e-9`.**

A mixed width file is therefore rejected at its first non 60 row, with the line number. The rule is
not "per file" because a per file rule leaves the mixed case undefined, which is the hole the fact
checker named. The tolerance answers the fact checker's third point. Spike question 7 measured
`float("60") == 60` as `True`, so an exact comparison would work for `60` and `60.0`; the tolerance
costs nothing and survives a round trip through a spreadsheet. Spike question 8 measured that the
tolerance test alone lets `nan` through, so `_parse_finite_float` runs first, always.

The value cannot be anything except 60. The engine takes 24 values per local day
(`models.py:76-79`), so a 30 minute file would carry 48 rows per date and would fail the duplicate
and the 24 row guards anyway. Requiring 60 makes the failure early and the message clear.

**Decision, part 2: reject the `*_mwh` column names. Do not accept them as aliases.**

`load_mwh`, `wind_mwh`, `oil_mwh` and `gas_mwh` in the header raise `ScenarioInputError` before any
row parse, compared against the lowercased fieldmap. The message:

```
header carries 'wind_mwh'. This reader takes average MW over the hour, never MWh.
Rename the column to 'wind_mw' and confirm the values are average MW over the hour,
not a daily energy total. A daily MWh total repeated on 24 rows cannot be told apart
from an average MW series, so this reader refuses the spelling instead of guessing.
```

**Why reject rather than accept with a warning.** The research recommended accept and warn. The
fact checker then proved the rule cannot detect a daily MWh total repeated on 24 rows, an error of
about 24 times. Detection needs an external magnitude reference. `load_mw` has one, since the load
series drives the whole run, but the three MWh spellings all sit on **optional** generation series
with no reference. So detection is impossible, not merely hard. Accepting an undetectable semantic
guess is the same error class the project already paid for once, recorded in `docs/HANDOFF.md`
under the five minute integration finding.

**Why this does not break the team contract.** The contract answers itself. Component 2 types wind,
oil and gas as MWh at lines 237 to 239. Component 6 types the same three series as MW at lines 470
to 472. `docs/ARCHITECTURE_REVIEW_2026-07-31.md:247` already logs the mixing as finding D5.
Choosing MW satisfies Component 6 exactly and Component 2 numerically at hourly grain.

**This is a team decision, and phase 0 posts it.** Repo convention 4 says a document disagreement
goes to the team rather than into the code silently. Phase 0 sends one message before phase 3
merges, and it also names the `demand_percentile` unit mismatch, where Component 2 says `%` and the
ETL writes a fraction in `[0, 1]`. Risk R11 records the cost of a reversal.

**What it costs.** A teammate who exports the literal Component 2 header gets an error instead of a
run. The error names the exact rename, so the fix is one edit. An error naming the fix beats a
silent factor of 24.

**Belt and braces.** The writer stamps the `# units` banner line on every file it produces, so the
convention and the fraction rule travel with the artifact.

---

## Open item 3 — the three schema version fields

**Decision: read "every exchanged object" as applying to simulation outputs. Emit `schema_version`
and `software_version`. Do not emit the other three as empty keys. Emit one banner line that
records the omission and its reason.**

The contract at architecture document lines 104 to 113 lists five fields, each with an unfilled
description placeholder: `schema_version`, `software_version`, `simulation_version`,
`calculation_version`, `configuration_version`.

Two are writable for an input file. `schema_version` is the format version, `1`.
`software_version` is the short git sha already produced by `owr.version.code_version()`.

Three are not writable. `simulation_version` and `calculation_version` identify a simulation run,
and the profile is an input to a run rather than a product of one. `configuration_version` would
version a configuration object, and `src/owr/config.py` carries no version field today.

**Why not emit them empty.** Three keys with empty values in a committed artifact read as a defect
to an auditor, and nothing can ever fill them on this path. An empty key is a promise the writer
cannot keep.

**Why not drop them silently.** `docs/HANDOFF.md` records the instruction "Do not silently drop
them". So the writer emits one line that states the decision in the artifact:

```
# version_fields_note = simulation_version, calculation_version and configuration_version are run scoped; this file is a simulation input
```

An auditor reading the file sees the omission and its reason without opening this plan. When the
simulator gains a result artifact, that writer carries all five.

---

## (c) Test specification

Single track, so the specification runs per phase. Every test named below is new unless it is
marked as an existing test.

### Phase 1 — `tests/test_etl_hourly.py` (new)

| Test | Asserts |
|---|---|
| `test_twelve_five_minute_readings_give_one_hourly_average` | 12 readings at 5 minutes, loads 100 to 1200, give `avg_mw` equal to the arithmetic mean, `hours_covered == 1.0`, `intervals == 12`, `complete is True`. |
| `test_uneven_interval_widths_weight_by_duration` | One 45 minute reading at 100 MW and one 15 minute reading at 200 MW give `avg_mw == 125.0`, not `150.0`. This is the integral rule, and a mean of `load_mw` fails it. |
| `test_daily_equals_sum_of_hourly_on_real_data` | Read `data/load_2025.csv` for 2025-01-01 through `read_rows_csv` and `DATASETS["load"]`. Assert `sum(h.avg_mw for h in hourly) == pytest.approx(daily.load_mwh, rel=1e-12)`, 24 hours, every `complete is True`. **This is the load bearing test.** Spike question 6 measured the residual as exactly `0.0`, so a failure means a real defect. Skip with a clear reason when the file is absent, because `data/` is gitignored. |
| `test_daily_equals_sum_of_hourly_on_a_synthetic_day` | The same identity over a self contained 288 interval synthetic day, so the invariant is still covered when `data/` is absent. |
| `test_missing_interval_marks_hour_incomplete` | 11 of 12 five minute readings give `hours_covered == pytest.approx(11/12)` and `complete is False`. |
| `test_naive_timestamp_rejected` | `ValueError` matching `naive timestamp`. |
| `test_duplicate_absolute_instant_rejected` | `ValueError` matching `duplicate absolute instant`. |
| `test_fall_back_day_gives_24_buckets_one_of_them_two_hours` | Build 25 local hours of readings for 2025-11-02, one hour wide each, with hour 1 present at both `-04:00` and `-05:00`. Assert **24** `HourlyValue` entries, not 25; the `(2025-11-02, 1)` bucket has `hours_covered == pytest.approx(2.0)`, `intervals == 2`, `complete is False`, and `ts` equal to the earlier `-04:00` instant. **This is the contract b.5 rule 5 depends on.** |
| `test_spring_forward_day_gives_23_buckets` | 2025-03-09 with no readings in the skipped local hour gives 23 entries, every one `complete is True`. |
| `test_local_date_and_hour_come_from_the_stored_offset` | A reading at `2026-01-06T00:00:00-05:00` lands on `date(2026,1,6)` hour `0`, not on the UTC hour 5. |
| `test_empty_input_returns_empty_list` | `hourly_from_readings([]) == []`. |
| `test_unsorted_input_gives_the_same_result` | Shuffled readings give the identical list. |
| `test_check_hourly_spacing_accepts_exact_hours` | 24 timestamps one hour apart raise nothing. |
| `test_check_hourly_spacing_accepts_the_fall_back_pair` | `2025-11-02T01:00-04:00` then `...-05:00` raise nothing, because the gap is 3600.0 s. |
| `test_check_hourly_spacing_rejects_a_gap` | A 2 hour gap raises `ValueError` naming both timestamps. |
| `test_check_hourly_spacing_rejects_sub_hourly_spacing` | A 30 minute gap raises. |

### Phase 2 — `tests/test_etl_transform.py` (existing file, new tests)

| Test | Asserts |
|---|---|
| `test_percentile_rank_matches_percentile_threshold_over_a_grid` | For a fixed population of 40 complete winter days with mixed ties, and for `p` in `(0.0, 0.05, 0.5, 0.9, 0.95, 1.0)`, `{d for d in days if rank[d.date] >= p}` equals `{d for d in days if d.load_mwh >= percentile_threshold(values, p)}`. **This is the identity the whole column rests on.** Spike finding A measured 0 mismatches in 21,000 trials, reproduced independently by the review. |
| `test_percentile_rank_population_matches_compute_threshold` | Given winter days, summer days, and an incomplete winter day, the returned dict holds exactly the complete winter dates, and `len(result) == compute_threshold(...).population_days`. |
| `test_percentile_rank_ties_share_the_top_rank` | Three days tied at the maximum all return `1.0`. |
| `test_percentile_rank_single_day_returns_one` | A one day population returns `{date: 1.0}`. |
| `test_percentile_rank_unique_minimum_day_returns_zero` | The population has a **strictly unique** minimum. That day returns `0.0`, and `percentile_threshold(values, 0.0)` equals its `load_mwh`. **The fixture must not tie the minimum.** |
| `test_percentile_rank_tied_minimum_takes_the_last_tied_index` | A population whose `load_mwh` values are `[1, 1, 2]` at MWh scale returns `0.5` for both tied days, not `0.0`. Spike question 10 measured this. The test pins the behavior so nobody "fixes" it back into a CDF. |
| `test_percentile_rank_empty_population_raises` | `ValueError` matching `no complete .* days`, the `compute_threshold` message. |

### Phase 3 — `tests/test_scenario_input.py` (existing file, rewritten helpers, new tests)

**Refactor first, then add.** Rewrite `_rows()` (lines 15 to 25) to build each row from a dict
keyed by column name, and add a `_mutate(lines, row, column, value)` helper. That removes all 12
positional `parts[N]` sites. See risk R2.

New tests:

| Test | Asserts |
|---|---|
| `test_ts_column_required` | A header without `ts` raises, message names `ts`. |
| `test_interval_minutes_column_required` | Same for `interval_minutes`. |
| `test_naive_ts_rejected` | `ts` of `2026-01-10T00:00:00` raises, message matches `naive` and the line number. Spike question 3 proved the parse itself does not raise. |
| `test_unparseable_ts_rejected` | `ts` of `not-a-ts` raises with the line number. |
| `test_non_finite_token_in_ts_rejected` | Parametrized over `nan`, `NaN`, `inf`, `-inf`, `+inf`, `Infinity`. Each raises the `column 'ts': cannot parse` error, because `datetime.fromisoformat` rejects all six. |
| `test_blank_ts_cell_rejected` | A blank `ts` cell raises with the line number. |
| `test_non_finite_interval_minutes_rejected` | Parametrized over the same six tokens. **`nan` is the load bearing case**: spike question 8 measured that the 60 minute magnitude test alone accepts it, so this test is what forces `_parse_finite_float`. For `nan` the message must match `finite`, not `60`. |
| `test_blank_interval_minutes_cell_rejected` | A blank `interval_minutes` cell raises with the line number. |
| `test_interval_minutes_not_sixty_rejected` | `interval_minutes` of `5.0` on one row raises, naming that line and matching `60`. |
| `test_interval_minutes_accepts_sixty_as_integer_string` | `60` and `60.0` both pass. |
| `test_mixed_interval_minutes_rejected_at_the_first_bad_row` | Row 0 at `60`, row 1 at `30`, raises naming row 1. This pins the per row rule. |
| `test_hour_must_match_ts_hour` | `hour=5` with `ts` at `T06:00:00-05:00` raises. |
| `test_date_must_match_ts_local_date` | `date=2026-01-10` with `ts` at `2026-01-11T00:00:00-05:00` raises. |
| `test_ts_local_date_uses_the_stored_offset` | 24 rows with `ts` at `-05:00` and `date=2026-01-10` pass, though the UTC dates of the last five hours are 2026-01-11. Spike question 1 verified this. |
| `test_duplicate_absolute_instant_rejected` | An exact repeated row raises matching `duplicate absolute instant`. |
| `test_fall_back_hour_pair_rejected_naming_dst` | **The DST rejection test for the fall back case.** Build 24 rows for 2025-11-02 plus one extra row that repeats `hour=1` at `-05:00` while the first carries `-04:00`. Assert the message matches `daylight saving`. **Do not assert on the number 25.** The per row duplicate check fires during parse, before the row count guard, so the message names the repeated hour, not a count. Spike question 12 confirmed the count guard can never see 25. |
| `test_twenty_three_hour_day_rejected_naming_dst` | 23 rows for 2025-03-09, all distinct hours, raise a message matching both `23` and `daylight saving`. This is the one reachable DST branch of the count guard. |
| `test_truncated_day_does_not_mention_dst` | 20 rows raise a message that matches `20` and does **not** match `daylight saving`. This stops the message misleading on a truncated file. |
| `test_mixed_utc_offsets_within_a_date_rejected` | 24 rows for 2025-11-02 with hours 0 and 1 at `-04:00` and hours 2 to 23 at `-05:00`. All 24 hours are distinct, so the count guard passes and the duplicate check passes. The same offset per date rule must raise, matching `daylight saving`. **Without rule 7 this file reads as valid and is silently wrong by one hour of load.** |
| `test_single_offset_within_a_date_accepted` | 24 rows all at `-05:00` pass, so rule 7 does not false-positive. |
| `test_wind_mwh_header_rejected` | The fixture carries all five required columns **plus** `wind_mwh`, so the missing column check cannot fire. The message must match `wind_mw` and `MWh`. |
| `test_rejected_mwh_headers_parametrized` | Parametrized over `oil_mwh`, `gas_mwh`, `load_mwh`. Each fixture carries all five required columns plus the offending one. Each message names the matching `*_mw` rename. |
| `test_mwh_rejection_is_case_insensitive` | A header of `Wind_MWh` is rejected. Spike question 11 confirmed `scenario_input.py:109` lowercases, so the check must compare against the lowercased fieldmap key. |
| `test_mwh_rejection_runs_before_missing_column_check` | A header with `wind_mwh` and no `load_mw` reports the MWh message, not the missing column message. |
| `test_oil_mw_and_gas_mw_columns_accepted_and_ignored` | A file carrying `oil_mw` and `gas_mw` parses, and `DayProfile` is unaffected. |
| `test_demand_percentile_basis_banner_without_the_column_rejected` | A `# demand_percentile_basis = pooled winter complete days, n=270` line with no `demand_percentile` column raises, message matching `truncated`. |
| `test_prose_comment_mentioning_the_basis_key_does_not_trigger` | A comment line `# note: see demand_percentile_basis in the docs` has no `=`, so it is ignored and the file parses. This pins exact key comparison over substring search. |
| `test_demand_percentile_basis_banner_with_the_column_accepted` | Both present, `demand_percentile_source == "file"`. |
| `test_derived_rank_warning_names_the_population` | The warning text matches `not comparable`. |
| `test_derived_rank_still_works_on_the_example_fixture` | Read `examples/synthetic_winter_stress.csv`, assert `demand_percentile_source == "derived-rank"`, six days, and the three cold days at `1.0`. **This is the fixture regression gate.** |

Existing tests that change, named with what each asserts:

| Line | Test | What breaks and the fix |
|---|---|---|
| 15-25 | `_rows()` helper | Emits three cells. Rewrite to emit `date,hour,ts,interval_minutes,load_mw` plus extras, and to build `ts` from `date_str` and `h` at a fixed `-05:00`. |
| 32-36 | `_csv()` helper | Unchanged. |
| 44 | `test_minimal_csv_one_day_profile_no_wind` | Header literal. |
| 52 | `test_wind_mw_column_present_gives_24_wind_values` | Header literal. |
| 63 | `test_rows_shuffled_gives_same_result_as_sorted` | Two header literals. |
| 77 | `test_blank_lines_and_comments_are_skipped` | Inline header literal at line 81. Still valid after the filter change: comment lines are retained for the banner rule but never reach `csv.DictReader`. |
| 96 | `test_per_day_scalars_read_from_file` | Header literal. |
| 112 | `test_demand_percentile_absent_is_derived_via_ecdf` | Header literal. The 1/3, 2/3, 3/3 assertions stay, because the fallback arithmetic does not change. |
| 129 | `test_wind_forecast_frac_absent_defaults_to_zero` | Header literal. |
| 145-187 | four `test_non_finite_*` parametrized tests | Header literals and the `parts[2]` and `parts[3]` sites at lines 150, 161, 172, 183. |
| 195-252 | **six** blank cell tests | `test_blank_wind_mw_cell_defaults_to_zero` (195), `test_blank_demand_percentile_cell_rejected` (205), `test_blank_wind_forecast_frac_cell_rejected` (215), `test_blank_load_mw_cell_rejected` (225), `test_blank_date_cell_rejected` (235), `test_blank_hour_cell_rejected` (245). Header literals and the sites at lines 198, 208, 218, 228, 238, 248. |
| 260 | `test_missing_required_header_column_rejected` | Content `"date,hour\n..."`. Passes today by accident, because `load_mw` stays in the missing list. Rewrite to assert all three of `ts`, `interval_minutes`, `load_mw` appear in the message. |
| 266 | `test_zero_data_rows_rejected` | Header literal. |
| 272 | `test_unparseable_date_rejected` | Header literal. The date parse must stay before the `ts` parse so the message does not change. |
| 282 | `test_hour_out_of_range_rejected` | Header literal. The `0..23` range check must stay before the `ts.hour` cross check so the message does not change. |
| 292 | `test_duplicate_date_hour_pair_rejected` | Rename to `test_duplicate_row_rejected`. The appended copy now carries the same `ts`, so the message becomes `duplicate absolute instant`. Update the `match`. |
| 300 | `test_date_with_wrong_row_count_rejected` | 23 rows now trigger the DST clause. Replace with the new 23 hour and truncated tests above. |
| 307, 316 | the two `varies within date` tests | Header literals only. |
| 325 | `test_non_consecutive_dates_rejected` | Header literal. |

### Phase 4 — `examples/` and `tests/test_cli.py`

| Test | Asserts |
|---|---|
| `test_generated_fixture_round_trips_through_the_reader` (new, in `tests/test_cli.py` or a new `tests/test_examples_fixture.py`) | `read_day_profiles` on `examples/synthetic_winter_stress.csv` returns six consecutive days, 24 hours each, `has_wind is True`. |
| `_check_invariants` in `examples/make_synthetic_winter_stress.py` (new assertions) | Every generated `ts` carries a UTC offset, every offset is exactly `-05:00`, `ts.hour == h`, and `ts.date() == d.date`. Spike finding B shows why the offset assertion matters. |
| `tests/test_cli.py:511` `test_malformed_csv_exits_two` (existing) | Content becomes a full five column header with one bad `date` cell, so the test keeps proving what its name says. It would still exit 2 without the edit, but for the wrong reason. |
| `tests/test_cli.py` other tests using `EXAMPLE` at line 22 (existing) | Must pass **unchanged**. The fixture's numbers do not move, only its columns. This is the proof that the format change is behavior neutral. |
| `tests/test_peak_window.py:18` `EXAMPLE` (existing) | Must pass unchanged. Run it and confirm; do not edit it speculatively. |

### Phase 5 — `tests/test_etl_profile_csv.py` (new)

| Test | Asserts |
|---|---|
| `test_round_trip_through_read_day_profiles` | Write 24 `ProfileRow` objects for one date to a real file under `tmp_path`, then open it with `open(path, encoding="utf-8", newline="")` and read it with `read_day_profiles`. Assert one day, 24 hours, matching loads. **Read from a real file, never a StringIO**, so the mixed `\n` banner and `\r\n` row endings are exercised. Spike question 4 and spike 3 part B both confirm this parses. **This is the load bearing test of the whole plan.** |
| `test_round_trip_preserves_wind_and_demand_percentile` | Optional columns survive, `demand_percentile_source == "file"`, `has_wind is True`. |
| `test_banner_lines_precede_the_header_and_start_with_hash` | Read the raw bytes and assert order and prefixes. |
| `test_units_banner_names_average_mw_and_the_fraction_rule` | The `# units` line matches `average MW` and `fractions in [0, 1]`. |
| `test_banner_values_are_redacted` | With a fake `EIA_API_KEY` in `getenv` and the key inside a `derived_from` path, the written file holds `***REDACTED***` and not the key. |
| `test_banner_value_with_a_newline_raises` | `ProfileCsvError`. This closes header injection. Parametrize over `\n` and `\r`, and over a key holding `=`. |
| `test_optional_column_omitted_when_every_row_is_none` | A file with no wind carries no `wind_mw` column. |
| `test_optional_column_emitted_when_any_row_has_a_value` | One non `None` value emits the column, and the `None` rows write an empty cell. |
| `test_oil_and_gas_are_never_emitted_by_the_etl_path` | With all rows `None`, the header carries neither. |
| `test_naive_ts_raises` | `ProfileCsvError`. |
| `test_hour_ts_mismatch_raises` | `ProfileCsvError`. |
| `test_date_ts_mismatch_raises` | `ProfileCsvError`. |
| `test_writer_does_not_guard_file_level_shape` | Write 23 rows for one date. `write_profile_csv` **succeeds**, and `read_day_profiles` on the result **raises**. This pins the accurate division of responsibility in b.2 rule 8 and stops a later reader assuming the writer guarded it. |
| `test_hour_is_written_as_an_integer` | The raw text holds `,0,` and not `,0.0,`. Spike question 4 measured this. |
| `test_column_order_follows_profile_columns` | Header order is exact. |

### Phase 6 — `tests/test_etl_cli_transform.py` (existing file, new tests)

| Test | Asserts |
|---|---|
| `test_profile_out_writes_a_readable_file` | Build a 3 day fixture with `write_rows_csv`, run `etl transform --profile-out`, then read the output with `read_day_profiles`. Three days, 24 hours each. **End to end proof.** |
| `test_profile_out_writes_demand_percentile_from_the_pooled_population` | The written `demand_percentile` for each date equals `percentile_rank_within(...)` for that date, and the banner `demand_percentile_basis` names the same `n`. |
| `test_profile_out_omits_wind_forecast_frac_and_the_reader_warns` | `wind_forecast_frac_source == "default-zero"`. |
| `test_profile_out_refuses_the_fall_back_day` | A fixture spanning 2025-11-02 at 60 minute grain, with hour 1 present at both `-04:00` and `-05:00`. Exit 2. The message names the date and matches `daylight saving`. The two hour bucket triggers the naming, not a count of 25, because the bucket count is 24. |
| `test_profile_out_refuses_the_spring_forward_day` | A fixture spanning 2025-03-09 with the skipped hour absent gives 23 buckets. Exit 2, message names the date and matches `daylight saving`. |
| `test_profile_out_refuses_an_incomplete_ordinary_day` | A winter date missing one hour exits 2, and the message does **not** match `daylight saving`. |
| `test_profile_out_refusal_names_the_range_exclusion` | The refusal message tells the operator to choose a range that ends before or starts after the transition date. It must not say "stay inside a single season". |
| `test_profile_out_refuses_non_consecutive_dates` | Exit 2. |
| `test_profile_out_refuses_an_out_of_season_date` | A summer date under `--season winter` exits 2. |
| `test_profile_start_and_end_filter_the_export` | A 5 day input with a 3 day range writes 72 rows. |
| `test_profile_start_without_profile_out_exits_two` | Exit 2. |
| `test_wind_input_joins_wind_into_the_profile` | A wind rows CSV at hourly grain produces a `wind_mw` column that `read_day_profiles` reports as `has_wind is True`, with matching values. |
| `test_wind_input_ignores_forecast_rows` | The wind fixture carries a realized row (`horizon_days=0`) and a forecast row (`horizon_days=1`) at the **same** `ts` with a different `gen_mw`. The written `wind_mw` equals the realized value. Without the filter the forecast row overwrites it, or `hourly_from_readings` raises on the duplicate instant; either way this test catches it. |
| `test_wind_input_at_utc_offset_joins_correctly` | The wind fixture stores `ts` at `+00:00` while the load fixture stores `-05:00`. The join still lands on the right hour, because aware datetimes compare by instant. |
| `test_wind_input_with_a_gap_exits_two` | A missing wind hour exits 2 naming the hour, not a silent zero. |
| `test_wind_input_at_thirty_minute_spacing_exits_two` | `check_hourly_spacing` surfaces as exit 2. |
| `test_wind_input_without_profile_out_exits_two` | Exit 2. |
| every existing test in the file (existing) | Must pass unchanged. `--profile-out` defaults to `None`. |

---

## (d) Shared file change list

No phase owns these files. The orchestrator applies every change below after phase 6, in one
commit, and then reruns the full suite.

**Files no builder may touch, with the required change:**

| File | Required change |
|---|---|
| `pyproject.toml` | **No change.** `dependencies = []` stays empty. Everything here is stdlib. |
| `uv.lock` | **No change.** |
| `src/owr/__init__.py` | **No change.** `hourly` and `profile_csv` are not public engine surface. |
| `src/owr/etl/__init__.py` | **No change.** Its `__all__` stays `["Provenance"]`. |
| `tests/conftest.py` | **Does not exist. Do not create one.** |
| `db/migrations/` | **No change.** No migration 004. |
| the repo map | Add two rows to the ETL table: `hourly.py` \| `Interval readings to one average MW value per local hour. Pure, mirrors daily.py.` and `profile_csv.py` \| `Writes the hourly scenario profile CSV, banner plus rows. Mirrors rows_csv.py.` Change the `scenario_input.py` row to: `Hourly scenario profile CSV reader for the simulator CLI. 24 hour days only.` |
| `README.md` lines 76 to 81 | Replace the "provisional" paragraph. The format is now defined once and written by `etl transform --profile-out`. Name the required columns and the average MW unit. |
| `docs/HANDOFF.md` line 43 | Re-baseline the byte identical row. The command does not change. Record the new line count and the date of the re-baseline. |
| `docs/DATA_SOURCES.md` | Add a section for the profile format: the column list, the average MW unit, the fraction unit for `demand_percentile` and `wind_forecast_frac` against Component 2's `%`, the two upstream sources (`gridstatus.isone.load` and `eia930.isne.wind`), the `demand_percentile` definition with a pointer to `percentile_rank_within`, and the note that `wind_forecast_frac` is never written. |
| `docs/BOARD.md` | One status row for this workstream. |

**Files a phase owns, listed here only so the boundary is unambiguous:** `src/owr/etl/hourly.py`,
`src/owr/etl/profile_csv.py`, `src/owr/etl/transform.py`, `src/owr/etl/cli.py`,
`src/owr/scenario_input.py`, `src/owr/cli.py`, `examples/make_synthetic_winter_stress.py`,
`examples/synthetic_winter_stress.csv`, and the six test files named in section (c).

---

## Phases and verification

The suite is **red between phase 3 and phase 4**, because the reader requires columns the fixture
does not yet carry. Phases 3 and 4 land in one commit. Do not stop between them.

| # | Goal | Files | Verify | Time |
|---|---|---|---|---|
| 0 | Team notification on the unit decision | none | The message is sent | 10 min |
| 1 | Hourly integration | `src/owr/etl/hourly.py`, `tests/test_etl_hourly.py` | `uv run pytest tests/test_etl_hourly.py` | 45 min |
| 2 | Pooled percentile rank | `src/owr/etl/transform.py`, `tests/test_etl_transform.py` | `uv run pytest tests/test_etl_transform.py` | 35 min |
| 3 | Reader | `src/owr/scenario_input.py`, `tests/test_scenario_input.py` | `uv run pytest tests/test_scenario_input.py` | 65 min |
| 4 | Fixture and simulator CLI text | `examples/make_synthetic_winter_stress.py`, `examples/synthetic_winter_stress.csv`, `src/owr/cli.py`, `tests/test_cli.py` | `uv run pytest` **fully green** | 25 min |
| 5 | Writer | `src/owr/etl/profile_csv.py`, `tests/test_etl_profile_csv.py` | `uv run pytest tests/test_etl_profile_csv.py` | 55 min |
| 6 | ETL CLI wiring | `src/owr/etl/cli.py`, `tests/test_etl_cli_transform.py` | `uv run pytest` **fully green** | 60 min |
| 7 | Shared files | Section (d) | `uv run pytest` and `uv run ruff check .` | 15 min |

Phase 0 blocks the merge of phase 3, not the start of phases 1 and 2.

Run `uv run ruff check .` after every phase. Line length is 100.

Final acceptance, all four commands:

```bash
uv run pytest                                              # expect 323 + new, 3 skipped
uv run ruff check .                                        # expect All checks passed
uv run simulate --input examples/synthetic_winter_stress.csv --storage-mwh 20000 --power-mw 2000
uv run python examples/make_synthetic_winter_stress.py && git diff --exit-code examples/synthetic_winter_stress.csv
```

The fourth command must exit 0 after the re-baseline in section 7.

---

## Section 7 — the example fixture migration and re-baseline

`docs/HANDOFF.md:43` records this invariant: run the generator, then
`git diff --exit-code examples/synthetic_winter_stress.csv` exits 0. This work changes the file
once, on purpose. Re-baseline it inside phase 4, in this order.

1. Change `BANNER_LINES` in `examples/make_synthetic_winter_stress.py` to add four lines:
   `# scenario_profile = v1`, `# schema_version = 1`, the `# units` line from b.2, and
   `# local_timezone = America/New_York`. Keep the two existing lines.
2. **Do not add a git sha, a timestamp, or an absolute path to the synthetic banner.** Any value
   that changes between runs breaks the byte identical check at step 7. The generator must not
   call `owr.version.code_version()`, `datetime.now`, or `os.getcwd`.
3. **Do not add a `demand_percentile_basis` line.** The fixture has no pooled population, and the
   b.3 banner rule raises when that key appears without the column. The demo depends on the derived
   rank path.
4. Change `render_csv` at line 135 to emit the header
   `date,hour,ts,interval_minutes,load_mw,wind_mw` and to write `ts` and `60.0` on each row. Build
   `ts` as `datetime.combine(d.date, time(h), tzinfo=ZoneInfo("America/New_York")).isoformat()`.
   `zoneinfo` is stdlib and `examples/` is not engine core, so this breaks no purity rule.
5. Add the offset assertions to `_check_invariants` per phase 4 of section (c).
6. Run `uv run python examples/make_synthetic_winter_stress.py`. Run
   `git diff --stat examples/synthetic_winter_stress.csv` and read the diff by eye. Expect 144 data
   rows unchanged in count and unchanged in every load and wind number, 4 new banner lines, and 2
   new cells per row. Record the measured line count; the arithmetic predicts 151.
7. Run the generator a **second** time, then run
   `git diff --exit-code examples/synthetic_winter_stress.csv`. It must exit 0. That is the
   re-baselined invariant.
8. Commit the generator change and the regenerated CSV together, in one commit.
9. Update `docs/HANDOFF.md:43` in phase 7 with the new line count and the re-baseline date.

The tie the demo depends on does not move. `COLD_DAY_TOTAL_MWH = 216000.0` at line 45 and every
load value stay exactly as they are, so `find_stress_windows` still returns one 3 day window and
`tests/test_cli.py` golden output is unchanged.

---

## Risks, ranked

**R1. An unfiltered export cannot produce a readable file, and a range across a transition is
inexpressible.** `data/load_2025.csv` holds a 23 hour day (2025-03-09, 276 intervals) and a 25 hour
day (2025-11-02, 300 intervals), both measured. A whole year export therefore contains a date the
reader rejects, and the whole file fails. **The stronger statement, which the refusal message must
carry:** because the reader requires consecutive dates and 24 hour days, **no** date range that
contains a transition date can be exported at all. The operator must choose a range that ends
before the transition or starts after it. Advice to "stay inside a single season" is wrong for a
shoulder study, which is why the message states the exclusion instead.
*Mitigation:* `--profile-start` and `--profile-end`, plus the write time refusal in b.5 rule 5.
*Detection:* the four refusal tests in phase 6.

**R2. Positional index churn in `tests/test_scenario_input.py`.** Twelve sites index a row by
position (`parts[2]`, `parts[3]`). Inserting `ts` and `interval_minutes` shifts `load_mw` from
index 2 to 4 and the extras from 3 to 5. A missed site mutates the wrong column, and the test
still passes for the wrong reason, because most of these tests only assert that **some** error
fires at line 2. *Mitigation:* remove positional indexing entirely. Rewrite `_rows()` to build a
dict per row and add `_mutate(lines, row_index, column_name, value)`. Do this refactor **before**
adding any new test. *Detection:* after the refactor, no `parts[` remains in the file; grep for it.

**R3. The byte identical fixture check breaks on any nondeterministic banner value.** *Mitigation:*
section 7 steps 2 and 3 forbid three specific calls and one banner key. *Detection:* section 7 step
7 runs the generator twice.

**R4. The research's `demand_percentile` identity claim is false under the plain CDF.** Measured:
5,777 mismatches in 21,000 trials, reproduced independently by the review. Anyone implementing the
research text literally ships a column that disagrees with the threshold on about a quarter of
percentile choices. *Mitigation:* the inverse interpolation definition in b.4. *Detection:* the
grid property test in phase 2, plus the tied minimum test that stops a later revert to the CDF.

**R5. Two `demand_percentile` definitions coexist and can never agree numerically.** The ETL writes
a pooled seasonal rank over `n` around 270. The reader's fallback computes a file local rank over
`n` equal to the file's day count. A six day file has no pooled population, so the two cannot
agree. *Mitigation:* keep the fallback arithmetic exactly as it is, label it through the existing
`demand_percentile_source` field, and extend the warning to say the values are not comparable.
Changing the fallback arithmetic would move `priority()` on every mild day and would perturb the
existing simulator tests, for no gain. *Detection:* the fixture regression test in phase 3.

**R6. Mixed line endings in the written file.** The banner uses `\n` and `csv.writer` uses `\r\n`.
*Mitigation:* this is exactly what `rows_csv.write_rows_csv` already produces and
`read_rows_csv` already consumes, so the pattern is proven in the current suite. Spike 3 part B
read a real mixed file through `read_day_profiles` successfully. *Detection:* the round trip test
in phase 5 reads from a real file on disk, never a `StringIO`.

**R7. No wind data exists on disk, and `$EIA_API_KEY` is unset.** `--wind-input` ships fixture
tested only. `data/` holds five load CSV files and no wind file. *Mitigation:* build the wind
fixture with `write_rows_csv` and `DATASETS["wind"]`, exactly as the existing transform tests build
load fixtures, and cover the forecast row, the offset and the spacing cases named in b.5 rule 8.
*Consequence:* the live EIA path stays unproven, which matches finding RU1 in the research.

**R8. `wind_forecast_frac` is never written.** Every profile the ETL produces triggers the
default zero warning, and `priority()` reduces to `0.7 * demand_percentile`. That matches today's
behavior and is out of scope here. Record it in `docs/DATA_SOURCES.md`.

**R9. The format cannot carry a sub hourly profile.** `interval_minutes` must equal 60. This is
deliberate: the engine takes 24 values per day (`models.py:76-79`) and the wire contract at
`api/schemas.py:15,50` pins the same number. Relaxing it later needs a format change.

**R10. `data/` is gitignored, so the real data test can be skipped in continuous integration.**
The daily equals sum of hourly test in phase 1 needs `data/load_2025.csv`. *Mitigation:* skip with
an explicit reason when the file is absent, and add the second, self contained version of the same
identity test over a synthetic 288 interval day so the invariant is always covered.

**R11. The team may reject the MW decision after phase 0.** The plan resolves a disagreement inside
the team's own document. If the team insists on MWh, the reader's rejection rule flips into a
conversion rule and the undetectable factor of 24 returns. *Mitigation:* phase 0 sends the message
before phase 3 merges, so a reversal costs one file rather than the whole chain. *Consequence if it
happens:* re-open open item 2 only. Nothing else in the plan depends on it.

---

## Assumptions

1. The study window never crosses a DST transition. `docs/HANDOFF.md:394` sets the MVP v1.0 data
   scope at five winters, December 1 to February 28 or 29, which excludes March, and 15 U.S.C. 260a
   puts every transition in March or November. If that changes, the guard becomes a blocker and
   `DayProfile` must generalize across eight modules.
2. `DayProfile.load_mwh` means a sum of average MW values over 24 one hour periods
   (`models.py:81-84`). The whole unit decision rests on that reading.
3. `oil_mw` and `gas_mw` stay reserved names. Populating them needs migration 004, because
   `db/migrations/001_init.sql:36-46` keys `raw.hourly_wind` on `(source, ts, horizon_days)` with
   no fuel column.
4. The team accepts the MW choice and the `*_mwh` rejection. Phase 0 asks before phase 3 merges,
   so this is a pending answer rather than a silent assumption. See open item 2 and risk R11.
