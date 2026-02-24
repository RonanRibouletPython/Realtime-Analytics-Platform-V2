#!/usr/bin/env bash
# scripts/kafka_init.sh
# Creates all required Kafka topics.
# Run once after Kafka starts. Idempotent (--if-not-exists).
set -euo pipefail

# Kafka binary lives inside the kafka container, not the devcontainer.
# We exec into it from the host via docker.
KAFKA_CONTAINER="realtime-analytics-platform-v2_devcontainer-kafka-1"
KAFKA_BIN="/opt/kafka/bin/kafka-topics.sh"
BOOTSTRAP="localhost:9092"

echo "Creating Kafka topics..."

docker exec "$KAFKA_CONTAINER" \
  "$KAFKA_BIN" --bootstrap-server "$BOOTSTRAP" \
  --create --if-not-exists \
  --topic metrics_ingestion \
  --partitions 3 \
  --replication-factor 1
echo "metrics_ingestion (3 partitions)"

# DLQ: 1 partition is intentional — if DLQ volume is high,
# that's the bug to fix, not the partition count.
docker exec "$KAFKA_CONTAINER" \
  "$KAFKA_BIN" --bootstrap-server "$BOOTSTRAP" \
  --create --if-not-exists \
  --topic metrics_dlq \
  --partitions 1 \
  --replication-factor 1
echo "metrics_dlq (1 partition)"