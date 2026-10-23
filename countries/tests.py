"""
The tests double as proof of the project's claim: query COUNT is what changes.
Run with:  python manage.py test
"""
import json
from pathlib import Path

from django.test import TestCase

from . import seed
from .listing import run_listing
from .models import Country

SAMPLE = Path(__file__).parent / "fixtures" / "sample_countries.json"


class QueryCountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.raw = json.loads(SAMPLE.read_text(encoding="utf-8"))
        seed.import_countries(cls.raw)

    def test_loader_is_idempotent(self):
        before = Country.objects.count()
        seed.import_countries(self.raw)
        self.assertEqual(Country.objects.count(), before)

    def test_slow_endpoint_is_n_plus_one(self):
        meta = run_listing({"limit": "30"}, optimised=False)["meta"]
        # 1 list query + 3 lookups (region, languages, currencies) per country
        self.assertEqual(meta["query_count"], 1 + 3 * meta["returned"])

    def test_fast_endpoint_uses_three_queries(self):
        meta = run_listing({"limit": "30"}, optimised=True)["meta"]
        # 1 query with a JOIN for region + 1 prefetch each for languages and currencies
        self.assertEqual(meta["query_count"], 3)

    def test_both_endpoints_return_identical_data(self):
        slow = run_listing({"limit": "30"}, optimised=False)["results"]
        fast = run_listing({"limit": "30"}, optimised=True)["results"]
        self.assertEqual(slow, fast)

    def test_api_routes(self):
        for path in ("/api/stats/", "/api/countries/slow/?limit=5", "/api/countries/fast/?limit=5&ordering=-population"):
            self.assertEqual(self.client.get(path).status_code, 200)


class ApiFormatTests(TestCase):
    """REST Countries moved to a v5 format (needs an API key). Both formats must load."""

    V5_PAGE = {"data": {"objects": [{
        "names": {"common": "Canada"}, "codes": {"alpha_3": "CAN"},
        "capitals": [{"name": "Ottawa"}], "region": "Americas", "population": 38005238,
        "area": {"kilometers": 9984670}, "flag": {"emoji": "CA"},
        "languages": [{"name": "English", "iso639_3": "eng"}, {"name": "French", "iso639_3": "fra"}],
        "currencies": [{"code": "CAD", "name": "Canadian dollar", "symbol": "$"}],
    }], "meta": {"more": False}}}

    def test_v5_page_loads(self):
        stats = seed.import_countries(self.V5_PAGE)
        self.assertEqual(stats["countries"], 1)
        canada = Country.objects.get(cca3="CAN")
        self.assertEqual(canada.capital, "Ottawa")
        self.assertEqual(sorted(l.name for l in canada.languages.all()), ["English", "French"])
        self.assertEqual([c.code for c in canada.currencies.all()], ["CAD"])

    def test_error_response_is_reported_clearly(self):
        with self.assertRaises(ValueError):
            seed.import_countries({"errors": [{"message": "Invalid API key"}]})
