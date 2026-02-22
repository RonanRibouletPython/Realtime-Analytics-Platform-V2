#!/usr/bin/env bash
# scripts/post_create.sh
# Runs once after the devcontainer is created.
# Idempotent: safe to run multiple times.
set -euo pipefail

echo ""
echo "════════════════════════════════════════════════"
echo "  Post-create setup"
echo "════════════════════════════════════════════════"

# ── Git config ────────────────────────────────────────────────────────────────
echo ""
echo "▶ Configuring git..."
bash scripts/git_config.sh

# ── Install service dependencies ──────────────────────────────────────────────
echo ""
echo "▶ Installing Python dependencies..."
for svc in shared ingestion worker query_service; do
  if [ -f "services/$svc/pyproject.toml" ]; then
    echo "  Installing $svc..."
    cd "services/$svc" && uv sync --quiet && cd ../..
  fi
done

# ── Wait for Kafka and create topics ──────────────────────────────────────────
echo ""
echo "▶ Waiting for Kafka..."
RETRIES=30
until /opt/kafka/bin/kafka-topics.sh \
        --bootstrap-server localhost:9092 --list > /dev/null 2>&1; do
  RETRIES=$((RETRIES - 1))
  if [ $RETRIES -eq 0 ]; then
    echo "  ⚠️  Kafka not ready — run 'make kafka-topics' manually once it starts"
    break
  fi
  echo "  Waiting... ($RETRIES retries left)"
  sleep 3
done

if [ $RETRIES -gt 0 ]; then
  bash scripts/kafka_init.sh
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════"
echo "  ✅ Ready. Quick reference:"
echo ""
echo "  make up           Start infrastructure"
echo "  make migrate      Run DB migrations"
echo "  make kafka-topics Create Kafka topics"
echo "  make test         Run all tests"
echo "  make help         Show all commands"
echo "════════════════════════════════════════════════"
echo ""