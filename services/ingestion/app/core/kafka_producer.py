import asyncio
import time
from datetime import timezone as tz
from enum import Enum
from pathlib import Path

import structlog
from confluent_kafka import SerializingProducer
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroSerializer
from confluent_kafka.serialization import (
    MessageField,
    SerializationContext,
    StringSerializer,
)

from app.core.settings import settings

logger = structlog.get_logger()


# ── Schema version enum ───────────────────────────────────────────────────────
# Callers import SchemaVersion and pass it to produce_metric().
# Enum prevents silent typos like "V 2" or "v 2" from falling through.
class SchemaVersion(str, Enum):
    V1 = "v1"
    V2 = "v2"
    V3 = "v3"  # current default — includes tenant_id


# ── Avro setup ────────────────────────────────────────────────────────────────
# Schemas live in shared/ — single source of truth.
# Path is resolved relative to the installed shared package.
_schema_registry = SchemaRegistryClient({"url": settings.SCHEMA_REGISTRY_URL})
_avro_dir = Path(__file__).parent.parent.parent.parent / "shared" / "shared" / "avro"


def _load_schema(filename: str) -> str:
    path = _avro_dir / filename
    with open(path) as f:
        return f.read()


def _metric_to_avro(metric: dict, ctx) -> dict:
    """
    Convert a metric dict to Avro-serialisable form.

    The timestamp comes in as a Python datetime — Avro needs milliseconds
    since epoch (timestamp-millis logical type). Everything else passes through.
    The v1 serialiser ignores keys not in its schema (environment, tenant_id)
    so one function works for all three versions.
    """
    timestamp = metric.get("timestamp")
    if timestamp is None:
        raise ValueError("'timestamp' is required and cannot be None")

    return {
        "name": metric["name"],
        "value": metric["value"],
        "timestamp": int(timestamp.astimezone(tz.utc).timestamp() * 1000),
        "labels": metric.get("labels", {}),
        "environment": metric.get("environment"),
        "tenant_id": metric.get("tenant_id", "default"),
    }


_serializers: dict[SchemaVersion, AvroSerializer] = {
    SchemaVersion.V1: AvroSerializer(
        _schema_registry, _load_schema("metric_event_v1.avsc"), _metric_to_avro
    ),
    SchemaVersion.V2: AvroSerializer(
        _schema_registry, _load_schema("metric_event_v2.avsc"), _metric_to_avro
    ),
    SchemaVersion.V3: AvroSerializer(
        _schema_registry, _load_schema("metric_event_v3.avsc"), _metric_to_avro
    ),
}

# Single shared producer — no value.serializer set at construction because
# we inject the correct one per-message via SerializationContext.
_producer = SerializingProducer(
    {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "key.serializer": StringSerializer("utf_8"),
    }
)


# ── Callbacks ─────────────────────────────────────────────────────────────────
def _on_delivery(err, msg) -> None:
    if err:
        logger.error("kafka_delivery_failed", error=str(err), topic=msg.topic())
    else:
        logger.info(
            "kafka_delivery_confirmed",
            topic=msg.topic(),
            partition=msg.partition(),
            offset=msg.offset(),
        )


# ── Public API ────────────────────────────────────────────────────────────────
async def produce_metric(
    metric: dict,
    version: SchemaVersion = SchemaVersion.V3,
) -> None:
    """
    Produce a metric event to Kafka.

    Non-blocking: puts the message in the local producer buffer and returns.
    Delivery confirmation comes asynchronously via _on_delivery().

    Args:
        metric:  Metric payload as a dict (from MetricCreate.model_dump()).
        version: Avro schema version. Defaults to V3 (current).
    """
    serializer = _serializers[version]
    ctx = SerializationContext(settings.KAFKA_TOPIC_METRICS, MessageField.VALUE)
    loop = asyncio.get_running_loop()

    await loop.run_in_executor(
        None,
        lambda: (
            _producer.produce(
                topic=settings.KAFKA_TOPIC_METRICS,
                key=metric.get("name"),
                value=serializer(metric, ctx),
                on_delivery=_on_delivery,
            ),
            _producer.poll(0),
        ),
    )


async def check_kafka_health() -> None:
    """Raises if Kafka is unreachable. Used by the /health endpoint."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: _producer.list_topics(timeout=3.0),
    )


def flush_producer() -> None:
    """
    Flush all buffered messages. Call at shutdown to avoid losing in-flight events.
    Blocks until all messages are delivered or the timeout expires.
    """
    logger.info("kafka_producer_flushing")
    start = time.time()
    remaining = _producer.flush(timeout=10.0)
    elapsed = round(time.time() - start, 3)

    if remaining > 0:
        logger.error("kafka_flush_incomplete", remaining=remaining, elapsed_sec=elapsed)
    else:
        logger.info("kafka_flush_complete", elapsed_sec=elapsed)
