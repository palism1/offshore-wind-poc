# Plan — Real-Data Demo Bridge — 2026-08-05 (revision 1)

Target date: Friday 2026-08-07. Estimated cost: half a working day.

Revision 1 answers the adversarial review of revision 0. See the revision log at the
end for each disposition.

## Goal

Make this command run on a real Independent System Operator New England (ISO-NE)
stress event:

```
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 4320
```

The command must use no flags beyond the three above. The synthetic demo must keep
working, unchanged.

## This bridge is disposable, and it has a death date

`docs/PLAN_SCENARIO_PROFILE_FORMAT.md` section b.3 makes `ts` and
`interval_minutes` **required** columns of the day-profile format. This bridge emits
`date,hour,load_mw,demand_percentile` only. On the day that redesign lands, the
reader rejects `examples/real_winter_stress_2026.csv`, and the README quickstart
command added in Phase 4 breaks.

That redesign's phase 4 regenerates `examples/synthetic_winter_stress.csv` only. Its
file list does not name this artifact. Its track A also plans
`src/owr/etl/hourly.py` and `src/owr/etl/profile_csv.py`, which overlap what this
bridge builds, and it extends `etl transform` with `--profile-out`,
`--profile-start` and `--profile-end` rather than adding a subcommand.

Two consequences the implementer must record, not solve:

1. **Only the data holder can regenerate the artifact.** `data/` is gitignored and
   lives on one machine. A rebuild needs those files. Nobody else can run the
   generator, in continuous integration or anywhere else.
2. **The format redesign must regenerate or retire two items**:
   `examples/real_winter_stress_2026.csv` and `src/owr/etl/demo_profile.py` with its
   `etl demo-profile` subcommand and its two test files.

Phase 4 records both in `docs/HANDOFF.md`. **Do not edit
`docs/PLAN_SCENARIO_PROFILE_FORMAT.md`.** It waits at a human gate.

The module is named `demo_profile.py` and the subcommand `demo-profile` for this
reason. The name states that the code is a bridge, keeps it clear of the redesign's
planned `profile_csv.py`, and makes a later retirement one `grep` away.

## What real data exists (measured 2026-08-05)

| Path | Content | State |
|---|---|---|
| `data/load_2023.csv` | ISO-NE five-minute system load, 2023-06-30 to 2023-12-31 | gitignored, 53,049 rows |
| `data/load_2024.csv` | Same feed, full year 2024 | gitignored, 105,406 rows |
| `data/load_2025.csv` | Same feed, full year 2025 | gitignored, 105,120 rows |
| `data/load_2026.csv` | Same feed, 2026-01-01 to 2026-07-29 | gitignored, 60,468 rows |
| `data/load_2022.csv` | Header only, zero rows | gitignored |
| `data/daily_stress_events_team.csv` | A teammate's event list | gitignored, not used here |

Provenance on every row: `source = gridstatus.isone.load`,
`dataset_version = gridstatus==0.36.0`, `retrieved_at` in 2026-07-30. The four
non-empty files carry four different `retrieved_at` instants, minutes apart.

The repository **does** hold real hourly load. The five-minute feed integrates to
exact hourly energy. No intraday shape is needed, and none is applied.

A read-only check on 2026-08-05 fed all 324,043 readings through
`owr.etl.daily.daily_loads_from_readings` and reproduced the recorded figures: 270
complete winter days, p90 (90th percentile) = 385832.584 megawatt hours per day.
That agrees with `docs/HANDOFF.md` to 3 decimals, which is the precision the ETL
command line interface (CLI) prints. The full float can differ in the last digit
with summation order: this run measured `385832.5839166666` where an earlier run
measured `...67`.

The target window is the recorded 11-day event, **2026-01-24 to 2026-02-03**. All
11 days carry 288 intervals and 24.0 hours. No daylight saving time (DST)
transition falls inside the window.

## What is real and what is absent

**Real, no transformation beyond integration.** `load_mw` per clock hour is the
integral of the five-minute ISO-NE readings over that America/New_York wall-clock
hour. One value per hour. No interpolation, no scaling, no smoothing.

**Real, derived by the documented rule.** `demand_percentile` per day is the
empirical rank of the day's total against the pooled complete winter days in the
inputs: `count(load_mwh <= x) / N`, with `N = 270`. This is the same formula
`owr.scenario_input` uses for its derived rank, over the same population
`owr.etl.transform.compute_threshold` filters.

