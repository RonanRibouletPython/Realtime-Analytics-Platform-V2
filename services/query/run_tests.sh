#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"  # always run from the service root

uv run pytest tests -v