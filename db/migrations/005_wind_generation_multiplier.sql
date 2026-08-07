-- Offshore Wind Reserve — Phase 1 schema, migration 005
--
-- Change 8, week 4B spec sync: a user-supplied multiplier that scales historical
-- wind before the engine sees it (D11, D12; Component 1 User Inputs). The default
-- 1.0 matches Component 1, so every existing row reads back unchanged: no backfill
-- is needed.
--
-- Still open (not encoded here): the source's validation range for this field is
-- "@" and the field is described as whole-number (OPEN team question
-- wind_multiplier_range). This migration only enforces non-negative.

ALTER TABLE app.scenario
    ADD COLUMN wind_generation_multiplier DOUBLE PRECISION NOT NULL DEFAULT 1.0;
ALTER TABLE app.scenario
    ADD CONSTRAINT scenario_wind_multiplier_non_negative
        CHECK (wind_generation_multiplier >= 0);
