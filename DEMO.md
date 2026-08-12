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

Expect: `832 passed, 4 skipped`. The 4 skips need a live Postgres and are
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
expected_recharge / remaining_cycles)`. Event-relative recharge routes all
pre-charge and off-peak wind to storage (`recharge.recharge_opportunity_mwh`,
`PLAN_BUDGET_FULL_TANK_FIX.md`), and that recharge term carries no state of
charge, so a fully-charged reserve reports a real recharge opportunity and
discharges from day one, at the identity wind multiplier:

```bash
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --lead-days 1
```

| Line | Value |
|---|---|
| Pre-event charging | 60,000 MWh -> 60,000 MWh over 1 lead day |
| Severity reduction | 0.8% |
| Energy discharged | 63,420 MWh |
| Energy charged | 73,861 MWh |

`--wind-multiplier 15` raises the recharge opportunity by more than an order
of magnitude, and discharged and charged energy both rise with it:

```bash
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --lead-days 1 --wind-multiplier 15
```

| Line | Value |
|---|---|
| Severity reduction | 0.8% |
| Energy discharged | 67,212 MWh |
| Energy charged | 85,186 MWh |
| Equivalent full cycles | 1.120 |
| Final SoC (floor 18,000 MWh) | 53,335 MWh |

Talking point: severity reduction does not move between the two runs above,
and that is not a defect. `dispatch.allocate_discharge` clips every hour at
`power_mw`, so once the reserve's own power rating is the binding limit on
the event's peak hour, more recharge opportunity moves more total energy
(discharged rises from 63,420 to 67,212 MWh) without moving the peak-hour
number severity reduction reads. Three expected quirks, say them before
anyone asks:

- A warning notes `wind_forecast_frac` defaulted to 0.0. Deriving it needs a
  wind nameplate capacity the team has not chosen (open question
  `wind_forecast_frac_derivation`).
- The recharge term applies no power clamp (`recharge_cycle_basis`): on this
  file the reported recharge opportunity (164,627 MWh) is far larger than
  what a 2,000 MW asset could ever absorb, so the two-term minimum degenerates
  to its `available_charge` term for most of the window. Delivered energy is
  unaffected; only the reported per-day budget carries the excess.
- `wind_charge_source` (F5): the engine cannot tell an ISO-NE system-wide
  wind series (which serves load) from a dedicated offshore farm whose
  output would go to the reserve first, and says so in its open-questions
  block instead of assuming the dedicated reading silently.

## Act 4 — same event at the historic 100%-efficient reading

Week 4B moved the engine default from 1.0 to 0.7225 (`0.85 * 0.85`, Report
B's 0.85 read as a per-leg figure and squared to the round-trip figure this
flag takes). This act runs the comparison at `--wind-multiplier 15`, the same
run Act 3 used, where the larger recharge opportunity makes the efficiency
choice visible in more than the last digit. `--efficiency 1.0` shows the
Overview's original "100% efficient" reading for comparison, and shows that
the flag still takes a round-trip figure directly, never a pre-squared value:

```bash
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --lead-days 1 \
  --wind-multiplier 15 --efficiency 1.0
```

Expect the same run shape with:

| Line | 0.7225 (default) | 1.0 |
|---|---|---|
| Severity reduction | 0.8% | 0.8% |
| Energy discharged | 67,212 MWh | 74,204 MWh |
| Equivalent full cycles | 1.120 | 1.237 |
| Final SoC (floor 18,000 MWh) | 53,335 MWh | 56,000 MWh |

Talking point: every published energy number moves with this one decision.
`--efficiency 0.72` still realizes the Dick et al. (J. Energy Storage,
StEnSea) Table 1 round-trip figure exactly, via `sqrt(0.72) = 0.8485` per
leg internally. That is why the engine refuses to hide the choice and labels
the value `[OPEN: round_trip_efficiency]` in its own output.

## Act 5 — how the answer scales with storage size

`sweep` starts every point of its ladder fully charged, with no
`--start-soc-mwh` override, so it is the deliverable
`PLAN_BUDGET_FULL_TANK_FIX.md` fixed: before that fix every row read 0.00%.
`--wind-multiplier 15` is the same recharge-fed scenario Acts 3 and 4 use:

```bash
uv run sweep --input examples/real_winter_stress_2026.csv \
  --power-mw 2000 --wind-multiplier 15 --chart sweep.png
```

Expect a 7-row table from 5,000 to 100,000 MWh, severity reduction rising
from 0.25% at 5,000 MWh and saturating at 0.76% from 20,000 MWh up. Reference
row at 60,000 MWh: severity 0.76%, discharged 70,457 MWh, EFC 1.174 (the
sweep runs every size over the full 11-day window with no lead days, which
is why its 60,000 MWh figures sit close to but not identical with Act 3's
1-lead-day run). Note EFC falls past 20,000 MWh (1.659, then 1.369, 1.174,
1.028, 0.912): larger storage draws a larger discharge budget denominator
while the same fixed wind supply caps how much energy actually moves, so
cycling intensity per MWh installed declines even as total energy discharged
keeps rising (33,179 MWh at 20,000 MWh up to 91,232 MWh at 100,000 MWh). Open
`sweep.png` for the slide-ready chart. Add `--data-out sweep.csv` for the
numbers as CSV.

## Optional act — API and database

Rehearsed green 2026-08-06: migrations applied on first init, 832 passed, 4 skipped,
and a scenario round-tripped through the Postgres-backed API.

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