**Absent, and left absent.** `wind_mw`. The repository holds no real ISO-NE or
Energy Information Administration (EIA) wind series. The EIA extractor is built but
has never run, because `$EIA_API_KEY` does not exist. The teammate file carries a
`total_wind` column per event, but only as an event aggregate, on a load series
about five times smaller than ours, so it cannot produce an hourly series.

There is no real wind total to shape, so the plan shapes nothing. The generator
emits no `wind_mw` column. **Do not add a synthetic wind column.**

Consequence, stated up front so the demo narrator is not surprised: with no wind,
`owr.simulator` charges zero every hour. The state of charge falls monotonically,
`recharge_sufficiency_ratio` reads 0.000 on every day but the last, and the peak
reduction is about 1.1%. That result is truthful. It shows a 60 gigawatt hour
reserve that survives an 11-day event without recharge and shaves about 214
megawatts off the worst hour.

## Design decision

Add an `etl demo-profile` subcommand plus one new pure module. Do **not** add a
script under `examples/`.

Reason: the work is interval integration, timezone handling, DST rejection and
season filtering. `src/owr/etl/` already owns all four, with tests. A script under
`examples/` would duplicate that logic where no test file mirrors it, which breaks
the repository convention that tests mirror module names one to one.

One new module, not two. `hourly_loads_from_readings` and
`render_day_profile_csv` are only ever used together in this bridge. The module
docstring must name `docs/PLAN_SCENARIO_PROFILE_FORMAT.md` as the work that
supersedes it.

## Phase 1 — the pure module

**New file:** `src/owr/etl/demo_profile.py`. Pure. No file access, no network, no
database. `pandas` allowed, plain Python is fine here.

```python
@dataclass(frozen=True)
class HourlyLoad:
    date: date           # LOCAL calendar date
    hour: int            # 0..23, local clock hour
    load_mwh: float      # integral of load_mw over the hour
    hours_covered: float
    intervals: int


def hourly_loads_from_readings(
    readings: list[IntervalReading],
    *,
    tz: ZoneInfo = EASTERN,
) -> list[HourlyLoad]: ...


def percentile_ranks(
    population_mwh: Sequence[float],
    day_totals: Mapping[date, float],
) -> dict[date, float]: ...


def render_day_profile_csv(
    hourly: Sequence[HourlyLoad],
    *,
    demand_percentile: Mapping[date, float],
    banner: Sequence[str],
) -> str: ...
```

Rules for `hourly_loads_from_readings`, copied from `owr.etl.daily`:

1. Energy is an integral: `load_mwh = Sum(load_mw * interval_hours)`. Never a count.
2. Group on `reading.ts.astimezone(tz)`, then on `(date, hour)` of the local time.
3. Reject a naive timestamp. Name the timestamp in the message.
4. Reject a duplicate absolute instant. Name the timestamp in the message.
5. Attribute an interval wholly to the local hour of its start.
6. Return the list sorted by `(date, hour)`.
7. Return an empty list for empty input.

Rules for `percentile_ranks`:

8. Return `count(p <= v) / len(population_mwh)` for each day total `v`.
9. Raise `ValueError` on an empty population.
10. **The caller must pass the day total that the population itself holds.** Never
    a total recomputed from the hourly rollup. The two summation orders differ by
    about 1e-9, which is enough to drop a day below its own population value and
    cost it one rank step. Measured 2026-08-05: 2026-01-31 scored 261 instead of
    262 under a recomputed total. Phase 2 step 7 enforces this.

Rules for `render_day_profile_csv`:

11. Write each banner line with a leading `# `. Write the banner before the header.
12. Write the header `date,hour,load_mw,demand_percentile`. Emit no other column.
13. Write `load_mw` with 3 decimals. The ISO-NE feed carries 3 decimals.
14. Format the day's `demand_percentile` once, to 6 decimals. Write the same token
    on all 24 rows of that day. The reader rejects a value that varies within a date.
15. Raise `ValueError` if a date does not carry exactly the 24 hours 0 to 23.
16. Raise `ValueError` if any hour has `hours_covered` outside 1.0 +/- 0.01.
17. Blame daylight saving time in the message under two conditions only: a date with
    23 hour buckets, or a bucket covering about 2.0 hours. Those are the spring
    forward and fall back signatures. Any other shortfall, such as a bucket at
    0.9167 hours from one lost five-minute interval, reports a plain coverage gap
    with the date, the hour and the covered hours, and says nothing about DST.
