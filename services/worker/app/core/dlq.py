import json
from datetime import datetime as dt
from datetime import timezone as tz

import structlog
from app.core.settings import settings
from confluent_kafka import Message, Producer

logger = structlog.get_logger()

# Separate plain producer — intentional.
# The DLQ must accept any payload format, including messages that failed
# Avro deserialisation. Using the Avro producer here would be circular.
_dlq_producer = Producer(
    {
        "bootstrap.servers": settings.KAFKA_BOOTSTRAP_SERVERS,
        "acks": "all",  # DLQ messages must be durable — don't compromise here
    }
)


async def send_to_dlq(message: Message, error: str, reason: str) -> None:
    """
    Route a failed Kafka message to the Dead Letter Queue.

    Wraps the original message in a forensics envelope with everything
    needed to debug, replay, or alert on the failure later.

    Args:
        message: The original confluent_kafka.Message (carries topic,
                 partition, offset, key, and raw bytes).
        error:   Human-readable description of what went wrong.
        reason:  Short machine-readable code for Prometheus labelling,
                 e.g. "ValueError", "deserialization_error", "db_error"
    """
    # Raw bytes as hex — the only safe representation when the bytes
    # themselves may have caused deserialisation to fail.
    raw_hex: str | None = None
    if message.value() is not None:
        try:
            raw_hex = message.value().hex()
        except Exception:
            raw_hex = "<unreadable>"

    envelope = {
        "dlq_metadata": {
            "routed_at_utc": dt.now(tz.utc).isoformat(),
            "reason": reason,
            "error": error,
        },
        # Everything needed to find and replay the original message
        "source": {
            "topic": message.topic(),
            "partition": message.partition(),
            "offset": message.offset(),
            "timestamp_ms": message.timestamp()[1] if message.timestamp() else None,
            "key": message.key().decode("utf-8", errors="replace")
            if message.key()
            else None,
            "raw_value_hex": raw_hex,
        },
    }

    try:
        _dlq_producer.produce(
            topic=settings.KAFKA_TOPIC_DLQ,
            value=json.dumps(envelope).encode("utf-8"),
            key=message.key(),
        )
        # flush() not poll(0) — ensures delivery before we commit the original offset.
        # poll(0) only triggers callbacks, it doesn't guarantee the message was sent.
        _dlq_producer.flush(timeout=5.0)

        logger.warning(
            "message_routed_to_dlq",
            reason=reason,
            source_topic=message.topic(),
            source_partition=message.partition(),
            source_offset=message.offset(),
        )

    except Exception as e:
        # If DLQ itself fails we can't do much — log at CRITICAL so it pages.
        # In production you'd also write to a local fallback file here.
        logger.critical(
            "dlq_send_failed",
            error=str(e),
            source_topic=message.topic(),
            source_partition=message.partition(),
            source_offset=message.offset(),
        )
