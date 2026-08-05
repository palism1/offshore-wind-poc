-- Offshore Wind Reserve — Phase 2 ETL, migration 004
-- raw.hourly_fuel_gen: EIA-930 hourly net generation by fuel type, one row per
-- (source, ts, fuel_code). Feeds the Fuel-Fired Generation Offset metric.
--
-- Why a new table and not raw.hourly_wind: that table's primary key is
-- (source, ts, horizon_days) and it carries no fuel column, so oil and gas rows
-- collide under a shared source string, and a per-fuel source string would label
-- oil rows as wind. See docs/PLAN_EIA_OIL_GAS.md decision D1.
--
-- Why interval_minutes is stored and not assumed: energy is
-- gen_mw * interval_minutes / 60. See decision D3.
--
-- What gen_mw = 0.0 means: "zero output OR not reported". gridstatus pivots with
-- aggfunc='sum', and pandas sums an all-null group to 0.0, so a null EIA
-- telemetry value is already 0.0 before it reaches this table. ISO-NE petroleum
-- output is legitimately 0.0 for most hours, so the two cases cannot be told
-- apart here. Do not read a zero as evidence of a reporting outage, and do not
-- read it as evidence of a real measurement.
--
-- What a missing row means: EIA omits an hour that has no row for the fuel, so a
-- gap in ts is a gap in the source, never a NaN. Use extract.hourly_gaps.

CREATE TABLE raw.hourly_fuel_gen (
    ts               TIMESTAMPTZ      NOT NULL,
    fuel_code        TEXT             NOT NULL,  -- EIA-930 energy source code: 'OIL', 'NG'
    gen_mw           DOUBLE PRECISION NOT NULL,  -- avg MW over the interval; see note below
    interval_minutes DOUBLE PRECISION NOT NULL,
    -- provenance (db/migrations/001_init.sql header)
    source           TEXT             NOT NULL,
    retrieved_at     TIMESTAMPTZ      NOT NULL DEFAULT now(),
    source_query     TEXT             NOT NULL,
    dataset_version  TEXT             NOT NULL,
    PRIMARY KEY (source, ts, fuel_code),
    CONSTRAINT hourly_fuel_gen_fuel_code_upper
        CHECK (fuel_code <> '' AND fuel_code = upper(fuel_code)),
    CONSTRAINT hourly_fuel_gen_interval_positive
        CHECK (interval_minutes > 0)
);
SELECT create_hypertable('raw.hourly_fuel_gen', 'ts', if_not_exists => TRUE);
