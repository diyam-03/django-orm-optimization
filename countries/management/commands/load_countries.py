import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from countries import seed

SAMPLE = Path(__file__).resolve().parents[2] / "fixtures" / "sample_countries.json"
SIGNUP = "https://restcountries.com/sign-up"


def get_json(url, api_key):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}", "User-Agent": "query-lab/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:300]
        hint = " The API key is missing or wrong." if exc.code == 401 else ""
        raise CommandError(f"API answered HTTP {exc.code}.{hint} {body}")
    except Exception as exc:
        raise CommandError(f"Could not reach the API ({exc}).")


def fetch_all(api_key, base_url):
    """Download every country, following the API's pages (100 per page on the free plan)."""
    countries, offset = [], 0
    while True:
        url = f"{base_url}?limit={seed.PAGE_SIZE}&offset={offset}&response_fields_omit=names.translations"
        page = get_json(url, api_key)
        if "errors" in page:
            raise CommandError("API returned an error: " + "; ".join(e.get("message", "?") for e in page["errors"]))
        data = page.get("data") or {}
        objects = data.get("objects") or []
        countries += objects
        if not objects or not (data.get("meta") or {}).get("more"):
            return countries
        offset += len(objects)


class Command(BaseCommand):
    help = "Load the REST Countries dataset into PostgreSQL through the Django ORM."

    def add_arguments(self, parser):
        parser.add_argument("--offline", action="store_true", help="Use the 30-country sample bundled in the repo.")
        parser.add_argument("--file", help="Load from a saved JSON file instead of the API.")
        parser.add_argument("--api-key", help="REST Countries API key (or set RESTCOUNTRIES_API_KEY in .env).")
        parser.add_argument("--inflate", type=int, default=0, metavar="N",
                            help="Also add N synthetic rows so index timings are measurable.")
        parser.add_argument("--reset-synthetic", action="store_true", help="Delete synthetic rows first.")

    def handle(self, *args, **opts):
        if opts["reset_synthetic"]:
            self.stdout.write(f"Removed {seed.remove_synthetic()} synthetic rows")

        if opts["offline"]:
            raw = json.loads(SAMPLE.read_text(encoding="utf-8"))
            self.stdout.write("Using bundled sample data (30 countries)")
        elif opts["file"]:
            raw = json.loads(Path(opts["file"]).read_text(encoding="utf-8"))
        else:
            key = opts["api_key"] or os.getenv("RESTCOUNTRIES_API_KEY")
            if not key:
                raise CommandError(
                    "No API key. REST Countries now needs a free key.\n"
                    f"  1. Sign up at {SIGNUP} and copy your key\n"
                    "  2. Put this line in a file named .env in the project folder:\n"
                    "         RESTCOUNTRIES_API_KEY=your_key_here\n"
                    "  3. Run this command again.\n"
                    "Or, to continue right now with 30 sample countries: python manage.py load_countries --offline"
                )
            base = os.getenv("RESTCOUNTRIES_URL", seed.API_URL)
            self.stdout.write("Fetching countries from restcountries.com ...")
            raw = fetch_all(key, base)
            self.stdout.write(f"Downloaded {len(raw)} records")

        try:
            stats = seed.import_countries(raw)
        except ValueError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(
            "Loaded {countries} countries, {regions} regions, {languages} languages, {currencies} currencies".format(**stats)
        ))
        if opts["inflate"]:
            seed.inflate(opts["inflate"])
            self.stdout.write(self.style.SUCCESS(f"Added {opts['inflate']} synthetic rows"))
