-- infrastructure/postgres/init.sql
-- Runs ONCE when the container is first created (via docker-entrypoint-initdb.d).
-- Rule: extensions only. Table schemas live in migrations/.
-- This keeps the answer to "what does the DB look like?" in one place.

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;