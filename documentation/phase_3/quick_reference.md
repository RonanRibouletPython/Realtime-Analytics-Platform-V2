# Phase 3 Quick Reference

Fast lookup guide for common operations.

## Common Queries

### Check System Status
```bash
# One-liner for complete status
psql postgresql://analytics:analytics@localhost:5432/analytics -c "SELECT 'Hypertable Chunks' as metric, num_chunks::text as value FROM timescaledb_information.hypertables WHERE hypertable_name = 'metrics' UNION ALL SELECT 'Raw Metrics', COUNT(*)::text FROM metrics UNION ALL SELECT 'Cagg 1-Min', COUNT(*)::text FROM metrics_1min UNION ALL SELECT 'Cagg 1-Hour', COUNT(*)::text FROM metrics_1hour UNION ALL SELECT 'Data Lag', (NOW() - MAX(timestamp))::text FROM metrics UNION ALL SELECT 'Cagg Lag', (NOW() - MAX(bucket))::text FROM metrics_1min;"
```

### Recent Metrics
```bash
psql postgresql://analytics:analytics@localhost:5432/analytics -c "SELECT tenant_id, name, value, timestamp FROM metrics ORDER BY timestamp DESC LIMIT 10;"
```

### Continuous Aggregate Performance
```bash
# Raw table query
psql -c "EXPLAIN ANALYZE SELECT tenant_id, AVG(value) FROM metrics WHERE timestamp >= NOW() - INTERVAL '1 hour' GROUP BY tenant_id;"

# Aggregate query
psql -c "EXPLAIN ANALYZE SELECT tenant_id, AVG(avg_value) FROM metrics_1min WHERE bucket >= NOW() - INTERVAL '1 hour' GROUP BY tenant_id;"
```

## Troubleshooting

### Continuous Aggregate Not Refreshing

**Check job status:**
```sql
SELECT job_id, last_run_status, total_failures, next_start
FROM timescaledb_information.job_stats
WHERE job_id IN (SELECT job_id FROM timescaledb_information.jobs WHERE proc_name = 'policy_refresh_continuous_aggregate');
```

**Manual refresh:**
```sql
CALL refresh_continuous_aggregate('metrics_1min', NULL, NULL);
```

### High Storage Usage

**Check chunk sizes:**
```sql
SELECT chunk_name, pg_size_pretty(chunk_size) as size
FROM timescaledb_information.chunks
WHERE hypertable_name = 'metrics'
ORDER BY chunk_size DESC;
```

**Check retention policy:**
```sql
SELECT * FROM timescaledb_information.jobs WHERE proc_name = 'policy_retention';
```

### Slow Queries

**Verify using continuous aggregates:**
```sql
-- ❌ BAD: Hitting raw table
SELECT * FROM metrics WHERE timestamp >= NOW() - INTERVAL '1 day';

-- ✅ GOOD: Using aggregate
SELECT * FROM metrics_1min WHERE bucket >= NOW() - INTERVAL '1 day';
```

## Maintenance Operations

### Backfill Continuous Aggregates
```bash
bash scripts/backfill_continuous_aggregates.sh
```

### Run Migrations
```bash
cd /workspace/migrations
uv run apply_migrations.py
```

### Check Migration Status
```sql
SELECT version, name, applied_at, success FROM schema_migrations ORDER BY version;
```

## Performance Tuning

### Adjust Refresh Frequency

**If database CPU is high:**
```sql
-- Increase interval from 1 minute to 5 minutes
SELECT alter_job(1001, schedule_interval => INTERVAL '5 minutes');
```

**If data freshness is critical:**
```sql
-- Decrease interval to 30 seconds
SELECT alter_job(1001, schedule_interval => INTERVAL '30 seconds');
```

### Adjust Chunk Size

**For higher write volume:**
```sql
-- Change to 1-hour chunks (cannot change existing, only future)
SELECT set_chunk_time_interval('metrics', INTERVAL '1 hour');
```

## Monitoring

### Key Metrics to Track
```sql
SELECT 
    'chunk_count' as metric,
    (SELECT COUNT(*) FROM timescaledb_information.chunks WHERE hypertable_name = 'metrics') as value
UNION ALL
SELECT 'cagg_lag_minutes',
       EXTRACT(EPOCH FROM (NOW() - MAX(bucket)))/60
FROM metrics_1min
UNION ALL
SELECT 'job_failures',
       SUM(total_failures)::text
FROM timescaledb_information.job_stats;
```

### Set Up Alerts

**Grafana Alert Example:**
```sql
-- Alert if continuous aggregate lag > 10 minutes
SELECT EXTRACT(EPOCH FROM (NOW() - MAX(bucket)))/60 as lag_minutes
FROM metrics_1min
HAVING EXTRACT(EPOCH FROM (NOW() - MAX(bucket)))/60 > 10;
```

## Useful Scripts

Located in `/workspace/scripts/`:
- `explore_timescaledb.sh` - Interactive query menu
- `backfill_continuous_aggregates.sh` - Backfill historical data
- `query_helpers.sh` - Common query shortcuts
- `db_connect.sh` - Quick psql connection

---
**See also:** [Full Technical Summary](./phase3_timescaledb_integration.md)
