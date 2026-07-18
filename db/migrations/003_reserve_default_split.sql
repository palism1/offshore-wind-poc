-- Offshore Wind Reserve — Phase 1 schema, migration 003
--
-- Team decision 2026-07-17: the protected reserve is a 20% floor plus a separate
-- 10% reserve of total storage (30% protected, 70% for regular operations),
-- replacing the earlier 33% floor placeholder. The engine already models the two
-- as separate fractions; this only realigns the app.scenario column DEFAULTS so a
-- scenario inserted without these values reflects the current team decision rather
-- than the stale placeholder. The API always inserts explicit values, so this is a
-- consistency/hygiene change, not a behavioural one.
--
-- Still open (not encoded here): when the 10% reserve and 20% floor may each be
-- drawn down. Until decided, the engine treats their sum as one protected floor.

ALTER TABLE app.scenario
    ALTER COLUMN soc_floor_frac SET DEFAULT 0.20,
    ALTER COLUMN strategic_reserve_frac SET DEFAULT 0.10;
