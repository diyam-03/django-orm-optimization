# Query Lab: Django ORM and Database Optimisation

Loads the REST Countries dataset into PostgreSQL through the Django ORM, finds and
fixes an N+1 query problem, adds indexes, and proves each fix with before/after
numbers. Includes a REST API (Django REST Framework) and a frontend that shows it live.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. PostgreSQL (pick one)
docker compose up -d                  # easiest
#   or create a database yourself: user=querylab password=querylab db=querylab
#   (or copy .env.example to .env and put your own credentials)

# 2. Tables and data
python manage.py migrate
python manage.py load_countries       # pulls ~250 countries from restcountries.com (needs a free API key, see below)
#   no key yet? python manage.py load_countries --offline   (30 bundled countries)

# 3. Run
python manage.py runserver            # open http://127.0.0.1:8000
```

The frontend is served by Django at `/`. To use a separate frontend instead, call the API
at `http://127.0.0.1:8000/api/` (CORS is enabled with django-cors-headers).

## REST Countries API key

REST Countries now requires a free API key.
1. Sign up at https://restcountries.com/sign-up and copy your key.
2. Copy `.env.example` to `.env` and set `RESTCOUNTRIES_API_KEY=your_key`.
3. `python manage.py load_countries` downloads all countries (100 per page, it follows the pages for you).

## Hosting

See `DEPLOY.md` for step-by-step deployment on Render (database and web service via `render.yaml`).

## The command-line proof

```bash
python manage.py load_countries --inflate 200000   # add fake rows so indexes matter
python manage.py benchmark                         # prints both before/after tables
python manage.py test                              # proves 1+3N queries vs 3
```

Indexes barely matter on 250 rows, so `--inflate` (or the button in the UI) adds 200,000
synthetic countries. They are flagged `is_synthetic` and hidden from the list endpoints.
Remove them any time with the "Remove test rows" button or `load_countries --reset-synthetic`.
For clean N+1 timings, remove them first: the N+1 query counts do not change, but the
list query itself gets slower on a big table.

## API

| Endpoint | What it does |
|---|---|
| `GET /api/countries/slow/` | Unoptimised list, N+1 queries |
| `GET /api/countries/fast/` | Same payload, `select_related` + `prefetch_related` |
| `GET /api/benchmark/queries/?limit=250` | Query count and timings, slow vs fast |
| `GET /api/benchmark/indexes/` | EXPLAIN ANALYZE with and without indexes, plus the costs |
| `GET /api/stats/` | Row counts, regions |
| `POST /api/dataset/` | `{"action":"inflate","rows":200000}` or `{"action":"reset"}` |

List filters: `limit`, `offset`, `search`, `name`, `region`, `min_population`,
`ordering` (`name`, `population`, with a `-` for descending), `include_synthetic=1`.
Every list response includes `meta.queries`: the exact SQL Django ran.

## Where things live

```
countries/models.py        Region, Country, Language, Currency + the 3 indexes (Meta.indexes)
countries/migrations/      0001 creates tables, 0002 adds the indexes (the "fix" as its own step)
countries/seed.py          loading data with bulk_create, inflating synthetic rows
countries/serializers.py   where the N+1 hides (obj.region.name, obj.languages.all())
countries/listing.py       slow vs fast queryset, query capture
countries/benchmarks.py    before/after measurement logic
countries/views.py         thin API layer
countries/templates + static/   the frontend (plain HTML, CSS, JS)
RESEARCH.md                answers to the three research questions
EXPLAIN.md                 a script for presenting this project
```
