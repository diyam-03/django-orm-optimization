from django.core.management.base import BaseCommand

from countries import benchmarks


def mb(n):
    return f"{n / 1024 / 1024:.2f} MB"


class Command(BaseCommand):
    help = "Print before/after timings for the N+1 fix and for the indexes."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=250, help="Countries per page for the N+1 test.")
        parser.add_argument("--skip-indexes", action="store_true")

    def handle(self, *args, **opts):
        r = benchmarks.benchmark_queries(limit=opts["limit"])
        w = self.stdout.write
        w(f"\nPART 1: N+1 fix ({r['limit']} countries per page, median of {r['runs']} runs)")
        w(f"{'':14}{'queries':>9}{'db ms':>10}{'total ms':>11}")
        for label in ("slow", "fast"):
            m = r[label]
            name = "before (N+1)" if label == "slow" else "after (fixed)"
            w(f"{name:14}{m['query_count']:>9}{m['db_ms']:>10}{m['total_ms']:>11}")
        w(f"-> {r['query_reduction']}x fewer queries, {r['speedup']}x faster\n")

        if opts["skip_indexes"]:
            return
        i = benchmarks.benchmark_indexes()
        if not i["supported"]:
            w(i["reason"])
            return
        w(f"PART 2: indexes ({i['rows']:,} rows in countries_country)")
        if i["small_table"]:
            w("  Table is small, so PostgreSQL may ignore indexes. Run:")
            w("  python manage.py load_countries --offline --inflate 200000")
        w(f"{'query':54}{'before ms':>11}{'after ms':>10}{'speed-up':>10}")
        for t in i["tests"]:
            w(f"{t['title'][:52]:54}{t['before']['ms']:>11}{t['after']['ms']:>10}{str(t['speedup']) + 'x':>10}")
            w(f"    plan before: {t['before']['plan']}   |   after: {t['after']['plan']}")
        c = i["cost"]
        w(f"\nWhat the indexes cost:")
        w(f"  disk: {mb(c['index_total_bytes'])} of indexes next to a {mb(c['table_bytes'])} table")
        w(f"  writes: inserting {c['insert_rows']:,} rows takes {c['insert_without_ms']} ms without them, "
          f"{c['insert_with_ms']} ms with them ({c['insert_slowdown_pct']}% slower)")
