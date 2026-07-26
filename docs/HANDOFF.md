# HANDOFF — Offshore Wind Reserve Scenario Tool

Read this first when resuming the project in a fresh session. Last updated: 2026-07-17.

## What this project is

A proof of concept scenario testing tool for the **Software & Infrastructure Lead**
role. Question under test: can long duration **seafloor wind energy reserves** (subsea
pumped hydro, StEnSea like) reduce the severity of multi day grid stress events on
ISO-NE (Boston / New England) versus sending offshore wind straight to the grid. Data
science and forecast modeling belong to a separate Data & Modeling Lead and are out of
scope for this repo.

## Where everything is

| Thing | Location |
|-------|----------|
| Repo (working checkout) | `~/Desktop/offshore-wind-poc/` |
| GitHub (private) | https://github.com/palism1/offshore-wind-poc (origin/main) |
| Phased plan | `docs/PLAN.md` |
| Fact check report (primary source verification) | `docs/FACT_CHECK_REPORT.md` |
| Slide deck assets + mermaid diagram | `docs/DIAGRAM_REFERENCES.md` |
| Resume log (LOCAL ONLY, gitignored) | `RESUME_LOG.md` |
| Engine code | `src/owr/` |
| API code | `src/owr/api/` |
| DB schema | `db/migrations/001_init.sql` |
| Tests | `tests/` |

## Current status (phase by phase)

| Phase | Scope | State |
|-------|-------|-------|
| 0 | Repo scaffold (uv, Python 3.12, ruff, pytest, docker-compose) | DONE |
| 1 | PostgreSQL + TimescaleDB schema | DONE (migration written, not yet run against a live DB) |
| 2 | ETL via `gridstatus` (ISO-NE + EIA) | BLOCKED on API credentials |
| 3 | Simulation engine (pure Python, MPC rolling window dispatch) | DONE, tested |
| 4 | FastAPI backend | DONE, tested (in-memory store) |
| 5 | React/Vite frontend | HELD on purpose (see Open decisions) |
| 6 | Deployment + CI | NOT STARTED |

Test suite: **35 tests, all green. ruff clean.** Run `uv run pytest` and
`uv run ruff check .` to confirm.

## How to run

```bash
cd ~/Desktop/offshore-wind-poc
uv sync --group dev                                   # .venv with Python 3.12 + dev tools
uv run pytest                                         # full suite (engine + API)
uv run ruff check .                                   # lint
uv run --with uvicorn uvicorn owr.api.app:app --reload # serve the API; docs at /docs
docker compose up -d db                               # Postgres 16 + TimescaleDB (later phases)
```

The API and engine run with **no database and no credentials**. The API talks to an
in-memory store behind `owr.api.store.Repository`; a Postgres backed store using the
Phase 1 schema drops in later without touching any route.

## Architecture at a glance

Engine (`src/owr/`), pure Python, no I/O in the core, so it is fully testable offline.
The rolling window (model predictive control) dispatch loop is:

```
stress_finder -> initial_soc -> [ per stress day: budget -> dispatch -> soc_engine ] -> metrics
```

One module per responsibility: `stress_finder`, `initial_soc`, `budget`, `dispatch`,
`soc_engine`, `metrics`, `simulator`. Each formula has a unit test that quotes the
Architecture doc line it implements.

API (`src/owr/api/`): `schemas.py` (Pydantic wire contract), `store.py` (Repository
protocol + in-memory impl), `app.py` (FastAPI factory + routes). Endpoints: create /
fetch scenario, launch run (synchronous for the POC), stress windows, results, and a
provenance tagged decision package annotation. Every run is stamped with the engine git
sha.

## Key design decisions already made

1. **Storage is a generic long duration asset** (power, energy, efficiency, floors), so
   the pumped hydro versus battery naming question is a copy decision, not a code fork.
2. **Efficiency is a parameter defaulting to 1.0**, which reconciles the Overview's
   "100% efficient" assumption with the Architecture doc's efficiency term.
3. **Every open design constant is a labeled config value** in `src/owr/config.py`
   (reserve floor 33%, priority weights 0.7/0.3, 80% budget rule), never a magic number.
   Each docstring names the open team question it maps to.
4. **Provenance is a product feature**: schema rows carry (source, retrieved_at,
   source_query, dataset_version); seasonal denominators live in `features.constants`
   with a derivation query, not as literals; runs are tagged with the code git sha.

## What is blocked and on what

1. **Phase 2 ETL** needs **ISO-NE Web Services credentials** (webservices.iso-ne.com)
   and an **EIA API key** (api.eia.gov). The skeleton can be built without them, but it
   stays untested against live data until the keys exist.
2. The **seasonal denominators** (561,878 MWh summer / 434,214 MWh winter) are
   unverifiable until derived from ISO-NE load history during ETL. Do not hard code them;
   derive and store in `features.constants` with the query.

## Open team decisions (still unresolved, from FACT_CHECK_REPORT.md)

These gate specific formulas. The code runs today on documented defaults, but confirm
before treating results as final:

1. Canonical reserve definition: is 33% the `soc_floor`, or `soc_floor` plus
   `strategic_reserve`? (Engine supports both as separate fractions.)
2. Architecture doc Steps 5 and 6 are blank / duplicated; the budget allocation detail
   is the labeled interpretation in `src/owr/budget.py`, not verbatim spec.
3. Which wind dataset (historical offshore proxy vs synthetic forecast). Data & Modeling
   Lead owns this; the schema needs the answer for Phase 2.
4. One storage label for external comms (subsea pumped hydro vs battery). Engine is
   agnostic; this is a UI/copy choice.

## Recommended next steps (in priority order)

1. **CI**: add a GitHub Actions workflow running `ruff check` and `uv run pytest` on push
   and PR. Cheap, and the repo has no CI yet. (Plan Phase 6.)
2. **Phase 2 ETL skeleton**: CLI entry points (`etl extract | transform | validate`),
   transform + validation gate structure, `gridstatus` wiring. Testable structure now,
   live pulls once credentials arrive.
3. **Postgres backed Repository**: implement the `owr.api.store.Repository` protocol
   against the Phase 1 schema so the API persists.
4. **Phase 5 frontend**: HELD until the API contract is exercised and the open team
   decisions land, to avoid rework.

## Repo conventions

1. `RESUME_LOG.md` is **LOCAL ONLY and gitignored**; never commit it. It holds resume
   flavored progress entries. Update it as work lands.
2. Verify before publishing. Every regulatory citation, grid statistic, formula and
   design constant taken from the spec docs needs a verdict — Verified, Contradicted or
   Unverifiable — against a primary source before it reaches a slide, schema, plan or
   code. Primary sources only: ISO-NE Web Services, EIA API v2, ferc.gov, BOEM,
   DOE/NREL/PNNL. The verification for the current claims is recorded in
   `docs/FACT_CHECK_REPORT.md`.
3. Surface disagreements between documents as a team decision; do not silently pick a
   side. See `docs/FINDINGS_REVIEW_2026-07-24.md` for the current open list.
