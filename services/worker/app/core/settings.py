from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # App
    ENV: Literal["development", "production"] = "development"

    # Database
    POSTGRES_USER: str = "analytics"
    POSTGRES_PASSWORD: str = "analytics"
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "analytics"

    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    KAFKA_TOPIC_METRICS: str = "metrics_ingestion"
    KAFKA_TOPIC_DLQ: str = "metrics_dlq"
    KAFKA_CONSUMER_GROUP: str = "metrics_worker_group"

    # Schema Registry
    SCHEMA_REGISTRY_URL: str = "http://localhost:8081"

    # Observability
    PROMETHEUS_PORT: int = 8001

    @property
    def DB_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_SERVER}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
