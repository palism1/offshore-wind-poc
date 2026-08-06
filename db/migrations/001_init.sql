-- Offshore Wind Reserve — Phase 1 schema (PostgreSQL 16 + TimescaleDB)
-- Maps 1:1 to docs/PLAN.md "Phase 1 — PostgreSQL schema".
--
-- Design rules encoded here:
--   * Provenance is a product feature: every raw/derived row carries
--     (source, retrieved_at, source_query, dataset_version).
--   * Storage is a GENERIC long-duration asset (power/energy/efficiency/floors),
--     so the pumped-hydro-vs-battery naming question never forks the schema
--     (docs/archive/reviews/FACT_CHECK_REPORT.md inconsistency #1).
--   * Seasonal denominators live in features.constants with a derivation query,
--     never as literals (docs/archive/reviews/FACT_CHECK_REPORT.md, Unverifiable section).

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE SCHEMA IF NOT EXISTS raw;       -- immutable landing zone for API payloads
CREATE SCHEMA IF NOT EXISTS features;  -- derived / transformed features
CREATE SCHEMA IF NOT EXISTS app;       -- scenario inputs, runs, results

-- ---------------------------------------------------------------------------
-- raw.* — immutable extracts, idempotent upserts keyed on (source, ts[, zone])
-- ---------------------------------------------------------------------------

CREATE TABLE raw.hourly_load (
    ts              TIMESTAMPTZ NOT NULL,
    zone            TEXT        NOT NULL,          -- 'ISONE' system-wide or a load zone
    load_mw         DOUBLE PRECISION NOT NULL,
    -- provenance
    source          TEXT        NOT NULL,
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_query    TEXT        NOT NULL,
    dataset_version TEXT        NOT NULL,
    PRIMARY KEY (source, zone, ts)
);
SELECT create_hypertable('raw.hourly_load', 'ts', if_not_exists => TRUE);

CREATE TABLE raw.hourly_wind (
    ts              TIMESTAMPTZ NOT NULL,
    gen_mw          DOUBLE PRECISION,              -- realized offshore wind generation
    forecast_mw     DOUBLE PRECISION,              -- forecast used by the dispatch horizon
    horizon_days    INTEGER,                       -- forecast lead time in days
    source          TEXT        NOT NULL,
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_query    TEXT        NOT NULL,
    dataset_version TEXT        NOT NULL,
    PRIMARY KEY (source, ts, horizon_days)
);
SELECT create_hypertable('raw.hourly_wind', 'ts', if_not_exists => TRUE);

CREATE TABLE raw.hourly_lmp (
    ts              TIMESTAMPTZ NOT NULL,
    zone            TEXT        NOT NULL,
    lmp             DOUBLE PRECISION NOT NULL,     -- $/MWh, optional economics metric
    source          TEXT        NOT NULL,
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_query    TEXT        NOT NULL,
    dataset_version TEXT        NOT NULL,
    PRIMARY KEY (source, zone, ts)
);
SELECT create_hypertable('raw.hourly_lmp', 'ts', if_not_exists => TRUE);

-- ---------------------------------------------------------------------------
-- features.* — transformed / derived
-- ---------------------------------------------------------------------------

CREATE TABLE features.daily_load (
    date               DATE NOT NULL PRIMARY KEY,
    load_mwh           DOUBLE PRECISION NOT NULL,  -- summed hourly load for the day
    season             TEXT NOT NULL CHECK (season IN ('summer', 'winter', 'shoulder')),
    demand_percentile  DOUBLE PRECISION,           -- vs seasonal denominator (features.constants)
    source             TEXT NOT NULL,
    retrieved_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    source_query       TEXT NOT NULL,
    dataset_version    TEXT NOT NULL
);

-- Data-derived constants (e.g. seasonal denominators 561,878 / 434,214 MWh).
-- Stored WITH the derivation query so no denominator is ever a magic number.
CREATE TABLE features.constants (
    name            TEXT PRIMARY KEY,              -- e.g. 'denominator_summer_mwh'
    value           DOUBLE PRECISION NOT NULL,
    unit            TEXT NOT NULL,
    derivation_query TEXT NOT NULL,                -- exact SQL/date-range used
    derived_from    TEXT NOT NULL,                 -- dataset_version(s) it was computed from
    retrieved_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- app.* — scenario inputs, runs, results (Architecture Step 1 onward)
-- ---------------------------------------------------------------------------

CREATE TABLE app.scenario (
    id                    BIGSERIAL PRIMARY KEY,
    name                  TEXT,
    -- generic storage asset (see design rule above)
    storage_total_mwh     DOUBLE PRECISION NOT NULL,
    storage_start_mwh     DOUBLE PRECISION NOT NULL,
    power_output_mw       DOUBLE PRECISION NOT NULL,
    efficiency            DOUBLE PRECISION NOT NULL DEFAULT 1.0,  -- round-trip; 1.0 satisfies both docs
    soc_floor_frac        DOUBLE PRECISION NOT NULL DEFAULT 0.33, -- team design choice
    strategic_reserve_frac DOUBLE PRECISION NOT NULL DEFAULT 0.0, -- team design choice
    -- event definition
    season                TEXT NOT NULL,
    date_start            DATE NOT NULL,
    date_end              DATE NOT NULL,
    min_stress_window_days INTEGER NOT NULL DEFAULT 2,
    severity_percentile   DOUBLE PRECISION NOT NULL,              -- 0.90, Architecture 2026-08-05 Component 3
    transmission_limit_mw  DOUBLE PRECISION,                      -- NULL = no limit (Goal B/C)
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE app.simulation_run (
    id               BIGSERIAL PRIMARY KEY,
    scenario_id      BIGINT NOT NULL REFERENCES app.scenario(id),
    code_version     TEXT NOT NULL,                 -- git sha of the engine
    dataset_versions JSONB NOT NULL,                -- {table: dataset_version} used
    status           TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'running', 'succeeded', 'failed')),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE app.run_result_hourly (
    run_id           BIGINT NOT NULL REFERENCES app.simulation_run(id),
    ts               TIMESTAMPTZ NOT NULL,
    soc              DOUBLE PRECISION NOT NULL,     -- state of charge (MWh)
    charge           DOUBLE PRECISION NOT NULL,
    discharge        DOUBLE PRECISION NOT NULL,
    discharge_peak   DOUBLE PRECISION NOT NULL,     -- peak-reduction component
    discharge_smooth DOUBLE PRECISION NOT NULL,     -- ramp-smoothing component
    net_load         DOUBLE PRECISION NOT NULL,     -- gross load minus discharge
    capacity_margin  DOUBLE PRECISION,
    PRIMARY KEY (run_id, ts)
);

CREATE TABLE app.run_result_daily (
    run_id                     BIGINT NOT NULL REFERENCES app.simulation_run(id),
    date                       DATE NOT NULL,
    budget                     DOUBLE PRECISION NOT NULL,  -- daily discharge budget (MWh)
    priority                   DOUBLE PRECISION NOT NULL,  -- 0.7*DemandPct + 0.3*WindForecast
    usable_energy              DOUBLE PRECISION NOT NULL,
    recharge_sufficiency_ratio DOUBLE PRECISION,
    PRIMARY KEY (run_id, date)
);

CREATE TABLE app.decision_package (
    run_id         BIGINT PRIMARY KEY REFERENCES app.simulation_run(id),
    payload        JSONB NOT NULL,                 -- structured inputs sent to the AI assistant
    annotation     TEXT,                           -- AI explanation, stored with provenance
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
