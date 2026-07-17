# Offshore Wind Reserve — Scenario Simulation Tool (POC)

Proof-of-concept scenario-testing tool evaluating whether long-duration **seafloor
wind energy reserves** (subsea pumped hydro, StEnSea-like) reduce the severity of
multi-day grid stress events on ISO-NE (Boston / New England).

This repository holds the **Software & Infrastructure Lead** deliverables. Data-science
and forecast modeling belong to the Data & Modeling Lead and are out of scope here.

## Status

| Phase | Scope | State |
|-------|-------|-------|
| 0 | Repo scaffold (uv, ruff, pytest, docker-compose) | ✅ built |
| 1 | PostgreSQL + TimescaleDB schema | ✅ migration written (`db/migrations/`) |
| 2 | ETL via `gridstatus` (ISO-NE + EIA) | ⛔ blocked on API credentials |
| 3 | Simulation engine (pure Python, MPC rolling-window dispatch) | ✅ built + tested |
| 4 | FastAPI backend (`src/owr/api/`) | ✅ built + tested (in-memory store) |
| 5 | Thin React/Vite frontend | ⏳ later |
| 6 | Deployment (docker-compose demo) | ⏳ later |

See `docs/PLAN.md` for the full phased plan, `docs/FACT_CHECK_REPORT.md` for the
primary-source verification of every claim, and `docs/DIAGRAM_REFERENCES.md` for
slide-deck assets.

## The simulation engine (Phase 3)

Pure-Python, no I/O in the core, so it runs and is tested without a database or any
external API. It implements the Architecture doc's daily rolling-horizon (model
predictive control) storage dispatch loop:

```
stress_finder → initial_soc → [ per stress day: budget → dispatch → soc_engine ] → metrics
```

Design constants that the source documents leave as open team decisions
(reserve floor 33%, priority weights 0.7/0.3, 80% energy-budget rule, round-trip
efficiency) are **configuration values labeled as team design choices** in
`owr/config.py`, never magic numbers. See the docstrings there for the open
questions each one maps to.

## Quickstart

```bash
uv sync --group dev          # create .venv with Python 3.12 + dev tools
uv run pytest                # run the full suite (engine + API)
uv run ruff check .          # lint

# run the API (Phase 4) — no database or credentials required
uv run --with uvicorn uvicorn owr.api.app:app --reload
#   OpenAPI docs / integration contract at http://127.0.0.1:8000/docs

# local database for the later DB-backed store (Phase 2+)
docker compose up -d db      # Postgres 16 + TimescaleDB on localhost:5432
```

The API runs against an in-memory store, so it is fully exercisable now; swapping in
a PostgreSQL-backed repository (the Phase 1 schema) is an isolated later change behind
the `owr.api.store.Repository` interface.

## Layout

```
src/owr/            simulation engine (Phase 3) + config/models
db/migrations/      PostgreSQL schema (Phase 1)
tests/              pytest suite (one test module per engine module)
docs/               plan, fact-check report, diagram references
docker-compose.yml  Postgres 16 + TimescaleDB for local dev
```

## Provenance

Provenance is a product feature: every simulation result is tagged with input
dataset versions and the code version, and every raw API payload lands immutably
before transformation. `RESUME_LOG.md` is local-only (gitignored).
