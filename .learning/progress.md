# Learning Progress

## First Session - Rate Limiter Tests

**Date:** 2026-04-24
**Status:** Completed

### Concepts Studied
- Token Bucket Algorithm (understood via docs/rate_limiter.md)
- RateLimitResult dataclass
- InMemoryStorage vs RedisStorage (understood — single-process vs atomic/distributed)
- Fail open vs fail closed (understood)
- Redis Lua scripts (prerequisite, not deep-dived yet)

### What Was Completed
- RedisStorage graceful degradation tests (tests/test_rate_limit_redis.py)
  - 4 tests: ConnectionError, TimeoutError, RedisError → fail open
  - 1 test: unexpected error → fail closed

### Gaps Remaining
1. **RedisStorage._calculate_ttl()** — not tested
2. **RedisStorage.get_current_tokens()** — not tested
3. **RedisStorage.reset_bucket()** — not tested
4. **RedisStorage happy path** — normal Redis operation not tested
5. **Config tier_limits** — not tested
6. **Config requests_per_window/window_seconds** — not tested
7. **Middleware 429 response behavior** — not tested (only mocked)
8. **Middleware skip when disabled** — not tested
9. **Integration tests with real Redis** — Docker-based (future work)

### Prerequisites That Might Be Missing
- Redis Lua scripts (why atomic execution prevents race conditions)

### Pending Challenges
- [x] Graceful degradation tests

---

## Session 2 - RedisStorage Deep Dive

**Date:** 2026-04-26

### Concepts Studied
- Redis Lua scripts for atomic multi-step operations
- Token bucket algorithm mechanics (refill calculation, consumption, reset time)
- Fail-open vs fail-closed error handling
- TTL calculation for auto-cleanup of abandoned buckets
- InMemoryStorage as test double
- Sliding window vs token bucket (concept clarification)

### What Was Completed
- Understood how Lua scripts execute atomically in Redis
- Traced the full flow of `check_and_consume` from Python → Lua → Python
- Identified testing gaps: Lua script returns, `_calculate_ttl`, `get_current_tokens`, `reset_bucket`, edge cases
- Designed hybrid test suite (mocked unit tests + integration tests)

### Tests Implemented
- `tests/test_calculate_ttl.py` — 13 tests covering boundary conditions, normal cases, edge cases, formula verification
- `tests/test_get_current_tokens.py` — 8 tests covering happy path, bucket not found, Redis error handling (fail open)
- `tests/test_reset_bucket.py` — 6 tests covering success path, correct mapping, error handling
- Fixed pre-existing `test_default_tenant` in `tests/test_rate_limit_middleware.py`

**Final Test Results:** 83 passed, 0 failed

### Gaps Remaining
1. **RedisStorage happy path** — normal operation with mocked Redis
2. **Integration tests with real Redis** — Docker-based

### Prerequisites That Might Be Missing
- None — all concepts understood through dialogue

### Pending Challenges
- [x] RedisStorage unit tests (TTL, get_current_tokens, reset_bucket)
- [ ] RedisStorage happy path tests
- [ ] Integration tests with real Redis

---

## Currently Studying
- [Nothing in progress - session was complete]

## Queued (Want to Learn Next)
- RedisStorage happy path — because this is the core functionality needed before moving to integration tests
- Integration tests with real Redis — because Docker-based tests validate the full stack

## Known Gaps / Revisit
- None flagged as still fuzzy from this session