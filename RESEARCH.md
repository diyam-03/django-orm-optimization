# Research answers

## 1. What is the N+1 problem?

You run **1 query** to fetch a list of N rows, then **N more queries**, one per row, to fetch
something related to each row. Total: N+1 (here, 1 + 3N, because each country needs its
region, languages and currencies).

In Django it hides in ordinary code:

```python
for country in Country.objects.all():      # 1 query
    print(country.region.name)             # +1 query for EVERY country
```

Foreign keys and many-to-many managers are *lazy*: Django only queries them when you touch them.
Each query is tiny, but each costs a network round trip, SQL parsing and planning, so the cost
grows linearly with the number of rows. It is invisible with 10 rows and painful with 10,000.

**How to spot it:** query count that grows with page size (`CaptureQueriesContext`,
`django-debug-toolbar`, or the tape in this project's frontend).

**In this project:** 250 countries on the slow endpoint = 1 + 250 + 250 + 250 = **751 queries**.
The fast endpoint needs **3**.

## 2. select_related vs prefetch_related

| | `select_related` | `prefetch_related` |
|---|---|---|
| Works on | ForeignKey, OneToOne (single-valued) | ManyToMany, reverse FK (multi-valued) |
| How | One query with a SQL `JOIN` | Separate query per relation, `WHERE id IN (...)`, joined in Python |
| Queries added | 0 (same query) | 1 per relation |
| Why not use the other | A join on a many-to-many repeats the parent row once per child, wasting data | A single-valued link is cheaper as a JOIN |
| Here | `region` | `languages`, `currencies` |

```python
Country.objects.select_related("region").prefetch_related("languages", "currencies")
```

## 3. How does an index speed up a query, and what does it cost?

**Speed-up.** Without an index, PostgreSQL does a *sequential scan*: it reads every row to find
matches, so time grows with table size. A B-tree index keeps the column values sorted with pointers
to the rows, so PostgreSQL can jump straight to matches (an *index scan*) in roughly logarithmic time.
It is the index at the back of a book. For `ORDER BY population DESC LIMIT 20` the index even hands
back rows already sorted, so no sorting is needed.

**Costs.**
1. **Disk space.** Each index is a separate structure stored on disk (and cached in RAM).
2. **Slower writes.** Every `INSERT`, `UPDATE` of an indexed column and `DELETE` must also update
   every index on the table.
3. **Maintenance.** More to vacuum and keep in memory; the planner has more choices to make.

**Rule of thumb.** Index columns you frequently filter, join or sort by on large tables.
Do not index everything, columns with very few distinct values, or tiny tables (PostgreSQL will
ignore the index there anyway).

**Measured in this project** (200,030 rows, your numbers will differ slightly): reads 575x to
1,480x faster, about 21 MB of extra disk for three indexes, and inserts about 15 to 20% slower.
