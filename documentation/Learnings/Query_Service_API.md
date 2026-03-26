# Various learnings during Query Service API development

 ## CQRS
 - CQRS stands for Command Query Responsibility Segregation
 - Decoupling the write path: Ingestion Service (API) -> Kafka Producer -> Worker (Kafka Consumer) -> Database
 - From the read path: Database -> Query Service (API) -> Cache -> UI
 - This ensures that the massive spikes in ingestion does not impact the dashboard & heavy analytical queries will not cause dropped events at the ingestion layer

 ## Benefits of Query Service (Query Validation)
 - Protects the database by implementing query validation (users requesting for 1 year of raw data at 1-second granularity)
 - Smart granularity selection (1m vs 1h based on time range): the query service can dynamically determines the granularity based on the requested time range
 - Independant scalability (Query Service can scale independently of the Ingestion Service)

 ## Use of Grafana vs Custom Frontend Dashboard
 - Grafana natively prefers to connect directly to TimescaleDB using its built-in PostgreSQL data source and expects to write SQL queries.
 - We could either use Grafana Infinity Data Source Plugin or the JSON API Plugin OR let Grafana connect directly DB (for admin use only) and use FastAPI Query Service to power a custom frontend dashboard
 - Using Query Service for custom Dashboard allows us to get caching, validation and rate limiting

 ## Time Series Caching with Redis
 - Caching time-series data is tricky because the latest data is always changing
- We need to avoid caching relative queries (now() - 24h)
- We can cache absolute time buckets: Round queries to the nearest minute or hour. If a user asks for data from 10:00 to 11:00, that result is immutable (if it's in the past) and highly cacheable.
- We can also split the query: for a query of "last 24 hours" we can fetch the historical 23.9 from Redis and only query the raw tail (last few minutes) from the DB

## Downsampling vs Pagination
- For dashboards pagination is an anti-pattern as a line chart is not able to plot page 1 and wait for a user click to plot page 2 -> Dashboards need the entire requested time window in one payload
- We can use downsampling instead: if a user requests 30 days of data, route the query to the 1h continous aggregation (720 points) and if the result is still too big for the response we can use an algorith such as LTTB (Largest Triangle Three Buckets) to reduce the number of points in TimescaleDB via the time_weight functions to downsample the visual representation exactly to the pixel width of the user's screen

## Connection Pooling
- Because FastAPI is highly concurrent (async), a sudden refresh of a dashboard with 15 panels will instantly open 15 concurrent database connections -> if we multiply that by 10 tenants, and Postgres will fall over
- We need to ensure we are using asyncpg combined with SQLAlchemy's async connection pooling with strict limits on maximum overflow connections

## Hot/Cold Split Pattern
- Old data is immutable so it's safe to use aggregates
- Recent data is still arriving so it's not safe to use aggregates and will need to use the raw table or frequently-refreshed aggregates

## Cache Invalidation
- For continuous aggregates: TTL = refresh_interval + safety margin
  - metrics_1min refreshes every 1 minute → TTL = 2 minutes
  - metrics_1hour refreshes every 15 minutes → TTL = 20 minutes
- For raw metrics: No caching (always fresh)
- Cache key versioning: Include schema version in key
  - `v1:metrics:acme:cpu:2026-03-06` 
  - Increment version when aggregate logic changes

## Rate Limiting
- Per-tenant limits: 100 requests/minute (prevent one tenant from monopolizing resources)
- Per-endpoint limits: /metrics → 1000 req/min, /heavy_query → 10 req/min
- Sliding window algorithm (not simple counter)
- Return 429 with Retry-After header

## Query Cost Estimation
Before executing, estimate cost:
- Time range × metric count × tenant count = estimated rows
- If estimated_rows > 100,000 → Reject or force downsampling
- Return 400 with message: "Query too large, try smaller time range or use hourly granularity"

# What can go wrong

## Full Table Scan
- User requests "all metrics for all tenants for all time"
- Query scans millions of rows
- Database CPU spikes to 100%
- Other queries slow down
**Solution:** Require time range of max 30 days

## Cache Stampede
- Popular query's cache expires
- 100 requests hit simultaneously
- All miss cache and hit DB
- Database overloaded
**Solution:** Cache warming, request coalescing

## Stale data
- Redis cache has old data
- Continuous aggregate refreshed
- User sees outdated metrics
**Solution:** Short TTL (1-5 minutes), or cache invalidation

