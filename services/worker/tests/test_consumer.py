from datetime import UTC
from datetime import datetime as dt
from datetime import timezone as tz
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.kafka_consumer import _process_message


def _make_message(payload: dict | None = None, error=None) -> MagicMock:
    """Build a fake confluent_kafka.Message for testing."""
    msg = MagicMock()
    msg.value.return_value = payload
    msg.error.return_value = error
    msg.topic.return_value = "metrics_ingestion"
    msg.partition.return_value = 0
    msg.offset.return_value = 42
    msg.key.return_value = b"cpu_usage"
    msg.timestamp.return_value = (1, 1_700_000_000_000)
    return msg


VALID_PAYLOAD = {
    "tenant_id": "acme",
    "name": "cpu_usage",
    "value": 72.5,
    "timestamp": 1_700_000_000_000,  # millis
    "labels": {"host": "server-1"},
    "environment": "production",
}


@pytest.mark.asyncio
async def test_valid_message_returns_true_and_commits():
    msg = _make_message(VALID_PAYLOAD)

    with patch("app.kafka_consumer.AsyncSessionLocal") as mock_session_cls:
        session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = session

        result = await _process_message(msg)

    assert result is True
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_name_routes_to_dlq_and_returns_true():
    bad_payload = {**VALID_PAYLOAD, "name": None}
    msg = _make_message(bad_payload)

    with (
        patch("app.kafka_consumer.AsyncSessionLocal") as mock_session_cls,
        patch("app.kafka_consumer.send_to_dlq", new_callable=AsyncMock) as mock_dlq,
    ):
        session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = session
        # Simulate DB raising ValueError on null name
        session.commit.side_effect = ValueError("name cannot be null")

        result = await _process_message(msg)

    assert result is True  # commit offset — DLQ handled it
    mock_dlq.assert_awaited_once()


@pytest.mark.asyncio
async def test_db_error_returns_false_for_retry():
    msg = _make_message(VALID_PAYLOAD)

    with patch("app.kafka_consumer.AsyncSessionLocal") as mock_session_cls:
        session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = session
        session.commit.side_effect = Exception("connection refused")

        result = await _process_message(msg)

    assert result is False  # do not commit — Kafka will redeliver


@pytest.mark.asyncio
async def test_timestamp_conversion():
    """Avro timestamp-millis must be converted to tz-aware UTC datetime."""
    msg = _make_message(VALID_PAYLOAD)
    written_metric = None

    with patch("app.kafka_consumer.AsyncSessionLocal") as mock_session_cls:
        session = AsyncMock()
        mock_session_cls.return_value.__aenter__.return_value = session

        def capture_add(metric):
            nonlocal written_metric
            written_metric = metric

        session.add.side_effect = capture_add
        await _process_message(msg)

    assert written_metric is not None
    assert written_metric.timestamp.tzinfo is not None
    expected = dt.fromtimestamp(1_700_000_000_000 / 1000, tz=UTC)
    assert written_metric.timestamp == expected
