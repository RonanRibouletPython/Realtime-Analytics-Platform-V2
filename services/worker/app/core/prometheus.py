from datetime import datetime as dt
from datetime import timezone as tz

import structlog
from prometheus_client import Counter, Histogram, start_http_server

logger = structlog.get_logger()

# ── Prometheus metrics ────────────────────────────────────────────────────────
# Defined at module level → registered once on import → process-global singletons.

MESSAGES_PROCESSED = Counter(
    "worker_messages_processed_total",
    "Total Kafka messages processed, labelled by outcome.",
    ["status"],  # "success" | "failure"
)

PROCESSING_LATENCY = Histogram(
    "worker_message_processing_duration_seconds",
    "End-to-end time from poll() to DB commit.",
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5),
)

DLQ_MESSAGES = Counter(
    "worker_dlq_messages_total",
    "Messages routed to the Dead Letter Queue, labelled by reason.",
    ["reason"],  # "ValueError" | "deserialization_error" | "db_error"
)


def start_prometheus_server(port: int) -> None:
    """Start the Prometheus scrape endpoint. Call once before the consume loop."""
    start_http_server(port)
    logger.info("prometheus_server_started", port=port)


# ── In-memory tracker ─────────────────────────────────────────────────────────
# Dual-track: Prometheus for dashboards, in-memory for structured log summaries.


class MessageTracker:
    """
    Tracks per-run stats and logs a summary every 100 messages.
    One instance lives for the lifetime of the worker process.
    """

    def __init__(self):
        self._processed = 0
        self._failed = 0
        self._dlq = 0
        self._latencies: list[float] = []
        self._started = dt.now(tz.utc)

    def record_success(self, latency_ms: float) -> None:
        self._processed += 1
        self._latencies.append(latency_ms)
        MESSAGES_PROCESSED.labels(status="success").inc()
        PROCESSING_LATENCY.observe(latency_ms / 1000)

        if self._processed % 100 == 0:
            self._log_summary()

    def record_failure(self) -> None:
        self._failed += 1
        MESSAGES_PROCESSED.labels(status="failure").inc()

    def record_dlq(self, reason: str) -> None:
        self._dlq += 1
        DLQ_MESSAGES.labels(reason=reason).inc()

    def _log_summary(self) -> None:
        uptime = (dt.now(tz.utc) - self._started).total_seconds()
        avg_ms = sum(self._latencies) / len(self._latencies) if self._latencies else 0

        logger.info(
            "worker_stats",
            processed=self._processed,
            failed=self._failed,
            dlq=self._dlq,
            rate_per_sec=round(self._processed / uptime, 2) if uptime else 0,
            avg_ms=round(avg_ms, 2),
            uptime_sec=round(uptime, 2),
        )


# Module-level singleton
tracker = MessageTracker()
