# Various learnings during Foundation development

## Schema evolution with JSONB
- Using the JSONB data type for flexible schema evolution without expensive ALTER TABLE migrations
- Allows storing arbitrary labels (e.g., host, region, tenant-specific tags) without requiring database schema changes
- Combined with GIN indexing or specific JSON operators (e.g., `@>`), it remains highly performant for analytics queries

## Composite indexing
- Created composite indexes (e.g., `name` + `timestamp`) to optimize time-series data retrieval
- Ensures that time-range queries on specific metrics avoid full table scans 
- Allows PostgreSQL to jump directly to the correct metric name and then scan only the relevant time window sequentially

## Modern Python Tooling (uv)
- Replaced standard `pip` with `uv` for package management
- Dependency resolution and installations are 10-100x faster
- Drastically speeds up DevContainer builds and CI/CD pipelines
- Provides robust lockfile support ensuring perfectly reproducible environments

## Preventing Schema Leakage (Anti-Corruption Layer)
- Created distinct Pydantic schemas (`MetricCreate`, `MetricResponse`) that are completely separate from SQLAlchemy ORM models
- Decoupling the API contract from the database representation prevents internal database fields from leaking to external clients
- Allows us to completely overhaul the underlying database schema later without breaking external API consumers

## The Fail-Fast Configuration Pattern
- Used `pydantic-settings` to manage environment variables with strict type validation at application startup
- Prevents apps from starting successfully but crashing randomly hours later when a missing variable (e.g., `POSTGRES_USER`) is finally called in code
- If required variables are missing or incorrectly typed, the container crashes instantly (Fail-Fast), preventing a bad deployment from ever taking live traffic

## Liveness vs. Readiness Probes
- Mapped out separate `/health` (liveness) and `/db_health` (readiness) endpoints
- Liveness simply indicates the Python process is running and hasn't crashed
- Readiness actually executes a query (e.g., `SELECT 1`) to prove the application can successfully talk to its downstream dependencies (PostgreSQL/Redis)
- This is critical for Kubernetes and Load Balancers to achieve zero-downtime routing by automatically stopping traffic to instances with disconnected databases

## Deterministic Connection Lifecycle (Dependency Injection)
- Used FastAPI's `Depends(get_db)` to yield database sessions and clean them up automatically
- Tying the database session lifecycle strictly to the HTTP request lifecycle guarantees cleanups
- Prevents connection leaks: even if an unhandled exception occurs deep in the business logic, the framework's dependency generator ensures the connection is returned to the pool

## I/O vs. CPU Boundary Recognition
- Successfully implemented `async/await` for database and HTTP calls (I/O bound operations)
- Recognized the strict limitations of Python's Event Loop and the GIL (Global Interpreter Lock)
- CPU-intensive tasks (complex math, massive JSON parsing) must not use async, as they will block the entire event loop and freeze all concurrent API requests
- This dictates that future heavy processing must be offloaded to the Kafka Worker layer

## Infrastructure-as-Code for Dev Environments
- Containerized the development environment using DevContainers and Docker Compose multi-service networks (`network_mode: service:db`)
- Eliminates the "It works on my machine" anti-pattern by standardizing the OS (Debian), Python version (3.13), and networking setup into source control
- Reduces "Time-to-First-Commit" for new developers joining the project from days down to minutes

## Structured Logging (structlog)
- Implemented contextual, machine-parseable JSON logs for production
- JSON logs can be easily ingested, searched, and filtered by observability stacks (ELK, Grafana Loki)
- Maintained pretty-printed, colorized logs for local development to ensure developer ergonomics


# What can go wrong

## Blocking the Event Loop
- Developer accidentally puts a heavy CPU task or a synchronous `requests.get()` inside an `async def` endpoint
- The entire FastAPI server freezes and stops processing all other concurrent user requests until that single task finishes
**Solution:** Strictly use asynchronous libraries (e.g., `httpx`, `asyncpg`) for I/O, and offload heavy CPU work to background tasks or the Kafka Worker service.

## Connection Leaks
- Opening database connections manually without using FastAPI's dependency injection (`Depends`) or async context managers
- An exception occurs mid-request, the connection is never explicitly closed, and the Postgres connection pool is quickly exhausted
**Solution:** Always use the injected `db: AsyncSession = Depends(get_db)` so the framework's `finally` block guarantees the connection returns to the pool regardless of errors.

## Silent Configuration Failures
- Using `os.getenv('DB_PASSWORD')` deep inside a service function
- The application starts fine and passes liveness checks, but crashes throwing 500 errors during the very first user request that triggers that function
**Solution:** Route all environment variables through the central `Settings` class using Pydantic so the application fails immediately at startup if misconfigured.

## Service Orchestration Failures
- The Ingestion API starts up faster than PostgreSQL in the Docker Compose environment
- The API immediately tries to connect, fails, and crashes before the database is ready to accept connections
**Solution:** Use Docker Compose `depends_on` with `condition: service_healthy` to ensure the database passes its `pg_isready` healthcheck before the FastAPI container is allowed to boot.