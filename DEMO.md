# Demo script

Rehearsed 2026-08-06 on `main` at `b2b599b`. Every "expect" line below is
output from that rehearsal, not a prediction. Total run time is
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

Expect: `738 passed, 4 skipped`. The 4 skips need a live Postgres and are
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

## Act 3 — the real event, recharge-limited vs recharge-fed

Real ISO-NE load and real EIA-930 hourly wind, the 11-day stress event
2026-01-24 to 2026-02-03 (the event Report B priced at $443/MWh). The reserve
starts fully charged: `docs/archive/plans/PLAN_REVIEW_FIXES.md` F5 fix makes
pre-event charging take only wind above the hour's load.

Week 4B change 7 replaced the daily discharge budget with Component 5's
two-term minimum: `min(available_charge / remaining_stress_days,
expected_recharge / remaining_cycles)`. ISO-NE system-wide wind almost never
exceeds system load, so at the identity wind multiplier the recharge term is
0.0 every day and the reserve cannot discharge at all:

```bash
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --lead-days 1
```

| Line | Value |
|---|---|
| Pre-event charging | 60,000 MWh -> 60,000 MWh over 1 lead day |
| Severity reduction | 0.0% |
| Energy discharged | 0 MWh |
| Budget every day | 0 MWh |

`--wind-multiplier 15` restores surplus wind and the reserve moves again, now
recharge-fed rather than sitting on its pre-charged energy alone:

```bash
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --lead-days 1 --wind-multiplier 15
```

| Line | Value |
|---|---|
| Severity reduction | 1.2% |
| Energy discharged | 60,231 MWh |
| Energy charged | 68,450 MWh |
| Equivalent full cycles | 1.004 |
| Final SoC (floor 18,000 MWh) | 47,322 MWh |

Talking point: under the revised rule the reserve is recharge limited, not
energy limited. A fully charged 60,000 MWh reserve delivers nothing across an
11-day event without surplus wind to refill it day over day; give it surplus
wind and it moves more energy than its own rated capacity (1.004 equivalent
full cycles). Three expected quirks, say them before anyone asks:

- A warning notes `wind_forecast_frac` defaulted to 0.0. Deriving it needs a
  wind nameplate capacity the team has not chosen (open question
  `wind_forecast_frac_derivation`).
- At the identity multiplier, wind is about 5% of system load inside this
  window, so in-window recharge rounds to zero and the budget floors at 0.0
  MWh every day (open question `recharge_cycle_basis`).
- `wind_charge_source` (F5): ISO-NE system-wide wind never exceeds system
  load in this window at the identity multiplier, so the reserve sees no
  surplus to charge from at any starting SoC, and the engine says so in its
  open-questions block instead of assuming a dedicated wind farm whose
  output goes to the reserve first.

## Act 4 — same event at the historic 100%-efficient reading

Week 4B moved the engine default from 1.0 to 0.7225 (`0.85 * 0.85`, Report
B's 0.85 read as a per-leg figure and squared to the round-trip figure this
flag takes). At the identity wind multiplier both readings show 0.0%
(Act 3), so this act runs the comparison at `--wind-multiplier 15`, where
the budget is non-zero and the efficiency choice is visible. `--efficiency
1.0` shows the Overview's original "100% efficient" reading for comparison,
and shows that the flag still takes a round-trip figure directly, never a
pre-squared value:

```bash
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --lead-days 1 \
  --wind-multiplier 15 --efficiency 1.0
```

Expect the same run shape with:

| Line | 0.7225 (default) | 1.0 |
|---|---|---|
| Severity reduction | 1.2% | 1.4% |
| Energy discharged | 60,231 MWh | 68,401 MWh |
| Equivalent full cycles | 1.004 | 1.140 |
| Final SoC (floor 18,000 MWh) | 47,322 MWh | 50,139 MWh |

Talking point: every published energy number moves with this one decision.
`--efficiency 0.72` still realizes the Dick et al. (J. Energy Storage,
StEnSea) Table 1 round-trip figure exactly, via `sqrt(0.72) = 0.8485` per
leg internally. That is why the engine refuses to hide the choice and labels
the value `[OPEN: round_trip_efficiency]` in its own output.

## Act 5 — how the answer scales with storage size

At the identity wind multiplier every row is 0.00% (R7: no surplus wind, no
recharge, no budget). `--wind-multiplier 15` is the same recharge-fed
scenario Acts 3 and 4 use:

```bash
uv run sweep --input examples/real_winter_stress_2026.csv \
  --power-mw 2000 --wind-multiplier 15 --chart sweep.png
```

Expect a 7-row table from 5,000 to 100,000 MWh. Reference row at
60,000 MWh: severity 1.10%, discharged 62,329 MWh, EFC 1.039 (the sweep runs
every size over the full 11-day window with no lead days, which is why its
60,000 MWh figures sit close to but not identical with Act 3's full-charge,
1-lead-day run). Note EFC falls past 60,000 MWh (0.953, then 0.886): larger
storage draws a larger discharge budget denominator while the same fixed
wind supply caps how much energy actually moves, so cycling intensity per
MWh installed declines even as total energy discharged keeps rising. Open
`sweep.png` for the slide-ready chart. Add `--data-out sweep.csv` for the
numbers as CSV.

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
