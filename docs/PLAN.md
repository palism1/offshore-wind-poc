# Software & Infrastructure Plan — Offshore Wind Reserve Scenario Tool
Date: 2026-07-16 · Status: PLAN ONLY, nothing built yet
Scope: the Software & Infrastructure Lead role (PostgreSQL, ETL, backend, frontend support, deployment). Data science and modeling work belongs to the Data & Modeling Lead and is out of scope here.

## Guiding constraints (from the documents)

- Target is the Scaling doc's **Goal B/C envelope**: 2 to 4 data sources, one low-complexity region (ISO-NE system-wide or Boston zone), no spatial data, no transmission losses, no flow directions, no inter-market interchange, no regulatory logic in code.
- System rules: reliability first, economics second, efficiency third; output always prioritizes the cheapest reliable way to meet demand.
- Provenance is a product feature: every result must be traceable to inputs (auditable results + AI explanations).
- Storage is modeled as a **generic long-duration asset** (power MW, energy MWh, efficiency, soc_floor, strategic_reserve) so the pumped-hydro vs battery naming question never forks the code (see FACT_CHECK_REPORT.md).

## Phase 0 — Foundation (repo + access)
1. Create GitHub repo (per Scaling doc MVP checklist), Python 3.12, uv or poetry, ruff, pytest, pre-commit.
2. Obtain ISO-NE Web Services credentials (webservices.iso-ne.com) and an EIA API key.
3. Confirm the wind generation/forecast dataset choice with the Data & Modeling Lead (this is the coupling point between the two roles).
4. Docker compose file with PostgreSQL 16 + TimescaleDB extension for local dev.

## Phase 1 — PostgreSQL schema
Tables (all with provenance columns: source, retrieved_at, source_query, dataset_version):
- `raw.hourly_load` (ts, zone, load_mw) — hypertable
- `raw.hourly_wind` (ts, gen_mw, forecast_mw, horizon_days) — hypertable
- `raw.hourly_lmp` (ts, zone, lmp) — optional, for the economics metric
- `features.daily_load` (date, load_mwh, season, demand_percentile)
- `app.scenario` (user inputs from Architecture Step 1: storage total/starting capacity, power output, season, date range, min stress window days, severity percentile, transmission limits, efficiency)
- `app.simulation_run` (scenario_id, code_version, dataset_versions, status, created_at)
- `app.run_result_hourly` (run_id, ts, soc, charge, discharge, discharge_peak, discharge_smooth, net_load, capacity_margin)
- `app.run_result_daily` (run_id, date, budget, priority, usable_energy, recharge_sufficiency_ratio)
- `app.decision_package` (run_id, jsonb payload sent to AI assistant, annotation text)
Seasonal denominators (561,878 / 434,214 MWh) become rows in a `features.constants` table with a derivation query recorded, not literals in code.

## Phase 2 — ETL pipeline
1. Extract via `gridstatus` (ISO-NE load/LMP, EIA) into `raw.*` immutably; idempotent upserts keyed on (source, ts).
2. Transform: hourly to daily aggregation, season tagging, demand percentile computation; data validation gates (gap detection, unit checks, DST handling) with a validation report the Data & Modeling Lead signs off on.
3. CLI entry points (`etl extract`, `etl transform`, `etl validate`) so pipeline steps are runnable and testable independently; nightly refresh is a stretch goal, historical backfill is the requirement.

## Phase 3 — Simulation engine (pure Python, no I/O in the core)
Modules mapping one-to-one to the Architecture doc outline:
1. `stress_finder`: daily-load window search for X or more consecutive days above the severity percentile.
2. `initial_soc`: pre-event charging from wind (Architecture Step 3), plus the Step 4 user confirmation data (day options and SoC per start day) returned as structured output for the frontend.
3. `dispatch`: peak reduction allocation (NetLoad, PeakWeight, Discharge_peak), smoothing allocation (Ramp, SmoothWeight, Discharge_smooth), off-peak charging; enforces ∑Discharge(t) ≤ Budget(d).
4. `soc_engine`: soc(t+1) = soc(t) + charge·eff − discharge/eff with eff parameter (default 1.0), soc_floor, strategic_reserve; usable_energy accounting.
5. `budget`: recharge sufficiency ratio, Priority(d) = 0.7·DemandPercentile + 0.3·WindForecast, Budget(d) allocation, the 80% energy budget rule.
6. `metrics`: capacity margin (gross vs net load with storage), residual load cost vs gas price, severity reduction vs direct-to-grid baseline.
7. `simulator`: the rolling-window loop orchestrating 1 through 6 day by day until the stress window ends.
Every formula gets a unit test quoting the document line it implements; constants (0.7/0.3, 80%, 33%) are config values labeled as team design choices.
**Blocked on team decisions:** the two blank Step 5/6 sections and the canonical reserve definition (see open questions).

## Phase 4 — Backend API (FastAPI)
- POST /scenarios, GET /scenarios/{id} (validated against Step 1 inputs)
- POST /scenarios/{id}/runs (async run, status polling), GET /runs/{id}/results (hourly + daily)
- GET /runs/{id}/stress-windows (Step 2 output for user confirmation, per Step 4)
- POST /runs/{id}/decision-package → assembles annotation payload, calls AI service, stores explanation with provenance
- OpenAPI docs double as the integration contract for whoever does frontend.

## Phase 5 — Frontend support
- Thin React (or plain Vite) app: scenario form, stress-window picker, results dashboard.
- Charts: SoC trajectory, capacity margin, net load vs gross load, discharge split (peak vs smoothing), reserve-vs-direct-to-grid comparison. Follow the Scaling doc's frontend loop: design interactions, user-test, code, cross-browser test, user-test again.

## Phase 6 — Deployment
- Docker compose for the demo (db + api + frontend); single cheap host (Fly.io / Render / small VPS) is sufficient for a POC. CI: lint + tests on PR.

## Open questions for the team (from FACT_CHECK_REPORT.md)
1. Canonical reserve definition: is 33% the soc_floor, or soc_floor + strategic_reserve?
2. Fill in Architecture Steps 5/6 blanks and resolve the duplicate Step 6.
3. One storage label for external comms (subsea pumped hydro vs battery); engine handles either.
4. Define the empty Overview sections (Constraints, Metrics, Required Inputs, Success Criteria); proposal: adopt Phase 3 metrics list as the Metrics draft.
5. Which wind dataset (historical offshore proxy vs synthetic forecast) — Data & Modeling Lead owns, but schema needs the answer by Phase 1.

## Explicit non-goals (per Scaling Goal B/C)
Spatial modeling, transmission/distribution losses, flow directions, market interchange, regulatory compliance logic, digital twin fidelity, more than 2 to 4 data sources.
