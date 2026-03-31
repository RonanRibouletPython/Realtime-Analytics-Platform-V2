# DB Connection Pool Size
* We chose pool_size parameter of 5
* Larger pools consume more memory
* Most queries take <100ms, so 5 connections serve many requests
* Overflow handles bursts (dashboard refreshes)

# Rounding Queries to 5 minutes
* This is a trade-off between accuracy and performance
* 1 minute: Cache hit rate ~20% (queries shift every minute)
* 5 minutes: Cache hit rate ~80% (queries stable for 5 minutes)
* 15 minutes: Cache hit rate ~95% (but less precision)

# Why max 30 days instead of unlimited?
* Protects database from accidental full scans
* For longer analysis, users should use data warehouse (BigQuery, Redshift)

# DB Pool Timeout
* We set the database_pool_timeout = 30 in settings.py
* This means that the 16th concurrent request will wait 30 seconds (User #16 will be queued) for a connection before timing out
* If the first 15 queries finish in 10 seconds, User #16 will actually succeed after waiting 10 seconds
* Else User #16 will receive a sqlalchemy.exc.TimeoutError

# Graceful Degradation for Redis Cache
* We treat the cache as strictly optional
* This means that if the cache server goes down or experiences OOM issues we only increment an error counter and return None 
* As the cache does not hit, the app will fall back to querying the database
* Redis Outages Handling: we will wrap all Redis calls in try/except blocks to ensure graceful degradation

# Observability
* We are completely blind from Cache Hit Rate
* So we will implement 3 Prometheus Counters:
    * cache_hits_total
    * cache_misses_total
    * cache_errors_total

# Preventing Cache Stampeed
* Use a pattern called "Probabilistic Early Expiration"
* Instead of waiting for exactly the TTL, the code flips a weighted coin starting at TTL - 1min
* One client gets a "cache miss" early, recalculates the data, and updates the cache before it actually expires, saving the other 49 users from hitting the DB

