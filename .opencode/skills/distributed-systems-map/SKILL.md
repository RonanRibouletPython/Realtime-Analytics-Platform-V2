---
name: distributed-systems-map
description: Concept dependency map for distributed systems and observability engineering. Load this when suggesting learning paths or checking prerequisites for a concept.
license: MIT
compatibility: opencode
---

## Concept Dependency Map

Read left to right. Each concept builds on the ones before it.

### Kafka / Message Queues

```
Pub/Sub basics
  └── Kafka fundamentals (topics, partitions, offsets)
        ├── Consumer groups
        │     └── Backpressure patterns
        │           └── Dead letter queues
        │                 └── Poison pill handling
        └── Producer guarantees (acks, idempotency)
              └── Exactly-once semantics
```

### Observability

```
Structured logging
  └── Log aggregation (Loki, ELK)
        └── Correlation IDs
              └── Distributed tracing (spans, traces)
                    ├── OpenTelemetry SDK
                    │     └── OTLP exporters
                    └── Context propagation across services
```

### Async Python / FastAPI

```
Async/await fundamentals
  └── FastAPI async endpoints
        ├── Background tasks
        │     └── Task queues (Celery, ARQ)
        │           └── Idempotency patterns
        └── Streaming responses
              └── WebSocket connections
```

### TimescaleDB / Time-Series Storage

```
PostgreSQL fundamentals
  └── TimescaleDB hypertables
        ├── Continuous aggregates
        │     ├── Retention policies
        │     └── Rollup strategies
        └── Partitioning and chunk management
              └── Compression policies
                    └── Query caching / materialized views
```

### Resilience Patterns

```
Timeouts and retries (exponential backoff)
  └── Circuit breakers
        └── Bulkheads
              └── Health checks
                    └── SLO / SLA design
                          └── Error budgets
```

### Data Consistency

```
ACID transactions
  └── Write-ahead logging (WAL)
        └── MVCC (multi-version concurrency)
              └── Snapshot isolation
                    └── Distributed transactions
                          └── Saga pattern
```

---

## Concept Status by Domain

Use this as a reference when reading `.learning/progress.md` to suggest next steps.

**High value, commonly skipped:**
- Backpressure in Kafka consumers (critical for metric ingestion at scale)
- Correlation IDs (prerequisite for distributed tracing to be useful)
- Continuous aggregates (transforms TimescaleDB from slow to fast for dashboards)
- Idempotency patterns (prerequisite for reliable retry logic)

**Advanced, high leverage:**
- Exactly-once semantics (when correctness of metrics matters more than throughput)
- Context propagation (makes distributed tracing actually useful across services)
- Error budgets (connects observability to engineering decisions)

---

## Recommended Learning Order for Metric Ingestion Systems

1. Kafka fundamentals → Consumer groups → Backpressure
2. Structured logging → Correlation IDs → Distributed tracing
3. TimescaleDB hypertables → Continuous aggregates → Retention
4. Circuit breakers → Bulkheads → Health checks
5. Idempotency → Exactly-once semantics