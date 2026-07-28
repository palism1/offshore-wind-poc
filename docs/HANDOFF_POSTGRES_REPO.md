# HANDOFF — Postgres-backed Repository (checklist item 2, IN PROGRESS)

Last updated: 2026-07-17. Read this to finish the Postgres store in one pass.
Companion to `docs/HANDOFF.md` (the whole-project handoff). This file covers only
the in-flight Phase 1/4 persistence work on branch `worktree-postgres-repo`.

## Goal

Implement a PostgreSQL-backed `owr.api.store.Repository` so the API persists across
requests, replacing the in-memory store, without restructuring the routes.

## Decisions already made (do not relitigate)

1. **Hybrid persistence** (user chose this): normalized `app.run_result_daily` /
   `app.run_result_hourly` tables as designed, PLUS a `result_summary` JSONB column on
   `app.simulation_run` for the run-level scalars (`final_soc`, `baseline_peak_mw`,
   `reserve_peak_mw`) and the detected stress windows. Not a full-JSONB blob, not a new
   `stress_window` table.
2. **`save_run` added to the Repository protocol.** The routes mutate the `RunRecord`
   in place (`run.status = ...`, `run.result = ...`); the in-memory store returned the
   same object so that worked for free, but a DB store returns detached rows. So routes
   must call `r.save_run(run)` after mutating. This is the one necessary route change;
   the handoff's "no route changes" claim was not achievable.
3. **Migration 002 is required** and also closes two other real schema gaps found while
   mapping: `app.scenario` was missing `available_capacity_mw`, `peak_weight`,
   `smooth_weight` (all three are on the wire model and consumed by every run), and
   `app.run_result_hourly` was missing `gross_load`.
4. **psycopg is optional**: `pg_store.py` is imported only when `OWR_DATABASE_URL` is
   set, so the default in-memory API and the existing 35 tests need no DB driver.

## DONE (committed on this branch)

- `db/migrations/002_run_summary_and_scenario_fields.sql` — adds the 3 scenario columns,
  `gross_load`, and `result_summary` JSONB. All `ADD COLUMN IF NOT EXISTS`, idempotent.
- `src/owr/api/store.py` — added `save_run` to the `Repository` protocol (with docstring
  explaining the in-place-mutation contract) and an in-memory `save_run` that re-stores.
- `src/owr/api/pg_store.py` — the full `PostgresRepository`: `add_scenario`,
  `get_scenario`, `add_run`, `save_run` (UPSERT run + rewrite daily/hourly + upsert
  decision package, all in one transaction), `get_run` (reconstructs `SimulationResult`
  from the normalized tables + `result_summary`, plus stress windows + decision package).
  One short-lived connection per method (thread-safe under FastAPI workers).

## REMAINING (to finish the task)

### 1. Wire `save_run` into the routes — `src/owr/api/app.py`
Currently `create_run` and `make_decision_package` mutate the run but never persist it.
Add `r.save_run(run)` at these points:
- In `create_run`, inside the `try`, right after `run.status = "succeeded"` (before the
  `return`).
- In `create_run`, inside the `except ValueError` block, after `run.status = "failed"`
  and before `raise` (so failed runs persist their status).
- In `make_decision_package`, right after `run.decision_package = {...}` (before `return`).

### 2. Runtime wiring — bottom of `src/owr/api/app.py`
Replace `app = create_app()` with a factory that picks the store from the environment,
lazily importing psycopg only when a DSN is present:
```python
import os
def _default_repo() -> Repository:
    dsn = os.getenv("OWR_DATABASE_URL")
    if dsn:
        from owr.api.pg_store import PostgresRepository
        return PostgresRepository(dsn)
    return InMemoryRepository()
app = create_app(_default_repo())
```
(Add `import os` at the top with the other stdlib imports.)

### 3. Dependencies — `pyproject.toml`
- Add `"psycopg[binary]>=3.1"` to the `[dependency-groups] dev` list so tests can import
  it. (It is already in the `etl` optional-extra; also add it to the `api` extra for
  real deployment.)

