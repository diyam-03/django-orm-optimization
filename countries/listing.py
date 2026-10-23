"""
One function builds the country list, in two flavours:

    optimised=False  -> plain queryset   -> N+1 queries
    optimised=True   -> select_related + prefetch_related -> a handful of queries

Everything runs inside CaptureQueriesContext, so we can report the exact SQL that
Django sent to PostgreSQL. That is what the frontend draws as the "query tape".
"""
import re
import time

from django.db import connection
from django.test.utils import CaptureQueriesContext

from .models import Country
from .serializers import CountrySerializer

ORDERINGS = {"name": "name", "-name": "-name", "population": "population", "-population": "-population"}
MAX_LIMIT = 250
MAX_TAPE = 1200  # cap on SQL lines returned to the browser


def build_queryset(params):
    qs = Country.objects.all()
    if params.get("include_synthetic") != "1":
        qs = qs.filter(is_synthetic=False)
    if params.get("search"):
        qs = qs.filter(name__icontains=params["search"])
    if params.get("name"):
        qs = qs.filter(name=params["name"])
    if params.get("region"):
        qs = qs.filter(region__name=params["region"])
    if params.get("min_population", "").isdigit():
        qs = qs.filter(population__gte=int(params["min_population"]))
    return qs.order_by(ORDERINGS.get(params.get("ordering"), "name"), "id")


def _int(value, default, lo, hi):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _describe(sql):
    """Return (table, kind, short_sql) so the UI can colour and label each query."""
    m = re.search(r'FROM "([a-z_]+)"', sql)
    raw_table = m.group(1) if m else "?"
    table = {
        "countries_country": "countries",
        "countries_region": "region",
        "countries_language": "languages",
        "countries_currency": "currencies",
    }.get(raw_table, raw_table)
    if table == "countries":
        kind = "join" if "JOIN" in sql.split("WHERE")[0] else "main"
    elif " IN (" in sql:
        kind = "prefetch"
    else:
        kind = "lazy"
    short = re.sub(r"^SELECT (DISTINCT )?.*? FROM ", lambda mm: f"SELECT {mm.group(1) or ''}… FROM ", sql)
    short = short.replace('"', "")
    short = re.sub(r"IN \([^)]{30,}\)", "IN (…)", short)
    return table, kind, (short[:230] + "…") if len(short) > 230 else short


def run_listing(params, optimised):
    qs = build_queryset(params)
    total = qs.count()  # outside the capture: it is pagination, not part of the demo
    limit = _int(params.get("limit"), 50, 1, MAX_LIMIT)
    offset = _int(params.get("offset"), 0, 0, 10**7)

    if optimised:
        qs = qs.select_related("region").prefetch_related("languages", "currencies")

    # CaptureQueriesContext gives us the SQL text; its timings are rounded to 1 ms,
    # which hides fast queries, so a small wrapper times each query precisely.
    durations = []

    def timer(execute, sql, params, many, context):
        t = time.perf_counter()
        try:
            return execute(sql, params, many, context)
        finally:
            durations.append((time.perf_counter() - t) * 1000)

    with CaptureQueriesContext(connection) as ctx, connection.execute_wrapper(timer):
        start = time.perf_counter()
        rows = list(qs[offset : offset + limit])
        data = list(CountrySerializer(rows, many=True).data)
        total_ms = (time.perf_counter() - start) * 1000

    queries = []
    for q, ms in list(zip(ctx.captured_queries, durations))[:MAX_TAPE]:
        table, kind, short = _describe(q["sql"])
        queries.append({"table": table, "kind": kind, "ms": round(ms, 2), "sql": short})

    meta = {
        "mode": "fast" if optimised else "slow",
        "count": total,
        "returned": len(data),
        "query_count": len(ctx.captured_queries),
        "db_ms": round(sum(durations), 2),
        "total_ms": round(total_ms, 2),
        "tape_truncated": len(ctx.captured_queries) > MAX_TAPE,
        "queries": queries,
    }
    return {"meta": meta, "results": data}
