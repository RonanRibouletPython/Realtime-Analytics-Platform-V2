-- V1_create_metrics_table.sql
-- Baseline schema: the metrics table with v1/v2 fields
-- IF NOT EXISTS guards make this safe to run against a DB where
-- SQLAlchemy's create_all already created the table on first boot

CREATE TABLE IF NOT EXISTS metrics (
    id          SERIAL                   NOT NULL,
    name        VARCHAR                  NOT NULL,
    value       DOUBLE PRECISION         NOT NULL,
    timestamp   TIMESTAMPTZ              NOT NULL DEFAULT now(),
    labels      JSONB                    NOT NULL DEFAULT '{}',
    environment VARCHAR
);

-- Index on id for lookups (non-unique)
CREATE INDEX IF NOT EXISTS ix_metrics_id
    ON metrics (id);

CREATE INDEX IF NOT EXISTS ix_metrics_name
    ON metrics (name);