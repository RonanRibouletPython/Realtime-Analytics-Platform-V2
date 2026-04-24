# Design: Test Coverage for RedisStorage

## Context

We're implementing tests for `RedisStorage` (the production backend) using mocking. This follows the learning path where:
1. We learned the difference between InMemoryStorage (tested) and RedisStorage (not tested)
2. We understood WHY RedisStorage exists (distributed state sharing)
3. We're choosing the mocking approach for unit tests

## What We Already Test (InMemoryStorage)

From `tests/test_rate_limit_storage.py`, these behaviors are covered:
- RateLimitResult dataclass (allowed/denied, to_headers)
- First request is allowed
- Bucket depletion after N requests
- Different keys have separate buckets
- Edge case: zero bucket size

## What RedisStorage Adds (New Tests Needed)

| Method | What to Test | Why It Matters |
|--------|--------------|---------------|
| `check_and_consume()` | Core token bucket logic via Lua | Same algorithm, Redis backend |
| `_calculate_ttl()` | TTL bounds (60s - 24h) | Prevents memory leaks |
| `get_current_tokens()` | Monitoring helper | Observability |
| `reset_bucket()` | Admin operation | Manual recovery |
| **Graceful degradation** | Fail open on Redis errors | **Critical for production** |

## Test Design

### File Location
`tests/test_rate_limit_redis.py`

### Imports
```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from redis.exceptions import ConnectionError, TimeoutError, RedisError

from rate_limit.storage import RedisStorage, RateLimitResult
```

### Mocking Strategy

| Component | Mock Strategy | Rationale |
|-----------|--------------|-----------|
| `self._redis` | `AsyncMock` | Full control over Redis behavior |
| `evalsha()` | Return controlled values | Test Lua script results |
| `script_load()` | Return fake SHA | Avoid Redis roundtrip |
| `hget()`, `hset()` | Return controlled values | Test monitoring/admin |

**What NOT to mock:**
- `_calculate_ttl()` — synchronous, test directly
- Parameter validation logic — call real code
- Return type construction — use real RateLimitResult

## Test Classes to Create

### Class 1: TestRedisStorageCheckAndConsume

Happy path tests that mirror InMemoryStorage:

| Test Method | Purpose |
|------------|---------|
| `test_first_request_allowed` | First request gets full bucket |
| `test_bucket_depletes` | Denied after bucket exhausted |
| `test_different_keys_separate` | Keys are isolated |
| `test_tenant_id_extracted` | Tenant ID for metrics labels |
| `test_script_sha_cached` | SHA cached after first call |

### Class 2: TestRedisStorageGracefulDegradation

**Critical: This is the key difference from InMemoryStorage.**

| Test Method | Purpose | Expected Result |
|------------|---------|-----------------|
| `test_connection_error_fails_open` | ConnectionError | `allowed=True` |
| `test_timeout_error_fails_open` | TimeoutError | `allowed=True` |
| `test_generic_redis_error_fails_open` | Any RedisError | `allowed=True` |
| `test_unexpected_error_fails_closed` | Unexpected error | `allowed=False` |

The design philosophy: **fail open** on Redis errors to prevent cascading outages.

### Class 3: TestRedisStorageTTL

Tests for synchronous `_calculate_ttl()`:

| Test Method | Purpose |
|------------|---------|
| `test_standard_ttl` | Normal: 100/10/60 → 900s |
| `test_ttl_clamped_to_min` | Minimum 60s |
| `test_ttl_clamped_to_max` | Maximum 86400s |
| `test_zero_refill_rate_default` | Default 300s |

### Class 4: TestRedisStorageMonitoring

| Test Method | Purpose |
|------------|---------|
| `test_get_current_tokens_exists` | Returns token count |
| `test_get_current_tokens_nonexistent` | Returns None |
| `test_get_current_tokens_redis_error` | Returns None on error |
| `test_reset_bucket_success` | Returns True |
| `test_reset_bucket_redis_error` | Returns False on error |

## Test Cases for Edge Conditions

### Input Validation
```python
async def test_negative_bucket_size(self):
    """Negative bucket_size: fails open"""
    # RedisStorage validates and returns allowed=True

async def test_zero_refill_rate(self):
    """Zero refill_rate: uses default handling"""
    # Same as InMemoryStorage

async def test_negative_refill_interval(self):
    """Negative refill_interval: fails open"""
    # Validated in check_and_consume
```

### Key Extraction
```python
async def test_key_without_tenant(self):
    """Key without ':' uses 'default' tenant"""
    # e.g., "/api" → tenant_id="default"

async def test_multicolon_key(self):
    """Key with multiple ':' uses first segment"""
    # e.g., "a:b:c" → tenant_id="a"
```

## Integration Tests (Out of Scope for Unit Tests)

Mark these with `pytest.mark.integration` to skip in unit test runs:

| Test | Why Skip | TODO |
|------|---------|------|
| Concurrent requests atomicity | Need real Redis | Integration test |
| Script SHA survives restart | Need Redis persistence | Integration test |
| TTL actually expires | Need real time passage | Integration test |
| Redis Cluster mode | Need cluster setup | Integration test |

## Implementation Order

1. **TTL calculation tests** — synchronous, no mocking complexity
2. **Graceful degradation tests** — critical production behavior
3. **Happy path tests** — mirrors InMemoryStorage
4. **Monitoring helper tests** — get_current_tokens, reset_bucket
5. **Edge case tests** — negative params, key extraction

## Complexity Assessment

- **Unit test complexity:** Medium
- **Mock setup:** Medium (async mocking required)
- **Test isolation:** High (each test gets fresh mock)

## Open Questions

1. Should we use `pytest.mark.asyncio` for all async tests? (Yes, follow existing pattern)
2. Do we need to test metrics being emitted? (Yes, verify labels)
3. Should we patch `redis_client` module-level? (No, inject mock in constructor)