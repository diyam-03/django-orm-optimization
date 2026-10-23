# How to present this project (about 5 minutes)

## The one-sentence version
"I loaded country data into PostgreSQL with Django, showed that a normal-looking API makes 751
database queries per page, cut that to 3, then added indexes that made searches hundreds of times
faster, and measured what the indexes cost."

## Walk-through (follow the left rail on the page)

**1. The problem (1.5 min).** Open the page. Point at the two paper tapes: each line is one SQL
query Django sent. Left lane keeps printing, right lane stops after 3. Drag the slider: the slow
lane grows as 3N+1, the fast lane stays at 3. Say: "Same data, same JSON, only the queries differ."
Point at the colour bar: 1 list query, then region, language and currency lookups per country.

**2. The fix (1 min).** Show the two code blocks. `select_related("region")` joins in the same
query (one region per country). `prefetch_related("languages", "currencies")` runs one extra query
per relation for the whole page, because a country has many languages. Scroll to "real queries":
there are exactly 3.

**3. Indexes (1.5 min).** Press "Add 200,000 test rows" then "Run index benchmark". Explain that
indexes are invisible on 250 rows, so we add test data. Read one row: "Without index PostgreSQL read
all 200,000 rows (Seq Scan), 30 ms. With the index it jumped straight to the rows (Index Scan),
0.03 ms." Then the costs: extra disk and slower inserts. "It is a trade-off, not free."

**4. Research (1 min).** Open the three answers, or summarise them from RESEARCH.md.

## Architecture in 20 seconds
REST Countries API -> `load_countries` (bulk_create) -> PostgreSQL -> Django models -> DRF
endpoints (`slow` and `fast`) -> frontend. `listing.py` records every SQL statement; `benchmarks.py`
measures with `EXPLAIN ANALYZE`.

## Questions you might get

**Why not just always use prefetch_related?** select_related is cheaper for single-valued links:
one query and no second round trip.

**Is the benchmark fair?** Slow and fast run the same filters and serializer. Timings are medians of
5 runs after a warm-up. For indexes, the "without" run drops the indexes inside a transaction that is
rolled back, so the database is never actually changed. Execution time comes from `EXPLAIN ANALYZE`.

**Why did the speed-up on the web request look smaller than the query reduction?** Time is not just
queries: serialization and the base list query cost the same either way. Query count is the
reliable metric. Gains grow with network latency (a remote database makes every query dearer).

**Why add fake rows?** On a few hundred rows PostgreSQL reads the whole table faster than it can
use an index. The fake rows are flagged `is_synthetic` and hidden from the API lists.

**Why a composite index on (region, -population)?** The query "top countries in a region" filters
on region then sorts by population; one index serves both steps.

**What does bulk_create do?** Inserts many rows in few queries instead of one INSERT per row, so
loading is fast. M2M links are bulk inserted through the hidden "through" table.

**What would you do in production?** Use `django-debug-toolbar` or query logging to catch N+1 in
development, add tests that assert query counts (`assertNumQueries`), index based on real slow
queries (`pg_stat_statements`), and add indexes with `CREATE INDEX CONCURRENTLY` on busy tables.
