from django.urls import path

from . import views

urlpatterns = [
    path("stats/", views.stats),
    path("countries/slow/", views.countries_slow),
    path("countries/fast/", views.countries_fast),
    path("benchmark/queries/", views.benchmark_queries),
    path("benchmark/indexes/", views.benchmark_indexes),
    path("dataset/", views.dataset),
]
