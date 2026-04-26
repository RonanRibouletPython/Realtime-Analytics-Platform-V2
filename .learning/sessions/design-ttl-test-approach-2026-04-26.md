# Design: Test Approach for RedisStorage._calculate_ttl()

## Context

`_calculate_ttl()` is a pure calculation that determines the Redis TTL for a rate limit bucket. The formula:
- Base TTL = (bucket_size / refill_rate) × refill_interval × 1.5 (50% buffer)
- Clamped to [60, 86400] seconds
- Returns 300 if refill_rate ≤ 0

## Constraints

- This is a **pure calculation** — no Redis interaction, no state, no side effects
- Tests should be **fast, deterministic, and isolated**
- Must verify the formula matches the operational intent (abandoned buckets auto-cleanup, active buckets stay alive)

## Approach Chosen

**Direct unit testing with parameterized boundary conditions** — no mocking needed since the function is pure.

---

## Test Structure

Organize tests by **behavioral categories**, not by Redis state. This makes tests self-documenting and easier to maintain.

### Category 1: Boundary Conditions

These tests verify the clamping logic and special cases.

| Test | Input | Expected Output | Rationale |
|------|-------|-----------------|------------|
| `test_ttl_zero_refill_rate` | refill_rate=0 | 300 | Division would fail; return default 5 minutes |
| `test_ttl_negative_refill_rate` | refill_rate=-1 | 300 | Same as zero; defensive |
| `test_ttl_min_bounds` | bucket_size=1, refill_rate=1000, refill_interval=1 | 60 | Formula gives ~1.5s, but minimum is 60s |
| `test_ttl_max_bounds` | bucket_size=1000000, refill_rate=0.001, refill_interval=86400 | 86400 | Formula gives ~14M seconds, but maximum is 24h |

### Category 2: Normal Operation

These tests verify the core formula with realistic values.

| Test | Input | Expected Output | Rationale |
|------|-------|-----------------|------------|
| `test_ttl_exact_calculation` | bucket_size=100, refill_rate=10, refill_interval=60 | 900 | (100/10)×60×1.5 = 900s (15 min) |
| `test_ttl_partial_calculation` | bucket_size=50, refill_rate=5, refill_interval=30 | 450 | (50/5)×30×1.5 = 450s (7.5 min) |
| `test_ttl_typical_values` | bucket_size=1000, refill_rate=100, refill_interval=60 | 9000 | (1000/100)×60×1.5 = 9000s (2.5h) |

### Category 3: Edge Cases

These tests verify behavior at extreme values.

| Test | Input | Expected Output | Rationale |
|------|-------|-----------------|------------|
| `test_ttl_extreme_bucket_size` | bucket_size=1000000000, refill_rate=1, refill_interval=1 | 86400 | Clamped to max |
| `test_ttl_extreme_refill_rate` | bucket_size=1, refill_rate=1000000, refill_interval=1 | 60 | Clamped to min |
| `test_ttl_extreme_interval` | bucket_size=100, refill_rate=100, refill_interval=100000 | 86400 | Clamped to max |

### Category 4: Regression / Intent

These tests verify the operational intent of the TTL calculation.

| Test | Input | Expected Output | Rationale |
|------|-------|-----------------|------------|
| `test_ttl_active_bucket_1h` | bucket_size=1000, refill_rate=100, refill_interval=60 | 9000 | Active buckets should live ~2.5h (buffered) |
| `test_ttl_abandoned_bucket_15m` | bucket_size=100, refill_rate=10, refill_interval=60 | 900 | Abandoned buckets should auto-cleanup in ~15m |
| `test_ttl_fast_refill_short_ttl` | bucket_size=100, refill_rate=1000, refill_interval=10 | 150 | Fast refill = short TTL, bucket empties quickly |
| `test_ttl_slow_refill_long_ttl` | bucket_size=100, refill_rate=10, refill_interval=300 | 4500 | Slow refill = longer TTL, bucket takes longer to empty |

---

## Mock Strategy

**No mocking needed for `_calculate_ttl()` itself** — it's a pure function.

However, if we're testing the **integration** (i.e., that the TTL is correctly passed to Redis), then:

1. **InMemoryStorage** can serve as a test double for Redis when testing `check_and_consume()`
2. But `_calculate_ttl()` is called **before** Redis interaction, so it's always testable in isolation
3. For integration tests, verify that the TTL passed to `evalsha()` matches what `_calculate_ttl()` computed

### When to use InMemoryStorage as a test double:

```python
# For integration tests of check_and_consume():
with mock.patch.object(RedisStorage, '_redis', InMemoryStorage()):
    storage = RedisStorage()
    result = await storage.check_and_consume(...)
    # Verify TTL was in the evalsha call
```

But this is testing the **entire flow**, not `_calculate_ttl()` specifically.

---

## Data Flow for Testing

```
[Test Input: bucket_size, refill_rate, refill_interval]
       ↓
[Pure Calculation: _calculate_ttl()]
       ↓
[Output: TTL in seconds]
```

### For integration testing:

```
[check_and_consume()]
       ↓
[_calculate_ttl()]
       ↓
[evalsha(key, bucket_size, refill_rate, refill_interval, now_ms, ttl)]
       ↓
[InMemoryStorage tracks evalsha call and verifies TTL argument]
```

---

## Failure Modes to Consider

| Failure | Where It Occurs | How to Test |
|---------|-----------------|-------------|
| None — pure calculation | — | All failures are caught by boundary tests |
| Redis down during `check_and_consume()` | Higher level | Test `check_and_consume()`, not `_calculate_ttl()` |
| TTL too short/long in production | Formula logic | Verify formula matches operational intent |

---

## Implementation Order

1. **Write the boundary condition tests first** — they define the contract
2. **Write normal operation tests** — they verify the formula works
3. **Write edge case tests** — they ensure no unexpected behavior at extremes
4. **Write intent/regression tests** — they connect formula to operational meaning
5. **If integration is needed**, write the evalsha verification test last

---

## Open Questions

- Should we add a test that verifies the TTL doesn't change unexpectedly when inputs are slightly modified? (e.g., bucket_size 100→101 should give roughly similar TTL)
- Is there a minimum TTL below which Redis key expiration might be unreliable? Should we add a test for that?

---

## Out of Scope

- Testing Redis network behavior (timeouts, retries, etc.) — belongs in `check_and_consume()` tests
- Testing Lua script execution — belongs in integration tests
- Testing rate limit algorithm correctness — belongs in end-to-end rate limiting tests

---

## Summary

The test approach uses **direct unit testing** with **no mocking** for `_calculate_ttl()` because it's a pure calculation. Tests are organized by **behavioral categories** (boundary, normal, edge, intent) which makes the test suite self-documenting. The only time mocking is needed is for integration tests of `check_and_consume()`, where InMemoryStorage can track the `evalsha()` call to verify the TTL argument.

This approach ensures:
- Fast, deterministic tests (no network, no state)
- Clear separation of concerns (formula logic vs. Redis interaction)
- Tests that verify both the formula and its operational intent

---

*Generated: 2026-04-26*

---

## ✅ Review Checklist

Before IMPLEMENT writes the tests:

- [ ] Do the boundary tests cover all clamping conditions?
- [ ] Are the intent tests connected to actual operational requirements?
- [ ] Is the integration test (if needed) isolated from pure formula tests?

---

## 🎯 Key Takeaway

**Test the formula, not the infrastructure.** Since `_calculate_ttl()` is pure, mock it out of existence and test it directly. The Redis infrastructure is tested at the integration level, not the unit level.

---

*End of design doc*