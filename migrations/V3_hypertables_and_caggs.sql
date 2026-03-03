-- V3_hypertables_and_caggs.sql
-- Phase 3: Convert metrics to a TimescaleDB hypertable, add continuous
-- aggregates for 1-minute and 1-hour rollups, and set retention policies
--
-- Run order matters:
--   1. create_hypertable()          — must run before any cagg references the table
--   2. CREATE MATERIALIZED VIEW     — caggs on top of the hypertable
--   3. add_continuous_aggregate_policy() — keeps caggs fresh automatically
--   4. add_retention_policy()       — auto-drops old chunks
--   5. CALL refresh_continuous_aggregate() — backfill existing data


-- 1. Convert to hypertable
-- chunk_time_interval = 1 day: each chunk holds 1 day of data.
-- Good default for a metrics workload writing thousands of rows/day.
-- Tune down to 1 hour if you're writing millions/day.
SELECT create_hypertable(
    'metrics',
    'timestamp',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists       => TRUE,   -- safe to re-run
    migrate_data        => TRUE    -- moves existing rows into the first chunk
);


-- 2. 1-minute continuous aggregate
-- Materialises per-minute summaries so the query service never hits raw rows
-- for recent-history queries (last hour, last 6 hours)
-- timescaledb.materialized_only = false: real-time aggregation fills the gap
-- between the last refresh and now — no stale data at the edge
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_1min
WITH (
    timescaledb.continuous,
    timescaledb.materialized_only = false
) AS
SELECT
    time_bucket('1 minute', timestamp)                   AS bucket,
    tenant_id,
    name,
    avg(value)                                           AS avg_value,
    min(value)                                           AS min_value,
    max(value)                                           AS max_value,
    count(*)                                             AS sample_count,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY value)  AS p95_value,
    percentile_cont(0.99) WITHIN GROUP (ORDER BY value)  AS p99_value
FROM metrics
GROUP BY bucket, tenant_id, name
WITH NO DATA;


-- 3. 1-hour continuous aggregate (rolls up from 1-min)
-- Covers medium-range queries (last 24 hours, last 7 days)
-- Built on top of metrics_1min, not raw metrics — efficient hierarchical rollup
CREATE MATERIALIZED VIEW IF NOT EXISTS metrics_1hour
WITH (
    timescaledb.continuous,
    timescaledb.materialized_only = false
) AS
SELECT
    time_bucket('1 hour', bucket)  AS bucket,
    tenant_id,
    name,
    avg(avg_value)                 AS avg_value,
    min(min_value)                 AS min_value,
    max(max_value)                 AS max_value,
    sum(sample_count)              AS sample_count,
    max(p95_value)                 AS p95_value,
    max(p99_value)                 AS p99_value
FROM metrics_1min
GROUP BY time_bucket('1 hour', bucket), tenant_id, name
WITH NO DATA;


-- 4. Refresh policies
-- These tell TimescaleDB's background job to keep the caggs materialised
-- Without these, caggs only refresh on manual CALL refresh_continuous_aggregate()

-- 1-min cagg: refresh every minute, covering data from 10min ago to 1min ago
-- The gap (end_offset = 1min) avoids refreshing data that's still being written
SELECT add_continuous_aggregate_policy(
    'metrics_1min',
    start_offset      => INTERVAL '10 minutes',
    end_offset        => INTERVAL '1 minute',
    schedule_interval => INTERVAL '1 minute',
    if_not_exists     => TRUE
);

-- 1-hour cagg: refresh every 15 minutes, covering data from 2h ago to 1h ago
SELECT add_continuous_aggregate_policy(
    'metrics_1hour',
    start_offset      => INTERVAL '2 hours',
    end_offset        => INTERVAL '1 hour',
    schedule_interval => INTERVAL '15 minutes',
    if_not_exists     => TRUE
);


-- 5. Retention policies
-- Raw rows: keep 30 days (high resolution, high storage cost)
-- 1-min rollups: keep 90 days (medium resolution)
-- 1-hour rollups: keep 1 year (low resolution, long history)
SELECT add_retention_policy(
    'metrics',
    INTERVAL '30 days',
    if_not_exists => TRUE
);

SELECT add_retention_policy(
    'metrics_1min',
    INTERVAL '90 days',
    if_not_exists => TRUE
);

SELECT add_retention_policy(
    'metrics_1hour',
    INTERVAL '365 days',
    if_not_exists => TRUE
);


-- 6. Backfill existing data
-- Refresh caggs over all existing data so the query service has
-- something to work with immediately after migration
CALL refresh_continuous_aggregate('metrics_1min',  NULL, NULL);
CALL refresh_continuous_aggregate('metrics_1hour', NULL, NULL);