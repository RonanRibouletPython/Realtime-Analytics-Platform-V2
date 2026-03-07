#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"  # always run from the service root

exec uv run python generator.py