18. Raise `ValueError` if the dates are not consecutive. Name both dates.
19. Raise `ValueError` if a date has no entry in `demand_percentile`.
20. Write no timestamp and no git revision. The committed artifact must stay byte
    stable, so a regeneration diff shows data changes only.

**New test file:** `tests/test_etl_demo_profile.py`.

| # | Test | Asserts |
|---|---|---|
| 1 | 12 five-minute readings in one hour | `load_mwh == pytest.approx(mean(mw))`, `hours_covered == 1.0`, `intervals == 12` |
| 2 | Mixed widths in one hour (one 30-minute plus six 5-minute) | The integral, not the mean, within `pytest.approx` |
| 3 | A reading at `2026-01-24T05:00:00+00:00` | Lands on local date 2026-01-24, hour 0 |
| 4 | Naive timestamp | Raises, message names the timestamp |
| 5 | Duplicate absolute instant | Raises, message names the timestamp |
| 6 | Empty input | Returns `[]` |
| 7 | `percentile_ranks` over `[1, 2, 3, 4]` | Rank of 3 is 0.75, rank of 4 is 1.0 |
| 8 | `percentile_ranks` where the day total is the population maximum | Rank is exactly 1.0. This pins rule 10 |
| 9 | Render two full days | Banner lines start with `#`, header exact, 48 data rows |
| 10 | Render output through `scenario_input.read_day_profiles` | Parses, `demand_percentile_source == "file"`, `has_wind is False` |
| 11 | Same round trip | Each `DayProfile.load_mwh` matches the daily integral within 0.02 |
| 12 | Render a 23-hour date | Raises, message names the date and daylight saving time |
| 13 | Render a date whose hour 1 covers 2.0 hours | Raises, message names daylight saving time |
| 14 | Render a date whose hour 4 covers 0.9167 hours | Raises, message names the gap and **does not** mention daylight saving time |
| 15 | Render non-consecutive dates | Raises, message names both dates |
| 16 | Render output | Contains no `wind_mw` token anywhere |

Tests 14 and 16 are guards. Test 14 stops a misleading DST message on an ordinary
gap. Test 16 stops a later change from adding a shaped wind column without a
decision.

Never assert exact float equality on a value that two summation orders can produce.
Use `pytest.approx`, or pick fixture values that are exact in binary.

**Verify:** `uv run pytest tests/test_etl_demo_profile.py` and `uv run ruff check .`.

## Phase 2 — the `etl demo-profile` subcommand

**Change:** `src/owr/etl/cli.py`. Add `cmd_demo_profile` and the `demo-profile`
subparser. Mirror `cmd_transform` exactly: an injected
`open_input: Callable[[str], TextIO]` defaulting to `open`, and a wrapper that turns
`OSError` and `ValueError` into `error: ...` on stdout with exit code 2.

Arguments:

| Flag | Type | Default | Meaning |
|---|---|---|---|
| `--input` | path, repeatable, required | none | A rows CSV from `etl extract --out`. All inputs pool. |
| `--start` | date, required | none | First local calendar date, inclusive. |
| `--end` | date, required | none | Last local calendar date, inclusive. |
| `--out` | path, required | none | Where to write the day-profile CSV. |
| `--season` | choice, same list as `transform` | `winter` | The population for `demand_percentile`. |

Help text on `--start` must point at `etl transform`, which reports the event dates.
Help text on the subcommand must say that the format redesign supersedes it.

Order of work inside `_run_demo_profile`:

1. Read every `--input` through `read_rows_csv(stream, DATASETS["load"], origin=path)`.
2. Skip a file with zero data rows. Print the skip note to stderr, as `transform` does.
3. Build `IntervalReading` values with the existing `_reading_from_row`.
4. Collect the distinct `(source, dataset_version, source_query, retrieved_at)`
   tuples from the raw rows, sorted. These become banner lines.
5. Build the population: `daily_loads_from_readings` -> `daily_frame` ->
   `add_season_columns`, then keep rows where `season == args.season` and
   `complete` is true. Raise `ValueError` on an empty population.
6. Reject the run if any date in `[--start, --end]` is missing from that population.
   Name the first offending date. This keeps the rank semantics clean: every emitted
   day is a member of its own population.
7. Take each selected day's total **from the population frame built in step 5**.
   Pass those floats to `percentile_ranks`. Never recompute a day total from the
   hourly rollup for this purpose. Phase 1 rule 10 gives the measurement.
8. Roll the readings up with `hourly_loads_from_readings`, then keep the entries
   inside `[--start, --end]`.
