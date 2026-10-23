from django.conf import settings
from django.db import connection
from django.db.models import Count
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import benchmarks, seed
from .listing import MAX_LIMIT, run_listing
from .models import Country, Currency, Language, Region


@api_view(["GET"])
def countries_slow(request):
    """UNOPTIMISED. One query for countries, then 3 more per country (N+1)."""
    return Response(run_listing(request.query_params, optimised=False))


@api_view(["GET"])
def countries_fast(request):
    """OPTIMISED. select_related('region') + prefetch_related('languages', 'currencies')."""
    return Response(run_listing(request.query_params, optimised=True))


@api_view(["GET"])
def benchmark_queries(request):
    try:
        limit = max(1, min(MAX_LIMIT, int(request.query_params.get("limit", MAX_LIMIT))))
    except ValueError:
        limit = MAX_LIMIT
    return Response(benchmarks.benchmark_queries(limit=limit))


LOCKED = Response({"error": "Demo tools are disabled on this server (DEMO_TOOLS=0)."}, status=403)


@api_view(["GET"])
def benchmark_indexes(request):
    if not settings.DEMO_TOOLS:
        return LOCKED
    return Response(benchmarks.benchmark_indexes())


@api_view(["GET"])
def stats(request):
    """Small summary the frontend shows in its header."""
    real = Country.objects.filter(is_synthetic=False).count()
    synthetic = Country.objects.filter(is_synthetic=True).count()
    regions = list(
        Region.objects.filter(countries__is_synthetic=False)
        .annotate(n=Count("countries"))
        .order_by("-n")
        .values("name", "n")
    )
    return Response({
        "countries": real,
        "synthetic": synthetic,
        "regions": regions,
        "languages": Language.objects.count(),
        "currencies": Currency.objects.count(),
        "database": connection.vendor,
        "max_limit": MAX_LIMIT,
        "demo_tools": settings.DEMO_TOOLS,
    })


@api_view(["POST"])
def dataset(request):
    """Add or remove the synthetic rows used by the index demo."""
    if not settings.DEMO_TOOLS:
        return LOCKED
    action = request.data.get("action")
    if action == "inflate":
        try:
            rows = max(1000, min(500_000, int(request.data.get("rows", 200_000))))
        except (TypeError, ValueError):
            rows = 200_000
        seed.inflate(rows)
        return Response({"added": rows})
    if action == "reset":
        return Response({"removed": seed.remove_synthetic()})
    return Response({"error": "action must be 'inflate' or 'reset'"}, status=400)
