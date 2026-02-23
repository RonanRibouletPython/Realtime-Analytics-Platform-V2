from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_kafka():
    """Prevent real Kafka connections during tests."""
    with patch("app.core.kafka_producer._producer") as mock:
        mock.produce = AsyncMock()
        mock.poll = AsyncMock()
        mock.list_topics = AsyncMock()
        yield mock


def test_health_returns_200():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_ingest_metric_returns_202():
    with patch("app.api.metrics.produce_metric", new_callable=AsyncMock):
        response = client.post(
            "/api/v1/metrics",
            json={
                "name": "cpu_usage",
                "value": 75.5,
                "tenant_id": "test-tenant",
                "environment": "test",
                "labels": {"host": "server-1"},
            },
        )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"


def test_ingest_metric_missing_name_returns_422():
    response = client.post(
        "/api/v1/metrics",
        json={"value": 42.0},
    )
    assert response.status_code == 422


def test_list_metrics_invalid_limit_returns_422():
    with patch("app.core.database.get_db"):
        response = client.get("/api/v1/metrics?limit=999")
    assert response.status_code == 422
