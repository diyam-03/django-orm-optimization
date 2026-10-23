# QueryLab: Django ORM and Database Optimisation

Loads the REST Countries dataset into PostgreSQL through the Django ORM, finds and fixes an N+1 query problem, adds indexes, and measures every change with before and after timings.

**Live demo:** https://querylab-m11i.onrender.com

## What it shows

| Topic | Before | After |
|---|---|---|
| N+1 queries | 1 + 3N queries (751 for 250 countries) | 3 queries, using `select_related` and `prefetch_related` |
| Indexes | Sequential scan | Index scan (indexes on name, population, and region + population) |

The web page shows every SQL query Django runs for both versions, and a benchmark compares queries with and without indexes using `EXPLAIN ANALYZE`, including the cost of indexes (disk space and slower writes).

## Tech stack
Django, Django REST Framework, PostgreSQL, plain HTML/CSS/JavaScript. Deployed on Render.

## Run locally
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # add your REST Countries API key and database details
python manage.py migrate
python manage.py load_countries
python manage.py runserver    # open http://127.0.0.1:8000
```
A free API key is needed from https://restcountries.com/sign-up. To use 30 bundled sample countries instead: `python manage.py load_countries --offline`.

For a visible index speed-up, add test rows: `python manage.py load_countries --inflate 200000`.

## Useful commands
```bash
python manage.py benchmark   # before/after tables in the terminal
python manage.py test        # checks the query counts
```

## API
| Endpoint | Purpose |
|---|---|
| `/api/countries/slow/` | Unoptimised list (N+1) |
| `/api/countries/fast/` | Same data, optimised |
| `/api/benchmark/queries/` | Query count and timing comparison |
| `/api/benchmark/indexes/` | Index vs no index comparison |
| `/api/stats/` | Row counts |

## Project structure
- `countries/models.py`: tables and indexes
- `countries/seed.py`: loading API data with `bulk_create`
- `countries/serializers.py`: where the N+1 problem appears
- `countries/listing.py`: the optimised queryset
- `countries/benchmarks.py`: measurements
- `RESEARCH.md`: answers to the research questions

Data source: [REST Countries](https://restcountries.com/).