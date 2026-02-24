import asyncio
import time
from datetime import UTC
from datetime import datetime as dt
from datetime import timezone as tz
from pathlib import Path

import structlog
from confluent_kafka import DeserializingConsumer, KafkaException, Message
from confluent_kafka.schema_registry import SchemaRegistryClient
from confluent_kafka.schema_registry.avro import AvroDeserializer
from confluent_kafka.serialization import StringDeserializer
from shared.models.metric import Metric

from app.core.database import AsyncSessionLocal
from app.core.dlq import send_to_dlq
from app.core.prometheus import tracker
from app.core.settings import settings

logger = structlog.get_logger()

# ── Avro deserialiser ─────────────────────────────────────────────────────────
_schema_registry = SchemaRegistryClient({"url": settings.SCHEMA_REGISTRY_URL})

_avro_dir = Path(__file__).parent.parent.parent / "shared" / "shared" / "avro"
_reader_schema = (_avro_dir / "metric_event_v3.avsc").read_text()

avro_deserializer = AvroDeserializer(
    schema_registry_client=_schema_registry,
    schema_str=_reader_schema,
)

# ── Consumer ──────────────────────────────────────────────────────────────────
consumer = DeserializingConsumer(
    {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "group.id": settings.KAFKA_CONSUMER_GROUP,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
        "key.deserializer": StringDeserializer("utf_8"),
        "value.deserializer": avro_deserializer,
    }
)

consumer.subscribe([settings.KAFKA_TOPIC_METRICS])


def _parse_timestamp(raw) -> dt:
    """
    Normalise the Avro timestamp field to a tz-aware UTC datetime.

    The confluent Avro deserialiser behaviour depends on the version:
    - Newer versions return a Python datetime directly (logical type resolved).
    - Older versions return a raw int (milliseconds since epoch).
    We handle both so the worker is resilient to library version changes.
    """
    if isinstance(raw, dt):
        # Already a datetime — just ensure it's tz-aware UTC
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    # Raw milliseconds since epoch
    return dt.fromtimestamp(raw / 1000, tz=UTC)


async def _process_message(message: Message) -> bool:
    """
    Process one Kafka message: deserialise → write to DB.

    Returns:
        True  → commit the offset (success, or permanent failure sent to DLQ)
        False → do NOT commit (transient failure — Kafka will redeliver)
    """
    start = time.time()
    payload = message.value()

    try:
        async with AsyncSessionLocal() as session:
            metric = Metric(
                tenant_id=payload.get("tenant_id", "default"),
                name=payload["name"],
                value=payload["value"],
                timestamp=_parse_timestamp(payload["timestamp"]),
                labels=payload.get("labels", {}),
                environment=payload.get("environment"),
            )
            session.add(metric)
            await session.commit()

        latency_ms = (time.time() - start) * 1000
        tracker.record_success(latency_ms)

        logger.info(
            "metric_written",
            name=metric.name,
            tenant_id=metric.tenant_id,
            value=metric.value,
            latency_ms=round(latency_ms, 2),
        )
        return True

    except ValueError as e:
        logger.error("invalid_payload_sent_to_dlq", error=str(e))
        await send_to_dlq(message, error=str(e), reason="ValueError")
        tracker.record_dlq(reason="ValueError")
        return True

    except Exception as e:
        logger.error("db_write_failed_will_retry", error=str(e))
        tracker.record_failure()
        return False


async def consume() -> None:
    logger.info("worker_started", topic=settings.KAFKA_TOPIC_METRICS)
    loop = asyncio.get_running_loop()

    try:
        while True:
            message: Message | None = await loop.run_in_executor(
                None,
                consumer.poll,
                1.0,
            )

            if message is None:
                continue

            if message.error():
                raise KafkaException(message.error())

            committed = await _process_message(message)

            if committed:
                consumer.commit(message=message)

    except asyncio.CancelledError:
        logger.info("worker_cancelled")
    except Exception as e:
        logger.critical("worker_crashed", error=str(e))
        raise
    finally:
        consumer.close()
        logger.info("worker_stopped")
