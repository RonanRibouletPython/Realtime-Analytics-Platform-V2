#!/usr/bin/env bash
# scripts/kafka_init.sh
# Creates all required Kafka topics.
# Run once after Kafka starts. Idempotent (--if-not-exists).
set -euo pipefail

KAFKA_BIN="/opt/kafka/bin/kafka-topics.sh"
BOOTSTRAP="localhost:9092"

echo "Creating Kafka topics..."

$KAFKA_BIN --bootstrap-server "$BOOTSTRAP" \
  --create --if-not-exists \
  --topic metrics_ingestion \
  --partitions 3 \
  --replication-factor 1
echo "metrics_ingestion (3 partitions)"

# Dead Letter Queue: 1 partition is fine — DLQ volume is low by design.
# If your DLQ is getting high volume, that's the problem to fix, not the partition count.
$KAFKA_BIN --bootstrap-server "$BOOTSTRAP" \
  --create --if-not-exists \
  --topic metrics_dlq \
  --partitions 1 \
  --replication-factor 1
echo "metrics_dlq (1 partition)"

echo ""
echo "Topics:"
$KAFKA_BIN --bootstrap-server "$BOOTSTRAP" --list