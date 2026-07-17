-- Offshore Wind Reserve — Phase 1 schema, migration 002
--
-- Closes gaps surfaced when wiring the Phase 4 API (its Pydantic wire contract and
-- route behaviour) to the Phase 1 schema. Each change below maps a value the API
-- already produces/returns to a place to store it. No behavioural change to the
-- engine; this is persistence plumbing only.
--
-- Gaps closed:
--   1. app.scenario was missing three inputs the API accepts and every run consumes:
--      available_capacity_mw, peak_weight, smooth_weight. Added as columns so a
--      scenario round-trips losslessly (normalized, not JSONB).
--   2. app.run_result_hourly stored net_load but not gross_load, which the API
--      returns per hour. Added gross_load.
--   3. Run-level result scalars (final_soc, baseline/reserve peak) and the detected
--      stress windows had nowhere to live. Stored as a single result_summary JSONB
--      on the run (the "hybrid" choice: normalized daily/hourly tables as designed,
--      JSONB only for the small run-level summary + stress windows).

ALTER TABLE app.scenario
    ADD COLUMN IF NOT EXISTS available_capacity_mw DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS peak_weight  DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    ADD COLUMN IF NOT EXISTS smooth_weight DOUBLE PRECISION NOT NULL DEFAULT 0.5;

ALTER TABLE app.run_result_hourly
    ADD COLUMN IF NOT EXISTS gross_load DOUBLE PRECISION;

-- Run-level summary: {final_soc, baseline_peak_mw, reserve_peak_mw,
--                     stress_windows: [{start, end, days}, ...]}
-- Populated when a run reaches 'succeeded'; NULL before then.
ALTER TABLE app.simulation_run
    ADD COLUMN IF NOT EXISTS result_summary JSONB;