9. Render, then write the text to `--out` with `newline=""` and UTF-8.
10. Print a 5-line summary to stdout.

Banner lines the command must emit, in this order:

```
Real ISO-NE day-profile input for the simulator CLI. Generated, do not hand-edit.
Superseded by docs/PLAN_SCENARIO_PROFILE_FORMAT.md when that format lands.
Generated by: etl demo-profile --input <each input> --start <s> --end <e> --out <path>
REAL  load_mw: ISO-NE system load, five-minute feed, integrated to hourly energy
      over America/New_York wall-clock hours. No interpolation, no scaling.
REAL  demand_percentile: empirical rank of the day total against the pooled
      complete <season> days in the inputs, N = <count>: count(load_mwh <= x) / N.
      The per-season population choice is an open question (docs/HANDOFF.md).
ABSENT wind_mw: no real ISO-NE or EIA wind series exists in this repository. The
      EIA extractor has never run. No wind column is emitted and none is shaped.
      The engine therefore models zero recharge across this window.
NOTE  simulate recomputes its own percentile from this file alone. At the default
      --severity-percentile 0.90 it reports no window inside a short file. Pass
      --severity-percentile 0 to see the whole file as the one event.
source = <value>  dataset_version = <value>  retrieved_at = <value>
source_query = <value>
source = <value>  dataset_version = <value>  retrieved_at = <value>
source_query = <value>
... one pair per distinct provenance tuple ...
```

The four non-empty input files carry four different `retrieved_at` instants, so the
real run emits four such pairs. Emit them sorted, so the output stays byte stable.

**New test file:** `tests/test_etl_cli_demo_profile.py`. Build fixtures with
`write_rows_csv`, exactly as `tests/test_etl_cli_transform.py` does.

| # | Test | Asserts |
|---|---|---|
| 1 | End to end over a 10-day winter fixture | Exit 0, the output file parses through `read_day_profiles` |
| 2 | Known daily totals | The emitted `demand_percentile` equals `count(<=)/N` by hand |
| 3 | The highest day in the fixture | Emits `demand_percentile` exactly `1.000000`. This pins step 7 |
| 4 | Missing input file | Exit 2, stdout starts with `error:`, no traceback |
| 5 | `--start` after `--end` | Exit 2 |
| 6 | A selected date with 23 hours | Exit 2, the message names the date |
| 7 | A selected date outside the season population | Exit 2, the message names the date |
| 8 | Header-only input file | Skip note on stderr, the run still succeeds |
| 9 | Two input fixtures with different provenance | The banner carries both pairs, sorted |
| 10 | Two runs over the same fixture | Produce byte-identical output |

**Verify:** `uv run pytest tests/test_etl_cli_demo_profile.py` and
`uv run ruff check .`.

## Phase 3 — generate and commit the artifact

Run:

```
uv run etl demo-profile \
  --input data/load_2023.csv --input data/load_2024.csv \
  --input data/load_2025.csv --input data/load_2026.csv \
  --start 2026-01-24 --end 2026-02-03 \
  --out examples/real_winter_stress_2026.csv
```

`.gitignore` carries `*.csv` with a `!examples/*.csv` exception, so the artifact
commits. Expect 264 data rows and about 10 kilobytes.

Expected values, measured 2026-08-05 through
`owr.etl.daily.daily_loads_from_readings` and `owr.simulator.simulate`. A mismatch
beyond the stated tolerance is a defect. Investigate before you ship.

The **population total** column is the raw integral, the value step 7 ranks against.
The **emitted sum** column is the sum of the 24 rendered 3-decimal cells, which is
what `DayProfile.load_mwh` returns. The two differ by up to 0.005 MWh, from rounding
alone.

| Date | Population total MWh | Rank count | demand_percentile | Emitted sum MWh | Hourly peak MW |
|---|---|---|---|---|---|
| 2026-01-24 | 400953.680 | 254 | 0.940741 | 400953.680 | 19769.385 |
| 2026-01-25 | 429967.417 | 269 | 0.996296 | 429967.418 | 20126.584 |
| 2026-01-26 | 407627.359 | 259 | 0.959259 | 407627.357 | 19394.670 |
| 2026-01-27 | 418721.237 | 267 | 0.988889 | 418721.234 | 19554.613 |
| 2026-01-28 | 418248.795 | 266 | 0.985185 | 418248.799 | 19409.919 |
| 2026-01-29 | 418222.973 | 265 | 0.981481 | 418222.972 | 19449.109 |
| 2026-01-30 | 430209.088 | 270 | 1.000000 | 430209.085 | 19862.469 |
| 2026-01-31 | 412529.662 | 262 | 0.970370 | 412529.661 | 18914.085 |
| 2026-02-01 | 409280.955 | 261 | 0.966667 | 409280.954 | 19346.375 |
| 2026-02-02 | 398796.728 | 253 | 0.937037 | 398796.728 | 18702.139 |
| 2026-02-03 | 385833.412 | 244 | 0.903704 | 385833.411 | 18320.198 |

