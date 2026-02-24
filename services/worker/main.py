import asyncio

import structlog
from app.core.logging import setup_logging
from app.core.prometheus import start_prometheus_server
from app.core.settings import settings
from app.kafka_consumer import consume

logger = structlog.get_logger()


async def main() -> None:
    setup_logging()
    logger.info("worker_starting", env=settings.ENV)

    # Prometheus scrape endpoint — up before the consume loop so we have
    # observability from the very first message.
    start_prometheus_server(port=settings.PROMETHEUS_PORT)

    await consume()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("worker_interrupted")