### 4. Integration tests — `tests/test_pg_store.py` (NEW)
- Guard: `psycopg = pytest.importorskip("psycopg")` and
  `pytestmark = pytest.mark.skipif(not os.getenv("OWR_TEST_DATABASE_URL"), reason=...)`.
  This keeps the default `uv run pytest` green (35 tests) with the PG tests SKIPPED when
  no DB is configured.
- Fixture: connect to `OWR_TEST_DATABASE_URL`, `TRUNCATE app.decision_package,
  app.run_result_hourly, app.run_result_daily, app.simulation_run, app.scenario
  RESTART IDENTITY CASCADE` before each test.
- Test A: `add_scenario` -> `get_scenario` round-trips ALL fields incl.
  `available_capacity_mw`, `peak_weight`, `smooth_weight`.
- Test B (the important one — proves persistence): build the app with
  `create_app(PostgresRepository(dsn))` + `TestClient`; POST /scenarios, POST
  /scenarios/{id}/runs (24-length hourly_load_mw), GET /runs/{id}, GET
  /runs/{id}/results, GET /runs/{id}/stress-windows, POST /runs/{id}/decision-package.
  Then build a FRESH `PostgresRepository`/app and GET /runs/{id}/results again — assert
  the results, peaks, and decision package survived (this is what the whole task is for).
- Test C (optional): a run whose inputs are rejected persists `status = 'failed'`.

## Verification (NOT yet run — do this before claiming done)

Docker daemon was DOWN when this work paused. Steps:
```bash
open -a Docker                       # start Docker Desktop, wait for daemon
cd ~/Desktop/offshore-wind-poc
docker compose down -v               # drop any stale volume so initdb re-runs
docker compose up -d db              # runs 001 then 002 in filename order on fresh volume
# wait for healthcheck: docker compose ps  (or pg_isready)
export OWR_TEST_DATABASE_URL='postgresql://owr:owr@localhost:5432/owr'
uv sync --group dev
uv run pytest                        # expect 35 prior + new PG tests PASS (not skipped)
unset OWR_TEST_DATABASE_URL && uv run pytest   # expect PG tests SKIP, 35 still green
uv run ruff check .
```
Confirm both modes: with DB (PG tests run and pass) and without (they skip, suite green).

## Gotchas / context

- **This branch does NOT contain the CI workflow.** It branched fresh from `origin/main`;
  the CI workflow lives on branch `worktree-ci-workflow` / draft PR #1, not yet merged to
  `main`. GitHub Actions will not run on this branch's PR until PR #1 is merged into
  `main` (pull_request workflows must exist on the base branch). Merge PR #1 first, or
  accept that CI validates this PR only after that merge.
- Migrations run via `docker-entrypoint-initdb.d` ONLY on a fresh (empty) volume, hence
  `docker compose down -v` before `up`. There is no standalone migration runner yet.
- The checklist lives in the task list: #1 CI (done, PR #1), #2 this work (in progress),
  #3 ETL skeleton (blocked on ISO-NE/EIA creds), #4 frontend (held).
- `RESUME_LOG.md` is LOCAL-ONLY / gitignored, in the main checkout only. Add a dated
  entry there when this lands.
- Source verification is NOT triggered by this task: it is pure
  persistence plumbing over the already-tested engine, introducing no new grid claims,
  statistics, or formulas.

## Field mapping reference (engine -> tables)

- `ScenarioCreate` -> `app.scenario` (all 16 fields listed as `_SCENARIO_FIELDS` in
  `pg_store.py`; order shared by INSERT and SELECT so they can't drift).
- `SimulationResult.daily[]` -> `app.run_result_daily` (date, budget, priority,
  usable_energy, recharge_sufficiency_ratio).
- `DailyResult.hourly[]` -> `app.run_result_hourly`; the hourly PK is `(run_id, ts)`, and
  `ts = datetime(date, ts_hour, tzinfo=UTC)` (see `_hour_ts`). On read, group hourly by
  `ts.date()` and set `ts_hour = ts.hour` after `astimezone(UTC)`.
- `SimulationResult` scalars + `run.stress_windows` -> `simulation_run.result_summary`
  JSONB (`_summary_json` / `_load_result` / `_load_windows`).
- `run.decision_package` `{payload, annotation}` -> `app.decision_package`.
