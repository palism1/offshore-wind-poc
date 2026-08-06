# Demo script

Rehearsed 2026-08-06 on `main` at `e889ea2` (tag `demo-fallback`). Every
"expect" line below is output from that rehearsal, not a prediction. Total
run time is under five minutes.

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

Expect: `596 passed, 4 skipped`. The 4 skips need a live Postgres and are
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
2026-01-24 to 2026-02-03 (the event Report B priced at $443/MWh):

```bash
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --start-soc-mwh 20000 --lead-days 1
```

Expect, in the report:

| Line | Value |
|---|---|
| Pre-event charging | 20,000 MWh -> 48,794 MWh over 1 lead day |
| Severity reduction | 0.8% |
| Energy discharged | 29,792 MWh |
| Equivalent full cycles | 0.497 |

Two expected quirks, say them before anyone asks:

- A warning notes `wind_forecast_frac` defaulted to 0.0. Deriving it needs a
  wind nameplate capacity the team has not chosen (open question
  `wind_forecast_frac_derivation`).
- `energy charged 0 MWh`: wind is about 5% of system load inside this
  window, so in-window recharge rounds to zero. The wind series does its
  work in the pre-event charging line.

## Act 4 — same event at realistic efficiency

Dick et al. (J. Energy Storage, StEnSea) Table 1 gives 0.72 round-trip.
The engine default is 1.0 and the default is an open team decision; the
flag lets the demo show both without waiting for the decision:

```bash
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --start-soc-mwh 20000 --lead-days 1 \
  --efficiency 0.72
```

Expect the same run shape with:

| Line | 1.0 | 0.72 |
|---|---|---|
| Pre-event charging reaches | 48,794 MWh | 40,732 MWh |
| Severity reduction | 0.8% | 0.6% |
| Energy discharged | 29,792 MWh | 16,387 MWh |
| Equivalent full cycles | 0.497 | 0.273 |

Talking point: every published energy number moves with this one decision.
That is why the engine refuses a silent default and labels the value
`[OPEN: round_trip_efficiency]` in its own output.

## Act 5 — how the answer scales with storage size

```bash
uv run sweep --input examples/real_winter_stress_2026.csv \
  --power-mw 2000 --chart sweep.png
```

Expect a 7-row table from 5,000 to 100,000 MWh. Reference row at
60,000 MWh: severity 1.06%, discharged 40,730 MWh, EFC 0.679 (the sweep
starts every size full, so its numbers sit above Act 3's, which starts at
20,000 MWh). Open `sweep.png` for the slide-ready chart. Add
`--data-out sweep.csv` for the numbers as CSV.

## Optional act — API and database

Rehearsed green 2026-08-06: migrations applied on first init, 600 tests
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
uv run pytest                    # the 4 gated tests now run: expect 600 passed, 0 skipped
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
