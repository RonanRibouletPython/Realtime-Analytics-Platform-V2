# Various learnings during Kafka Integration development

## Asynchronous Execution of Synchronous C-Extensions
- The confluent-kafka library is highly performant because it relies on C-extensions, but its core methods (producer.produce(), consumer.poll()) are synchronous and blocking
- Calling these directly inside an async def FastAPI route or worker loop freezes the Python Event Loop, stalling all concurrent requests for the duration of the call
- We must offload these blocking calls to a thread pool using asyncio.get_running_loop().run_in_executor(), ensuring the main event loop remains free to handle high-throughput I/O

## Schema Governance with Avro & Schema Registry
- We chose Avro over plain JSON to establish a strict, versioned contract between the Ingestion API and the Consumer Worker
- Schema mismatches are caught at produce time (before the message enters the broker), entirely preventing "poison pill" messages from polluting the raw metrics topic
- Binary serialization drastically reduces network payload size compared to plain text JSON, optimizing both Kafka storage and network throughput
- Implemented a multi-version schema producer leveraging a SchemaVersion enum, ensuring intentional, explicit version selection at every call site

## Backward-Compatible Schema Evolution
- We enforce a BACKWARD compatibility mode in the Schema Registry -> This means new consumer schemas can always read old messages
- This allows us to safely upgrade and deploy consumer workers before or alongside producer API upgrades, ensuring zero downtime
- Strict Rules established: Field renames are prohibited (requires a multi-step Add/Deprecate/Remove deployment process), and new fields must always define a default value (e.g., null)

## Delivery Guarantees & Idempotency
- Opted for At-Least-Once delivery by disabling enable.auto.commit on the consumer
- Offsets are manually committed only after a successful database write or a successful routing to the Dead Letter Queue
Because consumer crashes could cause Kafka to redeliver the same message, all downstream TimescaleDB writes must be strictly idempotent (e.g., using ON CONFLICT DO UPDATE)

## Explicit Error Classification
- Not all consumer exceptions should be handled equally
- Permanent Failures (e.g., ValueError for bad data, schema violations): Routed immediately to the DLQ, and the offset is committed to prevent an infinite crashloop
- Transient Failures (e.g., Database connection dropped): The offset is not committed, and the consumer relies on Kafka to redeliver the message once the system recovers

## The Forensics-Driven Dead Letter Queue (DLQ)
- A DLQ is useless if it doesn't provide enough context to fix the bug. We wrap failed messages in a "Forensics Envelope"
- The envelope captures the original topic, partition, offset, error reason, and crucially, the raw hex bytes of the payload (necessary if Avro deserialization failed completely)
- The DLQ uses a dedicated producer with acks=all and a synchronous flush(timeout=5.0) to guarantee the forensics data is durably persisted before the main consumer skips the poison pill's offset
- Circuit Breaker: If the DLQ producer fails repeatedly, the consumer halts. Silently dropping poison pills is unacceptable; it is better to stop processing and trigger a critical alert

## Dual-Track Observability
- Maintained structlog for human-readable, per-message debugging and tracing in log aggregators
- Introduced a dedicated Prometheus metrics server (:8001/metrics) to track time-series aggregations without analyzing massive log volumes
- Tracked metrics include: P99 processing latency (Histogram), throughput (Counter), and DLQ routing rates labeled by reason to quickly distinguish schema errors from business logic errors via PromQL

# What can go wrong

## Blocking the Event Loop
- Scenario: A developer uses msg = consumer.poll(1.0) inside an async loop
- Impact: The event loop freezes completely for 1 second per cycle. No database writes, health checks, or other coroutines can execute during this window, devastating service throughput
**Solution:** Always wrap poll() and produce() inside await loop.run_in_executor(...)

## Silent Coroutine Failures (Un-awaited Async Calls)
- Scenario: Calling send_to_dlq(msg) without the await keyword
- Impact: Python creates the coroutine object but immediately discards it without executing it. No error is thrown, the DLQ is never written to, and the data is silently and permanently lost
**Solution:** Enforce strict linting rules (like ruff) to catch un-awaited coroutines in CI

## Cryptic Serializer Crashes on Missing Data
- Scenario: Doing metric.get("timestamp").astimezone() when the timestamp is missing from the payload
- Impact: .get() returns None, and calling .astimezone() on None throws a deep AttributeError inside the Avro serializer with absolutely no context about which field caused it
**Solution:** Implement explicit None guards and raise clear ValueErrors early before data is passed to external libraries.

## Falsely Successful Health Checks
- Scenario: A /db_health endpoint catches a database connection error, formats a nice JSON error message, and returns it
- Impact: Because the endpoint returned a JSON payload without explicitly setting a 500/503 HTTP status code, the framework returns a 200 OK. Load balancers and Kubernetes think the service is healthy and continue sending it traffic, resulting in 100% request failure.
**Solution:** Always evaluate the internal status and explicitly raise an HTTPException(status_code=503) if downstream dependencies are unreachable