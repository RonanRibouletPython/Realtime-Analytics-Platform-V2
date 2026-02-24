#!/usr/bin/env bash
# services/worker/run.sh
set -euo pipefail

cd "$(dirname "$0")"  # always run from the service root

exec uv run python main.py