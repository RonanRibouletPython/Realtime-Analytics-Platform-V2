# Session: RedisStorage Graceful Degradation

**Date:** 2026-04-24
**Duration:** ~1 hour
**Phases completed:** Concept · Implement · Test · Review

---

## What we covered

We picked up where the last session left off: after understanding the gaps in test coverage for RedisStorage, we implemented a test suite for graceful degradation behavior.

The session started by clarifying the fundamental difference between the two storage backends:

- **InMemoryStorage** — stores bucket state in a Python dict. Works fine for single-process testing, but breaks down in multi-worker deployments because each worker has its own copy. No atomicity guarantees.
- **RedisStorage** — stores state in Redis using a Lua script that runs atomically (single-threaded execution in Redis prevents race conditions). Production-ready but introduces a new failure mode: what happens when Redis is unavailable?

The key design decision in RedisStorage is **fail open** on Redis errors. When `evalsha()` raises a `RedisError` (connection error, timeout, generic Redis error), the code catches it and returns `allowed=True` with a full bucket. This prevents a Redis outage from cascading into a full API outage — traffic keeps flowing even if rate limiting is temporarily bypassed.

For **unexpected errors** (anything not a `RedisError`), the behavior is **fail closed** — `allowed=False` is returned. This is a deliberate safety choice: if something truly unexpected goes wrong, better to be conservative than silently allow all traffic.

---

## The core idea

**Graceful degradation** means the rate limiter has a defined behavior when Redis is unavailable. Instead of crashing or blocking all traffic, it:
- **Fails open** on Redis errors → allows traffic through (availability over correctness)
- **Fails closed** on unknown errors → blocks traffic (safety over availability)

This trade-off makes sense because a rate limiter is a protection layer — when it can't protect, the service should continue operating rather than becoming the new failure point.

---

## Design decisions

**Approach:** Catch `RedisError` specifically (the base class for all redis-py exceptions like `ConnectionError`, `TimeoutError`, `ClusterError`) vs catching all other exceptions.
**Why:** Using the base class means any Redis failure mode is caught without needing to enumerate every exception type. Unexpected errors are a separate `except` block that fails closed.

---

## What was implemented

| Component | Location | What it does |
|-----------|----------|--------------|
| `TestRedisStorageGracefulDegradation` | `tests/test_rate_limit_redis.py` | 4 tests covering fail-open/fail-closed |
| `test_connection_error_fails_open` | same | Mocks `evalsha` to raise `ConnectionError` → asserts `allowed=True` |
| `test_timeout_error_fails_open` | same | Mocks `evalsha` to raise `TimeoutError` → asserts `allowed=True` |
| `test_generic_redis_error_fails_open` | same | Mocks `evalsha` to raise `RedisError` → asserts `allowed=True` |
| `test_unexpected_error_fails_closed` | same | Mocks `evalsha` to raise `ValueError` → asserts `allowed=False` |

All tests use `AsyncMock` to simulate Redis client behavior without requiring a real Redis instance.

---

## What was hard

The distinction between **fail open** and **fail closed** required explicit discussion. Both behaviors are intentional — the test for `ValueError` (unexpected error) failing closed is just as important as the Redis error tests failing open. The key insight: fail-closed on unexpected errors is a safety guard, not a sign that the code is broken.

---

## What to revisit

- [ ] TTL calculation tests (`_calculate_ttl`) — not tested yet
- [ ] Happy-path tests (normal Redis operation) — important coverage
- [ ] Monitoring helpers (`get_current_tokens`, `reset_bucket`) — useful for operational testing
- [ ] Integration tests with real Redis (Docker-based) — beyond mocking

---

## What to learn next

**Suggested:** Redis Lua scripts in depth — because understanding what the Lua script does (lines 161-205 of storage.py) is the key to understanding why RedisStorage is correct and InMemoryStorage is not. Specifically: why does atomic execution matter, and what race condition does it prevent?

---

## Resources

- `rate_limit/storage.py` — full implementation with comments
- `tests/test_rate_limit_redis.py` — 4 graceful degradation tests
- redis-py exceptions hierarchy: `redis.exceptions.RedisError` is the base class for all