Expected simulator output, read from `--format json`, tolerance +/- 0.01:

| JSON field | Expected |
|---|---|
| `input.days_read` | 11, 2026-01-24 to 2026-02-03 |
| `input.has_wind` | `false` |
| `input.demand_percentile_source` | `"file"` |
| `summary.baseline_peak_mw` | 20126.584 |
| `summary.reserve_peak_mw` | 19912.576 |
| `summary.severity_reduction` | 0.010633 |
| `summary.energy_discharged_mwh` | 40729.644 |
| `summary.energy_charged_mwh` | 0.0 |
| `summary.final_soc` | 19270.356 |
| `summary.min_soc_mwh` | 18000.0 |
| `summary.equivalent_full_cycles` | 0.678827 |
| `stress_windows` | `[]` at the default `--severity-percentile 0.90` |

The default table renderer prints comma-grouped integers, so read those values from
the JSON. The table shows: baseline peak `20,127 MW`, reserve peak `19,913 MW`,
severity reduction `1.1%`, final state of charge `19,270 MWh` against a protected
floor of `18,000 MWh`, energy discharged `40,730 MWh`, energy charged `0 MWh`,
equivalent full cycles `0.679`.

The five-minute peak for the window is 20167.019 MW. Hourly integration lowers the
observed peak to 20126.584 MW, a drop of 0.2%. State that when you present the
number.

## Phase 4 — documents

1. the repo map: add a row to the ETL table for `demo_profile.py`. One line, matching
   the style of its neighbours, and naming the module as a bridge.
2. `README.md`: add the real-data command under Quickstart, beside the synthetic
   one. Add one sentence in the `examples/` layout note that names the file, names
   the event dates, says the wind column is absent, and says the file needs
   regeneration when the profile format changes.
3. `docs/DATA_SOURCES.md`: no change. The source is already registered.
4. `docs/HANDOFF.md`: add these three items under the open questions for the format
   redesign. Exact content, wording free:
   - The format redesign's phase 4 file list must grow by
     `examples/real_winter_stress_2026.csv`. That plan currently regenerates
     `examples/synthetic_winter_stress.csv` only, so the real artifact would fail
     the new reader with no owner assigned.
   - `src/owr/etl/demo_profile.py`, the `etl demo-profile` subcommand and the two
     test files are superseded by that plan's `hourly.py` and `profile_csv.py`.
     Retire or absorb them in the same change.
   - Only the holder of `data/` can regenerate the artifact. The directory is
     gitignored and lives on one machine.

## Verification

Run in this order.

```
uv run ruff check .
uv run pytest
uv run etl demo-profile --input data/load_2023.csv --input data/load_2024.csv \
  --input data/load_2025.csv --input data/load_2026.csv \
  --start 2026-01-24 --end 2026-02-03 --out examples/real_winter_stress_2026.csv
uv run simulate --input examples/synthetic_winter_stress.csv \
  --storage-mwh 20000 --power-mw 2000
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 4320 --format json
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 4320
```

Pass conditions:

- `ruff` reports `All checks passed`.
- `pytest` reports the 360-passed baseline plus the 26 new tests, and 3 skipped.
- The synthetic demo prints the same output it printed before this change.
- The JSON run matches the table above within +/- 0.01 on every numeric field.
- The final table run prints the renderer strings quoted in Phase 3.
- `git status` shows no change under `examples/synthetic_winter_stress.csv`,
  `examples/make_synthetic_winter_stress.py`, `src/owr/scenario_input.py`,
  `src/owr/config.py`, `docs/PLAN_SCENARIO_PROFILE_FORMAT.md`, or any existing
  test file.

## Risks, ranked

1. **The artifact has a death date, and one owner.** The pending format redesign
   makes `ts` and `interval_minutes` required, which breaks this file and the README
   command that reads it. `data/` is gitignored, so only its holder can regenerate.
   Mitigation: the banner names the superseding plan, and Phase 4 writes all three
   items into `docs/HANDOFF.md`. Continuous integration never regenerates the file;
   it only runs the tests.
