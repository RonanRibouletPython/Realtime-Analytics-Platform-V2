#!/bin/bash
# scripts/backfill_continuous_aggregates.sh
# Backfills continuous aggregates after V3 migration

set -e

# Database connection (works with Docker network_mode: service:db)
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_USER="${DB_USER:-analytics}"
DB_PASSWORD="${DB_PASSWORD:-analytics}"
DB_NAME="${DB_NAME:-analytics}"

# Full connection string
PSQL_CONN="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

echo "========================================"
echo "Backfilling Continuous Aggregates"
echo "========================================"
echo "Database: ${DB_HOST}:${DB_PORT}/${DB_NAME}"
echo ""

echo "[1/2] Backfilling metrics_1min..."
psql "${PSQL_CONN}" -c "CALL refresh_continuous_aggregate('metrics_1min', NULL, NULL);"

echo "[2/2] Backfilling metrics_1hour..."
psql "${PSQL_CONN}" -c "CALL refresh_continuous_aggregate('metrics_1hour', NULL, NULL);"

echo ""
echo "Backfill complete! Verifying data..."
echo ""

psql "${PSQL_CONN}" << 'SQL'
SELECT 
    'metrics_1min' as view_name,
    COUNT(*) as rows,
    MIN(bucket) as oldest_bucket,
    MAX(bucket) as newest_bucket
FROM metrics_1min
UNION ALL
SELECT 
    'metrics_1hour',
    COUNT(*),
    MIN(bucket),
    MAX(bucket)
FROM metrics_1hour;
SQL

echo ""
echo "✓ Continuous aggregates are ready!"
echo ""
echo "Next steps:"
echo "  - Start load generator to see real-time refresh"
echo "  - Query aggregates: bash scripts/db_connect.sh"
EOF