# Challenges: Rate Limit Graceful Degradation
**Generated:** 2026-04-24
**Session:** rate-limit-graceful-degradation
**Status:** pending

---

## Challenge 1: Diagnose the fail-open bug in RedisStorage

Here's a version of `check_and_consume` with a bug introduced. The tests pass on the happy path but fail when Redis goes down during a high-traffic period.

```python
async def check_and_consume(
    self,
    key: str,
    bucket_size: int,
    refill_rate: float,
    refill_interval: int,
) -> RateLimitResult:
    # ... validation code same as original ...
    
    try:
        # ... script execution same as original ...
        result = await self._redis.evalsha(...)
        
        # Parse and return result
        allowed = bool(result[0])
        remaining = int(result[1])
        # ... rest of parsing ...
        
    except RedisError as e:
        # BUG: This returns fail-closed instead of fail-open!
        RATE_LIMIT_ERRORS.labels(error_type=type(e).__name__).inc()
        logger.warning("rate_limit_redis_error_falling_back", key=key, error=str(e))
        
        # Wrong: returning denied when Redis is down
        return RateLimitResult(
            allowed=False,  # <-- THIS IS THE BUG
            remaining=0,
            reset_time=int(time.time()) + refill_interval,
            bucket_size=bucket_size,
            retry_after=refill_interval,
        )
```

**Your task:** Identify the bug and explain why it causes the described failure during high traffic.

**Hint level:** None — this is a direct misunderstanding of the fail-open pattern.

---

## Challenge 2: Implement _calculate_ttl from spec

Without looking at what we built, implement the `_calculate_ttl` method from this spec:

**What it should do:** Calculate a TTL for a Redis key that ensures abandoned buckets auto-cleanup after they naturally empty.

**Inputs:**
- `bucket_size`: Maximum tokens in the bucket (int)
- `refill_rate`: Tokens added per interval (float)
- `refill_interval`: Refill interval in seconds (int)

**Outputs:**
- TTL in seconds (int), clamped between 60 (1 minute) and 86400 (24 hours)

**Constraints:**
- If `refill_rate <= 0`, return 300 (5-minute default)
- Time to fill empty bucket = `(bucket_size / refill_rate) * refill_interval`
- Add 50% buffer to the calculated time
- Return bounded TTL

**Success criteria:**
- [ ] Returns 300 when refill_rate is 0 or negative
- [ ] Returns 60 when bucket_size is 1 and refill_interval is 6 (1 token/6sec = 6sec to fill, *1.5=9sec -> clamped to 60)
- [ ] Returns 86400 when bucket_size is 1000 and refill_interval is 1 (1000 tokens/sec = 1sec to fill, *1.5=1.5sec -> clamped... wait, what's the actual calculation here?)

def _calculate_ttl(bucket_size: int, refill_rate: float, refill_interval: int) -> int:

    ttl: int = 0
    buffer: float = 1.5 # 50% buffer
    low_bound = 60 # 60 seconds
    high_bound = 86400 # 24 hours

    # Verify that refill_rate is positive (if not return default value)
    if refill_rate <= 0:
        return 300
    
    # Calculate the ttl with buffer
    seconds_to_fill = (bucket_size / refill_rate) * refill_interval
    ttl = seconds_to_fill * buffer

    return max(low_bound, min(ttl, high_bound))
    

---

## Challenge 3: Would you use fail-open here?

You're working on a payment processing service with these characteristics:
- Rate limiter protects a critical endpoint that charges customer cards
- Each denied request causes real financial loss (customer frustration, dropped transactions)
- Redis is in the same datacenter with 99.9% uptime SLA
- Your Ops team has pagerduty — they wake up fast

**Your task:** Should you use fail-open for Redis errors in this payment service? Walk through your reasoning. Reference the tradeoffs we discussed — what do you gain, what do you give up, and does the gain outweigh the cost given these constraints?

There is no single right answer. Reasoning quality matters more than the conclusion.

Answer: 
Fail-open = unprotected availability
Fail-close = protected unavailability
In this case we can have real financial harm potential (fraud, unbounded charges)
Tradeoff is between availability and enforceability

Senior answer:
No rigid fail-close but hybrid approach preffered:
1. Fail-open immediately: don't block payments during transient Redis blips
2. Circuit breaker: after N consecutive failures, transition to fail-close
3. Burn rate limit: even when Redis is down, enforce a hard cap (e.g., "max 100 requests/minute regardless")
This gives mostly available with some protection

---

## Answers

*Expand after attempting.*

<details>
<summary>Challenge 1 answer</summary>

The bug is returning `allowed=False` inside the `except RedisError` handler. When Redis is down (connection error, timeout, etc.), the code should return `allowed=True` to fail **open** �� allowing traffic through to prevent cascading failures.

Why this fails in production: During a Redis partition, the rate limiter would block ALL traffic (returning denied). This turns a transient Redis issue into a complete service outage. Every customer who tries to use the API gets 429'd, even legitimate users who should be allowed.

The correct behavior: return `allowed=True` with `remaining=bucket_size` to allow full burst capacity when Redis is unavailable.

</details>

<details>
<summary>Challenge 2 answer</summary>

```python
def _calculate_ttl(
    self,
    bucket_size: int,
    refill_rate: float,
    refill_interval: int,
) -> int:
    if refill_rate <= 0:
        return 300  # Default 5 minutes

    # Time to fill empty bucket: tokens_needed / tokens_per_second
    # tokens_needed = bucket_size, tokens_per_second = refill_rate / refill_interval
    seconds_to_fill = (bucket_size / refill_rate) * refill_interval

    # Add 50% buffer for safety
    ttl = int(seconds_to_fill * 1.5)

    # Clamp to reasonable bounds
    return max(60, min(ttl, 86400))  # 1 minute to 24 hours
```

The key insight: TTL should be proportional to how long it takes for the bucket to naturally empty. If nobody uses the bucket for that long, it's abandoned and should be cleaned up.

</details>

<details>
<summary>Challenge 3 answer</summary>

This is a judgment call, but here's the reasoning:

**Arguments for fail-open:**
- Redis downtime wouldn't block payments
- Financial loss per denied request is real
- High Redis availability reduces the risk

**Arguments for fail-closed (or fail-closed with circuit breaker):**
- Payments without rate limiting could allow unbounded charges
- Financial fraud risk if rate limits don't enforce
- "Just fail open" ignores the cost of abuse

**Better answer:** You'd likely use a **hybrid approach** — fail open for Redis errors, but have a circuit breaker that transitions to fail-closed after sustained Redis failures. Or: fail open immediately but with a "burn rate" limit (can't exceed N requests per minute even if Redis is down).

The point of the exercise: fail-open is not universally correct. Context matters. The trade-off table we discussed (availability vs. enforceability) directly applies here.

</details>