2. **The demo lists no stress window.** `simulate` recomputes the percentile from
   the file alone. A p90 over 11 days marks at most 2 days, and those 2 days are not
   adjacent, so no window survives the 2-day minimum. This is a property of the
   provisional format, and the redesign exists to fix that seam. Mitigation: the
   banner note and the `--severity-percentile 0` variant, which yields exactly one
   11-day window. **Do not change any engine default to work around this.**
3. **Zero recharge reads like a bug.** With no wind column the reserve never
   charges. Mitigation: the banner, the README sentence, and the demo narration.
4. **A rank can silently drop one step.** Two summation orders over the same day
   differ by about 1e-9, enough to push a day below its own population value.
   Measured on 2026-01-31. Mitigation: Phase 1 rule 10, Phase 2 step 7, and the two
   tests that pin a rank of exactly 1.0 on the population maximum.
5. **The event definition is unreconciled.** `data/daily_stress_events_team.csv`
   reports 18 days from the same 2026-01-24 start, on a load series about five times
   smaller. Present the 11-day window as this repository's finding, never as a team
   agreed figure.
6. **The percentile population is an open question.** Per-season against pooled
   across the year is still unanswered by Mitchell. The `demand_percentile` column
   inherits the per-season assumption. The banner names it.
7. **Rounding breaks an exact tie.** `load_mw` at 3 decimals makes
   `sum(hourly) == daily integral` true only within about 0.012 MWh. Test with a
   0.02 tolerance. Never assert exact float equality.
8. **Scope leak.** The new module must emit only `date`, `hour`, `load_mw` and
   `demand_percentile`. No `ts`, no `interval_minutes`, no `schema_version`. Those
   belong to the format redesign, which stays untouched.

## Out of scope

Do not open, edit or implement `docs/PLAN_SCENARIO_PROFILE_FORMAT.md`. Do not
change `src/owr/scenario_input.py`, `src/owr/config.py`,
`examples/make_synthetic_winter_stress.py`, `examples/synthetic_winter_stress.csv`,
or any existing test. Do not add a wind column. Do not add auto-selection of the
event window; the operator reads the dates from `etl transform`.

## Revision log

Revision 1, 2026-08-05, after adversarial review of revision 0.

| # | Finding | Disposition |
|---|---|---|
| 1 | Blocking. The plan hides the artifact's death date under the pending format redesign | **Accepted.** New section "This bridge is disposable, and it has a death date". Phase 4 step 4 writes three items into `docs/HANDOFF.md`. Risk 1 rewritten. The format plan stays untouched |
| 1a | Overlap with the redesign's `hourly.py` and `profile_csv.py` | **Accepted, and extended.** Module renamed `demo_profile.py`, subcommand renamed `demo-profile`. Planner-initiated, so the bridge is visible, clear of `profile_csv.py`, and greppable at retirement |
| 2 | Wrong rank for 2026-01-31, and two simulator figures | **Accepted, and the cause is deeper than a typo.** Re-measured through the repository's own modules: 2026-01-31 is 262/270 = 0.970370, and 2026-02-01 is 261/270 = 0.966667. The cause is a summation order difference of about 1e-9 between the population total and a total recomputed from the hourly rollup, which drops a day below its own value. Added Phase 1 rule 10, Phase 2 step 7, unit test 8, CLI test 3, and risk 4. Simulator figures now 40729.644 discharged and 19270.356 final state of charge |
| 3 | Pass condition unreadable from the table renderer | **Accepted.** Numeric checks now run with `--format json` at +/- 0.01. The renderer strings are quoted separately |
| 4 | Test 1 asserts exact float equality | **Accepted.** Tests 1 and 2 use `pytest.approx`. A general rule follows the test table |
| 5 | Rule 15 blames DST for every coverage gap | **Accepted.** Split into rules 16 and 17, two conditions only. New test 14 proves an ordinary gap says nothing about DST |
| a | "exactly" overclaims the p90 match | **Accepted.** Now "agrees to 3 decimals", with the last-digit variation stated |
| b | Size ~15 KB | **Accepted.** Now ~10 KB |
| c | Daily-total basis unstated | **Accepted.** The Phase 3 table carries both the population total and the emitted sum, with the 0.005 MWh gap named |
| d | Banner shows one provenance block, four exist | **Accepted.** The banner example shows the repeated form and says four pairs appear in the real run |
