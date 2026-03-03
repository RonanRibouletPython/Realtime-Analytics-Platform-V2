-- V2_add_tenant_id.sql
-- Adds tenant_id for multi-tenancy (introduced with Avro schema v3)
-- Default 'default' backfills all existing rows transparently

ALTER TABLE metrics
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64) NOT NULL DEFAULT 'default';

-- Composite index covering the primary query pattern in Phase 3:
-- WHERE tenant_id = X AND name = Y AND timestamp BETWEEN A AND B
CREATE INDEX IF NOT EXISTS idx_metrics_tenant_name_time
    ON metrics (tenant_id, name, timestamp);

CREATE INDEX IF NOT EXISTS ix_metrics_tenant_id
    ON metrics (tenant_id);