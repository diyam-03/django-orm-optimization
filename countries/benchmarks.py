"""
Before / after measurements, shared by the API and the `benchmark` command.

Part 1  benchmark_queries()  N+1 vs select_related/prefetch_related
Part 2  benchmark_indexes()  same SQL with and without indexes (EXPLAIN ANALYZE)

Part 2 never leaves the database changed: the indexes are dropped INSIDE a
transaction that is rolled back at the end, and PostgreSQL DDL is transactional.
"""
import json
import statistics
import time

from django.db import connection, transaction

from .listing import run_listing
from .models import Country, Region
from .seed import synthetic_rows

INDEX_NAMES = ["ctry_name_idx", "ctry_pop_idx", "ctry_region_pop_idx"]
INSERT_ROWS = 5000


def _median(xs):
    return round(statistics.median(xs), 2)


# ---------------------------------------------------------------- part 1: N+1
def benchmark_queries(limit=250, runs=5):
    out = {}
    for optimised in (False, True):
        counts, totals, dbs = [], [], []
        run_listing({"limit": str(limit)}, optimised)  # warm-up, not counted
        for _ in range(runs):
            meta = run_listing({"limit": str(limit)}, optimised)["meta"]
            counts.append(meta["query_count"])
            totals.append(meta["total_ms"])
            dbs.append(meta["db_ms"])
        out["fast" if optimised else "slow"] = {
            "query_count": counts[0],
            "total_ms": _median(totals),
            "db_ms": _median(dbs),
        }
    out["limit"] = limit
    out["runs"] = runs
    out["query_reduction"] = round(out["slow"]["query_count"] / max(out["fast"]["query_count"], 1), 1)
    out["speedup"] = round(out["slow"]["total_ms"] / max(out["fast"]["total_ms"], 0.01), 1)
    return out


# --------------------------------------------------------------- part 2: index
def _plan_nodes(node):
    yield node
    for child in node.get("Plans", []):
        yield from _plan_nodes(child)


def _explain(qs, runs=5):
    """Return (median execution ms, scan description) using EXPLAIN (ANALYZE, FORMAT JSON)."""
    times, scan = [], "?"
    for i in range(runs + 1):  # first run warms the cache
        raw = qs.explain(analyze=True, format="json")
        plan = json.loads(raw) if isinstance(raw, str) else raw
        plan = plan[0] if isinstance(plan, list) else plan
        if i == 0:
            continue
        times.append(plan["Execution Time"])
        scans = [n for n in _plan_nodes(plan["Plan"]) if "Scan" in n["Node Type"]]
        if scans:
            n = scans[0]
            scan = n["Node Type"] + (f" using {n['Index Name']}" if "Index Name" in n else "")
    return _median(times), scan


def _tests():
    region = Region.objects.order_by("id").first()
    name = Country.objects.order_by("-id").values_list("name", flat=True).first() or ""
    return [
        {
            "key": "population",
            "title": "20 most populated countries over 100 million people",
            "sql": "WHERE population > 100000000 ORDER BY population DESC LIMIT 20",
            "qs": Country.objects.filter(population__gt=100_000_000).order_by("-population")[:20],
        },
        {
            "key": "name",
            "title": "Look up one country by its exact name",
            "sql": f"WHERE name = '{name}'",
            "qs": Country.objects.filter(name=name),
        },
        {
            "key": "region",
            "title": f"10 most populated countries in {region.name if region else 'a region'}",
            "sql": "WHERE region_id = … ORDER BY population DESC LIMIT 10",
            "qs": Country.objects.filter(region=region).order_by("-population")[:10],
        },
    ]


def _timed_insert(prefix):
    """Insert INSERT_ROWS rows, return milliseconds. Caller rolls the transaction back."""
    rows = synthetic_rows(INSERT_ROWS, prefix=prefix, start=0, seed=7)
    t = time.perf_counter()
    Country.objects.bulk_create(rows, batch_size=1000)
    return (time.perf_counter() - t) * 1000


def benchmark_indexes(runs=5, insert_runs=3):
    if connection.vendor != "postgresql":
        return {"supported": False, "reason": "Index benchmarks need PostgreSQL (EXPLAIN ANALYZE)."}

    total_rows = Country.objects.count()
    with connection.cursor() as cur:
        cur.execute("ANALYZE countries_country")

    tests = _tests()
    after = {t["key"]: _explain(t["qs"], runs) for t in tests}

    # Index sizes, measured while the indexes exist.
    with connection.cursor() as cur:
        cur.execute("SELECT pg_relation_size('countries_country')")
        table_bytes = cur.fetchone()[0]
        cur.execute(
            "SELECT c.relname, pg_relation_size(c.oid) FROM pg_class c WHERE c.relname = ANY(%s) ORDER BY c.relname",
            [INDEX_NAMES],
        )
        index_sizes = [{"name": n, "bytes": b} for n, b in cur.fetchall()]

    # Inserts WITH indexes (rolled back).
    with_ms = []
    for i in range(insert_runs):
        with transaction.atomic():
            with_ms.append(_timed_insert(f"BW{i}"))
            transaction.set_rollback(True)

    # Reads and inserts WITHOUT the three indexes (rolled back, so they come back).
    before, without_ms = {}, []
    with transaction.atomic():
        with connection.cursor() as cur:
            for name in INDEX_NAMES:
                cur.execute(f"DROP INDEX {name}")
            cur.execute("ANALYZE countries_country")
        before = {t["key"]: _explain(t["qs"], runs) for t in tests}
        transaction.set_rollback(True)
    for i in range(insert_runs):
        with transaction.atomic():
            with connection.cursor() as cur:
                for name in INDEX_NAMES:
                    cur.execute(f"DROP INDEX {name}")
            without_ms.append(_timed_insert(f"BN{i}"))
            transaction.set_rollback(True)

    results = []
    for t in tests:
        b_ms, b_scan = before[t["key"]]
        a_ms, a_scan = after[t["key"]]
        results.append({
            "key": t["key"], "title": t["title"], "sql": t["sql"],
            "before": {"ms": b_ms, "plan": b_scan},
            "after": {"ms": a_ms, "plan": a_scan},
            "speedup": round(b_ms / max(a_ms, 0.001), 1),
        })

    w, wo = _median(with_ms), _median(without_ms)
    return {
        "supported": True,
        "rows": total_rows,
        "small_table": total_rows < 20_000,
        "tests": results,
        "cost": {
            "table_bytes": table_bytes,
            "indexes": index_sizes,
            "index_total_bytes": sum(i["bytes"] for i in index_sizes),
            "insert_rows": INSERT_ROWS,
            "insert_with_ms": w,
            "insert_without_ms": wo,
            "insert_slowdown_pct": round((w / max(wo, 0.01) - 1) * 100),
        },
    }
