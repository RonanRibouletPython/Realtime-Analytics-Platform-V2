from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── App ───────────────────────────────────────────────────────────────────
    PROJECT_NAME: str = "Ingestion Service"
    API_V1_PREFIX: str = "api/v1"
    ENV: Literal["development", "production"] = "development"

    # ── Database ──────────────────────────────────────────────────────────────
    POSTGRES_USER: str = "analytics"
    POSTGRES_PASSWORD: str = "analytics"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "analytics"

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379

    # ── Kafka ─────────────────────────────────────────────────────────────────
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_METRICS: str = "metrics_ingestion"
    KAFKA_TOPIC_DLQ: str = "metrics_dlq"

    # ── Schema Registry ───────────────────────────────────────────────────────
    SCHEMA_REGISTRY_URL: str = "http://localhost:8081"

    # ── Observability ─────────────────────────────────────────────────────────
    PROMETHEUS_PORT: int = 8001

    @property
    def DB_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def REDIS_URL(self) -> str:
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/0"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


# Module-level singleton — import this everywhere
settings = Settings()
