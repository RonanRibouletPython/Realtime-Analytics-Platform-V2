#!/usr/bin/env bash
# services/ingestion/run.sh
set -euo pipefail

cd "$(dirname "$0")"  # always run from the service root

exec uv run uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload