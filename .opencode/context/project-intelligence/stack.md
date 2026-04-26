# Project Stack

Loaded automatically every session. Used by ARCHITECT and IMPLEMENT to ground designs and
implementations in the real codebase - not generic templates.

Fill every section. The more specific this is, the more useful the agents become.
Delete example lines and replace with your actual values.

---

## Project overview

<!-- One paragraph. What does this system do? What problem does it solve?
     Be concrete - agents use this to calibrate which patterns make sense. -->

**Example:**
> A distributed metrics ingestion pipeline that receives time-series events from IoT sensors
> via Kafka, processes and validates them in async FastAPI workers, and stores aggregated
> results in TimescaleDB. Serves dashboards via a read API.

**Your project:**
> [fill this in]

---

## Tech stack

| Layer | Technology | Version | Notes |
|-------|-----------|---------|-------|
| Language | Python | 3.12 | |
| Runtime | CPython / async | - | asyncio throughout |
| Web framework | FastAPI | 0.111 | |
| Task queue | - | - | not yet implemented |
| Message broker | Apache Kafka | 3.6 | via confluent-kafka 2.4 |
| Database (primary) | TimescaleDB | 2.14 | on Postgres 16 |
| Database (cache) | - | - | |
| ORM / query layer | asyncpg | 0.29 | raw SQL, no ORM |
| Observability | OpenTelemetry | 1.24 | traces to Jaeger |
| Testing | pytest | 8.x | + pytest-asyncio |
| Package manager | uv | 0.4 | |
| Container | Docker | - | devcontainer in Dockerfile |
| CI | GitHub Actions | - | |

<!-- Replace values above with your actual versions.
     Add rows for anything not listed.
     "not yet implemented" is a valid and useful value - agents won't assume it exists. -->

---

## Directory layout

```
src/
├── ingestion/
│   ├── consumer.py          # Kafka consumer loop - KafkaConsumerService class
│   ├── processor.py         # Metric validation and transformation
│   └── writer.py            # TimescaleDB insert logic - MetricWriter class
├── api/
│   ├── main.py              # FastAPI app factory
│   ├── routes/
│   │   ├── metrics.py       # GET /metrics, GET /metrics/{id}
│   │   └── health.py        # GET /health, GET /ready
│   └── dependencies.py      # DB pool, Kafka client injection
├── models/
│   └── metric.py            # Pydantic models - MetricEvent, MetricBatch
├── db/
│   ├── pool.py              # asyncpg connection pool setup
│   └── migrations/          # SQL migration files
└── observability/
    └── tracing.py           # OTel tracer setup - currently a stub

tests/
├── ingestion/
├── api/
└── conftest.py              # Fixtures: test DB, mock Kafka consumer
```

<!-- Draw your actual directory tree here.
     For each directory, note the key class or function inside it.
     Agents use this to know where to look with AFT before they ask you. -->

---

## Key components

List the most important classes and functions. Agents will `aft_zoom` into these.

| Symbol | File | What it does |
|--------|------|--------------|
| `KafkaConsumerService` | `src/ingestion/consumer.py` | Main consumer loop, batch processing, offset commit |
| `process_batch` | `src/ingestion/consumer.py` | Validates and routes a batch of metric events |
| `MetricWriter` | `src/ingestion/writer.py` | Inserts validated metrics into TimescaleDB |
| `MetricEvent` | `src/models/metric.py` | Pydantic model for a single sensor reading |
| `create_app` | `src/api/main.py` | FastAPI app factory, registers routers and middleware |
| `get_db_pool` | `src/api/dependencies.py` | Dependency-injected asyncpg pool |

<!-- Add your real components here. Remove example rows.
     If you don't know all of them yet, add what you know and expand over time. -->

---

## External services and dependencies

| Service | What it does in this project | Local dev setup |
|---------|------------------------------|-----------------|
| Kafka (localhost:9092) | Message source for ingestion pipeline | docker-compose.yml |
| TimescaleDB (localhost:5432) | Primary data store | docker-compose.yml |
| Jaeger (localhost:16686) | Trace collector and UI | docker-compose.yml |

<!-- List every external service the code talks to.
     Include the local dev address - agents may suggest curl commands or test configurations. -->

---

## Constraints and decisions already made

List things that are settled. Agents should not re-open these unless explicitly asked.

- **No ORM.** Raw SQL via asyncpg. Performance and explicitness over convenience.
- **No Celery.** Task queue not yet introduced - may add later.
- **Async throughout.** No sync database calls anywhere. `asyncpg` only.
- **Kafka offset committed after write.** At-least-once delivery. Writes must be idempotent.
- **TimescaleDB inserts use `ON CONFLICT DO NOTHING`.** Idempotency enforced at DB layer.
- **One Kafka topic per sensor type.** Topics: `temperature.raw`, `pressure.raw`, `humidity.raw`

<!-- Add your own settled decisions. These prevent agents from proposing alternatives
     you've already considered and rejected. -->

---

## Known gaps / things not yet built

| Area | Status | Notes |
|------|--------|-------|
| Observability (tracing) | Stub only | `src/observability/tracing.py` exists but does nothing |
| Dead letter queue | Not implemented | Failed messages currently logged and dropped |
| Continuous aggregates | Not implemented | Queries hit raw hypertable - slow at scale |
| Authentication | Not implemented | API is unauthenticated internally |
| Task queue | Not designed | Background jobs run inline in request handlers |

<!-- This section is what agents use to know what's next and what's missing.
     Update it after each session. The REVIEW agent will suggest additions. -->

---

## How to run things

```bash
# Start all services
docker compose up -d

# Run the ingestion consumer
uv run python -m src.ingestion.consumer

# Run the API
uv run uvicorn src.api.main:create_app --factory --reload

# Run tests
uv run pytest tests/ -v

# Run a specific test file
uv run pytest tests/ingestion/test_processor.py -v

# Connect to TimescaleDB
psql postgresql://postgres:password@localhost:5432/metrics
```

<!-- Replace with your actual run commands.
     Agents use these when suggesting test runs or validation steps. -->

---

## Environment variables

| Variable | Required | What it does |
|----------|----------|--------------|
| `KAFKA_BOOTSTRAP_SERVERS` | Yes | Kafka broker address |
| `DATABASE_URL` | Yes | asyncpg-compatible Postgres connection string |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | Jaeger OTLP endpoint (default: localhost:4317) |
| `LOG_LEVEL` | No | Log verbosity (default: INFO) |

<!-- List every env var the project uses.
     Agents may reference these when writing configuration code. -->