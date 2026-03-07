-- migrations/V3_hypertables_and_caggs.sql
-- Phase 3: Convert metrics to TimescaleDB hypertable with continuous aggregates
--
-- This migration creates STRUCTURE only:
-- - Hypertable conversion
-- - Continuous aggregate definitions
-- - Refresh and retention policies
--
-- BACKFILLING is handled separately (see scripts/backfill_continuous_aggregates.sh)
-- This separation allows:
-- - Fast migrations (< 5 seconds even on large tables)
-- - Idempotent re-runs (safe to retry if interrupted)
-- - Transaction safety (no CALL statements that break transactions)

-- STEP 1: Pre-migration validation and cleanup

DO $$
BEGIN
    -- Drop primary key constraint if exists (TimescaleDB requirement)
    IF EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conrelid = 'metrics'::regclass AND contype = 'p'
    ) THEN
        ALTER TABLE metrics DROP CONSTRAINT metrics_pkey;
        RAISE NOTICE 'Dropped primary key constraint';
    END IF;
END $$;



-- STEP 2: Convert to hypertable

SELECT create_hypertable(
    'metrics',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE,
    migrate_data        => TRUE
);



-- STEP 3: Create continuous aggregates (empty - backfill happens separately)

CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_1min
WITH (
    timescaledb.continuous,
    timescaledb.materialized_only = false
) AS
SELECT
    time_bucket('1 minute', timestamp) AS bucket,
    tenant_id,
    name,
    avg(value) AS avg_value,
    min(value) AS min_value,
    max(value) AS max_value,
    count(*) AS sample_count,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY value) AS p95_value,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY value) AS p99_value
FROM metrics
GROUP BY bucket, tenant_id, name
WITH NO DATA;  -- Empty until backfill

CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_1hour
WITH (
    timescaledb.continuous,
    timescaledb.materialized_only = false
) AS
SELECT
    time_bucket('1 hour', bucket) AS bucket,
    tenant_id,
    name,
    avg(avg_value) AS avg_value,
    min(min_value) AS min_value,
    max(max_value) AS max_value,
    sum(sample_count) AS sample_count,
    max(p95_value) AS p95_value,
    max(p99_value) AS p99_value
FROM metrics_1min
GROUP BY time_bucket('1 hour', bucket), tenant_id, name
WITH NO DATA;  -- Empty until backfill



-- STEP 4: Add refresh policies

SELECT add_continuous_aggregate_policy(
    'metrics_1min',
    start_offset      => INTERVAL '2 hours',
    end_offset        => INTERVAL '5 minutes',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists     => TRUE
);

SELECT add_continuous_aggregate_policy(
    'metrics_1hour',
    start_offset      => INTERVAL '7 days',
    end_offset        => INTERVAL '2 hours',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists     => TRUE
);



-- STEP 5: Add retention policies

SELECT add_retention_policy('metrics', INTERVAL '30 days', if_not_exists => TRUE);
SELECT add_retention_policy('metrics_1min', INTERVAL '90 days', if_not_exists => TRUE);
SELECT add_retention_policy('metrics_1hour', INTERVAL '365 days', if_not_exists => TRUE);



-- STEP 6: Verification (informational output)

DO $$
BEGIN
    RAISE NOTICE '=== Migration V3 Complete ===';
    RAISE NOTICE 'Hypertable created: %', (SELECT COUNT(*) FROM timescaledb_information.hypertables WHERE hypertable_name = 'metrics');
    RAISE NOTICE 'Continuous aggregates created: %', (SELECT COUNT(*) FROM timescaledb_information.continuous_aggregates);
    RAISE NOTICE 'Background jobs scheduled: %', (SELECT COUNT(*) FROM timescaledb_information.jobs WHERE proc_name IN ('policy_refresh_continuous_aggregate', 'policy_retention'));
    RAISE NOTICE '';
    RAISE NOTICE 'NEXT STEP: Run backfill script to populate continuous aggregates:';
    RAISE NOTICE '  bash scripts/backfill_continuous_aggregates.sh';
END $$;