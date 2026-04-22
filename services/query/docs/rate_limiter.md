# Rate Limiter Documentation

## Overview

The query service implements a Token Bucket rate limiter to control request rates per tenant and endpoint. It uses Redis for distributed state management and integrates as FastAPI middleware.

## Algorithm

### Token Bucket

The Token Bucket algorithm allows burst traffic while enforcing a sustained rate:

- **bucket_size**: Maximum tokens (requests) allowed at once
- **refill_rate**: Tokens added per interval
- **refill_interval**: Time period for replenishment (seconds)

Example: `bucket_size=100, refill_rate=10, refill_interval=60`
- Burst up to 100 requests
- Then sustains 10 requests per minute

## Architecture

```
Request → RateLimitMiddleware → RedisStorage → Redis
                                      ↓
                              429 Too Many Requests
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RATE_LIMIT_ENABLED` | `true` | Enable/disable rate limiting |
| `RATE_LIMIT_BUCKET_SIZE` | `100` | Maximum burst capacity |
| `RATE_LIMIT_REFILL_RATE` | `10` | Tokens per interval |
| `RATE_LIMIT_REFILL_INTERVAL` | `60` | Interval in seconds |
| `RATE_LIMIT_ALGORITHM` | `token_bucket` | Algorithm (token_bucket only) |

### Per-Tenant Overrides

```bash
RATE_LIMIT_TENANT_OVERRIDES='{"tenant123": {"bucket_size": 500, "refill_rate": 50}}'
```

### Header Customization

Headers can be customized via config (not env vars):

```python
from rate_limit import RateLimitConfig
config = RateLimitConfig(
    header_limit="X-RateLimit-Limit",
    header_remaining="X-RateLimit-Remaining", 
    header_reset="X-RateLimit-Reset",
    header_retry_after="Retry-After",
)
```

## Response Headers

All responses include:

| Header | Description |
|--------|-------------|
| `X-RateLimit-Limit` | Maximum requests allowed |
| `X-RateLimit-Remaining` | Requests remaining |
| `X-RateLimit-Reset` | Unix timestamp when reset |

429 responses include:

| Header | Description |
|--------|-------------|
| `Retry-After` | Seconds until retry |

## Integration

### Adding to FastAPI

```python
from fastapi import FastAPI
from rate_limit import RateLimitMiddleware

app = FastAPI()
app.add_middleware(RateLimitMiddleware)
```

### Skipping Paths

```python
app.add_middleware(
    RateLimitMiddleware, 
    skip_paths={"/health", "/metrics", "/ready"}
)
```

## Tenant Identification

Priority order:
1. `X-Tenant-ID` header
2. Authorization Bearer token (hashed)
3. Client IP address (via `X-Forwarded-For`)

## Redis Keys

Format: `rate_limit:{tenant_id}:{endpoint}`

Example: `rate_limit:acme_corp:/api/v1/metrics`

## Storage

### RedisStorage (Production)

- Atomic operations via Lua script
- Automatic TTL management
- Graceful degradation on Redis failure (fails open)

### InMemoryStorage (Development)

- Non-atomic, single-process only
- Useful for testing

## Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `rate_limit_checks_total` | Counter | tenant_id, result | Total checks |
| `rate_limit_tokens_available` | Gauge | tenant_id | Current tokens |
| `rate_limit_errors_total` | Counter | error_type | Error count |
| `rate_limit_check_duration_seconds` | Histogram | - | Check latency |

## Testing

```bash
# Run all rate limit tests
pytest tests/test_rate_limit_config.py \
       tests/test_rate_limit_storage.py \
       tests/test_rate_limit_middleware.py -v
```

## API Response Codes

| Code | Description |
|------|-------------|
| 200 | Success |
| 429 | Rate limit exceeded |

### 429 Response Body

```json
{
  "error": "Too Many Requests",
  "message": "Rate limit exceeded. Please retry later.",
  "retry_after": 60
}
```