# Demo script

Rehearsed 2026-08-06 on `worktree-review-fixes` at `1835290`. Every "expect"
line below is output from that rehearsal, not a prediction. Total run time is
under five minutes. The `demo-fallback` tag still points at the pre-fix
rehearsal (`main` at `e889ea2`) if demo morning goes wrong.

The question the demo answers: does long-duration storage charged from
offshore wind reduce the severity of a multi-day winter grid stress event
on ISO-NE, and how does the answer move with storage size and efficiency.

## Setup (once, before the demo)

```bash
git clone https://github.com/palism1/offshore-wind-poc.git
cd offshore-wind-poc
uv sync --extra etl --extra api --extra viz
```

## Act 1 — prove the build (30 seconds)

```bash
uv run pytest
```

Expect: `622 passed, 4 skipped`. The 4 skips need a live Postgres and are
covered in the optional act.

## Act 2 — stress-window detection

```bash
uv run simulate --input examples/synthetic_winter_stress.csv --list-windows
```

Expect one window:

```
1   2026-01-09 .. 2026-01-11   3 days   hours 0..71   peak 12,000 MW
```

Talking point: the rule (daily total demand above the 0.90 percentile, 2+
consecutive days) is sourced to the 2026-08-05 Architecture document,
Component 3, and the output says so on its source line.

## Act 3 — the real event, baseline

Real ISO-NE load and real EIA-930 hourly wind, the 11-day stress event
2026-01-24 to 2026-02-03 (the event Report B priced at $443/MWh). The reserve
starts fully charged: `docs/archive/plans/PLAN_REVIEW_FIXES.md` F5 fix makes pre-event
charging take only wind above the hour's load, and ISO-NE system-wide wind
almost never exceeds system load, so a `--start-soc-mwh 20000` run now shows
almost no gain (severity reduction rounds to 0.0%). This full-charge command
is the one with a number worth discussing:

```bash
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --lead-days 1
```

Expect, in the report:

| Line | Value |
|---|---|
| Pre-event charging | 60,000 MWh -> 60,000 MWh over 1 lead day |
| Severity reduction | 1.1% |
| Energy discharged | 40,633 MWh |
| Equivalent full cycles | 0.677 |

Three expected quirks, say them before anyone asks:

- A warning notes `wind_forecast_frac` defaulted to 0.0. Deriving it needs a
  wind nameplate capacity the team has not chosen (open question
  `wind_forecast_frac_derivation`).
- `energy charged 0 MWh`: wind is about 5% of system load inside this
  window, so in-window recharge rounds to zero. The wind series does its
  work in the pre-event charging line, and here it reports no gain: the
  reserve is already at 60,000 MWh before the event starts.
- `wind_charge_source` (F5): ISO-NE system-wide wind never exceeds system
  load in this window, so the reserve sees no surplus to charge from at any
  starting SoC, and the engine now says so in its open-questions block
  instead of assuming a dedicated wind farm whose output goes to the
  reserve first.

## Act 4 — same event at realistic efficiency

Dick et al. (J. Energy Storage, StEnSea) Table 1 gives 0.72 round-trip. The
engine now splits that figure per leg (`sqrt(0.72) = 0.8485`), so the flag
takes the published round-trip number directly: `--efficiency 0.72` realizes
exactly 0.72 round trip, never a pre-squared value. The engine default is
1.0 and the default is an open team decision; the flag lets the demo show
both without waiting for the decision:

```bash
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --lead-days 1 --efficiency 0.72
```

Expect the same run shape with:

| Line | 1.0 | 0.72 |
|---|---|---|
| Severity reduction | 1.1% | 1.0% |
| Energy discharged | 40,633 MWh | 34,478 MWh |
| Equivalent full cycles | 0.677 | 0.575 |
| Final SoC (floor 18,000 MWh) | 19,367 MWh | 19,367 MWh |

Talking point: 0.72 is the round-trip figure Dick et al. publish; the engine
applies `sqrt(0.72) = 0.8485` per leg internally, so the number typed at the
flag is the number realized end to end. Every published energy number still
moves with this one decision. That is why the engine refuses a silent
default and labels the value `[OPEN: round_trip_efficiency]` in its own
output.

## Act 5 — how the answer scales with storage size

```bash
uv run sweep --input examples/real_winter_stress_2026.csv \
  --power-mw 2000 --chart sweep.png
```

Expect a 7-row table from 5,000 to 100,000 MWh. Reference row at
60,000 MWh: severity 1.06%, discharged 40,730 MWh, EFC 0.679 (the sweep runs
every size over the full 11-day window with no lead days, which is why its
60,000 MWh figures sit close to but not identical with Act 3's full-charge,
1-lead-day run). Open `sweep.png` for the slide-ready chart. Add
`--data-out sweep.csv` for the numbers as CSV.

## Optional act — API and database

Rehearsed green 2026-08-06: migrations applied on first init, 626 tests
passed with zero skips, and a scenario round-tripped through the
Postgres-backed API.

```bash
uv run uvicorn owr.api.app:app --reload
# open http://127.0.0.1:8000/docs — no database, in-memory store
```

With Docker running:

```bash
docker compose up -d db          # Postgres 16 + TimescaleDB, migrations auto-run
export OWR_TEST_DATABASE_URL=postgresql://owr:owr@localhost:5432/owr
uv run pytest                    # the 4 gated tests now run: expect 626 passed, 0 skipped
OWR_DATABASE_URL=postgresql://owr:owr@localhost:5432/owr \
  uv run uvicorn owr.api.app:app --reload   # same API, Postgres store
```

One known quirk if you POST a scenario live: `season` defaults to
`"summer"` unless set in the body, even for winter dates. Pass
`"season": "winter"` explicitly.

## If anything is red on demo morning

```bash
git checkout demo-fallback
```

That tag is the state this script was rehearsed against.
