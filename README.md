# Offshore Wind Reserve — Scenario Simulation Tool (POC)

A proof-of-concept scenario tool. It tests whether long-duration **seafloor wind
energy reserves** (subsea pumped hydro, StEnSea-like) reduce the severity of
multi-day grid stress events on ISO-NE (New England).

This repository holds the **Software & Infrastructure Lead** deliverables.
Data-science and forecast modeling belong to the Data & Modeling Lead and are out
of scope here.

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 0 | Repo scaffold (uv, ruff, pytest, docker-compose) | Done |
| 1 | PostgreSQL 16 + TimescaleDB schema (`db/migrations/`) | Done |
| 2 | ETL: ISO-NE load + EIA-930 wind, daily rollup, stress thresholds | Done |
| 3 | Simulation engine (pure core, MPC rolling-window dispatch) | Done, tested |
| 3.5 | Simulator CLI (`simulate`) and storage-size sweep (`sweep`) | Done, tested |
| 4 | FastAPI backend, in-memory and Postgres stores | Done, tested |
| 5 | Frontend | Deferred by team decision |
| 6 | CI (GitHub Actions: ruff + pytest) | Done, running |

See `docs/PLAN.md` for the full phased plan and `docs/FACT_CHECK_REPORT.md` for
the primary-source verification of every claim.

## Prerequisites

1. Install [uv](https://docs.astral.sh/uv/) (it manages Python 3.12 and the
   virtual environment for you).
2. Optional: install Docker Desktop. You need it only for the Postgres-backed
   store and its three gated tests. Everything else runs without it.
3. Optional: get a free [EIA API key](https://www.eia.gov/opendata/register.php).
   You need it only to pull fresh wind data. The committed examples already
   contain real data, so a demo needs no key.

## Quickstart

```bash
git clone https://github.com/palism1/offshore-wind-poc.git
cd offshore-wind-poc
uv sync --extra etl --extra api --extra viz   # env + all optional features
uv run pytest                                 # expect: 596 passed, 4 skipped
uv run ruff check .                           # expect: All checks passed
```

The 4 skipped tests need a live Postgres. Set `OWR_TEST_DATABASE_URL` to run
them (see Configuration). Without the `viz` extra, 3 chart tests also skip.

Run a real scenario end to end (real ISO-NE load and real EIA wind, an 11-day
stress event, 2026-01-24 to 2026-02-03):

```bash
uv run simulate --input examples/real_winter_stress_2026.csv \
  --storage-mwh 60000 --power-mw 2000 --start-soc-mwh 20000 --lead-days 1
```

Expected result: the pre-event charging block reports state of charge 20,000 MWh
to 48,794 MWh. Wind is about 5% of load inside this window, so in-window recharge
is 0 MWh; the `--start-soc-mwh` and `--lead-days` flags are what make the wind
series visible.

Sweep severity reduction across a ladder of storage sizes and render a chart:

```bash
uv run sweep --input examples/real_winter_stress_2026.csv \
  --power-mw 2000 --chart sweep.png
```

Expected result: severity 0.010633 at the 60,000 MWh rung, and `sweep.png` on
disk. Use `--data-out sweep.csv` for the numbers without the chart.

A synthetic profile with a known answer also ships:

```bash
uv run simulate --input examples/synthetic_winter_stress.csv \
  --storage-mwh 20000 --power-mw 2000
```

## The other surfaces

**API** (no database and no credentials required; it starts on an in-memory
store):

```bash
uv run uvicorn owr.api.app:app --reload
# OpenAPI docs at http://127.0.0.1:8000/docs
```

**ETL** (`extract | transform | validate | demo-profile`):

```bash
uv run etl --help
# real winter p90 threshold + stress windows from raw load CSVs:
uv run etl transform --input data/load_2023.csv --input data/load_2024.csv \
  --input data/load_2025.csv --input data/load_2026.csv
```

Raw pulls land in `data/`, which is git-ignored. `etl extract --dataset load`
needs no credentials; `--dataset wind` needs `EIA_API_KEY` (see Configuration).

**Database** (only for the Postgres-backed store and its tests):

```bash
docker compose up -d db     # Postgres 16 + TimescaleDB on localhost:5432
# migrations in db/migrations/ run automatically on first init
```

## Configuration

Everything runs with zero configuration except the two cases below.

| Variable | Needed for | Notes |
|---|---|---|
| `EIA_API_KEY` | `etl extract --dataset wind` (EIA-930 hourly wind) | Free key. Set it in your shell or a `.env` file (git-ignored). It never reaches logs, output, or the database. |
| `OWR_DATABASE_URL` | Switching the API from the in-memory store to Postgres | Example: `postgresql://owr:owr@localhost:5432/owr` (matches `docker-compose.yml`). Unset means in-memory. |
| `OWR_TEST_DATABASE_URL` | The 4 Postgres-gated tests | Point it at the docker-compose database above; the tests skip when it is unset. |

Optional-dependency extras (`uv sync --extra <name>`):

| Extra | Adds | Needed for |
|---|---|---|
| `etl` | gridstatus, psycopg | ETL provider pulls |
| `api` | fastapi, uvicorn, psycopg | Running the API server |
| `viz` | matplotlib | `sweep --chart` PNG rendering |

The dev group (pytest, ruff, fastapi test client) installs by default with
`uv sync`, so the full test suite runs with no extras at all.

Model constants that the source documents leave open (reserve floor, priority
weights 0.7/0.3, 80% energy-budget rule, round-trip efficiency) are named,
documented values in `src/owr/config.py`, never magic numbers. Each docstring
names the team question it maps to. Override them per run through the CLI flags
(`uv run simulate --help` lists every one with its labeled default).

## Layout

```
src/owr/            engine core (pure: no file, network, or DB access) + simulator CLI
src/owr/sweep*.py   storage-size sweep: core (sweep.py) + CLI + chart (the only
                    Matplotlib entry point)
src/owr/api/        FastAPI app, schemas, in-memory and Postgres stores
src/owr/etl/        extract | transform | validate | demo-profile
db/migrations/      PostgreSQL + TimescaleDB schema
tests/              pytest suite, one test module per source module
examples/           runnable day-profile CSVs (see below)
docs/               plan, fact-check report, data-source registry, shipped-feature plans
docker-compose.yml  local Postgres 16 + TimescaleDB
```

The engine pipeline:

```
stress_finder → initial_soc → [ per stress day: budget → dispatch → soc_engine ] → metrics
```

## Example data

- `examples/real_winter_stress_2026.csv` — real ISO-NE load and real EIA-930
  hourly wind for the 2026-01-24 to 2026-02-03 stress event. Generated by
  `etl demo-profile` (`docs/PLAN_REAL_DEMO_BRIDGE.md`).
- `examples/synthetic_winter_stress.csv` — synthetic profile with a known
  answer, generated by `examples/make_synthetic_winter_stress.py`. Regenerating
  it must produce a byte-identical file.

The day-profile column layout (`date,hour,load_mw,wind_mw,...`) is provisional;
`docs/PLAN_SCENARIO_PROFILE_FORMAT.md` holds the researched replacement format.

## Provenance

Provenance is a product feature: every simulation result carries the input
dataset versions and the code version (short git SHA), and every raw API payload
lands immutably with four provenance columns before transformation. Where each
number comes from is recorded in `docs/DATA_SOURCES.md`.
